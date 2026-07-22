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
        "agent_goal": collect_agent_goal(root, max_files, cycle_state),
        "cycle_state": cycle_state,
        "selection_publication": publication_status(root),
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
    if "git" in selectors:
        data["git"] = collect_git(root)
    model = project_model_context(data, max_paths=max_paths)
    metrics = {
        "context_sections_collected": sorted(data),
        "context_section_count": len(data),
        "target_context_bytes": len(canonical_bytes(model)),
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
    if "git" in selectors:
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
    return {
        "schema_version": 1,
        "artifact_kind": "orchestrate_stage_work_order",
        "cycle_id": cycle_id,
        "target": target,
        "workflow_mode": workflow_mode,
        "executor_kind": spec.executor_kind,
        "model_call_required": bool(spec.semantic_fields),
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


__all__ = [
    "collect_selected_context",
    "render_work_order",
    "selected_state_fingerprint",
]
