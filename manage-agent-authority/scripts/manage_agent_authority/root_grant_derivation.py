"""Reopen signed root-grant inputs and derive all authority bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .canonical import resolve_workspace_path
from .contracts import validate_grant
from .root_authorization_evidence import (
    ROOT_AUTHORIZATION_EVIDENCE_ROOT,
    load_root_authorization_evidence,
)
from .root_decision_seed import (
    ROOT_DECISION_SEED_ROOT,
    load_root_decision_seed,
)
from .root_grant_plan import ROOT_PLAN_ROOT, load_root_approval_plan
from .source_approval import validate_for_grant, validate_source_approval
from .stable_store import read_regular


AUTHORIZATION_ROOT = Path(".task/authorization")
MAX_ROOT_TRANSACTION_BYTES = 2 * 1024 * 1024
MAX_ROOT_STATE_BYTES = 64 * 1024


def json_bytes(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def closed_binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise SystemExit(f"{label} must contain exact ref and sha256.")
    ref = str(value["ref"] or "").strip()
    digest = str(value["sha256"] or "")
    if (
        not ref
        or Path(ref).is_absolute()
        or "*" in ref
        or ".." in Path(ref).parts
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SystemExit(f"{label} must be a canonical workspace binding.")
    return {"ref": ref, "sha256": digest}


def read_exact(
    path: Path,
    *,
    label: str,
    required: bool = True,
    max_bytes: int = MAX_ROOT_TRANSACTION_BYTES,
) -> bytes | None:
    return read_regular(
        path,
        required=required,
        label=label,
        max_bytes=max_bytes,
    )


def source_snapshot_binding(
    root: Path, source: dict[str, Any]
) -> dict[str, str]:
    digest = hashlib.sha256(json_bytes(source)).hexdigest()
    path = (
        root.resolve()
        / AUTHORIZATION_ROOT
        / "source_snapshots"
        / f"source_approval-{digest}.json"
    )
    return {
        "ref": path.relative_to(root.resolve()).as_posix(),
        "sha256": digest,
    }


def _acquire_binding_payload(
    root: Path,
    binding: dict[str, str],
    *,
    label: str,
) -> tuple[Path, bytes]:
    normalized = closed_binding(binding, label)
    path = resolve_workspace_path(root, normalized["ref"], f"{label}.ref")
    payload = read_exact(path, label=label)
    assert payload is not None
    if hashlib.sha256(payload).hexdigest() != normalized["sha256"]:
        raise SystemExit(f"{label} digest changed during bounded acquisition.")
    return path, payload


def _reopen_exact_binding(
    root: Path,
    binding: dict[str, str],
    value: dict[str, Any],
    *,
    label: str,
) -> None:
    _path, payload = _acquire_binding_payload(
        root,
        binding,
        label=label,
    )
    if payload != json_bytes(value):
        raise SystemExit(f"{label} bytes differ from compiler rendering.")


def _bounded_signed_bindings(
    root: Path,
    plan_binding: dict[str, str],
    decision_binding: dict[str, str],
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    requested_plan = closed_binding(
        plan_binding, "root approval plan binding"
    )
    requested_decision = closed_binding(
        decision_binding, "root approval decision seed binding"
    )
    plan_path, _plan_payload = _acquire_binding_payload(
        root,
        requested_plan,
        label="root approval plan",
    )
    decision_path, decision_payload = _acquire_binding_payload(
        root,
        requested_decision,
        label="root approval decision seed",
    )
    try:
        plan_path.relative_to(root / ROOT_PLAN_ROOT)
    except ValueError as exc:
        raise SystemExit(
            "Root approval plan is outside its producer CAS."
        ) from exc
    try:
        decision_path.relative_to(root / ROOT_DECISION_SEED_ROOT)
    except ValueError as exc:
        raise SystemExit(
            "Root approval decision seed is outside its producer CAS."
        ) from exc
    try:
        decision_seed = json.loads(decision_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "Root approval decision seed is not readable JSON."
        ) from exc
    if not isinstance(decision_seed, dict):
        raise SystemExit(
            "Root approval decision seed must be a JSON object."
        )
    evidence_binding = closed_binding(
        decision_seed.get("authorization_evidence"),
        "root authorization evidence binding",
    )
    evidence_path, _evidence_payload = _acquire_binding_payload(
        root,
        evidence_binding,
        label="root authorization evidence",
    )
    try:
        evidence_path.relative_to(root / ROOT_AUTHORIZATION_EVIDENCE_ROOT)
    except ValueError as exc:
        raise SystemExit(
            "Root authorization evidence is outside its verified producer CAS."
        ) from exc
    return requested_plan, requested_decision, evidence_binding


def _load_signed_chain(
    root: Path,
    plan_binding: dict[str, str],
    decision_binding: dict[str, str],
    evidence_binding: dict[str, str],
    *,
    skills_root: Path | None,
) -> tuple[dict[str, str], dict[str, str], dict[str, Any], dict[str, Any]]:
    normalized_plan, plan = load_root_approval_plan(
        root, plan_binding, skills_root=skills_root
    )
    normalized_decision, decision, decision_plan = load_root_decision_seed(
        root, decision_binding, skills_root=skills_root
    )
    if (
        normalized_plan != plan_binding
        or normalized_decision != decision_binding
        or decision["approval_plan"] != normalized_plan
        or decision_plan != plan
        or decision.get("authorization_evidence") != evidence_binding
    ):
        raise SystemExit(
            "Root approval decision seed does not bind the selected exact plan."
        )
    normalized_evidence, evidence, evidence_plan = (
        load_root_authorization_evidence(
            root, evidence_binding, skills_root=skills_root
        )
    )
    if (
        normalized_evidence != evidence_binding
        or evidence_plan != plan
        or evidence["approval_plan"] != normalized_plan
        or evidence["decided_at"] != decision["decided_at"]
        or evidence["evidence_id"] != decision["evidence_id"]
    ):
        raise SystemExit(
            "Root approval decision seed diverges from its signed evidence."
        )
    if (
        plan.get("schema_version") != 2
        or decision.get("schema_version") != 3
        or decision.get("authorization_trust_class")
        != "host_user_signed_exact_plan"
    ):
        raise SystemExit(
            "Prospective root authority requires a signed exact-plan decision."
        )
    for binding, value, label in (
        (normalized_plan, plan, "root approval plan"),
        (normalized_decision, decision, "root approval decision seed"),
        (normalized_evidence, evidence, "root authorization evidence"),
    ):
        _reopen_exact_binding(root, binding, value, label=label)
    return normalized_plan, normalized_decision, plan, decision


def _source_approval(
    projection: dict[str, Any],
    decision: dict[str, Any],
    decision_binding: dict[str, str],
) -> dict[str, Any]:
    coverage = projection["source_coverage"]
    return {
        "schema_version": 5,
        "artifact_kind": "authority_source_approval",
        "approval_id": projection["approval_id"],
        "source_kind": projection["source_kind"],
        "source_rank": projection["source_rank"],
        "decision_type": "grant_authority",
        "capabilities": coverage["capabilities"],
        "subjects": coverage["subjects"],
        "operations": coverage["operations"],
        "risk_ceiling": coverage["risk_ceiling"],
        "decision_classes": coverage["decision_classes"],
        "cardinalities": coverage["cardinalities"],
        "max_uses": coverage["max_uses"],
        "grant_ids": coverage["grant_ids"],
        "request_digests": coverage["request_digests"],
        "lineage_ids": coverage["lineage_ids"],
        "delegation_binding": None,
        "not_before": decision["decided_at"],
        "expires_at": projection["validity"]["expires_at"],
        "evidence_id": decision["evidence_id"],
        "decision_binding": decision_binding,
        "decision_trust_class": "host_user_signed_exact_plan",
        "grant_projections": projection["grants"],
    }


def _grant(
    projection: dict[str, Any],
    grant_projection: dict[str, Any],
    decision: dict[str, Any],
    source_binding: dict[str, str],
    policy_snapshot: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "artifact_kind": "authority_grant",
        "grant_id": grant_projection["grant_id"],
        "lineage_id": grant_projection["lineage_id"],
        "parent_grant_id": None,
        "issuer_rank": projection["source_rank"],
        "holder_rank": grant_projection["holder_rank"],
        "capabilities": grant_projection["capabilities"],
        "subjects": grant_projection["subjects"],
        "operations": grant_projection["operations"],
        "risk_ceiling": grant_projection["risk_ceiling"],
        "decision_classes": grant_projection["decision_classes"],
        "cardinality": grant_projection["cardinality"],
        "max_uses": grant_projection["max_uses"],
        "not_before": decision["decided_at"],
        "expires_at": projection["validity"]["expires_at"],
        "session_id": grant_projection["session_id"],
        "task_id": grant_projection["task_id"],
        "improvement_id": grant_projection["improvement_id"],
        "source_approval": source_binding,
        "policy_snapshot": policy_snapshot,
        "created_at": decision["decided_at"],
        "idempotency_key": grant_projection["grant_idempotency_key"],
        "request_sha256": grant_projection["request_sha256"],
        "root_materialization_ref": grant_projection[
            "root_materialization_ref"
        ],
    }


def _projection_identity(
    root: Path, projection: dict[str, Any]
) -> tuple[Path, str, list[dict[str, Any]]]:
    projection_id = str(projection["projection_id"])
    receipt_ref = (
        ".task/authorization/root_grant_materializations/"
        f"{projection_id}/receipt.json"
    )
    grant_projections = projection["grants"]
    if (
        not isinstance(grant_projections, list)
        or not grant_projections
        or any(
            item.get("root_materialization_ref") != receipt_ref
            for item in grant_projections
        )
    ):
        raise SystemExit(
            "Root approval plan has an invalid materialization identity."
        )
    materialization_root = (
        root
        / AUTHORIZATION_ROOT
        / "root_grant_materializations"
        / projection_id
    )
    return materialization_root, receipt_ref, grant_projections


def _derive_grants(
    root: Path,
    projection: dict[str, Any],
    grant_projections: list[dict[str, Any]],
    decision: dict[str, Any],
    source: dict[str, Any],
    source_binding: dict[str, str],
    policy_snapshot: dict[str, str],
    receipt_ref: str,
) -> list[dict[str, Any]]:
    grants: list[dict[str, Any]] = []
    for grant_projection in grant_projections:
        grant = validate_grant(
            _grant(
                projection,
                grant_projection,
                decision,
                source_binding,
                policy_snapshot,
            )
        )
        if (
            grant["source_approval"] != source_binding
            or grant["root_materialization_ref"] != receipt_ref
        ):
            raise SystemExit(
                "Derived root grant binding or materialization identity drifted."
            )
        validate_for_grant(root, source, grant)
        grants.append(grant)
    return grants


def derive_root_grant_materialization(
    root: Path,
    plan_binding: dict[str, str],
    decision_binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Return only mechanical effects reproduced from the signed exact plan."""

    root = root.resolve()
    requested_plan, requested_decision, evidence_binding = (
        _bounded_signed_bindings(root, plan_binding, decision_binding)
    )
    normalized_plan, normalized_decision, plan, decision = (
        _load_signed_chain(
            root,
            requested_plan,
            requested_decision,
            evidence_binding,
            skills_root=skills_root,
        )
    )
    projection = plan["approval_projection"]
    materialization_root, receipt_ref, grant_projections = (
        _projection_identity(root, projection)
    )
    source = validate_source_approval(
        _source_approval(projection, decision, normalized_decision)
    )
    if (
        source["capabilities"]
        != projection["source_coverage"]["capabilities"]
        or "authority.grant.issue" not in source["capabilities"]
    ):
        raise SystemExit(
            "Derived root source approval capabilities are invalid."
        )
    source_binding = source_snapshot_binding(root, source)
    grants = _derive_grants(
        root,
        projection,
        grant_projections,
        decision,
        source,
        source_binding,
        plan["policy_snapshot"],
        receipt_ref,
    )
    return {
        "materialization_root": materialization_root,
        "plan_binding": normalized_plan,
        "decision_binding": normalized_decision,
        "decided_at": decision["decided_at"],
        "source": source,
        "source_binding": source_binding,
        "grants": grants,
        "receipt_ref": receipt_ref,
    }


__all__ = (
    "MAX_ROOT_STATE_BYTES",
    "MAX_ROOT_TRANSACTION_BYTES",
    "closed_binding",
    "derive_root_grant_materialization",
    "json_bytes",
    "read_exact",
    "source_snapshot_binding",
)
