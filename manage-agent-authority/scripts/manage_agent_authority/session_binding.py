"""Deterministic, privacy-preserving authority-session identity bindings."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any


SESSION_BINDING_KIND = "authority_session_binding"
SESSION_BINDING_SCHEMA_VERSION = 1
_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,255}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TRUST_CLASSES = frozenset(
    {"platform_host_receipt", "agent_mediated_tty_narrowing"}
)


class SessionBindingError(ValueError):
    """Raised when a session identity is incomplete, unsafe, or caller-forged."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _opaque(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if not _OPAQUE.fullmatch(normalized):
        raise SessionBindingError(f"{label} must be a bounded opaque identifier")
    return normalized


def _digest_secret(value: Any, label: str) -> str:
    normalized = str(value or "")
    if not normalized:
        raise SessionBindingError(f"{label} is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _sha(value: Any, label: str) -> str:
    normalized = str(value or "").removeprefix("sha256:").lower()
    if not _SHA256.fullmatch(normalized):
        raise SessionBindingError(f"{label} must be a lowercase SHA-256 digest")
    return normalized


def session_ref(session_id: str) -> str:
    """Return the only tracked runtime location accepted for a session lease."""

    identifier = _opaque(session_id, "session_id")
    path = PurePosixPath(
        ".task", "authorization", "sessions", identifier, "session-lease.json"
    )
    if path.is_absolute() or ".." in path.parts:
        raise SessionBindingError("session lease ref must be repository relative")
    return path.as_posix()


def build_session_binding(
    *,
    workspace_identity: str,
    provider: str,
    thread_binding: str,
    activation_evidence_id: str,
    trust_class: str,
    approval_receipt: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build an owner-derived session binding without retaining host secrets.

    ``session_id`` is accepted only to make attempted caller overrides explicit.
    Callers must omit it; the producer always derives the identifier.
    """

    if session_id is not None:
        raise SessionBindingError("session_id is producer-derived and cannot be supplied")
    workspace = _opaque(workspace_identity, "workspace_identity")
    normalized_provider = _opaque(provider, "provider")
    evidence_id = _opaque(activation_evidence_id, "activation_evidence_id")
    if trust_class not in _TRUST_CLASSES:
        raise SessionBindingError("unsupported session trust_class")
    identity = {
        "workspace_identity": workspace,
        "provider": normalized_provider,
        "thread_binding_sha256": _digest_secret(
            thread_binding, "thread_binding"
        ),
        "activation_evidence_id": evidence_id,
        "trust_class": trust_class,
        "approval_receipt_sha256": _digest_secret(
            approval_receipt, "approval_receipt"
        ),
    }
    derived_id = f"session-{sha256_value(identity)[:32]}"
    return {
        "schema_version": SESSION_BINDING_SCHEMA_VERSION,
        "artifact_kind": SESSION_BINDING_KIND,
        "session_id": derived_id,
        **identity,
        "session_ref": session_ref(derived_id),
    }


def validate_session_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SessionBindingError("session binding must be an object")
    fields = {
        "schema_version",
        "artifact_kind",
        "session_id",
        "workspace_identity",
        "provider",
        "thread_binding_sha256",
        "activation_evidence_id",
        "trust_class",
        "approval_receipt_sha256",
        "session_ref",
    }
    if set(value) != fields:
        raise SessionBindingError("session binding fields are not closed")
    if (
        value.get("schema_version") != SESSION_BINDING_SCHEMA_VERSION
        or value.get("artifact_kind") != SESSION_BINDING_KIND
    ):
        raise SessionBindingError("unsupported session binding contract")
    trust_class = str(value.get("trust_class") or "")
    if trust_class not in _TRUST_CLASSES:
        raise SessionBindingError("unsupported session trust_class")
    identity = {
        "workspace_identity": _opaque(
            value.get("workspace_identity"), "workspace_identity"
        ),
        "provider": _opaque(value.get("provider"), "provider"),
        "thread_binding_sha256": _sha(
            value.get("thread_binding_sha256"), "thread_binding_sha256"
        ),
        "activation_evidence_id": _opaque(
            value.get("activation_evidence_id"), "activation_evidence_id"
        ),
        "trust_class": trust_class,
        "approval_receipt_sha256": _sha(
            value.get("approval_receipt_sha256"), "approval_receipt_sha256"
        ),
    }
    expected_id = f"session-{sha256_value(identity)[:32]}"
    if value.get("session_id") != expected_id:
        raise SessionBindingError("session_id does not match producer-owned identity")
    if value.get("session_ref") != session_ref(expected_id):
        raise SessionBindingError("session_ref does not match the derived session")
    return {
        "schema_version": SESSION_BINDING_SCHEMA_VERSION,
        "artifact_kind": SESSION_BINDING_KIND,
        "session_id": expected_id,
        **identity,
        "session_ref": session_ref(expected_id),
    }


__all__ = (
    "SESSION_BINDING_KIND",
    "SESSION_BINDING_SCHEMA_VERSION",
    "SessionBindingError",
    "build_session_binding",
    "canonical_bytes",
    "session_ref",
    "sha256_value",
    "validate_session_binding",
)
