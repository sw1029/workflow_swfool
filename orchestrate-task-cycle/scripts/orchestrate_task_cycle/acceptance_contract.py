"""Canonical acceptance-contract projection shared by workflow consumers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


_REGISTRY_PATH = (
    Path(__file__).resolve().parents[3]
    / "normalize-acceptance-and-demo"
    / "references"
    / "acceptance-contract-registry-v1.json"
)


@lru_cache(maxsize=1)
def _registry() -> dict[str, Any]:
    value = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or value.get("artifact_kind") != "acceptance_contract_field_registry"
    ):
        raise RuntimeError("acceptance contract registry is invalid")
    return value


def rich_contract_fields() -> frozenset[str]:
    return frozenset(
        _registry()["canonical_paths"]["rich_acceptance_contract"]
    )


def verifier_contract_fields() -> frozenset[str]:
    return frozenset(
        _registry()["nested_contracts"]["acceptance_verifier_contract"]["fields"]
    )


def acceptance_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    contract = value.get("acceptance_contract")
    return contract if isinstance(contract, dict) else {}


def acceptance_verifier_contract(value: Any) -> dict[str, Any]:
    """Read the nested canonical path, then the historical direct alias."""

    if not isinstance(value, dict):
        return {}
    contract = acceptance_contract(value)
    verifier = contract.get("acceptance_verifier_contract")
    if isinstance(verifier, dict):
        return verifier
    legacy = value.get("acceptance_verifier_contract")
    return legacy if isinstance(legacy, dict) else {}


def required_verifier_is_unverifiable(value: Any) -> bool:
    verifier = acceptance_verifier_contract(value)
    if not verifier:
        return False
    statuses = frozenset(
        _registry()["nested_contracts"]["acceptance_verifier_contract"][
            "unverifiable_statuses"
        ]
    )
    status = str(verifier.get("evaluation_status") or "").strip().lower()
    required = verifier.get("verifier_required") is True or bool(
        str(verifier.get("required_verifier") or "").strip()
    )
    if required and (not status or status in statuses):
        return True
    required_hooks = verifier.get("required_gate_hooks")
    hook_required = isinstance(required_hooks, list) and bool(required_hooks)
    hook_status = str(verifier.get("gate_hook_status") or "").strip().lower()
    return hook_required and (not hook_status or hook_status in statuses)


def consumer_projection(
    value: dict[str, Any],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Expose canonical nested values through historical consumer aliases."""

    projected = dict(value)
    contract = acceptance_contract(value)
    conflicts: list[str] = []
    for field in rich_contract_fields():
        if field not in contract:
            continue
        if field in value and value[field] != contract[field]:
            conflicts.append(field)
        projected[field] = contract[field]
    derived_unverifiable = required_verifier_is_unverifiable(value)
    supplied = value.get("unverifiable_acceptance_contract")
    if derived_unverifiable and supplied is not None and supplied is not True:
        conflicts.append("unverifiable_acceptance_contract")
    if derived_unverifiable:
        projected["unverifiable_acceptance_contract"] = True
        projected["acceptance_verifier_not_evaluated"] = True
    return projected, tuple(sorted(set(conflicts)))


__all__ = (
    "acceptance_contract",
    "acceptance_verifier_contract",
    "consumer_projection",
    "required_verifier_is_unverifiable",
    "rich_contract_fields",
    "verifier_contract_fields",
)
