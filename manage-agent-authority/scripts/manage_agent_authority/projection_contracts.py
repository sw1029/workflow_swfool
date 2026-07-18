from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import IDENTIFIER_RE
from .contracts import SHA_RE


AUTHORIZATION_ROOT = Path(".task/authorization")
STATE_ROOT = AUTHORIZATION_ROOT / "state"
MAX_INTENT_BYTES = 1024 * 1024
INTENT_DIRECTORIES = {
    "reservations": "authority_reservation",
    "use_receipts": "authority_use_receipt",
    "release_receipts": "authority_release_receipt",
    "events": "authority_grant_transition",
}

CHANGE_KEYS = {"ref", "before", "after"}
BINDING_KEYS = {"ref", "sha256"}
GRANT_USE_KEYS = {
    "grant_id",
    "grant_sha256",
    "units",
    "state_version_before",
    "state_version_after",
}
GRANT_STATE_KEYS = {
    "schema_version",
    "artifact_kind",
    "grant_id",
    "grant_sha256",
    "status",
    "remaining_uses",
    "reserved_uses",
    "consumed_uses",
    "version",
    "last_event_id",
}
RESERVATION_STATE_KEYS = {
    "schema_version",
    "artifact_kind",
    "reservation_id",
    "status",
    "version",
    "last_event_id",
}
RESERVATION_KEYS = {
    "schema_version",
    "artifact_kind",
    "reservation_id",
    "request_id",
    "request_sha256",
    "decision",
    "effective_authority_fingerprint",
    "grant_uses",
    "state_changes",
    "reserved_at",
    "idempotency_key",
}
USE_RECEIPT_KEYS = {
    "schema_version",
    "artifact_kind",
    "receipt_id",
    "reservation",
    "execution_result",
    "consumed_at",
    "grant_versions_after",
    "state_changes",
    "idempotency_key",
}
RELEASE_RECEIPT_KEYS = {
    "schema_version",
    "artifact_kind",
    "receipt_id",
    "reservation",
    "no_effect_evidence",
    "effect_status",
    "release_applied",
    "released_at",
    "idempotency_key",
    "state_changes",
}
TRANSITION_KEYS = {
    "schema_version",
    "artifact_kind",
    "event_id",
    "root_grant_id",
    "transition",
    "source_approval",
    "transitioned_at",
    "affected_before",
    "affected_grant_ids",
    "state_changes",
}
DECISION_KEYS = {
    "schema_version",
    "artifact_kind",
    "decision_id",
    "request",
    "request_sha256",
    "evaluation_context",
    "evaluation_context_sha256",
    "decision",
    "reason_codes",
    "approval_projection",
    "selected_grants",
    "lineage_grants",
    "operation_manifest",
    "effective_authority_fingerprint",
    "evaluated_at",
}
DECISION_GRANT_KEYS = {
    "grant_id",
    "grant_sha256",
    "state_version",
    "policy_snapshot",
}
GRANT_STATUSES = {
    "draft",
    "active",
    "reserved",
    "suspended",
    "revoked",
    "expired",
    "exhausted",
}
RESERVATION_STATUSES = {
    "reserved",
    "consumed",
    "released",
    "quarantined_unknown_effect",
}


def closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object.")
    missing = sorted(keys - set(value))
    extra = sorted(set(value) - keys)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unknown " + ", ".join(extra))
        raise SystemExit(f"{label} is not closed: {'; '.join(details)}.")
    return value


def identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise SystemExit(f"{label} must be a bounded opaque identifier.")
    return value


def sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise SystemExit(f"{label} must be a lowercase SHA-256 digest.")
    return value


def nonnegative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SystemExit(f"{label} must be a non-negative integer.")
    return value


def positive_int(value: Any, label: str) -> int:
    result = nonnegative_int(value, label)
    if result == 0:
        raise SystemExit(f"{label} must be a positive integer.")
    return result
