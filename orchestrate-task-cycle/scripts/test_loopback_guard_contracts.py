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
anti_loop_gate_provider = load_module(
    SKILLS_ROOT / "audit-cycle-loopback" / "scripts" / "anti_loop_gate_provider.py"
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

    assert reachability["reachability_verdict"] == "unreachable"
    assert reachability["relaxation_or_escalation_required"] is True
    assert metric_validity["metric_goal_productive_excluded"] is True
    assert missing_metric_validity["status"] == "not_provided"
    assert missing_metric_validity["constrains_disposition"] is False


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


def main() -> int:
    test_terminal_outcome_family_fallback_groups_mutating_blockers()
    test_adapter_mandate_blocks_missing_adapter_stall_chain()
    test_cumulative_chain_overrides_untried_veto_after_quality_stall()
    test_repo_owned_source_provenance_rejects_nonactionable_self_report()
    test_reachability_and_metric_validity_gates_are_conservative()
    test_terminal_recheck_escalates_to_user_input()
    test_supplied_input_delta_prevents_terminal_escalation()
    print("loopback guard contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
