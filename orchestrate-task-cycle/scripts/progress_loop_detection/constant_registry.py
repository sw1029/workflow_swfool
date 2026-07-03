from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

from . import constants as constants_module


REGISTRY_RESOURCE = "constant_registry.json"
REGEX_FLAG_NAMES = ("ASCII", "IGNORECASE", "LOCALE", "MULTILINE", "DOTALL", "VERBOSE")


def load_constant_registry() -> dict[str, Any]:
    registry_path = files(__package__).joinpath(REGISTRY_RESOURCE)
    return json.loads(registry_path.read_text(encoding="utf-8"))


def public_constant_names() -> list[str]:
    return sorted(name for name in vars(constants_module) if name.isupper() and not name.startswith("_"))


def constant_snapshot(value: Any) -> Any:
    if isinstance(value, re.Pattern):
        return {
            "kind": "regex",
            "pattern": value.pattern,
            "flags": regex_flag_names(value.flags),
        }
    if isinstance(value, set):
        return {
            "kind": "set",
            "items": sorted(constant_snapshot(item) for item in value),
        }
    if isinstance(value, tuple):
        return {
            "kind": "tuple",
            "items": [constant_snapshot(item) for item in value],
        }
    if isinstance(value, list):
        return {
            "kind": "list",
            "items": [constant_snapshot(item) for item in value],
        }
    if isinstance(value, dict):
        return {
            "kind": "dict",
            "items": {str(key): constant_snapshot(value[key]) for key in sorted(value)},
        }
    return value


def regex_flag_names(flags: int) -> list[str]:
    names: list[str] = []
    for name in REGEX_FLAG_NAMES:
        flag = getattr(re, name)
        if flags & flag:
            names.append(name)
    return names


def validate_constant_registry(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    registry = registry or load_constant_registry()
    findings: list[dict[str, Any]] = []
    entries = registry.get("entries")
    if not isinstance(entries, list):
        return {
            "status": "block",
            "registry_resource": REGISTRY_RESOURCE,
            "findings": [{"severity": "block", "code": "registry_entries_not_list"}],
        }

    entry_by_name = {str(entry.get("name")): entry for entry in entries if isinstance(entry, dict) and entry.get("name")}
    runtime_names = set(public_constant_names())
    registry_names = set(entry_by_name)
    if registry.get("coverage") == "all_public_uppercase_constants":
        for name in sorted(runtime_names - registry_names):
            findings.append({"severity": "block", "code": "constant_missing_from_registry", "name": name})
        for name in sorted(registry_names - runtime_names):
            findings.append({"severity": "block", "code": "registry_entry_without_runtime_constant", "name": name})

    for name, entry in sorted(entry_by_name.items()):
        if not hasattr(constants_module, name):
            continue
        expected = entry.get("expected")
        actual = constant_snapshot(getattr(constants_module, name))
        if actual != expected:
            findings.append(
                {
                    "severity": "block",
                    "code": "constant_registry_value_mismatch",
                    "name": name,
                    "expected": expected,
                    "actual": actual,
                }
            )
        if isinstance(expected, dict) and expected.get("kind") == "regex":
            try:
                re.compile(str(expected.get("pattern") or ""))
            except re.error as exc:
                findings.append(
                    {
                        "severity": "block",
                        "code": "constant_registry_regex_invalid",
                        "name": name,
                        "error": str(exc),
                    }
                )

    return {
        "status": "block" if any(item.get("severity") == "block" for item in findings) else "ok",
        "schema_version": registry.get("schema_version"),
        "registry_kind": registry.get("registry_kind"),
        "registry_resource": REGISTRY_RESOURCE,
        "coverage": registry.get("coverage"),
        "runtime_constant_count": len(runtime_names),
        "registry_entry_count": len(registry_names),
        "findings": findings,
    }
