"""Verify host/user-signed evidence for ordinary root-grant decisions."""

from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path
from typing import Any

from .artifact_store import verify_binding
from .canonical import (
    normalized_time,
    object_sha256,
    read_object,
    sha256_file,
    write_immutable_json,
)
from .root_authority_registry import (
    SIGNATURE_ALGORITHM,
    canonical_json,
    load_registry,
)
from .root_grant_plan import _identifier, load_root_approval_plan


ROOT_AUTHORIZATION_EVIDENCE_ROOT = Path(
    ".task/authorization/root_authorization_evidence/sha256"
)
TRUST_ANCHOR_REGISTRY = (
    Path(__file__).resolve().parents[2] / "root-authorization.trust.json"
)
MAX_EVIDENCE_BYTES = 64 * 1024
EVIDENCE_KEYS = {
    "schema_version",
    "artifact_kind",
    "audience",
    "issuer",
    "authorization_id",
    "approval_plan",
    "approved",
    "decided_at",
    "evidence_id",
    "signature",
}
SIGNATURE_KEYS = {"algorithm", "key_id", "value_base64"}
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _canonical_json(value: Any) -> bytes:
    return canonical_json(value)


def _unsigned_evidence(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in EVIDENCE_KEYS if key != "signature"}


def _load_trust_registry() -> dict[str, dict[str, Any]]:
    try:
        loaded = load_registry(TRUST_ANCHOR_REGISTRY)
    except SystemExit as exc:
        raise SystemExit(
            "Root authorization trust anchors are unavailable; refusing "
            "caller-asserted root authority."
        ) from exc
    assert loaded is not None
    return loaded[1]


def _verify_rsa_signature(
    message: bytes, signature: bytes, *, modulus_hex: str, exponent: int
) -> bool:
    modulus = int(modulus_hex, 16)
    width = (modulus.bit_length() + 7) // 8
    if width < 256 or len(signature) != width:
        return False
    signature_value = int.from_bytes(signature, "big")
    if signature_value >= modulus:
        return False
    encoded = pow(signature_value, exponent, modulus).to_bytes(
        width, "big"
    )
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(message).digest()
    padding_size = width - len(digest_info) - 3
    if padding_size < 8:
        return False
    expected = b"\x00\x01" + (b"\xff" * padding_size) + b"\x00" + digest_info
    return encoded == expected


def validate_root_authorization_evidence(
    value: Any,
    *,
    plan_binding: dict[str, str],
    plan: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != EVIDENCE_KEYS:
        raise SystemExit(
            "Root authorization evidence must be a closed signed object."
        )
    signature = value.get("signature")
    if (
        not isinstance(signature, dict)
        or set(signature) != SIGNATURE_KEYS
        or signature.get("algorithm") != SIGNATURE_ALGORITHM
    ):
        raise SystemExit("Root authorization evidence signature is invalid.")
    issuer = _identifier(value.get("issuer"), "root authorization issuer")
    authorization_id = _identifier(
        value.get("authorization_id"), "root authorization authorization_id"
    )
    evidence_id = _identifier(
        value.get("evidence_id"), "root authorization evidence_id"
    )
    decided_at = normalized_time(
        value.get("decided_at"), "root authorization decided_at"
    )
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind")
        != "authority_root_user_authorization_evidence"
        or value.get("audience")
        != "manage-agent-authority/root-grant"
        or value.get("approved") is not True
        or value.get("approval_plan") != plan_binding
    ):
        raise SystemExit(
            "Root authorization evidence does not approve the exact root plan."
        )
    from .canonical import parse_time

    if parse_time(decided_at, "root authorization decided_at") < parse_time(
        plan["prepared_at"], "root approval prepared_at"
    ):
        raise SystemExit("Root authorization evidence predates the root plan.")
    if parse_time(decided_at, "root authorization decided_at") >= parse_time(
        plan["approval_projection"]["validity"]["expires_at"],
        "root approval expires_at",
    ):
        raise SystemExit("Root authorization evidence is outside the approval window.")
    key_id = _identifier(signature.get("key_id"), "root authorization key_id")
    try:
        signature_bytes = base64.b64decode(
            str(signature.get("value_base64") or ""), validate=True
        )
    except (binascii.Error, ValueError) as exc:
        raise SystemExit(
            "Root authorization evidence signature is not valid base64."
        ) from exc
    anchors = _load_trust_registry()
    anchor = anchors.get(key_id)
    if (
        anchor is None
        or anchor["status"] != "active"
        or anchor["issuer"] != issuer
        or not _verify_rsa_signature(
            _canonical_json(_unsigned_evidence(value)),
            signature_bytes,
            modulus_hex=anchor["modulus_hex"],
            exponent=anchor["public_exponent"],
        )
    ):
        raise SystemExit(
            "Root authorization evidence is not signed by an active trusted "
            "host/user authorization key."
        )
    normalized = {
        "schema_version": 1,
        "artifact_kind": "authority_root_user_authorization_evidence",
        "audience": "manage-agent-authority/root-grant",
        "issuer": issuer,
        "authorization_id": authorization_id,
        "approval_plan": plan_binding,
        "approved": True,
        "decided_at": decided_at,
        "evidence_id": evidence_id,
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": key_id,
            "value_base64": base64.b64encode(signature_bytes).decode("ascii"),
        },
    }
    if value != normalized:
        raise SystemExit("Root authorization evidence is not canonical.")
    return normalized


def publish_root_authorization_evidence(
    root: Path,
    evidence: Any,
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if not isinstance(evidence, dict) or not isinstance(
        evidence.get("approval_plan"), dict
    ):
        raise SystemExit("Root authorization evidence lacks its exact plan binding.")
    plan_binding, plan = load_root_approval_plan(
        root, evidence["approval_plan"], skills_root=skills_root
    )
    normalized = validate_root_authorization_evidence(
        evidence, plan_binding=plan_binding, plan=plan
    )
    fingerprint = object_sha256(normalized)
    path = root / ROOT_AUTHORIZATION_EVIDENCE_ROOT / f"{fingerprint}.json"
    digest = write_immutable_json(
        path, normalized, "root authorization evidence"
    )
    return {
        "status": "verified_and_published",
        "authorization_evidence": {
            "ref": path.relative_to(root).as_posix(),
            "sha256": digest,
        },
        "authorization_trust_class": "host_user_signed_exact_plan",
        "authority_effects_applied": False,
        "model_authored_mechanical_bytes": 0,
    }


def load_root_authorization_evidence(
    root: Path,
    binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    path = verify_binding(root, binding, "root authorization evidence")
    try:
        path.relative_to(root / ROOT_AUTHORIZATION_EVIDENCE_ROOT)
    except ValueError as exc:
        raise SystemExit(
            "Root authorization evidence is outside its verified producer CAS."
        ) from exc
    if path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise SystemExit("Root authorization evidence exceeds 64 KiB.")
    normalized_binding = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    if normalized_binding != binding:
        raise SystemExit("Root authorization evidence binding is not canonical.")
    value = read_object(path, "root authorization evidence")
    if not isinstance(value.get("approval_plan"), dict):
        raise SystemExit("Root authorization evidence lacks its plan binding.")
    plan_binding, plan = load_root_approval_plan(
        root, value["approval_plan"], skills_root=skills_root
    )
    normalized = validate_root_authorization_evidence(
        value, plan_binding=plan_binding, plan=plan
    )
    if (
        value != normalized
        or path.name != f"{object_sha256(normalized)}.json"
    ):
        raise SystemExit(
            "Root authorization evidence differs from its verified CAS rendering."
        )
    return normalized_binding, normalized, plan


__all__ = (
    "ROOT_AUTHORIZATION_EVIDENCE_ROOT",
    "SIGNATURE_ALGORITHM",
    "TRUST_ANCHOR_REGISTRY",
    "load_root_authorization_evidence",
    "publish_root_authorization_evidence",
    "validate_root_authorization_evidence",
)
