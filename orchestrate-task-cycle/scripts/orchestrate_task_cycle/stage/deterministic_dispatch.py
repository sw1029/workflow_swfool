"""Allowlisted native dispatchers for the seven deterministic stage targets."""

from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Any, Callable

from ..adapter_architecture.native import build_code_structure_packet
from ..code_structure_audit import DEFAULT_THRESHOLDS, audit
from ..collect_cycle_context import collect_task
from ..cycle_ledger import read_current_expanded, read_events
from ..profile_cycle_efficiency import analyze
from ..repo_skill_adapter import scan_repo_skill_adapters
from ..render_cycle_dashboard import render_summary, summarize
from ..assemble_cycle_report import assemble
from ..ledger.support import read_initialization_metadata
from ..ledger.workflow_contract import require_cycle_mutation_contract
from .artifact_store import (
    compiler_artifact_binding,
)
from .contracts import (
    canonical_bytes,
    canonical_sha256,
    require_expected_preparation,
    stale_preparation_result,
)
from .executor_registry import executor_spec
from .preparation_v3 import render_preparation
from .specs import TARGET_COMPILE_SPECS
from .v2_context import (
    collect_selected_context,
    render_machine_input,
    selected_state_fingerprint,
)


Renderer = Callable[[Path, dict[str, Any], dict[str, Any]], dict[str, Any]]


def _repo_scan(
    root: Path, preparation: dict[str, Any], _machine: dict[str, Any]
) -> dict[str, Any]:
    return scan_repo_skill_adapters(root, cycle_id=str(preparation["cycle_id"]))


def _adapter_validate(
    root: Path, preparation: dict[str, Any], machine: dict[str, Any]
) -> dict[str, Any]:
    cycle_id = str(preparation["cycle_id"])
    scan = scan_repo_skill_adapters(root, cycle_id=cycle_id)
    blockers = list(scan.get("blockers") or [])
    changed = list(((machine.get("git") or {}).get("changed_paths") or {}).get("items") or [])
    adapter_changes = [path for path in changed if str(path).startswith(".codex/skills/")]
    revision = canonical_sha256(scan.get("repo_skill_adapter_packet") or {})
    packet = {
        "schema_version": 2,
        "artifact_kind": "repo_skill_adapter_validation_packet",
        "step": "repo_skill_adapter_validate",
        "cycle_id": cycle_id,
        "task_id": (preparation.get("derived_values") or {}).get("task_id"),
        "adapter_validation_status": "block" if blockers else "pass",
        "adapter_consumability_status": "block" if blockers else "pass",
        "adapter_architecture_status": "not_applicable",
        "adapter_change_count": len(adapter_changes),
        "adapter_validation_count": int(scan.get("adapter_count") or 0),
        "adapter_revision_before_sha256": revision,
        "adapter_revision_after_sha256": revision,
        "adapter_architecture": {
            "mode": "static_manifest_validation",
            "raw_source_persisted": False,
        },
        "field_origins": {
            "adapter_validation_status": "deterministic_adjudication",
            "adapter_change_count": "git_path_projection",
            "adapter_validation_count": "adapter_scan",
        },
        "blockers": blockers,
        "evidence_paths": list(scan.get("evidence_paths") or []),
    }
    packet["validation_packet_sha256"] = hashlib.sha256(
        canonical_bytes(packet) + b"\n"
    ).hexdigest()
    return packet


def _changed_source_paths(machine: dict[str, Any]) -> list[str]:
    paths = list(((machine.get("git") or {}).get("changed_paths") or {}).get("items") or [])
    return [str(path) for path in paths if Path(str(path)).suffix]


def _code_structure(
    root: Path, preparation: dict[str, Any], machine: dict[str, Any]
) -> dict[str, Any]:
    result = audit(
        root,
        _changed_source_paths(machine),
        dict(DEFAULT_THRESHOLDS),
        (preparation.get("derived_values") or {}).get("task_id"),
    )
    result = _allowed_owner_fields("code_structure_audit", result)
    return build_code_structure_packet(
        cycle_id=str(preparation["cycle_id"]), result=result
    )


def _repo_gap(
    root: Path, preparation: dict[str, Any], _machine: dict[str, Any]
) -> dict[str, Any]:
    state = collect_task(root, 64)
    misses = state.get("task_miss") or {}
    active = int(misses.get("active_count") or 0)
    files = [
        item.get("path")
        for item in misses.get("files") or []
        if isinstance(item, dict) and item.get("path")
    ]
    return {
        "gap_analysis_status": "pass",
        "gap_count": active,
        "repo_skill_gap_packet": {
            "schema_version": 1,
            "active_task_miss_count": active,
            "recommendation": "select" if active else "defer",
            "candidate_refs": files,
            "not_goal_truth": True,
        },
        "blockers": [],
        "evidence_paths": files,
    }


def _efficiency(
    root: Path, preparation: dict[str, Any], _machine: dict[str, Any]
) -> dict[str, Any]:
    events = read_events(root, str(preparation["cycle_id"]))
    result = analyze(
        root,
        events,
        [],
        (preparation.get("derived_values") or {}).get("task_id"),
    )
    return _allowed_owner_fields("cycle_efficiency_profile", result)


def _dashboard(
    root: Path, preparation: dict[str, Any], _machine: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    cycle_id = str(preparation["cycle_id"])
    events = read_events(root, cycle_id)
    current = read_current_expanded(root, cycle_id)
    result = summarize(events, current, "loaded", cycle_id, root)
    path = root / ".task" / "cycle" / cycle_id / "dashboard.md"
    content = render_summary(result)
    result["dashboard_path"] = path.relative_to(root).as_posix()
    result["evidence_paths"] = list(result.get("evidence_paths") or []) + [
        result["dashboard_path"]
    ]
    return _allowed_owner_fields("dashboard", result), {
        "kind": "write_text",
        "ref": path.relative_to(root).as_posix(),
        "content": content,
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def _latest(events: list[dict[str, Any]], step: str) -> dict[str, Any]:
    return next((event for event in reversed(events) if event.get("step") == step), {})


def _report(
    root: Path, preparation: dict[str, Any], machine: dict[str, Any]
) -> dict[str, Any]:
    cycle_id = str(preparation["cycle_id"])
    events = read_events(root, cycle_id)
    stage = read_current_expanded(root, cycle_id)
    context = {
        "cycle_state": {"latest_events": events},
        "goal_truth": machine.get("goal_truth"),
        "advice": machine.get("advice"),
    }
    result = assemble(
        context,
        stage,
        _latest(events, "validate"),
        _latest(events, "loopback_audit"),
        _latest(events, "commit"),
        _latest(events, "closeout_commit"),
    )
    return _allowed_owner_fields("report", result)


def _allowed_owner_fields(target: str, value: dict[str, Any]) -> dict[str, Any]:
    spec = TARGET_COMPILE_SPECS[target]
    allowed = set(spec.owner_receipt_fields) | set(spec.optional_owner_fields)
    return {key: item for key, item in value.items() if key in allowed}


_RENDERERS: dict[str, Renderer] = {
    "repo_skill_adapter_scan": _repo_scan,
    "repo_skill_adapter_validate": _adapter_validate,
    "code_structure_audit": _code_structure,
    "repo_skill_gap_analysis": _repo_gap,
    "cycle_efficiency_profile": _efficiency,
    "report": _report,
}


def _current_machine_input(
    root: Path,
    preparation: dict[str, Any],
    *,
    max_files: int,
    max_paths: int,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any] | None,
]:
    cycle_id, target = (
        str(preparation["cycle_id"]),
        str(preparation["target"]),
    )
    spec = TARGET_COMPILE_SPECS[target]
    full, model, observed = collect_selected_context(
        root, cycle_id, spec, max_files=max_files, max_paths=max_paths
    )
    metrics = dict(observed)
    fingerprints = metrics.pop("precondition_fingerprints")
    fingerprint = selected_state_fingerprint(
        model, spec.dependency_selectors
    )
    before = preparation.get("precondition_fingerprints") or {}
    changed = sorted(
        selector
        for selector in before
        if fingerprints.get(selector) != before[selector]
    )
    if changed or fingerprint != preparation.get("state_fingerprint"):
        return full, {}, {
            **stale_preparation_result(preparation, fingerprint),
            "freshness_status": "stale_precondition",
            "changed_precondition_selectors": changed,
            "disallowed_post_effect_selectors": changed,
            "model_call_count": 0,
            "model_visible_bytes": 0,
            "files_written_count": 0,
        }
    machine = render_machine_input(
        cycle_id,
        target,
        str(preparation["workflow_mode"]),
        model,
        fingerprint,
        metrics,
        fingerprints,
    )
    raw_binding = compiler_artifact_binding(
        root,
        cycle_id,
        "machine_input",
        machine,
        persist=False,
    )
    binding = {
        key: raw_binding[key]
        for key in ("artifact_type", "ref", "sha256", "size_bytes")
    }
    expected = render_preparation(
        cycle_id,
        target,
        str(preparation["workflow_mode"]),
        (read_initialization_metadata(root, cycle_id).get("task_id")),
        model,
        metrics,
        {"machine_input_binding": binding},
        fingerprints,
        schema_version=int(preparation["schema_version"]),
        compiler_io_receipts=(raw_binding["compiler_io_receipt"],),
    )
    require_expected_preparation(preparation, expected)
    return full, machine, None


def predict_deterministic(
    root: Path,
    preparation: dict[str, Any],
    *,
    max_files: int = 12,
    max_paths: int = 40,
) -> dict[str, Any]:
    """Render one deterministic result and effect plan without writing."""

    target = str(preparation["target"])
    require_cycle_mutation_contract(
        read_initialization_metadata(
            root, str(preparation["cycle_id"])
        ),
        "predict deterministic stage",
    )
    registered = executor_spec(target)
    if registered.executor_kind != "deterministic" or (
        target not in _RENDERERS and target != "dashboard"
    ):
        raise ValueError("stage target has no registered deterministic dispatcher")
    full, machine, stale = _current_machine_input(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
    )
    if stale is not None:
        return stale
    if target == "dashboard":
        result, effect = _dashboard(root, preparation, machine)
    else:
        result = _RENDERERS[target](root, preparation, machine)
        effect = None
    return {
        "executor_spec": registered.projection(),
        "raw_owner_result": result,
        "effect_plan": effect,
        "full_context": full,
        "model_call_count": 0,
        "model_visible_bytes": 0,
        "owner_result_bytes": len(canonical_bytes(result)),
        "freshness_status": "exact_precondition",
    }


def dispatch_deterministic(
    root: Path,
    preparation: dict[str, Any],
    *,
    max_files: int = 12,
    max_paths: int = 40,
) -> dict[str, Any]:
    """Compatibility name for the now write-free deterministic prediction."""

    return predict_deterministic(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
    )


if set(_RENDERERS) | {"dashboard"} != {
    target
    for target in TARGET_COMPILE_SPECS
    if executor_spec(target).executor_kind == "deterministic"
}:
    raise RuntimeError("deterministic dispatcher registry is incomplete")


__all__ = [
    "dispatch_deterministic",
    "predict_deterministic",
]
