from __future__ import annotations

import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from orchestrate_task_cycle import cycle_ledger
from orchestrate_task_cycle.ledger import candidate_validation, finalization_publication
from orchestrate_task_cycle.result_contract.consumer_receipt_contract import (
    CONSUMER_RECEIPT_CONTRACT_VERSION,
    CONSUMER_REVISION_SHA256,
    VALIDATOR_SIGNATURE_SHA256,
)
from historical_cycle_test_support import create_sealed_legacy_v1_cycle


ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPTS = ROOT / "audit-cycle-loopback" / "scripts"
if str(AUDIT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUDIT_SCRIPTS))
from audit_cycle_loopback.consumer_context import (  # noqa: E402
    consumer_context_conformance_gate,
    consumer_receipt_binding_sha256,
)
from audit_cycle_loopback.decision_identity_binding import (  # noqa: E402
    decision_identity_echo,
)


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


def initialize_with_context(
    root: Path, cycle_id: str, task_id: str = "task-1", reason: str = "init"
) -> None:
    create_sealed_legacy_v1_cycle(
        root,
        cycle_id,
        task_id,
        reason,
    )
    cycle_ledger.append_event(
        root,
        cycle_id,
        {
            "step": "context",
            "status": "complete",
            "task_id": task_id,
            "reason": "context established",
        },
    )


def test_append_requires_initialization_context_and_task_coherence(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="must be initialized"):
        cycle_ledger.append_event(
            tmp_path, "cycle-missing-init", {"step": "context", "status": "complete"}
        )

    create_sealed_legacy_v1_cycle(
        tmp_path,
        "cycle-order",
        "task-1",
        "init",
    )
    with pytest.raises(ValueError, match="first canonical stage event"):
        cycle_ledger.append_event(
            tmp_path, "cycle-order", {"step": "authority", "status": "complete"}
        )
    with pytest.raises(ValueError, match="context task_id must match"):
        cycle_ledger.append_event(
            tmp_path,
            "cycle-order",
            {"step": "context", "status": "complete", "task_id": "task-other"},
        )

    create_sealed_legacy_v1_cycle(
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
    event_cycle_id = "cycle-event-id-collision"
    create_sealed_legacy_v1_cycle(
        tmp_path,
        event_cycle_id,
        "task-1",
        "legacy event ID fixture",
    )
    cycle_ledger.append_event(
        tmp_path,
        event_cycle_id,
        {"step": "context", "status": "complete", "task_id": "task-1"},
    )

    one = cycle_ledger.append_event(
        tmp_path,
        event_cycle_id,
        {"step": "run", "status": "complete"},
    )
    two = cycle_ledger.append_event(
        tmp_path,
        event_cycle_id,
        {"step": "run", "status": "complete"},
    )
    assert one["event"]["event_id"] != two["event"]["event_id"]


def test_explicit_event_id_is_idempotent_and_conflicts_fail_closed(
    tmp_path: Path,
) -> None:
    initialize_with_context(tmp_path, "cycle-dedupe")
    packet = {
        "event_id": "run-fixed",
        "step": "run",
        "status": "complete",
        "reason": "same",
    }

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


def test_artifact_hashes_are_immutable_and_only_exact_repeats_are_unchanged(
    tmp_path: Path,
) -> None:
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
    assert repeated["event"]["unchanged_refs"] == [
        {"path": "packet.json", "sha256": old_hash}
    ]

    artifact.write_text('{"value": 2}\n', encoding="utf-8")
    changed = cycle_ledger.append_event(
        tmp_path,
        "cycle-artifact",
        {"step": "report", "status": "complete", "artifacts": ["packet.json"]},
    )

    assert changed["event"]["artifact_refs"][0]["sha256"] != old_hash
    assert changed["event"]["unchanged_refs"] == []
    assert (
        cycle_ledger.read_events(tmp_path, "cycle-artifact")[1]["artifact_refs"][0][
            "sha256"
        ]
        == old_hash
    )


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
    assert [
        row["step"] for row in cycle_ledger.read_events(tmp_path, "cycle-supplied-ref")
    ] == ["context"]


def test_malformed_or_unsupported_jsonl_fails_closed_without_append(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-corrupt"
    create_sealed_legacy_v1_cycle(
        tmp_path,
        cycle_id,
        "task-1",
        "init",
    )
    ledger = tmp_path / ".task" / "cycle" / cycle_id / "stage.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    valid = {
        "cycle_id": cycle_id,
        "event_id": "event-1",
        "step": "run",
        "status": "complete",
    }
    ledger.write_text(json.dumps(valid) + "\n{\n", encoding="utf-8")
    before = ledger.read_bytes()

    with pytest.raises(ValueError, match="malformed ledger JSON"):
        cycle_ledger.read_events(tmp_path, cycle_id)
    with pytest.raises(ValueError, match="malformed ledger JSON"):
        cycle_ledger.append_event(
            tmp_path, cycle_id, {"step": "validate", "status": "complete"}
        )
    assert ledger.read_bytes() == before

    ledger.write_text(
        json.dumps({**valid, "format_version": 3})
        + "\n",
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
        {
            key: value
            for key, value in terminal.items()
            if key not in {"step", "status"}
        },
    )
    rows = cycle_ledger.read_events(tmp_path, "cycle-terminal")
    assert restart["cycle_suppressed"] is True
    assert restart["observation_result"]["observation_appended"] is True
    assert rows[-1]["terminal_latch_streak"] == 3
    assert not (tmp_path / ".task" / "cycle" / "cycle-restart-not-created").exists()


def terminal_transition_receipt(
    root: Path, *, transaction_id: str = "transaction_A"
) -> dict[str, Any]:
    artifacts: dict[str, dict[str, str]] = {}
    for name in ("seal", "registry", "pack", "index"):
        path = root / f"{name}_A.json"
        path.write_text(
            json.dumps({"artifact_id": f"{name}_A"}) + "\n", encoding="utf-8"
        )
        artifacts[name] = {
            "ref": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    receipt: dict[str, Any] = {"transaction_id": transaction_id, "artifacts": artifacts}
    normalized, missing = cycle_ledger.terminal_reopen_contract(receipt)
    assert missing == ["transaction_sha256"]
    receipt["transaction_sha256"] = normalized["transaction_sha256"]
    return receipt


def test_v2_terminal_latch_reopens_once_for_content_delta_and_rejects_tampering(
    tmp_path: Path,
) -> None:
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
        **{
            key: value
            for key, value in terminal.items()
            if key not in {"step", "status"}
        },
        "material_delta": {"artifact_sha256": "b" * 64},
        "lifecycle_transition_result": receipt,
    }
    reopened = cycle_ledger.init_cycle(
        tmp_path, "cycle_D", "task-1", "material delta", changed
    )
    repeated = cycle_ledger.init_cycle(
        tmp_path, "cycle_E", "task-1", "same material delta", changed
    )
    rows = cycle_ledger.read_events(tmp_path, "cycle_C")

    assert reopened["cycle_id"] == "cycle_D"
    assert (
        reopened["terminal_reopen_result"]["event"]["terminal_latch_status"]
        == "reopened"
    )
    assert repeated["cycle_suppressed"] is True
    assert not (tmp_path / ".task" / "cycle" / "cycle_E").exists()
    assert sum(row.get("terminal_latch_status") == "reopened" for row in rows) == 1
    assert rows[2]["unchanged_ref"]["prior_packet_ref"].endswith(
        f"#{rows[1]['event_id']}"
    )
    assert len(rows[2]["unchanged_ref"]["prior_packet_sha256"]) == 64

    tampered_receipt = terminal_transition_receipt(
        tmp_path, transaction_id="transaction_B"
    )
    tampered_receipt["artifacts"]["seal"]["sha256"] = "0" * 64
    normalized, _missing = cycle_ledger.terminal_reopen_contract(tampered_receipt)
    tampered_receipt["transaction_sha256"] = normalized["transaction_sha256"]
    tampered = {
        **changed,
        "material_delta": {"artifact_sha256": "c" * 64},
        "lifecycle_transition_result": tampered_receipt,
    }
    with pytest.raises(ValueError, match="failed content verification"):
        cycle_ledger.init_cycle(
            tmp_path, "cycle_F", "task-1", "tampered delta", tampered
        )
    assert not (tmp_path / ".task" / "cycle" / "cycle_F").exists()


def test_current_terminal_identity_and_unchanged_refs_fail_closed(
    tmp_path: Path,
) -> None:
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
    current = json.loads(
        (tmp_path / ".task" / "cycle" / cycle_id / "current_stage.json").read_text(
            encoding="utf-8"
        )
    )
    assert current["event_count"] == 33
    assert current["format_version"] == cycle_ledger.LEDGER_FORMAT_VERSION


def test_versionless_legacy_rows_remain_readable(tmp_path: Path) -> None:
    cycle_id = "cycle-legacy"
    ledger = tmp_path / ".task" / "cycle" / cycle_id / "stage.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            {
                "cycle_id": cycle_id,
                "event_id": "legacy-1",
                "step": "run",
                "status": "complete",
            }
        )
        + "\n",
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
    registry_updates: dict[str, Any] | None = None,
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
    target_revisions = expected_receipt.get("target_revision_ids") or {}
    registry_payload = {"artifact_id": state_marker, **(registry_updates or {})}
    registry_operation = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity=attempt_id,
        payload_schema_id="registry-projection-v1",
        payload=registry_payload,
        expected_revision_id=target_revisions.get("registry_projection"),
    )
    ledger_payload = [{"evidence_id": f"evidence_{state_marker}"}]
    ledger_operation = cycle_ledger.build_durable_operation(
        target_ref="ledger_projection",
        operation_kind="replace_projection",
        attempt_identity=attempt_id,
        payload_schema_id="ledger-projection-v1",
        payload={"rows": ledger_payload},
        expected_revision_id=target_revisions.get("ledger_projection"),
        depends_on_operation_ids=[registry_operation["operation_id"]],
    )
    return {
        "schema_version": 1,
        "kind": "cycle_final_candidate",
        "final_candidate": True,
        "cycle_id": cycle_id,
        "attempt_id": attempt_id,
        "expected_previous_revision": expected_receipt.get("attempt_revision"),
        "expected_previous_attempt_id": expected_receipt.get("attempt_id"),
        "expected_previous_finalization_token": expected_receipt.get(
            "finalization_token"
        ),
        "verdict_contract_version": 1,
        **axes,
        "durable_state_candidate": cycle_ledger.build_typed_operations_candidate(
            producer="cycle-ledger-test",
            attempt_identity=attempt_id,
            operations=[registry_operation, ledger_operation],
        ),
    }


def absent_no_change_evidence(
    attempt_identity: str,
    *target_refs: str,
) -> dict[str, Any]:
    targets = target_refs or ("registry_projection",)
    observations: list[dict[str, Any]] = []
    for target_ref in targets:
        state_digest = cycle_ledger.absent_target_state_digest(target_ref)
        observations.append(
            cycle_ledger.build_unchanged_target_observation(
                observation_id=f"{attempt_identity}-{target_ref}-observation",
                attempt_identity=attempt_identity,
                target_ref=target_ref,
                state_status="absent",
                before_revision_id="absent",
                current_revision_id="absent",
                before_state_digest=state_digest,
                current_state_digest=state_digest,
            )
        )
    return cycle_ledger.build_no_change_evidence(
        evidence_id=f"{attempt_identity}-no-change-evidence",
        attempt_identity=attempt_identity,
        target_observations=observations,
    )


def present_no_change_evidence(
    attempt_identity: str,
    authoritative_projection: dict[str, Any],
    *target_refs: str,
) -> dict[str, Any]:
    observations: list[dict[str, Any]] = []
    for target_ref in target_refs:
        target_state = authoritative_projection[target_ref]
        observations.append(
            cycle_ledger.build_unchanged_target_observation(
                observation_id=f"{attempt_identity}-{target_ref}-observation",
                attempt_identity=attempt_identity,
                target_ref=target_ref,
                state_status="present",
                before_revision_id=target_state["resulting_revision_id"],
                current_revision_id=target_state["resulting_revision_id"],
                before_state_digest=target_state["payload_digest"],
                current_state_digest=target_state["payload_digest"],
            )
        )
    return cycle_ledger.build_no_change_evidence(
        evidence_id=f"{attempt_identity}-no-change-evidence",
        attempt_identity=attempt_identity,
        target_observations=observations,
    )


def _loopback_gate_for(
    root: Path,
    candidate: dict[str, Any],
    *,
    conformance_status: str = "pass",
    identity_status: str = "verified",
) -> dict[str, Any]:
    exact_identity = {
        "decision_subject_id": "SUBJECT_REF",
        "subject_class_id": "BODY_REF",
        "revision_id": "REVISION_REF",
        "subject_digest": "a" * 64,
        "lineage_id": "EVIDENCE_REF",
        "freshness_status": "current",
        "body_fingerprint": {
            "applicability": "applicable",
            "value": "b" * 64,
        },
        "production_lane": {"applicability": "not_applicable", "value": None},
        "cohort": {"applicability": "applicable", "value": ["COHORT_REF"]},
        "producer_run": {"applicability": "not_applicable", "value": None},
    }
    decision_ref = {
        **exact_identity,
        "decision_identity_kind": "explicit_v2",
        "decision_identity": exact_identity,
        "artifact_id": "SUBJECT_REF",
        "artifact_class": "BODY_REF",
        "artifact_path_or_store_ref": "EVIDENCE_REF",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": None,
        "body_projection_fingerprint": "b" * 64,
        "cohort_identity": ["COHORT_REF"],
        "producer_run_id": None,
        "verification_input_ids": ["COHORT_REF"],
        "input_fingerprints": None,
        "created_or_observed_at": None,
        "discovery_basis": "explicit_caller_path",
        "advisory_discovery": False,
        "conflicting_discovery_paths": [],
        "identity_status": identity_status,
        "scope_verified": identity_status == "verified",
    }
    consumer_id = "CONSUMER_REF"
    hook_id = "HOOK_REF"
    gate_id = "GATE_REF"
    task_id = "TASK_REF"
    adapter_revision = "d" * 64
    input_fingerprint = "c" * 64
    consumer_contract = {
        "consumer_id": consumer_id,
        "task_id": task_id,
        "adapter_revision_sha256": adapter_revision,
        "consumer_revision_sha256": CONSUMER_REVISION_SHA256,
        "hook_id": hook_id,
        "required_hook_ids": [hook_id],
        "required_gate_ids": [gate_id],
    }
    rows: list[dict[str, Any]] = []
    if conformance_status == "pass":
        row = {
            "consumer_context_id": consumer_id,
            "hook_id": hook_id,
            "cycle_id": candidate["cycle_id"],
            "task_id": task_id,
            "attempt_identity": candidate["attempt_id"],
            "input_state_fingerprint": input_fingerprint,
            "adapter_revision_sha256": adapter_revision,
            "consumer_contract_version": CONSUMER_RECEIPT_CONTRACT_VERSION,
            "consumer_revision_sha256": CONSUMER_REVISION_SHA256,
            "validator_signature_sha256": VALIDATOR_SIGNATURE_SHA256,
            "hook_io_receipts": [
                {
                    "acceptance_required": True,
                    "invocation_index": 0,
                    "hook_id": hook_id,
                    "input_sha256": "1" * 64,
                    "output_sha256": "2" * 64,
                    "return_contract_valid": True,
                    "semantic_status": "accepted",
                    "signature_sha256": "3" * 64,
                    "status": "completed",
                    "value_consumed_by_decision": True,
                }
            ],
            "decision_identity_echo": decision_identity_echo(decision_ref),
            "required_hook_ids": [hook_id],
            "required_gate_ids": [gate_id],
            "consumed_hook_ids": [hook_id],
            "consumed_gate_ids": [gate_id],
            "excluded_gate_ids": [],
            "result_contract_status": "conformant",
            "adapter_loaded": True,
            "hook_resolved": True,
            "required_hook_callable": True,
            "hook_signature_compatible": True,
            "invocation_completed": True,
            "return_contract_valid": True,
            "artifact_identity_echo_valid": True,
            "value_consumed_by_decision": True,
            "evidence_provenance": "independently_verified",
            "probe_evidence_ref": "EVIDENCE_REF",
        }
        row["probe_evidence_sha256"] = consumer_receipt_binding_sha256(row)
        rows.append(row)
    conformance = consumer_context_conformance_gate(
        {
            "required_consumer_ids": [consumer_id],
            "consumer_contract": consumer_contract,
            "consumer_context_conformance": {"rows": rows},
        },
        expected_artifact_ref=decision_ref,
        expected_cycle_id=candidate["cycle_id"],
        expected_input_state_fingerprint=input_fingerprint,
        expected_attempt_identity=candidate["attempt_id"],
        expected_task_id=task_id,
        expected_adapter_revision_sha256=adapter_revision,
    )
    packet = {
        "schema_version": "anti-loop-progress-gate-v1",
        "handoff_contract_version": 1,
        "decision_contract_version": 1,
        "step": "loopback_audit",
        "cycle_id": candidate["cycle_id"],
        "task_id": task_id,
        "finalization_required": True,
        "finalization_state": "candidate",
        "authoritative_consumption_allowed": False,
        "attempt_identity": candidate["attempt_id"],
        "attempt_identity_version": 2,
        "input_state_fingerprint": input_fingerprint,
        "decision_artifact_ref": decision_ref,
        "scope_verified": identity_status == "verified",
        "artifact_id": "SUBJECT_REF",
        "artifact_sha256": "a" * 64,
        "artifact_family": "BODY_REF",
        "blocker_signature": "BLOCKER_REF",
        "progress_verdict": (
            "advanced" if conformance_status == "pass" else "not_evaluated"
        ),
        "hard_stop_required": False,
        "terminal_state": "derive",
        "allowed_next_action_classes": ["derive"],
        "gate_compatibility_results": [],
        "consumer_context_conformance": conformance,
        "durable_mutation_candidate": candidate["durable_state_candidate"],
    }
    packet_path = root / (
        "loopback-packet-"
        + conformance_status.replace("_", "-")
        + "-"
        + identity_status.replace("_", "-")
        + ".json"
    )
    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    packet["anti_loop_handoff"] = {
        "handoff_contract_version": 1,
        "applicability": "required",
        "finalization_required": True,
        "authoritative_consumption_allowed": False,
        "packet_ref": packet_path.name,
        "packet_sha256": packet_sha,
        "artifact_id": packet["artifact_id"],
        "artifact_sha256": packet["artifact_sha256"],
        "artifact_family": packet["artifact_family"],
        "blocker_signature": packet["blocker_signature"],
        "progress_verdict": packet["progress_verdict"],
        "hard_stop": packet["hard_stop_required"],
        "terminal_state": packet["terminal_state"],
        "allowed_next_action_classes": packet["allowed_next_action_classes"],
        "compatible_gate_ids": [],
        "incompatible_gate_ids": [],
        "durable_mutation_candidate_sha256": candidate["durable_state_candidate"][
            "candidate_sha256"
        ],
    }
    return packet


def _rewrite_loopback_packet(root: Path, gate: dict[str, Any]) -> None:
    handoff = gate["anti_loop_handoff"]
    packet_path = root / handoff["packet_ref"]
    packet_path.write_text(
        json.dumps(
            {key: value for key, value in gate.items() if key != "anti_loop_handoff"},
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    handoff["packet_sha256"] = hashlib.sha256(packet_path.read_bytes()).hexdigest()


def test_exact_loopback_consumer_and_typed_mutation_finalize_successfully(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-loopback-exact-happy"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-happy")
    candidate = final_candidate(cycle_id, attempt)
    candidate["anti_loop_progress_gate"] = _loopback_gate_for(tmp_path, candidate)
    candidate["decision_artifact_ref"] = candidate["anti_loop_progress_gate"][
        "decision_artifact_ref"
    ]

    finalized = cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)

    assert finalized["receipt"]["authoritative_final"] == "success"
    assert finalized["snapshot"]["durable_state_candidate"] == (
        candidate["durable_state_candidate"]
    )
    assert finalized["receipt"]["attempt_id"] == attempt


@pytest.mark.parametrize("tamper", ["probe_ref", "hook_io_input"])
def test_loopback_consumer_receipt_hash_is_recomputed_before_finalization(
    tmp_path: Path,
    tamper: str,
) -> None:
    cycle_id = "cycle-loopback-receipt-tamper"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-tamper")
    candidate = final_candidate(cycle_id, attempt)
    gate = _loopback_gate_for(tmp_path, candidate)
    row = gate["consumer_context_conformance"]["rows"][0]
    if tamper == "probe_ref":
        row["probe_evidence_ref"] = "EVIDENCE_OTHER"
    else:
        row["hook_io_receipts"][0]["input_sha256"] = "9" * 64
    _rewrite_loopback_packet(tmp_path, gate)
    candidate["anti_loop_progress_gate"] = gate
    candidate["decision_artifact_ref"] = gate["decision_artifact_ref"]

    with pytest.raises(ValueError, match="blocks favorable semantic and goal"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


@pytest.mark.parametrize(
    "mutation",
    ["missing_field", "duplicate", "extra", "conflicted"],
)
def test_explicit_loopback_consumer_contract_cannot_relax_expectations(
    tmp_path: Path,
    mutation: str,
) -> None:
    cycle_id = f"cycle-loopback-contract-{mutation}"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-contract")
    candidate = final_candidate(cycle_id, attempt)
    gate = _loopback_gate_for(tmp_path, candidate)
    contracts = gate["consumer_context_conformance"]["consumer_contracts"]
    if mutation == "missing_field":
        contracts[0].pop("task_id")
    elif mutation == "duplicate":
        contracts.append(json.loads(json.dumps(contracts[0])))
    elif mutation == "extra":
        extra = json.loads(json.dumps(contracts[0]))
        extra["consumer_id"] = "CONSUMER_OTHER"
        contracts.append(extra)
    else:
        contracts[0]["contract_conflicted"] = True
    _rewrite_loopback_packet(tmp_path, gate)
    candidate["anti_loop_progress_gate"] = gate
    candidate["decision_artifact_ref"] = gate["decision_artifact_ref"]

    with pytest.raises(ValueError, match="blocks favorable semantic and goal"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


def test_mixed_owner_loopback_operation_set_cannot_omit_gate(tmp_path: Path) -> None:
    cycle_id = "cycle-loopback-mixed-owner"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-mixed")
    candidate = final_candidate(cycle_id, attempt)
    audit_operation = cycle_ledger.build_durable_operation(
        target_ref="family_progress_registry",
        operation_kind="replace_projection",
        attempt_identity=attempt,
        payload_schema_id="family-progress-registry-v1",
        payload={"rows": [{"cycle_id": cycle_id, "family_key": "ROOT_REF"}]},
    )
    candidate["durable_state_candidate"] = (
        cycle_ledger.build_typed_operations_candidate(
            producer="mixed-owner-producer",
            attempt_identity=attempt,
            operations=[
                *candidate["durable_state_candidate"]["operations"],
                audit_operation,
            ],
        )
    )

    with pytest.raises(ValueError, match="loopback-owned finalization cannot omit"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


def test_audit_owned_exact_no_change_cannot_omit_loopback_gate(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-loopback-audit-no-change"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-no-change")
    candidate = final_candidate(cycle_id, attempt)
    candidate["durable_state_candidate"] = (
        cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity=attempt,
            reason_id="validation-has-no-durable-axis-change",
            evidence=absent_no_change_evidence(
                attempt,
                "family_progress_registry",
            ),
        )
    )

    with pytest.raises(ValueError, match="loopback-owned finalization cannot omit"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


def test_loopback_packet_rejects_symlinked_parent_component(tmp_path: Path) -> None:
    cycle_id = "cycle-loopback-parent-symlink"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-symlink")
    candidate = final_candidate(cycle_id, attempt)
    gate = _loopback_gate_for(tmp_path, candidate)
    real_parent = tmp_path / "real-packets"
    real_parent.mkdir()
    real_packet = real_parent / "packet.json"
    real_packet.write_text(
        json.dumps(
            {key: value for key, value in gate.items() if key != "anti_loop_handoff"},
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "linked-packets").symlink_to(real_parent, target_is_directory=True)
    gate["anti_loop_handoff"]["packet_ref"] = "linked-packets/packet.json"
    gate["anti_loop_handoff"]["packet_sha256"] = hashlib.sha256(
        real_packet.read_bytes()
    ).hexdigest()
    candidate["anti_loop_progress_gate"] = gate
    candidate["decision_artifact_ref"] = gate["decision_artifact_ref"]

    with pytest.raises(ValueError, match="not a safe local file"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


@pytest.mark.parametrize("path_form", ["dot_prefix", "parent_segment"])
def test_loopback_packet_ref_must_be_canonical_posix_relative(
    tmp_path: Path,
    path_form: str,
) -> None:
    cycle_id = f"cycle-loopback-noncanonical-{path_form}"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-path")
    candidate = final_candidate(cycle_id, attempt)
    gate = _loopback_gate_for(tmp_path, candidate)
    packet_name = gate["anti_loop_handoff"]["packet_ref"]
    if path_form == "dot_prefix":
        gate["anti_loop_handoff"]["packet_ref"] = f"./{packet_name}"
    else:
        (tmp_path / "nested").mkdir()
        gate["anti_loop_handoff"]["packet_ref"] = f"nested/../{packet_name}"
    candidate["anti_loop_progress_gate"] = gate
    candidate["decision_artifact_ref"] = gate["decision_artifact_ref"]

    with pytest.raises(ValueError, match="not a safe local file"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


def test_loopback_packet_read_is_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = "cycle-loopback-oversized-packet"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-oversized")
    candidate = final_candidate(cycle_id, attempt)
    gate = _loopback_gate_for(tmp_path, candidate)
    oversized = tmp_path / "oversized-loopback-packet.json"
    monkeypatch.setattr(candidate_validation, "MAX_LOOPBACK_PACKET_BYTES", 32)
    oversized.write_bytes(b" " * 33)
    gate["anti_loop_handoff"]["packet_ref"] = oversized.name
    gate["anti_loop_handoff"]["packet_sha256"] = hashlib.sha256(
        oversized.read_bytes()
    ).hexdigest()
    candidate["anti_loop_progress_gate"] = gate
    candidate["decision_artifact_ref"] = gate["decision_artifact_ref"]

    with pytest.raises(ValueError, match="bounded size limit"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


@pytest.mark.parametrize(
    ("container", "field", "invalid_value"),
    [
        ("packet", "handoff_contract_version", True),
        ("packet", "handoff_contract_version", 1.0),
        ("packet", "decision_contract_version", True),
        ("packet", "decision_contract_version", 1.0),
        ("packet", "attempt_identity_version", True),
        ("packet", "attempt_identity_version", 2.0),
        ("handoff", "handoff_contract_version", True),
        ("handoff", "handoff_contract_version", 1.0),
    ],
)
def test_loopback_version_fields_require_exact_integers(
    tmp_path: Path,
    container: str,
    field: str,
    invalid_value: object,
) -> None:
    cycle_id = f"cycle-loopback-bool-{container}-{field}"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-bool")
    candidate = final_candidate(cycle_id, attempt)
    gate = _loopback_gate_for(tmp_path, candidate)
    if container == "packet":
        gate[field] = invalid_value
        _rewrite_loopback_packet(tmp_path, gate)
    else:
        gate["anti_loop_handoff"][field] = invalid_value
    candidate["anti_loop_progress_gate"] = gate
    candidate["decision_artifact_ref"] = gate["decision_artifact_ref"]

    with pytest.raises(ValueError, match="finalization contract|producer packet"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


def test_ungated_legacy_decision_ref_preserves_preexisting_commit_digest(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-legacy-decision-digest"
    initialize_with_context(tmp_path, cycle_id, task_id="task-legacy-digest")
    candidate = final_candidate(cycle_id, "ATTEMPT_REF")
    legacy = json.loads(json.dumps(candidate))
    legacy["decision_artifact_ref"] = {
        "artifact_id": "SUBJECT_REF",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "COHORT_REF",
    }
    legacy["anti_loop_progress_gate"] = None
    legacy["anti_loop_handoff"] = None

    assert cycle_ledger.final_candidate_commit_material(legacy) == (
        cycle_ledger.final_candidate_commit_material(candidate)
    )
    first = cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
    replay = cycle_ledger.finalize_candidate(tmp_path, cycle_id, legacy)
    assert replay["idempotent"] is True
    assert replay["receipt"] == first["receipt"]


def test_finalizer_consumes_exact_loopback_mutation_and_limits_unevaluated_consumer(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-loopback-finalization-binding"
    attempt = "ATTEMPT_REF"
    initialize_with_context(tmp_path, cycle_id, task_id="task-loopback-binding")
    candidate = final_candidate(cycle_id, attempt)
    typed_candidate = candidate["durable_state_candidate"]
    explicit_without_gate = json.loads(json.dumps(candidate))
    explicit_without_gate["decision_artifact_ref"] = {
        "decision_identity_kind": "explicit_v2",
        "decision_identity": {
            "artifact_id": "SUBJECT_REF",
            "artifact_sha256": "a" * 64,
            "production_lane_identity": "COHORT_REF",
        },
    }
    with pytest.raises(ValueError, match="cannot omit anti_loop_progress_gate"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, explicit_without_gate)

    audit_owned = json.loads(json.dumps(candidate))
    audit_operation = cycle_ledger.build_durable_operation(
        target_ref="family_progress_registry",
        operation_kind="replace_projection",
        attempt_identity=attempt,
        payload_schema_id="family-progress-registry-v1",
        payload={"rows": [{"cycle_id": cycle_id, "family_key": "ROOT_REF"}]},
    )
    audit_owned["durable_state_candidate"] = (
        cycle_ledger.build_typed_operations_candidate(
            producer="audit-cycle-loopback",
            attempt_identity=attempt,
            operations=[audit_operation],
        )
    )
    with pytest.raises(ValueError, match="loopback-owned finalization cannot omit"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, audit_owned)

    candidate["anti_loop_progress_gate"] = _loopback_gate_for(tmp_path, candidate)
    candidate["decision_artifact_ref"] = candidate["anti_loop_progress_gate"][
        "decision_artifact_ref"
    ]
    downgraded_gate = json.loads(json.dumps(candidate))
    downgraded_gate["anti_loop_progress_gate"]["finalization_required"] = False
    with pytest.raises(ValueError, match="cannot lower finalization_required"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, downgraded_gate)

    missing_handoff = json.loads(json.dumps(candidate))
    missing_handoff["anti_loop_progress_gate"].pop("anti_loop_handoff")
    with pytest.raises(ValueError, match="lacks its hash-bound handoff"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, missing_handoff)

    no_change = cycle_ledger.build_no_durable_state_change_candidate(
        attempt_identity=attempt,
        reason_id="validation-has-no-durable-axis-change",
        evidence=absent_no_change_evidence(attempt),
    )
    bypass = json.loads(json.dumps(candidate))
    bypass["durable_state_candidate"] = no_change
    bypass["anti_loop_progress_gate"]["durable_mutation_candidate"] = no_change
    with pytest.raises(ValueError, match="reopened anti-loop producer packet"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, bypass)

    unevaluated = json.loads(json.dumps(candidate))
    unevaluated["anti_loop_progress_gate"] = _loopback_gate_for(
        tmp_path,
        unevaluated,
        conformance_status="not_evaluated",
    )
    with pytest.raises(ValueError, match="blocks favorable semantic and goal"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, unevaluated)

    malformed = json.loads(json.dumps(candidate))
    malformed["anti_loop_progress_gate"] = _loopback_gate_for(
        tmp_path,
        malformed,
        conformance_status="missing",
    )
    malformed["anti_loop_progress_gate"]["consumer_context_conformance"] = {}
    malformed_packet = tmp_path / "loopback-packet-missing-verified.json"
    malformed_packet.write_text(
        json.dumps(
            {
                key: value
                for key, value in malformed["anti_loop_progress_gate"].items()
                if key != "anti_loop_handoff"
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    malformed["anti_loop_progress_gate"]["anti_loop_handoff"][
        "packet_sha256"
    ] = hashlib.sha256(malformed_packet.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="blocks favorable semantic and goal"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, malformed)

    stale_identity = json.loads(json.dumps(candidate))
    stale_identity["anti_loop_progress_gate"] = _loopback_gate_for(
        tmp_path,
        stale_identity,
        identity_status="hash_mismatch",
    )
    with pytest.raises(ValueError, match="blocks favorable semantic and goal"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, stale_identity)

    bounded = json.loads(json.dumps(unevaluated))
    bounded["artifact_semantic_verdict"] = {
        "status": "not_evaluated",
        "evidence_ref": "EVIDENCE_REF",
    }
    bounded["goal_readiness_verdict"] = {
        "status": "not_evaluated",
        "evidence_ref": "EVIDENCE_REF",
    }
    finalized = cycle_ledger.finalize_candidate(tmp_path, cycle_id, bounded)

    assert typed_candidate == bounded["durable_state_candidate"]
    assert finalized["authoritative_projection"]["task_acceptance_verdict"][
        "status"
    ] == "pass"
    assert finalized["authoritative_projection"]["artifact_semantic_verdict"][
        "status"
    ] == "not_evaluated"
    assert finalized["authoritative_projection"]["goal_readiness_verdict"][
        "status"
    ] == "not_evaluated"
    expected_digest = cycle_ledger.canonical_sha256(
        cycle_ledger.final_candidate_commit_material(bounded)
    )
    assert finalized["receipt"]["final_candidate_digest"] == expected_digest
    other_packet = json.loads(json.dumps(bounded))
    other_packet["anti_loop_progress_gate"]["blocker_signature"] = "BLOCKER_OTHER"
    assert cycle_ledger.canonical_sha256(
        cycle_ledger.final_candidate_commit_material(other_packet)
    ) != expected_digest


def test_exported_final_candidate_normalizer_keeps_legacy_two_argument_api() -> None:
    candidate = final_candidate("cycle-normalizer-api", "ATTEMPT_REF")

    normalized = cycle_ledger.normalize_final_candidate(
        "cycle-normalizer-api", candidate
    )

    assert normalized["attempt_id"] == "ATTEMPT_REF"


def _no_op_pointer_writer(_path: Path, _body: str) -> None:
    return None


def _corrupt_pointer_writer(path: Path, _body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"kind":"corrupt"}\n', encoding="utf-8")


@pytest.mark.parametrize(
    "writer",
    [_no_op_pointer_writer, _corrupt_pointer_writer],
    ids=["no-op", "corrupt"],
)
def test_finalizer_post_reads_authoritative_pointer_before_returning_valid(
    tmp_path: Path,
    writer: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = f"cycle-post-read-{writer.__name__}"
    initialize_with_context(tmp_path, cycle_id, task_id="task-post-read")
    candidate = final_candidate(cycle_id, "ATTEMPT_REF")
    monkeypatch.setattr(cycle_ledger, "atomic_write_text", writer)

    with pytest.raises(ValueError, match="current finalization pointer"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)


def registered_payload_cases() -> list[tuple[str, str, dict[str, Any]]]:
    root_material = {
        "stable_root_id": "root-A",
        "root_predicate_id": "predicate-A",
        "root_scope_id": "scope-A",
    }
    recurrence_state = {
        "applicability": "applicable",
        **root_material,
        "root_identity_sha256": cycle_ledger.canonical_sha256(root_material),
        "prior_stable_root_id": "root-A",
        "prior_root_predicate_id": "predicate-A",
        "prior_root_scope_id": "scope-A",
        "prior_root_identity_sha256": cycle_ledger.canonical_sha256(root_material),
        "facet_id": "facet-A",
        "local_family_id": "family-A",
        "root_recurrence_count": 1,
        "prior_root_recurrence_count": 1,
        "facet_recurrence_count": 1,
        "local_family_attempt_count": 1,
        "evaluation_debt_streak": 0,
        "root_predicate_unchanged": True,
        "binding_status": "pass",
        "lineage_transition": {"kind": "none"},
    }
    return [
        (
            "registry_projection",
            "registry-projection-v1",
            {"artifact_id": "artifact-valid"},
        ),
        (
            "ledger_projection",
            "ledger-projection-v1",
            {"rows": [{"evidence_id": "evidence-valid"}]},
        ),
        (
            "family_progress_registry",
            "family-progress-registry-v1",
            {"rows": [{"cycle_id": "cycle-valid", "family_key": "family-valid"}]},
        ),
        (
            "root_cause_ledger",
            "root-cause-ledger-v1",
            {"rows": [{"cycle_id": "cycle-valid", "root_key": "root-valid"}]},
        ),
        (
            "sealed_blocker_families",
            "sealed-blocker-families-v1",
            {
                "state": {
                    "schema_version": "sealed-blocker-families-v1",
                    "families": [],
                }
            },
        ),
        (
            "recurrence_identity",
            "recurrence-identity-v1",
            {"state": recurrence_state},
        ),
        (
            "dedup_symbol_registry",
            "dedup-symbol-registry-v1",
            {
                "rows": [
                    {
                        "symbol": "symbol-valid",
                        "scope": "workflow_loop",
                        "occurrence_count": 1,
                        "observed_output_classes": ["no_delta"],
                        "last_observed_output_class": "no_delta",
                        "last_observed_material_delta": 0,
                        "status": "seen",
                    }
                ]
            },
        ),
    ]


@pytest.mark.parametrize(
    ("target_ref", "payload_schema_id", "valid_payload"),
    registered_payload_cases(),
)
def test_each_owner_registration_enforces_closed_payload_schema(
    target_ref: str,
    payload_schema_id: str,
    valid_payload: dict[str, Any],
) -> None:
    operation = cycle_ledger.build_durable_operation(
        target_ref=target_ref,
        operation_kind="replace_projection",
        attempt_identity="attempt-payload-schema",
        payload_schema_id=payload_schema_id,
        payload=valid_payload,
    )
    assert operation["payload"] == valid_payload

    with pytest.raises(ValueError, match="unregistered schema fields"):
        cycle_ledger.build_durable_operation(
            target_ref=target_ref,
            operation_kind="replace_projection",
            attempt_identity="attempt-payload-schema",
            payload_schema_id=payload_schema_id,
            payload={**valid_payload, "totally_invented_field": 7},
        )


def test_durable_operation_owner_registry_is_closed_and_revalidated(
    tmp_path: Path,
) -> None:
    valid = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt-owner-contract",
        payload_schema_id="registry-projection-v1",
        payload={"artifact_id": "artifact-owner-contract"},
    )
    assert valid["target_kind"] == "projection"

    with pytest.raises(ValueError, match="target_ref is not owner-registered"):
        cycle_ledger.build_durable_operation(
            target_ref="unregistered_projection",
            operation_kind="replace_projection",
            attempt_identity="attempt-owner-contract",
            payload_schema_id="unregistered-projection-v1",
            payload={"artifact_id": "artifact-owner-contract"},
        )
    with pytest.raises(ValueError, match="target_kind is not registered"):
        cycle_ledger.build_durable_operation(
            target_ref="registry_projection",
            target_kind="arbitrary_target_kind",
            operation_kind="replace_projection",
            attempt_identity="attempt-owner-contract",
            payload_schema_id="registry-projection-v1",
            payload={"artifact_id": "artifact-owner-contract"},
        )
    with pytest.raises(ValueError, match="payload_schema_id is not owner-registered"):
        cycle_ledger.build_durable_operation(
            target_ref="registry_projection",
            operation_kind="replace_projection",
            attempt_identity="attempt-owner-contract",
            payload_schema_id="arbitrary-schema-v1",
            payload={"artifact_id": "artifact-owner-contract"},
        )
    with pytest.raises(ValueError, match="operation_kind is not owner-registered"):
        cycle_ledger.build_durable_operation(
            target_ref="registry_projection",
            operation_kind="append_projection",
            attempt_identity="attempt-owner-contract",
            payload_schema_id="registry-projection-v1",
            payload={"artifact_id": "artifact-owner-contract"},
        )
    with pytest.raises(ValueError, match="recovery_policy_id is not owner-registered"):
        cycle_ledger.build_durable_operation(
            target_ref="registry_projection",
            operation_kind="replace_projection",
            attempt_identity="attempt-owner-contract",
            payload_schema_id="registry-projection-v1",
            payload={"artifact_id": "artifact-owner-contract"},
            recovery_policy_id="arbitrary-recovery-policy",
        )

    cycle_id = "cycle-owner-contract-revalidation"
    initialize_with_context(tmp_path, cycle_id, task_id="task-owner-contract")
    candidate = final_candidate(cycle_id, "attempt-owner-contract")
    tampered = dict(valid)
    tampered["payload_schema_id"] = "arbitrary-schema-v1"
    candidate["durable_state_candidate"] = (
        cycle_ledger.build_typed_operations_candidate(
            producer="owner-contract-test",
            attempt_identity="attempt-owner-contract",
            operations=[tampered],
        )
    )
    with pytest.raises(ValueError, match="payload_schema_id is not owner-registered"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
    assert not cycle_ledger.current_finalization_path(tmp_path, cycle_id).exists()

    rehashed_payload = dict(valid)
    rehashed_payload["payload"] = {
        "artifact_id": "artifact-owner-contract",
        "totally_invented_field": 7,
    }
    rehashed_payload["payload_digest"] = cycle_ledger.canonical_sha256(
        rehashed_payload["payload"]
    )
    rehashed_payload["payload_sha256"] = rehashed_payload["payload_digest"]
    identity_material = {
        field: rehashed_payload[field]
        for field in (
            "target_kind",
            "target_ref",
            "operation_kind",
            "expected_revision_id",
            "attempt_identity",
            "depends_on_operation_ids",
            "payload_schema_id",
            "payload_digest",
            "recovery_policy_id",
        )
    }
    identity_digest = cycle_ledger.canonical_sha256(identity_material)
    rehashed_payload["operation_id"] = f"operation-{identity_digest}"
    rehashed_payload["idempotency_key"] = f"idempotency-{identity_digest}"
    candidate["durable_state_candidate"] = (
        cycle_ledger.build_typed_operations_candidate(
            producer="owner-contract-test",
            attempt_identity="attempt-owner-contract",
            operations=[rehashed_payload],
        )
    )
    with pytest.raises(ValueError, match="unregistered schema fields"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
    assert not cycle_ledger.current_finalization_path(tmp_path, cycle_id).exists()


def rehash_observation(observation: dict[str, Any]) -> dict[str, Any]:
    rehashed = dict(observation)
    rehashed["observation_receipt_sha256"] = cycle_ledger.canonical_sha256(
        {
            key: value
            for key, value in rehashed.items()
            if key != "observation_receipt_sha256"
        }
    )
    return rehashed


def rehash_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    rehashed = dict(evidence)
    rehashed["evidence_sha256"] = cycle_ledger.canonical_sha256(
        {key: value for key, value in rehashed.items() if key != "evidence_sha256"}
    )
    return rehashed


def test_no_change_requires_owner_observations_and_rejects_rehashed_fabrication() -> (
    None
):
    attempt = "attempt-no-change"
    evidence = absent_no_change_evidence(attempt)
    observation = evidence["target_observations"][0]
    candidate_state = cycle_ledger.build_no_durable_state_change_candidate(
        attempt_identity=attempt,
        reason_id="validation-has-no-durable-axis-change",
        evidence=evidence,
    )
    assert candidate_state["no_change_evidence"] == evidence

    with pytest.raises(ValueError, match="reason_id is not registered"):
        cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity=attempt,
            reason_id="arbitrary-no-change-reason",
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="evidence fields"):
        cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity=attempt,
            reason_id="validation-has-no-durable-axis-change",
            evidence={
                "evaluated_target_ids": ["registry_projection"],
                "changed_target_ids": [],
            },
        )
    with pytest.raises(ValueError, match="non-empty registered owner"):
        cycle_ledger.build_no_change_evidence(
            evidence_id="no-change-list-only",
            attempt_identity=attempt,
            target_observations=[],
        )

    fabricated_owner = dict(observation)
    fabricated_owner["owner_id"] = "fabricated-owner"
    fabricated_owner = rehash_observation(fabricated_owner)
    with pytest.raises(ValueError, match="observation owner mismatch"):
        cycle_ledger.build_no_change_evidence(
            evidence_id="fabricated-owner-evidence",
            attempt_identity=attempt,
            target_observations=[fabricated_owner],
        )

    changed_observation = dict(observation)
    changed_observation["state_status"] = "present"
    changed_observation["before_revision_id"] = "sha256-" + "a" * 64
    changed_observation["before_state_digest"] = "a" * 64
    changed_observation["current_revision_id"] = "sha256-" + "b" * 64
    changed_observation["current_state_digest"] = "b" * 64
    changed_observation = rehash_observation(changed_observation)
    with pytest.raises(ValueError, match="reports a state change"):
        cycle_ledger.build_no_change_evidence(
            evidence_id="changed-observation-evidence",
            attempt_identity=attempt,
            target_observations=[changed_observation],
        )

    wrong_attempt = dict(observation)
    wrong_attempt["attempt_identity"] = "attempt-other"
    wrong_attempt = rehash_observation(wrong_attempt)
    with pytest.raises(ValueError, match="observation attempt mismatch"):
        cycle_ledger.build_no_change_evidence(
            evidence_id="wrong-attempt-evidence",
            attempt_identity=attempt,
            target_observations=[wrong_attempt],
        )

    inventory_mismatch = dict(evidence)
    inventory_mismatch["evaluated_target_ids"] = ["ledger_projection"]
    inventory_mismatch = rehash_evidence(inventory_mismatch)
    with pytest.raises(ValueError, match="inventory does not match"):
        cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity=attempt,
            reason_id="validation-has-no-durable-axis-change",
            evidence=inventory_mismatch,
        )


def test_no_change_owner_observations_preserve_replay_and_digest_binding(
    tmp_path: Path,
) -> None:
    attempt = "attempt-no-change"
    evidence = absent_no_change_evidence(
        attempt,
        "registry_projection",
        "ledger_projection",
    )
    candidate_state = cycle_ledger.build_no_durable_state_change_candidate(
        attempt_identity=attempt,
        reason_id="validation-has-no-durable-axis-change",
        evidence=evidence,
    )
    assert candidate_state["no_change_evidence"]["evaluated_target_ids"] == [
        "registry_projection",
        "ledger_projection",
    ]

    cycle_id = "cycle-no-change-replay"
    initialize_with_context(tmp_path, cycle_id, task_id="task-no-change")
    final = final_candidate(cycle_id, attempt)
    final["durable_state_candidate"] = candidate_state
    first = cycle_ledger.finalize_candidate(tmp_path, cycle_id, final)
    replay = cycle_ledger.finalize_candidate(tmp_path, cycle_id, final)
    assert first["idempotent"] is False
    assert replay["idempotent"] is True
    assert replay["receipt"] == first["receipt"]

    tampered_cycle_id = "cycle-no-change-digest-tamper"
    tampered_attempt = "attempt-no-change-tamper"
    initialize_with_context(
        tmp_path,
        tampered_cycle_id,
        task_id="task-no-change-digest-tamper",
    )
    tampered_final = final_candidate(tampered_cycle_id, tampered_attempt)
    tampered_state = cycle_ledger.build_no_durable_state_change_candidate(
        attempt_identity=tampered_attempt,
        reason_id="validation-has-no-durable-axis-change",
        evidence=absent_no_change_evidence(tampered_attempt),
    )
    tampered_state["no_change_evidence_digest"] = "0" * 64
    tampered_final["durable_state_candidate"] = tampered_state
    with pytest.raises(ValueError, match="evidence digest mismatch"):
        cycle_ledger.finalize_candidate(tmp_path, tampered_cycle_id, tampered_final)
    assert not cycle_ledger.current_finalization_path(
        tmp_path, tampered_cycle_id
    ).exists()


def test_no_change_rejects_absent_claim_for_live_owner_targets_before_publication(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-no-change-live-owner"
    initialize_with_context(tmp_path, cycle_id, task_id="task-no-change-live-owner")
    first = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(cycle_id, "attempt-live-owner-1"),
    )
    pointer_path = cycle_ledger.current_finalization_path(tmp_path, cycle_id)
    pointer_before = pointer_path.read_bytes()
    snapshot_count = len(
        list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json"))
    )
    successor = final_candidate(
        cycle_id,
        "attempt-live-owner-2",
        expected_receipt=first["receipt"],
    )
    successor["durable_state_candidate"] = (
        cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity="attempt-live-owner-2",
            reason_id="validation-has-no-durable-axis-change",
            evidence=absent_no_change_evidence(
                "attempt-live-owner-2",
                "registry_projection",
                "ledger_projection",
            ),
        )
    )

    with pytest.raises(
        cycle_ledger.FinalizationConflictError,
        match="current owner projection",
    ):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, successor)

    assert pointer_path.read_bytes() == pointer_before
    assert (
        len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json")))
        == snapshot_count
    )
    pending = cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id)
    assert len(pending) == 1
    assert pending[0]["attempt_memory_disposition"] == "pending_conflict"


def test_no_change_accepts_exact_present_owner_state_and_preserves_projection(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-no-change-present-owner"
    initialize_with_context(
        tmp_path,
        cycle_id,
        task_id="task-no-change-present-owner",
    )
    first = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(cycle_id, "attempt-present-owner-1"),
    )
    prior_projection = first["snapshot"]["post_write_projection"]
    successor = final_candidate(
        cycle_id,
        "attempt-present-owner-2",
        expected_receipt=first["receipt"],
    )
    successor["durable_state_candidate"] = (
        cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity="attempt-present-owner-2",
            reason_id="validation-has-no-durable-axis-change",
            evidence=present_no_change_evidence(
                "attempt-present-owner-2",
                prior_projection,
                "registry_projection",
                "ledger_projection",
            ),
        )
    )

    finalized = cycle_ledger.finalize_candidate(tmp_path, cycle_id, successor)

    assert finalized["snapshot"]["post_write_projection"] == prior_projection
    assert (
        finalized["receipt"]["target_revision_ids"]
        == first["receipt"]["target_revision_ids"]
    )


def test_no_change_rejects_stale_and_cross_target_owner_state(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-no-change-stale-owner"
    initialize_with_context(tmp_path, cycle_id, task_id="task-no-change-stale-owner")
    first = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(cycle_id, "attempt-stale-owner-1"),
    )
    second = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(
            cycle_id,
            "attempt-stale-owner-2",
            expected_receipt=first["receipt"],
            state_marker="state-stale-owner-new",
        ),
    )
    pointer_path = cycle_ledger.current_finalization_path(tmp_path, cycle_id)
    pointer_before = pointer_path.read_bytes()
    stale_attempt = "attempt-stale-owner-3"
    stale = final_candidate(
        cycle_id,
        stale_attempt,
        expected_receipt=second["receipt"],
    )
    stale["durable_state_candidate"] = (
        cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity=stale_attempt,
            reason_id="validation-has-no-durable-axis-change",
            evidence=present_no_change_evidence(
                stale_attempt,
                first["snapshot"]["post_write_projection"],
                "registry_projection",
                "ledger_projection",
            ),
        )
    )
    with pytest.raises(
        cycle_ledger.FinalizationConflictError,
        match="current owner projection",
    ):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, stale)
    assert pointer_path.read_bytes() == pointer_before

    sibling_state = second["snapshot"]["post_write_projection"]["ledger_projection"]
    cross_attempt = "attempt-cross-owner-3"
    cross_observation = cycle_ledger.build_unchanged_target_observation(
        observation_id="cross-owner-registry-observation",
        attempt_identity=cross_attempt,
        target_ref="registry_projection",
        state_status="present",
        before_revision_id=sibling_state["resulting_revision_id"],
        current_revision_id=sibling_state["resulting_revision_id"],
        before_state_digest=sibling_state["payload_digest"],
        current_state_digest=sibling_state["payload_digest"],
    )
    cross = final_candidate(
        cycle_id,
        cross_attempt,
        expected_receipt=second["receipt"],
    )
    cross["durable_state_candidate"] = (
        cycle_ledger.build_no_durable_state_change_candidate(
            attempt_identity=cross_attempt,
            reason_id="validation-has-no-durable-axis-change",
            evidence=cycle_ledger.build_no_change_evidence(
                evidence_id="cross-owner-evidence",
                attempt_identity=cross_attempt,
                target_observations=[cross_observation],
            ),
        )
    )
    with pytest.raises(
        cycle_ledger.FinalizationConflictError,
        match="current owner projection",
    ):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, cross)
    assert pointer_path.read_bytes() == pointer_before


def test_finalization_happy_path_is_content_bound_and_exact_retry_is_idempotent(
    tmp_path: Path,
) -> None:
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
    assert (
        first["authoritative_projection"]
        == first["snapshot"]["authoritative_projection"]
    )
    assert receipt["attempt_revision"] == 1
    assert receipt["supersedes_revision"] is None
    assert receipt["state_commit_status"] == "committed"
    assert receipt["authoritative_final"] == "success"
    assert (
        hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
        == receipt["finalization_token"]
    )
    assert receipt["snapshot_sha256"] == receipt["finalization_token"]
    verified = cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, receipt)
    assert verified["valid"] is True
    assert (
        verified["snapshot"]["authoritative_projection_digest"]
        == receipt["authoritative_projection_digest"]
    )
    loaded = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    assert loaded["valid"] is True
    assert loaded["durable_state_candidate"] == candidate["durable_state_candidate"]
    assert loaded["receipt"] == receipt
    assert len(list(snapshot_path.parent.glob("*.json"))) == 1

    trace_only_retry = {
        **candidate,
        "intermediate_observation": {
            "checked_at": "trace_B",
            "family_label": "family_B",
        },
    }
    trace_only_repeated = cycle_ledger.finalize_candidate(
        tmp_path, cycle_id, trace_only_retry
    )
    assert trace_only_repeated["idempotent"] is True
    assert trace_only_repeated["receipt"] == receipt
    assert len(list(snapshot_path.parent.glob("*.json"))) == 1


def test_same_attempt_correction_supersedes_revision_and_preserves_task_pass_goal_failure(
    tmp_path: Path,
) -> None:
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
        registry_updates={
            "semantic_progress": False,
            "authoritative_semantic_progress": False,
            "goal_productive": False,
            "progress_verdict": "no_progress",
        },
    )
    corrected_candidate["intermediate_observation"] = {
        "evidence_id": "evidence_intermediate_A",
        "semantic_progress": True,
        "progress_verdict": "advanced",
    }
    contradictory = final_candidate(
        cycle_id,
        "attempt_B",
        expected_receipt=first["receipt"],
        goal_status="fail",
        state_marker="state_B",
        registry_updates={
            "semantic_progress": True,
            "authoritative_semantic_progress": False,
            "goal_productive": False,
            "progress_verdict": "no_progress",
        },
    )
    with pytest.raises(
        ValueError, match="contradicts the final artifact semantic verdict"
    ):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, contradictory)
    assert (
        cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)["receipt"]
        == first["receipt"]
    )

    corrected = cycle_ledger.finalize_candidate(tmp_path, cycle_id, corrected_candidate)
    receipt = corrected["receipt"]
    projection = corrected["snapshot"]["authoritative_projection"]
    registry_projection = corrected["snapshot"]["post_write_projection"][
        "registry_projection"
    ]["payload"]

    assert receipt["attempt_revision"] == 2
    assert receipt["supersedes_revision"] == 1
    assert (
        receipt["supersedes_finalization_token"]
        == first["receipt"]["finalization_token"]
    )
    assert receipt["authoritative_final"] == "failure"
    assert projection["task_acceptance_verdict"]["status"] == "pass"
    assert projection["goal_readiness_verdict"]["status"] == "fail"
    assert registry_projection["semantic_progress"] is False
    assert registry_projection["goal_productive"] is False
    assert registry_projection["progress_verdict"] == "no_progress"
    assert "intermediate_observation" not in corrected["snapshot"]
    with pytest.raises(ValueError, match="stale"):
        cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, first["receipt"])
    assert (
        cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, receipt)["valid"]
        is True
    )


def test_finalization_rejects_source_metadata_before_any_durable_publication(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-final-private"
    initialize_with_context(tmp_path, cycle_id, task_id="task_private")
    with pytest.raises(ValueError, match="unregistered schema fields"):
        cycle_ledger.build_durable_operation(
            target_ref="registry_projection",
            operation_kind="replace_projection",
            attempt_identity="attempt_private",
            payload_schema_id="registry-projection-v1",
            payload={
                "artifact_id": "artifact_A",
                "source_path": "source/private_A.txt",
                "direct_quote": "private body A",
            },
        )

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


def test_finalization_verifies_typed_operation_hashes_and_unique_targets(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-final-operation-binding"
    initialize_with_context(tmp_path, cycle_id, task_id="task_operation_binding")
    candidate = final_candidate(cycle_id, "attempt_operation_binding")
    payload = {"artifact_id": "artifact_A"}
    operation = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt_operation_binding",
        payload_schema_id="registry-projection-v1",
        payload=payload,
    )
    durable_candidate = cycle_ledger.build_typed_operations_candidate(
        producer="producer_A",
        attempt_identity="attempt_operation_binding",
        operations=[operation],
    )
    candidate["durable_state_candidate"] = durable_candidate

    finalized = cycle_ledger.finalize_candidate(tmp_path, cycle_id, candidate)
    assert finalized["receipt"]["authoritative_final"] == "success"

    missing_hash_cycle_id = "cycle-final-operation-missing-hash"
    initialize_with_context(
        tmp_path, missing_hash_cycle_id, task_id="task_operation_missing_hash"
    )
    missing_hash = final_candidate(
        missing_hash_cycle_id, "attempt_operation_missing_hash"
    )
    missing_hash_operation = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt_operation_missing_hash",
        payload_schema_id="registry-projection-v1",
        payload=payload,
    )
    missing_hash_operation.pop("payload_digest")
    missing_hash["durable_state_candidate"] = (
        cycle_ledger.build_typed_operations_candidate(
            producer="producer_A",
            attempt_identity="attempt_operation_missing_hash",
            operations=[missing_hash_operation],
        )
    )
    with pytest.raises(ValueError, match="fields are invalid"):
        cycle_ledger.finalize_candidate(tmp_path, missing_hash_cycle_id, missing_hash)
    assert not cycle_ledger.current_finalization_path(
        tmp_path, missing_hash_cycle_id
    ).exists()

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
    candidate_hash_operation = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt_operation_missing_candidate_hash",
        payload_schema_id="registry-projection-v1",
        payload=payload,
    )
    missing_candidate_hash["durable_state_candidate"] = (
        cycle_ledger.build_typed_operations_candidate(
            producer="producer_A",
            attempt_identity="attempt_operation_missing_candidate_hash",
            operations=[candidate_hash_operation],
        )
    )
    missing_candidate_hash["durable_state_candidate"].pop("candidate_sha256")
    with pytest.raises(ValueError, match="candidate fields"):
        cycle_ledger.finalize_candidate(
            tmp_path,
            missing_candidate_hash_cycle_id,
            missing_candidate_hash,
        )
    assert not cycle_ledger.current_finalization_path(
        tmp_path, missing_candidate_hash_cycle_id
    ).exists()

    tampered_cycle_id = "cycle-final-operation-tamper"
    initialize_with_context(
        tmp_path, tampered_cycle_id, task_id="task_operation_tamper"
    )
    tampered = final_candidate(tampered_cycle_id, "attempt_operation_tamper")
    tampered_operation = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt_operation_tamper",
        payload_schema_id="registry-projection-v1",
        payload=payload,
    )
    tampered_operation["payload"] = {"artifact_id": "artifact_B"}
    tampered["durable_state_candidate"] = cycle_ledger.build_typed_operations_candidate(
        producer="producer_A",
        attempt_identity="attempt_operation_tamper",
        operations=[tampered_operation],
    )
    with pytest.raises(ValueError, match="payload digest mismatch"):
        cycle_ledger.finalize_candidate(tmp_path, tampered_cycle_id, tampered)
    assert not cycle_ledger.current_finalization_path(
        tmp_path, tampered_cycle_id
    ).exists()

    duplicate_cycle_id = "cycle-final-operation-duplicate"
    initialize_with_context(
        tmp_path, duplicate_cycle_id, task_id="task_operation_duplicate"
    )
    duplicate = final_candidate(duplicate_cycle_id, "attempt_operation_duplicate")
    first_duplicate = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt_operation_duplicate",
        payload_schema_id="registry-projection-v1",
        payload=payload,
    )
    second_duplicate = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt_operation_duplicate",
        payload_schema_id="registry-projection-v1",
        payload={"artifact_id": "artifact_B"},
        depends_on_operation_ids=[first_duplicate["operation_id"]],
    )
    duplicate["durable_state_candidate"] = (
        cycle_ledger.build_typed_operations_candidate(
            producer="producer_A",
            attempt_identity="attempt_operation_duplicate",
            operations=[first_duplicate, second_duplicate],
        )
    )
    with pytest.raises(ValueError, match="target_ref is duplicated"):
        cycle_ledger.finalize_candidate(tmp_path, duplicate_cycle_id, duplicate)
    assert not cycle_ledger.current_finalization_path(
        tmp_path, duplicate_cycle_id
    ).exists()


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
    operations: list[dict[str, Any]] = []
    for target_ref, operation_kind, payload_schema_id, payload in (
        (
            "registry_projection",
            "replace_projection",
            "registry-projection-v1",
            {"artifact_id": "artifact-C"},
        ),
        (
            "ledger_projection",
            "append_projection",
            "ledger-projection-v1",
            {"rows": [{"evidence_id": "evidence-C"}]},
        ),
        (
            "dedup_symbol_registry",
            "replace_projection",
            "dedup-symbol-registry-v1",
            {
                "rows": [
                    {
                        "symbol": "symbol-C",
                        "scope": "workflow_loop",
                        "occurrence_count": 1,
                        "observed_output_classes": ["no_delta"],
                        "last_observed_output_class": "no_delta",
                        "last_observed_material_delta": 0,
                        "status": "seen",
                    }
                ]
            },
        ),
    ):
        operations.append(
            cycle_ledger.build_durable_operation(
                target_ref=target_ref,
                operation_kind=operation_kind,
                attempt_identity="attempt_C",
                payload_schema_id=payload_schema_id,
                payload=payload,
                expected_revision_id=first["receipt"]["target_revision_ids"].get(
                    target_ref
                ),
                depends_on_operation_ids=(
                    [operations[-1]["operation_id"]] if operations else []
                ),
            )
        )
    correction["durable_state_candidate"] = (
        cycle_ledger.build_typed_operations_candidate(
            producer="cycle-ledger-test",
            attempt_identity="attempt_C",
            operations=operations,
        )
    )
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
    assert (
        cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, first["receipt"])[
            "valid"
        ]
        is True
    )
    still_current = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    assert (
        still_current["durable_state_candidate"]
        == final_candidate(
            cycle_id,
            "attempt_C",
        )["durable_state_candidate"]
    )
    monkeypatch.setattr(cycle_ledger, "atomic_write_text", original_atomic_write)
    recovered = cycle_ledger.finalize_candidate(tmp_path, cycle_id, correction)
    assert recovered["receipt"]["attempt_revision"] == 2
    assert recovered["receipt"]["authoritative_final"] == "failure"
    assert (
        cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)[
            "durable_state_candidate"
        ]
        == correction["durable_state_candidate"]
    )
    assert (
        len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json")))
        == 2
    )


def test_snapshot_is_reloaded_before_authoritative_pointer_switch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = "cycle-final-snapshot-reload"
    initialize_with_context(tmp_path, cycle_id, task_id="task_snapshot_reload")
    pointer_path = cycle_ledger.current_finalization_path(tmp_path, cycle_id)

    def corrupt_immutable_write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}")

    monkeypatch.setattr(cycle_ledger, "immutable_write_bytes", corrupt_immutable_write)
    with pytest.raises(ValueError, match="snapshot reload mismatch"):
        cycle_ledger.finalize_candidate(
            tmp_path,
            cycle_id,
            final_candidate(cycle_id, "attempt_snapshot_reload"),
        )

    assert not pointer_path.exists()


def test_target_revision_cas_conflict_preserves_pending_attempt_memory(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-final-target-cas"
    initialize_with_context(tmp_path, cycle_id, task_id="task_target_cas")
    first = cycle_ledger.finalize_candidate(
        tmp_path, cycle_id, final_candidate(cycle_id, "attempt_target_cas")
    )
    stale = final_candidate(
        cycle_id,
        "attempt_target_cas",
        expected_receipt=first["receipt"],
        state_marker="state_target_cas_next",
    )
    stale_operation = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt_target_cas",
        payload_schema_id="registry-projection-v1",
        payload={"artifact_id": "state_target_cas_next"},
        expected_revision_id="stale-target-revision",
    )
    stale["durable_state_candidate"] = cycle_ledger.build_typed_operations_candidate(
        producer="cycle-ledger-test",
        attempt_identity="attempt_target_cas",
        operations=[stale_operation],
    )

    with pytest.raises(
        cycle_ledger.FinalizationConflictError,
        match="expected target revision",
    ):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, stale)

    current = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    assert (
        current["receipt"]["finalization_token"]
        == first["receipt"]["finalization_token"]
    )
    pending = cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id)
    assert len(pending) == 1
    assert pending[0]["attempt_memory_disposition"] == "pending_conflict"


def test_stale_cas_and_tampered_receipt_fail_closed_without_publishing(
    tmp_path: Path,
) -> None:
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
    snapshot_count = len(
        list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json"))
    )

    with pytest.raises(ValueError, match="does not match current pointer"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, stale)
    assert (
        len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json")))
        == snapshot_count
    )
    pending = cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id)
    assert len(pending) == 1
    assert pending[0]["state_commit_status"] == "recovery_required"
    assert pending[0]["attempt_memory_disposition"] == "pending_conflict"
    assert (
        pending[0]["candidate_material"]["durable_state_candidate"]
        == stale["durable_state_candidate"]
    )

    recovered_candidate = json.loads(json.dumps(stale))
    recovered_candidate.update(
        {
            "expected_previous_revision": first["receipt"]["attempt_revision"],
            "expected_previous_attempt_id": first["receipt"]["attempt_id"],
            "expected_previous_finalization_token": first["receipt"][
                "finalization_token"
            ],
        }
    )
    recovered = cycle_ledger.finalize_candidate(tmp_path, cycle_id, recovered_candidate)
    assert recovered["receipt"]["attempt_revision"] == 2
    assert len(recovered["merged_pending_conflicts"]) == 1
    assert (
        recovered["merged_pending_conflicts"][0]["attempt_memory_disposition"]
        == "merged"
    )
    assert cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id) == []

    tampered = dict(first["receipt"])
    tampered["authoritative_final"] = "failure"
    with pytest.raises(ValueError, match="receipt hash mismatch"):
        cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, tampered)
    with pytest.raises(ValueError, match="stale"):
        cycle_ledger.verify_finalization_receipt(tmp_path, cycle_id, first["receipt"])


def test_exact_retry_finishes_pending_merge_after_pointer_publication_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle_id = "cycle-final-replay-merge"
    initialize_with_context(tmp_path, cycle_id, task_id="task-replay-merge")
    first = cycle_ledger.finalize_candidate(
        tmp_path,
        cycle_id,
        final_candidate(cycle_id, "attempt-replay-merge"),
    )
    stale = final_candidate(
        cycle_id,
        "attempt-replay-merge",
        expected_receipt=first["receipt"],
        state_marker="state-replay-merge",
    )
    stale["expected_previous_finalization_token"] = "0" * 64
    with pytest.raises(cycle_ledger.FinalizationConflictError):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, stale)

    recovered_candidate = json.loads(json.dumps(stale))
    recovered_candidate.update(
        {
            "expected_previous_revision": first["receipt"]["attempt_revision"],
            "expected_previous_attempt_id": first["receipt"]["attempt_id"],
            "expected_previous_finalization_token": first["receipt"][
                "finalization_token"
            ],
        }
    )
    original_merge = finalization_publication.merge_matching_pending_conflicts_unlocked
    crashed = False

    def crash_before_pending_merge(
        *args: object, **kwargs: object
    ) -> list[dict[str, Any]]:
        nonlocal crashed
        if not crashed:
            crashed = True
            raise RuntimeError("simulated crash before pending-conflict merge")
        return original_merge(*args, **kwargs)

    monkeypatch.setattr(
        finalization_publication,
        "merge_matching_pending_conflicts_unlocked",
        crash_before_pending_merge,
    )
    with pytest.raises(RuntimeError, match="before pending-conflict merge"):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, recovered_candidate)

    pointer_path = cycle_ledger.current_finalization_path(tmp_path, cycle_id)
    pointer_after_crash = pointer_path.read_bytes()
    current_after_crash = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    committed_token = current_after_crash["receipt"]["finalization_token"]
    snapshot_count = len(
        list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json"))
    )
    assert committed_token != first["receipt"]["finalization_token"]
    assert (
        len(cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id)) == 1
    )

    replay = cycle_ledger.finalize_candidate(tmp_path, cycle_id, recovered_candidate)

    assert replay["idempotent"] is True
    assert replay["receipt"]["finalization_token"] == committed_token
    assert len(replay["merged_pending_conflicts"]) == 1
    assert (
        replay["merged_pending_conflicts"][0]["attempt_memory_disposition"] == "merged"
    )
    assert pointer_path.read_bytes() == pointer_after_crash
    assert cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id) == []
    assert (
        len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json")))
        == snapshot_count
    )


def test_concurrent_corrections_publish_one_current_revision_and_preserve_history(
    tmp_path: Path,
) -> None:
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
            return "published", cycle_ledger.finalize_candidate(
                tmp_path, cycle_id, candidate
            )
        except ValueError as exc:
            return "rejected", str(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, candidates))

    assert sorted(status for status, _ in outcomes) == ["published", "rejected"]
    assert any(
        "does not match current pointer" in str(value)
        for status, value in outcomes
        if status == "rejected"
    )
    current = cycle_ledger.load_current_finalized_state(tmp_path, cycle_id)
    assert current["receipt"]["attempt_revision"] == 2
    assert current["receipt"]["supersedes_revision"] == 1
    assert (
        len(list(cycle_ledger.finalizations_dir(tmp_path, cycle_id).glob("*.json")))
        == 2
    )


def test_pending_retirement_requires_content_bound_rationale_and_loader_rechecks_it(
    tmp_path: Path,
) -> None:
    cycle_id = "cycle-final-retirement"
    initialize_with_context(tmp_path, cycle_id, task_id="task_retirement")
    first = cycle_ledger.finalize_candidate(
        tmp_path, cycle_id, final_candidate(cycle_id, "attempt_retirement")
    )
    stale = final_candidate(
        cycle_id,
        "attempt_retirement",
        expected_receipt=first["receipt"],
        state_marker="state_retirement",
    )
    stale["expected_previous_finalization_token"] = "0" * 64
    with pytest.raises(cycle_ledger.FinalizationConflictError):
        cycle_ledger.finalize_candidate(tmp_path, cycle_id, stale)
    pending_id = cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id)[
        0
    ]["pending_conflict_id"]

    with pytest.raises(ValueError, match="full SHA-256"):
        cycle_ledger.resolve_pending_finalization_conflict(
            tmp_path,
            cycle_id,
            pending_id,
            disposition="retired",
            resolution_evidence_id="evidence-retirement-A",
            resolution_evidence_digest="not-a-digest",
            resolution_evidence_ref="retirement-review-A",
            resolution_rationale_id="conflicting-target-owned-externally",
        )

    resolution = cycle_ledger.resolve_pending_finalization_conflict(
        tmp_path,
        cycle_id,
        pending_id,
        disposition="retired",
        resolution_evidence_id="evidence-retirement-A",
        resolution_evidence_digest="a" * 64,
        resolution_evidence_ref="retirement-review-A",
        resolution_rationale_id="conflicting-target-owned-externally",
    )
    assert len(resolution["resolution_record_digest"]) == 64
    assert cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id) == []

    resolution_path = tmp_path / resolution["resolution_ref"]
    tampered = json.loads(resolution_path.read_text(encoding="utf-8"))
    tampered["resolution_rationale_id"] = "unbound-rationale"
    resolution_path.write_bytes(cycle_ledger.canonical_json_bytes(tampered))
    with pytest.raises(ValueError, match="resolution binding is invalid"):
        cycle_ledger.load_pending_finalization_conflicts(tmp_path, cycle_id)
