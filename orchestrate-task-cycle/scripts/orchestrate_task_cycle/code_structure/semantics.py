from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .contracts import convention_enforced, numeric_contract_value
from .source import is_exempt, is_source


def directory_fan_out(root: Path, scanned_files: list[str]) -> dict[str, int]:
    fan_out: dict[str, int] = {}
    for path_value in scanned_files:
        parent = Path(path_value).parent
        abs_parent = root / parent
        if not abs_parent.is_dir():
            continue
        children = set()
        try:
            for child in abs_parent.iterdir():
                if is_exempt(child):
                    continue
                if child.is_dir() or is_source(child):
                    children.add(child.name)
        except OSError:
            continue
        fan_out[parent.as_posix() if parent.as_posix() != "." else "."] = len(children)
    return fan_out


def duplicate_symbol_findings(scanned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, set[str]] = defaultdict(set)
    for item in scanned:
        path = str(item.get("path", ""))
        for name in item.get("symbol_names", []):
            if name and not str(name).startswith("_"):
                by_name[str(name)].add(path)
    duplicates = []
    for name, paths in sorted(by_name.items()):
        if len(paths) > 1:
            duplicates.append(
                {"name": name, "file_count": len(paths), "paths": sorted(paths)[:6]}
            )
    return duplicates[:25]


def semantic_findings(
    *,
    scanned: list[dict[str, Any]],
    semantic_metrics: dict[str, Any],
    duplicates: list[dict[str, Any]],
    convention_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    enforced = convention_enforced(convention_contract)
    severity = "refactor_required" if enforced else "warn"
    findings: list[dict[str, Any]] = []
    min_reuse_ratio = numeric_contract_value(
        convention_contract, "min_reuse_root_import_ratio"
    )
    reuse_ratio = semantic_metrics.get("reuse_root_import_ratio")
    reuse_below = (
        min_reuse_ratio is not None
        and reuse_ratio is not None
        and reuse_ratio < min_reuse_ratio
    )
    placement_coupled = bool(
        int(semantic_metrics.get("mechanical_shard_file_count", 0) or 0)
        or duplicates
        or int(semantic_metrics.get("global_rebinding_signal_count", 0) or 0)
        or reuse_below
    )
    mechanical = [
        {
            "path": str(item.get("path")),
            "signals": item.get("mechanical_naming_signals", []),
        }
        for item in scanned
        if item.get("mechanical_naming_signals")
    ]
    if mechanical:
        findings.append(
            {
                "code": "mechanical_or_versioned_naming_detected",
                "severity": "refactor_required"
                if semantic_metrics.get("mechanical_shard_file_count") and enforced
                else "warn",
                "message": "Changed files include numbered shard, part, or version-suffix naming that needs semantic justification or convention approval.",
                "paths": mechanical[:20],
            }
        )
    rebinding = [
        {
            "path": str(item.get("path")),
            "signals": item.get("global_rebinding_signals", []),
        }
        for item in scanned
        if item.get("global_rebinding_signals")
    ]
    if rebinding:
        findings.append(
            {
                "code": "global_rebinding_coupling_detected",
                "severity": severity,
                "message": "Changed files include global rebinding or binding-shim signals; prefer explicit parameters or dependency injection.",
                "paths": rebinding[:20],
            }
        )
    if duplicates:
        findings.append(
            {
                "code": "duplicate_public_symbol_names_detected",
                "severity": severity,
                "message": "Changed files repeat public symbol names across files; verify reuse or consolidate shared behavior.",
                "duplicates": duplicates,
            }
        )
    max_depth = numeric_contract_value(convention_contract, "max_tree_depth")
    if (
        max_depth is not None
        and semantic_metrics.get("max_changed_tree_depth", 0) > max_depth
    ):
        findings.append(
            {
                "code": "tree_depth_exceeds_convention",
                "severity": "refactor_required"
                if enforced and placement_coupled
                else "warn",
                "message": "Changed file depth exceeds the repository-owned convention contract; depth alone is warn-only unless coupled with reuse, duplicate, mechanical-shard, or coupling evidence.",
                "observed": semantic_metrics.get("max_changed_tree_depth"),
                "limit": max_depth,
                "standalone_depth_penalty_blocked": not placement_coupled,
            }
        )
    max_fan_out = numeric_contract_value(convention_contract, "max_dir_fan_out")
    if (
        max_fan_out is not None
        and semantic_metrics.get("max_changed_dir_fan_out", 0) > max_fan_out
    ):
        findings.append(
            {
                "code": "dir_fan_out_exceeds_convention",
                "severity": "refactor_required"
                if enforced and placement_coupled
                else "warn",
                "message": "Changed directory fan-out exceeds the repository-owned convention contract; fan-out alone is warn-only unless coupled with reuse, duplicate, mechanical-shard, or coupling evidence.",
                "observed": semantic_metrics.get("max_changed_dir_fan_out"),
                "limit": max_fan_out,
                "standalone_fan_out_penalty_blocked": not placement_coupled,
            }
        )
    if reuse_below:
        findings.append(
            {
                "code": "reuse_root_import_ratio_below_convention",
                "severity": severity,
                "message": "Changed files import less from the repository reuse layer than the convention contract requires.",
                "observed": reuse_ratio,
                "limit": min_reuse_ratio,
            }
        )
    return findings
