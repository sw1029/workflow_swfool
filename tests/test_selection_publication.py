from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from selection_publication_legacy_support import prepare_legacy_publication

from orchestrate_task_cycle import selection_publication as publication
from orchestrate_task_cycle.selection_publication import (
    pending_transaction_ids,
    prepare_drift_reconciliation,
    prepare_publication,
    publication_status,
    publish_prepared,
    recover_publications,
)


public_prepare_publication = prepare_publication
prepare_publication = prepare_legacy_publication


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _target(
    role: str, path: str, before: bytes | None, after: bytes
) -> dict[str, object]:
    return {
        "role": role,
        "target_ref": path,
        "before_sha256": _sha(before) if before is not None else None,
        "after_payload_b64": base64.b64encode(after).decode("ascii"),
    }


def _plan(targets: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "selection_publication_plan",
        "selection_id": "selection-A",
        "source_decision_id": "derive-A",
        "source_decision_sha256": "a" * 64,
        "targets": targets,
    }


def _named_plan(
    before: bytes | None,
    after: bytes,
    suffix: str,
) -> dict[str, object]:
    plan = _plan([_target("task_alias", "task.md", before, after)])
    plan["selection_id"] = f"selection-{suffix}"
    plan["source_decision_id"] = f"derive-{suffix}"
    plan["source_decision_sha256"] = hashlib.sha256(
        f"decision-{suffix}".encode("utf-8")
    ).hexdigest()
    return plan


def _write_legacy_prepare(
    root: Path, plan: dict[str, object]
) -> tuple[str, dict[str, object], Path]:
    normalized = publication._normalize_plan(root, plan)
    transaction_id = "selection-" + publication._sha256_bytes(
        publication._canonical_json(normalized)
    )
    prepare = {**normalized, "transaction_id": transaction_id}
    path = publication._prepare_path(root, transaction_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(publication._display_json(prepare))
    return transaction_id, prepare, path


def _write_legacy_receipt(
    root: Path,
    transaction_id: str,
    prepare: dict[str, object],
    prepare_path: Path,
) -> None:
    targets = [
        {
            key: target.get(key)
            for key in ("role", "target_ref", "before_sha256", "after_sha256")
        }
        for target in prepare["targets"]  # type: ignore[index]
    ]
    receipt = {
        "schema_version": 1,
        "kind": "selection_publication_receipt",
        "status": "committed",
        "transaction_id": transaction_id,
        "selection_id": prepare["selection_id"],
        "source_decision_id": prepare["source_decision_id"],
        "source_decision_sha256": prepare["source_decision_sha256"],
        "prepare_ref": prepare_path.relative_to(root).as_posix(),
        "prepare_sha256": _sha(prepare_path.read_bytes()),
        "targets": targets,
        "authoritative_pointer_role": "task_alias",
        "all_targets_verified_before_receipt": True,
    }
    receipt_path = publication._receipt_path(root, transaction_id)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_bytes(publication._display_json(receipt))


def test_public_v1_prepare_rejects_new_inline_write_without_journal(
    tmp_path: Path,
) -> None:
    task = b"# task-a\n"
    (tmp_path / "task.md").write_bytes(task)

    with pytest.raises(ValueError, match="v1 new write is forbidden"):
        public_prepare_publication(
            tmp_path, _named_plan(task, b"# task-b\n", "forbidden")
        )

    transactions = tmp_path / ".task/selection_publication/transactions"
    assert not transactions.exists()


def test_selection_publication_commits_all_targets_and_replays(tmp_path: Path) -> None:
    old_task = b"# old\n"
    new_task = b"# new\n"
    old_index = b'{"id":"old"}\n'
    new_index = b'{"id":"new"}\n'
    new_log_index = b'{"path":".agent_log/2026-01-01/archive.md"}\n'
    (tmp_path / "task.md").write_bytes(old_task)
    (tmp_path / ".task").mkdir()
    (tmp_path / ".task/index.jsonl").write_bytes(old_index)
    (tmp_path / ".agent_log/2026-01-01").mkdir(parents=True)
    (tmp_path / ".agent_log/2026-01-01/archive.md").write_bytes(old_task)
    (tmp_path / ".agent_log/index.jsonl").write_bytes(new_log_index)
    plan = _plan(
        [
            _target("task_alias", "task.md", old_task, new_task),
            _target("task_index_jsonl", ".task/index.jsonl", old_index, new_index),
            _target(
                "past_task_archive",
                ".agent_log/2026-01-01/archive.md",
                old_task,
                old_task,
            ),
            _target(
                "agent_log_index_jsonl",
                ".agent_log/index.jsonl",
                new_log_index,
                new_log_index,
            ),
        ]
    )

    prepared = prepare_publication(tmp_path, plan)
    receipt = publish_prepared(tmp_path, prepared["transaction_id"])
    replay = publish_prepared(tmp_path, prepared["transaction_id"])

    assert (tmp_path / "task.md").read_bytes() == new_task
    assert (tmp_path / ".task/index.jsonl").read_bytes() == new_index
    assert (tmp_path / ".agent_log/2026-01-01/archive.md").read_bytes() == old_task
    assert (tmp_path / ".agent_log/index.jsonl").read_bytes() == new_log_index
    assert receipt["status"] == "committed"
    assert receipt["authoritative_selection_published"] is True
    assert replay["receipt_sha256"] == receipt["receipt_sha256"]
    assert pending_transaction_ids(tmp_path) == []
    assert publication_status(tmp_path)["current_head"]["status"] == "current"


def test_historical_owner_projection_reopens_after_later_owner_append(
    tmp_path: Path,
) -> None:
    old_task = b"# old\n"
    new_task = b"# new\n"
    archive = b"# archived task\n"
    original_index = b'{"path":".agent_log/2026-01-01/archive.md"}\n'
    appended_index = original_index + b'{"path":".agent_log/2026-01-02/later.md"}\n'
    (tmp_path / "task.md").write_bytes(old_task)
    (tmp_path / ".agent_log/2026-01-01").mkdir(parents=True)
    (tmp_path / ".agent_log/2026-01-01/archive.md").write_bytes(archive)
    (tmp_path / ".agent_log/index.jsonl").write_bytes(original_index)
    prepared = prepare_publication(
        tmp_path,
        _plan(
            [
                _target("task_alias", "task.md", old_task, new_task),
                _target(
                    "past_task_archive",
                    ".agent_log/2026-01-01/archive.md",
                    archive,
                    archive,
                ),
                _target(
                    "agent_log_index_jsonl",
                    ".agent_log/index.jsonl",
                    original_index,
                    original_index,
                ),
            ]
        ),
    )
    committed = publish_prepared(tmp_path, prepared["transaction_id"])
    (tmp_path / ".agent_log/index.jsonl").write_bytes(appended_index)

    status = publication_status(tmp_path)
    historical = publish_prepared(tmp_path, prepared["transaction_id"])

    assert status["status"] == "clear"
    assert status["current_head"]["status"] == "current"
    assert historical["receipt_sha256"] == committed["receipt_sha256"]
    assert historical["publication_authority_status"] == "historical_receipt_only"
    assert historical["mutation_performed"] is False
    assert (tmp_path / ".agent_log/index.jsonl").read_bytes() == appended_index


def test_selection_publication_drift_blocks_before_any_target_write(
    tmp_path: Path,
) -> None:
    old_task = b"# old\n"
    old_index = b"old-index\n"
    (tmp_path / "task.md").write_bytes(old_task)
    (tmp_path / ".task").mkdir()
    (tmp_path / ".task/index.jsonl").write_bytes(old_index)
    plan = _plan(
        [
            _target("task_alias", "task.md", old_task, b"# new\n"),
            _target("task_index_jsonl", ".task/index.jsonl", old_index, b"new-index\n"),
        ]
    )
    prepared = prepare_publication(tmp_path, plan)
    (tmp_path / ".task/index.jsonl").write_bytes(b"foreign-drift\n")

    with pytest.raises(ValueError, match="drifted"):
        publish_prepared(tmp_path, prepared["transaction_id"])

    assert (tmp_path / "task.md").read_bytes() == old_task
    assert (tmp_path / ".task/index.jsonl").read_bytes() == b"foreign-drift\n"
    assert publication_status(tmp_path)["status"] == "recovery_required"


def test_selection_publication_forward_recovers_partial_after_state(
    tmp_path: Path,
) -> None:
    old_task = b"# old\n"
    new_task = b"# new\n"
    old_index = b"old-index\n"
    new_index = b"new-index\n"
    (tmp_path / "task.md").write_bytes(old_task)
    (tmp_path / ".task").mkdir()
    (tmp_path / ".task/index.jsonl").write_bytes(old_index)
    plan = _plan(
        [
            _target("task_alias", "task.md", old_task, new_task),
            _target("task_index_jsonl", ".task/index.jsonl", old_index, new_index),
        ]
    )
    prepared = prepare_publication(tmp_path, plan)
    (tmp_path / ".task/index.jsonl").write_bytes(new_index)

    recovered = recover_publications(tmp_path, prepared["transaction_id"])

    assert recovered["status"] == "recovered"
    assert (tmp_path / "task.md").read_bytes() == new_task
    assert recovered["remaining_pending_transaction_ids"] == []


def test_compact_head_rejects_self_sealed_malformed_receipt(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    (tmp_path / "task.md").write_bytes(task_a)
    prepared = prepare_publication(
        tmp_path, _named_plan(task_a, task_b, "malformed-head")
    )
    publish_prepared(tmp_path, prepared["transaction_id"])
    receipt_path = publication._receipt_path(tmp_path, prepared["transaction_id"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["schema_version"] = 999
    receipt["extra"] = "self-sealed"
    receipt_path.write_bytes(publication._display_json(receipt))
    state_path = tmp_path / ".task/selection_publication/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["head"]["receipt"]["sha256"] = _sha(receipt_path.read_bytes())
    state_body = {
        key: value for key, value in state.items() if key != "state_content_sha256"
    }
    state["state_content_sha256"] = _sha(publication._canonical_json(state_body))
    state_path.write_bytes(publication._canonical_json(state))

    with pytest.raises(ValueError, match="receipt fields are invalid"):
        publication_status(tmp_path)


def test_compact_state_rejects_noncanonical_raw_bytes(tmp_path: Path) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    (tmp_path / "task.md").write_bytes(task_a)
    prepared = prepare_publication(
        tmp_path, _named_plan(task_a, task_b, "raw-state")
    )
    publish_prepared(tmp_path, prepared["transaction_id"])
    state_path = tmp_path / ".task/selection_publication/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state_path.write_bytes(publication._display_json(state))

    with pytest.raises(ValueError, match="state is non-canonical"):
        publication_status(tmp_path)


def test_pending_publication_blocks_competing_prepare_without_mutation(
    tmp_path: Path,
) -> None:
    old_task = b"# old\n"
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    (tmp_path / "task.md").write_bytes(old_task)
    plan_a = _plan([_target("task_alias", "task.md", old_task, task_a)])
    prepared_a = prepare_publication(tmp_path, plan_a)
    replay_a = prepare_publication(tmp_path, plan_a)
    plan_b = _plan([_target("task_alias", "task.md", old_task, task_b)])
    plan_b["selection_id"] = "selection-B"
    plan_b["source_decision_id"] = "derive-B"
    plan_b["source_decision_sha256"] = "b" * 64

    with pytest.raises(ValueError, match="different pending transaction"):
        prepare_publication(tmp_path, plan_b)

    assert replay_a["transaction_id"] == prepared_a["transaction_id"]
    assert pending_transaction_ids(tmp_path) == [prepared_a["transaction_id"]]
    assert (tmp_path / "task.md").read_bytes() == old_task
    recovered = recover_publications(tmp_path)
    assert recovered["remaining_pending_transaction_ids"] == []
    assert (tmp_path / "task.md").read_bytes() == task_a


def test_legacy_competing_prepares_cannot_publish_or_auto_recover(
    tmp_path: Path,
) -> None:
    old_task = b"# old\n"
    (tmp_path / "task.md").write_bytes(old_task)
    transaction_ids: list[str] = []
    for suffix, payload in (("A", b"# task-a\n"), ("B", b"# task-b\n")):
        plan = _plan([_target("task_alias", "task.md", old_task, payload)])
        plan["selection_id"] = f"selection-{suffix}"
        plan["source_decision_id"] = f"derive-{suffix}"
        normalized = publication._normalize_plan(tmp_path, plan)
        transaction_id = "selection-" + publication._sha256_bytes(
            publication._canonical_json(normalized)
        )
        prepare = {**normalized, "transaction_id": transaction_id}
        path = publication._prepare_path(tmp_path, transaction_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(publication._display_json(prepare))
        transaction_ids.append(transaction_id)

    with pytest.raises(ValueError, match="multiple pending transactions"):
        publish_prepared(tmp_path, transaction_ids[1])
    with pytest.raises(ValueError, match="state migration required"):
        recover_publications(tmp_path)

    with pytest.raises(ValueError, match="state migration required"):
        pending_transaction_ids(tmp_path)
    assert (tmp_path / "task.md").read_bytes() == old_task


def test_selection_publication_rejects_delete_or_unowned_path(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("old\n", encoding="utf-8")
    plan = _plan(
        [
            _target("task_alias", "task.md", b"old\n", b"new\n"),
            _target("task_pack_state", ".task/other.json", None, b"{}\n"),
        ]
    )

    with pytest.raises(ValueError, match="not allowed"):
        prepare_publication(tmp_path, plan)

    malformed = _plan([_target("task_alias", "task.md", b"old\n", b"new\n")])
    malformed["targets"][0].pop("after_payload_b64")
    with pytest.raises(ValueError, match="payload"):
        prepare_publication(tmp_path, malformed)

    (tmp_path / ".agent_log/2026-01-01").mkdir(parents=True)
    (tmp_path / ".agent_log/2026-01-01/archive.md").write_bytes(b"old\n")
    unindexed_archive = _plan(
        [
            _target("task_alias", "task.md", b"old\n", b"new\n"),
            _target(
                "past_task_archive",
                ".agent_log/2026-01-01/archive.md",
                b"old\n",
                b"old\n",
            ),
        ]
    )
    with pytest.raises(ValueError, match="must be published together"):
        prepare_publication(tmp_path, unindexed_archive)

    (tmp_path / ".task/task_pack").mkdir(parents=True)
    (tmp_path / ".task/task_pack/pack-A.json").write_bytes(b'{"status":"active"}\n')
    direct_pack_mutation = _plan(
        [
            _target("task_alias", "task.md", b"old\n", b"new\n"),
            _target(
                "task_pack_state",
                ".task/task_pack/pack-A.json",
                b'{"status":"active"}\n',
                b'{"status":"completed"}\n',
            ),
        ]
    )
    with pytest.raises(ValueError, match="owner-committed unchanged projection"):
        prepare_publication(tmp_path, direct_pack_mutation)


def test_uninitialized_publication_store_does_not_claim_selection_consumption(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Existing task\n", encoding="utf-8")

    status = publication_status(tmp_path)

    assert status["status"] == "clear"
    assert status["selection_journal_initialized"] is False
    assert status["selection_consumption_allowed"] is False
    assert status["selection_consumption_reason"] == "no_committed_selection"


def test_selection_publication_status_blocks_unjournaled_current_task_drift(
    tmp_path: Path,
) -> None:
    old_task = b"# old\n"
    new_task = b"# new\n"
    (tmp_path / "task.md").write_bytes(old_task)
    prepared = prepare_publication(
        tmp_path,
        _plan([_target("task_alias", "task.md", old_task, new_task)]),
    )
    publish_prepared(tmp_path, prepared["transaction_id"])
    (tmp_path / "task.md").write_bytes(b"# foreign\n")

    status = publication_status(tmp_path)

    assert status["status"] == "drift_blocked"
    assert status["selection_consumption_allowed"] is False
    assert status["current_head"]["status"] == "drifted"


def test_legacy_v1_drift_reconciliation_new_write_is_forbidden(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    task_c = b"# task-c\n"
    (tmp_path / "task.md").write_bytes(task_a)
    first = prepare_publication(
        tmp_path,
        _named_plan(task_a, task_b, "A"),
    )
    publish_prepared(tmp_path, first["transaction_id"])
    (tmp_path / "task.md").write_bytes(task_c)

    with pytest.raises(ValueError, match="v1 new write is forbidden"):
        prepare_drift_reconciliation(
            tmp_path,
            _named_plan(task_b, task_c, "reconcile"),
        )
    assert (tmp_path / "task.md").read_bytes() == task_c


def test_selection_publication_reconciliation_rejects_noncurrent_or_extra_targets(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    task_c = b"# task-c\n"
    (tmp_path / "task.md").write_bytes(task_a)
    (tmp_path / ".task").mkdir()
    (tmp_path / ".task/index.jsonl").write_bytes(b"old-index\n")
    first = prepare_publication(
        tmp_path,
        _named_plan(task_a, task_b, "A"),
    )
    publish_prepared(tmp_path, first["transaction_id"])
    (tmp_path / "task.md").write_bytes(task_c)

    with pytest.raises(ValueError, match="v1 new write is forbidden"):
        prepare_drift_reconciliation(
            tmp_path,
            _named_plan(task_b, b"# foreign\n", "wrong-current"),
        )
    extra_target_plan = _named_plan(task_b, task_c, "extra-target")
    extra_target_plan["targets"].append(
        _target(
            "task_index_jsonl",
            ".task/index.jsonl",
            b"old-index\n",
            b"new-index\n",
        )
    )
    with pytest.raises(ValueError, match="accepts only task_alias"):
        prepare_drift_reconciliation(tmp_path, extra_target_plan)


def test_selection_publication_tracks_the_unique_superseding_head(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    task_c = b"# task-c\n"
    (tmp_path / "task.md").write_bytes(task_a)
    first = prepare_publication(
        tmp_path,
        _plan([_target("task_alias", "task.md", task_a, task_b)]),
    )
    publish_prepared(tmp_path, first["transaction_id"])
    second_plan = _plan([_target("task_alias", "task.md", task_b, task_c)])
    second_plan["selection_id"] = "selection-B"
    second_plan["source_decision_id"] = "derive-B"
    second_plan["source_decision_sha256"] = "b" * 64
    second = prepare_publication(tmp_path, second_plan)
    publish_prepared(tmp_path, second["transaction_id"])

    status = publication_status(tmp_path)

    assert status["status"] == "clear"
    assert status["current_head"]["status"] == "current"
    assert status["current_head"]["head_transaction_id"] == second["transaction_id"]


def test_drifted_committed_head_blocks_new_prepare_without_journal_mutation(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    task_c = b"# task-c\n"
    (tmp_path / "task.md").write_bytes(task_a)
    first_plan = _named_plan(task_a, task_b, "A")
    first = prepare_publication(tmp_path, first_plan)
    publish_prepared(tmp_path, first["transaction_id"])
    (tmp_path / "task.md").write_bytes(task_a)
    transaction_root = tmp_path / ".task" / "selection_publication" / "transactions"
    before_transactions = sorted(path.name for path in transaction_root.iterdir())

    with pytest.raises(ValueError, match="drifted or ambiguous"):
        prepare_publication(tmp_path, _named_plan(task_a, task_c, "B"))

    assert (
        sorted(path.name for path in transaction_root.iterdir()) == before_transactions
    )
    assert (tmp_path / "task.md").read_bytes() == task_a


def test_explicit_lineage_keeps_byte_content_cycle_on_one_current_head(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    (tmp_path / "task.md").write_bytes(task_a)
    first = prepare_publication(tmp_path, _named_plan(task_a, task_b, "A"))
    first_receipt = publish_prepared(tmp_path, first["transaction_id"])
    second = prepare_publication(tmp_path, _named_plan(task_b, task_a, "B"))
    second_prepare = json.loads(
        (tmp_path / second["prepare_ref"]).read_text(encoding="utf-8")
    )
    second_receipt = publish_prepared(tmp_path, second["transaction_id"])

    assert first_receipt["predecessor_transaction_id"] is None
    assert second_prepare["predecessor_transaction_id"] == first["transaction_id"]
    assert second_receipt["predecessor_transaction_id"] == first["transaction_id"]
    status = publication_status(tmp_path)
    assert status["status"] == "clear"
    assert status["current_head"]["status"] == "current"
    assert status["current_head"]["head_transaction_id"] == second["transaction_id"]
    assert status["current_head"]["head_count"] == 1


def test_historical_publish_replay_is_read_only_and_claims_no_current_authority(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    task_c = b"# task-c\n"
    (tmp_path / "task.md").write_bytes(task_a)
    first = prepare_publication(tmp_path, _named_plan(task_a, task_b, "A"))
    first_receipt = publish_prepared(tmp_path, first["transaction_id"])
    second = prepare_publication(tmp_path, _named_plan(task_b, task_c, "B"))
    publish_prepared(tmp_path, second["transaction_id"])
    store = tmp_path / ".task" / "selection_publication"
    before_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in store.rglob("*")
        if path.is_file()
    }

    historical = publish_prepared(tmp_path, first["transaction_id"])

    after_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in store.rglob("*")
        if path.is_file()
    }
    assert historical["receipt_sha256"] == first_receipt["receipt_sha256"]
    assert historical["mutation_performed"] is False
    assert historical["authoritative_selection_published"] is False
    assert historical["current_selection_authority_claimed"] is False
    assert historical["publication_authority_status"] == "historical_receipt_only"
    assert (tmp_path / "task.md").read_bytes() == task_c
    assert after_files == before_files


def test_duplicate_transition_requires_exact_committed_replay(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    (tmp_path / "task.md").write_bytes(task_a)
    first_plan = _named_plan(task_a, task_b, "A")
    first = prepare_publication(tmp_path, first_plan)
    publish_prepared(tmp_path, first["transaction_id"])
    transactions = tmp_path / ".task" / "selection_publication" / "transactions"
    before_ids = sorted(path.name for path in transactions.iterdir())

    with pytest.raises(ValueError, match="before_sha256 must match"):
        prepare_publication(tmp_path, _named_plan(task_a, task_b, "B"))

    exact = prepare_publication(tmp_path, first_plan)
    assert exact["status"] == "already_committed"
    assert exact["transaction_id"] == first["transaction_id"]
    assert exact["mutation_performed"] is False
    assert sorted(path.name for path in transactions.iterdir()) == before_ids
    assert publication_status(tmp_path)["current_head"]["head_count"] == 1


def test_lineage_fields_are_helper_owned_and_tampering_fails_closed(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    (tmp_path / "task.md").write_bytes(task_a)
    spoofed = _named_plan(task_a, task_b, "spoof")
    spoofed["predecessor_transaction_id"] = "selection-" + "0" * 64
    with pytest.raises(ValueError, match="helper-owned"):
        prepare_publication(tmp_path, spoofed)
    assert not (tmp_path / ".task").exists()

    prepared = prepare_publication(tmp_path, _named_plan(task_a, task_b, "A"))
    prepare_path = tmp_path / prepared["prepare_ref"]
    body = json.loads(prepare_path.read_text(encoding="utf-8"))
    body["predecessor_transaction_id"] = "selection-" + "1" * 64
    prepare_path.write_bytes(publication._display_json(body))
    with pytest.raises(ValueError, match="binding has drifted"):
        publish_prepared(tmp_path, prepared["transaction_id"])
    assert (tmp_path / "task.md").read_bytes() == task_a

    receipt_root = tmp_path / "receipt-tamper"
    receipt_root.mkdir()
    (receipt_root / "task.md").write_bytes(task_a)
    committed = prepare_publication(
        receipt_root, _named_plan(task_a, task_b, "receipt")
    )
    publish_prepared(receipt_root, committed["transaction_id"])
    receipt_path = publication._receipt_path(receipt_root, committed["transaction_id"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["predecessor_transaction_id"] = "selection-" + "2" * 64
    receipt_path.write_bytes(publication._display_json(receipt))
    with pytest.raises(ValueError, match="receipt binding has drifted"):
        publish_prepared(receipt_root, committed["transaction_id"])
    assert (receipt_root / "task.md").read_bytes() == task_b


def test_exact_pending_prepare_replay_bypasses_after_state_drift_guard(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    (tmp_path / "task.md").write_bytes(task_a)
    plan = _named_plan(task_a, task_b, "pending")
    prepared = prepare_publication(tmp_path, plan)
    (tmp_path / "task.md").write_bytes(task_b)

    replay = prepare_publication(tmp_path, plan)

    assert replay["transaction_id"] == prepared["transaction_id"]
    assert replay["mutation_performed"] is False
    assert replay["recovery_required"] is True
    committed = publish_prepared(tmp_path, replay["transaction_id"])
    assert committed["authoritative_selection_published"] is True
    assert pending_transaction_ids(tmp_path) == []


def test_legacy_committed_head_can_be_extended_once_with_explicit_lineage(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    task_c = b"# task-c\n"
    (tmp_path / "task.md").write_bytes(task_a)
    legacy_id, _prepare, _path = _write_legacy_prepare(
        tmp_path, _named_plan(task_a, task_b, "legacy")
    )
    legacy_receipt = publish_prepared(tmp_path, legacy_id)
    assert "predecessor_transaction_id" not in legacy_receipt

    successor = prepare_publication(tmp_path, _named_plan(task_b, task_c, "new"))
    successor_prepare = json.loads(
        (tmp_path / successor["prepare_ref"]).read_text(encoding="utf-8")
    )
    publish_prepared(tmp_path, successor["transaction_id"])

    assert successor_prepare["predecessor_transaction_id"] == legacy_id
    status = publication_status(tmp_path)
    assert status["current_head"]["status"] == "current"
    assert status["current_head"]["head_transaction_id"] == successor["transaction_id"]
    assert status["current_head"]["lineage_mode"] == "explicit"


def test_ambiguous_legacy_heads_block_new_prepare_without_choosing_one(
    tmp_path: Path,
) -> None:
    task_a = b"# task-a\n"
    task_b = b"# task-b\n"
    task_c = b"# task-c\n"
    (tmp_path / "task.md").write_bytes(task_b)
    for suffix, after in (("legacy-A", task_b), ("legacy-B", task_c)):
        transaction_id, prepare, path = _write_legacy_prepare(
            tmp_path, _named_plan(task_a, after, suffix)
        )
        _write_legacy_receipt(tmp_path, transaction_id, prepare, path)
    before_transactions = sorted(
        path.name
        for path in (
            tmp_path / ".task" / "selection_publication" / "transactions"
        ).iterdir()
    )

    with pytest.raises(ValueError, match="migration required"):
        prepare_publication(tmp_path, _named_plan(task_b, b"# task-d\n", "new"))

    assert publication_status(tmp_path)["status"] == "migration_required"
    assert (
        sorted(
            path.name
            for path in (
                tmp_path / ".task" / "selection_publication" / "transactions"
            ).iterdir()
        )
        == before_transactions
    )


def test_selection_publication_store_rejects_symlink_or_file_task_root(
    tmp_path: Path,
) -> None:
    task = b"# task-a\n"
    (tmp_path / "task.md").write_bytes(task)
    outside = tmp_path.parent / f"{tmp_path.name}-outside-store"
    outside.mkdir()
    (tmp_path / ".task").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="cannot be a symlink"):
        prepare_publication(tmp_path, _named_plan(task, b"# task-b\n", "A"))
    assert list(outside.iterdir()) == []

    file_root = tmp_path.parent / f"{tmp_path.name}-file-root"
    file_root.mkdir()
    (file_root / "task.md").write_bytes(task)
    (file_root / ".task").write_text("not a directory\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a directory"):
        prepare_publication(file_root, _named_plan(task, b"# task-b\n", "B"))
    assert (file_root / ".task").read_text(encoding="utf-8") == "not a directory\n"
