"""Content-bound bridge for revisionless legacy decision identities."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


BRIDGE_FIELDS = {
    "bridge_contract_version",
    "bridge_status",
    "artifact_id",
    "artifact_class",
    "artifact_sha256",
    "revision_id",
    "subject_digest",
    "lineage_id",
    "freshness_status",
    "evidence_ref",
    "evidence_sha256",
    "receipt_sha256",
}
OPAQUE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}")
SOURCE_LIKE_SUFFIXES = (".csv", ".json", ".jsonl", ".md", ".parquet", ".py", ".txt")


def _first_present(result: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = result
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current is None:
            continue
        if isinstance(current, (dict, list)) and not current:
            continue
        if isinstance(current, str) and not current.strip():
            continue
        return current
    return None


def terminal_consumption_claim(result: dict[str, Any]) -> bool:
    """Return whether a packet consumes an explicit terminal disposition."""
    terminal_state = _first_present(
        result,
        (
            "terminal_state",
            "terminal_outcome",
            "decision.terminal_state",
            "result.terminal_state",
        ),
    )
    return str(terminal_state or "").strip().lower() not in {
        "",
        "none",
        "not_applicable",
        "not_evaluated",
        "candidate",
        "continue",
    }


def legacy_revision_bridge_finding(
    result: dict[str, Any],
    identity: Any,
    *,
    required: bool,
) -> tuple[str, list[str]] | None:
    """Return a stable finding code and evidence for a required legacy bridge."""
    if not required:
        return None
    receipt = _first_present(
        result,
        (
            "legacy_revision_bridge_receipt",
            "decision.legacy_revision_bridge_receipt",
            "result.legacy_revision_bridge_receipt",
        ),
    )
    issues = validate_legacy_revision_bridge(receipt, identity)
    if not issues:
        return None
    code = (
        "legacy_positive_decision_revision_bridge_missing"
        if not isinstance(receipt, dict)
        else "legacy_positive_decision_revision_bridge_invalid"
    )
    return code, issues


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _opaque_scalar(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and value == value.strip()
        and OPAQUE_ID_PATTERN.fullmatch(value)
        and not value.lower().endswith(SOURCE_LIKE_SUFFIXES)
    )


def legacy_revision_bridge_sha256(receipt: dict[str, Any]) -> str:
    basis = {
        key: receipt.get(key) for key in sorted(BRIDGE_FIELDS - {"receipt_sha256"})
    }
    raw = json.dumps(
        basis,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_legacy_revision_bridge(
    receipt: Any,
    identity: Any,
) -> list[str]:
    """Return exact fields that make a positive legacy bridge unconsumable."""
    if not isinstance(receipt, dict):
        return ["legacy_revision_bridge_receipt"]
    issues: list[str] = []
    if set(receipt) != BRIDGE_FIELDS:
        issues.append("closed_schema")
    if receipt.get("bridge_contract_version") != 1:
        issues.append("bridge_contract_version")
    if receipt.get("bridge_status") != "revision_bound":
        issues.append("bridge_status")
    if receipt.get("freshness_status") != "current":
        issues.append("freshness_status")
    for field in (
        "artifact_id",
        "artifact_class",
        "revision_id",
        "lineage_id",
        "evidence_ref",
    ):
        if not _opaque_scalar(receipt.get(field)):
            issues.append(field)
    for field in (
        "artifact_sha256",
        "subject_digest",
        "evidence_sha256",
        "receipt_sha256",
    ):
        if not _full_sha256(receipt.get(field)):
            issues.append(field)
    if receipt.get("artifact_sha256") != receipt.get("subject_digest"):
        issues.append("subject_digest")
    if receipt.get("receipt_sha256") != legacy_revision_bridge_sha256(receipt):
        issues.append("receipt_sha256")

    if not isinstance(identity, dict):
        issues.append("decision_artifact_ref")
    else:
        for identity_field, receipt_field in (
            ("artifact_id", "artifact_id"),
            ("artifact_class", "artifact_class"),
            ("artifact_sha256", "artifact_sha256"),
        ):
            if identity.get(identity_field) != receipt.get(receipt_field):
                issues.append(f"decision_artifact_ref.{identity_field}")
        if identity.get("scope_verified") is not True:
            issues.append("decision_artifact_ref.scope_verified")
        if identity.get("advisory_discovery") is True:
            issues.append("decision_artifact_ref.advisory_discovery")
    return sorted(set(issues))


__all__ = [
    "BRIDGE_FIELDS",
    "legacy_revision_bridge_finding",
    "legacy_revision_bridge_sha256",
    "terminal_consumption_claim",
    "validate_legacy_revision_bridge",
]
