#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
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


def analyze_file(root: Path, path_value: str, thresholds: dict[str, int]) -> dict[str, Any]:
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
    cluster_evidence = " ".join(python_imports(text)) if is_python else text[:12000]
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
        "responsibility_clusters": clusters,
        "cluster_count": len(clusters),
        "largest_symbols": symbols[:8],
        "soft_threshold_triggered": soft,
        "hard_threshold_triggered": hard,
    }


def audit(root: Path, files: list[str], thresholds: dict[str, int], task_id: str | None) -> dict[str, Any]:
    records = [analyze_file(root, path, thresholds) for path in sorted(dict.fromkeys(files))]
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
    if not scanned:
        audit_status = "not_applicable"
        status = "not_applicable"
    elif hard_items:
        audit_status = "refactor_required"
        status = "complete"
    elif soft_items:
        audit_status = "warn"
        status = "complete"
    else:
        audit_status = "pass"
        status = "complete"
    primary = hard_items[0] if hard_items else (soft_items[0] if soft_items else None)
    clusters_by_file = {str(item["path"]): item.get("responsibility_clusters", []) for item in scanned}
    moduleization_required = bool(hard_items)
    return {
        "step": "code_structure_audit",
        "status": status,
        "task_id": task_id or None,
        "audit_status": audit_status,
        "changed_files_scanned": [str(item["path"]) for item in scanned],
        "oversize_files": oversize,
        "thresholds": thresholds,
        "responsibility_clusters": clusters_by_file,
        "moduleization_required": moduleization_required,
        "suggested_module_root": suggested_root(str(primary["path"])) if primary and moduleization_required else None,
        "responsibility_split_plan": split_plan(str(primary["path"]), list(primary.get("responsibility_clusters", []))) if primary and moduleization_required else [],
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
    parser.add_argument("--from-git", action="store_true", help="Include git status --short changed files.")
    parser.add_argument("--task-id")
    for key, value in DEFAULT_THRESHOLDS.items():
        parser.add_argument(f"--{key.replace('_', '-')}", type=int, default=value)
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    files = list(args.file)
    if args.input_json:
        files.extend(collect_changed_files(load_json(args.input_json)))
    if args.from_git or not files:
        files.extend(git_files(root))
    thresholds = {key: int(getattr(args, key)) for key in DEFAULT_THRESHOLDS}
    result = audit(root, files, thresholds, args.task_id)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
