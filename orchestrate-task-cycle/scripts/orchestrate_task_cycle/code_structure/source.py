from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import Any

from .contracts import (
    CLUSTER_KEYWORDS,
    EXEMPT_NAMES,
    EXEMPT_PARTS,
    GLOBAL_REBINDING_PATTERNS,
    MECHANICAL_NAME_PATTERNS,
    SOURCE_SUFFIXES,
    list_contract_values,
    reuse_root_modules,
)


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
    if path.name in EXEMPT_NAMES or parts & EXEMPT_PARTS:
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
        if suffix in {".py", ".sh"}:
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
                symbols.append(
                    {
                        "name": node.name,
                        "kind": type(node).__name__.replace("Def", "").lower(),
                        "loc": loc,
                    }
                )
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
    signals: list[str] = []
    for code, pattern in MECHANICAL_NAME_PATTERNS.items():
        candidate = path.stem if code == "numeric_only_stem" else target
        if pattern.search(candidate):
            signals.append(code)
    for index, raw_pattern in enumerate(
        list_contract_values(contract, "forbidden_name_patterns")
    ):
        try:
            if re.search(raw_pattern, target):
                signals.append(f"repo_forbidden_name_pattern_{index + 1}")
        except re.error:
            signals.append(f"invalid_repo_forbidden_name_pattern_{index + 1}")
    return sorted(set(signals))


def global_rebinding_signals(text: str) -> list[str]:
    return sorted(
        {
            code
            for code, pattern in GLOBAL_REBINDING_PATTERNS.items()
            if pattern.search(text)
        }
    )


def import_reuse_counts(
    imports: list[str], contract: dict[str, Any]
) -> tuple[int, int, float | None]:
    roots = reuse_root_modules(contract)
    if not roots:
        return (0, len(imports), None)
    total = len(imports)
    if total == 0:
        return (0, 0, None)
    reused = sum(
        1
        for imported in imports
        if any(
            imported.strip() == root or imported.strip().startswith(f"{root}.")
            for root in roots
        )
    )
    return (reused, total, reused / total)


def clusters_for(
    path: str, evidence_text: str, symbols: list[dict[str, Any]]
) -> list[str]:
    haystack = " ".join(
        [path, *(str(item.get("name", "")) for item in symbols), evidence_text]
    ).lower()
    return sorted(
        {
            cluster
            for cluster, keywords in CLUSTER_KEYWORDS.items()
            if any(keyword in haystack for keyword in keywords)
        }
    )


def suggested_root(path: str) -> str:
    p = Path(path)
    return (p.parent / p.stem).as_posix() if p.suffix else (p / "modules").as_posix()


def split_plan(path: str, clusters: list[str]) -> list[dict[str, str]]:
    root = suggested_root(path)
    selected = clusters[:6] if clusters else ["core"]
    return [
        {"target_module": f"{root}/{cluster}.py", "responsibility": cluster}
        for cluster in selected
    ]


def analyze_file(
    root: Path,
    path_value: str,
    thresholds: dict[str, int],
    convention_contract: dict[str, Any],
) -> dict[str, Any]:
    path = Path(path_value)
    abs_path = path if path.is_absolute() else root / path
    rel = path_value if not path.is_absolute() else path.as_posix()
    if not abs_path.is_file():
        return {"path": rel, "scan_status": "missing"}
    if is_exempt(path):
        return {
            "path": rel,
            "scan_status": "exempt",
            "exemption": "generated_vendor_migration_snapshot_or_lockfile",
        }
    if not is_source(path):
        return {"path": rel, "scan_status": "not_source"}
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {
            "path": rel,
            "scan_status": "unreadable",
            "error": exc.__class__.__name__,
        }
    logical_loc = logical_line_count(text, path.suffix.lower())
    is_python = path.suffix.lower() == ".py"
    symbols = python_symbols(text) if is_python else []
    imports = python_imports(text) if is_python else []
    clusters = clusters_for(
        rel, " ".join(imports) if is_python else text[:12000], symbols
    )
    largest_function = max(
        (
            int(item["loc"])
            for item in symbols
            if item["kind"] in {"function", "asyncfunction"}
        ),
        default=0,
    )
    largest_class = max(
        (int(item["loc"]) for item in symbols if item["kind"] == "class"), default=0
    )
    size_pressure = (
        logical_loc >= thresholds["soft_file_logical_loc"]
        or largest_function >= thresholds["soft_function_logical_loc"]
        or largest_class >= thresholds["soft_class_logical_loc"]
    )
    hard = (
        logical_loc >= thresholds["hard_file_logical_loc"]
        or largest_function >= thresholds["hard_function_logical_loc"]
        or largest_class >= thresholds["hard_class_logical_loc"]
        or (
            len(clusters) >= thresholds["hard_responsibility_cluster_count"]
            and size_pressure
        )
    )
    soft = (
        logical_loc >= thresholds["soft_file_logical_loc"]
        or largest_function >= thresholds["soft_function_logical_loc"]
        or largest_class >= thresholds["soft_class_logical_loc"]
        or len(clusters) >= thresholds["soft_responsibility_cluster_count"]
    )
    reuse = import_reuse_counts(imports, convention_contract)
    rebinding = global_rebinding_signals(text)
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
        "global_rebinding_signals": rebinding,
        "global_rebinding_signal_count": len(rebinding),
        "import_count": len(imports),
        "reuse_root_import_count": reuse[0],
        "reuse_root_import_ratio": reuse[2],
        "soft_threshold_triggered": soft,
        "hard_threshold_triggered": hard,
    }
