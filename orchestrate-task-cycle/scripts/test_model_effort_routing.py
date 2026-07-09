#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).resolve().parents[1]
render_subskill_packet = load_module(ROOT / "scripts" / "render_subskill_packet.py")
result_contract = load_module(ROOT / "scripts" / "result_contract.py")
validate_cycle_transition = load_module(ROOT / "scripts" / "validate_cycle_transition.py")
assemble_cycle_report = load_module(ROOT / "scripts" / "assemble_cycle_report.py")
model_effort_router = load_module(ROOT / "scripts" / "model_effort_router.py")


def finding_codes(result: dict[str, Any]) -> set[str]:
    return {str(item.get("code")) for item in result.get("findings", [])}


def architecture_evidence() -> dict[str, str]:
    return {"path": ".schema/decision-004.md"}


def prior_tier5_evidence() -> dict[str, Any]:
    return {
        "path": ".task/cycle/test/derive-synthesis.json",
        "profile_id": "derive_synthesis",
        "routing_tier": 5,
        "requested_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "xhigh",
        "unresolved_finding_id": "ambiguity-1",
    }


def delegated_governance_result(**overrides: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "step": "governance",
        "task_id": "task-test",
        "changed_files": ["src/example.py"],
        "evidence_paths": ["evidence.json"],
        "agent_routing_applicability": "delegated",
        "policy_id": "gpt-5.6-tiered-routing-v2",
        "profile_id": "code_worker",
        "routing_tier": 2,
        "requested_model": "gpt-5.6-terra",
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


def test_policy_has_expected_tier_models() -> None:
    policy = render_subskill_packet.MODEL_EFFORT_POLICY

    assert policy["tiers"]["1"] == {
        "model": "gpt-5.6-terra",
        "effort": "low",
        "work_class": "mechanical_reversible",
    }
    assert policy["tiers"]["4"]["model"] == "gpt-5.6-terra"
    assert policy["tiers"]["4"]["effort"] == "xhigh"
    assert policy["tiers"]["5"]["model"] == "gpt-5.6-sol"
    assert policy["tiers"]["5"]["effort"] == "xhigh"
    assert policy["profiles"]["code_worker"]["default_tier"] == 2
    assert policy["profiles"]["derive_synthesis"]["default_tier"] == 5
    assert "ultra" in policy["prohibited_delegated_efforts"]


def test_renderer_uses_role_specific_terra_profiles() -> None:
    governance = render_subskill_packet.packet_for("governance", {}, {})
    derive = render_subskill_packet.packet_for("derive", {}, {})
    review = render_subskill_packet.packet_for("qualitative_review", {}, {})
    commit = render_subskill_packet.packet_for("commit", {}, {})

    assert governance["routing"]["code_worker"] == {
        "dynamic_routing": False,
        "policy_id": "gpt-5.6-tiered-routing-v2",
        "profile_id": "code_worker",
        "routing_tier": 2,
        "requested_model": "gpt-5.6-terra",
        "requested_reasoning_effort": "medium",
        "routing_reason_codes": ["profile_default"],
        "routing_signals": {},
        "routing_signal_evidence": {},
        "routing_violations": [],
    }
    assert governance["routing"]["important_review"]["requested_reasoning_effort"] == "xhigh"
    assert derive["routing"]["evidence_inspectors"]["requested_reasoning_effort"] == "high"
    assert derive["routing"]["synthesis"]["routing_tier"] == 5
    assert derive["routing"]["synthesis"]["requested_model"] == "gpt-5.6-sol"
    assert derive["routing"]["synthesis"]["requested_reasoning_effort"] == "xhigh"
    assert derive["routing"]["id_consistency"]["requested_reasoning_effort"] == "medium"
    assert review["routing"]["reviewer"]["requested_reasoning_effort"] == "xhigh"
    assert commit["routing"]["commit_finalization"]["requested_reasoning_effort"] == "low"


def test_result_contract_accepts_prompt_only_terra_with_limitation() -> None:
    result = result_contract.validate("governance", delegated_governance_result(), "warn")
    codes = finding_codes(result)

    assert "noncanonical_requested_model" not in codes
    assert "delegated_routing_evidence_missing" not in codes
    assert "routing_limitation_missing" not in codes
    assert "delegated_ultra_prohibited" not in codes


def test_result_contract_rejects_legacy_model_and_delegated_ultra() -> None:
    legacy = result_contract.validate(
        "derive",
        delegated_governance_result(requested_model="gpt-5.5"),
        "warn",
    )
    ultra = result_contract.validate(
        "governance",
        delegated_governance_result(requested_reasoning_effort="ultra"),
        "warn",
    )

    assert "unsupported_requested_model" in finding_codes(legacy)
    assert "tier_model_mismatch" in finding_codes(legacy)
    assert "delegated_ultra_prohibited" in finding_codes(ultra)


def test_result_contract_requires_max_reason() -> None:
    without_reason = result_contract.validate(
        "derive",
        delegated_governance_result(
            profile_id="exceptional_arbitration",
            routing_tier=5,
            requested_model="gpt-5.6-sol",
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
            requested_model="gpt-5.6-sol",
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
            requested_model="gpt-5.6-sol",
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


def test_dynamic_direction_signal_promotes_schema_planning_to_sol() -> None:
    route = model_effort_router.select_route(
        "schema_planning",
        {
            "final_direction_ownership": True,
            "signals": {"architecture_direction_change": True},
            "signal_evidence": {"architecture_direction_change": architecture_evidence()},
        },
    )

    assert route["routing_tier"] == 5
    assert route["requested_model"] == "gpt-5.6-sol"
    assert route["requested_reasoning_effort"] == "xhigh"
    assert route["routing_violations"] == []


def test_tier5_signal_without_evidence_does_not_promote() -> None:
    route = model_effort_router.select_route(
        "schema_planning",
        {"final_direction_ownership": True, "signals": {"architecture_direction_change": True}},
    )

    assert route["routing_tier"] == 3
    assert route["requested_model"] == "gpt-5.6-terra"
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
    assert route["requested_model"] == "gpt-5.6-sol"
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


def test_result_contract_accepts_justified_sol_and_rejects_unjustified_sol() -> None:
    justified = result_contract.validate(
        "schema_pre_derive",
        delegated_governance_result(
            profile_id="schema_planning",
            routing_tier=5,
            requested_model="gpt-5.6-sol",
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
            requested_model="gpt-5.6-sol",
            requested_reasoning_effort="xhigh",
            routing_reason_codes=["manual_upgrade"],
            final_direction_ownership=True,
            routing_signals={},
        ),
        "warn",
    )

    assert "dynamic_tier_not_justified" not in finding_codes(justified)
    assert "dynamic_tier_not_justified" in finding_codes(unjustified)


def test_advisory_review_profile_cannot_claim_sol() -> None:
    result = result_contract.validate(
        "qualitative_review",
        delegated_governance_result(
            profile_id="qualitative_review",
            routing_tier=5,
            requested_model="gpt-5.6-sol",
            requested_reasoning_effort="xhigh",
            routing_reason_codes=["final_direction_floor"],
            routing_signals={"direction_setting": True, "final_decision": True},
            routing_signal_evidence={"direction_setting": {"path": "task.md"}, "final_decision": {"path": "task.md"}},
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
            requested_model="gpt-5.6-sol",
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
        delegated_governance_result(actual_model="gpt-5.6-terra", actual_reasoning_effort="max"),
        "warn",
    )

    assert "actual_effort_route_mismatch" in finding_codes(result)
    assert result["status"] == "block"


def test_dynamic_direction_signal_cannot_promote_code_worker_to_sol() -> None:
    route = model_effort_router.select_route(
        "code_worker",
        {
            "signals": {"direction_setting": True, "final_decision": True},
            "signal_evidence": {"direction_setting": {"path": "task.md"}, "final_decision": {"path": "task.md"}},
        },
    )

    assert route["routing_tier"] == 3
    assert route["requested_model"] == "gpt-5.6-terra"
    assert {item["code"] for item in route["routing_violations"]} == {"tier_above_profile_max"}


def test_direct_tier_override_is_rejected() -> None:
    route = model_effort_router.select_route("schema_planning", {"final_direction_ownership": False, "requested_tier": 5})

    assert route["routing_tier"] == 3
    assert route["requested_model"] == "gpt-5.6-terra"
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
    assert accepted["requested_model"] == "gpt-5.6-sol"
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


def test_transition_validator_accepts_terra_and_warns_on_legacy_worker() -> None:
    terra = validate_cycle_transition.validate(
        {},
        {"routing": {"code_worker_model": "gpt-5.6-terra"}},
        "pre_governance",
    )
    legacy = validate_cycle_transition.validate(
        {},
        {"routing": {"code_worker_model": "gpt-5.5"}},
        "pre_governance",
    )

    assert "noncanonical_worker_model" not in finding_codes(terra)
    assert "noncanonical_worker_model" in finding_codes(legacy)


def test_transition_validator_binds_profile_to_target() -> None:
    stage = delegated_governance_result(
        profile_id="derive_synthesis",
        routing_tier=5,
        requested_model="gpt-5.6-sol",
        requested_reasoning_effort="xhigh",
    )

    result = validate_cycle_transition.validate({}, stage, "pre_governance")

    assert "target_profile_mismatch" in finding_codes(result)


def test_transition_validator_does_not_trust_supplied_target() -> None:
    stage = delegated_governance_result(
        step="bogus",
        profile_id="derive_synthesis",
        routing_tier=5,
        requested_model="gpt-5.6-sol",
        requested_reasoning_effort="xhigh",
    )

    result = validate_cycle_transition.validate({}, stage, "pre_governance")

    assert "routing_target_transition_mismatch" in finding_codes(result)
    assert "target_profile_mismatch" in finding_codes(result)


def test_transition_validator_rejects_actual_max_deviation() -> None:
    stage = delegated_governance_result(
        actual_model="gpt-5.6-terra",
        actual_reasoning_effort="max",
    )

    result = validate_cycle_transition.validate({}, stage, "pre_governance")

    assert "actual_effort_route_mismatch" in finding_codes(result)


def test_cycle_report_surfaces_routing_enforcement() -> None:
    stage = {
        "events": [
            {
                "step": "governance",
                "agent_routing_applicability": "delegated",
                "policy_id": "gpt-5.6-tiered-routing-v2",
                "profile_id": "code_worker",
                "routing_tier": 2,
                "requested_model": "gpt-5.6-terra",
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
        "governance: T2 code_worker gpt-5.6-terra/medium; policy=gpt-5.6-tiered-routing-v2; "
        'reasons=["profile_default"]; signals={}; violations=[]; enforcement=prompt_only; '
        "limitation=delegation API exposes no selectors"
    ]


def test_cycle_report_preserves_max_preconditions() -> None:
    stage = {
        "events": [
            {
                "step": "derive",
                "agent_routing_applicability": "delegated",
                "policy_id": "gpt-5.6-tiered-routing-v2",
                "profile_id": "exceptional_arbitration",
                "routing_tier": 5,
                "requested_model": "gpt-5.6-sol",
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

    assert "prior_tier5_evidence={'path': '.task/cycle/test/derive-synthesis.json'" in line
    assert "agent_count=1" in line
    assert "violations=[]" in line
