from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import manage_agent_authority.root_authorization_evidence as authorization
from manage_agent_authority.root_authorization_evidence import (
    SIGNATURE_ALGORITHM,
    publish_root_authorization_evidence,
)


_MODULUS_HEX = (
    "d5e8280502a395626ab6f847bc020607afae9acab3fd813463b2e5956efc2d45e"
    "772ab3ca60e5050e6cb13cdeedd0cb77146daae747dd5b51da85764c4aaa21c6"
    "543e7710692856ed5060eee7bdef6d1b0b6b14cd5a3eedd62fb0c82ce01ae734"
    "389f8d4ea187c1ea51eccd3c83db3e22b6c8050c143dad8bf2d750c4ac1b9ed"
    "64dc0ea86ef8e455a0332a88cae4b1866ebe53413963b50e85ddd096d1efca06"
    "3cc4ee71f0a89f0565e2a1c68d5ed812dac2453a0d6a8edb6e531a70d255cfc"
    "0f90bc9fe90ff39a4887d07ea530cbd2f7a7a644ac9a182dcb06cbc8c9e5c8c"
    "7c72727ff526baa2215ee2b7ea4d3c2d128660954abd9ba256280100777bbe6f27"
)
_PRIVATE_EXPONENT_HEX = (
    "812104b256f029889ff8947e6420a9ede495a31c25a12e13a79bf766f3a38831"
    "0ae74e37ee86a0358bc84c21a51b619c86901f5df134dad885c424a87ae6070c"
    "329580c1da6b2e8c6ef743f6f3baf02f905e0e94de38cd99c286e0514120ad64"
    "7d011815c5666d31e811652a49574ba03256984a27b6aeb0e9b7fca624503921"
    "85d69ab399903ec65e942e17e4c988fee3f0727d61a23dc95428c1a22155c1a"
    "7aa76c8eff73c391700bd896ea0424686d7f70b0f564fcd0621e2e5f85e7409"
    "bf3e490a9f8099e65d0a439ad3c8abb9b77c49212babf95415ebad8ee9be1429"
    "a217721177814a3573f5ab48d001cacca824152b6ea3a004b924934e942455441"
)
_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
TEST_KEY_ID = "test-host-user-key"
TEST_ISSUER = "test-host-user-mediator"


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def install_test_trust_anchor(monkeypatch: Any, directory: Path) -> Path:
    registry = directory / "test-root-authorization.trust.json"
    value = {
        "schema_version": 1,
        "artifact_kind": "authority_root_authorization_trust_anchors",
        "keys": [
            {
                "key_id": TEST_KEY_ID,
                "issuer": TEST_ISSUER,
                "algorithm": SIGNATURE_ALGORITHM,
                "modulus_hex": _MODULUS_HEX,
                "public_exponent": 65537,
                "status": "active",
            }
        ],
    }
    registry.write_bytes(_canonical_json(value))
    monkeypatch.setattr(authorization, "TRUST_ANCHOR_REGISTRY", registry)
    return registry


def _signature(message: bytes) -> str:
    modulus = int(_MODULUS_HEX, 16)
    width = (modulus.bit_length() + 7) // 8
    digest_info = _DIGEST_INFO_PREFIX + hashlib.sha256(message).digest()
    encoded = (
        b"\x00\x01"
        + (b"\xff" * (width - len(digest_info) - 3))
        + b"\x00"
        + digest_info
    )
    signature = pow(
        int.from_bytes(encoded, "big"),
        int(_PRIVATE_EXPONENT_HEX, 16),
        modulus,
    ).to_bytes(width, "big")
    return base64.b64encode(signature).decode("ascii")


def signed_root_authorization(
    root: Path,
    plan_binding: dict[str, str],
    *,
    decided_at: str,
    evidence_id: str,
    skills_root: Path,
) -> dict[str, str]:
    unsigned = {
        "schema_version": 1,
        "artifact_kind": "authority_root_user_authorization_evidence",
        "audience": "manage-agent-authority/root-grant",
        "issuer": TEST_ISSUER,
        "authorization_id": f"authorization-{evidence_id}",
        "approval_plan": plan_binding,
        "approved": True,
        "decided_at": decided_at,
        "evidence_id": evidence_id,
    }
    evidence = {
        **unsigned,
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": TEST_KEY_ID,
            "value_base64": _signature(_canonical_json(unsigned)),
        },
    }
    return publish_root_authorization_evidence(
        root, evidence, skills_root=skills_root
    )["authorization_evidence"]


__all__ = (
    "install_test_trust_anchor",
    "signed_root_authorization",
)
