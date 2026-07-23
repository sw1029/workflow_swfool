"""Load the versioned canonical acceptance field registry."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


REGISTRY_SCHEMA_VERSION = 1
REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "references"
    / "acceptance-contract-registry-v1.json"
)


@lru_cache(maxsize=1)
def registry() -> dict[str, Any]:
    value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != REGISTRY_SCHEMA_VERSION
        or value.get("artifact_kind") != "acceptance_contract_field_registry"
    ):
        raise RuntimeError("acceptance contract registry is invalid")
    paths = value.get("canonical_paths")
    nested = value.get("nested_contracts")
    if not isinstance(paths, dict) or not isinstance(nested, dict):
        raise RuntimeError("acceptance contract registry sections are invalid")
    required_groups = {
        "core_top_level",
        "compiler_derived_top_level",
        "rich_acceptance_contract",
    }
    if set(paths) != required_groups:
        raise RuntimeError("acceptance contract canonical path groups are invalid")
    for group in required_groups:
        fields = paths[group]
        if (
            not isinstance(fields, list)
            or fields != sorted(fields)
            or len(fields) != len(set(fields))
            or any(not isinstance(field, str) or not field for field in fields)
        ):
            raise RuntimeError(f"acceptance contract registry group is invalid: {group}")
    verifier = nested.get("acceptance_verifier_contract")
    if (
        set(nested) != {"acceptance_verifier_contract"}
        or not isinstance(verifier, dict)
        or set(verifier) != {"fields", "unverifiable_statuses"}
    ):
        raise RuntimeError("acceptance verifier registry is invalid")
    for key in ("fields", "unverifiable_statuses"):
        values = verifier[key]
        if (
            not isinstance(values, list)
            or values != sorted(values)
            or len(values) != len(set(values))
        ):
            raise RuntimeError(f"acceptance verifier registry list is invalid: {key}")
    return value


def canonical_fields(group: str) -> frozenset[str]:
    return frozenset(registry()["canonical_paths"][group])


RICH_ACCEPTANCE_CONTRACT_FIELDS = canonical_fields("rich_acceptance_contract")
VERIFIER_CONTRACT_FIELDS = frozenset(
    registry()["nested_contracts"]["acceptance_verifier_contract"]["fields"]
)
UNVERIFIABLE_STATUSES = frozenset(
    registry()["nested_contracts"]["acceptance_verifier_contract"][
        "unverifiable_statuses"
    ]
)


def required_verifier_is_unverifiable(contract: Any) -> bool:
    """Derive fail-closed verifier/hook incompleteness from canonical input."""

    if not isinstance(contract, dict):
        return False
    verifier = contract.get("acceptance_verifier_contract")
    if not isinstance(verifier, dict):
        return False
    status = str(verifier.get("evaluation_status") or "").strip().lower()
    verifier_required = verifier.get("verifier_required") is True or bool(
        str(verifier.get("required_verifier") or "").strip()
    )
    if verifier_required and (not status or status in UNVERIFIABLE_STATUSES):
        return True
    required_hooks = verifier.get("required_gate_hooks")
    hook_required = isinstance(required_hooks, list) and bool(required_hooks)
    hook_status = str(verifier.get("gate_hook_status") or "").strip().lower()
    return hook_required and (
        not hook_status or hook_status in UNVERIFIABLE_STATUSES
    )


__all__ = (
    "REGISTRY_PATH",
    "REGISTRY_SCHEMA_VERSION",
    "RICH_ACCEPTANCE_CONTRACT_FIELDS",
    "UNVERIFIABLE_STATUSES",
    "VERIFIER_CONTRACT_FIELDS",
    "canonical_fields",
    "registry",
    "required_verifier_is_unverifiable",
)
