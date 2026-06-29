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
    test_terminal_recheck_escalates_to_user_input()
    test_supplied_input_delta_prevents_terminal_escalation()
    print("loopback guard contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
