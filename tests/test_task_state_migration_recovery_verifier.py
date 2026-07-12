from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from task_state_migration_verifier_fixtures import (
    assert_forward_recovery_fails,
    assert_pass_result,
    build_fixture_plan,
    committed_fixture,
    crash_fixture,
    make_workspace,
    migration,
    mutate_graph_target,
    observe_and_recover,
    rehash_observation,
    sha,
    task_index,
    verifier,
    verify,
    write_json,
)


@pytest.mark.parametrize(
    (
        "crash_point",
        "journal_state",
        "publication_state",
        "sealed",
        "anchor",
        "receipt",
        "marker",
        "rendered",
        "live_projection",
        "forward_required",
        "replay_noop",
        "receipt_recovery_status",
    ),
    [
        (
            "after_prepare",
            "prepared",
            "pre_seal_incomplete",
            False,
            False,
            False,
            False,
            False,
            False,
            True,
            False,
            "absent",
        ),
        (
            "after_partial_suffix",
            "partial_suffix",
            "pre_seal_incomplete",
            False,
            False,
            False,
            False,
            False,
            False,
            True,
            False,
            "absent",
        ),
        (
            "after_suffix",
            "sealed",
            "post_seal_incomplete",
            True,
            False,
            False,
            False,
            False,
            False,
            True,
            False,
            "absent",
        ),
        (
            "after_receipt",
            "receipt_written",
            "post_seal_incomplete",
            True,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
            "not_required",
        ),
        (
            "after_anchor",
            "receipt_anchored",
            "post_seal_incomplete",
            True,
            True,
            True,
            False,
            True,
            False,
            True,
            False,
            "not_required",
        ),
        (
            "after_completion_marker_before_render",
            "committed",
            "committed_render_pending",
            True,
            True,
            True,
            True,
            True,
            False,
            True,
            False,
            "not_required",
        ),
        (
            "after_render",
            "committed",
            "committed",
            True,
            True,
            True,
            True,
            True,
            True,
            False,
            True,
            "not_required",
        ),
    ],
)
def test_recovery_phase_matrix_is_observed_and_verified_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
    journal_state: str,
    publication_state: str,
    sealed: bool,
    anchor: bool,
    receipt: bool,
    marker: bool,
    rendered: bool,
    live_projection: bool,
    forward_required: bool,
    replay_noop: bool,
    receipt_recovery_status: str,
) -> None:
    fixture, plan, _plan_path = crash_fixture(
        tmp_path, monkeypatch, crash_point=crash_point
    )
    observation = verifier.inspect_transaction_boundary(
        fixture["root"], plan["migration_id"]
    )

    assert observation["journal_state"] == journal_state
    assert observation["publication_state"] == publication_state
    assert observation["sealed_boundary_present"] is sealed
    assert observation["anchor_present"] is anchor
    assert observation["receipt_present"] is receipt
    assert observation["completion_marker_present"] is marker
    assert observation["rendered_snapshot_present"] is rendered
    assert observation["live_projection_present"] is live_projection
    assert observation["forward_recovery_required"] is forward_required
    assert observation["exact_replay_noop_eligible"] is replay_noop
    assert observation["receipt_recovery_status"] == receipt_recovery_status
    assert observation["read_only"] is True

    if forward_required:
        migration.recover_transaction(fixture["root"], plan["migration_id"])
        result = verify(
            fixture["root"],
            fixture["root"] / plan["receipt_ref"],
            fixture["mapping"],
            recovery_status="forward_completed",
            recovery_observation=observation,
            recovery_observation_sha256=observation["observation_sha256"],
        )
        assert_pass_result(result)
        assert result["recovery_status"] == "forward_completed"
    else:
        result = verify(
            fixture["root"],
            fixture["root"] / plan["receipt_ref"],
            fixture["mapping"],
            recovery_status="not_required",
        )
        assert_pass_result(result)


@pytest.mark.parametrize("outside_change", ["file_mutation", "empty_directory_addition"])
def test_forward_recovery_rejects_every_outside_tree_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outside_change: str,
) -> None:
    fixture, plan, _plan_path = crash_fixture(tmp_path, monkeypatch)
    sentinel = fixture["root"] / "protected-nonowned-sentinel.txt"
    if outside_change == "file_mutation":
        sentinel.write_text("before\n", encoding="utf-8")
    observation = verifier.inspect_transaction_boundary(
        fixture["root"], plan["migration_id"]
    )
    if outside_change == "file_mutation":
        sentinel.write_text("after unauthorized mutation\n", encoding="utf-8")
    else:
        (fixture["root"] / "new-empty-unowned-directory").mkdir()
    migration.recover_transaction(fixture["root"], plan["migration_id"])

    assert_forward_recovery_fails(
        fixture,
        fixture["root"] / plan["receipt_ref"],
        observation,
    )


def test_forward_recovery_rejects_missing_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, plan, _plan_path = crash_fixture(tmp_path, monkeypatch)
    migration.recover_transaction(fixture["root"], plan["migration_id"])

    with pytest.raises(verifier.VerificationError):
        verify(
            fixture["root"],
            fixture["root"] / plan["receipt_ref"],
            fixture["mapping"],
            recovery_status="forward_completed",
        )


def test_after_prepare_foreign_ledger_tail_cannot_be_observed_as_recoverable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = make_workspace(tmp_path)
    plan_path = tmp_path / "caller-plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    monkeypatch.setenv("TASK_STATE_MIGRATION_CRASH_AT", "after_prepare")
    with pytest.raises(RuntimeError, match="injected crash"):
        migration.apply_plan(
            fixture["root"],
            plan_path,
            sha(plan_path.read_bytes()),
            sha(fixture["prefix"]),
        )
    monkeypatch.delenv("TASK_STATE_MIGRATION_CRASH_AT")
    fixture["index"].write_bytes(
        fixture["prefix"] + b'{"event":"foreign-unowned-tail"}\n'
    )
    with pytest.raises(verifier.VerificationError):
        verifier.inspect_transaction_boundary(
            fixture["root"],
            plan["migration_id"],
            expected_mapping_raw=fixture["mapping"],
            expected_recovery_status="forward_completed",
        )


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("journal_state", "prepared"),
        ("journal_sha256", "0" * 64),
        ("journal_base_sha256", "0" * 64),
        ("index_byte_length", lambda value: value + 1),
        ("index_sha256", "0" * 64),
        ("sealed_boundary_present", True),
        ("anchor_present", True),
        ("receipt_present", True),
        ("completion_marker_present", True),
    ],
)
def test_rehashed_recovery_observation_semantic_field_forgery_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    forged_value: Any,
) -> None:
    fixture, _plan, receipt, observation = observe_and_recover(tmp_path, monkeypatch)
    value = forged_value(observation[field]) if callable(forged_value) else forged_value
    forged = rehash_observation(observation, field, value)
    assert forged["observation_sha256"] != observation["observation_sha256"]
    assert_forward_recovery_fails(fixture, receipt, forged)


@pytest.mark.parametrize(
    "field",
    [
        "transaction_id",
        "plan_sha256",
        "recovery_owned_write_set_sha256",
        "immutable_transaction_sha256",
        "protected_anchor_aggregate_sha256",
        "outside_owned_tree_sha256",
    ],
)
def test_rehashed_recovery_observation_identity_graph_binding_forgery_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    fixture, _plan, receipt, observation = observe_and_recover(tmp_path, monkeypatch)
    forged = rehash_observation(observation, field, "0" * 64)
    assert_forward_recovery_fails(fixture, receipt, forged)


def test_recovery_observation_requires_the_external_sha_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, _plan, receipt, observation = observe_and_recover(tmp_path, monkeypatch)
    assert_forward_recovery_fails(
        fixture, receipt, observation, expected_sha="0" * 64
    )


def test_forward_recovery_rejects_unauthorized_live_projection_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, _plan, receipt, observation = observe_and_recover(tmp_path, monkeypatch)
    (fixture["root"] / ".task/index.md").write_text(
        "# unauthorized recovered projection\n", encoding="utf-8"
    )
    assert_forward_recovery_fails(fixture, receipt, observation)


@pytest.mark.parametrize(
    "target", ["plan", "prepare_journal", "receipt", "completion_marker"]
)
def test_forward_recovery_has_no_immutable_transaction_or_publication_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    fixture, plan, receipt, observation = observe_and_recover(tmp_path, monkeypatch)
    mutate_graph_target(fixture, plan, receipt, target)
    assert_forward_recovery_fails(fixture, receipt, observation)


def test_result_names_historical_and_current_ids_and_body_free_evidence_refs(
    tmp_path: Path,
) -> None:
    fixture, plan, receipt, expected_mapping = committed_fixture(tmp_path)
    current_task_id = "task-successor-evidence-fixture"
    current_pack_id = "pack-successor-evidence-fixture"
    current_pack = fixture["root"] / ".task/task_pack/evidence-successor.json"
    write_json(
        current_pack,
        {
            "schema_version": 1,
            "pack_id": current_pack_id,
            "status": "active",
            "items": [],
        },
    )
    current_task = fixture["root"] / "task.md"
    current_task.write_text("# BODY-MUST-NOT-ENTER-EVIDENCE-REF\n", encoding="utf-8")
    events = [
        migration._versioned(
            {
                "event": "upsert",
                "id": fixture["task_id"],
                "status": "superseded",
                "updated_at": "2026-07-12T04:00:00+09:00",
            }
        ),
        migration._versioned(
            {
                "event": "upsert",
                "id": fixture["pack_id"],
                "status": "superseded",
                "updated_at": "2026-07-12T04:00:01+09:00",
            }
        ),
        migration._versioned(
            {
                "event": "upsert",
                "id": current_pack_id,
                "type": "task_pack",
                "status": "active",
                "path": ".task/task_pack/evidence-successor.json",
                "title": "Successor evidence pack",
                "content_sha256": sha(current_pack.read_bytes()),
                "updated_at": "2026-07-12T04:00:02+09:00",
            }
        ),
        migration._versioned(
            {
                "event": "upsert",
                "id": current_task_id,
                "type": "task",
                "status": "active",
                "path": "task.md",
                "title": "Successor evidence task",
                "content_sha256": sha(current_task.read_bytes()),
                "updated_at": "2026-07-12T04:00:03+09:00",
                "links": [{"rel": "pack_for_task", "id": current_pack_id}],
            }
        ),
    ]
    for event in events:
        task_index.append_event(fixture["root"], event)

    result = verify(fixture["root"], receipt, expected_mapping)
    assert_pass_result(result)
    assert result["historical_boundary_task_id"] == (
        f"task-sha256-{sha(fixture['task_id'].encode())}"
    )
    assert result["historical_boundary_pack_id"] == (
        f"pack-sha256-{sha(fixture['pack_id'].encode())}"
    )
    assert result["historical_boundary_evidence_ref"] == (
        f"{plan['plan_snapshot_ref']}#anchors"
    )
    assert result["post_migration_current_task_id"] == (
        f"task-sha256-{sha(current_task_id.encode())}"
    )
    assert result["post_migration_current_pack_id"] == (
        f"pack-sha256-{sha(current_pack_id.encode())}"
    )
    assert result["post_migration_current_evidence_ref"] == (
        ".task/index.jsonl#post_anchor_projection"
    )
    assert "BODY-MUST-NOT-ENTER-EVIDENCE-REF" not in repr(result)
    assert fixture["task_id"] not in repr(result)
    assert fixture["pack_id"] not in repr(result)
    assert current_task_id not in repr(result)
    assert current_pack_id not in repr(result)
