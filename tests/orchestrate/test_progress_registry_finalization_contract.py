from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


sys.dont_write_bytecode = True
SKILLS_ROOT = Path(__file__).resolve().parents[2]
SUBPROCESS_ENV = {
    **os.environ,
    "PYTHONPATH": os.pathsep.join(
        [
            str(SKILLS_ROOT / "orchestrate-task-cycle" / "scripts"),
            str(SKILLS_ROOT / "record-agent-work-log" / "scripts"),
        ]
    ),
}

from orchestrate_task_cycle import cycle_ledger  # noqa: E402
from orchestrate_task_cycle.progress.analysis import analyze  # noqa: E402
from orchestrate_task_cycle.progress.constants import REGISTRY_REL_PATH  # noqa: E402
from orchestrate_task_cycle.progress.registry import (  # noqa: E402
    append_feature_symbol_registry,
    load_symbol_registry_state,
    prepare_feature_symbol_registry_update,
)


def observed_item() -> dict[str, Any]:
    return {
        "evidence_id": "evidence_A",
        "feature_symbol": {
            "symbol": "feature_A",
            "consumed_input_fp": "input_fp_A",
            "target_unit_fp": "target_fp_A",
            "target_unit_count": 2,
            "blocker_root_axis": "axis_A",
        },
        "observed_output": {
            "observed_output_class": "metadata_only",
            "artifact_record_count": 0,
            "artifact_fingerprint": "artifact_fp_A",
            "artifact_count_fingerprint": "count_fp_A",
        },
    }


def final_candidate(cycle_id: str, durable_state: dict[str, Any]) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "schema_version": 1,
        "kind": "cycle_final_candidate",
        "final_candidate": True,
        "cycle_id": cycle_id,
        "attempt_id": "attempt_A",
        "expected_previous_revision": None,
        "expected_previous_attempt_id": None,
        "expected_previous_finalization_token": None,
        "verdict_contract_version": 1,
        "durable_state_candidate": durable_state,
    }
    for axis in cycle_ledger.VERDICT_AXES:
        candidate[axis] = {"status": "pass", "evidence_ref": "evidence_axis_A"}
    return candidate


def write_repeated_history(root: Path) -> None:
    ledger = root / ".task" / "cycle" / "cycle_A" / "stage.jsonl"
    ledger.parent.mkdir(parents=True)
    rows = []
    for attempt_id in ("attempt_A", "attempt_B"):
        rows.append(
            {
                "attempt_id": attempt_id,
                "progress_verdict": "advanced",
                "progress_kind": "governance_only",
                "root_axis": "axis_A",
                "root_key": "root_A",
                "blocker_signature": "blocker_A",
                "feature_symbol": {
                    "symbol": "feature_A",
                    "consumed_input_fp": "input_fp_A",
                    "target_unit_fp": "target_fp_A",
                },
                "observed_output": {
                    "observed_output_class": "metadata_only",
                    "artifact_fingerprint": "artifact_fp_A",
                    "artifact_record_count": 0,
                },
            }
        )
    ledger.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def finalize_registry_projection(root: Path, cycle_id: str = "cycle_A") -> dict[str, Any]:
    cycle_ledger.init_cycle(root, cycle_id, "task_A", "fixture initialization")
    prepared = prepare_feature_symbol_registry_update(root, observed_item())
    return cycle_ledger.finalize_candidate(
        root,
        cycle_id,
        final_candidate(cycle_id, prepared["durable_mutation_candidate"]),
    )


def test_finalizer_rejects_unsigned_axis_alias_and_favorable_body_divergence(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle_alias_A"
    cycle_ledger.init_cycle(tmp_path, cycle_id, "task_T", "fixture initialization")
    prepared = prepare_feature_symbol_registry_update(tmp_path, observed_item())
    durable_state = prepared["durable_mutation_candidate"]

    alias_candidate = final_candidate(cycle_id, durable_state)
    alias_candidate["verdict_axes"] = {
        "artifact_semantic_verdict": {
            "status": "fail",
            "evidence_ref": "evidence_semantic_fail",
        }
    }
    with pytest.raises(ValueError, match="verdict alias conflicts"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, alias_candidate)

    divergence_candidate = final_candidate(cycle_id, durable_state)
    divergence_candidate["report_body_divergence"] = True
    with pytest.raises(ValueError, match="body/report divergence"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, divergence_candidate)

    nested_divergence_candidate = final_candidate(cycle_id, durable_state)
    nested_divergence_candidate["result"] = {"report_body_divergence": True}
    with pytest.raises(ValueError, match="body/report divergence"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, nested_divergence_candidate)

    nested_review_divergence_candidate = final_candidate(cycle_id, durable_state)
    nested_review_divergence_candidate["result"] = {
        "quality_review": {"report_body_divergence": True}
    }
    with pytest.raises(ValueError, match="body/report divergence"):
        cycle_ledger.finalize_candidate(
            tmp_path,
            cycle_id,
            nested_review_divergence_candidate,
        )

    assert not cycle_ledger.current_finalization_path(tmp_path, cycle_id).exists()

    conflicted_candidate = final_candidate(cycle_id, durable_state)
    conflicted_candidate["report_body_divergence"] = True
    conflicted_candidate["artifact_truth_verdict"] = {
        "status": "conflicted",
        "evidence_ref": "evidence_truth_conflict",
    }
    conflicted_candidate["artifact_semantic_verdict"] = {
        "status": "blocked",
        "evidence_ref": "evidence_semantic_blocked",
    }
    conflicted_candidate["goal_readiness_verdict"] = {
        "status": "blocked",
        "evidence_ref": "evidence_goal_blocked",
    }
    finalized = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        conflicted_candidate,
    )

    assert finalized["authoritative_projection"]["task_acceptance_verdict"][
        "status"
    ] == "pass"
    assert finalized["authoritative_projection"]["artifact_truth_verdict"][
        "status"
    ] == "conflicted"
    assert finalized["authoritative_projection"]["authoritative_final"] == "blocked"


def test_legacy_write_request_is_prepare_only_and_privacy_bounded(tmp_path: Path) -> None:
    prepared = prepare_feature_symbol_registry_update(tmp_path, observed_item())
    alias_result = append_feature_symbol_registry(tmp_path, observed_item())
    repeated = prepare_feature_symbol_registry_update(tmp_path, observed_item())

    assert prepared["prepared"] is True
    assert prepared["updated"] is False
    assert prepared["state_commit_status"] == "not_finalized"
    assert alias_result["updated"] is False
    assert not (tmp_path / REGISTRY_REL_PATH).exists()
    assert prepared["durable_mutation_candidate"] == repeated["durable_mutation_candidate"]
    serialized = json.dumps(prepared["durable_mutation_candidate"], sort_keys=True)
    assert "updated_at" not in serialized
    assert "axis_A" not in serialized
    assert "last_evidence_path" not in serialized
    assert "first_seen_cycle" not in serialized


def test_same_path_with_changed_hash_is_fresh_evidence_not_unchanged_ref(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle_evidence_A"
    artifact = tmp_path / "artifact_A.json"
    artifact.write_text('{"revision":1}\n', encoding="utf-8")
    cycle_ledger.init_cycle(tmp_path, cycle_id, "task_T", "fixture initialization")
    cycle_ledger.append_event(
        tmp_path,
        cycle_id,
        {"step": "context", "status": "complete", "task_id": "task_T"},
    )
    first = cycle_ledger.append_event(
        tmp_path,
        cycle_id,
        {"step": "run", "status": "complete", "artifacts": [artifact.name]},
    )
    artifact.write_text('{"revision":2}\n', encoding="utf-8")
    second = cycle_ledger.append_event(
        tmp_path,
        cycle_id,
        {"step": "validate", "status": "complete", "artifacts": [artifact.name]},
    )

    assert first["event"]["artifact_refs"][0]["sha256"] != second["event"][
        "artifact_refs"
    ][0]["sha256"]
    assert second["event"].get("unchanged_refs") in (None, [])


def test_finalization_consumer_reloads_prepared_registry_projection(tmp_path: Path) -> None:
    cycle_id = "cycle_A"
    finalized = finalize_registry_projection(tmp_path, cycle_id)
    loaded = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    registry = load_symbol_registry_state(tmp_path, cycle_id)
    consumed = analyze(tmp_path, None, False, finalized_cycle_id=cycle_id)
    cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrate_task_cycle",
            "progress-loop",
            "--root",
            str(tmp_path),
            "--finalized-cycle-id",
            cycle_id,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=SUBPROCESS_ENV,
    )
    cli_packet = json.loads(cli.stdout)

    assert finalized["valid"] is True
    assert loaded["valid"] is True
    assert registry["status"] == "verified_current"
    assert registry["receipt_verified"] is True
    assert registry["rows"]["feature_A"]["symbol"] == "feature_A"
    assert consumed["registry_input_gate"]["status"] == "verified_current"
    assert consumed["registry_input_gate"]["receipt_verified"] is True
    assert consumed["registry_input_gate"]["hard_stop_required"] is False
    assert cli.returncode == 0
    assert cli_packet["registry_input_gate"]["status"] == "verified_current"
    operations = loaded["durable_state_candidate"]["operations"]
    assert operations[0]["target_id"] == "dedup_symbol_registry"
    assert operations[0]["payload"]["rows"][0]["symbol"] == "feature_A"
    assert not (tmp_path / REGISTRY_REL_PATH).exists()


def test_same_attempt_negative_correction_replaces_current_and_preserves_history(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle_correction_A"
    cycle_ledger.init_cycle(tmp_path, cycle_id, "task_T", "fixture initialization")
    prepared = prepare_feature_symbol_registry_update(tmp_path, observed_item())
    candidate = final_candidate(cycle_id, prepared["durable_mutation_candidate"])
    first = cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
    first_receipt = first["receipt"]
    first_snapshot = cycle_ledger.finalization_snapshot_path(
        tmp_path,
        cycle_id,
        first_receipt["finalization_token"],
    )

    corrected = final_candidate(cycle_id, prepared["durable_mutation_candidate"])
    corrected["expected_previous_revision"] = first_receipt["attempt_revision"]
    corrected["expected_previous_attempt_id"] = first_receipt["attempt_id"]
    corrected["expected_previous_finalization_token"] = first_receipt[
        "finalization_token"
    ]
    corrected["artifact_semantic_verdict"] = {
        "status": "fail",
        "evidence_ref": "evidence_semantic_negative",
    }
    corrected["goal_readiness_verdict"] = {
        "status": "blocked",
        "evidence_ref": "evidence_goal_blocked",
    }
    second = cycle_ledger.finalize_candidate(tmp_path, cycle_id, corrected)
    current = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)

    assert first_snapshot.is_file()
    assert second["receipt"]["attempt_revision"] == 2
    assert second["receipt"]["supersedes_revision"] == 1
    assert current["receipt"]["finalization_token"] == second["receipt"][
        "finalization_token"
    ]
    assert current["authoritative_projection"]["authoritative_final"] == "failure"
    assert current["authoritative_projection"]["artifact_semantic_verdict"][
        "status"
    ] == "fail"


def test_explicit_finalized_cycle_rejects_tampered_or_missing_current_pointer(tmp_path: Path) -> None:
    cycle_id = "cycle_A"
    finalized = finalize_registry_projection(tmp_path, cycle_id)
    assert finalized["valid"] is True
    pointer_path = cycle_ledger.current_finalization_path(tmp_path, cycle_id)
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["receipt_hash"] = "0" * 64
    pointer_path.write_text(json.dumps(pointer, sort_keys=True) + "\n", encoding="utf-8")

    tampered = analyze(tmp_path, None, False, finalized_cycle_id=cycle_id)
    missing = analyze(tmp_path, None, False, finalized_cycle_id="cycle_stale")

    assert tampered["registry_input_gate"]["status"] == "block"
    assert tampered["registry_input_gate"]["receipt_verified"] is False
    assert tampered["hard_stop_required"] is True
    assert missing["registry_input_gate"]["status"] == "block"
    assert missing["hard_stop_required"] is True


def test_omitted_finalized_cycle_uses_explicit_legacy_compat_mode(tmp_path: Path) -> None:
    registry_path = tmp_path / REGISTRY_REL_PATH
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps({"symbol": "feature_A", "occurrence_count": 1}) + "\n", encoding="utf-8")

    result = analyze(tmp_path, None, False)

    assert result["registry_input_gate"]["status"] == "legacy_compat"
    assert result["registry_input_gate"]["legacy_compat"] is True
    assert result["registry_input_gate"]["receipt_verified"] is False
    assert result["registry_input_gate"]["hard_stop_required"] is False


def test_missing_detector_budgets_are_reported_without_invented_stop(tmp_path: Path) -> None:
    write_repeated_history(tmp_path)

    result = analyze(tmp_path, None, True)

    assert result["recurrence_budget"]["evaluation_status"] == "budget_unverified"
    assert result["feature_symbol_gate"]["evaluation_status"] == "budget_unverified"
    assert result["root_axis_gate"]["evaluation_status"] == "budget_unverified"
    assert result["goal_distance_gate"]["evaluation_status"] == "budget_unverified"
    assert result["evidence_scope"]["status"] == "not_evaluated"
    assert result["safety_only_count"] == 0
    assert result["hard_stop_required"] is False


def test_explicit_detector_budget_activates_existing_gate(tmp_path: Path) -> None:
    write_repeated_history(tmp_path)

    result = analyze(
        tmp_path,
        2,
        True,
        feature_symbol_threshold=2,
    )

    assert result["feature_symbol_gate"]["evaluation_status"] == "evaluated"
    assert result["feature_symbol_gate"]["threshold"] == 2
    assert result["feature_symbol_gate"]["hard_stop_required"] is True


def test_repository_policy_owns_evidence_scope_and_threshold(tmp_path: Path) -> None:
    write_repeated_history(tmp_path)

    result = analyze(
        tmp_path,
        None,
        True,
        policy={"budgets": {"evidence_scope_limit": 2, "feature_symbol_stall": 2}},
    )

    assert result["evidence_scope"] == {"status": "explicit_limit", "limit": 2}
    assert result["feature_symbol_gate"]["evaluation_status"] == "evaluated"
    assert result["feature_symbol_gate"]["hard_stop_required"] is True


def test_cli_write_registry_is_prepare_only(tmp_path: Path) -> None:
    write_repeated_history(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrate_task_cycle",
            "progress-loop",
            "--root",
            str(tmp_path),
            "--feature-symbol-threshold",
            "2",
            "--recent",
            "2",
            "--write-registry",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=SUBPROCESS_ENV,
    )
    packet = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert packet["feature_symbol_registry_update"]["prepared"] is True
    assert packet["feature_symbol_registry_update"]["updated"] is False
    assert packet["feature_symbol_registry_update"]["finalization_required"] is True
    assert not (tmp_path / REGISTRY_REL_PATH).exists()
