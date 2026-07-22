"""Read-only preparation precondition and owner post-effect validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cycle_ledger import read_initialization_metadata
from .artifact_store import load_compiler_artifact
from .contracts import (
    PREPARATION_SCHEMA_VERSION_V3,
    canonical_bytes,
    canonical_sha256,
    require_expected_preparation,
    stale_preparation_result,
    validate_preparation,
)
from .executor_registry import allowed_post_effect_selectors
from .preparation_v3 import prepare_v2, render_preparation
from .specs import TARGET_COMPILE_SPECS
from .v2_context import (
    collect_selected_context,
    render_machine_input,
    render_work_order,
    selected_state_fingerprint,
)


_MACHINE_MODEL_KEYS = (
    "projection_status",
    "stop_reason",
    "workspace",
    "task",
    "goal_truth",
    "advice",
    "cycle",
    "selection_publication",
    "authority",
    "pending_runs",
    "git",
    "diagnostic_artifacts",
)

_EXACT_CHANGED_FILE_TARGETS = frozenset({"governance", "visible_increment"})
_HEX = frozenset("0123456789abcdef")


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def load_bound_material(
    root: Path, preparation: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    cycle_id = str(preparation["cycle_id"])
    if preparation.get("schema_version") == PREPARATION_SCHEMA_VERSION_V3 and (
        preparation.get("executor_kind") == "deterministic"
    ):
        machine = load_compiler_artifact(
            root, cycle_id, preparation["machine_input_binding"], "machine_input"
        )
        if (
            machine.get("cycle_id") != cycle_id
            or machine.get("target") != preparation["target"]
            or machine.get("state_fingerprint") != preparation["state_fingerprint"]
        ):
            raise ValueError("machine input binding scope does not match preparation")
        return machine, None
    context = load_compiler_artifact(
        root, cycle_id, preparation["context_binding"], "context"
    )
    work_order = load_compiler_artifact(
        root, cycle_id, preparation["work_order_binding"], "work_order"
    )
    for value, label in ((context, "context"), (work_order, "work_order")):
        if value.get("cycle_id") != cycle_id or value.get("target") != preparation["target"]:
            raise ValueError(f"{label} binding scope does not match preparation")
        if value.get("state_fingerprint") != preparation["state_fingerprint"]:
            raise ValueError(f"{label} state fingerprint does not match preparation")
    if work_order.get("context_binding") != preparation["context_binding"]:
        raise ValueError("work_order context binding does not match preparation")
    return context, work_order


def _task_id(root: Path, cycle_id: str) -> str | None:
    value = read_initialization_metadata(root, cycle_id).get("task_id")
    return str(value) if value is not None and str(value).strip() else None


def _machine_model(machine: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "orchestrate_model_context",
        **{key: machine.get(key) for key in _MACHINE_MODEL_KEYS},
    }


def _bound_model(material: dict[str, Any], deterministic: bool) -> dict[str, Any]:
    value = _machine_model(material) if deterministic else material.get("model_context")
    if not isinstance(value, dict):
        raise ValueError("preparation-bound model context is invalid")
    return value


def _git_worktree_entries(
    model: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], str | None]:
    git = model.get("git") if isinstance(model.get("git"), dict) else {}
    changed = git.get("changed_paths")
    identity = git.get("worktree_identity")
    if not isinstance(changed, dict) or not isinstance(identity, dict):
        return {}, "incomplete"
    if identity.get("binding_status") != "exact":
        return {}, "incomplete"
    paths = changed.get("items")
    items = identity.get("items")
    if not isinstance(paths, list) or not isinstance(items, list):
        return {}, "incomplete"
    total_count = identity.get("total_count")
    included_count = identity.get("included_count")
    truncated = identity.get("truncated")
    if (
        identity.get("schema_version") != 1
        or identity.get("item_alignment") != "git.changed_paths.items"
        or identity.get("error_codes") != []
        or type(total_count) is not int
        or type(included_count) is not int
        or type(truncated) is not bool
        or total_count < 0
        or included_count < 0
        or included_count != len(items)
        or changed.get("included_count") != len(paths)
        or total_count != changed.get("total_count")
        or included_count != changed.get("included_count")
        or truncated != changed.get("truncated")
        or len(paths) != len(items)
        or not all(isinstance(path, str) and path for path in paths)
    ):
        return {}, "incomplete"
    if len(set(paths)) != len(paths):
        return {}, "incomplete"
    path_digest = identity.get("path_set_sha256")
    if (
        not _is_sha256(path_digest)
        or path_digest != changed.get("set_sha256")
        or (not truncated and path_digest != canonical_sha256(paths))
    ):
        return {}, "incomplete"
    rows: dict[str, dict[str, Any]] = {}
    expected_fields = {
        "status",
        "kind",
        "mode",
        "size_bytes",
        "content_sha256",
        "index_identity_sha256",
    }
    for path, item in zip(paths, items, strict=True):
        if not isinstance(item, dict) or set(item) != expected_fields:
            return {}, "incomplete"
        if (
            not isinstance(item.get("status"), str)
            or len(item["status"]) != 2
            or item.get("kind") not in {"regular_file", "symlink", "missing"}
            or not _is_sha256(item.get("index_identity_sha256"))
        ):
            return {}, "incomplete"
        if item["kind"] == "missing":
            if any(item.get(key) is not None for key in ("mode", "size_bytes", "content_sha256")):
                return {}, "incomplete"
        elif (
            not isinstance(item.get("mode"), str)
            or len(item["mode"]) != 6
            or any(character not in "01234567" for character in item["mode"])
            or type(item.get("size_bytes")) is not int
            or item["size_bytes"] < 0
            or not _is_sha256(item.get("content_sha256"))
        ):
            return {}, "incomplete"
        rows[path] = item
    inventory_digest = identity.get("inventory_sha256")
    if not _is_sha256(inventory_digest):
        return {}, "incomplete"
    if truncated:
        return rows, "truncated"
    material = {
        "repository_state": identity.get("repository_state"),
        "entries": [{"path": path, **rows[path]} for path in paths],
    }
    if canonical_sha256(material) != inventory_digest:
        return {}, "incomplete"
    return rows, None


def validate_owner_post_effect_claims(
    preparation: dict[str, Any],
    freshness: dict[str, Any],
    owner_result: Any,
) -> dict[str, Any] | None:
    """Reject allowed selector movement that exceeds an exact owner path claim."""

    target = str(preparation["target"])
    changed = set(freshness.get("changed_precondition_selectors") or [])
    if target not in _EXACT_CHANGED_FILE_TARGETS or not changed:
        return None
    owner = owner_result if isinstance(owner_result, dict) else {}
    claimed_value = owner.get("changed_files")
    claimed = (
        {str(item) for item in claimed_value}
        if isinstance(claimed_value, list)
        else set()
    )
    mismatches: list[str] = []
    if "task" in changed and "task.md" not in claimed:
        mismatches.append("task_effect_not_claimed")
    if "git_worktree" in changed:
        material = freshness.get("bound_material")
        current = freshness.get("model_context")
        if not isinstance(material, dict) or not isinstance(current, dict):
            mismatches.append("post_effect_context_unavailable")
        else:
            before = _bound_model(material, False)
            before_entries, before_scope = _git_worktree_entries(before)
            after_entries, after_scope = _git_worktree_entries(current)
            if "incomplete" in {before_scope, after_scope}:
                mismatches.append("git_effect_scope_incomplete")
            elif "truncated" in {before_scope, after_scope}:
                mismatches.append("git_effect_scope_truncated")
            else:
                effect_paths = {
                    path
                    for path in set(before_entries) | set(after_entries)
                    if before_entries.get(path) != after_entries.get(path)
                }
                before_identity = (
                    (before.get("git") or {}).get("worktree_identity") or {}
                )
                after_identity = (
                    (current.get("git") or {}).get("worktree_identity") or {}
                )
                if (
                    not effect_paths
                    and before_identity.get("inventory_sha256")
                    != after_identity.get("inventory_sha256")
                ):
                    mismatches.append("git_effect_delta_unattributed")
                elif effect_paths != claimed:
                    mismatches.append("git_effect_paths_differ_from_owner_claim")
    if not mismatches:
        return None
    return {
        **stale_preparation_result(
            preparation, str(freshness.get("actual_state_fingerprint") or "")
        ),
        "freshness_status": "post_effect_owner_claim_mismatch",
        "changed_precondition_selectors": sorted(changed),
        "post_effect_claim_mismatches": mismatches,
    }


def _bound_preparation(
    root: Path,
    preparation: dict[str, Any],
    material: dict[str, Any],
    work_order: dict[str, Any] | None,
) -> dict[str, Any]:
    deterministic = preparation.get("executor_kind") == "deterministic"
    model = _bound_model(material, deterministic)
    context_metrics = material.get("context_metrics")
    fingerprints = material.get("precondition_fingerprints")
    if not isinstance(context_metrics, dict) or not isinstance(fingerprints, dict):
        raise ValueError("v3 compiler artifact lacks precondition evidence")
    if fingerprints != preparation.get("precondition_fingerprints"):
        raise ValueError("preparation preconditions differ from compiler artifact")
    spec = TARGET_COMPILE_SPECS[str(preparation["target"])]
    if deterministic:
        expected_material = render_machine_input(
            str(preparation["cycle_id"]),
            str(preparation["target"]),
            str(preparation["workflow_mode"]),
            model,
            str(preparation["state_fingerprint"]),
            context_metrics,
            fingerprints,
        )
        if canonical_bytes(material) != canonical_bytes(expected_material):
            raise ValueError("v3 machine input differs from compiler rendering")
    else:
        expected_material = {
            "schema_version": 1,
            "artifact_kind": "orchestrate_stage_context",
            "cycle_id": preparation["cycle_id"],
            "target": preparation["target"],
            "dependency_selectors": list(spec.dependency_selectors),
            "state_fingerprint": preparation["state_fingerprint"],
            "context_metrics": context_metrics,
            "precondition_fingerprints": fingerprints,
            "model_context": model,
        }
        if canonical_bytes(material) != canonical_bytes(expected_material):
            raise ValueError("v3 context differs from compiler rendering")
        expected_work_order = render_work_order(
            str(preparation["cycle_id"]),
            str(preparation["target"]),
            str(preparation["workflow_mode"]),
            spec,
            model,
            str(preparation["state_fingerprint"]),
            preparation["context_binding"],
            fingerprints,
        )
        if canonical_bytes(work_order) != canonical_bytes(expected_work_order):
            raise ValueError("v3 work order differs from compiler rendering")
    binding_keys = (
        ("machine_input_binding",)
        if deterministic
        else ("context_binding", "work_order_binding")
    )
    bindings = {key: preparation[key] for key in binding_keys}
    expected = render_preparation(
        str(preparation["cycle_id"]),
        str(preparation["target"]),
        str(preparation["workflow_mode"]),
        _task_id(root, str(preparation["cycle_id"])),
        model,
        context_metrics,
        bindings,
        fingerprints,
        schema_version=PREPARATION_SCHEMA_VERSION_V3,
    )
    require_expected_preparation(preparation, expected)
    # Actual CAS write/reuse counters are intentionally outside preparation
    # identity; preserve the supplied receipt metrics after stable rendering.
    return preparation


def _stale(
    preparation: dict[str, Any],
    actual_fingerprint: str,
    changed: tuple[str, ...],
    disallowed: tuple[str, ...],
) -> dict[str, Any]:
    return {
        **stale_preparation_result(preparation, actual_fingerprint),
        "freshness_status": "stale_precondition",
        "changed_precondition_selectors": list(changed),
        "disallowed_post_effect_selectors": list(disallowed),
    }


def evaluate_preparation_freshness(
    root: Path,
    preparation: dict[str, Any],
    *,
    max_files: int,
    max_paths: int,
    allow_post_effect: bool,
) -> dict[str, Any]:
    """Reopen the prestate and compare exact selector boundaries without writes."""

    supplied = validate_preparation(preparation)
    material, work_order = load_bound_material(root, supplied)
    cycle_id, target = str(supplied["cycle_id"]), str(supplied["target"])
    spec = TARGET_COMPILE_SPECS[target]
    full, model, observed_metrics = collect_selected_context(
        root, cycle_id, spec, max_files=max_files, max_paths=max_paths
    )
    current_metrics = dict(observed_metrics)
    current_preconditions = current_metrics.pop("precondition_fingerprints")
    actual_fingerprint = selected_state_fingerprint(
        model, spec.dependency_selectors
    )
    if supplied.get("schema_version") != PREPARATION_SCHEMA_VERSION_V3:
        if actual_fingerprint != supplied["state_fingerprint"]:
            return _stale(supplied, actual_fingerprint, (), ())
        expected = prepare_v2(
            root,
            cycle_id,
            target,
            str(supplied["workflow_mode"]),
            _task_id(root, cycle_id),
            max_files=max_files,
            max_paths=max_paths,
            schema_version=int(supplied["schema_version"]),
        )
        supplied = require_expected_preparation(supplied, expected)
        changed: tuple[str, ...] = ()
    else:
        supplied = _bound_preparation(root, supplied, material, work_order)
        before = supplied["precondition_fingerprints"]
        changed = tuple(
            sorted(
                selector
                for selector in before
                if current_preconditions.get(selector) != before[selector]
            )
        )
        allowed = (
            set(allowed_post_effect_selectors(target))
            if allow_post_effect
            else set()
        )
        disallowed = tuple(selector for selector in changed if selector not in allowed)
        if disallowed or (not changed and actual_fingerprint != supplied["state_fingerprint"]):
            return _stale(supplied, actual_fingerprint, changed, disallowed)
    return {
        "status": "ok",
        "freshness_status": (
            "post_effect_pending_owner_validation"
            if changed
            else "exact_precondition"
        ),
        "changed_precondition_selectors": list(changed),
        "actual_state_fingerprint": actual_fingerprint,
        "preparation": supplied,
        "bound_material": material,
        "work_order": work_order,
        "full_context": full,
        "model_context": model,
    }


__all__ = [
    "evaluate_preparation_freshness",
    "load_bound_material",
    "validate_owner_post_effect_claims",
]
