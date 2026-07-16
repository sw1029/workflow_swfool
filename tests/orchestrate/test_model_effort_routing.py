#!/usr/bin/env python3
from __future__ import annotations

from typing import Any

from orchestrate_task_cycle import (
    assemble_cycle_report,
    model_effort_router,
    render_subskill_packet,
    validate_cycle_transition,
)
from orchestrate_task_cycle.result_contract import api as result_contract

POLICY_ID = "configured-tiered-routing-v3"
BALANCED_MODEL_REF = "model_ref:balanced"
DIRECTION_MODEL_REF = "model_ref:direction"
RUNTIME_BALANCED_MODEL = "model_id_A"
RUNTIME_DIRECTION_MODEL = "model_id_B"


def finding_codes(result: dict[str, Any]) -> set[str]:
    return {str(item.get("code")) for item in result.get("findings", [])}


def architecture_evidence() -> dict[str, str]:
    return {"artifact_id": "evidence-004"}


def model_bindings() -> dict[str, dict[str, str]]:
    return {
        BALANCED_MODEL_REF: {
            "model": RUNTIME_BALANCED_MODEL,
            "binding_id": "binding-A",
            "source": "caller_configuration",
        },
        DIRECTION_MODEL_REF: {
            "model": RUNTIME_DIRECTION_MODEL,
            "binding_id": "binding-B",
            "source": "repository_adapter",
        },
    }


def prior_tier5_evidence() -> dict[str, Any]:
    return {
        "artifact_id": "evidence-005",
        "profile_id": "derive_synthesis",
        "routing_tier": 5,
        "requested_model_ref": DIRECTION_MODEL_REF,
        "requested_model": DIRECTION_MODEL_REF,
        "model_configuration_status": "reference_only",
        "requested_reasoning_effort": "xhigh",
        "unresolved_finding_id": "finding-001",
    }


def delegated_governance_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "step": "governance",
        "task_id": "task-test",
        "changed_files": ["src/example.py"],
        "evidence_paths": ["evidence.json"],
        "agent_routing_applicability": "delegated",
        "policy_id": POLICY_ID,
        "profile_id": "code_worker",
        "routing_tier": 2,
        "requested_model_ref": BALANCED_MODEL_REF,
        "requested_model": BALANCED_MODEL_REF,
        "model_configuration_status": "reference_only",
        "requested_reasoning_effort": "medium",
        "routing_reason_codes": ["profile_default"],
        "routing_signals": {},
        "routing_signal_evidence": {},
        "routing_violations": [],
        "routing_enforcement": "prompt_only",
        "routing_limitation": "delegation API exposes no model or effort selector",
    }
    result.update(overrides)
    return result


def test_policy_has_expected_abstract_tier_models() -> None:
    policy = render_subskill_packet.MODEL_EFFORT_POLICY

    assert policy["tiers"]["1"] == {
        "model": BALANCED_MODEL_REF,
        "effort": "low",
        "work_class": "mechanical_reversible",
    }
    assert policy["tiers"]["4"]["model"] == BALANCED_MODEL_REF
    assert policy["tiers"]["4"]["effort"] == "xhigh"
    assert policy["tiers"]["5"]["model"] == DIRECTION_MODEL_REF
    assert policy["tiers"]["5"]["effort"] == "xhigh"
    assert policy["profiles"]["code_worker"]["default_tier"] == 2
    assert policy["profiles"]["derive_synthesis"]["default_tier"] == 5
    assert "ultra" in policy["prohibited_delegated_efforts"]


def test_renderer_uses_role_specific_configured_profiles() -> None:
    governance = render_subskill_packet.packet_for("governance", {}, {})
    derive = render_subskill_packet.packet_for("derive", {}, {})
    review = render_subskill_packet.packet_for("qualitative_review", {}, {})
    commit = render_subskill_packet.packet_for("commit", {}, {})

    assert governance["routing"]["code_worker"] == {
        "dynamic_routing": False,
        "policy_id": POLICY_ID,
        "profile_id": "code_worker",
        "routing_tier": 2,
        "requested_model_ref": BALANCED_MODEL_REF,
        "requested_model": BALANCED_MODEL_REF,
        "model_configuration_status": "reference_only",
        "requested_reasoning_effort": "medium",
        "routing_reason_codes": ["profile_default"],
        "routing_signals": {},
        "routing_signal_evidence": {},
        "routing_violations": [],
    }
    assert governance["routing"]["important_review"]["requested_reasoning_effort"] == "xhigh"
    assert derive["routing"]["evidence_inspectors"]["requested_reasoning_effort"] == "high"
    assert derive["routing"]["synthesis"]["routing_tier"] == 5
    assert derive["routing"]["synthesis"]["requested_model"] == DIRECTION_MODEL_REF
    assert derive["routing"]["synthesis"]["requested_reasoning_effort"] == "xhigh"
    assert derive["routing"]["id_consistency"]["requested_reasoning_effort"] == "medium"
    assert review["routing"]["reviewer"]["requested_reasoning_effort"] == "xhigh"
    assert commit["routing"]["commit_finalization"]["requested_reasoning_effort"] == "low"


def test_result_contract_accepts_prompt_only_model_ref_with_limitation() -> None:
    result = result_contract.validate("governance", delegated_governance_result(), "warn")
    codes = finding_codes(result)

    assert "noncanonical_requested_model" not in codes
    assert "delegated_routing_evidence_missing" not in codes
    assert "routing_limitation_missing" not in codes
    assert "delegated_ultra_prohibited" not in codes


def test_result_contract_rejects_unknown_model_and_delegated_ultra() -> None:
    unknown = result_contract.validate(
        "derive",
        delegated_governance_result(requested_model="model_ref:unknown"),
        "warn",
    )
    ultra = result_contract.validate(
        "governance",
        delegated_governance_result(requested_reasoning_effort="ultra"),
        "warn",
    )

    assert "unsupported_requested_model" in finding_codes(unknown)
    assert "tier_model_mismatch" in finding_codes(unknown)
    assert "delegated_ultra_prohibited" in finding_codes(ultra)


def test_result_contract_requires_max_reason() -> None:
    without_reason = result_contract.validate(
        "derive",
        delegated_governance_result(
            profile_id="exceptional_arbitration",
            routing_tier=5,
            requested_model=DIRECTION_MODEL_REF,
            requested_reasoning_effort="max",
            routing_signals={"prior_tier5_unresolved": True},
            prior_tier5_unresolved=True,
            prior_tier5_evidence=prior_tier5_evidence(),
            agent_count=1,
        ),
        "warn",
    )
    with_reason = result_contract.validate(
        "derive",
        delegated_governance_result(
            profile_id="exceptional_arbitration",
            routing_tier=5,
            requested_model=DIRECTION_MODEL_REF,
            requested_reasoning_effort="max",
            routing_signals={"prior_tier5_unresolved": True},
            prior_tier5_unresolved=True,
            prior_tier5_evidence=prior_tier5_evidence(),
            agent_count=1,
            max_escalation_reason="xhigh synthesis left conflicting terminal dispositions",
        ),
        "warn",
    )

    assert "max_escalation_reason_missing" in finding_codes(without_reason)
    assert "max_escalation_reason_missing" not in finding_codes(with_reason)


def test_result_contract_requires_structured_prior_tier5_signal_for_max() -> None:
    result = result_contract.validate(
        "derive",
        delegated_governance_result(
            profile_id="exceptional_arbitration",
            routing_tier=5,
            requested_model=DIRECTION_MODEL_REF,
            requested_reasoning_effort="max",
            routing_signals={},
            prior_tier5_unresolved=True,
            prior_tier5_evidence=prior_tier5_evidence(),
            agent_count=1,
            max_escalation_reason="conflicting terminal dispositions",
        ),
        "warn",
    )

    assert "max_prior_tier5_evidence_missing" in finding_codes(result)


def test_result_contract_rejects_tier_effort_mismatch() -> None:
    result = result_contract.validate(
        "governance",
        delegated_governance_result(requested_reasoning_effort="high"),
        "warn",
    )

    assert "tier_effort_mismatch" in finding_codes(result)


def test_result_contract_blocks_unknown_profile() -> None:
    result = result_contract.validate(
        "governance",
        delegated_governance_result(profile_id="invented_profile"),
        "warn",
    )

    assert "unknown_model_effort_profile" in finding_codes(result)
    assert result["status"] == "block"


def test_dynamic_direction_signal_promotes_schema_planning_to_direction_profile() -> None:
    route = model_effort_router.select_route(
        "schema_planning",
        {
            "final_direction_ownership": True,
            "signals": {"architecture_direction_change": True},
            "signal_evidence": {"architecture_direction_change": architecture_evidence()},
        },
    )

    assert route["routing_tier"] == 5
    assert route["requested_model"] == DIRECTION_MODEL_REF
    assert route["requested_reasoning_effort"] == "xhigh"
    assert route["routing_violations"] == []


def test_tier5_signal_without_evidence_does_not_promote() -> None:
    route = model_effort_router.select_route(
        "schema_planning",
        {"final_direction_ownership": True, "signals": {"architecture_direction_change": True}},
    )

    assert route["routing_tier"] == 3
    assert route["requested_model"] == BALANCED_MODEL_REF
    assert route["routing_violations"] == [
        {"code": "tier5_signal_evidence_missing", "signal": "architecture_direction_change"}
    ]


def test_schema_direction_ownership_must_be_classified() -> None:
    unclassified = model_effort_router.select_route("schema_planning", {})
    ordinary = model_effort_router.select_route(
        "schema_planning",
        {"final_direction_ownership": False},
    )

    assert unclassified["routing_violations"] == [
        {"code": "direction_ownership_unclassified", "profile_id": "schema_planning"}
    ]
    assert ordinary["routing_tier"] == 3
    assert ordinary["routing_violations"] == []


def test_bare_string_is_not_valid_tier5_evidence() -> None:
    route = model_effort_router.select_route(
        "schema_planning",
        {
            "final_direction_ownership": True,
            "signals": {"architecture_direction_change": True},
            "signal_evidence": {"architecture_direction_change": "x"},
        },
    )

    assert route["routing_tier"] == 3
    assert route["routing_violations"] == [
        {"code": "tier5_signal_evidence_missing", "signal": "architecture_direction_change"}
    ]


def test_legacy_path_evidence_is_rejected_and_not_echoed() -> None:
    route = model_effort_router.select_route(
        "schema_planning",
        {
            "final_direction_ownership": True,
            "signals": {"architecture_direction_change": True},
            "signal_evidence": {"architecture_direction_change": {"path": "private/source"}},
        },
    )

    assert route["routing_tier"] == 3
    assert route["routing_signal_evidence"] == {}
    assert route["routing_violations"] == [
        {"code": "tier5_signal_evidence_missing", "signal": "architecture_direction_change"}
    ]


def test_resolved_binding_receipt_is_content_bound_and_validates() -> None:
    route = model_effort_router.select_route(
        "schema_planning",
        {
            "final_direction_ownership": True,
            "signals": {"architecture_direction_change": True},
            "signal_evidence": {"architecture_direction_change": architecture_evidence()},
            "model_bindings": model_bindings(),
        },
    )

    assert route["requested_model_ref"] == DIRECTION_MODEL_REF
    assert route["requested_model"] == RUNTIME_DIRECTION_MODEL
    assert route["model_configuration_status"] == "resolved"
    assert route["model_binding_receipt"]["model_ref"] == DIRECTION_MODEL_REF
    assert route["routing_violations"] == []
    assert model_effort_router.validate_claim({**route, "routing_enforcement": "enforced"}, target="schema_pre_derive") == []

    tampered = {**route, "requested_model": "model_id_C", "routing_enforcement": "enforced"}
    assert "model_binding_model_digest_mismatch" in {
        item["code"] for item in model_effort_router.validate_claim(tampered, target="schema_pre_derive")
    }


def test_resolved_binding_is_consumed_and_tamper_blocks_in_both_consumers() -> None:
    route = model_effort_router.select_route(
        "code_worker",
        {"model_bindings": model_bindings()},
    )
    stage = delegated_governance_result(
        **route,
        routing_enforcement="enforced",
        actual_model=route["requested_model"],
        actual_reasoning_effort=route["requested_reasoning_effort"],
    )

    contracted = result_contract.validate("governance", stage, "warn")
    transitioned = validate_cycle_transition.validate({}, stage, "pre_governance", stage)
    forbidden = {
        "unsupported_requested_model",
        "actual_model_outside_policy",
        "model_binding_model_digest_mismatch",
        "model_binding_receipt_hash_mismatch",
    }
    assert not (finding_codes(contracted) & forbidden)
    assert not (finding_codes(transitioned) & forbidden)

    tampered_receipt = {**route["model_binding_receipt"], "model_sha256": "0" * 64}
    tampered = {**stage, "model_binding_receipt": tampered_receipt}
    for observed in (
        result_contract.validate("governance", tampered, "warn"),
        validate_cycle_transition.validate({}, tampered, "pre_governance", tampered),
    ):
        assert "model_binding_model_digest_mismatch" in finding_codes(observed)
        assert "model_binding_receipt_hash_mismatch" in finding_codes(observed)
        severities = {
            item["code"]: item["severity"]
            for item in observed["findings"]
            if item["code"].startswith("model_binding_")
        }
        assert set(severities.values()) == {"block"}


def test_nested_resolved_binding_matches_top_level_consumer_validation() -> None:
    route = model_effort_router.select_route("code_worker", {"model_bindings": model_bindings()})
    top_level = delegated_governance_result(
        **route,
        routing_enforcement="enforced",
        actual_model=route["requested_model"],
        actual_reasoning_effort=route["requested_reasoning_effort"],
    )
    nested = {
        "step": "governance",
        "task_id": "task-test",
        "changed_files": ["artifact-A"],
        "evidence_paths": ["evidence-A"],
        "agent_routing_applicability": "delegated",
        "agent_routing": {
            **route,
            "routing_enforcement": "enforced",
            "actual_model": route["requested_model"],
            "actual_reasoning_effort": route["requested_reasoning_effort"],
        },
    }
    for payload in (top_level, nested):
        for observed in (
            result_contract.validate("governance", payload, "warn"),
            validate_cycle_transition.validate({}, payload, "pre_governance", payload),
        ):
            assert not {
                code
                for code in finding_codes(observed)
                if code.startswith("model_binding_") or code in {"unsupported_requested_model", "actual_model_outside_policy"}
            }


def test_resolved_claim_without_receipt_and_reference_only_enforced_fail_closed() -> None:
    missing_receipt = delegated_governance_result(
        requested_model_ref=BALANCED_MODEL_REF,
        requested_model=RUNTIME_BALANCED_MODEL,
        model_configuration_status="resolved",
        routing_enforcement="enforced",
        actual_model=RUNTIME_BALANCED_MODEL,
        actual_reasoning_effort="medium",
    )
    unresolved = delegated_governance_result(
        routing_enforcement="enforced",
        actual_model=BALANCED_MODEL_REF,
        actual_reasoning_effort="medium",
    )
    for consumer in (
        result_contract.validate("governance", missing_receipt, "warn"),
        validate_cycle_transition.validate({}, missing_receipt, "pre_governance", missing_receipt),
    ):
        assert "model_binding_receipt_missing" in finding_codes(consumer)
    for consumer in (
        result_contract.validate("governance", unresolved, "warn"),
        validate_cycle_transition.validate({}, unresolved, "pre_governance", unresolved),
    ):
        assert "unresolved_model_binding_for_enforced_route" in finding_codes(consumer)


def test_reference_only_route_cannot_claim_enforced_execution() -> None:
    route = model_effort_router.select_route("code_worker")
    findings = model_effort_router.validate_claim(
        {**route, "routing_enforcement": "enforced"},
        target="governance",
    )

    assert route["model_configuration_status"] == "reference_only"
    assert "unresolved_model_binding_for_enforced_route" in {item["code"] for item in findings}


def test_renderer_applies_structured_dynamic_signal() -> None:
    packet = render_subskill_packet.packet_for(
        "schema_pre_derive",
        {
            "model_effort_routing": {
                "profiles": {
                    "schema_planning": {
                        "final_direction_ownership": True,
                        "signals": {"architecture_direction_change": True},
                        "signal_evidence": {"architecture_direction_change": architecture_evidence()},
                    }
                }
            }
        },
        {},
    )

    route = packet["routing"]["schema_planning"]
    assert route["routing_tier"] == 5
    assert route["requested_model"] == DIRECTION_MODEL_REF
    assert route["routing_signals"] == {"architecture_direction_change": True}
    assert route["routing_signal_evidence"] == {"architecture_direction_change": architecture_evidence()}


def test_renderer_ignores_unscoped_global_direction_signal() -> None:
    packet = render_subskill_packet.packet_for(
        "governance",
        {"model_effort_routing": {"signals": {"architecture_direction_change": True}}},
        {},
    )

    assert packet["routing"]["code_worker"]["routing_tier"] == 2
    assert packet["routing"]["code_worker"]["routing_violations"] == []


def test_result_contract_accepts_justified_direction_and_rejects_unjustified_direction() -> None:
    justified = result_contract.validate(
        "schema_pre_derive",
        delegated_governance_result(
            profile_id="schema_planning",
            routing_tier=5,
            requested_model=DIRECTION_MODEL_REF,
            requested_reasoning_effort="xhigh",
            routing_reason_codes=["critical_direction_floor"],
            final_direction_ownership=True,
            routing_signals={"architecture_direction_change": True},
            routing_signal_evidence={"architecture_direction_change": architecture_evidence()},
        ),
        "warn",
    )
    unjustified = result_contract.validate(
        "schema_pre_derive",
        delegated_governance_result(
            profile_id="schema_planning",
            routing_tier=5,
            requested_model=DIRECTION_MODEL_REF,
            requested_reasoning_effort="xhigh",
            routing_reason_codes=["manual_upgrade"],
            final_direction_ownership=True,
            routing_signals={},
        ),
        "warn",
    )

    assert "dynamic_tier_not_justified" not in finding_codes(justified)
    assert "dynamic_tier_not_justified" in finding_codes(unjustified)


def test_advisory_review_profile_cannot_claim_direction_profile() -> None:
    result = result_contract.validate(
        "qualitative_review",
        delegated_governance_result(
            profile_id="qualitative_review",
            routing_tier=5,
            requested_model=DIRECTION_MODEL_REF,
            requested_reasoning_effort="xhigh",
            routing_reason_codes=["final_direction_floor"],
            routing_signals={"direction_setting": True, "final_decision": True},
            routing_signal_evidence={"direction_setting": {"artifact_id": "evidence-006"}, "final_decision": {"artifact_id": "evidence-007"}},
        ),
        "warn",
    )

    assert "profile_tier_mismatch" in finding_codes(result)
    assert "dynamic_tier_not_justified" in finding_codes(result)


def test_governance_cannot_claim_derive_synthesis_profile() -> None:
    result = result_contract.validate(
        "governance",
        delegated_governance_result(
            profile_id="derive_synthesis",
            routing_tier=5,
            requested_model=DIRECTION_MODEL_REF,
            requested_reasoning_effort="xhigh",
        ),
        "warn",
    )

    assert "target_profile_mismatch" in finding_codes(result)
    assert result["status"] == "block"


def test_reported_selector_violation_blocks_result() -> None:
    result = result_contract.validate(
        "governance",
        delegated_governance_result(
            routing_violations=[{"code": "explicit_tier_override_prohibited"}],
        ),
        "warn",
    )

    assert "reported_routing_violations" in finding_codes(result)
    assert result["status"] == "block"


def test_actual_max_cannot_bypass_validated_xhigh_route() -> None:
    result = result_contract.validate(
        "governance",
        delegated_governance_result(actual_model=BALANCED_MODEL_REF, actual_reasoning_effort="max"),
        "warn",
    )

    assert "actual_effort_route_mismatch" in finding_codes(result)
    assert result["status"] == "block"


def test_dynamic_direction_signal_cannot_promote_code_worker_to_direction_profile() -> None:
    route = model_effort_router.select_route(
        "code_worker",
        {
            "signals": {"direction_setting": True, "final_decision": True},
            "signal_evidence": {"direction_setting": {"artifact_id": "evidence-006"}, "final_decision": {"artifact_id": "evidence-007"}},
        },
    )

    assert route["routing_tier"] == 3
    assert route["requested_model"] == BALANCED_MODEL_REF
    assert {item["code"] for item in route["routing_violations"]} == {"tier_above_profile_max"}


def test_direct_tier_override_is_rejected() -> None:
    route = model_effort_router.select_route("schema_planning", {"final_direction_ownership": False, "requested_tier": 5})

    assert route["routing_tier"] == 3
    assert route["requested_model"] == BALANCED_MODEL_REF
    assert {item["code"] for item in route["routing_violations"]} == {
        "explicit_tier_override_prohibited"
    }


def test_bounded_max_requires_prior_tier5_evidence() -> None:
    rejected = model_effort_router.select_route(
        "exceptional_arbitration",
        {"request_max": True, "max_escalation_reason": "conflict", "agent_count": 1},
    )
    accepted = model_effort_router.select_route(
        "exceptional_arbitration",
        {
            "signals": {"prior_tier5_unresolved": True},
            "request_max": True,
            "max_escalation_reason": "conflict",
            "prior_tier5_evidence": prior_tier5_evidence(),
            "agent_count": 1,
        },
    )

    assert rejected["requested_reasoning_effort"] == "xhigh"
    assert rejected["routing_violations"][0]["code"] == "max_escalation_preconditions_unmet"
    assert accepted["requested_model"] == DIRECTION_MODEL_REF
    assert accepted["requested_reasoning_effort"] == "max"
    assert accepted["prior_tier5_unresolved"] is True
    assert accepted["prior_tier5_evidence"] == prior_tier5_evidence()
    assert accepted["max_escalation_reason"] == "conflict"
    assert accepted["agent_count"] == 1
    assert accepted["routing_violations"] == []


def test_final_synthesis_cannot_self_escalate_to_max() -> None:
    route = model_effort_router.select_route(
        "derive_synthesis",
        {
            "signals": {"prior_tier5_unresolved": True},
            "request_max": True,
            "max_escalation_reason": "conflict",
            "prior_tier5_evidence": prior_tier5_evidence(),
            "agent_count": 1,
        },
    )

    assert route["requested_reasoning_effort"] == "xhigh"
    assert route["routing_violations"][0]["code"] == "max_escalation_preconditions_unmet"


def test_renderer_preserves_context_max_evidence() -> None:
    packet = render_subskill_packet.packet_for(
        "derive",
        {
            "model_effort_routing": {
                "profiles": {
                    "exceptional_arbitration": {
                        "signals": {"prior_tier5_unresolved": True},
                        "request_max": True,
                        "max_escalation_reason": "conflicting terminal dispositions",
                        "prior_tier5_evidence": prior_tier5_evidence(),
                        "agent_count": 1,
                    }
                }
            }
        },
        {},
    )

    route = packet["routing"]["exceptional_arbitration"]
    assert route["requested_reasoning_effort"] == "max"
    assert route["prior_tier5_unresolved"] is True
    assert route["prior_tier5_evidence"] == prior_tier5_evidence()
    assert route["agent_count"] == 1
    assert route["routing_violations"] == []


def test_transition_validator_accepts_balanced_ref_and_warns_on_unknown_worker() -> None:
    balanced_routing = {"routing": {"code_worker_model": BALANCED_MODEL_REF}}
    unknown_routing = {"routing": {"code_worker_model": "model_ref:unknown"}}
    balanced = validate_cycle_transition.validate(
        {},
        balanced_routing,
        "pre_governance",
        balanced_routing,
    )
    unknown = validate_cycle_transition.validate(
        {},
        unknown_routing,
        "pre_governance",
        unknown_routing,
    )

    assert "noncanonical_worker_model" not in finding_codes(balanced)
    assert "noncanonical_worker_model" in finding_codes(unknown)


def test_transition_validator_binds_profile_to_target() -> None:
    stage = delegated_governance_result(
        profile_id="derive_synthesis",
        routing_tier=5,
        requested_model=DIRECTION_MODEL_REF,
        requested_reasoning_effort="xhigh",
    )

    result = validate_cycle_transition.validate({}, stage, "pre_governance", stage)

    assert "target_profile_mismatch" in finding_codes(result)


def test_transition_validator_does_not_trust_supplied_target() -> None:
    stage = delegated_governance_result(
        step="bogus",
        profile_id="derive_synthesis",
        routing_tier=5,
        requested_model=DIRECTION_MODEL_REF,
        requested_reasoning_effort="xhigh",
    )

    result = validate_cycle_transition.validate({}, stage, "pre_governance", stage)

    assert "routing_target_transition_mismatch" in finding_codes(result)
    assert "target_profile_mismatch" in finding_codes(result)


def test_transition_validator_rejects_actual_max_deviation() -> None:
    stage = delegated_governance_result(
        actual_model=BALANCED_MODEL_REF,
        actual_reasoning_effort="max",
    )

    result = validate_cycle_transition.validate({}, stage, "pre_governance", stage)

    assert "actual_effort_route_mismatch" in finding_codes(result)


def test_cycle_report_surfaces_routing_enforcement() -> None:
    stage = {
        "events": [
            {
                "step": "governance",
                "agent_routing_applicability": "delegated",
                "policy_id": POLICY_ID,
                "profile_id": "code_worker",
                "routing_tier": 2,
                "requested_model": BALANCED_MODEL_REF,
                "requested_reasoning_effort": "medium",
                "routing_reason_codes": ["profile_default"],
                "routing_signals": {},
                "routing_violations": [],
                "routing_enforcement": "prompt_only",
                "routing_limitation": "delegation API exposes no selectors",
            }
        ]
    }

    lines = assemble_cycle_report.model_effort_routing_lines({}, stage)

    assert lines == [
        f"governance: T2 code_worker {BALANCED_MODEL_REF}/medium; policy={POLICY_ID}; "
        'reasons=["profile_default"]; signals={}; violations=[]; enforcement=prompt_only; '
        "limitation=delegation API exposes no selectors"
    ]


def test_cycle_report_preserves_max_preconditions() -> None:
    stage = {
        "events": [
            {
                "step": "derive",
                "agent_routing_applicability": "delegated",
                "policy_id": POLICY_ID,
                "profile_id": "exceptional_arbitration",
                "routing_tier": 5,
                "requested_model": DIRECTION_MODEL_REF,
                "requested_reasoning_effort": "max",
                "routing_reason_codes": ["bounded_max_escalation"],
                "routing_signals": {"prior_tier5_unresolved": True},
                "routing_violations": [],
                "routing_enforcement": "enforced",
                "max_escalation_reason": "conflicting terminal dispositions",
                "prior_tier5_evidence": prior_tier5_evidence(),
                "agent_count": 1,
            }
        ]
    }

    line = assemble_cycle_report.model_effort_routing_lines({}, stage)[0]

    assert "prior_tier5_evidence={'artifact_id': 'evidence-005'" in line
    assert "agent_count=1" in line
    assert "violations=[]" in line
