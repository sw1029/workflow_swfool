"""Compile closed child-delegation intent and expose exact grant replay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import (
    _register_compiled_grant,
    grant_path,
    load_grant,
    state_path,
)
from .canonical import normalized_time, object_sha256
from .contracts import validate_grant
from .producer_capability import _AUTHORITY_PRODUCER_CAPABILITY


DELEGATION_SEMANTIC_KEYS = {
    "holder_rank",
    "capabilities",
    "subjects",
    "operations",
    "risk_ceiling",
    "decision_classes",
    "cardinality",
    "max_uses",
    "expires_at",
    "session_id",
    "task_id",
    "improvement_id",
}


def _compact_result(
    root: Path,
    grant: dict[str, Any],
    digest: str,
    state: dict[str, Any],
    *,
    status: str,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    result = {
        "status": status,
        "grant_id": grant["grant_id"],
        "lineage_id": grant["lineage_id"],
        "grant_binding": {
            "ref": grant_path(root, grant["grant_id"]).relative_to(root).as_posix(),
            "sha256": digest,
        },
        "state_ref": state_path(root, grant["grant_id"])
        .relative_to(root)
        .as_posix(),
        "grant_status": state["status"],
        "state_version": state["version"],
        "model_call_count": 0,
        "model_visible_bytes": 0,
        "model_authored_mechanical_bytes": 0,
    }
    if fingerprint is not None:
        result["delegation_intent_fingerprint"] = fingerprint
    return result


def replay_registered_grant(
    root: Path, raw: dict[str, Any]
) -> dict[str, Any]:
    """Read an exact registered grant; never create prospective authority."""

    workspace = root.resolve()
    supplied = validate_grant(raw)
    artifact = grant_path(workspace, supplied["grant_id"])
    projection = state_path(workspace, supplied["grant_id"])
    if not artifact.is_file() or not projection.is_file():
        raise SystemExit(
            "register-grant is sealed to exact historical replay; use a "
            "registered compiler/materializer for prospective grant issuance."
        )
    existing, digest, state = load_grant(workspace, supplied["grant_id"])
    if existing != supplied:
        raise SystemExit("Historical grant replay differs from registered bytes.")
    return _compact_result(
        workspace, existing, digest, state, status="replayed"
    )


def _delegation_candidate(
    parent: dict[str, Any],
    parent_digest: str,
    semantics: dict[str, Any],
    *,
    delegated_at: str,
) -> dict[str, Any]:
    if not isinstance(semantics, dict):
        raise SystemExit("Delegation semantics must be an object.")
    extra = sorted(set(semantics) - DELEGATION_SEMANTIC_KEYS)
    missing = sorted(DELEGATION_SEMANTIC_KEYS - set(semantics))
    if extra or missing:
        raise SystemExit(
            f"Delegation semantics has unknown={extra} missing={missing}."
        )
    return {
        "schema_version": 2,
        "artifact_kind": "authority_grant",
        "grant_id": "authg-delegation-provisional",
        "lineage_id": parent["lineage_id"],
        "parent_grant_id": parent["grant_id"],
        "issuer_rank": parent["holder_rank"],
        "holder_rank": semantics["holder_rank"],
        "capabilities": semantics["capabilities"],
        "subjects": semantics["subjects"],
        "operations": semantics["operations"],
        "risk_ceiling": semantics["risk_ceiling"],
        "decision_classes": semantics["decision_classes"],
        "cardinality": semantics["cardinality"],
        "max_uses": semantics["max_uses"],
        "not_before": delegated_at,
        "expires_at": semantics["expires_at"],
        "session_id": semantics["session_id"],
        "task_id": semantics["task_id"],
        "improvement_id": semantics["improvement_id"],
        "source_approval": {
            "ref": (
                Path(".task/authorization/grants")
                / f"{parent['grant_id']}.json"
            ).as_posix(),
            "sha256": parent_digest,
        },
        "policy_snapshot": parent["policy_snapshot"],
        "created_at": delegated_at,
        "idempotency_key": "authgk-delegation-provisional",
    }


def compile_delegated_grant(
    root: Path,
    parent_grant_id: str,
    semantics: dict[str, Any],
    *,
    delegated_at: str,
) -> dict[str, Any]:
    """Derive and register one exact child from compact narrowing semantics."""

    workspace = root.resolve()
    at = normalized_time(delegated_at, "delegated_at")
    parent, parent_digest, parent_state = load_grant(
        workspace, parent_grant_id
    )
    if parent_state["status"] != "active":
        raise SystemExit("Delegation requires an active parent grant.")
    provisional = validate_grant(
        _delegation_candidate(
            parent, parent_digest, semantics, delegated_at=at
        )
    )
    semantic_projection = {
        key: provisional[key]
        for key in sorted(DELEGATION_SEMANTIC_KEYS)
    }
    identity = object_sha256(
        {
            "parent_grant_id": parent["grant_id"],
            "parent_grant_sha256": parent_digest,
            "delegated_at": at,
            "semantics": semantic_projection,
        }
    )
    grant = validate_grant(
        {
            **provisional,
            "grant_id": f"authg-{identity[:24]}",
            "idempotency_key": f"authgk-{identity[:24]}",
        }
    )
    registered = _register_compiled_grant(
        workspace,
        grant,
        parent_id=parent["grant_id"],
        producer_capability=_AUTHORITY_PRODUCER_CAPABILITY,
    )
    return _compact_result(
        workspace,
        registered["grant"],
        registered["grant_sha256"],
        registered["state"],
        status="delegated",
        fingerprint=identity,
    )


__all__ = (
    "DELEGATION_SEMANTIC_KEYS",
    "compile_delegated_grant",
    "replay_registered_grant",
)
