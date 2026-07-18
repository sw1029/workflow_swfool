"""Closed schemas and deterministic identities for legacy retirement."""

from __future__ import annotations

from typing import Any

from .legacy_retirement_store import canonical_sha256


PREPARE_KEYS = {
    "schema_version",
    "artifact_kind",
    "transaction_id",
    "plan",
    "source_snapshot",
    "overlay",
}
OVERLAY_KEYS = {
    "schema_version",
    "artifact_kind",
    "retirement_id",
    "disposition",
    "source_pack",
    "eligibility",
    "non_claims",
    "authority",
    "transaction",
}
COMPLETION_KEYS = {
    "schema_version",
    "artifact_kind",
    "transaction_id",
    "status",
    "prepare",
    "source_snapshot",
    "overlay",
    "source_pack",
    "completed_at",
}
ACTIVATION_KEYS = {
    "schema_version",
    "artifact_kind",
    "activation_id",
    "retirement",
    "completion",
    "authority_use_receipt",
    "activated_at",
}
SOURCE_OVERLAY_KEYS = {
    "pack_id",
    "ref",
    "file_sha256",
    "canonical_pack_sha256",
    "snapshot_ref",
    "snapshot_sha256",
    "declared_status",
}
ELIGIBILITY_KEYS = {
    "contract_version",
    "blocking_finding_codes",
    "blocking_finding_fingerprint",
    "raw_contract_status",
    "derived_operational_status",
    "current_task_bound",
}
NON_CLAIMS = {
    "pack_completed": False,
    "items_completed": False,
    "dependencies_satisfied": False,
    "provenance_repaired": False,
    "historical_authority_pass": False,
    "raw_pack_modified": False,
}


def closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return value


def binding(value: Any, label: str) -> dict[str, str]:
    row = closed(value, {"ref", "sha256"}, label)
    return {"ref": str(row["ref"]), "sha256": str(row["sha256"])}


def transaction_id(plan: dict[str, Any]) -> str:
    return "lgrtx-" + canonical_sha256(plan)[:32]


def snapshot_id(file_sha256: str) -> str:
    return "lgrsnap-" + file_sha256[:32]


__all__ = (
    "ACTIVATION_KEYS",
    "COMPLETION_KEYS",
    "ELIGIBILITY_KEYS",
    "NON_CLAIMS",
    "OVERLAY_KEYS",
    "PREPARE_KEYS",
    "SOURCE_OVERLAY_KEYS",
    "binding",
    "closed",
    "snapshot_id",
    "transaction_id",
)
