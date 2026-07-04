#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
from pathlib import Path
from typing import Any


def load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_PATH = Path(__file__).resolve()
ORCHESTRATE_ROOT = SCRIPT_PATH.parents[1]
SKILLS_ROOT = ORCHESTRATE_ROOT.parent
detect_progress_loop = load_module(ORCHESTRATE_ROOT / "scripts" / "detect_progress_loop.py")
code_structure_audit = load_module(ORCHESTRATE_ROOT / "scripts" / "code_structure_audit.py")
result_contract = load_module(ORCHESTRATE_ROOT / "scripts" / "result_contract.py")
validate_cycle_transition = load_module(ORCHESTRATE_ROOT / "scripts" / "validate_cycle_transition.py")
monitor_running_execution = load_module(ORCHESTRATE_ROOT / "scripts" / "monitor_running_execution.py")
anti_loop_gate_provider = load_module(
    SKILLS_ROOT / "audit-cycle-loopback" / "scripts" / "anti_loop_gate_provider.py"
)
task_pack_queue = load_module(ORCHESTRATE_ROOT / "scripts" / "task_pack_queue.py")
safe_failure_autopsy = load_module(SKILLS_ROOT / "run-task-code-and-log" / "scripts" / "safe_failure_autopsy.py")
cycle_ledger = load_module(ORCHESTRATE_ROOT / "scripts" / "cycle_ledger.py")


def base_pack(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pack_id": "pack-test",
        "status": "active",
        "goal": "Test pack.",
        "current_item_id": items[0]["item_id"] if items else None,
        "items": items,
        "mutation_log": [],
    }


def base_item(item_id: str, status: str = "planned") -> dict[str, Any]:
    return {
        "item_id": item_id,
        "order": 1,
        "status": status,
        "title": item_id,
        "objective": "Do work.",
        "acceptance": ["Meet the original measurable target."],
        "validation_profile": "current_only",
        "progress_target": "advanced",
    }


def test_task_pack_scope_fidelity_blocks_diluted_consumed_item() -> None:
    item = base_item("item-001", status="consumed")
    item["scope_fidelity"] = {
        "directive_id": "directive-r1",
        "original_target": {"metric": "entrypoint_loc", "comparator": "<=", "target": 2000},
        "item_acceptance": ["Meet the original measurable target."],
    }
    item["result"] = {
        "validation_verdict": "complete",
        "acceptance_provenance_gate": {"target_met": False, "acceptance_diluted": True},
    }

    findings = task_pack_queue.validate_pack(base_pack([item]))

    assert any(finding.get("code") == "acceptance_diluted_item_consumed" for finding in findings)
    assert task_pack_queue.status_from_findings(findings) == "block"


def test_task_pack_scope_fidelity_allows_explicit_descope_with_open_residual() -> None:
    narrowed = base_item("item-001", status="consumed")
    narrowed["scope_fidelity"] = {
        "directive_id": "directive-r1",
        "original_target": {"metric": "entrypoint_loc", "comparator": "<=", "target": 2000},
        "item_acceptance": ["Meet the original measurable target."],
        "narrowed": True,
        "narrow_reason": "Bounded first slice.",
        "residual_item_id": "item-002",
    }
    narrowed["result"] = {
        "validation_verdict": "complete",
        "acceptance_provenance_gate": {"target_met": False, "explicit_descope_decision": True},
    }
    residual = base_item("item-002", status="planned")
    residual["order"] = 2

    findings = task_pack_queue.validate_pack(base_pack([narrowed, residual]))

    assert not any(finding.get("severity") == "block" for finding in findings)


def test_task_pack_blocks_consumed_item_with_required_verifier_not_evaluated() -> None:
    item = base_item("item-001", status="consumed")
    item["scope_fidelity"] = {
        "directive_id": "directive-r1",
        "original_target": {"metric": "abstract_metric", "comparator": ">=", "target": 1},
        "item_acceptance": ["Meet the original measurable target."],
        "acceptance_verifier_contract": {
            "required_verifier": "abstract_verifier",
            "verifier_required": True,
            "evaluation_status": "not_evaluated",
        },
    }
    item["result"] = {
        "validation_verdict": "complete",
        "acceptance_provenance_gate": {"target_met": True},
    }

    findings = task_pack_queue.validate_pack(base_pack([item]))

    assert any(
        finding.get("code") == "acceptance_verifier_not_passed_item_consumed"
        for finding in findings
    )
    assert task_pack_queue.status_from_findings(findings) == "block"


def test_task_pack_blocks_coupled_verifier_pass_as_consumed() -> None:
    item = base_item("item-001", status="consumed")
    item["scope_fidelity"] = {
        "directive_id": "directive-r1",
        "original_target": {"metric": "abstract_metric", "comparator": ">=", "target": 1},
        "item_acceptance": ["Meet the original measurable target."],
        "acceptance_verifier_contract": {
            "required_verifier": "abstract_verifier",
            "verifier_required": True,
            "evaluation_status": "pass",
            "pass_with_coupled_verifier": True,
        },
    }
    item["result"] = {
        "validation_verdict": "complete",
        "acceptance_provenance_gate": {"target_met": True},
    }

    findings = task_pack_queue.validate_pack(base_pack([item]))

    assert any(
        finding.get("code") == "acceptance_verifier_not_passed_item_consumed"
        for finding in findings
    )
    assert task_pack_queue.status_from_findings(findings) == "block"


def test_task_pack_blocks_producer_attested_consumed_progress() -> None:
    item = base_item("item-001", status="consumed")
    item["scope_fidelity"] = {
        "directive_id": "directive-r1",
        "original_target": {"metric": "abstract_metric", "comparator": ">=", "target": 1},
        "item_acceptance": ["Meet the original measurable target."],
    }
    item["result"] = {
        "validation_verdict": "complete",
        "acceptance_provenance_gate": {"target_met": True},
        "evidence_provenance_gate": {
            "producer_attested_fields": ["abstract_metric"],
            "attested_only_movement": True,
        },
    }

    findings = task_pack_queue.validate_pack(base_pack([item]))

    assert any(
        finding.get("code") == "producer_attested_progress_item_consumed"
        for finding in findings
    )
    assert task_pack_queue.status_from_findings(findings) == "block"


def test_structure_metrics_gate_preserves_high_water_fields() -> None:
    gate = anti_loop_gate_provider.structure_metrics_gate(
        {
            "structure_metrics": {"entrypoint_loc": 1200, "structure_consolidation_recommended": True},
            "semantic_structure_metrics": {"mechanical_shard_file_count": 3},
            "global_invariants": {"global_part_file_count": 113},
            "structure_high_water_moved": True,
            "improved_structure_axes": ["entrypoint_loc"],
            "refactor_effect_required": True,
        }
    )

    assert gate["structure_consolidation_recommended"] is True
    assert gate["structure_high_water_moved"] is True
    assert gate["improved_structure_axes"] == ["entrypoint_loc"]
    assert gate["refactor_effect_required"] is True
    assert gate["structure_metrics"]["mechanical_shard_file_count"] == 3.0
    assert gate["structure_high_water_key_scope"] == "global_invariant"
    assert gate["structure_global_invariant_metrics"]["global_part_file_count"] == 113.0


def test_code_structure_audit_reports_semantic_signals_warn_only_without_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        src.mkdir()
        (src / "part_001.py").write_text(
            "_PREBIND_GLOBAL_NAMES = ['shared']\n"
            "globals().update({'shared': object()})\n"
            "def repeated():\n"
            "    return 1\n",
            encoding="utf-8",
        )
        (src / "part_002.py").write_text("def repeated():\n    return 2\n", encoding="utf-8")

        packet = code_structure_audit.audit(
            root,
            ["src/part_001.py", "src/part_002.py"],
            code_structure_audit.DEFAULT_THRESHOLDS,
            "task-test",
        )

    assert packet["audit_status"] == "warn"
    assert packet["moduleization_required"] is False
    assert packet["convention_conformance"]["code_convention_contract_status"] == "not_provided"
    assert packet["semantic_structure_metrics"]["mechanical_shard_file_count"] == 2
    assert packet["semantic_structure_metrics"]["global_rebinding_signal_count"] >= 2
    assert packet["semantic_structure_metrics"]["duplicate_symbol_name_count"] == 1


def test_code_structure_audit_enforced_contract_requires_semantic_refactor() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        src.mkdir()
        (src / "part_001.py").write_text("def repeated():\n    return 1\n", encoding="utf-8")
        contract = {
            "status": "provided",
            "enforcement": "required",
            "warn_only": False,
            "raw": {"enforcement": "required"},
        }

        packet = code_structure_audit.audit(
            root,
            ["src/part_001.py"],
            code_structure_audit.DEFAULT_THRESHOLDS,
            "task-test",
            contract,
        )

    assert packet["audit_status"] == "refactor_required"
    assert packet["moduleization_required"] is True
    assert packet["responsibility_split_plan"]
    assert any(finding["severity"] == "refactor_required" for finding in packet["semantic_structure_findings"])


def test_validate_result_contract_blocks_complete_with_convention_violation() -> None:
    result = result_contract.validate(
        "validate",
        {
            "task_id": "task-test",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "blockers": [],
            "evidence_paths": ["validation.md"],
            "convention_conformance_gate": {"status": "failed"},
        },
        "block",
    )

    assert any(
        finding.get("code") == "validate_complete_with_convention_violation"
        for finding in result["findings"]
    )


def test_terminal_outcome_family_fallback_groups_mutating_blockers() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registry = root / ".task" / "anti_loop" / "family_progress_registry.jsonl"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            json.dumps(
                {
                    "cycle_id": "cycle-old",
                    "family_key": "primary_output|old_blocker",
                    "root_family_key": "primary_output_no_delta",
                    "blocker_root_family": "primary_output_no_delta",
                    "same_family_micro_hardening_count": 2,
                    "micro_hardening_count": 2,
                    "semantic_progress": False,
                    "changed_vs_previous": False,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        args = argparse.Namespace(
            root=str(root),
            cycle_id="cycle-new",
            task_id="task-new",
            artifact_family="primary_output",
            semantic_signature="renamed_blocker_v2",
            root_key=None,
            domain_adapter=None,
            provider_request_count=0,
            artifact_path=[],
            artifact_paths_json=None,
            gate_state_json=[],
            recent_progress_json=None,
            runner_validation_json=None,
            output_delta_json=json.dumps(
                {
                    "produced_domain_delta": False,
                    "changed_vs_previous": False,
                    "semantic_progress": False,
                }
            ),
            substance_metrics_json=None,
            corrective_resolution_json=None,
            facet_root_map_json=None,
            root_cause_hypotheses_json=None,
            hypothesized_root_cause=None,
            root_cause_repair_attempted=False,
            root_cause_repair_task_id=None,
            root_cause_actionable=False,
            untried_promotion_budget=2,
            measurement_check_id=[],
            measurement_check_ids_json=None,
            measurement_frontier=[],
            measurement_streak_cap=1,
            detection_only_streak_cap=2,
            blocker_signature="different_proximate_blocker",
            blocker_rung=None,
            max_forward_mutations=3,
            consolidation_streak_cap=2,
            registry_path=".task/anti_loop/family_progress_registry.jsonl",
            root_cause_ledger_path=".task/anti_loop/root_cause_ledger.jsonl",
            threshold=3,
            epsilon=1e-9,
            max_rows_per_family=200,
            max_root_cause_rows_per_family=200,
            write_registry=False,
            output=None,
        )

        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    assert packet["facet_root_map_missing"] is True
    assert packet["family_key"] == "primary_output_no_delta"
    assert packet["legacy_family_key"] == "primary_output|renamed_blocker-v"
    assert packet["terminal_outcome_key"] == "no_primary_output_delta"
    assert packet["terminal_outcome_family_key"] == "primary_output_no_delta"
    assert packet["same_family_micro_hardening_count"] == 3
    assert any(
        finding.get("code") == "facet_root_map_missing"
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )


def test_adapter_mandate_blocks_missing_adapter_stall_chain() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registry = root / ".task" / "anti_loop" / "family_progress_registry.jsonl"
        registry.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "cycle_id": f"cycle-old-{index}",
                "family_key": f"primary_output_no_delta_{index}",
                "artifact_family": "primary_output",
                "root_family_key": f"renamed_family_{index}",
                "facet_root_map_missing": True,
                "coverage_quality_delta_gate": {"quality_delta_pass": False},
                "substance_delta_gate": {"status": "missing", "substance_delta_pass": False},
                "quality_vector": {},
                "semantic_progress": False,
            }
            for index in range(2)
        ]
        registry.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        args = argparse.Namespace(
            root=str(root),
            cycle_id="cycle-new",
            task_id="task-new",
            artifact_family="primary_output",
            semantic_signature="renamed_blocker_v3",
            root_key=None,
            domain_adapter=None,
            provider_request_count=0,
            artifact_path=[],
            artifact_paths_json=None,
            gate_state_json=[],
            recent_progress_json=None,
            runner_validation_json=None,
            output_delta_json=json.dumps({"changed_vs_previous": False, "semantic_progress": False}),
            substance_metrics_json=None,
            corrective_resolution_json=None,
            facet_root_map_json=None,
            acceptance_reachability_json=None,
            metric_validity_json=None,
            root_cause_hypotheses_json=None,
            hypothesized_root_cause=None,
            root_cause_repair_attempted=False,
            root_cause_repair_task_id=None,
            root_cause_actionable=False,
            untried_promotion_budget=2,
            measurement_check_id=[],
            measurement_check_ids_json=None,
            measurement_frontier=[],
            measurement_streak_cap=1,
            detection_only_streak_cap=2,
            adapter_mandate_streak_cap=3,
            cumulative_chain_streak_cap=3,
            blocker_signature="yet_another_blocker",
            blocker_rung=None,
            max_forward_mutations=3,
            consolidation_streak_cap=2,
            registry_path=".task/anti_loop/family_progress_registry.jsonl",
            root_cause_ledger_path=".task/anti_loop/root_cause_ledger.jsonl",
            threshold=3,
            epsilon=1e-9,
            max_rows_per_family=200,
            max_root_cause_rows_per_family=200,
            write_registry=False,
            output=None,
        )

        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    assert packet["adapter_mandate_required"] is True
    assert packet["adapter_missing_streak"] == 3
    assert set(packet["adapter_contract_unmet"]) >= {"facet_root_map", "substance_metrics"}
    assert packet["recommended_disposition"] == "adapter_mandate_required"
    assert any(
        finding.get("code") == "adapter_mandate_required"
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )


def test_registered_adapter_load_failure_routes_wiring_defect() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = root / ".task" / "domain_adapter.py"
        adapter.parent.mkdir(parents=True, exist_ok=True)
        adapter.write_text("raise RuntimeError('adapter boom')\n", encoding="utf-8")
        args = argparse.Namespace(
            root=str(root),
            cycle_id="cycle-new",
            task_id="task-new",
            artifact_family="primary_output",
            semantic_signature="same_root",
            root_key="same_root",
            domain_adapter=None,
            provider_request_count=0,
            artifact_path=[],
            artifact_paths_json=None,
            gate_state_json=[],
            recent_progress_json=None,
            runner_validation_json=None,
            output_delta_json=json.dumps({"changed_vs_previous": False, "semantic_progress": False}),
            substance_metrics_json=None,
            corrective_resolution_json=None,
            facet_root_map_json=None,
            acceptance_reachability_json=None,
            metric_validity_json=None,
            root_cause_hypotheses_json=None,
            hypothesized_root_cause=None,
            root_cause_repair_attempted=False,
            root_cause_repair_task_id=None,
            root_cause_actionable=False,
            untried_promotion_budget=2,
            measurement_check_id=[],
            measurement_check_ids_json=None,
            measurement_frontier=[],
            measurement_streak_cap=1,
            detection_only_streak_cap=2,
            adapter_mandate_streak_cap=3,
            cumulative_chain_streak_cap=3,
            blocker_signature="same_root",
            blocker_rung=None,
            max_forward_mutations=3,
            consolidation_streak_cap=2,
            registry_path=".task/anti_loop/family_progress_registry.jsonl",
            root_cause_ledger_path=".task/anti_loop/root_cause_ledger.jsonl",
            threshold=3,
            epsilon=1e-9,
            max_rows_per_family=200,
            max_root_cause_rows_per_family=200,
            write_registry=False,
            output=None,
        )

        anti_loop_gate_provider._DOMAIN_ADAPTER_MODULE = None
        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    assert packet["adapter_registered"] is True
    assert packet["adapter_loaded"] is False
    assert packet["adapter_wiring_defect"] is True
    assert packet["adapter_mandate_required"] is False
    assert packet["recommended_disposition"] == "self_inflicted_gate_defect"
    assert "adapter_wiring_fix" in packet["disposition_intersection_basis"]["adapter_wiring_gate"]["allowed_task_kinds"]
    assert any(
        finding.get("code") == "adapter_wiring_defect"
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )


def test_cumulative_chain_overrides_untried_veto_after_quality_stall() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = root / "domain_adapter.py"
        adapter.write_text(
            "\n".join(
                [
                    "def quality_vector(**kwargs):",
                    "    return {'quality_vector': {'event_named_ratio': 0, 'proper_noun_character_ratio': 0, 'coreference_resolved_ratio': 0, 'causal_edge_count': 0, 'windows_covered': 0, 'current_output_fingerprint': 'fp-current'}}",
                    "def substance_metrics(**kwargs):",
                    "    return {'event_count': 0}",
                    "def facet_root_map(**kwargs):",
                    "    return {'same_root': 'same_root'}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        registry = root / ".task" / "anti_loop" / "family_progress_registry.jsonl"
        registry.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "cycle_id": f"cycle-old-{index}",
                "family_key": "primary_output|same-root",
                "artifact_family": "primary_output",
                "root_family_key": "same_root",
                "facet_root_map_missing": False,
                "cumulative_goal_distance_scope_key": "root_family:same_root",
                "coverage_quality_delta_gate": {"quality_delta_pass": False},
                "substance_delta_gate": {"status": "block", "substance_delta_pass": False},
                "semantic_progress": False,
            }
            for index in range(2)
        ]
        registry.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        hypotheses = [
            {
                "hypothesized_root_cause": "new_distinct_hypothesis",
                "target_surface": "producer",
                "observed_delta_class": "no_observed_domain_delta",
                "local": True,
                "bounded": True,
                "provider_free": True,
                "in_scope": True,
                "authority_allowed": True,
                "actionable": True,
                "evidence_paths": ["evidence/packet.json"],
            }
        ]
        hypotheses_path = root / "hypotheses.json"
        hypotheses_path.write_text(json.dumps(hypotheses, sort_keys=True), encoding="utf-8")
        args = argparse.Namespace(
            root=str(root),
            cycle_id="cycle-new",
            task_id="task-new",
            artifact_family="primary_output",
            semantic_signature="same_root",
            root_key="same_root",
            domain_adapter=str(adapter),
            provider_request_count=0,
            artifact_path=[],
            artifact_paths_json=None,
            gate_state_json=[],
            recent_progress_json=None,
            runner_validation_json=None,
            output_delta_json=json.dumps({"changed_vs_previous": False, "semantic_progress": False}),
            substance_metrics_json=None,
            corrective_resolution_json=None,
            facet_root_map_json=None,
            acceptance_reachability_json=None,
            metric_validity_json=None,
            root_cause_hypotheses_json=str(hypotheses_path),
            hypothesized_root_cause=None,
            root_cause_repair_attempted=False,
            root_cause_repair_task_id=None,
            root_cause_actionable=False,
            untried_promotion_budget=2,
            measurement_check_id=[],
            measurement_check_ids_json=None,
            measurement_frontier=[],
            measurement_streak_cap=1,
            detection_only_streak_cap=2,
            adapter_mandate_streak_cap=3,
            cumulative_chain_streak_cap=3,
            blocker_signature="distinct_surface_label",
            blocker_rung=None,
            max_forward_mutations=3,
            consolidation_streak_cap=2,
            registry_path=".task/anti_loop/family_progress_registry.jsonl",
            root_cause_ledger_path=".task/anti_loop/root_cause_ledger.jsonl",
            threshold=3,
            epsilon=1e-9,
            max_rows_per_family=200,
            max_root_cause_rows_per_family=200,
            write_registry=False,
            output=None,
        )

        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    assert packet["cumulative_goal_distance_stalled"] is True
    assert packet["cumulative_goal_distance_stall_streak"] == 3
    assert packet["untried_actionable_root_cause_exists"] is True
    assert packet["cumulative_untried_chain_without_quality_delta"] is True
    assert packet["untried_veto_overridden_by_chain_stall"] is True
    assert packet["terminal_blocked_invalid_due_to_untried_root_cause"] is False
    assert packet["effective_allowed_dispositions"] == ["terminal_blocked", "user_escalation"]


def test_chain_stall_forces_actionable_ladder_task_kind() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = root / "domain_adapter.py"
        adapter.write_text(
            "\n".join(
                [
                    "def quality_vector(**kwargs):",
                    "    return {'quality_vector': {'event_named_ratio': 0, 'proper_noun_character_ratio': 0, 'coreference_resolved_ratio': 0, 'causal_edge_count': 0, 'windows_covered': 0, 'current_output_fingerprint': 'fp-current'}}",
                    "def substance_metrics(**kwargs):",
                    "    return {'event_count': 0}",
                    "def facet_root_map(**kwargs):",
                    "    return {'same_root': 'same_root'}",
                    "def capability_ladder(**kwargs):",
                    "    return {'rungs': [{'selected_task_kind': 'bounded_extraction', 'rung': 'M0', 'actionable': True, 'satisfied': False}]}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        registry = root / ".task" / "anti_loop" / "family_progress_registry.jsonl"
        registry.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "cycle_id": f"cycle-old-{index}",
                "family_key": "primary_output|same-root",
                "artifact_family": "primary_output",
                "root_family_key": "same_root",
                "blocker_root_family": "same_root",
                "cumulative_goal_distance_scope_key": "root_family:same_root",
                "blocker_signature": "old_surface",
                "coverage_quality_delta_gate": {"quality_delta_pass": False},
                "substance_delta_gate": {"status": "block", "substance_delta_pass": False},
                "semantic_progress": False,
            }
            for index in range(5)
        ]
        registry.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        args = argparse.Namespace(
            root=str(root),
            cycle_id="cycle-new",
            task_id="task-new",
            artifact_family="primary_output",
            semantic_signature="same_root",
            root_key="same_root",
            domain_adapter=str(adapter),
            provider_request_count=0,
            artifact_path=[],
            artifact_paths_json=None,
            gate_state_json=[],
            recent_progress_json=None,
            runner_validation_json=None,
            output_delta_json=json.dumps({"changed_vs_previous": False, "semantic_progress": False}),
            substance_metrics_json=None,
            corrective_resolution_json=None,
            facet_root_map_json=None,
            acceptance_reachability_json=None,
            metric_validity_json=None,
            root_cause_hypotheses_json=None,
            hypothesized_root_cause=None,
            root_cause_repair_attempted=False,
            root_cause_repair_task_id=None,
            root_cause_actionable=False,
            untried_promotion_budget=2,
            measurement_check_id=[],
            measurement_check_ids_json=None,
            measurement_frontier=[],
            measurement_streak_cap=1,
            detection_only_streak_cap=2,
            adapter_mandate_streak_cap=3,
            cumulative_chain_streak_cap=3,
            blocker_signature="new_surface",
            blocker_rung=None,
            max_forward_mutations=3,
            consolidation_streak_cap=2,
            registry_path=".task/anti_loop/family_progress_registry.jsonl",
            root_cause_ledger_path=".task/anti_loop/root_cause_ledger.jsonl",
            threshold=3,
            epsilon=1e-9,
            max_rows_per_family=200,
            max_root_cause_rows_per_family=200,
            write_registry=False,
            output=None,
        )

        anti_loop_gate_provider._DOMAIN_ADAPTER_MODULE = None
        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    assert packet["cumulative_goal_distance_stall_streak"] == 6
    assert packet["blocker_mutation_kind"] == "facet_rename"
    assert packet["chain_stall_forced_retarget_gate"]["chain_stall_force_retarget"] is True
    assert packet["recommended_disposition"] == "goal_productive"
    assert packet["forced_selected_task"]["selected_task_kind"] == "bounded_extraction"
    assert "bounded_extraction" in packet["disposition_intersection_basis"]["chain_stall_forced_retarget_gate"]["allowed_task_kinds"]
    assert "goal_productive" in packet["effective_allowed_dispositions"]


def test_repo_owned_source_provenance_rejects_nonactionable_self_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = root / "domain_adapter.py"
        adapter.write_text(
            "\n".join(
                [
                    "def repo_owned_source_roots(**kwargs):",
                    "    return ['scripts/**/*.py']",
                    "def facet_root_map(**kwargs):",
                    "    return {'self_gate': 'self_gate'}",
                    "def quality_vector(**kwargs):",
                    "    return {'quality_vector': {'event_named_ratio': 0, 'proper_noun_character_ratio': 0, 'coreference_resolved_ratio': 0, 'causal_edge_count': 0, 'windows_covered': 0, 'current_output_fingerprint': 'fp-current'}}",
                    "def substance_metrics(**kwargs):",
                    "    return {'event_count': 0}",
                    "def partial_progress_axes(**kwargs):",
                    "    return ['extraction_axis_observed']",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "scripts").mkdir()
        (root / "scripts" / "gate.py").write_text("# gate producer\n", encoding="utf-8")
        hypotheses = [
            {
                "hypothesized_root_cause": "pre_exec_gate_self_defect",
                "target_surface": "pre_exec_gate",
                "observed_delta_class": "blocked_pre_exec",
                "local": False,
                "bounded": True,
                "provider_free": True,
                "in_scope": False,
                "authority_allowed": True,
                "actionable": False,
                "evidence_paths": ["scripts/gate.py"],
            }
        ]
        hypotheses_path = root / "hypotheses.json"
        hypotheses_path.write_text(json.dumps(hypotheses, sort_keys=True), encoding="utf-8")
        args = argparse.Namespace(
            root=str(root),
            cycle_id="cycle-new",
            task_id="task-new",
            artifact_family="primary_output",
            semantic_signature="self_gate",
            root_key="self_gate",
            domain_adapter=str(adapter),
            provider_request_count=0,
            artifact_path=[],
            artifact_paths_json=None,
            gate_state_json=[
                json.dumps(
                    {
                        "gates": [
                            {
                                "gate_id": "pre_exec_gate",
                                "prior_verdict": "passed",
                                "current_verdict": "blocked",
                                "env_fingerprint_stable": True,
                            }
                        ]
                    }
                )
            ],
            recent_progress_json=None,
            runner_validation_json=None,
            output_delta_json=json.dumps({"changed_vs_previous": False, "semantic_progress": False}),
            substance_metrics_json=None,
            corrective_resolution_json=None,
            facet_root_map_json=None,
            acceptance_reachability_json=None,
            metric_validity_json=None,
            root_cause_hypotheses_json=str(hypotheses_path),
            hypothesized_root_cause=None,
            root_cause_repair_attempted=False,
            root_cause_repair_task_id=None,
            root_cause_actionable=False,
            untried_promotion_budget=2,
            measurement_check_id=[],
            measurement_check_ids_json=None,
            measurement_frontier=[],
            measurement_streak_cap=1,
            detection_only_streak_cap=2,
            adapter_mandate_streak_cap=3,
            cumulative_chain_streak_cap=3,
            blocker_signature="pre_exec_gate_blocked",
            blocker_rung=None,
            max_forward_mutations=3,
            consolidation_streak_cap=2,
            registry_path=".task/anti_loop/family_progress_registry.jsonl",
            root_cause_ledger_path=".task/anti_loop/root_cause_ledger.jsonl",
            threshold=3,
            epsilon=1e-9,
            max_rows_per_family=200,
            max_root_cause_rows_per_family=200,
            write_registry=False,
            output=None,
        )

        anti_loop_gate_provider._DOMAIN_ADAPTER_MODULE = None
        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    entry = packet["root_cause_ledger_entries"][0]
    assert packet["repo_owned_source_roots_status"] == "provided"
    assert packet["untried_actionable_root_cause_exists"] is True
    assert entry["local"] is True
    assert entry["in_scope"] is True
    assert entry["actionable"] is True
    assert entry["actionability_status"] == "verified"
    assert entry["self_report_rejected_fields"] == {"actionable": False, "in_scope": False, "local": False}
    assert entry["actionability_basis"]["provenance_derived_actionable"] is True
    assert entry["repo_owned_source_refs"] == ["scripts/gate.py"]
    assert packet["partial_progress_axes_gate"]["status"] == "warn"
    assert packet["advice_freshness_gate"]["gate_result_regression_stale"] is True
    assert any(
        finding.get("code") == "repo_owned_source_self_report_rejected"
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )
    assert any(
        finding.get("code") == "partial_progress_axes_flatlined"
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )
    assert any(
        finding.get("code") == "gate_result_regression_stale"
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )


def test_reachability_and_metric_validity_gates_are_conservative() -> None:
    reachability = anti_loop_gate_provider.acceptance_reachability_gate(
        {
            "acceptance_min_output": {"candidate_count": 2},
            "frozen_envelope": {"max_candidate_count": 1},
        }
    )
    metric_validity = anti_loop_gate_provider.oracle_metric_validity_gate(
        {"checks": [{"metric_validity": "tautological"}]}
    )
    missing_metric_validity = anti_loop_gate_provider.oracle_metric_validity_gate(None)
    required_missing = anti_loop_gate_provider.acceptance_reachability_gate(
        {"verifier_required": True, "required_verifier": "span_grounding"}
    )
    required_reachable_without_live_verifier = anti_loop_gate_provider.acceptance_reachability_gate(
        {
            "acceptance_min_output": {"candidate_count": 1},
            "frozen_envelope": {"max_candidate_count": 1},
            "required_verifier": "span_grounding",
        }
    )
    required_reachable_with_live_verifier = anti_loop_gate_provider.acceptance_reachability_gate(
        {
            "acceptance_min_output": {"candidate_count": 1},
            "frozen_envelope": {"max_candidate_count": 1},
            "acceptance_verifier_contract": {
                "required_verifier": "span_grounding",
                "evaluation_status": "pass",
            },
        }
    )
    required_metric_without_live_verifier = anti_loop_gate_provider.oracle_metric_validity_gate(
        {"required_verifier": "independent_metric"}
    )

    assert reachability["reachability_verdict"] == "unreachable"
    assert reachability["evaluation_status"] == "fail"
    assert reachability["relaxation_or_escalation_required"] is True
    assert metric_validity["metric_goal_productive_excluded"] is True
    assert metric_validity["evaluation_status"] == "fail"
    assert missing_metric_validity["status"] == "not_provided"
    assert missing_metric_validity["evaluation_status"] == "not_evaluated"
    assert missing_metric_validity["constrains_disposition"] is False
    assert required_missing["unverifiable_acceptance_contract"] is True
    assert required_missing["constrains_disposition"] is True
    assert required_reachable_without_live_verifier["reachability_verdict"] == "reachable"
    assert required_reachable_without_live_verifier["evaluation_status"] == "not_evaluated"
    assert required_reachable_without_live_verifier["unverifiable_acceptance_contract"] is True
    assert required_reachable_with_live_verifier["evaluation_status"] == "pass"
    assert required_reachable_with_live_verifier["unverifiable_acceptance_contract"] is False
    assert required_metric_without_live_verifier["evaluation_status"] == "not_evaluated"
    assert required_metric_without_live_verifier["metric_goal_productive_excluded"] is True


def test_evaluate_applies_target_required_verifier_adapter_contract() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = root / "domain_adapter.py"
        adapter.write_text(
            "\n".join(
                [
                    "def quality_vector(**kwargs):",
                    "    return {'quality_vector': {'event_named_ratio': 0, 'proper_noun_character_ratio': 0, 'coreference_resolved_ratio': 0, 'causal_edge_count': 0, 'windows_covered': 0, 'current_output_fingerprint': 'fp-current'}}",
                    "def substance_metrics(**kwargs):",
                    "    return {'event_count': 0}",
                    "def facet_root_map(**kwargs):",
                    "    return {'same_root': 'same_root'}",
                    "def acceptance_reachability(**kwargs):",
                    "    return {'target': {'metric': 'candidate_count', 'target': 1}, 'acceptance_min_output': {'candidate_count': 1}, 'frozen_envelope': {'max_candidate_count': 1}}",
                    "def target_required_verifier(target=None, **kwargs):",
                    "    assert target == {'metric': 'candidate_count', 'target': 1}",
                    "    return {'required_verifier': 'span_grounding', 'verifier_required': True}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        args = argparse.Namespace(
            root=str(root),
            cycle_id="cycle-new",
            task_id="task-new",
            artifact_family="primary_output",
            semantic_signature="same_root",
            root_key="same_root",
            domain_adapter=str(adapter),
            provider_request_count=0,
            artifact_path=[],
            artifact_paths_json=None,
            gate_state_json=[],
            recent_progress_json=None,
            runner_validation_json=None,
            output_delta_json=json.dumps({"changed_vs_previous": False, "semantic_progress": False}),
            substance_metrics_json=None,
            corrective_resolution_json=None,
            facet_root_map_json=None,
            acceptance_reachability_json=None,
            metric_validity_json=None,
            root_cause_hypotheses_json=None,
            hypothesized_root_cause=None,
            root_cause_repair_attempted=False,
            root_cause_repair_task_id=None,
            root_cause_actionable=False,
            untried_promotion_budget=2,
            measurement_check_id=[],
            measurement_check_ids_json=None,
            measurement_frontier=[],
            measurement_streak_cap=1,
            detection_only_streak_cap=2,
            adapter_mandate_streak_cap=3,
            cumulative_chain_streak_cap=3,
            blocker_signature="same_root",
            blocker_rung=None,
            max_forward_mutations=3,
            consolidation_streak_cap=2,
            registry_path=".task/anti_loop/family_progress_registry.jsonl",
            root_cause_ledger_path=".task/anti_loop/root_cause_ledger.jsonl",
            threshold=3,
            epsilon=1e-9,
            max_rows_per_family=200,
            max_root_cause_rows_per_family=200,
            write_registry=False,
            output=None,
        )

        anti_loop_gate_provider._DOMAIN_ADAPTER_MODULE = None
        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    reachability_gate = packet["acceptance_reachability_gate"]
    assert reachability_gate["reachability_verdict"] == "reachable"
    assert reachability_gate["required_verifier"] == "span_grounding"
    assert reachability_gate["evaluation_status"] == "not_evaluated"
    assert packet["unverifiable_acceptance_contract"] is True
    assert packet["recommended_disposition"] == "verifier_contract_required"
    assert any(
        finding.get("code") == "unverifiable_acceptance_contract"
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )


def test_terminal_recheck_escalates_to_user_input() -> None:
    progress_items = [
        {
            "blocker_root_family": "primary_output_no_primary_output_delta",
            "selected_task_source": "terminal_blocked",
            "recommended_disposition": "terminal_blocked",
            "path": ".task/cycle/cycle-new/packets/derive.json",
        },
        {
            "blocker_root_family": "primary_output_no_primary_output_delta",
            "selected_task_kind": "terminal_recheck",
            "disposition": "terminal_blocked",
            "path": ".task/cycle/cycle-old/packets/derive.json",
        },
    ]

    gate = detect_progress_loop.terminal_escalation_gate(progress_items, False, 2)

    assert gate["status"] == "block"
    assert gate["terminal_recheck_streak"] == 2
    assert gate["forced_disposition"] == "user_escalation"
    assert gate["missing_input_count"] == 1
    assert gate["missing_input"]["kind"] in {
        "new_input_kind",
        "authority_change",
        "external_state_change",
        "gate_contract_fix_approval",
    }
    assert gate["seal_required"] is True
    assert gate["recheck_counts_as_progress"] is False


def test_supplied_input_delta_prevents_terminal_escalation() -> None:
    progress_items = [
        {
            "blocker_root_family": "family",
            "selected_task_source": "terminal_blocked",
            "recommended_disposition": "terminal_blocked",
        },
        {
            "blocker_root_family": "family",
            "selected_task_kind": "terminal_recheck",
        },
    ]

    gate = detect_progress_loop.terminal_escalation_gate(progress_items, True, 2)

    assert gate["status"] == "ok"
    assert gate["terminal_recheck_streak"] == 2
    assert gate["escalation_required"] is False
    assert gate["forced_disposition"] is None


def test_result_contract_blocks_label_only_goal_productive_task_kind() -> None:
    result = result_contract.validate(
        "derive",
        {
            "completed_task_id": "task-old",
            "selected_task_source": "standalone",
            "next_task_id": "task-new",
            "loop_breaker_disposition": "goal_productive",
            "progress_kind": "goal_productive",
            "semantic_signature": "same-root",
            "selected_task_kind": "facet_rename",
            "effective_allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
            "disposition_intersection_basis": {
                "adapter_mandate_gate": {
                    "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
                    "allowed_task_kinds": ["adapter_registration", "adapter_wiring_fix"],
                    "constrains_disposition": True,
                }
            },
            "evidence_paths": ["derive.json"],
        },
        "block",
    )

    assert any(
        finding.get("code") == "goal_productive_task_kind_not_allowed"
        for finding in result["findings"]
    )


def test_result_contract_blocks_derive_goal_productive_from_part_f_failures() -> None:
    result = result_contract.validate(
        "derive",
        {
            "completed_task_id": "task-old",
            "selected_task_source": "standalone",
            "next_task_id": "task-new",
            "progress_kind": "goal_productive",
            "semantic_signature": "same-root",
            "pass_with_coupled_verifier": True,
            "attested_only_movement": True,
            "primary_metric_stalled": True,
            "evidence_paths": ["derive.json"],
        },
        "block",
    )

    codes = {finding.get("code") for finding in result["findings"]}
    assert "derive_goal_productive_from_coupled_verifier" in codes
    assert "derive_goal_productive_from_attested_only_movement" in codes
    assert "derive_primary_metric_stall_without_forced_task" in codes


def test_result_contract_blocks_loopback_part_f_misrouting() -> None:
    result = result_contract.validate(
        "loopback_audit",
        {
            "task_id": "task-1",
            "cycle_id": "cycle-1",
            "family_key": "family",
            "changed_vs_previous": True,
            "semantic_progress": True,
            "same_family_micro_hardening_count": 0,
            "recommended_disposition": "goal_productive",
            "hard_stop_required": False,
            "evidence_class": "direct",
            "pass_with_coupled_verifier": True,
            "evidence_provenance_gate": {"attested_only_movement": True},
            "primary_metric_gate": {
                "primary_metric_high_water_moved": True,
                "primary_metric_stalled": True,
                "c4_user_escalation_backstop_required": True,
            },
            "evidence_paths": ["loopback.json"],
        },
        "block",
    )

    codes = {finding.get("code") for finding in result["findings"]}
    assert "loopback_coupled_verifier_consumable_as_pass" in codes
    assert "loopback_attested_only_movement_counted_as_progress" in codes
    assert "loopback_primary_metric_stall_without_hard_stop" in codes
    assert "loopback_c4_user_escalation_misrouted" in codes


def test_result_contract_blocks_validate_completion_from_part_f_failures() -> None:
    result = result_contract.validate(
        "validate",
        {
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "pass_with_coupled_verifier": True,
            "evidence_provenance_gate": {
                "producer_attested_fields": ["abstract_metric"],
                "attested_only_movement": True,
            },
            "evidence_paths": ["validate.json"],
        },
        "block",
    )

    codes = {finding.get("code") for finding in result["findings"]}
    assert "validate_coupled_verifier_complete" in codes
    assert "validate_advanced_from_attested_only_movement" in codes
    assert "validate_complete_from_producer_attested_fields" in codes


def test_safe_failure_autopsy_records_stage_and_diagnostics_unavailable() -> None:
    packet = safe_failure_autopsy.autopsy(
        stdout_text="",
        stderr_text="",
        exit_code=1,
        command="python run.py",
        allow_secret_env_key_names=False,
        execution_stage_ladder={"stages": ["load", "generate", "parse"]},
        last_successful_stage="generate",
        post_failure_diagnostics=None,
    )

    assert packet["execution_stage_ladder_status"] == "provided"
    assert packet["last_successful_stage"] == "generate"
    assert packet["failure_surface_stage"] == "parse"
    assert packet["diagnostics_unavailable"] is True


def test_loopback_stage_contradiction_blocks_counting() -> None:
    gate = anti_loop_gate_provider.terminal_stage_resolution_gate(
        ladder_value={"stages": ["load", "generate", "parse"]},
        classification_map_value={"unavailable": ["load"]},
        contexts=[{"last_successful_stage": "generate", "classification": "unavailable"}],
        root_family_key="root",
        dominant_parameter="window_count_64",
    )

    assert gate["failure_surface_stage"] == "parse"
    assert gate["terminal_classification_stage_contradiction"] is True
    assert gate["terminal_classification_invalid_for_counting"] is True
    assert gate["status"] == "block"


def test_loopback_uses_failure_surface_count_key_and_forces_instrumentation_option() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registry = root / ".task" / "anti_loop" / "family_progress_registry.jsonl"
        registry.parent.mkdir(parents=True, exist_ok=True)
        current_count_key = anti_loop_gate_provider.normalize_root_family_key("same_root_family", "window_64", "parse")
        other_count_key = anti_loop_gate_provider.normalize_root_family_key("same_root_family", "window_64", "record")
        rows = [
            {
                "cycle_id": "cycle-other-surface",
                "family_key": "legacy",
                "root_family_key": "same_root_family",
                "failure_surface_count_key": other_count_key,
                "same_family_micro_hardening_count": 7,
                "diagnostics_unavailable": True,
                "semantic_progress": False,
            },
            {
                "cycle_id": "cycle-same-surface",
                "family_key": "legacy",
                "root_family_key": "same_root_family",
                "failure_surface_count_key": current_count_key,
                "same_family_micro_hardening_count": 1,
                "diagnostics_unavailable": True,
                "semantic_progress": False,
            },
        ]
        registry.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")
        args = argparse.Namespace(
            root=str(root),
            cycle_id="cycle-new",
            task_id="task-new",
            artifact_family="primary_output",
            semantic_signature="same_root",
            root_key="same_root",
            domain_adapter=None,
            provider_request_count=0,
            artifact_path=[],
            artifact_paths_json=None,
            gate_state_json=[],
            recent_progress_json=None,
            runner_validation_json=None,
            output_delta_json=json.dumps({"changed_vs_previous": False, "semantic_progress": False}),
            failure_autopsy_json=[
                json.dumps(
                    {
                        "execution_stage_ladder": ["load", "generate", "parse"],
                        "last_successful_stage": "generate",
                        "root_dominant_parameter_key": "window_64",
                        "diagnostics_unavailable": True,
                    }
                )
            ],
            instrumentation_trigger_threshold=2,
            substance_metrics_json=None,
            corrective_resolution_json=None,
            facet_root_map_json=json.dumps({"same_root": "same_root_family"}),
            acceptance_reachability_json=None,
            metric_validity_json=None,
            root_cause_hypotheses_json=None,
            hypothesized_root_cause=None,
            root_cause_repair_attempted=False,
            root_cause_repair_task_id=None,
            root_cause_actionable=False,
            untried_promotion_budget=2,
            measurement_check_id=[],
            measurement_check_ids_json=None,
            measurement_frontier=[],
            measurement_streak_cap=1,
            detection_only_streak_cap=2,
            adapter_mandate_streak_cap=3,
            cumulative_chain_streak_cap=3,
            blocker_signature="same_root",
            blocker_rung=None,
            max_forward_mutations=3,
            consolidation_streak_cap=2,
            registry_path=".task/anti_loop/family_progress_registry.jsonl",
            root_cause_ledger_path=".task/anti_loop/root_cause_ledger.jsonl",
            threshold=3,
            epsilon=1e-9,
            max_rows_per_family=200,
            max_root_cause_rows_per_family=200,
            envelope_thaw_streak_cap=2,
            write_registry=False,
            output=None,
        )

        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    forced_kinds = {option.get("selected_task_kind") for option in packet["forced_selected_task_options"]}
    assert packet["failure_surface_count_key"] == current_count_key
    assert packet["effective_count_key"] == current_count_key
    assert packet["same_family_micro_hardening_count"] == 2
    assert packet["diagnostics_unavailable_streak"] == 2
    assert packet["instrumentation_supply_required"] is True
    assert "instrumentation_supply" in forced_kinds


def test_loopback_downgrades_independent_when_verification_source_overlaps() -> None:
    gate = anti_loop_gate_provider.verification_source_separation_gate(
        provenance_value={
            "verification_input_paths": ["artifacts/result.json"],
            "evidence_provenance": {"metric": "independently_verified"},
        },
        verified_artifact_paths=["artifacts/result.json"],
        independently_verified_fields=["metric"],
    )

    assert gate["independent_source_separation_status"] == "overlap"
    assert gate["independently_verified_downgraded_fields"] == ["metric"]
    assert gate["status"] == "block"


def test_task_pack_blocks_independent_verified_without_source_separation() -> None:
    item = base_item("item-001", status="consumed")
    item["scope_fidelity"] = {
        "directive_id": "directive-r1",
        "original_target": {"metric": "abstract_metric", "comparator": ">=", "target": 1},
        "item_acceptance": ["Meet the original measurable target."],
    }
    item["result"] = {
        "validation_verdict": "complete",
        "acceptance_provenance_gate": {"target_met": True},
        "evidence_provenance_gate": {
            "independently_verified_fields": ["abstract_metric"],
            "independent_source_separation_status": "overlap",
        },
    }

    findings = task_pack_queue.validate_pack(base_pack([item]))

    assert any(
        finding.get("code") == "independent_verification_source_not_disjoint_item_consumed"
        for finding in findings
    )
    assert task_pack_queue.status_from_findings(findings) == "block"


def test_result_contract_blocks_part_h_misrouting() -> None:
    derive = result_contract.validate(
        "derive",
        {
            "completed_task_id": "task-1",
            "selected_task_source": "standalone",
            "next_task_id": "task-2",
            "progress_kind": "goal_productive",
            "semantic_signature": "sig",
            "selected_task_kind": "ordinary_repair",
            "instrumentation_supply_required": True,
            "terminal_classification_stage_contradiction": True,
            "same_input_contract_violation": True,
            "envelope_thaw_item_required": True,
            "evidence_paths": ["derive.json"],
        },
        "block",
    )
    loopback = result_contract.validate(
        "loopback_audit",
        {
            "task_id": "task-1",
            "cycle_id": "cycle-1",
            "family_key": "family",
            "changed_vs_previous": False,
            "semantic_progress": False,
            "same_family_micro_hardening_count": 1,
            "recommended_disposition": "goal_productive",
            "hard_stop_required": False,
            "evidence_class": "direct",
            "terminal_classification_stage_contradiction": True,
            "same_input_contract_violation": True,
            "instrumentation_supply_required": True,
            "envelope_thaw_item_required": True,
            "evidence_paths": ["loopback.json"],
        },
        "block",
    )
    validate = result_contract.validate(
        "validate",
        {
            "task_id": "task-1",
            "validation_verdict": "complete",
            "progress_verdict": "advanced",
            "independently_verified_fields": ["metric"],
            "independent_source_separation_status": "missing",
            "envelope_thaw_item_required": True,
            "terminal_classification_stage_contradiction": True,
            "same_input_contract_violation": True,
            "instrumentation_supply_required": True,
            "evidence_paths": ["validate.json"],
        },
        "block",
    )

    derive_codes = {finding.get("code") for finding in derive["findings"]}
    loopback_codes = {finding.get("code") for finding in loopback["findings"]}
    validate_codes = {finding.get("code") for finding in validate["findings"]}
    assert "derive_missing_instrumentation_supply" in derive_codes
    assert "derive_terminal_classification_stage_repair_missing" in derive_codes
    assert "derive_same_input_contract_repair_missing" in derive_codes
    assert "derive_envelope_thaw_item_missing" in derive_codes
    assert "loopback_terminal_classification_stage_not_fail_closed" in loopback_codes
    assert "loopback_same_input_contract_not_fail_closed" in loopback_codes
    assert "loopback_instrumentation_supply_not_fail_closed" in loopback_codes
    assert "loopback_envelope_thaw_item_not_reserved" in loopback_codes
    assert "validate_independent_verification_source_not_disjoint" in validate_codes
    assert "validate_frozen_envelope_complete_without_thaw_item" in validate_codes
    assert "validate_complete_with_terminal_classification_contradiction" in validate_codes


def test_cycle_ledger_records_unchanged_ref_for_duplicate_artifact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifact = root / "packet.json"
        artifact.write_text(json.dumps({"same": True}, sort_keys=True), encoding="utf-8")
        first = cycle_ledger.append_event(
            root,
            "cycle-1",
            {"step": "run", "status": "complete", "artifacts": ["packet.json"]},
        )
        second = cycle_ledger.append_event(
            root,
            "cycle-1",
            {"step": "validate", "status": "complete", "artifacts": ["packet.json"]},
        )

    assert first["event"]["artifact_refs"][0]["sha256"]
    assert second["event"]["unchanged_refs"][0]["path"] == "packet.json"
    assert second["current_stage"]["latest_event"]["unchanged_refs"][0]["sha256"] == first["event"]["artifact_refs"][0]["sha256"]


def long_run_packet(**overrides: Any) -> dict[str, Any]:
    packet = {
        "step": "run",
        "task_id": "task-long-run",
        "execution_status": "running",
        "long_run_branch": True,
        "long_run_role": "monitor",
        "event_kind": "long_run_monitor",
        "run_id": "run-long-1",
        "owner_task_id": "task-long-run",
        "launch_cycle_id": "cycle-long-1",
        "command_argv": ["python", "runner.py", "--output-dir", ".task/run/long"],
        "workdir": ".",
        "output_dir": ".task/run/long",
        "log_path": ".task/run/long/run.log",
        "startup_or_heartbeat_evidence": "heartbeat observed",
        "monitor_command": "python monitor.py --run-json .task/run/long/run.json",
        "stop_command": "tmux kill-session -t run-long-1",
        "remaining_validation": "harvest terminal report and validate scalars",
        "expected_completion_signal": "terminal_report.json exists",
        "expected_completion_artifacts": [".task/run/long/terminal_report.json"],
        "session_id": "tmux:run-long-1",
        "evidence_paths": [".agent_log/run-long.md"],
    }
    packet.update(overrides)
    return packet


def test_result_contract_blocks_incomplete_long_run_branch() -> None:
    packet = long_run_packet(run_id="", expected_completion_artifacts=[])

    result = result_contract.validate("run", packet, "block")

    codes = {finding.get("code") for finding in result["findings"]}
    assert result["status"] == "block"
    assert "long_run_detail_missing" in codes


def test_result_contract_accepts_complete_long_run_running_packet() -> None:
    result = result_contract.validate("run", long_run_packet(), "block")

    codes = {finding.get("code") for finding in result["findings"]}
    assert "long_run_detail_missing" not in codes
    assert "running_detail_missing" not in codes


def test_monitor_running_execution_detects_completed_pending_validation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        log_path = root / "run.log"
        done_path = root / "terminal_report.json"
        log_path.write_text("heartbeat\n", encoding="utf-8")
        done_path.write_text("{}", encoding="utf-8")
        args = argparse.Namespace(
            pid=None,
            log_path=str(log_path),
            monitor_command="monitor",
            stop_command="stop",
            heartbeat="heartbeat",
            remaining_validation="validate terminal report",
            run_id="run-long-1",
            task_id="task-long-run",
            launch_cycle_id="cycle-long-1",
            long_run_branch=True,
            long_run_role="monitor",
            event_kind="long_run_monitor",
            output_dir=str(root),
            command_arg=["python", "runner.py", "--output-dir", str(root)],
            workdir=str(root),
            expected_completion_signal="terminal_report.json exists",
            expected_completion_path=[str(done_path)],
            tmux_session="run-long-1",
            tmux_window=None,
            tmux_pane=None,
        )

        result = monitor_running_execution.monitor({}, args)

    assert result["status"] == "completed_pending_validation"
    assert result["completion_artifacts"][0]["exists"] is True


def test_validate_transition_blocks_pending_long_run_derive() -> None:
    stage = {"events": [long_run_packet()]}

    result = validate_cycle_transition.validate({}, stage, "pre_derive")

    codes = {finding.get("code") for finding in result["findings"]}
    assert result["status"] == "block"
    assert "long_run_pending_final_output_phase" in codes


def test_cycle_ledger_accepts_long_run_monitor_as_run_step() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = cycle_ledger.append_event(
            root,
            "cycle-long-1",
            {
                "step": "run",
                "status": "partial",
                "execution_status": "running",
                "event_kind": "long_run_monitor",
                "long_run_branch": True,
                "long_run_role": "monitor",
            },
        )

    assert result["event"]["step"] == "run"
    assert result["event"]["event_kind"] == "long_run_monitor"
    assert "noncanonical_step" not in result["event"]


def main() -> int:
    test_task_pack_scope_fidelity_blocks_diluted_consumed_item()
    test_task_pack_scope_fidelity_allows_explicit_descope_with_open_residual()
    test_task_pack_blocks_consumed_item_with_required_verifier_not_evaluated()
    test_task_pack_blocks_coupled_verifier_pass_as_consumed()
    test_task_pack_blocks_producer_attested_consumed_progress()
    test_terminal_outcome_family_fallback_groups_mutating_blockers()
    test_adapter_mandate_blocks_missing_adapter_stall_chain()
    test_registered_adapter_load_failure_routes_wiring_defect()
    test_cumulative_chain_overrides_untried_veto_after_quality_stall()
    test_chain_stall_forces_actionable_ladder_task_kind()
    test_repo_owned_source_provenance_rejects_nonactionable_self_report()
    test_reachability_and_metric_validity_gates_are_conservative()
    test_evaluate_applies_target_required_verifier_adapter_contract()
    test_terminal_recheck_escalates_to_user_input()
    test_supplied_input_delta_prevents_terminal_escalation()
    test_result_contract_blocks_label_only_goal_productive_task_kind()
    test_result_contract_blocks_derive_goal_productive_from_part_f_failures()
    test_result_contract_blocks_loopback_part_f_misrouting()
    test_result_contract_blocks_validate_completion_from_part_f_failures()
    test_safe_failure_autopsy_records_stage_and_diagnostics_unavailable()
    test_loopback_stage_contradiction_blocks_counting()
    test_loopback_uses_failure_surface_count_key_and_forces_instrumentation_option()
    test_loopback_downgrades_independent_when_verification_source_overlaps()
    test_task_pack_blocks_independent_verified_without_source_separation()
    test_result_contract_blocks_part_h_misrouting()
    test_cycle_ledger_records_unchanged_ref_for_duplicate_artifact()
    test_result_contract_blocks_incomplete_long_run_branch()
    test_result_contract_accepts_complete_long_run_running_packet()
    test_monitor_running_execution_detects_completed_pending_validation()
    test_validate_transition_blocks_pending_long_run_derive()
    test_cycle_ledger_accepts_long_run_monitor_as_run_step()
    print("loopback guard contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
