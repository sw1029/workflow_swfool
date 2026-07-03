from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any


REGISTRY_FILENAME = "refactor_constant_registry.json"
PACKAGE_NAME = __package__ or "anti_loop_provider"


def constant_registry_path() -> Path:
    return Path(__file__).resolve().with_name(REGISTRY_FILENAME)


def load_constant_registry(path: str | Path | None = None) -> dict[str, Any]:
    registry_path = Path(path) if path is not None else constant_registry_path()
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schema_version": "anti-loop-refactor-constant-registry-v1",
            "status": "error",
            "entries": [],
            "error": f"{type(exc).__name__}:{exc}",
        }


def _module_for_entry(entry: dict[str, Any]) -> Any | None:
    module_name = str(entry.get("module") or "").strip()
    if not module_name:
        return None
    return importlib.import_module(f"{PACKAGE_NAME}.{module_name}")


def _constant_kind(value: Any) -> str:
    if isinstance(value, re.Pattern):
        return "pattern"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, tuple):
        return "tuple"
    if isinstance(value, set):
        return "set"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def _registry_value(value: Any) -> Any:
    if isinstance(value, re.Pattern):
        return value.pattern
    if isinstance(value, dict):
        return {str(key): _registry_value(child) for key, child in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (set, tuple, list)):
        return sorted(_registry_value(item) for item in value)
    return value


def validate_constant_registry(path: str | Path | None = None) -> dict[str, Any]:
    registry = load_constant_registry(path)
    findings: list[dict[str, Any]] = []
    checked = 0
    for entry in registry.get("entries", []):
        if not isinstance(entry, dict):
            findings.append({"severity": "block", "code": "malformed_entry", "entry": entry})
            continue
        module_name = str(entry.get("module") or "")
        name = str(entry.get("name") or "")
        try:
            module = _module_for_entry(entry)
        except Exception as exc:
            findings.append(
                {
                    "severity": "block",
                    "code": "constant_module_import_failed",
                    "module": module_name,
                    "name": name,
                    "error": f"{type(exc).__name__}:{exc}",
                }
            )
            continue
        if module is None or not name:
            findings.append({"severity": "block", "code": "constant_entry_missing_module_or_name", "entry": entry})
            continue
        if not hasattr(module, name):
            findings.append({"severity": "block", "code": "constant_missing", "module": module_name, "name": name})
            continue
        checked += 1
        value = getattr(module, name)
        expected_type = entry.get("expected_type")
        actual_type = _constant_kind(value)
        if expected_type and actual_type != expected_type:
            findings.append(
                {
                    "severity": "block",
                    "code": "constant_type_mismatch",
                    "module": module_name,
                    "name": name,
                    "expected_type": expected_type,
                    "actual_type": actual_type,
                }
            )
        if "expected_value" in entry:
            expected_value = entry["expected_value"]
            actual_value = _registry_value(value)
            if actual_value != expected_value:
                findings.append(
                    {
                        "severity": "block",
                        "code": "constant_value_mismatch",
                        "module": module_name,
                        "name": name,
                        "expected_value": expected_value,
                        "actual_value": actual_value,
                    }
                )
        expected_pattern_contains = entry.get("expected_pattern_contains")
        if expected_pattern_contains and expected_pattern_contains not in str(_registry_value(value)):
            findings.append(
                {
                    "severity": "block",
                    "code": "constant_pattern_mismatch",
                    "module": module_name,
                    "name": name,
                    "expected_pattern_contains": expected_pattern_contains,
                }
            )
    return {
        "schema_version": registry.get("schema_version"),
        "registry_path": str(Path(path).resolve()) if path is not None else str(constant_registry_path()),
        "checked_count": checked,
        "finding_count": len(findings),
        "status": "pass" if not findings else "block",
        "findings": findings,
    }
