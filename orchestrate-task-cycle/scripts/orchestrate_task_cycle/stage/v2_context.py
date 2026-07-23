"""Target-selected context collection and bounded v2 work-order rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..collect_cycle_context import (
    collect_agent_goal,
    collect_agent_log,
    collect_contract_dir,
    collect_cycle_state,
    collect_external_advice,
    collect_git,
    collect_issue,
    collect_task,
    collect_validation_assets,
)
from ..context_support import file_info
from ..model_context import project_model_context
from ..result_contract.session_audit import collect_session_audit_directory
from ..selection_publication import publication_status
from .contracts import canonical_bytes, canonical_sha256
from .executor_registry import executor_spec
from .specs import TargetCompileSpec


def _empty_advice(root: Path) -> dict[str, Any]:
    directory = root / ".agent_advice"
    return {
        "directory": file_info(root, directory),
        "index_jsonl": file_info(root, directory / "index.jsonl"),
        "active_count": 0,
        "normalized_packet": None,
        "normalized_packet_status": "not_applicable",
    }


def _empty_goal() -> dict[str, Any]:
    return {
        "goal_truth_files": {},
        "available_goal_truth": [],
        "used_goal_truth": [],
    }


def _observed_file_count(value: Any) -> int:
    paths: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            path = item.get("path")
            if (
                isinstance(path, str)
                and path
                and item.get("exists") is True
                and item.get("is_file") is True
            ):
                paths.add(path)
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return len(paths)


def _stable_observation(value: Any) -> Any:
    """Remove timestamps/directory sizes while retaining exact file bindings."""

    if isinstance(value, dict):
        if {"path", "exists", "is_file"} <= set(value):
            if value.get("is_file") is True:
                return {
                    key: value.get(key)
                    for key in ("path", "exists", "is_file", "size_bytes", "sha256")
                    if key in value
                }
            return {
                key: value.get(key)
                for key in ("path", "exists", "is_file", "is_dir")
                if key in value
            }
        return {
            str(key): _stable_observation(item)
            for key, item in sorted(value.items())
            if key not in {"collected_at", "modified_at", "title"}
        }
    if isinstance(value, list):
        return [_stable_observation(item) for item in value]
    return value


def _selector_material(
    data: dict[str, Any], model: dict[str, Any], selector: str
) -> Any:
    if selector == "core":
        return {
            "schema_version": model.get("schema_version"),
            "artifact_kind": model.get("artifact_kind"),
            "projection_status": model.get("projection_status"),
            "stop_reason": model.get("stop_reason"),
            "workspace": model.get("workspace"),
        }
    if selector == "task":
        task = model.get("task") if isinstance(model.get("task"), dict) else {}
        return {"task_md": task.get("task_md")}
    if selector == "cycle":
        return model.get("cycle")
    if selector == "authority":
        return model.get("authority")
    if selector == "pending_runs":
        return model.get("pending_runs")
    if selector == "git_head":
        git = model.get("git") if isinstance(model.get("git"), dict) else {}
        return {
            "inside_work_tree": git.get("inside_work_tree"),
            "head": git.get("head"),
        }
    if selector == "git_worktree":
        git = model.get("git") if isinstance(model.get("git"), dict) else {}
        identity = git.get("worktree_identity")
        # Historical bound contexts had path-set-only preconditions. Keep them
        # readable, while every newly collected v3 context binds the exact
        # content-sensitive worktree identity.
        return identity if isinstance(identity, dict) else git.get("changed_paths")
    if selector == "advice":
        return model.get("advice")
    if selector == "goal":
        return model.get("goal_truth")
    if selector == "selection":
        return model.get("selection_publication")
    if selector == "task_state":
        state = data.get("task_state") or {}
        return {
            key: value
            for key, value in state.items()
            if key not in {"authorization", "cycle"}
        }
    if selector == "schema":
        return {"schema": data.get("schema"), "contract": data.get("contract")}
    source_key = {
        "issue": "issue",
        "agent_log": "agent_log",
        "session": "session_audit",
        "validation": "validation_assets",
    }.get(selector)
    if source_key is None:
        raise ValueError(f"unsupported stage dependency selector: {selector}")
    return data.get(source_key)


def selector_fingerprints(
    data: dict[str, Any], model: dict[str, Any], selectors: tuple[str, ...]
) -> dict[str, str]:
    return {
        selector: canonical_sha256(
            _stable_observation(_selector_material(data, model, selector))
        )
        for selector in selectors
    }


def collect_selected_context(
    root: Path,
    cycle_id: str,
    spec: TargetCompileSpec,
    *,
    max_files: int,
    max_paths: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    selectors = frozenset(spec.dependency_selectors)
    cycle_state = collect_cycle_state(root, max_files, cycle_id)
    data: dict[str, Any] = {
        "schema_version": 2,
        "workspace": str(root),
        "task_md": file_info(root, root / "task.md"),
        "agent_goal": (
            collect_agent_goal(root, max_files, cycle_state)
            if "goal" in selectors
            else _empty_goal()
        ),
        "cycle_state": cycle_state,
        "selection_publication": (
            publication_status(root) if "selection" in selectors else None
        ),
        "external_advice": (
            collect_external_advice(root, max_files)
            if "advice" in selectors
            else _empty_advice(root)
        ),
    }
    if "task_state" in selectors:
        data["task_state"] = collect_task(root, max_files)
    if "issue" in selectors:
        data["issue"] = collect_issue(root, max_files)
    if "agent_log" in selectors:
        data["agent_log"] = collect_agent_log(root, max_files)
    if "session" in selectors:
        data["session_audit"] = collect_session_audit_directory(root, max_files)
    if "validation" in selectors:
        data["validation_assets"] = collect_validation_assets(root, max_files)
    if "schema" in selectors:
        data["schema"] = collect_contract_dir(root, ".schema", max_files)
        data["contract"] = collect_contract_dir(root, ".contract", max_files)
    if selectors & {"git_head", "git_worktree"}:
        data["git"] = collect_git(root)
    model = project_model_context(
        data,
        max_paths=max_paths,
        worktree_root=root,
        collect_git_worktree_identity="git_worktree" in selectors,
        require_exact_git_worktree="git_worktree" in selectors,
    )
    metrics = {
        "collection_limits": {
            "max_files": max_files,
            "max_paths": max_paths,
        },
        "context_sections_collected": sorted(data),
        "context_section_count": len(data),
        "target_context_bytes": len(canonical_bytes(model)),
        # Count only evidence that survived the target selector/model projection.
        # Raw collector inventories include packet-CAS outputs that are not opened
        # by this stage; counting them makes an otherwise identical preparation
        # change after a crash between the result-CAS write and ledger append.
        "files_opened_count": _observed_file_count(model),
        "selection_status_collected": "selection" in selectors,
        "precondition_fingerprints": selector_fingerprints(
            data, model, spec.dependency_selectors
        ),
    }
    return data, model, metrics


def selected_state_fingerprint(
    model: dict[str, Any], selectors: tuple[str, ...] | list[str]
) -> str:
    material = {
        key: value
        for key, value in model.items()
        if key not in {"compiler_metrics", "semantic_context_binding"}
    }
    return canonical_sha256(
        {"dependency_selectors": list(selectors), "model_context": material}
    )


def render_work_order(
    cycle_id: str,
    target: str,
    workflow_mode: str,
    spec: TargetCompileSpec,
    model: dict[str, Any],
    state_fingerprint: str,
    context_binding: dict[str, Any],
    precondition_fingerprints: dict[str, str] | None = None,
) -> dict[str, Any]:
    selectors = frozenset(spec.dependency_selectors)
    selected_context: dict[str, Any] = {
        "task": model.get("task"),
        "goal_truth": model.get("goal_truth"),
        "cycle": model.get("cycle"),
        "authority": model.get("authority"),
        "selection_publication": model.get("selection_publication"),
    }
    if "advice" in selectors:
        selected_context["advice"] = model.get("advice")
    if selectors & {"git_head", "git_worktree"}:
        selected_context["git"] = model.get("git")
    if selectors & {
        "task_state",
        "issue",
        "agent_log",
        "session",
        "validation",
        "schema",
    }:
        selected_context["diagnostic_artifacts"] = model.get(
            "diagnostic_artifacts"
        )
    registered = executor_spec(target)
    work_order = {
        "schema_version": 2,
        "artifact_kind": "orchestrate_stage_work_order",
        "cycle_id": cycle_id,
        "target": target,
        "workflow_mode": workflow_mode,
        "executor_kind": spec.executor_kind,
        "model_call_required": bool(spec.semantic_fields),
        "executor_spec": registered.projection(),
        "routing_requirement": {
            "required": registered.routing_required,
            "policy_id": registered.routing_policy_id,
            "allowed_profile_ids": list(registered.allowed_routing_profiles),
            "receipt_schema_version": 1 if registered.routing_required else None,
        },
        "state_fingerprint": state_fingerprint,
        "context_binding": context_binding,
        "selected_context": selected_context,
        "required_output": {
            "semantic_fields": list(spec.semantic_fields),
            "optional_semantic_fields": list(spec.optional_semantic_fields),
            "owner_fields": list(spec.owner_receipt_fields),
            "optional_owner_fields": list(spec.optional_owner_fields),
        },
    }
    if precondition_fingerprints is not None:
        work_order["precondition_fingerprints"] = precondition_fingerprints
    return work_order


def render_machine_input(
    cycle_id: str,
    target: str,
    workflow_mode: str,
    model: dict[str, Any],
    state_fingerprint: str,
    context_metrics: dict[str, Any],
    precondition_fingerprints: dict[str, str],
) -> dict[str, Any]:
    """Render deterministic exact inputs without a model-facing context body."""

    registered = executor_spec(target)
    if registered.executor_kind != "deterministic":
        raise ValueError("machine input is reserved for deterministic executors")
    return {
        "schema_version": 1,
        "artifact_kind": "orchestrate_stage_machine_input",
        "cycle_id": cycle_id,
        "target": target,
        "workflow_mode": workflow_mode,
        "state_fingerprint": state_fingerprint,
        "context_metrics": context_metrics,
        "precondition_fingerprints": precondition_fingerprints,
        "executor_spec": registered.projection(),
        "projection_status": model.get("projection_status"),
        "stop_reason": model.get("stop_reason"),
        "workspace": model.get("workspace"),
        "task": model.get("task"),
        "goal_truth": model.get("goal_truth"),
        "advice": model.get("advice"),
        "cycle": model.get("cycle"),
        "selection_publication": model.get("selection_publication"),
        "authority": model.get("authority"),
        "pending_runs": model.get("pending_runs"),
        "git": model.get("git"),
        "diagnostic_artifacts": model.get("diagnostic_artifacts"),
    }


__all__ = [
    "collect_selected_context",
    "render_work_order",
    "render_machine_input",
    "selector_fingerprints",
    "selected_state_fingerprint",
]
