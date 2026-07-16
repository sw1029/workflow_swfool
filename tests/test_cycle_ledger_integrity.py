from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from orchestrate_task_cycle import cycle_ledger


sys.dont_write_bytecode = True
EXPECTED_STEPS = [
    "context",
    "authority",
    "repo_skill_adapter_scan",
    "acceptance",
    "route_plan",
    "validation_scope_plan",
    "validation_set_plan",
    "governance",
    "result_contract",
    "repo_skill_adapter_validate",
    "ledger_append",
    "code_structure_audit",
    "run",
    "qualitative_review",
    "loopback_audit",
    "validation_set_build",
    "visible_increment",
    "repo_skill_gap_analysis",
    "cycle_efficiency_profile",
    "validation_scope_finalize",
    "index_pre_validate",
    "validate",
    "issue",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "commit",
    "dashboard",
    "report",
    "closeout_commit",
]


def test_canonical_step_order_matches_transition_contract() -> None:
    assert cycle_ledger.DEFAULT_STEPS == EXPECTED_STEPS


def test_long_inline_json_is_not_misclassified_as_a_path() -> None:
    payload = {"artifact_id": "artifact_" + ("A" * 1024)}
    assert cycle_ledger.load_json_value(json.dumps(payload)) == payload


def initialize_with_context(root: Path, cycle_id: str, task_id: str = "task-1", reason: str = "init") -> None:
    cycle_ledger.init_cycle(root, cycle_id, task_id, reason)
    cycle_ledger.append_event(
        root,
        cycle_id,
        {"step": "context", "status": "complete", "task_id": task_id, "reason": "context established"},
    )


def test_append_requires_initialization_context_and_task_coherence(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be initialized"):
        cycle_ledger.append_event(tmp_path, "cycle-missing-init", {"step": "context", "status": "complete"})

    cycle_ledger.init_cycle(tmp_path, "cycle-order", "task-1", "init")
    with pytest.raises(ValueError, match="first canonical stage event"):
        cycle_ledger.append_event(tmp_path, "cycle-order", {"step": "authority", "status": "complete"})
    with pytest.raises(ValueError, match="context task_id must match"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-order",
            {"step": "context", "status": "complete", "task_id": "task-other"},
        )

    cycle_ledger.init_cycle(
        tmp_path,
        "cycle-bootstrap",
        None,
        "bootstrap",
        allow_missing_task_for_bootstrap=True,
    )
    bootstrap = cycle_ledger.append_event(
        tmp_path,
        "cycle-bootstrap",
        {"step": "context", "status": "complete", "task_absent": True},
    )
    assert bootstrap["event"]["task_id"] is None


def test_append_requires_status_and_matching_cycle_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit non-empty `status`"):
        cycle_ledger.append_event(tmp_path, "cycle-a", {"step": "run"})

    with pytest.raises(ValueError, match="does not match ledger cycle"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-a",
            {"cycle_id": "cycle-b", "step": "run", "status": "complete"},
        )

    assert not (tmp_path / ".task" / "cycle" / "cycle-a" / "stage.jsonl").exists()


def test_cycle_directory_symlink_escape_is_rejected(tmp_path: Path) -> None:
    cycle_root = tmp_path / ".task" / "cycle"
    cycle_root.mkdir(parents=True)
    outside = tmp_path / "outside-cycle-storage"
    outside.mkdir()
    (cycle_root / "cycle-escape").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes .task/cycle"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-escape",
            {"step": "run", "status": "complete"},
        )

    assert not (outside / "stage.jsonl").exists()


def test_default_cycle_and_event_ids_are_collision_resistant(tmp_path: Path) -> None:
    first = cycle_ledger.init_cycle(tmp_path, None, "task-1", "first")
    second = cycle_ledger.init_cycle(tmp_path, None, "task-2", "second")

    assert first["cycle_id"] != second["cycle_id"]
    assert len(first["cycle_id"].rsplit("-", 1)[-1]) == 32
    cycle_ledger.append_event(
        tmp_path,
        first["cycle_id"],
        {"step": "context", "status": "complete", "task_id": "task-1"},
    )

    one = cycle_ledger.append_event(
        tmp_path,
        first["cycle_id"],
        {"step": "run", "status": "complete"},
    )
    two = cycle_ledger.append_event(
        tmp_path,
        first["cycle_id"],
        {"step": "run", "status": "complete"},
    )
    assert one["event"]["event_id"] != two["event"]["event_id"]


def test_explicit_event_id_is_idempotent_and_conflicts_fail_closed(tmp_path: Path) -> None:
    initialize_with_context(tmp_path, "cycle-dedupe")
    packet = {"event_id": "run-fixed", "step": "run", "status": "complete", "reason": "same"}

    first = cycle_ledger.append_event(tmp_path, "cycle-dedupe", packet)
    second = cycle_ledger.append_event(tmp_path, "cycle-dedupe", packet)

    assert first.get("event_duplicate") is not True
    assert second["event_duplicate"] is True
    assert len(cycle_ledger.read_events(tmp_path, "cycle-dedupe")) == 2

    with pytest.raises(ValueError, match="different content"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-dedupe",
            {**packet, "reason": "conflict"},
        )


def test_artifact_hashes_are_immutable_and_only_exact_repeats_are_unchanged(tmp_path: Path) -> None:
    artifact = tmp_path / "packet.json"
    artifact.write_text('{"value": 1}\n', encoding="utf-8")
    initialize_with_context(tmp_path, "cycle-artifact")

    first = cycle_ledger.append_event(
        tmp_path,
        "cycle-artifact",
        {"step": "run", "status": "complete", "artifacts": ["packet.json"]},
    )
    repeated = cycle_ledger.append_event(
        tmp_path,
        "cycle-artifact",
        {"step": "validate", "status": "complete", "artifacts": ["packet.json"]},
    )
    old_hash = first["event"]["artifact_refs"][0]["sha256"]
    assert repeated["event"]["unchanged_refs"] == [{"path": "packet.json", "sha256": old_hash}]

    artifact.write_text('{"value": 2}\n', encoding="utf-8")
    changed = cycle_ledger.append_event(
        tmp_path,
        "cycle-artifact",
        {"step": "report", "status": "complete", "artifacts": ["packet.json"]},
    )

    assert changed["event"]["artifact_refs"][0]["sha256"] != old_hash
    assert changed["event"]["unchanged_refs"] == []
    assert cycle_ledger.read_events(tmp_path, "cycle-artifact")[1]["artifact_refs"][0]["sha256"] == old_hash


def test_supplied_artifact_ref_must_match_current_body(tmp_path: Path) -> None:
    artifact = tmp_path / "packet.json"
    artifact.write_text("{}\n", encoding="utf-8")
    initialize_with_context(tmp_path, "cycle-supplied-ref")

    with pytest.raises(ValueError, match="does not match current artifact"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-supplied-ref",
            {
                "step": "run",
                "status": "complete",
                "artifact_refs": [{"path": "packet.json", "sha256": "0" * 64}],
            },
        )
    assert [row["step"] for row in cycle_ledger.read_events(tmp_path, "cycle-supplied-ref")] == ["context"]


def test_malformed_or_unsupported_jsonl_fails_closed_without_append(tmp_path: Path) -> None:
    cycle_id = "cycle-corrupt"
    cycle_ledger.init_cycle(tmp_path, cycle_id, "task-1", "init")
    ledger = tmp_path / ".task" / "cycle" / cycle_id / "stage.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    valid = {"cycle_id": cycle_id, "event_id": "event-1", "step": "run", "status": "complete"}
    ledger.write_text(json.dumps(valid) + "\n{\n", encoding="utf-8")
    before = ledger.read_bytes()

    with pytest.raises(ValueError, match="malformed ledger JSON"):
        cycle_ledger.read_events(tmp_path, cycle_id)
    with pytest.raises(ValueError, match="malformed ledger JSON"):
        cycle_ledger.append_event(tmp_path, cycle_id, {"step": "validate", "status": "complete"})
    assert ledger.read_bytes() == before

    ledger.write_text(
        json.dumps({**valid, "format_version": cycle_ledger.LEDGER_FORMAT_VERSION + 1}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported ledger format_version"):
        cycle_ledger.read_events(tmp_path, cycle_id)


def test_corrective_event_clears_latest_step_failure(tmp_path: Path) -> None:
    initialize_with_context(tmp_path, "cycle-corrective")
    cycle_ledger.append_event(
        tmp_path,
        "cycle-corrective",
        {"step": "validate", "status": "failed"},
    )
    corrected = cycle_ledger.append_event(
        tmp_path,
        "cycle-corrective",
        {"step": "validate", "status": "complete", "reason": "corrected"},
    )

    assert corrected["current_stage"]["status"] == "complete"
    assert corrected["current_stage"]["steps"]["validate"]["status"] == "complete"


def test_terminal_latch_appends_compact_durable_observations(tmp_path: Path) -> None:
    terminal = {
        "step": "report",
        "status": "complete",
        "terminal_justified": True,
        "terminal_outcome_family_key": "family-a",
        "input_state_fingerprint": "input-a",
        "authority_state_fingerprint": "authority-a",
    }
    initialize_with_context(tmp_path, "cycle-terminal")
    cycle_ledger.append_event(tmp_path, "cycle-terminal", terminal)
    repeated = cycle_ledger.append_event(tmp_path, "cycle-terminal", terminal)
    rows = cycle_ledger.read_events(tmp_path, "cycle-terminal")

    assert repeated["event_suppressed"] is True
    assert repeated["observation_appended"] is True
    assert len(rows) == 3
    assert rows[-1]["event_kind"] == "terminal_latch_observation"
    assert rows[-1]["compact_observation"] is True
    assert rows[-1]["terminal_latch_streak"] == 2
    assert rows[-1]["unchanged_terminal_ref"] == rows[-2]["event_id"]

    restart = cycle_ledger.init_cycle(
        tmp_path,
        "cycle-restart-not-created",
        "task-1",
        "restart",
        {key: value for key, value in terminal.items() if key not in {"step", "status"}},
    )
    rows = cycle_ledger.read_events(tmp_path, "cycle-terminal")
    assert restart["cycle_suppressed"] is True
    assert restart["observation_result"]["observation_appended"] is True
    assert rows[-1]["terminal_latch_streak"] == 3
    assert not (tmp_path / ".task" / "cycle" / "cycle-restart-not-created").exists()


def terminal_transition_receipt(root: Path, *, transaction_id: str = "transaction_A") -> dict[str, Any]:
    artifacts: dict[str, dict[str, str]] = {}
    for name in ("seal", "registry", "pack", "index"):
        path = root / f"{name}_A.json"
        path.write_text(json.dumps({"artifact_id": f"{name}_A"}) + "\n", encoding="utf-8")
        artifacts[name] = {
            "ref": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    receipt: dict[str, Any] = {"transaction_id": transaction_id, "artifacts": artifacts}
    normalized, missing = cycle_ledger.terminal_reopen_contract(receipt)
    assert missing == ["transaction_sha256"]
    receipt["transaction_sha256"] = normalized["transaction_sha256"]
    return receipt


def test_v2_terminal_latch_reopens_once_for_content_delta_and_rejects_tampering(tmp_path: Path) -> None:
    terminal = {
        "step": "report",
        "status": "complete",
        "terminal_justified": True,
        "terminal_latch_key_version": 2,
        "terminal_outcome_family_key": "family_F",
        "blocker_signature": "blocker_A",
        "input_state_fingerprint": "input_D",
        "authority_state_fingerprint": "authority_A",
        "external_state_fingerprint": "external_A",
    }
    initialize_with_context(tmp_path, "cycle_C")
    cycle_ledger.append_event(tmp_path, "cycle_C", terminal)
    cycle_ledger.append_event(tmp_path, "cycle_C", terminal)

    receipt = terminal_transition_receipt(tmp_path)
    changed = {
        **{key: value for key, value in terminal.items() if key not in {"step", "status"}},
        "material_delta": {"artifact_sha256": "b" * 64},
        "lifecycle_transition_result": receipt,
    }
    reopened = cycle_ledger.init_cycle(tmp_path, "cycle_D", "task-1", "material delta", changed)
    repeated = cycle_ledger.init_cycle(tmp_path, "cycle_E", "task-1", "same material delta", changed)
    rows = cycle_ledger.read_events(tmp_path, "cycle_C")

    assert reopened["cycle_id"] == "cycle_D"
    assert reopened["terminal_reopen_result"]["event"]["terminal_latch_status"] == "reopened"
    assert repeated["cycle_suppressed"] is True
    assert not (tmp_path / ".task" / "cycle" / "cycle_E").exists()
    assert sum(row.get("terminal_latch_status") == "reopened" for row in rows) == 1
    assert rows[2]["unchanged_ref"]["prior_packet_ref"].endswith(f"#{rows[1]['event_id']}")
    assert len(rows[2]["unchanged_ref"]["prior_packet_sha256"]) == 64

    tampered_receipt = terminal_transition_receipt(tmp_path, transaction_id="transaction_B")
    tampered_receipt["artifacts"]["seal"]["sha256"] = "0" * 64
    normalized, _missing = cycle_ledger.terminal_reopen_contract(tampered_receipt)
    tampered_receipt["transaction_sha256"] = normalized["transaction_sha256"]
    tampered = {
        **changed,
        "material_delta": {"artifact_sha256": "c" * 64},
        "lifecycle_transition_result": tampered_receipt,
    }
    with pytest.raises(ValueError, match="failed content verification"):
        cycle_ledger.init_cycle(tmp_path, "cycle_F", "task-1", "tampered delta", tampered)
    assert not (tmp_path / ".task" / "cycle" / "cycle_F").exists()


def test_current_terminal_identity_and_unchanged_refs_fail_closed(tmp_path: Path) -> None:
    state = cycle_ledger.terminal_latch_state(
        [],
        {
            "terminal_justified": True,
            "terminal_latch_key_version": 2,
            "terminal_outcome_family_key": "family_F",
            "blocker_signature": "blocker_A",
            "input_state_fingerprint": "input_D",
            "authority_state_fingerprint": "authority_A",
        },
    )
    assert state["terminal_latch_status"] == "not_evaluated"
    assert state["terminal_latch_missing_fields"] == ["external_state_fingerprint"]

    initialize_with_context(tmp_path, "cycle-forged-ref")
    with pytest.raises(ValueError, match="does not match prior authoritative"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-forged-ref",
            {
                "step": "run",
                "status": "complete",
                "unchanged_refs": [{"path": "artifact_A.json", "sha256": "a" * 64}],
            },
        )


def test_concurrent_appends_are_complete_unique_jsonl_records(tmp_path: Path) -> None:
    cycle_id = "cycle-concurrent"
    initialize_with_context(tmp_path, cycle_id)

    def append(index: int) -> str:
        result = cycle_ledger.append_event(
            tmp_path,
            cycle_id,
            {
                "event_id": f"run-{index}",
                "step": "run",
                "status": "complete",
                "reason": f"worker-{index}",
            },
        )
        return str(result["event"]["event_id"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        event_ids = list(executor.map(append, range(32)))

    rows = cycle_ledger.read_events(tmp_path, cycle_id)
    assert len(rows) == 33
    assert len(set(event_ids)) == 32
    assert len({row["event_id"] for row in rows}) == 33
    current = json.loads((tmp_path / ".task" / "cycle" / cycle_id / "current_stage.json").read_text(encoding="utf-8"))
    assert current["event_count"] == 33
    assert current["format_version"] == cycle_ledger.LEDGER_FORMAT_VERSION


def test_versionless_legacy_rows_remain_readable(tmp_path: Path) -> None:
    cycle_id = "cycle-legacy"
    ledger = tmp_path / ".task" / "cycle" / cycle_id / "stage.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps({"cycle_id": cycle_id, "event_id": "legacy-1", "step": "run", "status": "complete"}) + "\n",
        encoding="utf-8",
    )

    assert cycle_ledger.read_events(tmp_path, cycle_id)[0].get("format_version") is None
    with pytest.raises(ValueError, match="must be initialized"):
        cycle_ledger.append_event(
            tmp_path,
            cycle_id,
            {"step": "validate", "status": "complete"},
        )


def final_candidate(
    cycle_id: str,
    attempt_id: str,
    *,
    expected_receipt: dict[str, Any] | None = None,
    goal_status: str = "pass",
    state_marker: str = "state_A",
) -> dict[str, Any]:
    expected_receipt = expected_receipt or {}
    axes = {
        axis: {"status": "pass", "evidence_ref": f"evidence_{index}"}
        for index, axis in enumerate(cycle_ledger.VERDICT_AXES, start=1)
    }
    axes["goal_readiness_verdict"] = {
        "status": goal_status,
        "evidence_ref": "evidence_goal",
    }
    return {
        "schema_version": 1,
        "kind": "cycle_final_candidate",
        "final_candidate": True,
        "cycle_id": cycle_id,
        "attempt_id": attempt_id,
        "expected_previous_revision": expected_receipt.get("attempt_revision"),
        "expected_previous_attempt_id": expected_receipt.get("attempt_id"),
        "expected_previous_finalization_token": expected_receipt.get("finalization_token"),
        "verdict_contract_version": 1,
        **axes,
        "durable_state_candidate": {
            "mode": "complete_projection",
            "projections": {
                "registry_projection": {"artifact_id": state_marker},
                "ledger_projection": [{"evidence_id": f"evidence_{state_marker}"}],
            },
        },
    }


def test_finalization_happy_path_is_content_bound_and_exact_retry_is_idempotent(tmp_path: Path) -> None:
    cycle_id = "cycle-final-A"
    initialize_with_context(tmp_path, cycle_id, task_id="task_A")
    candidate = final_candidate(cycle_id, "attempt_A")

    first = cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
    repeated = cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
    receipt = first["receipt"]
    snapshot_path = tmp_path / receipt["snapshot_ref"]

    assert first["idempotent"] is False
    assert repeated["idempotent"] is True
    assert first["finalization_receipt"] == receipt
    assert repeated["finalization_receipt"] == receipt
    assert repeated["receipt"] == receipt
    assert first["authoritative_projection"] == first["snapshot"]["authoritative_projection"]
    assert receipt["attempt_revision"] == 1
    assert receipt["supersedes_revision"] is None
    assert receipt["state_commit_status"] == "committed"
    assert receipt["authoritative_final"] == "success"
    assert hashlib.sha256(snapshot_path.read_bytes()).hexdigest() == receipt["finalization_token"]
    assert receipt["snapshot_sha256"] == receipt["finalization_token"]
    verified = cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, receipt)
    assert verified["valid"] is True
    assert verified["snapshot"]["authoritative_projection_digest"] == receipt["authoritative_projection_digest"]
    loaded = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    assert loaded["valid"] is True
    assert loaded["durable_state_candidate"] == candidate["durable_state_candidate"]
    assert loaded["receipt"] == receipt
    assert len(list(snapshot_path.parent.glob("*.json"))) == 1

    trace_only_retry = {**candidate, "intermediate_observation": {"checked_at": "trace_B", "family_label": "family_B"}}
    trace_only_repeated = cycle_ledger.finalize_candidate(tmp_path, cycle_id, trace_only_retry)
    assert trace_only_repeated["idempotent"] is True
    assert trace_only_repeated["receipt"] == receipt
    assert len(list(snapshot_path.parent.glob("*.json"))) == 1


def test_same_attempt_correction_supersedes_revision_and_preserves_task_pass_goal_failure(tmp_path: Path) -> None:
    cycle_id = "cycle-final-B"
    initialize_with_context(tmp_path, cycle_id, task_id="task_B")
    first = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(cycle_id, "attempt_B"),
    )
    corrected_candidate = final_candidate(
        cycle_id,
        "attempt_B",
        expected_receipt=first["receipt"],
        goal_status="fail",
        state_marker="state_B",
    )
    corrected_candidate["intermediate_observation"] = {
        "evidence_id": "evidence_intermediate_A",
        "semantic_progress": True,
        "progress_verdict": "advanced",
    }
    corrected_candidate["durable_state_candidate"]["projections"]["registry_projection"].update(
        {
            "semantic_progress": False,
            "authoritative_semantic_progress": False,
            "goal_productive": False,
            "progress_verdict": "no_progress",
        }
    )
    contradictory = json.loads(json.dumps(corrected_candidate))
    contradictory["durable_state_candidate"]["projections"]["registry_projection"]["semantic_progress"] = True
    with pytest.raises(ValueError, match="contradicts the final artifact semantic verdict"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, contradictory)
    assert cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)["receipt"] == first["receipt"]

    corrected = cycle_ledger.finalize_candidate(tmp_path, cycle_id, corrected_candidate)
    receipt = corrected["receipt"]
    projection = corrected["snapshot"]["authoritative_projection"]
    registry_projection = corrected["snapshot"]["durable_state_candidate"]["projections"]["registry_projection"]

    assert receipt["attempt_revision"] == 2
    assert receipt["supersedes_revision"] == 1
    assert receipt["supersedes_finalization_token"] == first["receipt"]["finalization_token"]
    assert receipt["authoritative_final"] == "failure"
    assert projection["task_acceptance_verdict"]["status"] == "pass"
    assert projection["goal_readiness_verdict"]["status"] == "fail"
    assert registry_projection["semantic_progress"] is False
    assert registry_projection["goal_productive"] is False
    assert registry_projection["progress_verdict"] == "no_progress"
    assert "intermediate_observation" not in corrected["snapshot"]
    with pytest.raises(ValueError, match="stale"):
        cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, first["receipt"])
    assert cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, receipt)["valid"] is True


def test_finalization_rejects_source_metadata_before_any_durable_publication(tmp_path: Path) -> None:
    cycle_id = "cycle-final-private"
    initialize_with_context(tmp_path, cycle_id, task_id="task_private")
    candidate = final_candidate(cycle_id, "attempt_private")
    candidate["durable_state_candidate"] = {
        "mode": "typed_operations",
        "operations": [
            {
                "operation_type": "replace_projection",
                "target_id": "registry_A",
                "target_ref": ".task/state_A.json",
                "payload": {
                    "artifact_id": "artifact_A",
                    "source_path": "source/private_A.txt",
                    "direct_quote": "private body A",
                },
            }
        ],
    }

    with pytest.raises(ValueError, match="prohibited source metadata"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)

    assert not cycle_ledger.current_finalization_path(tmp_path, cycle_id).exists()
    assert not cycle_ledger.finalizations_dir(tmp_path, cycle_id).exists()

    axis_candidate = final_candidate(cycle_id, "attempt_private_axis")
    axis_candidate["artifact_truth_verdict"] = {
        "status": "pass",
        "evidence_ref": "source/private_B.json",
    }
    with pytest.raises(ValueError, match="path-like string"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, axis_candidate)

    assert not cycle_ledger.current_finalization_path(tmp_path, cycle_id).exists()
    assert not cycle_ledger.finalizations_dir(tmp_path, cycle_id).exists()


def test_finalization_verifies_typed_operation_hashes_and_unique_targets(tmp_path: Path) -> None:
    cycle_id = "cycle-final-operation-binding"
    initialize_with_context(tmp_path, cycle_id, task_id="task_operation_binding")
    candidate = final_candidate(cycle_id, "attempt_operation_binding")
    payload = {"artifact_id": "artifact_A"}
    operation = {
        "operation_type": "replace_projection",
        "target_id": "registry_A",
        "payload": payload,
        "payload_sha256": cycle_ledger.canonical_sha256(payload),
    }
    durable_candidate = {
        "contract_version": 1,
        "mode": "typed_operations",
        "producer": "producer_A",
        "operations": [operation],
    }
    durable_candidate["candidate_sha256"] = cycle_ledger.canonical_sha256(durable_candidate)
    candidate["durable_state_candidate"] = durable_candidate

    finalized = cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
    assert finalized["receipt"]["authoritative_final"] == "success"

    missing_hash_cycle_id = "cycle-final-operation-missing-hash"
    initialize_with_context(tmp_path, missing_hash_cycle_id, task_id="task_operation_missing_hash")
    missing_hash = final_candidate(missing_hash_cycle_id, "attempt_operation_missing_hash")
    missing_hash["durable_state_candidate"] = {
        "contract_version": 1,
        "mode": "typed_operations",
        "producer": "producer_A",
        "operations": [
            {
                "operation_type": "replace_projection",
                "target_id": "registry_A",
                "payload": payload,
            }
        ],
    }
    with pytest.raises(ValueError, match="requires payload_sha256"):
        cycle_ledger.finalize_candidate(tmp_path, missing_hash_cycle_id, missing_hash)
    assert not cycle_ledger.current_finalization_path(tmp_path, missing_hash_cycle_id).exists()

    missing_candidate_hash_cycle_id = "cycle-final-operation-missing-candidate-hash"
    initialize_with_context(
        tmp_path,
        missing_candidate_hash_cycle_id,
        task_id="task_operation_missing_candidate_hash",
    )
    missing_candidate_hash = final_candidate(
        missing_candidate_hash_cycle_id,
        "attempt_operation_missing_candidate_hash",
    )
    missing_candidate_hash["durable_state_candidate"] = {
        "contract_version": 1,
        "mode": "typed_operations",
        "producer": "producer_A",
        "operations": [operation],
    }
    with pytest.raises(ValueError, match="requires candidate_sha256"):
        cycle_ledger.finalize_candidate(
            tmp_path,
            missing_candidate_hash_cycle_id,
            missing_candidate_hash,
        )
    assert not cycle_ledger.current_finalization_path(
        tmp_path, missing_candidate_hash_cycle_id
    ).exists()

    tampered_cycle_id = "cycle-final-operation-tamper"
    initialize_with_context(tmp_path, tampered_cycle_id, task_id="task_operation_tamper")
    tampered = final_candidate(tampered_cycle_id, "attempt_operation_tamper")
    tampered["durable_state_candidate"] = {
        "mode": "typed_operations",
        "operations": [{**operation, "payload": {"artifact_id": "artifact_B"}}],
    }
    with pytest.raises(ValueError, match="payload_sha256 mismatch"):
        cycle_ledger.finalize_candidate(tmp_path, tampered_cycle_id, tampered)
    assert not cycle_ledger.current_finalization_path(tmp_path, tampered_cycle_id).exists()

    duplicate_cycle_id = "cycle-final-operation-duplicate"
    initialize_with_context(tmp_path, duplicate_cycle_id, task_id="task_operation_duplicate")
    duplicate = final_candidate(duplicate_cycle_id, "attempt_operation_duplicate")
    duplicate["durable_state_candidate"] = {
        "mode": "typed_operations",
        "operations": [operation, {**operation, "operation_type": "append_projection"}],
    }
    with pytest.raises(ValueError, match="target_id is duplicated"):
        cycle_ledger.finalize_candidate(tmp_path, duplicate_cycle_id, duplicate)
    assert not cycle_ledger.current_finalization_path(tmp_path, duplicate_cycle_id).exists()

def test_failure_before_pointer_publish_leaves_prior_truth_unchanged_and_retry_recovers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = "cycle-final-C"
    initialize_with_context(tmp_path, cycle_id, task_id="task_C")
    first = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(cycle_id, "attempt_C"),
    )
    correction = final_candidate(
        cycle_id,
        "attempt_C",
        expected_receipt=first["receipt"],
        goal_status="fail",
        state_marker="state_C",
    )
    correction["durable_state_candidate"] = {
        "mode": "typed_operations",
        "operations": [
            {
                "operation_type": "replace_projection",
                "target_id": "registry_A",
                "payload": {"artifact_id": "artifact_registry_B"},
            },
            {
                "operation_type": "append_projection",
                "target_id": "root_ledger_A",
                "payload": {"evidence_id": "evidence_root_B"},
            },
            {
                "operation_type": "replace_projection",
                "target_id": "seal_A",
                "payload": {"artifact_id": "artifact_seal_B"},
            },
            {
                "operation_type": "replace_projection",
                "target_id": "current_A",
                "payload": {"artifact_id": "artifact_current_B"},
            },
        ],
    }
    pointer_path = cycle_ledger.current_finalization_path(tmp_path, cycle_id)
    pointer_before = pointer_path.read_bytes()
    original_atomic_write = cycle_ledger.atomic_write_text

    def fail_pointer_publish(path: Path, content: str) -> None:
        if path == pointer_path:
            raise OSError("injected pointer publication failure")
        original_atomic_write(path, content)

    monkeypatch.setattr(cycle_ledger, "atomic_write_text", fail_pointer_publish)
    with pytest.raises(OSError, match="injected pointer"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, correction)

    assert pointer_path.read_bytes() == pointer_before
    assert cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, first["receipt"])["valid"] is True
    still_current = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    assert still_current["durable_state_candidate"] == final_candidate(
        cycle_id,
        "attempt_C",
    )["durable_state_candidate"]
    monkeypatch.setattr(cycle_ledger, "atomic_write_text", original_atomic_write)
    recovered = cycle_ledger.finalize_candidate(tmp_path, cycle_id, correction)
    assert recovered["receipt"]["attempt_revision"] == 2
    assert recovered["receipt"]["authoritative_final"] == "failure"
    assert cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)["durable_state_candidate"] == correction[
        "durable_state_candidate"
    ]
    assert len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json"))) == 2


def test_stale_cas_and_tampered_receipt_fail_closed_without_publishing(tmp_path: Path) -> None:
    cycle_id = "cycle-final-D"
    initialize_with_context(tmp_path, cycle_id, task_id="task_D")
    first = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(cycle_id, "attempt_D"),
    )
    stale = final_candidate(
        cycle_id,
        "attempt_D",
        expected_receipt=first["receipt"],
        goal_status="fail",
        state_marker="state_D",
    )
    stale["expected_previous_finalization_token"] = "0" * 64
    snapshot_count = len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json")))

    with pytest.raises(ValueError, match="does not match current pointer"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, stale)
    assert len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json"))) == snapshot_count

    tampered = dict(first["receipt"])
    tampered["authoritative_final"] = "failure"
    with pytest.raises(ValueError, match="receipt hash mismatch"):
        cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, tampered)
    assert cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, first["receipt"])["valid"] is True


def test_concurrent_corrections_publish_one_current_revision_and_preserve_history(tmp_path: Path) -> None:
    cycle_id = "cycle-final-E"
    initialize_with_context(tmp_path, cycle_id, task_id="task_E")
    first = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(cycle_id, "attempt_E"),
    )
    candidates = [
        final_candidate(
            cycle_id,
            "attempt_E",
            expected_receipt=first["receipt"],
            goal_status="fail",
            state_marker=state_marker,
        )
        for state_marker in ("state_E1", "state_E2")
    ]

    def publish(candidate: dict[str, Any]) -> tuple[str, Any]:
        try:
            return "published", cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
        except ValueError as exc:
            return "rejected", str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, candidates))

    assert sorted(status for status, _ in outcomes) == ["published", "rejected"]
    assert any("does not match current pointer" in str(value) for status, value in outcomes if status == "rejected")
    current = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    assert current["receipt"]["attempt_revision"] == 2
    assert current["receipt"]["supersedes_revision"] == 1
    assert len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json"))) == 2
