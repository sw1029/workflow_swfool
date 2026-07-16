from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import reuse_root_modules
from .semantics import directory_fan_out, duplicate_symbol_findings, semantic_findings
from .source import analyze_file
from .state import AuditState


def _semantic_metrics(
    root: Path,
    scanned: list[dict[str, Any]],
    duplicates: list[dict[str, Any]],
    convention_contract: dict[str, Any],
) -> dict[str, Any]:
    fan_out = directory_fan_out(root, [str(item["path"]) for item in scanned])
    total_imports = sum(int(item.get("import_count", 0)) for item in scanned)
    total_reuse_imports = sum(
        int(item.get("reuse_root_import_count", 0)) for item in scanned
    )
    reuse_ratio = (
        total_reuse_imports / total_imports
        if total_imports and reuse_root_modules(convention_contract)
        else None
    )
    metrics = {
        "mechanical_shard_file_count": sum(
            1
            for item in scanned
            if any(
                signal in {"numbered_part", "numbered_shard", "numeric_only_stem"}
                for signal in item.get("mechanical_naming_signals", [])
            )
        ),
        "version_suffix_file_count": sum(
            1
            for item in scanned
            if "version_suffix" in item.get("mechanical_naming_signals", [])
        ),
        "global_rebinding_signal_count": sum(
            int(item.get("global_rebinding_signal_count", 0)) for item in scanned
        ),
        "duplicate_symbol_name_count": len(duplicates),
        "max_changed_tree_depth": max(
            (int(item.get("tree_depth", 0)) for item in scanned), default=0
        ),
        "max_changed_dir_fan_out": max(fan_out.values(), default=0),
        "max_file_logical_loc": max(
            (int(item.get("logical_loc", 0)) for item in scanned), default=0
        ),
    }
    if reuse_ratio is not None:
        metrics["reuse_root_import_ratio"] = reuse_ratio
    metrics["relocated_mechanical_shard"] = bool(metrics["mechanical_shard_file_count"])
    metrics["depth_fan_out_enforcement"] = (
        "contract_coupled"
        if convention_contract.get("status") == "provided"
        else "warn_only_no_contract"
    )
    metrics["depth_fan_out_standalone_penalty_blocked"] = True
    return metrics


def build_audit_state(
    root: Path,
    files: list[str],
    thresholds: dict[str, int],
    convention_contract: dict[str, Any],
) -> AuditState:
    records = [
        analyze_file(root, path, thresholds, convention_contract)
        for path in sorted(dict.fromkeys(files))
    ]
    scanned = [item for item in records if item.get("scan_status") == "scanned"]
    exempt = [item for item in records if item.get("scan_status") == "exempt"]
    hard_items = [item for item in scanned if item.get("hard_threshold_triggered")]
    soft_items = [item for item in scanned if item.get("soft_threshold_triggered")]
    duplicates = duplicate_symbol_findings(scanned)
    metrics = _semantic_metrics(root, scanned, duplicates, convention_contract)
    findings = semantic_findings(
        scanned=scanned,
        semantic_metrics=metrics,
        duplicates=duplicates,
        convention_contract=convention_contract,
    )
    required = any(
        str(item.get("severity")) == "refactor_required" for item in findings
    )
    semantic_items = [
        item
        for item in scanned
        if item.get("mechanical_naming_signals") or item.get("global_rebinding_signals")
    ]
    primary = (
        hard_items[0]
        if hard_items
        else (
            soft_items[0]
            if soft_items
            else (
                semantic_items[0]
                if semantic_items
                else (scanned[0] if required and scanned else None)
            )
        )
    )
    return AuditState(
        records=records,
        scanned=scanned,
        exempt=exempt,
        oversize=[
            {
                "path": item["path"],
                "logical_loc": item["logical_loc"],
                "cluster_count": item["cluster_count"],
                "hard_threshold_triggered": item["hard_threshold_triggered"],
                "soft_threshold_triggered": item["soft_threshold_triggered"],
            }
            for item in scanned
            if item.get("soft_threshold_triggered")
            or item.get("hard_threshold_triggered")
        ],
        hard_items=hard_items,
        soft_items=soft_items,
        metrics=metrics,
        findings=findings,
        refactor_required=required,
        primary=primary,
    )
