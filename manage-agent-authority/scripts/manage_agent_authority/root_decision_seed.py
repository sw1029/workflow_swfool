"""Compile and reopen compact plan-bound root approval decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import verify_binding
from .canonical import (
    normalized_time,
    object_sha256,
    parse_time,
    read_object,
    sha256_file,
    write_immutable_json,
)
from .root_grant_plan import (
    DECISION_SEED_KEYS,
    LEGACY_DECISION_SEED_KEYS,
    _identifier,
    load_root_approval_plan,
)
from .root_authorization_evidence import load_root_authorization_evidence


ROOT_DECISION_SEED_ROOT = Path(
    ".task/authorization/root_decision_seeds/sha256"
)


def normalize_root_decision_seed(
    value: Any,
    *,
    plan_binding: dict[str, str],
    plan: dict[str, Any],
    authorization_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(
            "Root approval decision seed must be a closed typed object."
        )
    schema_version = value.get("schema_version")
    expected_keys = (
        LEGACY_DECISION_SEED_KEYS
        if schema_version == 2
        else DECISION_SEED_KEYS
        if schema_version == 3
        else set()
    )
    if set(value) != expected_keys:
        raise SystemExit(
            "Root approval decision seed must be a closed typed object."
        )
    if (
        value.get("artifact_kind") != "authority_root_approval_decision_seed"
        or value.get("approved") is not True
        or value.get("approval_plan") != plan_binding
    ):
        raise SystemExit(
            "Root approval decision seed must explicitly approve the exact plan."
        )
    decided_at = normalized_time(value["decided_at"], "root approval decided_at")
    if parse_time(decided_at, "root approval decided_at") < parse_time(
        plan["prepared_at"], "root approval prepared_at"
    ):
        raise SystemExit("Root approval decision predates the prepared projection.")
    expiry = plan["approval_projection"]["validity"]["expires_at"]
    if parse_time(decided_at, "root approval decided_at") >= parse_time(
        expiry, "root approval expires_at"
    ):
        raise SystemExit("Root approval decision is outside the approval window.")
    normalized = {
        "schema_version": schema_version,
        "artifact_kind": "authority_root_approval_decision_seed",
        "approved": True,
        "approval_plan": plan_binding,
        "decided_at": decided_at,
        "evidence_id": _identifier(
            value["evidence_id"], "root approval evidence_id"
        ),
    }
    if schema_version == 2:
        if plan.get("schema_version") != 1:
            raise SystemExit(
                "Caller-asserted root decisions are historical-only and cannot "
                "approve a current root plan."
            )
        return normalized
    if (
        plan.get("schema_version") != 2
        or authorization_evidence is None
        or value.get("authorization_trust_class")
        != "host_user_signed_exact_plan"
        or value.get("authorization_evidence") is None
        or authorization_evidence.get("approval_plan") != plan_binding
        or authorization_evidence.get("approved") is not True
        or authorization_evidence.get("decided_at") != decided_at
        or authorization_evidence.get("evidence_id") != normalized["evidence_id"]
    ):
        raise SystemExit(
            "Current root decisions require non-self-asserted signed host/user "
            "authorization evidence for the exact plan."
        )
    return {
        **normalized,
        "authorization_evidence": value["authorization_evidence"],
        "authorization_trust_class": "host_user_signed_exact_plan",
    }


def compile_root_decision_seed(
    root: Path,
    plan_binding: dict[str, str],
    *,
    authorization_evidence: dict[str, str],
    skills_root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    normalized_plan_binding, plan = load_root_approval_plan(
        root, plan_binding, skills_root=skills_root
    )
    (
        normalized_evidence_binding,
        evidence,
        evidence_plan,
    ) = load_root_authorization_evidence(
        root, authorization_evidence, skills_root=skills_root
    )
    if evidence["approval_plan"] != normalized_plan_binding or evidence_plan != plan:
        raise SystemExit(
            "Root authorization evidence does not bind the selected root plan."
        )
    seed = normalize_root_decision_seed(
        {
            "schema_version": 3,
            "artifact_kind": "authority_root_approval_decision_seed",
            "approved": True,
            "approval_plan": normalized_plan_binding,
            "decided_at": evidence["decided_at"],
            "evidence_id": evidence["evidence_id"],
            "authorization_evidence": normalized_evidence_binding,
            "authorization_trust_class": "host_user_signed_exact_plan",
        },
        plan_binding=normalized_plan_binding,
        plan=plan,
        authorization_evidence=evidence,
    )
    fingerprint = object_sha256(seed)
    path = root / ROOT_DECISION_SEED_ROOT / f"{fingerprint}.json"
    digest = write_immutable_json(path, seed, "root approval decision seed")
    return {
        "status": "compiled",
        "decision_seed": {
            "ref": path.relative_to(root).as_posix(),
            "sha256": digest,
        },
        "approved": True,
        "authorization_trust_class": "host_user_signed_exact_plan",
        "authority_effects_applied": False,
        "model_authored_mechanical_bytes": 0,
    }


def load_root_decision_seed(
    root: Path,
    binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    path = verify_binding(root, binding, "root approval decision seed")
    try:
        path.relative_to(root / ROOT_DECISION_SEED_ROOT)
    except ValueError as exc:
        raise SystemExit(
            "Root approval decision seed is outside its producer CAS."
        ) from exc
    normalized_binding = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    if normalized_binding != binding:
        raise SystemExit("Root approval decision seed binding is not canonical.")
    value = read_object(path, "root approval decision seed")
    if not isinstance(value.get("approval_plan"), dict):
        raise SystemExit("Root approval decision seed lacks its plan binding.")
    normalized_plan_binding, plan = load_root_approval_plan(
        root, value["approval_plan"], skills_root=skills_root
    )
    evidence: dict[str, Any] | None = None
    if value.get("schema_version") == 3:
        binding = value.get("authorization_evidence")
        if not isinstance(binding, dict):
            raise SystemExit(
                "Root approval decision seed lacks authorization evidence."
            )
        (
            normalized_evidence_binding,
            evidence,
            evidence_plan,
        ) = load_root_authorization_evidence(
            root, binding, skills_root=skills_root
        )
        if (
            normalized_evidence_binding != binding
            or evidence_plan != plan
        ):
            raise SystemExit(
                "Root approval decision seed authorization evidence drifted."
            )
    expected = normalize_root_decision_seed(
        value,
        plan_binding=normalized_plan_binding,
        plan=plan,
        authorization_evidence=evidence,
    )
    if value != expected or path.name != f"{object_sha256(expected)}.json":
        raise SystemExit(
            "Root approval decision seed differs from compiler rendering."
        )
    return normalized_binding, expected, plan


__all__ = (
    "ROOT_DECISION_SEED_ROOT",
    "compile_root_decision_seed",
    "load_root_decision_seed",
    "normalize_root_decision_seed",
)
