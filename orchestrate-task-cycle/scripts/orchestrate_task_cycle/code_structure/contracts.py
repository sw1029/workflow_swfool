from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


SOURCE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
}
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
    "numbered_shard": re.compile(
        r"(^|[/_.-])(?:chunk|shard|section|segment)[_-]?\d{2,}($|[_.-])", re.IGNORECASE
    ),
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
    "cli": {
        "argparse",
        "click",
        "typer",
        "command",
        "subcommand",
        "argv",
        "stdin",
        "stdout",
    },
    "configuration": {"config", "settings", "env", "dotenv", "toml", "yaml", "ini"},
    "provider_runtime": {
        "provider",
        "client",
        "http",
        "request",
        "response",
        "retry",
        "timeout",
        "api",
    },
    "io": {
        "path",
        "file",
        "read",
        "write",
        "open",
        "jsonl",
        "csv",
        "parquet",
        "sqlite",
    },
    "domain_transform": {
        "transform",
        "normalize",
        "extract",
        "parse",
        "convert",
        "map",
        "merge",
    },
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
    if (
        contract is None
        and isinstance(raw, dict)
        and any(key in raw for key in ("reuse_roots", "max_tree_depth", "enforcement"))
    ):
        contract = raw
    if not isinstance(contract, dict):
        return {"status": "not_provided", "enforcement": "warn", "warn_only": True}
    enforcement = (
        str(contract.get("enforcement") or contract.get("mode") or "warn")
        .strip()
        .lower()
    )
    strict_values = {
        "gate",
        "required",
        "enforce",
        "enforced",
        "block",
        "strict",
        "fail",
    }
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
    try:
        return float(raw.get(key))
    except (TypeError, ValueError):
        return None


def convention_enforced(contract: dict[str, Any]) -> bool:
    return contract.get("status") == "provided" and not bool(contract.get("warn_only"))


def reuse_root_modules(contract: dict[str, Any]) -> list[str]:
    roots = []
    for value in list_contract_values(contract, "reuse_roots") + list_contract_values(
        contract, "kernel_roots"
    ):
        normalized = value.strip().strip("./")
        if normalized.endswith(".py"):
            normalized = normalized[:-3]
        normalized = normalized.replace("/", ".").replace("\\", ".").strip(".")
        if normalized:
            roots.append(normalized)
    return sorted(dict.fromkeys(roots))


def load_json(path_value: str) -> Any:
    if path_value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    stripped = path_value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    return json.loads(Path(path_value).read_text(encoding="utf-8"))
