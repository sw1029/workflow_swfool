#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
ORCHESTRATE_ROOT = SCRIPT_PATH.parents[1]
SKILLS_ROOT = ORCHESTRATE_ROOT.parent
for package_root in (
    ORCHESTRATE_ROOT / "scripts",
    SKILLS_ROOT / "audit-cycle-loopback" / "scripts",
    SKILLS_ROOT / "run-task-code-and-log" / "scripts",
    SKILLS_ROOT / "manage-task-state-index" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

import audit_cycle_loopback as anti_loop_gate_provider  # noqa: E402
from manage_task_state_index import index as task_state_index  # noqa: E402
from orchestrate_task_cycle import code_structure_audit  # noqa: E402
from orchestrate_task_cycle import cycle_ledger  # noqa: E402
from orchestrate_task_cycle import monitor_running_execution  # noqa: E402
from orchestrate_task_cycle import profile_cycle_efficiency  # noqa: E402
from orchestrate_task_cycle import validate_cycle_transition  # noqa: E402
from orchestrate_task_cycle.progress import api as detect_progress_loop  # noqa: E402
from orchestrate_task_cycle.result_contract import api as result_contract  # noqa: E402
from orchestrate_task_cycle.task_pack import api as task_pack_queue  # noqa: E402
from run_task_code_and_log import safe_failure_autopsy  # noqa: E402


def bind_exact_artifact(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    artifact_path = root / "artifact_A.json"
    artifact_path.write_text('{"artifact_id":"artifact_A"}\n', encoding="utf-8")
    artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    artifact_ref = {
        "artifact_id": "artifact_A",
        "artifact_class": str(args.artifact_family),
        "artifact_path_or_store_ref": artifact_path.name,
        "artifact_sha256": artifact_sha256,
        "production_lane_identity": "lane_L",
    }
    args.artifact_path = [artifact_path.name]
    args.artifact_ref_json = json.dumps(artifact_ref, sort_keys=True)
    return artifact_ref


def base_pack(items: list[dict[str, Any]]) -> dict[str, Any]:
    pack = {
        "schema_version": 1,
        "pack_id": "pack-test",
        "status": "active",
        "goal": "Test pack.",
        "current_item_id": None,
        "items": items,
        "mutation_log": [],
    }
    task_pack_queue.refresh_current_item(pack)
    return pack


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

    unrelated_provenance_codes = {
        "promotion_provenance_missing",
        "completion_provenance_missing",
    }
    assert not any(
        finding.get("severity") == "block" and finding.get("code") not in unrelated_provenance_codes
        for finding in findings
    )


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

        bind_exact_artifact(root, args)
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

        bind_exact_artifact(root, args)
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


def hook_demand_args(root: Path, cycle_id: str, *, domain_adapter: Path | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        root=str(root),
        cycle_id=cycle_id,
        task_id="task-hook-demand",
        artifact_family="primary_output",
        semantic_signature="same_root",
        root_key="same_root",
        domain_adapter=str(domain_adapter) if domain_adapter else None,
        provider_request_count=0,
        artifact_path=[],
        artifact_paths_json=None,
        changed_file=[],
        changed_files_json=None,
        gate_state_json=[],
        recent_progress_json=None,
        runner_validation_json=None,
        output_delta_json=json.dumps({"changed_vs_previous": False, "semantic_progress": False}),
        failure_autopsy_json=[],
        substance_metrics_json=None,
        corrective_resolution_json=None,
        facet_root_map_json=None,
        acceptance_reachability_json=json.dumps({"target": "abstract_target"}),
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
        instrumentation_trigger_threshold=2,
        envelope_thaw_streak_cap=2,
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


def write_hook_demand_adapter(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "def quality_vector(**kwargs):",
                "    return {'quality_vector': {'quality_score': 1, 'current_output_fingerprint': 'fp-hook-demand'}}",
                "def quality_delta_policy(**kwargs):",
                "    return {'keys': ['quality_score']}",
                "",
                "def substance_metrics(**kwargs):",
                "    return {'substance_metrics': {'primary_output_rows': 1}}",
                "",
                "def facet_root_map(**kwargs):",
                "    return {'same_root': 'same_root'}",
                "",
                "def hook_demand_threshold(**kwargs):",
                "    return 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_hook_demand_no_adapter_is_noop() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        anti_loop_gate_provider._DOMAIN_ADAPTER_MODULE = None
        packet, _, _ = anti_loop_gate_provider.evaluate(hook_demand_args(root, "cycle-hook-noop"))

    assert "adapter_hook_demand" not in packet
    assert "hook_supply_required" not in packet
    assert "demanded_hooks" not in packet
    assert not any(
        finding.get("code") in {"adapter_hook_demand", "hook_supply_required"}
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )


def test_hook_demand_single_skip_warns_without_supply_required() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = root / "domain_adapter.py"
        write_hook_demand_adapter(adapter)
        anti_loop_gate_provider._DOMAIN_ADAPTER_MODULE = None
        packet, _, _ = anti_loop_gate_provider.evaluate(
            hook_demand_args(root, "cycle-hook-one", domain_adapter=adapter)
        )

    demand = packet["adapter_hook_demand"]
    assert demand == [
        {
            "hook_id": "target_required_verifier",
            "skip_count": 1,
            "decision_relevant_skip_count": 1,
            "affected_gate_ids": ["acceptance_reachability_gate"],
            "first_skip_cycle_id": "cycle-hook-one",
            "last_skip_cycle_id": "cycle-hook-one",
        }
    ]
    assert packet["adapter_mandate_gate"]["status"] == "warn"
    assert packet["hook_supply_required"] is False
    assert packet["demanded_hooks"] == []
    assert any(
        finding.get("code") == "adapter_hook_demand"
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    )


def test_hook_demand_two_decision_relevant_skips_emit_supply_required() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        registry = root / ".task" / "anti_loop" / "family_progress_registry.jsonl"
        adapter = root / "domain_adapter.py"
        write_hook_demand_adapter(adapter)

        anti_loop_gate_provider._DOMAIN_ADAPTER_MODULE = None
        _, rows, should_write = anti_loop_gate_provider.evaluate(
            hook_demand_args(root, "cycle-hook-one", domain_adapter=adapter)
        )
        assert should_write is True
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
                for row in rows
            ),
            encoding="utf-8",
        )

        anti_loop_gate_provider._DOMAIN_ADAPTER_MODULE = None
        packet, _, _ = anti_loop_gate_provider.evaluate(
            hook_demand_args(root, "cycle-hook-two", domain_adapter=adapter)
        )

    demand = packet["adapter_hook_demand"]
    assert demand[0]["hook_id"] == "target_required_verifier"
    assert demand[0]["skip_count"] == 2
    assert demand[0]["decision_relevant_skip_count"] == 2
    assert demand[0]["first_skip_cycle_id"] == "cycle-hook-one"
    assert demand[0]["last_skip_cycle_id"] == "cycle-hook-two"
    assert packet["hook_supply_required"] is True
    assert packet["demanded_hooks"] == ["target_required_verifier"]
    assert any(
        finding.get("code") == "hook_supply_required"
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
                        "    ref = kwargs.get('decision_artifact_ref') or {}",
                        "    return {'quality_vector': {'quality_score': 0, 'current_output_fingerprint': 'fp-current', 'artifact_id': ref.get('artifact_id'), 'artifact_sha256': ref.get('artifact_sha256')}}",
                        "def quality_delta_policy(**kwargs):",
                        "    return {'keys': ['quality_score']}",
                        "def previous_accepted_fp(**kwargs):",
                        "    return {'previous_accepted_fp': 'fp-prior', 'previous_quality_vector': {'quality_score': 0}}",
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

        bind_exact_artifact(root, args)
        packet, _, _ = anti_loop_gate_provider.evaluate(args)

    assert packet["cumulative_goal_distance_stalled"] is True
    assert packet["cumulative_goal_distance_stall_streak"] == 3
    assert packet["untried_actionable_root_cause_exists"] is True
    assert packet["cumulative_untried_chain_without_quality_delta"] is True
    assert packet["untried_veto_overridden_by_chain_stall"] is True
    assert packet["terminal_blocked_invalid_due_to_untried_root_cause"] is False
    assert packet["effective_allowed_dispositions"] == ["goal_productive"]
    assert packet["goal_terminal_prohibited"] is True
    assert packet["offline_scope_unverified"] is True


def test_chain_stall_forces_actionable_ladder_task_kind() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = root / "domain_adapter.py"
        adapter.write_text(
            "\n".join(
                [
                        "def quality_vector(**kwargs):",
                        "    ref = kwargs.get('decision_artifact_ref') or {}",
                        "    return {'quality_vector': {'quality_score': 0, 'current_output_fingerprint': 'fp-current', 'artifact_id': ref.get('artifact_id'), 'artifact_sha256': ref.get('artifact_sha256')}}",
                        "def quality_delta_policy(**kwargs):",
                        "    return {'keys': ['quality_score']}",
                        "def previous_accepted_fp(**kwargs):",
                        "    return {'previous_accepted_fp': 'fp-prior', 'previous_quality_vector': {'quality_score': 0}}",
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
        bind_exact_artifact(root, args)
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
                        "    ref = kwargs.get('decision_artifact_ref') or {}",
                        "    return {'quality_vector': {'quality_score': 0, 'current_output_fingerprint': 'fp-current', 'artifact_id': ref.get('artifact_id'), 'artifact_sha256': ref.get('artifact_sha256')}}",
                        "def quality_delta_policy(**kwargs):",
                        "    return {'keys': ['quality_score']}",
                        "def previous_accepted_fp(**kwargs):",
                        "    return {'previous_accepted_fp': 'fp-prior', 'previous_quality_vector': {'quality_score': 0}}",
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
        bind_exact_artifact(root, args)
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
                    "    return {'quality_vector': {'quality_score': 0, 'current_output_fingerprint': 'fp-current'}}",
                    "def quality_delta_policy(**kwargs):",
                    "    return {'keys': ['quality_score']}",
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


def test_loopback_result_contract_requires_an_evaluated_same_family_budget() -> None:
    base = {
        "task_id": "task-A",
        "cycle_id": "cycle-A",
        "family_key": "family-A",
        "changed_vs_previous": False,
        "semantic_progress": False,
        "same_family_micro_hardening_count": 7,
        "recommended_disposition": "prefer_primary_artifact",
        "hard_stop_required": False,
        "evidence_class": "direct",
        "evidence_paths": ["evidence-A"],
    }
    unverified = result_contract.validate("loopback_audit", base, "block")
    evaluated = result_contract.validate(
        "loopback_audit",
        {
            **base,
            "same_family_nonsemantic_budget": 2,
            "same_family_budget_evaluation": {
                "budget_id": "same_family_nonsemantic_attempts",
                "budget_value": 2,
                "budget_evaluation_status": "evaluated",
                "source": "caller_configuration",
                "reason_code": "budget_supplied",
            },
        },
        "block",
    )

    assert "loopback_streak_without_hard_stop" not in {
        item.get("code") for item in unverified["findings"]
    }
    assert "loopback_streak_without_hard_stop" in {
        item.get("code") for item in evaluated["findings"]
    }
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

        bind_exact_artifact(root, args)
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
        cycle_ledger.init_cycle(root, "cycle-1", "task-1", "test")
        cycle_ledger.append_event(
            root,
            "cycle-1",
            {"step": "context", "status": "complete", "task_id": "task-1"},
        )
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
        cycle_ledger.init_cycle(root, "cycle-long-1", "task-long-run", "test")
        cycle_ledger.append_event(
            root,
            "cycle-long-1",
            {"step": "context", "status": "complete", "task_id": "task-long-run"},
        )
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


def validate_packet(**overrides: Any) -> dict[str, Any]:
    packet = {
        "step": "validate",
        "task_id": "task-forward",
        "validation_verdict": "complete",
        "progress_verdict": "advanced",
        "authoritative_progress_verdict": "advanced",
        "changed_vs_previous": True,
        "semantic_progress": True,
        "produced_domain_delta": True,
        "blockers": [],
        "evidence_paths": ["validation.json"],
    }
    packet.update(overrides)
    return packet


def test_fixture_only_movement_cannot_satisfy_real_artifact() -> None:
    result = result_contract.validate(
        "validate",
        validate_packet(required_artifact_class="real_artifact", observed_artifact_class="fixture"),
        "block",
    )
    assert any(item.get("code") == "validate_required_artifact_class_mismatch" for item in result["findings"])
    nonadvanced = result_contract.validate(
        "validate",
        validate_packet(
            progress_verdict="safety_only",
            authoritative_progress_verdict="safety_only",
            required_artifact_class="real_artifact",
            observed_artifact_class="fixture",
        ),
        "block",
    )
    assert any(item.get("code") == "validate_complete_required_artifact_class_mismatch" for item in nonadvanced["findings"])


def test_actual_artifact_report_body_divergence_blocks_close() -> None:
    result = result_contract.validate(
        "validate",
        validate_packet(
            actual_body_truth_required=True,
            truth_basis="independently_recomputed_actual_artifact",
            report_body_divergence=True,
        ),
        "block",
    )
    assert any(item.get("code") == "report_body_divergence" for item in result["findings"])
    automatic = result_contract.validate(
        "validate",
        validate_packet(
            body_projection_fingerprint="a" * 64,
            actual_artifact={"metric_M": 1},
            validation_report={"body_projection_fingerprint": "a" * 64, "metric_M": 2},
        ),
        "block",
    )
    assert any(item.get("code") == "report_body_divergence" for item in automatic["findings"])


def test_metadata_only_delta_cannot_advance() -> None:
    result = result_contract.validate(
        "validate",
        validate_packet(metadata_only=True, produced_domain_delta=False, semantic_progress=False),
        "block",
    )
    assert any(item.get("code") == "validate_advanced_without_terminal_outcome_changed" for item in result["findings"])
    contradictory = result_contract.validate(
        "validate",
        validate_packet(metadata_only=True, produced_domain_delta=True, semantic_progress=True),
        "block",
    )
    assert any(item.get("code") == "validate_advanced_from_metadata_only_delta" for item in contradictory["findings"])


def test_downstream_cannot_upgrade_loopback_false_or_hard_stop() -> None:
    result = result_contract.validate(
        "validate",
        validate_packet(authoritative_semantic_progress=False, hard_stop_required=True),
        "block",
    )
    codes = {item.get("code") for item in result["findings"]}
    assert "validate_progress_monotonicity_violation" in codes
    assert "validate_advanced_despite_hard_stop" in codes


def test_root_import_does_not_satisfy_failed_consumer_context() -> None:
    result = result_contract.validate(
        "validate",
        validate_packet(
            required_consumer_ids=["runtime-loader"],
            consumer_context_conformance={
                "rows": [{
                    "consumer_context_id": "runtime-loader",
                    "adapter_loaded": False,
                    "required_hook_callable": False,
                    "hook_signature_compatible": False,
                    "return_contract_valid": False,
                    "probe_evidence_id": "probe-runtime-failed",
                    "repository_root_import_succeeded": True,
                }]
            },
        ),
        "block",
    )
    assert any(item.get("code") == "required_consumer_context_not_evaluated" for item in result["findings"])


def test_terminal_request_with_local_residual_is_prohibited() -> None:
    gate = anti_loop_gate_provider.terminal_self_resolution_gate(
        {"terminal_requested": True, "residuals": [{"residual_id": "r1", "classification": "self_resolvable_local"}]}
    )
    assert gate["goal_terminal_prohibited"] is True
    assert gate["status"] == "block"


def test_repeated_terminal_tuple_latches_without_full_cycle() -> None:
    previous = {
        "event_id": "terminal-1",
        "terminal_justified": True,
        "terminal_outcome_family_key": "family-a",
        "input_state_fingerprint": "input-a",
        "authority_state_fingerprint": "authority-a",
        "terminal_latch_streak": 1,
    }
    current = dict(previous, event_id="terminal-2")
    state = cycle_ledger.terminal_latch_state([previous], current)
    assert state["quiescent_terminal_latched"] is True
    assert state["suppress_full_cycle"] is True
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cycle_ledger.init_cycle(root, "cycle-terminal", "task-terminal", "test")
        cycle_ledger.append_event(
            root,
            "cycle-terminal",
            {"step": "context", "status": "complete", "task_id": "task-terminal"},
        )
        first = cycle_ledger.append_event(root, "cycle-terminal", {**previous, "step": "report", "status": "complete"})
        second = cycle_ledger.append_event(root, "cycle-terminal", {**current, "step": "report", "status": "complete"})
        rows = cycle_ledger.read_events(root, "cycle-terminal")
        restart = cycle_ledger.init_cycle(root, "cycle-terminal-restart", "task-terminal", "restart", current)
        restart_dir_exists = (root / ".task" / "cycle" / "cycle-terminal-restart").exists()
    assert first.get("event_suppressed") is not True
    assert second["event_suppressed"] is True
    assert len(rows) == 3
    assert rows[-1]["event_kind"] == "terminal_latch_observation"
    assert rows[-1]["compact_observation"] is True
    assert rows[-1]["unchanged_terminal_ref"] == rows[-2]["event_id"]
    assert restart["cycle_suppressed"] is True
    assert not restart_dir_exists


def test_mutable_alias_change_preserves_immutable_history() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "task.md").write_text("# First\n", encoding="utf-8")
        first = task_state_index.upsert_item(root, "task", "task.md", "active")
        (root / "task.md").write_text("# Second\n", encoding="utf-8")
        second = task_state_index.upsert_item(root, "task", "task.md", "active")
        audit = task_state_index.audit_index(root)
        first_snapshot_body = (root / ".task" / "snapshots" / f"{first['id']}.md").read_text(encoding="utf-8")
    assert first["id"] != second["id"]
    assert second["lifecycle_transition_result"]["atomic"] is True
    assert not any(item.get("code") == "digest_mismatch" and first["id"] in item.get("ids", []) for item in audit["issues"])
    assert first_snapshot_body == "# First\n"


def test_trace_label_variants_share_family_profile_scope() -> None:
    shared = {
        "goal_axis": "quality",
        "producer_lineage": "producer-main",
        "artifact_class": "real-artifact",
        "current_decision_lane": "production",
        "input_cohort": "cohort-a",
    }
    events = [
        {**shared, "event_id": "outside", "root_family_key": "other", "goal_axis": "other"},
        {**shared, "event_id": "e1", "root_family_key": "root-run-1", "hypothesis_exhausted": True},
        {**shared, "event_id": "e2", "root_family_key": "root-run-2"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        profile = profile_cycle_efficiency.analyze(Path(tmp), events, [])
    assert profile["profile_scope_unverified"] is False
    assert profile["family_scoped_event_count"] == 2
    assert profile["hypothesis_exhausted"] is True
    assert profile["cycle_fixed_cost"] == 2


def test_exact_artifact_precedence_and_incompatible_gate_are_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifact_a = root / "artifact_A.json"
        artifact_b = root / "artifact_B.json"
        artifact_a.write_text('{"value":"A"}\n', encoding="utf-8")
        artifact_b.write_text('{"value":"B"}\n', encoding="utf-8")
        artifact_a_sha = hashlib.sha256(artifact_a.read_bytes()).hexdigest()
        paths, selected = anti_loop_gate_provider.load_artifact_selection(
            root,
            json.dumps({"artifacts": [{"artifact_path_or_store_ref": artifact_b.name}]}),
            [artifact_a.name],
            artifact_ref_json=json.dumps(
                {
                    "artifact_id": "artifact_A",
                    "artifact_class": "family_F",
                    "artifact_path_or_store_ref": artifact_a.name,
                    "artifact_sha256": artifact_a_sha,
                    "production_lane_identity": "lane_L",
                }
            ),
            artifact_family="family_F",
        )
        compatibility = anti_loop_gate_provider.gate_artifact_compatibility_result(
            None,
            "gate_G",
            selected,
            {"required_artifact_class": "other_family"},
        )
        applied = anti_loop_gate_provider.apply_gate_artifact_compatibility(
            {"hard_stop_required": True, "constrains_disposition": True, "quality_delta_pass": True},
            compatibility,
            pass_fields=("quality_delta_pass",),
        )
        store_ref = f"sha256:{artifact_a_sha}"
        _store_paths, store_selected = anti_loop_gate_provider.load_artifact_selection(
            root,
            None,
            [],
            artifact_ref_json=json.dumps(
                {
                    "artifact_id": "artifact_A",
                    "artifact_class": "family_F",
                    "artifact_path_or_store_ref": store_ref,
                    "artifact_sha256": artifact_a_sha,
                    "production_lane_identity": "lane_L",
                }
            ),
            artifact_family="family_F",
        )
        list_paths, _list_selected = anti_loop_gate_provider.load_artifact_selection(
            root,
            json.dumps([{"artifact_path_or_store_ref": artifact_b.name}]),
            [],
            artifact_family="family_F",
        )

    assert paths == [artifact_a]
    assert selected["scope_verified"] is True
    assert selected["artifact_id"] == "artifact_A"
    assert selected["conflicting_discovery_paths"] == [artifact_b.name]
    assert compatibility["gate_compatibility_status"] == "incompatible"
    assert applied["decision_contribution_allowed"] is False
    assert applied["hard_stop_required"] is False
    assert applied["constrains_disposition"] is False
    assert applied["quality_delta_pass"] is False
    assert store_selected["scope_verified"] is True
    assert store_selected["artifact_path_or_store_ref"] == store_ref
    assert list_paths == [artifact_b]


def test_consumer_receipts_require_strict_signature_union_and_decision_consumption() -> None:
    artifact_ref = {
        "artifact_id": "artifact_A",
        "artifact_class": "family_F",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "lane_L",
        "body_projection_fingerprint": "c" * 64,
        "verification_input_ids": ["source_cohort_C"],
        "scope_verified": True,
    }

    def zero_arg_compatibility() -> dict[str, Any]:
        return {"compatible": True, "artifact_id": "artifact_A", "artifact_sha256": "a" * 64}

    compatibility = anti_loop_gate_provider.gate_artifact_compatibility_result(
        types.SimpleNamespace(gate_artifact_compatibility=zero_arg_compatibility),
        "gate_G",
        artifact_ref,
        {},
    )
    valid = {
        "consumer_context_id": "hook_H",
        "cycle_id": "cycle_C",
        "input_state_fingerprint": "b" * 64,
        "attempt_identity": "attempt_A",
        "adapter_loaded": True,
        "hook_resolved": True,
        "required_hook_callable": True,
        "hook_signature_compatible": True,
        "invocation_completed": True,
        "return_contract_valid": True,
        "artifact_identity_echo_valid": True,
        "artifact_id": "artifact_A",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "lane_L",
        "body_projection_fingerprint": "c" * 64,
        "verification_input_ids": ["source_cohort_C"],
        "evidence_provenance": "independently_verified",
        "value_consumed_by_decision": True,
        "probe_evidence_ref": "packet:receipt/hook_H",
    }

    def bound(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        digest = anti_loop_gate_provider.consumer_receipt_binding_sha256(result)
        result["probe_evidence_sha256"] = digest
        return result

    valid = bound(valid)
    invalid_consumption = {**valid, "consumer_context_id": "hook_I", "value_consumed_by_decision": False}
    invalid_return = {**valid, "consumer_context_id": "hook_J", "return_contract_valid": False}
    invalid_identity = {**valid, "consumer_context_id": "hook_K", "artifact_identity_echo_valid": False}
    invalid_consumption = bound(invalid_consumption)
    invalid_return = bound(invalid_return)
    invalid_identity = bound(invalid_identity)
    conformance = anti_loop_gate_provider.consumer_context_conformance_gate(
        {"required_consumer_ids": ["hook_H"], "consumer_context_conformance": {"rows": [valid]}},
        {
            "required_consumer_ids": ["hook_I", "hook_J", "hook_K"],
            "consumer_context_conformance": {
                "rows": [invalid_consumption, invalid_return, invalid_identity]
            },
        },
        expected_artifact_ref=artifact_ref,
        expected_cycle_id="cycle_C",
        expected_input_state_fingerprint="b" * 64,
        expected_attempt_identity="attempt_A",
    )

    assert compatibility["gate_compatibility_status"] == "not_evaluated"
    assert compatibility["consumer_invocation_receipt"]["hook_signature_compatible"] is False
    assert conformance["status"] == "not_evaluated"
    assert conformance["missing_consumer_context_ids"] == ["hook_I", "hook_J", "hook_K"]
    assert {row["consumer_context_id"] for row in conformance["rows"]} == {
        "hook_H",
        "hook_I",
        "hook_J",
        "hook_K",
    }


def test_verification_coupling_preserves_self_grounded_and_rejects_identity_overlap() -> None:
    axis_key = anti_loop_gate_provider.normalize_gate_key("axis_A")
    gate, independent, attested, self_grounded = anti_loop_gate_provider.apply_evidence_provenance_filter(
        {"improved_fields": ["axis_A"], "quality_delta_pass": True, "status": "pass"},
        improved_key="improved_fields",
        pass_key="quality_delta_pass",
        provenance={axis_key: "self_grounded"},
        hook_provided=True,
    )
    overlap = anti_loop_gate_provider.verification_source_separation_gate(
        provenance_value={
            "verification_input_ids": ["input_D"],
            "producer_input_ids": ["input_D"],
            "verified_artifact_ids": ["artifact_A"],
            "evidence_provenance": {"axis_A": {"axis_kind": "semantic"}},
        },
        verified_artifact_paths=[],
        independently_verified_fields=["axis_A"],
    )
    structural = anti_loop_gate_provider.verification_source_separation_gate(
        provenance_value={
            "self_grounded_axes": ["axis_A"],
            "evidence_provenance": {
                "axis_A": {
                    "axis_kind": "structural",
                    "axis_scope": "root_local",
                }
            },
        },
        verified_artifact_paths=["artifact_A.json"],
        independently_verified_fields=[],
        self_grounded_fields=["axis_A"],
    )

    assert independent == []
    assert attested == []
    assert self_grounded == ["axis_A"]
    assert gate["quality_delta_pass"] is False
    assert overlap["independent_source_separation_status"] == "overlap"
    assert overlap["verification_identity_overlap_ids"] == ["input_D"]
    assert overlap["verification_axes"][0]["evidence_provenance"] == "producer_attested"
    assert structural["independent_source_separation_status"] == "self_grounded"
    assert structural["verification_axes"][0]["evidence_provenance"] == "self_grounded"
    assert structural["verification_axes"][0]["semantic_axis"] is False


def test_registry_identity_is_content_bound_and_label_correction_is_not_a_new_attempt() -> None:
    fingerprint_a = anti_loop_gate_provider.decision_input_state_fingerprint(
        [{"input_state_fingerprint": "input_D"}],
        {"artifact_sha256": "a" * 64, "production_lane_identity": "lane_L"},
    )
    fingerprint_b = anti_loop_gate_provider.decision_input_state_fingerprint(
        [{"input_state_fingerprint": "input_D"}],
        {"artifact_sha256": "b" * 64, "production_lane_identity": "lane_L"},
    )
    attempt_a = anti_loop_gate_provider.content_bound_attempt_identity(
        "cycle_C", "family_F", "blocker_A", fingerprint_a
    )
    attempt_b = anti_loop_gate_provider.content_bound_attempt_identity(
        "cycle_C", "family_F", "blocker_A", fingerprint_b
    )
    corrected = anti_loop_gate_provider.compact_registry(
        [
            {"attempt_identity": attempt_a, "family_key": "family_old", "cycle_id": "cycle_C"},
            {"attempt_identity": attempt_a, "family_key": "family_corrected", "cycle_id": "cycle_C"},
        ],
        10,
    )
    original_root_cause = {
        "attempt_identity": attempt_a,
        "cycle_id": "cycle_C",
        "family_key": "family_old",
        "root_key": "root_A",
        "root_family_key": "root_A",
        "hypothesized_root_cause": "cause_A",
        "target_surface": "surface_A",
        "observed_delta_class": "no_delta",
        "repair_attempted": True,
        "attempt_count": 1,
        "vacuous_attempt_count": 1,
    }
    durable_rows = anti_loop_gate_provider.compact_root_cause_ledger(
        [original_root_cause, {**original_root_cause, "family_key": "family_corrected"}],
        10,
    )
    durable_changed = durable_rows != [original_root_cause]

    assert fingerprint_a != fingerprint_b
    assert attempt_a != attempt_b
    assert len(corrected) == 1
    assert corrected[0]["registry_label_correction"] is True
    assert corrected[0]["correction_of_attempt_identity"] == attempt_a
    assert durable_changed is True
    assert durable_rows[-1]["label_correction"] is True
    assert sum(int(row.get("attempt_count") or 0) for row in durable_rows) == 1


def test_scope_unverified_profile_preserves_cost_without_global_hard_gate() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scripts = root / "scripts"
        scripts.mkdir()
        (scripts / "surface.py").write_text(
            "\n".join(f"build-packet-v{index}-contract" for index in range(1, 14)) + "\n",
            encoding="utf-8",
        )
        events = [
            {
                "event_id": f"event_{index}",
                "progress_verdict": "safety_only",
                "progress_kind": "governance_only",
                "metadata_only": True,
            }
            for index in range(3)
        ]
        profile = profile_cycle_efficiency.analyze(root, events, [])

    assert profile["profile_scope_unverified"] is True
    assert profile["family_scoped_event_count"] == 0
    assert profile["cycle_fixed_cost"] == 3
    assert profile["command_surface_budget"]["budget_exceeded"] is True
    assert profile["command_surface_budget"]["decision_scope"] == "global_dashboard"
    assert profile["command_surface_budget"]["hard_gate"] is False
    assert profile["command_surface_budget"]["constrains_current_family"] is False
    assert detect_progress_loop.gate_constrains_disposition(
        "command_surface_budget", profile["command_surface_budget"]
    ) is False
    assert "goal_productive" in detect_progress_loop.gate_allowed_dispositions(
        "command_surface_budget", profile["command_surface_budget"]
    )
    assert not any(item["code"] == "consecutive_safety_only" for item in profile["findings"])


def test_family_scoped_profile_does_not_inherit_other_family_streak() -> None:
    shared = {
        "goal_axis": "axis_A",
        "producer_lineage": "producer_A",
        "artifact_class": "family_F",
        "current_decision_lane": "lane_L",
        "input_cohort": "input_D",
    }
    events = [
        {**shared, "event_id": "event_A", "root_family_key": "family_A", "progress_verdict": "safety_only"},
        {**shared, "event_id": "event_B", "root_family_key": "family_A", "progress_verdict": "safety_only"},
        {**shared, "event_id": "event_C", "root_family_key": "family_B", "progress_verdict": "advanced"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        profile = profile_cycle_efficiency.analyze(Path(tmp), events, [])

    assert profile["profile_scope_unverified"] is False
    assert profile["family_scoped_event_count"] == 1
    assert profile["progress_counts"] == {"advanced": 1}
    assert not any(item["code"] == "consecutive_safety_only" for item in profile["findings"])


def test_hash_bound_handoff_requires_body_match_explicit_echo_and_reasoned_not_applicable() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        packet_path = root / "packet_K.json"
        packet = {
            "decision_contract_version": 1,
            "artifact_id": "artifact_A",
            "artifact_sha256": "a" * 64,
            "artifact_family": "family_F",
            "blocker_signature": "blocker_A",
            "progress_verdict": "stalled",
            "hard_stop_required": False,
            "terminal_state": "conservative_hold",
            "allowed_next_action_classes": ["conservative_hold"],
        }
        packet_path.write_text(json.dumps(packet, sort_keys=True) + "\n", encoding="utf-8")
        packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        handoff = {
            "handoff_contract_version": 1,
            "applicability": "required",
            "packet_ref": packet_path.name,
            "packet_sha256": packet_sha,
            "artifact_id": "artifact_A",
            "artifact_sha256": "a" * 64,
            "artifact_family": "family_F",
            "blocker_signature": "blocker_A",
            "progress_verdict": "stalled",
            "hard_stop": False,
            "terminal_state": "conservative_hold",
            "allowed_next_action_classes": ["conservative_hold"],
        }
        result = {
            "workspace_root": str(root),
            "decision_contract_version": 1,
            "decision_artifact_ref": {
                "artifact_id": "artifact_A",
                "artifact_class": "family_F",
                "artifact_sha256": "a" * 64,
                "production_lane_identity": "lane_L",
                "discovery_basis": "explicit_artifact_ref",
                "scope_verified": True,
            },
            "anti_loop_handoff": handoff,
            "consumed_anti_loop_packet_sha256": packet_sha,
            "progress_verdict": "stalled",
        }
        valid = result_contract.validate("derive", result, "block")
        missing_echo = result_contract.validate(
            "derive",
            {key: value for key, value in result.items() if key != "consumed_anti_loop_packet_sha256"},
            "block",
        )
        packet_path.write_text(json.dumps({**packet, "progress_verdict": "advanced"}) + "\n", encoding="utf-8")
        tampered = result_contract.validate("derive", result, "block")
        missing = result_contract.validate(
            "derive",
            {
                "governed_transition": True,
                "decision_contract_version": 0,
                "progress_verdict": "stalled",
            },
            "block",
        )
        standalone = result_contract.validate(
            "derive",
            {
                "derive_mode": "initial_init",
                "decision_contract_version": 0,
                "anti_loop_handoff": {
                    "handoff_contract_version": 1,
                    "applicability": "not_applicable",
                    "applicability_reason": "initial transition has no prior loopback packet",
                },
            },
            "block",
        )

    valid_codes = {item["code"] for item in valid["findings"]}
    assert not any(code.startswith("derive_anti_loop_handoff") for code in valid_codes)
    assert any(item["code"] == "derive_anti_loop_handoff_echo_mismatch" for item in missing_echo["findings"])
    assert any(item["code"] == "derive_anti_loop_handoff_hash_mismatch" for item in tampered["findings"])
    assert any(item["code"] == "derive_anti_loop_handoff_missing" for item in missing["findings"])
    assert not any(item["code"] == "derive_anti_loop_not_applicable_invalid" for item in standalone["findings"])


def main() -> int:
    test_task_pack_scope_fidelity_blocks_diluted_consumed_item()
    test_task_pack_scope_fidelity_allows_explicit_descope_with_open_residual()
    test_task_pack_blocks_consumed_item_with_required_verifier_not_evaluated()
    test_task_pack_blocks_coupled_verifier_pass_as_consumed()
    test_task_pack_blocks_producer_attested_consumed_progress()
    test_terminal_outcome_family_fallback_groups_mutating_blockers()
    test_adapter_mandate_blocks_missing_adapter_stall_chain()
    test_registered_adapter_load_failure_routes_wiring_defect()
    test_hook_demand_no_adapter_is_noop()
    test_hook_demand_single_skip_warns_without_supply_required()
    test_hook_demand_two_decision_relevant_skips_emit_supply_required()
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
    test_fixture_only_movement_cannot_satisfy_real_artifact()
    test_actual_artifact_report_body_divergence_blocks_close()
    test_metadata_only_delta_cannot_advance()
    test_downstream_cannot_upgrade_loopback_false_or_hard_stop()
    test_root_import_does_not_satisfy_failed_consumer_context()
    test_terminal_request_with_local_residual_is_prohibited()
    test_repeated_terminal_tuple_latches_without_full_cycle()
    test_mutable_alias_change_preserves_immutable_history()
    test_trace_label_variants_share_family_profile_scope()
    test_exact_artifact_precedence_and_incompatible_gate_are_fail_closed()
    test_consumer_receipts_require_strict_signature_union_and_decision_consumption()
    test_verification_coupling_preserves_self_grounded_and_rejects_identity_overlap()
    test_registry_identity_is_content_bound_and_label_correction_is_not_a_new_attempt()
    test_scope_unverified_profile_preserves_cost_without_global_hard_gate()
    test_family_scoped_profile_does_not_inherit_other_family_streak()
    test_hash_bound_handoff_requires_body_match_explicit_echo_and_reasoned_not_applicable()
    print("loopback guard contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
