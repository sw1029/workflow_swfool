from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from manage_agent_authority.evaluator import evaluate as evaluate_owner_decision
from orchestrate_task_cycle.authority_artifacts import (
    validate_authority_use_receipt_settlement,
    validate_authority_verification_binding,
)
from orchestrate_task_cycle.authority_boundary import (
    authority_watch_row,
    canonical_sha256,
    effective_authority_fingerprint,
    project_authority_packet,
)
from orchestrate_task_cycle.authority_packet import build_authority_packet
from orchestrate_task_cycle.result_contract.base import RuleContext
from orchestrate_task_cycle.result_contract.api import validate
from orchestrate_task_cycle.result_contract.rules.derive_checks.authority_terminal import (
    check_authority_terminal,
)
from orchestrate_task_cycle.result_contract.rules.derive_checks.state import DeriveFacts
from orchestrate_task_cycle.selection_tick import build_selection_tick


def authority_packet(
    *,
    decision: str = "allowed",
    mutation_class: str = "observe",
    authority_status: str = "granted",
    local_status: str = "available",
    external_status: str = "not_required",
    risk_status: str = "not_required",
    goal_status: str = "aligned",
) -> dict[str, object]:
    granted = authority_status == "granted"
    packet: dict[str, object] = {
        "step": "authority",
        "schema_version": 2,
        "artifact_kind": "orchestrator_authority_packet",
        "packet_id": "authority-packet-A",
        "decision_binding": {
            "decision_id": "authority-decision-A",
            "artifact_ref": ".task/authorization/decisions/authority-decision-A.json",
            "artifact_sha256": "2" * 64,
            "request_id": "authority-request-A",
            "request_sha256": "1" * 64,
            "decision": decision,
            "effective_authority_fingerprint": "c" * 64,
        },
        "operation_binding": {
            "skill_id": "task-md-agent-governance",
            "skill_version": "2",
            "operation_id": "implementation.apply",
            "operation_version": "2",
            "manifest_ref": "task-md-agent-governance/authority.operations.json",
            "manifest_sha256": "3" * 64,
            "manifest_status": "verified",
            "mutation_class": mutation_class,
        },
        "subject": {
            "kind": "task",
            "ref": "task.md",
            "digest": "4" * 64,
            "revision": "task-revision-A",
        },
        "scope": {
            "cycle_id": "cycle-A",
            "task_id": "task-A",
            "pack_id": None,
            "attempt_id": "attempt-A",
            "scope_kind": "action",
            "decision_class": "D3",
            "intent_type": "grant_authority",
            "required_source_rank": "S1",
            "risk_tier": "R1",
        },
        "axes": {
            "authority": {
                "status": authority_status,
                "evidence_ids": ["authority-evidence-A"]
                if authority_status not in {"unverified", "not_applicable"}
                else [],
            },
            "local_resolution": {
                "status": local_status,
                "evidence_ids": ["local-evidence-A"]
                if local_status not in {"unverified", "not_applicable"}
                else [],
            },
            "external_input": {
                "status": external_status,
                "evidence_ids": ["external-evidence-A"]
                if external_status
                not in {"not_required", "unverified", "not_applicable"}
                else [],
            },
            "risk_cost": {
                "status": risk_status,
                "evidence_ids": ["risk-evidence-A"]
                if risk_status not in {"not_required", "unverified", "not_applicable"}
                else [],
            },
            "goal_truth": {
                "status": goal_status,
                "evidence_ids": ["goal-evidence-A"]
                if goal_status not in {"unverified", "not_applicable"}
                else [],
            },
        },
        "selected_grants": [
            {
                "grant_id": "grant-A",
                "grant_sha256": "6" * 64,
                "state_version": 3,
                "policy_snapshot": {
                    "ref": ".task/authorization/policy_snapshots/policy-A.md",
                    "sha256": "5" * 64,
                },
            }
        ]
        if granted
        else [],
        "lineage_grants": [],
        "approval_projection": None,
        "reservation_binding": {
            "applicability": "not_applicable",
            "reservation_id": None,
            "artifact_ref": None,
            "artifact_sha256": None,
            "state_ref": None,
            "state_sha256": None,
            "state_version": None,
            "status": None,
            "effective_authority_fingerprint": None,
            "grant_uses": [],
        },
        "composition_receipt": None,
        "dispatch_preflight": {
            "status": "not_applicable",
            "artifact_ref": None,
            "artifact_sha256": None,
            "verification_id": None,
            "stage": None,
            "reservation": None,
            "reservation_state": None,
            "grant_states": [],
            "request_id": None,
            "effective_authority_fingerprint": None,
            "verified_at": None,
        },
        "effective_authority_fingerprint": "",
        "evidence_ids": ["authority-decision-evidence-A"],
        "packet_sha256": "",
    }
    if decision == "approval_required":
        packet["approval_projection"] = packet_approval_projection(packet)
    fingerprint = effective_authority_fingerprint(packet)
    packet["effective_authority_fingerprint"] = fingerprint
    packet["packet_sha256"] = canonical_sha256(
        {key: value for key, value in packet.items() if key != "packet_sha256"}
    )
    return packet


def reseal(packet: dict[str, object]) -> None:
    fingerprint = effective_authority_fingerprint(packet)
    packet["effective_authority_fingerprint"] = fingerprint
    packet["packet_sha256"] = canonical_sha256(
        {key: value for key, value in packet.items() if key != "packet_sha256"}
    )


def mutating_packet() -> dict[str, object]:
    packet = authority_packet(mutation_class="local_mutation", local_status="available")
    packet["reservation_binding"] = {
        "applicability": "required",
        "reservation_id": "reservation-A",
        "artifact_ref": ".task/authorization/reservations/reservation-A.json",
        "artifact_sha256": "8" * 64,
        "state_ref": ".task/authorization/state/reservations/reservation-A.json",
        "state_sha256": "9" * 64,
        "state_version": 0,
        "status": "reserved",
        "effective_authority_fingerprint": "c" * 64,
        "grant_uses": [
            {
                "grant_id": "grant-A",
                "grant_sha256": "6" * 64,
                "units": 1,
                "state_version_before": 3,
                "state_version_after": 4,
            }
        ],
    }
    packet["dispatch_preflight"] = {
        "status": "verified",
        "artifact_ref": ".task/authorization/verifications/verification-A.json",
        "artifact_sha256": "d" * 64,
        "verification_id": "verification-A",
        "stage": "pre_dispatch",
        "reservation": {
            "ref": ".task/authorization/reservations/reservation-A.json",
            "sha256": "8" * 64,
        },
        "reservation_state": {
            "ref": ".task/authorization/state/reservations/reservation-A.json",
            "sha256": "9" * 64,
            "version": 0,
            "status": "reserved",
        },
        "grant_states": [
            {
                "grant_id": "grant-A",
                "grant_sha256": "6" * 64,
                "state_version": 4,
                "status": "active",
                "remaining_uses": 1,
                "reserved_uses": 1,
            }
        ],
        "request_id": "authority-request-A",
        "effective_authority_fingerprint": "c" * 64,
        "verified_at": "2026-07-17T00:00:00+00:00",
    }
    reseal(packet)
    return packet


def add_lineage_grant(packet: dict[str, object]) -> None:
    packet["lineage_grants"] = [
        {
            "grant_id": "grant-parent-A",
            "grant_sha256": "a" * 64,
            "state_version": 7,
            "policy_snapshot": {
                "ref": ".task/authorization/policy_snapshots/policy-parent-A.md",
                "sha256": "b" * 64,
            },
        }
    ]
    packet["reservation_binding"]["grant_uses"].append(  # type: ignore[index]
        {
            "grant_id": "grant-parent-A",
            "grant_sha256": "a" * 64,
            "units": 1,
            "state_version_before": 7,
            "state_version_after": 8,
        }
    )
    packet["dispatch_preflight"]["grant_states"].append(  # type: ignore[index]
        {
            "grant_id": "grant-parent-A",
            "grant_sha256": "a" * 64,
            "state_version": 8,
            "status": "active",
            "remaining_uses": 2,
            "reserved_uses": 1,
        }
    )
    reseal(packet)


def finding_codes(packet: dict[str, object]) -> set[str]:
    return {
        str(row["code"]) for row in validate("authority", packet, "block")["findings"]
    }


def derive_authority_codes(
    result: dict[str, object], workspace_root: Path | None = None
) -> set[str]:
    findings: list[dict[str, object]] = []
    context = RuleContext(
        target="derive",
        result=result,
        mode="block",
        findings=findings,
        missing=[],
        require_context_field=lambda _field, _code, _message: None,
        metadata={
            "contract_context": {"workspace_root": str(workspace_root)}
            if workspace_root is not None
            else {}
        },
    )
    check_authority_terminal(DeriveFacts(context=context))
    return {str(row["code"]) for row in findings}


def wait_baseline(packet: dict[str, object]) -> dict[str, object]:
    return {"format_version": 2, "watch_entries": [authority_watch_row(packet)]}


def repo(root: Path) -> Path:
    (root / ".agent_goal").mkdir(parents=True)
    (root / "task.md").write_text("# Task\n", encoding="utf-8")
    (root / ".agent_goal/final_goal.md").write_text("# Goal\n", encoding="utf-8")
    (root / ".agent_goal/agent_authority.md").write_text(
        "# Mutable current policy\n", encoding="utf-8"
    )
    return root


def packet_approval_projection(packet: dict[str, object]) -> dict[str, object]:
    operation = packet["operation_binding"]  # type: ignore[assignment]
    binding = packet["decision_binding"]  # type: ignore[assignment]
    scope = packet["scope"]  # type: ignore[assignment]
    excluded_effects = [
        "accept_risk_or_cost",
        "add_capabilities",
        "broaden_subject_or_operation",
        "change_goal_truth",
        "increase_risk_or_irreversibility",
        "reuse_beyond_scope_or_budget",
        "select_design_option",
        "supply_external_input",
    ]
    if scope["intent_type"] in excluded_effects:
        excluded_effects.remove(scope["intent_type"])
    core: dict[str, object] = {
        "schema_version": 2,
        "artifact_kind": "authority_approval_projection",
        "typed_intent": scope["intent_type"],
        "request_id": binding["request_id"],
        "operation": {
            key: operation[key]
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        },
        "subject": packet["subject"],
        "capabilities": ["repository.write"],
        "effect": {
            "effect_class": "bounded_effect",
            "data_class": "repository_code",
            "mutation_class": operation["mutation_class"],
            "reversibility": "reversible",
            "risk_tier": scope["risk_tier"],
            "decision_class": scope["decision_class"],
        },
        "scope": {
            "cardinality": "single_use",
            "use_budget": 1,
            "session_id": "session-A",
            "cycle_id": scope["cycle_id"],
            "task_id": scope["task_id"],
            "improvement_id": scope["pack_id"],
            "attempt_id": scope["attempt_id"],
        },
        "excluded_effects": excluded_effects,
        "safe_alternative": "request_narrowest_covering_grant_or_proceed_read_only",
        "reason_codes": [],
        "exact_replay_key": "attempt-operation-A",
    }
    return {"projection_id": f"authp-{canonical_sha256(core)[:24]}", **core}


def _write_json(path: Path, value: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def write_real_owner_approval_decision(
    root: Path,
    *,
    decision_class: str = "D3",
    risk_tier: str = "R1",
    risk_acceptance_status: str = "not_required",
    design_selection_status: str = "not_required",
) -> tuple[dict[str, object], dict[str, str]]:
    """Evaluate and persist one decision with the real authority owner."""

    subject_path = root / ".task/task.md"
    subject_path.parent.mkdir(parents=True, exist_ok=True)
    subject_path.write_text("# Owner integration subject\n", encoding="utf-8")
    subject_digest = hashlib.sha256(subject_path.read_bytes()).hexdigest()
    goal_path = root / ".agent_goal/goal_architecture.md"
    goal_path.parent.mkdir(parents=True, exist_ok=True)
    goal_path.write_text("# Exact autonomy source\n", encoding="utf-8")
    goal_digest = hashlib.sha256(goal_path.read_bytes()).hexdigest()

    skills_root = root / "owner-skills"
    manifest = {
        "schema_version": 2,
        "manifest_kind": "authority_operations",
        "skill_id": "owner-integration-skill",
        "skill_version": "1.0.0",
        "operations": [
            {
                "operation_id": "perform_change",
                "operation_version": "1",
                "mutation_class": "local_mutation",
                "required_capabilities": ["implementation.local.edit"],
                "source_rank_floor": "S1",
                "risk_floor": "R1",
                "decision_class": decision_class,
                "effect_classes": ["edit_local"],
                "data_classes": ["repository_code"],
                "reversibility": "conditionally_reversible",
                "subject_kinds": ["task"],
                "authority_applicability": "required",
                "authorization_mechanism": "grant",
            }
        ],
    }
    _write_json(
        skills_root / "owner-integration-skill/authority.operations.json", manifest
    )
    subject = {
        "kind": "task",
        "ref": ".task/task.md",
        "digest": subject_digest,
        "revision": "revision-owner-integration",
    }
    request = {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": "request-owner-integration",
        "skill_id": "owner-integration-skill",
        "skill_version": "1.0.0",
        "operation_id": "perform_change",
        "operation_version": "1",
        "cycle_id": "cycle-owner-integration",
        "task_id": "task-owner-integration",
        "pack_id": None,
        "attempt_id": "attempt-owner-integration",
        "actor_rank": "S0",
        "subject": subject,
        "required_capabilities": ["implementation.local.edit"],
        "effect_class": "edit_local",
        "data_class": "repository_code",
        "mutation_class": "local_mutation",
        "reversibility": "conditionally_reversible",
        "risk_tier": risk_tier,
        "decision_class": decision_class,
        "intent_type": "grant_authority",
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "idempotency_key": "owner-integration-replay",
        "context": {
            "external_input_status": "not_required",
            "goal_truth_status": "aligned",
            "risk_acceptance_status": risk_acceptance_status,
            "design_selection_status": design_selection_status,
            "external_input_evidence": None,
            "risk_acceptance_evidence": None,
            "design_selection_evidence": None,
        },
        "composition_receipt": None,
    }
    operation_key = ":".join(
        str(request[key])
        for key in ("skill_id", "skill_version", "operation_id", "operation_version")
    )
    context = {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {
            "capabilities": ["implementation.local.edit"],
            "risk_ceiling": "R3",
            "mutation_classes": ["local_mutation", "observe"],
            "evidence_id": "session-owner-integration",
        },
        "goal_autonomy_envelope": {
            "envelope_id": "envelope-owner-integration",
            "capabilities": ["implementation.local.edit"],
            "risk_ceiling": "R3",
            "decision_classes": [decision_class],
            "subjects": [subject_digest],
            "operations": [operation_key],
            "source_binding": {
                "ref": ".agent_goal/goal_architecture.md",
                "sha256": goal_digest,
            },
        },
    }
    decision = evaluate_owner_decision(
        root,
        request,
        context,
        evaluated_at="2026-07-18T00:00:00+00:00",
        skills_root=skills_root,
    )
    decision_ref = f".task/authorization/decisions/{decision['decision_id']}.json"
    decision_sha = _write_json(root / decision_ref, decision)
    return decision, {"ref": decision_ref, "sha256": decision_sha}


def write_bound_artifacts(root: Path, packet: dict[str, object]) -> None:
    """Materialize exact authority-owner files and reseal their packet echo."""

    operation = packet["operation_binding"]  # type: ignore[assignment]
    binding = packet["decision_binding"]  # type: ignore[assignment]
    scope = packet["scope"]  # type: ignore[assignment]
    axes = packet["axes"]  # type: ignore[assignment]
    selected = packet["selected_grants"]  # type: ignore[assignment]
    lineage = packet["lineage_grants"]  # type: ignore[assignment]
    mutating = operation["mutation_class"] != "observe"
    allowed = binding["decision"] == "allowed"
    for row in [*selected, *lineage]:
        grant_id = row["grant_id"]
        snapshot_ref = f".task/authorization/policy_snapshots/{grant_id}.md"
        snapshot = root / snapshot_ref
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(f"policy:{grant_id}\n", encoding="utf-8")
        row["policy_snapshot"] = {
            "ref": snapshot_ref,
            "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        }
        grant = {
            "schema_version": 2,
            "artifact_kind": "authority_grant",
            "grant_id": grant_id,
            "policy_snapshot": row["policy_snapshot"],
        }
        grant_ref = f".task/authorization/grants/{grant_id}.json"
        row["grant_sha256"] = _write_json(root / grant_ref, grant)
        state_version = row["state_version"]
        use = next(
            (
                item
                for item in packet["reservation_binding"]["grant_uses"]  # type: ignore[index]
                if item["grant_id"] == grant_id
            ),
            None,
        )
        if allowed and mutating and use is not None:
            use["grant_sha256"] = row["grant_sha256"]
            state_version = use["state_version_after"]
        state = {
            "schema_version": 2,
            "artifact_kind": "authority_grant_state",
            "grant_id": grant_id,
            "grant_sha256": row["grant_sha256"],
            "status": "active",
            "remaining_uses": 1,
            "reserved_uses": 1 if allowed and mutating else 0,
            "consumed_uses": 0,
            "version": state_version,
            "last_event_id": packet["reservation_binding"]["reservation_id"]  # type: ignore[index]
            if allowed and mutating
            else None,
        }
        _write_json(root / f".task/authorization/state/grants/{grant_id}.json", state)
        for verification in packet["dispatch_preflight"]["grant_states"]:  # type: ignore[index]
            if verification["grant_id"] == grant_id:
                verification.update(
                    {
                        "grant_sha256": row["grant_sha256"],
                        "state_version": state_version,
                        "status": "active",
                        "remaining_uses": state["remaining_uses"],
                        "reserved_uses": state["reserved_uses"],
                    }
                )

    risk_context = {
        "not_required": "not_required",
        "accepted": "resolved",
        "confirmation_required": "unresolved",
        "unverified": "unverified",
    }[axes["risk_cost"]["status"]]

    def evidence_binding(name: str) -> dict[str, str]:
        ref = f".task/authorization/source_snapshots/{name}-A.txt"
        path = root / ref
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"evidence:{name}\n", encoding="utf-8")
        return {"ref": ref, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    external_evidence = (
        evidence_binding("external")
        if axes["external_input"]["status"]
        in {"available", "missing_supplyable", "missing_unsupplyable"}
        else None
    )
    risk_evidence = evidence_binding("risk") if risk_context == "resolved" else None
    request = {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": binding["request_id"],
        "skill_id": operation["skill_id"],
        "skill_version": operation["skill_version"],
        "operation_id": operation["operation_id"],
        "operation_version": operation["operation_version"],
        "cycle_id": scope["cycle_id"],
        "task_id": scope["task_id"],
        "pack_id": scope["pack_id"],
        "attempt_id": scope["attempt_id"],
        "actor_rank": scope["required_source_rank"],
        "subject": packet["subject"],
        "required_capabilities": ["repository.write"],
        "effect_class": "bounded_effect",
        "data_class": "repository_code",
        "mutation_class": operation["mutation_class"],
        "reversibility": "reversible",
        "risk_tier": scope["risk_tier"],
        "decision_class": scope["decision_class"],
        "intent_type": scope["intent_type"],
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "idempotency_key": "attempt-operation-A",
        "context": {
            "external_input_status": axes["external_input"]["status"],
            "goal_truth_status": axes["goal_truth"]["status"],
            "risk_acceptance_status": risk_context,
            "design_selection_status": "not_required",
            "external_input_evidence": external_evidence,
            "risk_acceptance_evidence": risk_evidence,
            "design_selection_evidence": None,
        },
        "composition_receipt": packet["composition_receipt"],
    }
    evaluation_context = {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {"evidence_id": "session-A"},
        "goal_autonomy_envelope": {},
    }
    packet["approval_projection"] = (
        packet_approval_projection(packet)
        if binding["decision"] == "approval_required"
        else None
    )
    manifest = (
        {
            "ref": operation["manifest_ref"],
            "sha256": operation["manifest_sha256"],
        }
        if operation["manifest_ref"] is not None
        else None
    )
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_decision",
        "request": request,
        "request_sha256": canonical_sha256(request),
        "evaluation_context": evaluation_context,
        "evaluation_context_sha256": canonical_sha256(evaluation_context),
        "decision": binding["decision"],
        "reason_codes": [],
        "approval_projection": packet["approval_projection"],
        "selected_grants": selected,
        "lineage_grants": lineage,
        "operation_manifest": manifest,
        "effective_authority_fingerprint": binding["effective_authority_fingerprint"],
        "evaluated_at": "2026-07-17T00:00:00+00:00",
    }
    decision = {
        "decision_id": f"authd-{canonical_sha256(core)[:24]}",
        **core,
    }
    decision_ref = f".task/authorization/decisions/{decision['decision_id']}.json"
    decision_sha = _write_json(root / decision_ref, decision)
    binding.update(
        {
            "decision_id": decision["decision_id"],
            "artifact_ref": decision_ref,
            "artifact_sha256": decision_sha,
            "request_sha256": core["request_sha256"],
        }
    )
    for name, row in axes.items():
        status = row["status"]
        row["evidence_ids"] = (
            []
            if status in {"not_required", "not_applicable", "unverified"}
            else [f"{decision['decision_id']}:{name}"]
        )

    if allowed and mutating:
        reservation = packet["reservation_binding"]  # type: ignore[assignment]
        reservation_state = {
            "schema_version": 2,
            "artifact_kind": "authority_reservation_state",
            "reservation_id": reservation["reservation_id"],
            "status": reservation["status"],
            "version": reservation["state_version"],
            "last_event_id": reservation["reservation_id"],
        }
        reservation_artifact = {
            "schema_version": 2,
            "artifact_kind": "authority_reservation",
            "reservation_id": reservation["reservation_id"],
            "request_id": binding["request_id"],
            "request_sha256": binding["request_sha256"],
            "decision": {"ref": decision_ref, "sha256": decision_sha},
            "effective_authority_fingerprint": binding[
                "effective_authority_fingerprint"
            ],
            "grant_uses": reservation["grant_uses"],
            "state_changes": [
                {
                    "ref": reservation["state_ref"],
                    "before": None,
                    "after": reservation_state,
                }
            ],
            "reserved_at": "2026-07-17T00:00:00+00:00",
            "idempotency_key": "reservation-A",
        }
        reservation["artifact_sha256"] = _write_json(
            root / reservation["artifact_ref"], reservation_artifact
        )
        reservation["state_sha256"] = _write_json(
            root / reservation["state_ref"], reservation_state
        )
        preflight = packet["dispatch_preflight"]  # type: ignore[assignment]
        preflight["reservation"] = {
            "ref": reservation["artifact_ref"],
            "sha256": reservation["artifact_sha256"],
        }
        preflight["reservation_state"] = {
            "ref": reservation["state_ref"],
            "sha256": reservation["state_sha256"],
            "version": reservation["state_version"],
            "status": reservation["status"],
        }
        verification = {
            "schema_version": 2,
            "artifact_kind": "authority_verification",
            **{
                key: value
                for key, value in preflight.items()
                if key not in {"status", "artifact_ref", "artifact_sha256"}
            },
        }
        preflight["artifact_sha256"] = _write_json(
            root / preflight["artifact_ref"], verification
        )
    reseal(packet)


def test_closed_v2_authority_packet_passes_result_contract(tmp_path: Path) -> None:
    packet = authority_packet()
    write_bound_artifacts(tmp_path, packet)

    assert project_authority_packet(packet).valid
    assert (
        validate(
            "authority",
            packet,
            "block",
            {"workspace_root": str(tmp_path)},
        )["status"]
        == "ok"
    )


def test_approval_packet_passes_with_empty_grant_sets_and_owner_projection(
    tmp_path: Path,
) -> None:
    packet = authority_packet(
        decision="approval_required",
        authority_status="approval_required",
        local_status="unavailable",
    )
    write_bound_artifacts(tmp_path, packet)

    result = validate("authority", packet, "block", {"workspace_root": str(tmp_path)})

    assert result["status"] == "ok"
    assert packet["selected_grants"] == []
    assert packet["lineage_grants"] == []
    assert packet["approval_projection"] is not None


def test_legacy_authority_material_is_diagnostic_only() -> None:
    projection = project_authority_packet(
        {"authority_status": "already_granted", "classification_valid": True}
    )

    assert projection.status == "legacy_unverified"
    assert projection.decision == "classification_repair"
    assert projection.findings[0]["code"] == "authority_legacy_unverified"


def test_unknown_fields_and_axis_evidence_conflation_fail_closed() -> None:
    packet = authority_packet()
    packet["unexpected"] = True
    packet["axes"]["external_input"]["status"] = "available"  # type: ignore[index]
    packet["axes"]["external_input"]["evidence_ids"] = ["authority-evidence-A"]  # type: ignore[index]
    reseal(packet)

    codes = finding_codes(packet)

    assert "authority_packet_unknown_fields" in codes
    assert "authority_axes_evidence_conflated" in codes


def test_external_input_and_permission_cannot_be_inferred_from_each_other() -> None:
    packet = authority_packet(
        decision="approval_required",
        authority_status="granted",
        local_status="unavailable",
        external_status="missing_supplyable",
    )

    assert "authority_permission_inferred_from_other_axis" in finding_codes(packet)


def test_multi_grant_composition_is_explicit_and_closed() -> None:
    packet = authority_packet()
    second = copy.deepcopy(packet["selected_grants"][0])  # type: ignore[index]
    second["grant_id"] = "grant-B"
    second["grant_sha256"] = "7" * 64
    second["policy_snapshot"] = {
        "ref": ".task/authorization/policy_snapshots/policy-B.md",
        "sha256": "8" * 64,
    }
    packet["selected_grants"].append(second)  # type: ignore[union-attr]
    reseal(packet)

    assert "authority_implicit_grant_union" in finding_codes(packet)

    packet["composition_receipt"] = {
        "ref": ".task/authorization/compositions/composition-A.json",
        "sha256": "9" * 64,
    }
    reseal(packet)

    assert project_authority_packet(packet).valid


def test_duplicate_grants_never_collapse_into_an_implicit_union() -> None:
    packet = authority_packet()
    packet["selected_grants"].append(  # type: ignore[union-attr]
        copy.deepcopy(packet["selected_grants"][0])  # type: ignore[index]
    )
    packet["composition_receipt"] = {
        "ref": ".task/authorization/compositions/composition-A.json",
        "sha256": "9" * 64,
    }
    reseal(packet)

    assert "authority_duplicate_grant_binding" in finding_codes(packet)


def test_unknown_mutating_operation_and_toctou_drift_fail_closed() -> None:
    packet = mutating_packet()
    packet["operation_binding"]["manifest_status"] = "unknown"  # type: ignore[index]
    packet["dispatch_preflight"]["grant_states"][0]["state_version"] = 3  # type: ignore[index]
    reseal(packet)

    codes = finding_codes(packet)

    assert "authority_unknown_mutating_operation" in codes
    assert "authority_dispatch_toctou_mismatch" in codes


def test_unknown_mutating_operation_can_be_denied_without_fake_manifest() -> None:
    packet = authority_packet(
        decision="denied",
        mutation_class="local_mutation",
        authority_status="denied",
        local_status="unavailable",
    )
    packet["operation_binding"]["manifest_status"] = "unknown"  # type: ignore[index]
    packet["operation_binding"]["manifest_ref"] = None  # type: ignore[index]
    packet["operation_binding"]["manifest_sha256"] = None  # type: ignore[index]
    reseal(packet)

    assert project_authority_packet(packet).valid


def test_non_dispatch_and_observe_packets_cannot_hide_lease_state() -> None:
    packet = authority_packet(
        decision="approval_required",
        authority_status="approval_required",
        local_status="unavailable",
    )
    packet["dispatch_preflight"]["verification_id"] = "hidden-verification"  # type: ignore[index]
    reseal(packet)

    assert "authority_preflight_not_applicable_invalid" in finding_codes(packet)


def test_mutating_dispatch_accepts_exact_reservation_and_usage_echo() -> None:
    assert project_authority_packet(mutating_packet()).valid


def test_mutating_dispatch_requires_selected_and_lineage_budget_uses() -> None:
    packet = mutating_packet()
    add_lineage_grant(packet)

    assert project_authority_packet(packet).valid

    packet["reservation_binding"]["grant_uses"].pop()  # type: ignore[index]
    reseal(packet)
    assert "authority_reservation_grant_mismatch" in finding_codes(packet)


def test_allowed_mutation_fails_closed_without_artifact_context() -> None:
    result = validate("authority", mutating_packet(), "warn")

    assert result["status"] == "block"
    assert "authority_artifact_verification_unavailable" in {
        row["code"] for row in result["findings"]
    }


def test_mutating_dispatch_reopens_exact_owner_artifacts(tmp_path: Path) -> None:
    packet = mutating_packet()
    add_lineage_grant(packet)
    write_bound_artifacts(tmp_path, packet)

    result = validate("authority", packet, "block", {"workspace_root": str(tmp_path)})

    assert result["status"] == "ok"


def test_packet_builder_projects_exact_observe_and_mutating_owner_state(
    tmp_path: Path,
) -> None:
    observe = authority_packet()
    write_bound_artifacts(tmp_path, observe)
    built = build_authority_packet(
        tmp_path,
        {
            "ref": observe["decision_binding"]["artifact_ref"],  # type: ignore[index]
            "sha256": observe["decision_binding"]["artifact_sha256"],  # type: ignore[index]
        },
    )
    assert project_authority_packet(built).valid
    assert built["decision_binding"] == observe["decision_binding"]

    mutating = mutating_packet()
    add_lineage_grant(mutating)
    write_bound_artifacts(tmp_path, mutating)
    built = build_authority_packet(
        tmp_path,
        {
            "ref": mutating["decision_binding"]["artifact_ref"],  # type: ignore[index]
            "sha256": mutating["decision_binding"]["artifact_sha256"],  # type: ignore[index]
        },
        reservation_binding={
            "ref": mutating["reservation_binding"]["artifact_ref"],  # type: ignore[index]
            "sha256": mutating["reservation_binding"]["artifact_sha256"],  # type: ignore[index]
        },
        verification_binding={
            "ref": mutating["dispatch_preflight"]["artifact_ref"],  # type: ignore[index]
            "sha256": mutating["dispatch_preflight"]["artifact_sha256"],  # type: ignore[index]
        },
    )
    assert project_authority_packet(built).valid
    assert {row["grant_id"] for row in built["reservation_binding"]["grant_uses"]} == {
        "grant-A",
        "grant-parent-A",
    }


def test_packet_builder_accepts_real_owner_risk_approval_projection(
    tmp_path: Path,
) -> None:
    decision, binding = write_real_owner_approval_decision(
        tmp_path,
        risk_tier="R2",
        risk_acceptance_status="unresolved",
    )

    packet = build_authority_packet(tmp_path, binding)

    assert decision["reason_codes"] == ["risk_acceptance_unresolved"]
    assert packet["approval_projection"] == decision["approval_projection"]
    assert packet["approval_projection"]["typed_intent"] == "accept_risk_or_cost"
    assert (
        "accept_risk_or_cost" not in packet["approval_projection"]["excluded_effects"]
    )
    assert (
        validate("authority", packet, "block", {"workspace_root": str(tmp_path)})[
            "status"
        ]
        == "ok"
    )


def test_packet_builder_accepts_real_owner_design_approval_projection(
    tmp_path: Path,
) -> None:
    decision, binding = write_real_owner_approval_decision(
        tmp_path,
        decision_class="D1",
        design_selection_status="unresolved",
    )

    packet = build_authority_packet(tmp_path, binding)

    assert decision["reason_codes"] == ["goal_or_design_decision_unresolved"]
    assert packet["approval_projection"] == decision["approval_projection"]
    assert packet["approval_projection"]["typed_intent"] == "select_design_option"
    assert (
        "select_design_option" not in packet["approval_projection"]["excluded_effects"]
    )
    assert (
        validate("authority", packet, "block", {"workspace_root": str(tmp_path)})[
            "status"
        ]
        == "ok"
    )


def test_packet_builder_preserves_real_owner_grant_approval_projection(
    tmp_path: Path,
) -> None:
    decision, binding = write_real_owner_approval_decision(tmp_path)

    packet = build_authority_packet(tmp_path, binding)

    assert decision["reason_codes"] == [
        "no_authority_grants_registered",
        "no_single_covering_active_grant",
    ]
    assert packet["approval_projection"] == decision["approval_projection"]
    assert packet["approval_projection"]["typed_intent"] == "grant_authority"
    assert packet["approval_projection"]["excluded_effects"] == [
        "accept_risk_or_cost",
        "add_capabilities",
        "broaden_subject_or_operation",
        "change_goal_truth",
        "increase_risk_or_irreversibility",
        "reuse_beyond_scope_or_budget",
        "select_design_option",
        "supply_external_input",
    ]
    assert (
        validate("authority", packet, "block", {"workspace_root": str(tmp_path)})[
            "status"
        ]
        == "ok"
    )


def test_forged_packet_projection_cannot_replace_owner_decision(
    tmp_path: Path,
) -> None:
    packet = authority_packet()
    write_bound_artifacts(tmp_path, packet)
    packet["decision_binding"]["decision"] = "denied"  # type: ignore[index]
    packet["axes"]["authority"] = {  # type: ignore[index]
        "status": "denied",
        "evidence_ids": [
            f"{packet['decision_binding']['decision_id']}:authority"  # type: ignore[index]
        ],
    }
    packet["axes"]["local_resolution"] = {  # type: ignore[index]
        "status": "unavailable",
        "evidence_ids": [
            f"{packet['decision_binding']['decision_id']}:local_resolution"  # type: ignore[index]
        ],
    }
    packet["selected_grants"] = []
    reseal(packet)

    result = validate("authority", packet, "block", {"workspace_root": str(tmp_path)})

    assert "authority_owner_decision_mismatch" in {
        row["code"] for row in result["findings"]
    }


def test_owner_artifact_content_drift_is_rejected(tmp_path: Path) -> None:
    packet = authority_packet()
    write_bound_artifacts(tmp_path, packet)
    decision_path = tmp_path / packet["decision_binding"]["artifact_ref"]  # type: ignore[index]
    decision_path.write_text("{}\n", encoding="utf-8")

    result = validate("authority", packet, "block", {"workspace_root": str(tmp_path)})

    assert "authority_artifact_content_drift" in {
        row["code"] for row in result["findings"]
    }


def test_owner_artifact_path_escape_and_symlink_are_rejected(
    tmp_path: Path,
) -> None:
    escaped = authority_packet()
    escaped["decision_binding"]["artifact_ref"] = "../forged.json"  # type: ignore[index]
    reseal(escaped)
    result = validate("authority", escaped, "block", {"workspace_root": str(tmp_path)})
    assert "authority_artifact_path_unsafe" in {
        row["code"] for row in result["findings"]
    }

    packet = authority_packet()
    write_bound_artifacts(tmp_path, packet)
    decision_path = tmp_path / packet["decision_binding"]["artifact_ref"]  # type: ignore[index]
    target = tmp_path / "decision-copy.json"
    target.write_bytes(decision_path.read_bytes())
    decision_path.unlink()
    decision_path.symlink_to(target)
    result = validate("authority", packet, "block", {"workspace_root": str(tmp_path)})
    assert "authority_artifact_path_unsafe" in {
        row["code"] for row in result["findings"]
    }


def test_effective_fingerprint_ignores_non_authority_axes_but_binds_snapshot() -> None:
    packet = authority_packet()
    before = packet["effective_authority_fingerprint"]
    changed_axis = copy.deepcopy(packet)
    changed_axis["axes"]["risk_cost"] = {  # type: ignore[index]
        "status": "accepted",
        "evidence_ids": ["risk-evidence-B"],
    }
    assert effective_authority_fingerprint(changed_axis) == before

    changed_snapshot = copy.deepcopy(packet)
    changed_snapshot["selected_grants"][0]["policy_snapshot"]["sha256"] = "f" * 64  # type: ignore[index]
    assert effective_authority_fingerprint(changed_snapshot) != before


def test_derive_approval_wait_replays_only_exact_scoped_packet(
    tmp_path: Path,
) -> None:
    packet = authority_packet(
        decision="approval_required",
        authority_status="approval_required",
        local_status="unavailable",
    )
    write_bound_artifacts(tmp_path, packet)
    result = {
        "selection_outcome": "terminal_wait",
        "selected_task_kind": "",
        "authority_packet": packet,
        "terminal_wait": {"selection_tick_baseline": wait_baseline(packet)},
    }

    assert "derive_terminal_wait_authority_route_invalid" not in derive_authority_codes(
        result, tmp_path
    )

    result["terminal_wait"] = {"selection_tick_baseline": {"watch_entries": []}}
    assert "derive_terminal_wait_authority_route_invalid" in derive_authority_codes(
        result, tmp_path
    )


def test_derive_external_wait_is_not_permission_or_local_engineering(
    tmp_path: Path,
) -> None:
    packet = authority_packet(
        decision="waiting_external_input",
        authority_status="not_applicable",
        local_status="unavailable",
        external_status="missing_supplyable",
    )
    write_bound_artifacts(tmp_path, packet)
    waiting = {
        "selection_outcome": "terminal_wait",
        "authority_packet": packet,
        "terminal_wait": {"selection_tick_baseline": wait_baseline(packet)},
    }
    assert "derive_terminal_wait_authority_route_invalid" not in derive_authority_codes(
        waiting, tmp_path
    )

    local = copy.deepcopy(packet)
    local["axes"]["local_resolution"] = {  # type: ignore[index]
        "status": "available",
        "evidence_ids": ["local-evidence-B"],
    }
    reseal(local)
    waiting["authority_packet"] = local
    waiting["terminal_wait"] = {"selection_tick_baseline": wait_baseline(packet)}
    codes = derive_authority_codes(waiting, tmp_path)
    assert "derive_terminal_authority_axes_unverified" not in codes
    assert "derive_terminal_wait_authority_route_invalid" in codes


def test_local_resolution_does_not_suppress_explicit_risk_confirmation(
    tmp_path: Path,
) -> None:
    packet = authority_packet(
        decision="approval_required",
        authority_status="not_applicable",
        local_status="available",
        risk_status="confirmation_required",
    )
    packet["scope"]["intent_type"] = "accept_risk_or_cost"  # type: ignore[index]
    write_bound_artifacts(tmp_path, packet)
    result = {
        "selection_outcome": "user_escalation",
        "authority_packet": packet,
    }

    projection = project_authority_packet(packet)
    assert projection.valid
    assert projection.intent_type == "accept_risk_or_cost"
    assert (
        "derive_user_escalation_not_supported_by_authority_axes"
        not in derive_authority_codes(result, tmp_path)
    )


def test_unsupplyable_external_fact_stays_external_for_descope_or_terminal(
    tmp_path: Path,
) -> None:
    packet = authority_packet(
        decision="waiting_external_input",
        authority_status="not_applicable",
        local_status="unavailable",
        external_status="missing_unsupplyable",
        goal_status="aligned",
    )
    write_bound_artifacts(tmp_path, packet)

    terminal = {
        "selection_outcome": "terminal_blocked",
        "authority_packet": packet,
    }
    repair = {
        "selection_outcome": "selected",
        "selected_task_kind": "external_dependency_probe",
        "authority_packet": packet,
    }

    assert packet["axes"]["external_input"]["status"] == "missing_unsupplyable"  # type: ignore[index]
    assert packet["axes"]["goal_truth"]["status"] == "aligned"  # type: ignore[index]
    assert (
        "derive_goal_terminal_prohibited_by_authority_axes"
        not in derive_authority_codes(terminal, tmp_path)
    )
    assert "derive_waiting_state_monitor_not_selected" not in derive_authority_codes(
        repair, tmp_path
    )
    packet["scope"]["intent_type"] = "accept_risk_or_cost"  # type: ignore[index]
    reseal(packet)
    write_bound_artifacts(tmp_path, packet)
    result = {
        "selection_outcome": "user_escalation",
        "authority_packet": packet,
    }

    assert project_authority_packet(packet).valid
    assert (
        "derive_user_escalation_not_supported_by_authority_axes"
        in derive_authority_codes(result, tmp_path)
    )


def test_derive_legacy_packet_cannot_retroactively_support_terminal() -> None:
    result = {
        "selection_outcome": "terminal_blocked",
        "authority_classification": [
            {
                "authority_status": "already_granted",
                "classification_valid": True,
            }
        ],
    }

    assert "derive_terminal_authority_axes_unverified" in derive_authority_codes(result)


def test_selection_tick_ignores_unrelated_mutable_policy_change(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    packet = authority_packet(
        decision="approval_required",
        authority_status="approval_required",
        local_status="unavailable",
    )
    baseline = build_selection_tick(root, authority_packets=[packet])
    (root / ".agent_goal/agent_authority.md").write_text(
        "# Unrelated grant changed\n", encoding="utf-8"
    )

    replay = build_selection_tick(root, previous=baseline, authority_packets=[packet])

    assert replay["status"] == "no_op"
    assert replay["authority_scope_ids"] == baseline["authority_scope_ids"]


def test_unchanged_approval_and_external_wait_packets_replay_as_no_op(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    packets = (
        authority_packet(
            decision="approval_required",
            authority_status="approval_required",
            local_status="unavailable",
        ),
        authority_packet(
            decision="waiting_external_input",
            authority_status="granted",
            local_status="unavailable",
            external_status="waiting_state",
        ),
    )
    for packet in packets:
        baseline = build_selection_tick(root, authority_packets=[packet])
        replay = build_selection_tick(
            root, previous=baseline, authority_packets=[copy.deepcopy(packet)]
        )

        assert replay["status"] == "no_op"
        assert replay["reason"] == "watched_selection_inputs_unchanged"


def test_selection_tick_reopens_for_scoped_axis_or_subject_change(
    tmp_path: Path,
) -> None:
    root = repo(tmp_path)
    packet = authority_packet(
        decision="approval_required",
        authority_status="approval_required",
        local_status="unavailable",
    )
    baseline = build_selection_tick(root, authority_packets=[packet])
    changed_axis = copy.deepcopy(packet)
    changed_axis["axes"]["risk_cost"] = {  # type: ignore[index]
        "status": "accepted",
        "evidence_ids": ["risk-evidence-B"],
    }
    reseal(changed_axis)

    changed = build_selection_tick(
        root, previous=baseline, authority_packets=[changed_axis]
    )
    assert changed["status"] == "selection_required"

    changed_subject = copy.deepcopy(packet)
    changed_subject["subject"]["digest"] = "d" * 64  # type: ignore[index]
    changed_subject["approval_projection"] = packet_approval_projection(changed_subject)
    reseal(changed_subject)
    changed = build_selection_tick(
        root, previous=baseline, authority_packets=[changed_subject]
    )
    assert changed["status"] == "selection_required"


def test_selection_tick_rejects_mutable_whole_policy_watch(tmp_path: Path) -> None:
    root = repo(tmp_path)

    try:
        build_selection_tick(root, watch_paths=[".agent_goal/agent_authority.md"])
    except ValueError as exc:
        assert "mutable whole authority policy" in str(exc)
    else:  # pragma: no cover - explicit fail-close assertion
        raise AssertionError("mutable whole-policy watch was accepted")


def test_authority_watch_row_contains_no_source_bodies_or_paths() -> None:
    row = authority_watch_row(authority_packet())
    serialized = json.dumps(row, sort_keys=True)

    assert "artifact_ref" not in serialized
    assert "policy_snapshots" not in serialized


def _persist_verification(
    root: Path, core: dict[str, object]
) -> tuple[dict[str, object], dict[str, str]]:
    verification_id = f"authv-{canonical_sha256(core)[:24]}"
    verification = {"verification_id": verification_id, **core}
    ref = f".task/authorization/verifications/{verification_id}.json"
    return verification, {"ref": ref, "sha256": _write_json(root / ref, verification)}


def _settlement_fixture(
    root: Path,
) -> tuple[dict[str, object], dict[str, str], dict[str, str], dict[str, str]]:
    """Materialize an owner-shaped reserved -> consumed lifecycle."""

    packet = mutating_packet()
    write_bound_artifacts(root, packet)
    reservation = packet["reservation_binding"]  # type: ignore[assignment]
    preflight = packet["dispatch_preflight"]  # type: ignore[assignment]
    decision = packet["decision_binding"]  # type: ignore[assignment]
    use = reservation["grant_uses"][0]
    grant_state_ref = ".task/authorization/state/grants/grant-A.json"
    reserved_grant = json.loads((root / grant_state_ref).read_text(encoding="utf-8"))
    grant_before = {
        **reserved_grant,
        "reserved_uses": reserved_grant["reserved_uses"] - use["units"],
        "version": use["state_version_before"],
        "last_event_id": None,
    }
    reservation_state_ref = reservation["state_ref"]
    reserved_state = json.loads(
        (root / reservation_state_ref).read_text(encoding="utf-8")
    )
    reservation_artifact = json.loads(
        (root / reservation["artifact_ref"]).read_text(encoding="utf-8")
    )
    reservation_artifact["state_changes"] = [
        {
            "ref": grant_state_ref,
            "before": grant_before,
            "after": reserved_grant,
        },
        {
            "ref": reservation_state_ref,
            "before": None,
            "after": reserved_state,
        },
    ]
    reservation["artifact_sha256"] = _write_json(
        root / reservation["artifact_ref"], reservation_artifact
    )
    preflight_core: dict[str, object] = {
        "schema_version": 2,
        "artifact_kind": "authority_verification",
        "stage": "pre_dispatch",
        "reservation": {
            "ref": reservation["artifact_ref"],
            "sha256": reservation["artifact_sha256"],
        },
        "reservation_state": preflight["reservation_state"],
        "grant_states": preflight["grant_states"],
        "request_id": decision["request_id"],
        "effective_authority_fingerprint": reservation[
            "effective_authority_fingerprint"
        ],
        "verified_at": "2026-07-17T00:00:00+00:00",
    }
    predispatch, predispatch_binding = _persist_verification(root, preflight_core)
    preflight.update(
        {
            "status": "verified",
            "artifact_ref": predispatch_binding["ref"],
            "artifact_sha256": predispatch_binding["sha256"],
            **{
                key: value
                for key, value in predispatch.items()
                if key not in {"schema_version", "artifact_kind"}
            },
        }
    )
    reseal(packet)

    precommit_core = {
        **preflight_core,
        "stage": "pre_commit",
        "verified_at": "2026-07-17T00:01:00+00:00",
    }
    _, precommit_binding = _persist_verification(root, precommit_core)

    execution_ref = ".task/task_pack_retirement/overlays/overlay-A.json"
    execution_result = {
        "ref": execution_ref,
        "sha256": _write_json(
            root / execution_ref,
            {"schema_version": 1, "artifact_kind": "test_effect"},
        ),
    }
    idempotency_key = "settle-overlay-A"
    receipt_id = (
        "authu-"
        + canonical_sha256(
            {
                "reservation": reservation["artifact_sha256"],
                "key": idempotency_key,
            }
        )[:24]
    )
    grant_after = {
        **reserved_grant,
        "remaining_uses": reserved_grant["remaining_uses"] - use["units"],
        "reserved_uses": reserved_grant["reserved_uses"] - use["units"],
        "consumed_uses": reserved_grant["consumed_uses"] + use["units"],
        "status": "exhausted",
        "version": reserved_grant["version"] + 1,
        "last_event_id": receipt_id,
    }
    reservation_after = {
        **reserved_state,
        "status": "consumed",
        "version": reserved_state["version"] + 1,
        "last_event_id": receipt_id,
    }
    _write_json(root / grant_state_ref, grant_after)
    _write_json(root / reservation_state_ref, reservation_after)
    receipt = {
        "schema_version": 2,
        "artifact_kind": "authority_use_receipt",
        "receipt_id": receipt_id,
        "reservation": {
            "ref": reservation["artifact_ref"],
            "sha256": reservation["artifact_sha256"],
        },
        "execution_result": execution_result,
        "consumed_at": "2026-07-17T00:02:00+00:00",
        "grant_versions_after": {"grant-A": grant_after["version"]},
        "state_changes": [
            {
                "ref": grant_state_ref,
                "before": reserved_grant,
                "after": grant_after,
            },
            {
                "ref": reservation_state_ref,
                "before": reserved_state,
                "after": reservation_after,
            },
        ],
        "idempotency_key": idempotency_key,
    }
    receipt_ref = f".task/authorization/use_receipts/{receipt_id}.json"
    receipt_binding = {
        "ref": receipt_ref,
        "sha256": _write_json(root / receipt_ref, receipt),
    }
    return packet, precommit_binding, receipt_binding, execution_result


def _typed_settlement_fixture(
    root: Path,
) -> tuple[dict[str, object], dict[str, str], dict[str, str], dict[str, str]]:
    packet, precommit, receipt_binding, owner_result = _settlement_fixture(root)
    reservation = packet["reservation_binding"]  # type: ignore[assignment]
    subject = packet["subject"]  # type: ignore[assignment]
    result_core = {
        "schema_version": 2,
        "artifact_kind": "authority_execution_result",
        "reservation": {
            "ref": reservation["artifact_ref"],
            "sha256": reservation["artifact_sha256"],
        },
        "pre_commit_verification": precommit,
        "owner_result": owner_result,
        "effect_status": "confirmed_effect",
        "subject_before": subject,
        "subject_after": {
            "ref": subject["ref"],
            "sha256": subject["digest"],
        },
        "expected_subject_after_sha256": subject["digest"],
        "completed_at": "2026-07-17T00:02:00+00:00",
    }
    result_id = f"authr-{canonical_sha256(result_core)[:24]}"
    typed_result = {"result_id": result_id, **result_core}
    result_ref = f".task/authorization/execution_results/{result_id}.json"
    result_binding = {
        "ref": result_ref,
        "sha256": _write_json(root / result_ref, typed_result),
    }
    receipt = json.loads((root / receipt_binding["ref"]).read_text(encoding="utf-8"))
    receipt.update(
        {
            "execution_result": result_binding,
            "owner_execution_result": owner_result,
            "pre_commit_verification": precommit,
        }
    )
    receipt_binding["sha256"] = _write_json(root / receipt_binding["ref"], receipt)
    return packet, receipt_binding, owner_result, result_binding


def test_precommit_verification_binds_exact_reserved_packet(tmp_path: Path) -> None:
    packet, precommit, _, _ = _settlement_fixture(tmp_path)

    assert not validate_authority_verification_binding(packet, precommit, tmp_path)

    predispatch = packet["dispatch_preflight"]  # type: ignore[assignment]
    codes = {
        row["code"]
        for row in validate_authority_verification_binding(
            packet,
            {
                "ref": predispatch["artifact_ref"],
                "sha256": predispatch["artifact_sha256"],
            },
            tmp_path,
        )
    }
    assert "authority_verification_packet_mismatch" in codes


def test_precommit_verification_rejects_wrong_reservation(tmp_path: Path) -> None:
    packet, precommit, _, _ = _settlement_fixture(tmp_path)
    verification = json.loads((tmp_path / precommit["ref"]).read_text(encoding="utf-8"))
    core = {
        key: value for key, value in verification.items() if key != "verification_id"
    }
    core["reservation"] = {
        **core["reservation"],
        "sha256": "f" * 64,
    }
    _, wrong_binding = _persist_verification(tmp_path, core)

    codes = {
        row["code"]
        for row in validate_authority_verification_binding(
            packet, wrong_binding, tmp_path
        )
    }
    assert "authority_verification_packet_mismatch" in codes


def test_use_receipt_settlement_validates_activation_and_history(
    tmp_path: Path,
) -> None:
    packet, _, receipt, result = _settlement_fixture(tmp_path)

    assert not validate_authority_use_receipt_settlement(
        packet,
        receipt,
        tmp_path,
        execution_result=result,
        idempotency_key="settle-overlay-A",
    )
    assert not validate_authority_use_receipt_settlement(
        packet,
        receipt,
        tmp_path,
        execution_result=result,
        idempotency_key="settle-overlay-A",
        phase="historical",
    )


def test_typed_use_receipt_settlement_uses_owner_validator(tmp_path: Path) -> None:
    packet, receipt, owner_result, _ = _typed_settlement_fixture(tmp_path)

    assert not validate_authority_use_receipt_settlement(
        packet,
        receipt,
        tmp_path,
        execution_result=owner_result,
        idempotency_key="settle-overlay-A",
    )


@pytest.mark.parametrize(
    "tamper",
    (
        "extra_key",
        "reservation",
        "subject_before",
        "subject_after",
        "completed_at",
        "pre_commit_verification",
    ),
)
def test_typed_use_receipt_rejects_rehashed_closed_contract_forgery(
    tmp_path: Path,
    tamper: str,
) -> None:
    packet, receipt_binding, owner_result, result_binding = _typed_settlement_fixture(
        tmp_path
    )
    result = json.loads(
        (tmp_path / result_binding["ref"]).read_text(encoding="utf-8")
    )
    receipt = json.loads(
        (tmp_path / receipt_binding["ref"]).read_text(encoding="utf-8")
    )
    if tamper == "extra_key":
        result["forged"] = True
    elif tamper == "reservation":
        result["reservation"] = {**result["reservation"], "sha256": "f" * 64}
    elif tamper == "subject_before":
        result["subject_before"] = {
            **result["subject_before"],
            "digest": "e" * 64,
        }
    elif tamper == "subject_after":
        result["subject_after"] = {
            **result["subject_after"],
            "ref": ".task/a-different-subject.md",
        }
    elif tamper == "completed_at":
        result["completed_at"] = "not-a-timestamp"
    else:
        receipt["pre_commit_verification"] = owner_result
        result["pre_commit_verification"] = owner_result
    result.pop("result_id")
    result_id = f"authr-{canonical_sha256(result)[:24]}"
    result = {"result_id": result_id, **result}
    forged_ref = f".task/authorization/execution_results/{result_id}.json"
    receipt["execution_result"] = {
        "ref": forged_ref,
        "sha256": _write_json(tmp_path / forged_ref, result),
    }
    receipt_binding["sha256"] = _write_json(
        tmp_path / receipt_binding["ref"], receipt
    )

    codes = {
        row["code"]
        for row in validate_authority_use_receipt_settlement(
            packet,
            receipt_binding,
            tmp_path,
            execution_result=owner_result,
            idempotency_key="settle-overlay-A",
        )
    }
    assert "authority_execution_result_contract_invalid" in codes


def test_use_receipt_rejects_execution_result_and_idempotency_drift(
    tmp_path: Path,
) -> None:
    packet, _, receipt, result = _settlement_fixture(tmp_path)
    other_ref = ".task/task_pack_retirement/overlays/overlay-B.json"
    other = {
        "ref": other_ref,
        "sha256": _write_json(tmp_path / other_ref, {"different": True}),
    }
    result_codes = {
        row["code"]
        for row in validate_authority_use_receipt_settlement(
            packet,
            receipt,
            tmp_path,
            execution_result=other,
            idempotency_key="settle-overlay-A",
        )
    }
    assert "authority_use_receipt_binding_mismatch" in result_codes

    key_codes = {
        row["code"]
        for row in validate_authority_use_receipt_settlement(
            packet,
            receipt,
            tmp_path,
            execution_result=result,
            idempotency_key="different-settlement-key",
        )
    }
    assert "authority_artifact_path_unsafe" in key_codes


def test_use_receipt_rejects_malformed_delta(tmp_path: Path) -> None:
    packet, _, receipt_binding, result = _settlement_fixture(tmp_path)
    receipt = json.loads(
        (tmp_path / receipt_binding["ref"]).read_text(encoding="utf-8")
    )
    receipt["state_changes"][0]["after"]["consumed_uses"] += 1
    tampered_binding = {
        "ref": receipt_binding["ref"],
        "sha256": _write_json(tmp_path / receipt_binding["ref"], receipt),
    }

    codes = {
        row["code"]
        for row in validate_authority_use_receipt_settlement(
            packet,
            tampered_binding,
            tmp_path,
            execution_result=result,
            idempotency_key="settle-overlay-A",
        )
    }
    assert "authority_use_receipt_state_changes_invalid" in codes


def test_historical_settlement_ignores_later_cas_progress(tmp_path: Path) -> None:
    packet, _, receipt, result = _settlement_fixture(tmp_path)
    state_ref = ".task/authorization/state/grants/grant-A.json"
    state = json.loads((tmp_path / state_ref).read_text(encoding="utf-8"))
    state["version"] += 1
    state["last_event_id"] = "later-authority-event"
    _write_json(tmp_path / state_ref, state)

    activation_codes = {
        row["code"]
        for row in validate_authority_use_receipt_settlement(
            packet,
            receipt,
            tmp_path,
            execution_result=result,
            idempotency_key="settle-overlay-A",
        )
    }
    assert "authority_settlement_state_mismatch" in activation_codes
    assert not validate_authority_use_receipt_settlement(
        packet,
        receipt,
        tmp_path,
        execution_result=result,
        idempotency_key="settle-overlay-A",
        phase="historical",
    )
