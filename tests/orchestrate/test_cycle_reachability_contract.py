from __future__ import annotations

import argparse
import copy
from pathlib import Path
import tempfile

from audit_cycle_loopback.cycle_reachability import cycle_reachability_gate
from audit_cycle_loopback.evaluation_frame import _EvaluationFrame
from audit_cycle_loopback.evaluation_stages.progress_reachability import (
    _evaluate_progress_reachability,
)
from orchestrate_task_cycle import cycle_ledger, monitor_running_execution
from orchestrate_task_cycle.result_contract import api as result_contract
from orchestrate_task_cycle.result_contract.cycle_reachability import (
    assess_harvest_completion,
    canonical_sha256,
)
from orchestrate_task_cycle.result_contract.policy import pending_long_run_context
from orchestrate_task_cycle.result_contract.base import RuleContext
from orchestrate_task_cycle.result_contract.rules.derive_checks.cycle_reachability import (
    check_cycle_reachability,
)
from orchestrate_task_cycle.result_contract.rules.derive_checks.state import DeriveFacts


def unreachable_gate() -> dict[str, object]:
    return cycle_reachability_gate(
        {
            "acceptance_scale_id": "scale-A",
            "required_scale": 100,
            "unit": "items",
        },
        {
            "throughput_evidence_id": "throughput-A",
            "observed_cycle_throughput": 10,
            "unit": "items",
            "cycle_execution_cap": 5,
            "run_id": "measurement-A",
        },
    )


def launch_packet() -> dict[str, object]:
    gate = unreachable_gate()
    return {
        "step": "run",
        "task_id": "task-A",
        "execution_status": "running",
        "long_run_branch": True,
        "long_run_role": "monitor",
        "event_kind": "long_run_monitor",
        "run_id": "run-A",
        "owner_task_id": "task-A",
        "launch_cycle_id": "cycle-A",
        "command_argv": ["runner", "--run-id", "run-A"],
        "workdir": ".",
        "output_dir": ".task/run-A",
        "log_path": ".task/run-A/run.log",
        "startup_or_heartbeat_evidence": "heartbeat-A",
        "monitor_command": "monitor-A",
        "stop_command": "stop-A",
        "remaining_validation": "harvest predicate-A",
        "expected_completion_signal": "artifact-A",
        "expected_completion_artifacts": ["artifact-A"],
        "evidence_paths": ["evidence-A"],
        "unreachable_within_cycle": True,
        "cycle_reachability_gate": gate,
        "residual_acceptance": {
            "residual_acceptance_id": "residual-A",
            "original_acceptance_id": "acceptance-A",
            "status": "open",
            "acceptance_scale_id": "scale-A",
            "required_scale": 100.0,
            "scale_unit": "items",
        },
        "harvest_validation_plan": {
            "harvest_plan_id": "harvest-plan-A",
            "run_id": "run-A",
            "cycle_reachability_sha256": gate["cycle_reachability_sha256"],
            "acceptance_scale_id": "scale-A",
            "throughput_evidence_id": "throughput-A",
            "residual_acceptance_id": "residual-A",
            "validation_predicate_ids": ["predicate-A"],
        },
    }


def finding_codes(value: dict[str, object]) -> set[str]:
    return {
        str(row.get("code"))
        for row in value.get("findings", [])
        if isinstance(row, dict)
    }


def test_cycle_reachability_calculation_is_fail_quiet_and_confidence_aware() -> None:
    missing = cycle_reachability_gate(None, None)
    unreachable = unreachable_gate()
    uncertain = cycle_reachability_gate(
        {"required_scale": 100, "unit": "items"},
        {
            "observed_cycle_throughput": 20,
            "confidence_lower_bound": 0,
            "confidence_upper_bound": 30,
            "unit": "items",
            "cycle_execution_cap": 5,
        },
    )

    assert missing["evaluation_status"] == "not_evaluated"
    assert missing["constrains_disposition"] is False
    assert unreachable["reachability_verdict"] == "unreachable"
    assert unreachable["projected_cycle_capacity_upper"] == 50.0
    assert uncertain["reachability_verdict"] == "indeterminate"
    assert uncertain["constrains_disposition"] is False


def test_audit_consumes_adapter_scale_and_throughput_hooks() -> None:
    class Adapter:
        @staticmethod
        def acceptance_reachability(**_: object) -> dict[str, object]:
            return {"cycle_execution_cap": 5}

        @staticmethod
        def acceptance_scale(**_: object) -> dict[str, object]:
            return {
                "acceptance_scale_id": "scale-A",
                "required_scale": 100,
                "unit": "items",
            }

        @staticmethod
        def throughput_evidence(**_: object) -> dict[str, object]:
            return {
                "throughput_evidence_id": "throughput-A",
                "observed_cycle_throughput": 10,
                "unit": "items",
            }

    frame = _EvaluationFrame(
        {
            "args": argparse.Namespace(
                acceptance_reachability_json=None, metric_validity_json=None
            ),
            "bind_artifact_gate": lambda _name, value, **_kwargs: value,
            "current_root_key": "root-A",
            "domain_adapter": Adapter(),
            "family_key": "family-A",
            "gate_inputs": [],
            "output_delta": {},
            "paths": [],
            "quality": {},
            "record_adapter_hook_demand": lambda *_args, **_kwargs: None,
            "root": Path(".").resolve(),
            "runner_validation": {},
        }
    )

    _evaluate_progress_reachability(frame)
    state = frame.snapshot()

    assert state["cycle_reachability_gate"]["unreachable_within_cycle"] is True
    assert any(
        row.get("name") == "cycle_reachability_gate" for row in state["gate_inputs"]
    )


def test_run_contract_requires_conditional_reachability_transport() -> None:
    valid = result_contract.validate("run", launch_packet(), "block")
    invalid_packet = launch_packet()
    invalid_packet.pop("harvest_validation_plan")
    invalid = result_contract.validate("run", invalid_packet, "block")

    assert not any(
        code.startswith("run_cycle_reachability")
        or code == "run_harvest_validation_plan_missing"
        for code in finding_codes(valid)
    )
    assert "run_harvest_validation_plan_missing" in finding_codes(invalid)


def test_false_outer_flag_cannot_mask_nested_unreachable_gate() -> None:
    packet = launch_packet()
    packet["unreachable_within_cycle"] = False
    packet.pop("harvest_validation_plan")

    result = result_contract.validate("run", packet, "block")

    assert "run_harvest_validation_plan_missing" in finding_codes(result)


def test_false_or_unstructured_harvest_claim_cannot_complete() -> None:
    false_claim = launch_packet()
    false_claim.update(
        {
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "harvest_validation_complete": False,
        }
    )
    true_claim = copy.deepcopy(false_claim)
    true_claim["harvest_validation_complete"] = True

    false_result = result_contract.validate("validate", false_claim, "block")
    true_result = result_contract.validate("validate", true_claim, "block")

    assert "validate_unreachable_within_cycle_complete" in finding_codes(false_result)
    assert "validate_advanced_with_unreachable_within_cycle" in finding_codes(
        false_result
    )
    assert "validate_cycle_reachability_evidence_invalid" in finding_codes(true_result)
    assert "validate_unreachable_within_cycle_complete" in finding_codes(true_result)


def test_matching_harvest_receipt_or_fresh_recalculation_is_accepted() -> None:
    packet = launch_packet()
    gate = packet["cycle_reachability_gate"]
    receipt = {
        "receipt_version": 1,
        "status": "pass",
        "run_id": "run-A",
        "harvest_plan_id": "harvest-plan-A",
        "acceptance_scale_id": "scale-A",
        "residual_acceptance_id": "residual-A",
        "cycle_reachability_sha256": gate["cycle_reachability_sha256"],
        "observed_scale": 100,
        "scale_unit": "items",
        "validation_predicate_ids": ["predicate-A"],
        "output_fingerprint": "a" * 64,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    packet["harvest_validation_receipt"] = receipt
    assert assess_harvest_completion(packet).complete is True

    recalculated = launch_packet()
    recalculated["recomputed_cycle_reachability_gate"] = cycle_reachability_gate(
        {"acceptance_scale_id": "scale-A", "required_scale": 100, "unit": "items"},
        {
            "throughput_evidence_id": "throughput-B",
            "observed_cycle_throughput": 25,
            "unit": "items",
            "cycle_execution_cap": 5,
        },
    )
    assert assess_harvest_completion(recalculated).complete is True


def monitor_args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        pid=None,
        log_path=str(root / "run.log"),
        monitor_command=None,
        stop_command=None,
        heartbeat=None,
        remaining_validation=None,
        run_id=None,
        task_id=None,
        launch_cycle_id=None,
        long_run_branch=False,
        long_run_role=None,
        event_kind="long_run_monitor",
        output_dir=None,
        command_arg=None,
        workdir=None,
        expected_completion_signal=None,
        expected_completion_path=None,
        tmux_session=None,
        tmux_window=None,
        tmux_pane=None,
    )


def test_monitor_and_ledger_preserve_reachability_contract_losslessly() -> None:
    source = launch_packet()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "run.log").write_text("heartbeat\n", encoding="utf-8")
        source["log_path"] = str(root / "run.log")
        output = monitor_running_execution.monitor(source, monitor_args(root))
        cycle_ledger.init_cycle(root, "cycle-A", "task-A", "test")
        cycle_ledger.append_event(
            root,
            "cycle-A",
            {"step": "context", "status": "complete", "task_id": "task-A"},
        )
        event = {
            "step": "run",
            "status": "partial",
            "execution_status": output["status"],
            "event_kind": "long_run_monitor",
            "long_run_branch": True,
            "long_run_role": "monitor",
            **{
                key: output[key]
                for key in (
                    "run_id",
                    "cycle_reachability_gate",
                    "residual_acceptance",
                    "harvest_validation_plan",
                )
            },
        }
        appended = cycle_ledger.append_event(root, "cycle-A", event)

    for field in (
        "cycle_reachability_gate",
        "residual_acceptance",
        "harvest_validation_plan",
    ):
        assert output[field] == source[field]
        assert appended["event"][field] == source[field]


def test_pending_projection_merges_richer_reachability_binding_losslessly() -> None:
    packet = launch_packet()
    context = {
        "run_id": "run-A",
        "execution_status": "running",
        "long_run_branch": True,
        "latest_event": packet,
    }

    pending = pending_long_run_context(context)

    assert len(pending) == 1
    assert (
        pending[0]["cycle_reachability_sha256"]
        == packet["cycle_reachability_gate"]["cycle_reachability_sha256"]
    )
    assert pending[0]["harvest_plan_id"] == "harvest-plan-A"


def test_pending_projection_prefers_latest_status_after_historical_merge() -> None:
    historical = launch_packet()
    latest = copy.deepcopy(historical)
    latest["execution_status"] = "completed_pending_validation"
    latest["event_kind"] = "long_run_harvest"
    context = {
        "events": [historical],
        "latest_event": latest,
    }

    pending = pending_long_run_context(context)

    assert len(pending) == 1
    assert pending[0]["execution_status"] == "completed_pending_validation"
    assert pending[0]["event_kind"] == "long_run_harvest"
    assert pending[0]["binding_conflict"] is False


def test_pending_projection_marks_conflicting_same_run_bindings_and_derive_blocks() -> (
    None
):
    first = launch_packet()
    second = copy.deepcopy(first)
    second["owner_task_id"] = "task-B"
    second["task_id"] = "task-B"
    second["harvest_validation_plan"]["harvest_plan_id"] = "harvest-plan-B"

    pending = pending_long_run_context({"events": [first, second]})

    assert len(pending) == 1
    assert pending[0]["binding_conflict"] is True
    assert {row["field"] for row in pending[0]["binding_conflicts"]} == {
        "task_id",
        "harvest_plan_id",
    }
    first["cycle_reachability_route_binding"] = {
        "cycle_reachability_sha256": first["cycle_reachability_gate"][
            "cycle_reachability_sha256"
        ],
        "run_id": "run-A",
        "harvest_plan_id": "harvest-plan-A",
    }
    assert "derive_pending_run_reachability_binding_conflict" in derive_codes(
        first, "long_run_monitor", pending
    )


def derive_codes(
    packet: dict[str, object],
    selected_kind: str,
    pending: list[dict[str, object]],
) -> set[str]:
    findings: list[dict[str, object]] = []
    context = RuleContext(
        target="derive",
        result=packet,
        mode="block",
        findings=findings,
        missing=[],
        require_context_field=lambda *_args: None,
        metadata={"pending_long_runs": pending},
    )
    facts = DeriveFacts(context)
    facts.selected_kind = selected_kind
    check_cycle_reachability(facts)
    return {str(row["code"]) for row in findings}


def test_derive_separates_prelaunch_and_bound_active_run_routes() -> None:
    prelaunch = launch_packet()
    gate = prelaunch["cycle_reachability_gate"]
    prelaunch["cycle_reachability_route_binding"] = {
        "cycle_reachability_sha256": gate["cycle_reachability_sha256"]
    }
    assert "derive_cycle_reachability_prelaunch_route_invalid" in derive_codes(
        prelaunch, "long_run_monitor", []
    )
    assert "derive_cycle_reachability_prelaunch_route_invalid" not in derive_codes(
        prelaunch, "long_run_launch", []
    )

    active = copy.deepcopy(prelaunch)
    active["cycle_reachability_route_binding"] = {
        "cycle_reachability_sha256": gate["cycle_reachability_sha256"],
        "run_id": "run-A",
        "harvest_plan_id": "harvest-plan-A",
    }
    pending = [
        {
            "run_id": "run-A",
            "execution_status": "running",
            "cycle_reachability_sha256": gate["cycle_reachability_sha256"],
            "harvest_plan_id": "harvest-plan-A",
        }
    ]
    assert "derive_cycle_reachability_active_route_invalid" not in derive_codes(
        active, "long_run_monitor", pending
    )
    assert "derive_cycle_reachability_active_route_invalid" in derive_codes(
        active, "long_run_harvest", pending
    )
    active["cycle_reachability_route_binding"]["run_id"] = "run-B"
    assert "derive_cycle_reachability_active_binding_mismatch" in derive_codes(
        active, "long_run_monitor", pending
    )


def test_unrelated_pending_run_does_not_reclassify_prelaunch_reachability() -> None:
    prelaunch = launch_packet()
    gate = prelaunch["cycle_reachability_gate"]
    prelaunch["cycle_reachability_route_binding"] = {
        "cycle_reachability_sha256": gate["cycle_reachability_sha256"]
    }
    unrelated_pending = [
        {
            "run_id": "run-unrelated",
            "execution_status": "running",
            "cycle_reachability_sha256": "f" * 64,
            "harvest_plan_id": "harvest-plan-unrelated",
        }
    ]

    codes = derive_codes(prelaunch, "long_run_launch", unrelated_pending)

    assert "derive_pending_run_reachability_binding_missing" not in codes
    assert "derive_cycle_reachability_prelaunch_route_invalid" not in codes
