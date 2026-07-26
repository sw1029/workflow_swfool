"""Domain-separated TTY signer for 30-day authority-mode activations."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from . import root_authorization_signer as signer
from .authority_interaction import (
    activation_evidence_unsigned,
    load_activation_plan,
    validate_activation_evidence,
)
from .root_authority_registry import SIGNATURE_ALGORITHM, canonical_json, load_registry, sha256_bytes
from .root_authorization_evidence import TRUST_ANCHOR_REGISTRY


def _summary(workspace: Path, binding: dict[str, str], plan: dict[str, Any]) -> dict[str, Any]:
    return {"workspace": str(workspace), "activation_plan": binding, "authority_interaction_mode": plan["authority_interaction_mode"], "prepared_at": plan["prepared_at"], "expires_at": plan["expires_at"], "non_sliding_ttl_days": plan["non_sliding_ttl_days"], "profile": plan["profile"], "limits": plan["limits"], "always_ask": plan["always_ask"]}


def _window(plan: dict[str, Any], at: str) -> None:
    signer._assert_approval_window({"prepared_at": plan["prepared_at"], "approval_projection": {"validity": {"expires_at": plan["expires_at"]}}}, at)


def activate_authority_mode(workspace: Path, *, activation_plan_ref: str, activation_plan_sha256: str, key_id: str) -> dict[str, Any]:
    """Sign exactly one mode activation after a real controlling-TTY confirmation."""
    root = signer._workspace(str(workspace))
    digest = signer._digest(activation_plan_sha256, "activation plan SHA-256")
    binding = {"ref": str(activation_plan_ref), "sha256": digest}
    normalized_binding, plan = load_activation_plan(root, binding)
    if normalized_binding != binding:
        raise SystemExit("Authority interaction activation plan binding is not canonical.")
    registry = load_registry(TRUST_ANCHOR_REGISTRY)
    assert registry is not None
    anchor, registry_digest = signer._active_anchor(registry, key_id), registry[3]
    _window(plan, signer._utc_now())
    expected = f"ACTIVATE AUTHORITY MODE {digest}"
    if signer._tty_confirmation(_summary(root, binding, plan), expected) != expected:
        raise SystemExit("Authority interaction activation was not confirmed.")
    decided_at = signer._utc_now()
    binding_after, plan_after = load_activation_plan(root, binding)
    if binding_after != binding or plan_after != plan:
        raise SystemExit("Authority interaction activation plan changed during confirmation.")
    registry_after = load_registry(TRUST_ANCHOR_REGISTRY)
    assert registry_after is not None
    if registry_after[3] != registry_digest or signer._active_anchor(registry_after, key_id) != anchor:
        raise SystemExit("Root authorization registry changed during confirmation.")
    _window(plan_after, decided_at)
    private_key = signer._load_signing_key(key_id, anchor)
    registry_before_signing = load_registry(TRUST_ANCHOR_REGISTRY)
    assert registry_before_signing is not None
    if registry_before_signing[3] != registry_digest:
        raise SystemExit("Root authorization registry changed during confirmation.")
    unsigned = activation_evidence_unsigned(binding, plan_after, key_id=key_id, decided_at=decided_at)
    hashes, _serialization, padding, _rsa = signer._cryptography()
    signature = private_key.sign(canonical_json(unsigned), padding.PKCS1v15(), hashes.SHA256())
    evidence = {**unsigned, "signature": {"algorithm": SIGNATURE_ALGORITHM, "key_id": key_id, "value_base64": base64.b64encode(signature).decode("ascii")}}
    if validate_activation_evidence(evidence, root=root, plan_binding=binding, plan=plan_after) != evidence:
        raise SystemExit("Authority interaction signer self-verification changed bytes.")
    payload = canonical_json(evidence)
    path = signer._ensure_outbox() / f"{evidence['evidence_id']}.json"
    signer._exclusive_outbox_write(path, payload)
    return {"activation_plan": binding, "evidence_path": str(path), "evidence_sha256": sha256_bytes(payload), "key_id": key_id}
