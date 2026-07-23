"""Test-only authority fixtures for the selected-successor executor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manage_agent_authority import artifact_store as artifact_store_module
from manage_agent_authority.artifact_store import (
    _register_compiled_grant as _production_register_grant,
    snapshot_file,
)
from manage_agent_authority.canonical import (
    object_sha256,
    parse_time,
    sha256_file,
    write_immutable_json,
)
from manage_agent_authority.evaluator import evaluate
from manage_agent_authority.lifecycle import reserve, verify_reservation_with_recovery
from manage_agent_authority.operations import load_operation
from manage_agent_authority.producer_capability import (
    _AUTHORITY_PRODUCER_CAPABILITY,
)
from manage_agent_authority.source_approval import validate_for_grant
from orchestrate_task_cycle.selected_successor_authority_context_compiler import (
    prepare_selected_successor_authority_contexts,
)


SKILLS_ROOT = Path(__file__).resolve().parents[1]
AT = "2026-07-17T10:00:00+09:00"
LATER = "2026-07-17T10:05:00+09:00"
EXPIRY = "2026-07-17T11:00:00+09:00"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _snapshot_historical_source(root: Path, source: Path) -> dict[str, str]:
    payload = source.read_bytes()
    digest = sha256_file(source)
    snapshot = (
        root
        / ".task/authorization/source_snapshots"
        / f"source_approval-{digest}.json"
    )
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.exists() and snapshot.read_bytes() != payload:
        raise AssertionError("historical source fixture conflicts")
    snapshot.write_bytes(payload)
    return {"ref": snapshot.relative_to(root).as_posix(), "sha256": digest}


def register_grant(
    root: Path, raw: dict[str, Any], *, parent_id: str | None = None
) -> dict[str, Any]:
    """Test-only registration for pre-upgrade schema-v2 fixtures."""

    original = artifact_store_module.validate_for_grant

    def validate_historical(
        fixture_root: Path,
        approval: dict[str, Any],
        grant: dict[str, Any],
    ) -> None:
        validate_for_grant(
            fixture_root,
            approval,
            grant,
            prospective=approval["schema_version"] != 2,
        )

    artifact_store_module.validate_for_grant = validate_historical
    try:
        return _production_register_grant(
            root,
            raw,
            parent_id=parent_id,
            producer_capability=_AUTHORITY_PRODUCER_CAPABILITY,
        )
    finally:
        artifact_store_module.validate_for_grant = original


def _context(goal: Path, request: dict[str, Any]) -> dict[str, Any]:
    operation = ":".join(
        request[key]
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    )
    return {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {
            "capabilities": list(request["required_capabilities"]),
            "risk_ceiling": "R3",
            "mutation_classes": ["observe", "local_mutation"],
            "evidence_id": "selected-successor-session",
        },
        "goal_autonomy_envelope": {
            "envelope_id": "selected-successor-envelope",
            "capabilities": list(request["required_capabilities"]),
            "risk_ceiling": "R3",
            "decision_classes": [request["decision_class"]],
            "subjects": [request["subject"]["digest"]],
            "operations": [operation],
            "source_binding": {
                "ref": goal.relative_to(goal.parents[1]).as_posix(),
                "sha256": sha256_file(goal),
            },
        },
    }


def _request(row: dict[str, Any], manifest: dict[str, Any], index: int) -> dict[str, Any]:
    operation = row["operation"]
    return {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": f"selected-successor-request-{index}",
        **operation,
        "cycle_id": "cycle-selected-successor",
        "task_id": None,
        "pack_id": None,
        "attempt_id": f"selected-successor-attempt-{index}",
        "actor_rank": "S0",
        "subject": row["subject"],
        "required_capabilities": manifest["required_capabilities"],
        "effect_class": manifest["effect_classes"][0],
        "data_class": manifest["data_classes"][0],
        "mutation_class": manifest["mutation_class"],
        "reversibility": manifest["reversibility"],
        "risk_tier": manifest["risk_floor"],
        "decision_class": manifest["decision_class"],
        "intent_type": "grant_authority",
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "idempotency_key": row["idempotency_key"],
        "context": {
            "external_input_status": "not_required",
            "goal_truth_status": "aligned",
            "risk_acceptance_status": "not_required",
            "design_selection_status": "not_required",
            "external_input_evidence": None,
            "risk_acceptance_evidence": None,
            "design_selection_evidence": None,
        },
        "composition_receipt": None,
    }


def _precommit(
    root: Path, reserved: dict[str, Any], *, at: str = LATER
) -> dict[str, str]:
    reservation, state, verified, state_sha256 = verify_reservation_with_recovery(
        root,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        verified_at=at,
        expected_version=0,
        skills_root=SKILLS_ROOT,
    )
    state_path = (
        root
        / ".task/authorization/state/reservations"
        / f"{reservation['reservation_id']}.json"
    )
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_verification",
        "stage": "pre_commit",
        "reservation": {
            "ref": reserved["reservation_ref"],
            "sha256": reserved["reservation_sha256"],
        },
        "reservation_state": {
            "ref": state_path.relative_to(root).as_posix(),
            "sha256": state_sha256,
            "version": state["version"],
            "status": state["status"],
        },
        "grant_states": verified["grant_states"],
        "request_id": verified["decision"]["request"]["request_id"],
        "effective_authority_fingerprint": reservation[
            "effective_authority_fingerprint"
        ],
        "verified_at": parse_time(at, "at").isoformat(),
    }
    value = {"verification_id": f"authv-{object_sha256(core)[:24]}", **core}
    path = root / ".task/authorization/verifications" / f"{value['verification_id']}.json"
    digest = write_immutable_json(path, value, "selected-successor test precommit")
    return {"ref": path.relative_to(root).as_posix(), "sha256": digest}


def prepare_authority_proofs(
    root: Path, bundle: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Create exact grants, decisions, reservations, and precommits for a bundle."""

    policy = _write(
        root / ".agent_goal/agent_authority.md", "# Authority\n\nBounded local changes.\n"
    )
    goal = _write(
        root / ".agent_goal/goal_architecture.md", "# Goal Architecture\n"
    )
    policy_binding = snapshot_file(
        root, policy.relative_to(root).as_posix(), "policy"
    )
    manifests: list[dict[str, Any]] = []
    for row in bundle["execution_order"]:
        manifest, _binding = load_operation(
            row["operation"]["skill_id"],
            row["operation"]["skill_version"],
            row["operation"]["operation_id"],
            row["operation"]["operation_version"],
            skills_root=SKILLS_ROOT,
        )
        manifests.append(manifest)
    capabilities = sorted(
        {
            "authority.grant.issue",
            *(capability for manifest in manifests for capability in manifest["required_capabilities"]),
        }
    )
    source = {
        "schema_version": 2,
        "artifact_kind": "authority_source_approval",
        "approval_id": "selected-successor-approval",
        "source_kind": "explicit_user_instruction",
        "source_rank": "S3",
        "decision_type": "grant_authority",
        "capabilities": capabilities,
        "subjects": [row["subject"] for row in bundle["execution_order"]],
        "operations": [row["operation"] for row in bundle["execution_order"]],
        "risk_ceiling": "R3",
        "decision_classes": ["D2"],
        "cardinalities": ["single_use"],
        "max_uses": 3,
        "grant_ids": [f"selected-successor-grant-{index}" for index in range(1, 4)],
        "request_digests": [],
        "lineage_ids": [
            f"selected-successor-lineage-{index}" for index in range(1, 4)
        ],
        "delegation_binding": None,
        "not_before": AT,
        "expires_at": EXPIRY,
        "evidence_id": "selected-successor-user-message",
        "integrity_status": "verified",
    }
    source_path = _write(
        root / ".task/authorization/selected-successor-approval.json",
        json.dumps(source, indent=2, sort_keys=True) + "\n",
    )
    source_binding = _snapshot_historical_source(root, source_path)
    proofs: dict[str, dict[str, Any]] = {}
    for index, (row, manifest) in enumerate(
        zip(bundle["execution_order"], manifests), start=1
    ):
        request = _request(row, manifest, index)
        grant_id = f"selected-successor-grant-{index}"
        grant = {
            "schema_version": 2,
            "artifact_kind": "authority_grant",
            "grant_id": grant_id,
            "lineage_id": f"selected-successor-lineage-{index}",
            "parent_grant_id": None,
            "issuer_rank": "S3",
            "holder_rank": "S0",
            "capabilities": request["required_capabilities"],
            "subjects": [request["subject"]],
            "operations": [row["operation"]],
            "risk_ceiling": "R3",
            "decision_classes": ["D2"],
            "cardinality": "single_use",
            "max_uses": 1,
            "not_before": AT,
            "expires_at": EXPIRY,
            "session_id": None,
            "task_id": None,
            "improvement_id": None,
            "source_approval": source_binding,
            "policy_snapshot": policy_binding,
            "created_at": AT,
            "idempotency_key": f"selected-successor-grant-key-{index}",
        }
        register_grant(root, grant)
        decision = evaluate(
            root,
            request,
            _context(goal, request),
            evaluated_at=AT,
            skills_root=SKILLS_ROOT,
        )
        if decision.get("decision") != "allowed":
            raise AssertionError(f"authority fixture denied: {decision}")
        decision_path = (
            root
            / ".task/authorization/decisions"
            / f"{decision['decision_id']}.json"
        )
        decision_sha256 = write_immutable_json(
            decision_path, decision, "selected-successor test decision"
        )
        reserved = reserve(
            root,
            decision_path.relative_to(root).as_posix(),
            decision_sha256,
            reserved_at=LATER,
            idempotency_key=row["idempotency_key"],
            skills_root=SKILLS_ROOT,
        )
        proofs[row["action"]] = {
            "reservation": {
                "ref": reserved["reservation_ref"],
                "sha256": reserved["reservation_sha256"],
            },
            "pre_commit_verification": _precommit(root, reserved),
            "expected_version": 0,
        }
    return proofs


def prepare_authority_inputs(
    root: Path,
    bundle: dict[str, Any],
    bundle_binding: dict[str, str],
    *,
    register_existing_grants: bool = True,
    shared_grant_max_uses: int | None = None,
) -> dict[str, Any]:
    """Create external policy/grant/context inputs, but no lifecycle proofs."""

    policy = _write(
        root / ".agent_goal/agent_authority.md", "# Authority\n\nBounded local changes.\n"
    )
    goal = _write(root / ".agent_goal/goal_architecture.md", "# Goal Architecture\n")
    policy_binding = snapshot_file(
        root, policy.relative_to(root).as_posix(), "policy"
    )
    manifests = [
        load_operation(
            row["operation"]["skill_id"],
            row["operation"]["skill_version"],
            row["operation"]["operation_id"],
            row["operation"]["operation_version"],
            skills_root=SKILLS_ROOT,
        )[0]
        for row in bundle["execution_order"]
    ]
    capabilities = sorted(
        {
            "authority.grant.issue",
            *(item for manifest in manifests for item in manifest["required_capabilities"]),
        }
    )
    source = {
        "schema_version": 2,
        "artifact_kind": "authority_source_approval",
        "approval_id": "selected-successor-compiler-approval",
        "source_kind": "explicit_user_instruction",
        "source_rank": "S3",
        "decision_type": "grant_authority",
        "capabilities": capabilities,
        "subjects": [row["subject"] for row in bundle["execution_order"]],
        "operations": [row["operation"] for row in bundle["execution_order"]],
        "risk_ceiling": "R3",
        "decision_classes": ["D2"],
        "cardinalities": [
            "bounded_reusable"
            if shared_grant_max_uses is not None
            else "single_use"
        ],
        "max_uses": shared_grant_max_uses or 3,
        "grant_ids": (
            ["selected-compiler-shared-grant"]
            if shared_grant_max_uses is not None
            else [f"selected-compiler-grant-{index}" for index in range(1, 4)]
        ),
        "request_digests": [],
        "lineage_ids": (
            ["selected-compiler-shared-lineage"]
            if shared_grant_max_uses is not None
            else [f"selected-compiler-lineage-{index}" for index in range(1, 4)]
        ),
        "delegation_binding": None,
        "not_before": AT,
        "expires_at": EXPIRY,
        "evidence_id": "selected-successor-compiler-user-message",
        "integrity_status": "verified",
    }
    source_path = _write(
        root / ".task/authorization/selected-successor-compiler-approval.json",
        json.dumps(source, indent=2, sort_keys=True) + "\n",
    )
    source_binding = _snapshot_historical_source(root, source_path)
    grants: dict[str, dict[str, str]] = {}
    if register_existing_grants and shared_grant_max_uses is not None:
        shared = {
            "schema_version": 2,
            "artifact_kind": "authority_grant",
            "grant_id": "selected-compiler-shared-grant",
            "lineage_id": "selected-compiler-shared-lineage",
            "parent_grant_id": None,
            "issuer_rank": "S3",
            "holder_rank": "S0",
            "capabilities": sorted(
                {item for manifest in manifests for item in manifest["required_capabilities"]}
            ),
            "subjects": [row["subject"] for row in bundle["execution_order"]],
            "operations": [row["operation"] for row in bundle["execution_order"]],
            "risk_ceiling": "R3",
            "decision_classes": ["D2"],
            "cardinality": "bounded_reusable",
            "max_uses": shared_grant_max_uses,
            "not_before": AT,
            "expires_at": EXPIRY,
            "session_id": None,
            "task_id": None,
            "improvement_id": None,
            "source_approval": source_binding,
            "policy_snapshot": policy_binding,
            "created_at": AT,
            "idempotency_key": "selected-compiler-shared-grant-key",
        }
        registered = register_grant(root, shared)
        shared_binding = {
            "ref": ".task/authorization/grants/selected-compiler-shared-grant.json",
            "sha256": registered["grant_sha256"],
        }
        grants = {
            row["action"]: shared_binding for row in bundle["execution_order"]
        }
    for index, (row, manifest) in enumerate(
        zip(bundle["execution_order"], manifests), start=1
    ):
        grant_id = f"selected-compiler-grant-{index}"
        grant = {
            "schema_version": 2,
            "artifact_kind": "authority_grant",
            "grant_id": grant_id,
            "lineage_id": f"selected-compiler-lineage-{index}",
            "parent_grant_id": None,
            "issuer_rank": "S3",
            "holder_rank": "S0",
            "capabilities": manifest["required_capabilities"],
            "subjects": [row["subject"]],
            "operations": [row["operation"]],
            "risk_ceiling": "R3",
            "decision_classes": ["D2"],
            "cardinality": "single_use",
            "max_uses": 1,
            "not_before": AT,
            "expires_at": EXPIRY,
            "session_id": None,
            "task_id": None,
            "improvement_id": None,
            "source_approval": source_binding,
            "policy_snapshot": policy_binding,
            "created_at": AT,
            "idempotency_key": f"selected-compiler-grant-key-{index}",
        }
        if register_existing_grants and shared_grant_max_uses is None:
            registered = register_grant(root, grant)
            grants[row["action"]] = {
                "ref": f".task/authorization/grants/{grant_id}.json",
                "sha256": registered["grant_sha256"],
            }
        elif not register_existing_grants:
            grants[row["action"]] = {"status": "absent"}
    operations = [
        ":".join(
            row["operation"][key]
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        )
        for row in bundle["execution_order"]
    ]
    session_ceiling = {
        "capabilities": sorted(
            {
                item
                for manifest in manifests
                for item in manifest["required_capabilities"]
            }
        ),
        "risk_ceiling": "R3",
        "mutation_classes": ["local_mutation"],
        "evidence_id": "selected-successor-compiler-session",
    }
    goal_autonomy_envelope = {
        "envelope_id": "selected-successor-compiler-envelope",
        "capabilities": sorted(
            {
                item
                for manifest in manifests
                for item in manifest["required_capabilities"]
            }
        ),
        "risk_ceiling": "R3",
        "decision_classes": ["D2"],
        "subjects": sorted(
            {row["subject"]["digest"] for row in bundle["execution_order"]}
        ),
        "operations": sorted(operations),
        "source_binding": {
            "ref": goal.relative_to(root).as_posix(),
            "sha256": sha256_file(goal),
        },
    }
    contexts = prepare_selected_successor_authority_contexts(
        root,
        bundle_binding=bundle_binding,
        actor_rank="S0",
        request_context={
            "external_input_status": "not_required",
            "goal_truth_status": "aligned",
            "risk_acceptance_status": "not_required",
            "design_selection_status": "not_required",
            "external_input_evidence": None,
            "risk_acceptance_evidence": None,
            "design_selection_evidence": None,
        },
        session_ceiling=session_ceiling,
        goal_autonomy_envelope=goal_autonomy_envelope,
        skills_root=SKILLS_ROOT,
    )
    return {
        "request_context": contexts["request_context"],
        "evaluation_context": contexts["evaluation_context"],
        "grants": grants,
    }


__all__ = (
    "AT",
    "LATER",
    "SKILLS_ROOT",
    "prepare_authority_inputs",
    "prepare_authority_proofs",
)
