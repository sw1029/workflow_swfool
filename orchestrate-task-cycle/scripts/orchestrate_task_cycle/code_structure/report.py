from __future__ import annotations

from pathlib import Path
from typing import Any

from .source import split_plan, suggested_root
from .state import AuditState


def _status(state: AuditState) -> tuple[str, str]:
    if not state.scanned:
        return "not_applicable", "not_applicable"
    if state.hard_items or state.refactor_required:
        return "refactor_required", "complete"
    if state.soft_items or state.findings:
        return "warn", "complete"
    return "pass", "complete"


def render_result(
    state: AuditState,
    thresholds: dict[str, int],
    task_id: str | None,
    convention_contract: dict[str, Any],
) -> dict[str, Any]:
    audit_status, status = _status(state)
    moduleization_required = bool(state.hard_items or state.refactor_required)
    convention_status = (
        "refactor_required"
        if state.refactor_required
        else ("warn" if state.findings else "not_applicable")
    )
    return {
        "step": "code_structure_audit",
        "status": status,
        "task_id": task_id or None,
        "audit_status": audit_status,
        "changed_files_scanned": [str(item["path"]) for item in state.scanned],
        "oversize_files": state.oversize,
        "thresholds": thresholds,
        "responsibility_clusters": {
            str(item["path"]): item.get("responsibility_clusters", [])
            for item in state.scanned
        },
        "semantic_structure_metrics": state.metrics,
        "semantic_structure_findings": state.findings,
        "convention_conformance": {
            "code_convention_contract_status": convention_contract.get("status"),
            "enforcement": convention_contract.get("enforcement"),
            "warn_only": bool(convention_contract.get("warn_only")),
            "status": convention_status,
            "checked_axes": [
                "reuse_before_create",
                "semantic_naming",
                "global_rebinding_coupling",
                "duplicate_definitions",
                "tree_depth",
                "fan_out",
                "reuse_root_import_ratio",
                "relocated_mechanical_shard",
            ],
        },
        "moduleization_required": moduleization_required,
        "suggested_module_root": suggested_root(str(state.primary["path"]))
        if state.primary and moduleization_required
        else None,
        "responsibility_split_plan": split_plan(
            str(state.primary["path"]),
            list(state.primary.get("responsibility_clusters", [])),
        )
        if state.primary and moduleization_required
        else [],
        "semantic_refactor_plan": [
            {
                "target": "semantic_consolidation",
                "reason": "replace mechanical shards, version-suffix files, duplicate definitions, or global rebinding with meaningfully named modules and explicit dependencies",
            }
        ]
        if state.findings
        else [],
        "compatibility_constraints": [
            "preserve public entry points, CLI behavior, schema IDs, artifact paths, and validation commands"
        ],
        "validation_scope_delta": ["affected_chain"]
        if moduleization_required
        else ["current_only"],
        "existing_debt_exemptions": [
            f"{item['path']}: {item.get('exemption')}" for item in state.exempt
        ],
        "forbidden_raw_source_persisted": True,
        "raw_source_persisted": False,
        "scanned_file_details": state.scanned,
        "skipped_files": [
            item for item in state.records if item.get("scan_status") != "scanned"
        ],
        "evidence_paths": [
            "stdout:code_structure_audit",
            (
                Path(__file__).resolve().parents[3]
                / "references"
                / "code-structure-audit.md"
            ).as_posix(),
        ],
    }
