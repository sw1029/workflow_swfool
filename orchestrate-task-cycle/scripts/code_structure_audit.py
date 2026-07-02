#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".sh"}
EXEMPT_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "generated",
    "migrations",
    "node_modules",
    "snapshots",
    "vendor",
}
EXEMPT_NAMES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock"}

DEFAULT_THRESHOLDS = {
    "soft_file_logical_loc": 500,
    "hard_file_logical_loc": 900,
    "soft_function_logical_loc": 80,
    "hard_function_logical_loc": 140,
    "soft_class_logical_loc": 250,
    "hard_class_logical_loc": 420,
    "soft_responsibility_cluster_count": 3,
    "hard_responsibility_cluster_count": 4,
}

CONVENTION_CONTRACT_KEYS = {
    "code_convention_contract",
    "convention_contract",
    "architecture_convention_contract",
}

MECHANICAL_NAME_PATTERNS = {
    "numbered_part": re.compile(r"(^|[/_.-])part[_-]?\d{2,}($|[_.-])", re.IGNORECASE),
    "numbered_shard": re.compile(r"(^|[/_.-])(?:chunk|shard|section|segment)[_-]?\d{2,}($|[_.-])", re.IGNORECASE),
    "numeric_only_stem": re.compile(r"^\d{2,}$"),
    "version_suffix": re.compile(r"(^|[/_.-])v\d{2,}($|[_.-])", re.IGNORECASE),
}

GLOBAL_REBINDING_PATTERNS = {
    "globals_update": re.compile(r"\bglobals\s*\(\s*\)\s*\.\s*update\b"),
    "globals_assignment": re.compile(r"\bglobals\s*\(\s*\)\s*\[[^\]]+\]\s*="),
    "prebind_global_names": re.compile(r"\b_PREBIND_GLOBAL_NAMES\b"),
    "reserved_globals": re.compile(r"\b_RESERVED_GLOBALS\b"),
    "binding_module": re.compile(r"(^|\W)_binding(\W|$)"),
    "sys_modules_setattr": re.compile(r"\bsetattr\s*\(\s*sys\.modules\s*\["),
}

CLUSTER_KEYWORDS = {
    "cli": {"argparse", "click", "typer", "command", "subcommand", "argv", "stdin", "stdout"},
    "configuration": {"config", "settings", "env", "dotenv", "toml", "yaml", "ini"},
    "provider_runtime": {"provider", "client", "http", "request", "response", "retry", "timeout", "api"},
    "io": {"path", "file", "read", "write", "open", "jsonl", "csv", "parquet", "sqlite"},
    "domain_transform": {"transform", "normalize", "extract", "parse", "convert", "map", "merge"},
    "schema_contract": {"schema", "contract", "manifest", "version", "compat"},
    "validation": {"validate", "validator", "assert", "check", "test", "oracle"},
    "reporting": {"report", "dashboard", "render", "summary", "markdown"},
    "persistence": {"save", "load", "store", "cache", "registry", "ledger", "index"},
    "orchestration": {"stage", "workflow", "phase", "cycle", "route", "dispatch"},
}


def find_contract(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    for key in CONVENTION_CONTRACT_KEYS:
        child = value.get(key)
        if isinstance(child, dict):
            return child
    for child in value.values():
        found = find_contract(child)
        if found is not None:
            return found
    return None


def normalize_convention_contract(raw: Any) -> dict[str, Any]:
    contract = find_contract(raw) if isinstance(raw, dict) else None
    if contract is None and isinstance(raw, dict) and any(key in raw for key in ("reuse_roots", "max_tree_depth", "enforcement")):
        contract = raw
    if not isinstance(contract, dict):
        return {"status": "not_provided", "enforcement": "warn", "warn_only": True}
    enforcement = str(contract.get("enforcement") or contract.get("mode") or "warn").strip().lower()
    strict_values = {"gate", "required", "enforce", "enforced", "block", "strict", "fail"}
    return {
        "status": "provided",
        "enforcement": enforcement,
        "warn_only": enforcement not in strict_values,
        "raw": contract,
    }


def load_optional_contract(path_or_json: str | None) -> dict[str, Any]:
    if not path_or_json:
        return normalize_convention_contract(None)
    return normalize_convention_contract(load_json(path_or_json))


def list_contract_values(contract: dict[str, Any], key: str) -> list[str]:
    raw = contract.get("raw", {}) if isinstance(contract, dict) else {}
    value = raw.get(key) if isinstance(raw, dict) else None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def numeric_contract_value(contract: dict[str, Any], key: str) -> float | None:
    raw = contract.get("raw", {}) if isinstance(contract, dict) else {}
    if not isinstance(raw, dict) or key not in raw:
        return None
    value = raw.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def convention_enforced(contract: dict[str, Any]) -> bool:
    return contract.get("status") == "provided" and not bool(contract.get("warn_only"))


def reuse_root_modules(contract: dict[str, Any]) -> list[str]:
    roots = []
    for value in list_contract_values(contract, "reuse_roots") + list_contract_values(contract, "kernel_roots"):
        normalized = value.strip().strip("./")
        if normalized.endswith(".py"):
            normalized = normalized[:-3]
        normalized = normalized.replace("/", ".").replace("\\", ".").strip(".")
        if normalized:
            roots.append(normalized)
    return sorted(dict.fromkeys(roots))


def git_files(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        value = line[3:].strip()
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        if value:
            files.append(value)
    return files


def load_json(path_value: str) -> Any:
    if path_value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    stripped = path_value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    return json.loads(Path(path_value).read_text(encoding="utf-8"))


def collect_changed_files(data: Any) -> list[str]:
    files: list[str] = []

    def visit(value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key))
        elif isinstance(value, list):
            if key in {"changed_files", "files", "changed_files_scanned"}:
                for item in value:
                    if isinstance(item, str):
                        files.append(item)
                    elif isinstance(item, dict) and item.get("path"):
                        files.append(str(item["path"]))
            else:
                for item in value:
                    visit(item, key)

    visit(data)
    return sorted(dict.fromkeys(files))


def is_exempt(path: Path) -> bool:
    parts = set(path.parts)
    if path.name in EXEMPT_NAMES:
        return True
    if parts & EXEMPT_PARTS:
        return True
    lower = path.as_posix().lower()
    return ".generated." in lower or lower.endswith((".min.js", ".snap", ".snapshot"))


def is_source(path: Path) -> bool:
    return path.suffix.lower() in SOURCE_SUFFIXES


def logical_line_count(text: str, suffix: str) -> int:
    count = 0
    in_block_comment = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if suffix == ".py" or suffix == ".sh":
            if line.startswith("#"):
                continue
        else:
            if in_block_comment:
                if "*/" in line:
                    in_block_comment = False
                continue
            if line.startswith("/*"):
                if "*/" not in line:
                    in_block_comment = True
                continue
            if line.startswith("//"):
                continue
        count += 1
    return count


def python_symbols(text: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    symbols: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end_lineno = getattr(node, "end_lineno", None)
            if isinstance(end_lineno, int):
                loc = max(1, end_lineno - node.lineno + 1)
                symbols.append({"name": node.name, "kind": type(node).__name__.replace("Def", "").lower(), "loc": loc})
    return sorted(symbols, key=lambda item: int(item["loc"]), reverse=True)


def python_imports(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def mechanical_name_signals(path_value: str, contract: dict[str, Any]) -> list[str]:
    path = Path(path_value)
    target = path.as_posix()
    stem = path.stem
    signals: list[str] = []
    for code, pattern in MECHANICAL_NAME_PATTERNS.items():
        candidate = stem if code == "numeric_only_stem" else target
        if pattern.search(candidate):
            signals.append(code)
    for index, raw_pattern in enumerate(list_contract_values(contract, "forbidden_name_patterns")):
        try:
            if re.search(raw_pattern, target):
                signals.append(f"repo_forbidden_name_pattern_{index + 1}")
        except re.error:
            signals.append(f"invalid_repo_forbidden_name_pattern_{index + 1}")
    return sorted(set(signals))


def global_rebinding_signals(text: str) -> list[str]:
    signals: list[str] = []
    for code, pattern in GLOBAL_REBINDING_PATTERNS.items():
        if pattern.search(text):
            signals.append(code)
    return sorted(set(signals))


def import_reuse_counts(imports: list[str], contract: dict[str, Any]) -> tuple[int, int, float | None]:
    roots = reuse_root_modules(contract)
    if not roots:
        return (0, len(imports), None)
    total = len(imports)
    if total == 0:
        return (0, 0, None)
    reused = 0
    for imported in imports:
        normalized = imported.strip()
        if any(normalized == root or normalized.startswith(f"{root}.") for root in roots):
            reused += 1
    return (reused, total, reused / total)


def clusters_for(path: str, evidence_text: str, symbols: list[dict[str, Any]]) -> list[str]:
    haystack = " ".join([path, *(str(item.get("name", "")) for item in symbols), evidence_text]).lower()
    clusters: list[str] = []
    for cluster, keywords in CLUSTER_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            clusters.append(cluster)
    return sorted(set(clusters))


def suggested_root(path: str) -> str:
    p = Path(path)
    if p.suffix:
        return (p.parent / p.stem).as_posix()
    return (p / "modules").as_posix()


def split_plan(path: str, clusters: list[str]) -> list[dict[str, str]]:
    root = suggested_root(path)
    selected = clusters[:6] if clusters else ["core"]
    return [{"target_module": f"{root}/{cluster}.py", "responsibility": cluster} for cluster in selected]


def analyze_file(root: Path, path_value: str, thresholds: dict[str, int], convention_contract: dict[str, Any]) -> dict[str, Any]:
    path = Path(path_value)
    abs_path = path if path.is_absolute() else root / path
    rel = path_value if not path.is_absolute() else path.as_posix()
    if not abs_path.is_file():
        return {"path": rel, "scan_status": "missing"}
    if is_exempt(path):
        return {"path": rel, "scan_status": "exempt", "exemption": "generated_vendor_migration_snapshot_or_lockfile"}
    if not is_source(path):
        return {"path": rel, "scan_status": "not_source"}
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"path": rel, "scan_status": "unreadable", "error": exc.__class__.__name__}
    logical_loc = logical_line_count(text, path.suffix.lower())
    is_python = path.suffix.lower() == ".py"
    symbols = python_symbols(text) if is_python else []
    imports = python_imports(text) if is_python else []
    cluster_evidence = " ".join(imports) if is_python else text[:12000]
    clusters = clusters_for(rel, cluster_evidence, symbols)
    largest_function = max((int(item["loc"]) for item in symbols if item["kind"] in {"function", "asyncfunction"}), default=0)
    largest_class = max((int(item["loc"]) for item in symbols if item["kind"] == "class"), default=0)
    size_pressure = (
        logical_loc >= thresholds["soft_file_logical_loc"]
        or largest_function >= thresholds["soft_function_logical_loc"]
        or largest_class >= thresholds["soft_class_logical_loc"]
    )
    hard = (
        logical_loc >= thresholds["hard_file_logical_loc"]
        or largest_function >= thresholds["hard_function_logical_loc"]
        or largest_class >= thresholds["hard_class_logical_loc"]
        or (len(clusters) >= thresholds["hard_responsibility_cluster_count"] and size_pressure)
    )
    soft = (
        logical_loc >= thresholds["soft_file_logical_loc"]
        or largest_function >= thresholds["soft_function_logical_loc"]
        or largest_class >= thresholds["soft_class_logical_loc"]
        or len(clusters) >= thresholds["soft_responsibility_cluster_count"]
    )
    return {
        "path": rel,
        "scan_status": "scanned",
        "logical_loc": logical_loc,
        "total_lines": len(text.splitlines()),
        "tree_depth": max(0, len(Path(rel).parts) - 1),
        "responsibility_clusters": clusters,
        "cluster_count": len(clusters),
        "largest_symbols": symbols[:8],
        "symbol_names": [str(item.get("name")) for item in symbols if item.get("name")],
        "mechanical_naming_signals": mechanical_name_signals(rel, convention_contract),
        "global_rebinding_signals": global_rebinding_signals(text),
        "global_rebinding_signal_count": len(global_rebinding_signals(text)),
        "import_count": len(imports),
        "reuse_root_import_count": import_reuse_counts(imports, convention_contract)[0],
        "reuse_root_import_ratio": import_reuse_counts(imports, convention_contract)[2],
        "soft_threshold_triggered": soft,
        "hard_threshold_triggered": hard,
    }


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
            duplicates.append({"name": name, "file_count": len(paths), "paths": sorted(paths)[:6]})
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
    mechanical_paths = [
        {"path": str(item.get("path")), "signals": item.get("mechanical_naming_signals", [])}
        for item in scanned
        if item.get("mechanical_naming_signals")
    ]
    if mechanical_paths:
        findings.append(
            {
                "code": "mechanical_or_versioned_naming_detected",
                "severity": severity,
                "message": "Changed files include numbered shard, part, or version-suffix naming that needs semantic justification or convention approval.",
                "paths": mechanical_paths[:20],
            }
        )
    rebinding_paths = [
        {"path": str(item.get("path")), "signals": item.get("global_rebinding_signals", [])}
        for item in scanned
        if item.get("global_rebinding_signals")
    ]
    if rebinding_paths:
        findings.append(
            {
                "code": "global_rebinding_coupling_detected",
                "severity": severity,
                "message": "Changed files include global rebinding or binding-shim signals; prefer explicit parameters or dependency injection.",
                "paths": rebinding_paths[:20],
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
    if max_depth is not None and semantic_metrics.get("max_changed_tree_depth", 0) > max_depth:
        findings.append(
            {
                "code": "tree_depth_exceeds_convention",
                "severity": severity,
                "message": "Changed file depth exceeds the repository-owned convention contract.",
                "observed": semantic_metrics.get("max_changed_tree_depth"),
                "limit": max_depth,
            }
        )
    max_fan_out = numeric_contract_value(convention_contract, "max_dir_fan_out")
    if max_fan_out is not None and semantic_metrics.get("max_changed_dir_fan_out", 0) > max_fan_out:
        findings.append(
            {
                "code": "dir_fan_out_exceeds_convention",
                "severity": severity,
                "message": "Changed directory fan-out exceeds the repository-owned convention contract.",
                "observed": semantic_metrics.get("max_changed_dir_fan_out"),
                "limit": max_fan_out,
            }
        )
    min_reuse_ratio = numeric_contract_value(convention_contract, "min_reuse_root_import_ratio")
    reuse_ratio = semantic_metrics.get("reuse_root_import_ratio")
    if min_reuse_ratio is not None and reuse_ratio is not None and reuse_ratio < min_reuse_ratio:
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


def audit(
    root: Path,
    files: list[str],
    thresholds: dict[str, int],
    task_id: str | None,
    convention_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    convention_contract = convention_contract or normalize_convention_contract(None)
    records = [analyze_file(root, path, thresholds, convention_contract) for path in sorted(dict.fromkeys(files))]
    scanned = [item for item in records if item.get("scan_status") == "scanned"]
    exempt = [item for item in records if item.get("scan_status") == "exempt"]
    oversize = [
        {
            "path": item["path"],
            "logical_loc": item["logical_loc"],
            "cluster_count": item["cluster_count"],
            "hard_threshold_triggered": item["hard_threshold_triggered"],
            "soft_threshold_triggered": item["soft_threshold_triggered"],
        }
        for item in scanned
        if item.get("soft_threshold_triggered") or item.get("hard_threshold_triggered")
    ]
    hard_items = [item for item in scanned if item.get("hard_threshold_triggered")]
    soft_items = [item for item in scanned if item.get("soft_threshold_triggered")]
    duplicates = duplicate_symbol_findings(scanned)
    fan_out = directory_fan_out(root, [str(item["path"]) for item in scanned])
    total_imports = sum(int(item.get("import_count", 0)) for item in scanned)
    total_reuse_imports = sum(int(item.get("reuse_root_import_count", 0)) for item in scanned)
    reuse_ratio = (total_reuse_imports / total_imports) if total_imports and reuse_root_modules(convention_contract) else None
    semantic_metrics = {
        "mechanical_shard_file_count": sum(1 for item in scanned if any(signal in {"numbered_part", "numbered_shard", "numeric_only_stem"} for signal in item.get("mechanical_naming_signals", []))),
        "version_suffix_file_count": sum(1 for item in scanned if "version_suffix" in item.get("mechanical_naming_signals", [])),
        "global_rebinding_signal_count": sum(int(item.get("global_rebinding_signal_count", 0)) for item in scanned),
        "duplicate_symbol_name_count": len(duplicates),
        "max_changed_tree_depth": max((int(item.get("tree_depth", 0)) for item in scanned), default=0),
        "max_changed_dir_fan_out": max(fan_out.values(), default=0),
        "max_file_logical_loc": max((int(item.get("logical_loc", 0)) for item in scanned), default=0),
    }
    if reuse_ratio is not None:
        semantic_metrics["reuse_root_import_ratio"] = reuse_ratio
    semantic_structure_findings = semantic_findings(
        scanned=scanned,
        semantic_metrics=semantic_metrics,
        duplicates=duplicates,
        convention_contract=convention_contract,
    )
    semantic_refactor_required = any(str(item.get("severity")) == "refactor_required" for item in semantic_structure_findings)
    semantic_warn = bool(semantic_structure_findings)
    if not scanned:
        audit_status = "not_applicable"
        status = "not_applicable"
    elif hard_items or semantic_refactor_required:
        audit_status = "refactor_required"
        status = "complete"
    elif soft_items or semantic_warn:
        audit_status = "warn"
        status = "complete"
    else:
        audit_status = "pass"
        status = "complete"
    semantic_items = [
        item
        for item in scanned
        if item.get("mechanical_naming_signals") or item.get("global_rebinding_signals")
    ]
    primary = hard_items[0] if hard_items else (
        soft_items[0] if soft_items else (semantic_items[0] if semantic_items else (scanned[0] if semantic_refactor_required and scanned else None))
    )
    clusters_by_file = {str(item["path"]): item.get("responsibility_clusters", []) for item in scanned}
    moduleization_required = bool(hard_items or semantic_refactor_required)
    semantic_refactor_plan = [
        {
            "target": "semantic_consolidation",
            "reason": "replace mechanical shards, version-suffix files, duplicate definitions, or global rebinding with meaningfully named modules and explicit dependencies",
        }
    ] if semantic_structure_findings else []
    return {
        "step": "code_structure_audit",
        "status": status,
        "task_id": task_id or None,
        "audit_status": audit_status,
        "changed_files_scanned": [str(item["path"]) for item in scanned],
        "oversize_files": oversize,
        "thresholds": thresholds,
        "responsibility_clusters": clusters_by_file,
        "semantic_structure_metrics": semantic_metrics,
        "semantic_structure_findings": semantic_structure_findings,
        "convention_conformance": {
            "code_convention_contract_status": convention_contract.get("status"),
            "enforcement": convention_contract.get("enforcement"),
            "warn_only": bool(convention_contract.get("warn_only")),
            "status": audit_status if semantic_structure_findings else "not_applicable",
            "checked_axes": [
                "reuse_before_create",
                "semantic_naming",
                "global_rebinding_coupling",
                "duplicate_definitions",
                "tree_depth",
                "fan_out",
                "reuse_root_import_ratio",
            ],
        },
        "moduleization_required": moduleization_required,
        "suggested_module_root": suggested_root(str(primary["path"])) if primary and moduleization_required else None,
        "responsibility_split_plan": split_plan(str(primary["path"]), list(primary.get("responsibility_clusters", []))) if primary and moduleization_required else [],
        "semantic_refactor_plan": semantic_refactor_plan,
        "compatibility_constraints": ["preserve public entry points, CLI behavior, schema IDs, artifact paths, and validation commands"],
        "validation_scope_delta": ["affected_chain"] if moduleization_required else ["current_only"],
        "existing_debt_exemptions": [f"{item['path']}: {item.get('exemption')}" for item in exempt],
        "forbidden_raw_source_persisted": True,
        "raw_source_persisted": False,
        "scanned_file_details": scanned,
        "skipped_files": [item for item in records if item.get("scan_status") != "scanned"],
        "evidence_paths": ["stdout:code_structure_audit", "/home/swfool/.codex/skills/orchestrate-task-cycle/references/code-structure-audit.md"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only generated-code size and module-boundary audit.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--input-json", help="Governance or changed-surface JSON containing changed_files.")
    parser.add_argument("--convention-json", help="Optional JSON object or path containing code_convention_contract.")
    parser.add_argument("--from-git", action="store_true", help="Include git status --short changed files.")
    parser.add_argument("--task-id")
    for key, value in DEFAULT_THRESHOLDS.items():
        parser.add_argument(f"--{key.replace('_', '-')}", type=int, default=value)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    files = list(args.file)
    input_data: Any = None
    if args.input_json:
        input_data = load_json(args.input_json)
        files.extend(collect_changed_files(input_data))
    if args.from_git or not files:
        files.extend(git_files(root))
    thresholds = {key: int(getattr(args, key)) for key in DEFAULT_THRESHOLDS}
    convention_contract = load_optional_contract(args.convention_json)
    if convention_contract.get("status") != "provided" and input_data is not None:
        convention_contract = normalize_convention_contract(input_data)
    result = audit(root, files, thresholds, args.task_id, convention_contract)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
