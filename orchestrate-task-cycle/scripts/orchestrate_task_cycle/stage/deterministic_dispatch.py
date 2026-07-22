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
from ..dashboard.io import atomic_write
from ..assemble_cycle_report import assemble
from .artifact_store import write_stage_input
from .contracts import canonical_bytes, canonical_sha256
from .executor_registry import executor_spec
from .freshness import evaluate_preparation_freshness
from .specs import TARGET_COMPILE_SPECS


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
) -> dict[str, Any]:
    cycle_id = str(preparation["cycle_id"])
    events = read_events(root, cycle_id)
    current = read_current_expanded(root, cycle_id)
    result = summarize(events, current, "loaded", cycle_id, root)
    path = root / ".task" / "cycle" / cycle_id / "dashboard.md"
    atomic_write(path, render_summary(result))
    result["dashboard_path"] = path.relative_to(root).as_posix()
    result["evidence_paths"] = list(result.get("evidence_paths") or []) + [
        result["dashboard_path"]
    ]
    return _allowed_owner_fields("dashboard", result)


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
    "dashboard": _dashboard,
    "report": _report,
}


def dispatch_deterministic(
    root: Path,
    preparation: dict[str, Any],
    *,
    max_files: int = 12,
    max_paths: int = 40,
) -> dict[str, Any]:
    target = str(preparation["target"])
    registered = executor_spec(target)
    if registered.executor_kind != "deterministic" or target not in _RENDERERS:
        raise ValueError("stage target has no registered deterministic dispatcher")
    freshness = evaluate_preparation_freshness(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
        allow_post_effect=False,
    )
    if freshness["status"] == "block":
        return {
            **freshness,
            "model_call_count": 0,
            "model_visible_bytes": 0,
            "files_written_count": 0,
        }
    preparation = freshness["preparation"]
    machine = freshness["bound_material"]
    result = _RENDERERS[target](root, preparation, machine)
    binding = write_stage_input(
        root,
        str(preparation["cycle_id"]),
        target,
        "owner_result",
        result,
    )
    return {
        "executor_spec": registered.projection(),
        "owner_result_binding": binding,
        "model_call_count": 0,
        "model_visible_bytes": 0,
        "owner_result_bytes": len(canonical_bytes(result)),
        "freshness_status": freshness["freshness_status"],
    }


if set(_RENDERERS) != {
    target
    for target in TARGET_COMPILE_SPECS
    if executor_spec(target).executor_kind == "deterministic"
}:
    raise RuntimeError("deterministic dispatcher registry is incomplete")


__all__ = ["dispatch_deterministic"]
