from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from progress_loop_detection.constants import REGISTRY_REL_PATH  # noqa: E402
from progress_loop_detection.analysis import analyze  # noqa: E402
from progress_loop_detection.registry import (  # noqa: E402
    append_feature_symbol_registry,
    load_symbol_registry_state,
    prepare_feature_symbol_registry_update,
)


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cycle_ledger = load_module(SCRIPTS_ROOT / "cycle_ledger.py", "cycle_ledger_progress_registry_test")


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


def test_finalization_consumer_reloads_prepared_registry_projection(tmp_path: Path) -> None:
    cycle_id = "cycle_A"
    finalized = finalize_registry_projection(tmp_path, cycle_id)
    loaded = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    registry = load_symbol_registry_state(tmp_path, cycle_id)
    consumed = analyze(tmp_path, None, False, finalized_cycle_id=cycle_id)
    cli = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_ROOT / "detect_progress_loop.py"),
            "--root",
            str(tmp_path),
            "--finalized-cycle-id",
            cycle_id,
        ],
        check=False,
        capture_output=True,
        text=True,
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
            str(SCRIPTS_ROOT / "detect_progress_loop.py"),
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
    )
    packet = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert packet["feature_symbol_registry_update"]["prepared"] is True
    assert packet["feature_symbol_registry_update"]["updated"] is False
    assert packet["feature_symbol_registry_update"]["finalization_required"] is True
    assert not (tmp_path / REGISTRY_REL_PATH).exists()
