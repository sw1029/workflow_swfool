from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from orchestrate_task_cycle import selection_decision_receipt_cli
from orchestrate_task_cycle import selection_publication as publication
from orchestrate_task_cycle import selection_publication_migration as migration
from orchestrate_task_cycle import (
    selection_publication_migration_contract as migration_contract,
)
from orchestrate_task_cycle.selection_publication import (
    migrate_publication_state,
    publication_status,
)
from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.selection_publication_state import load_state
from selection_synthesis_support import persisted_selection_synthesis
from selection_publication_legacy_support import (
    prepare_legacy_intent_fixture as prepare_publication_intent,
    publish_legacy_prepared_fixture as publish_prepared,
    recover_legacy_publications_fixture as recover_publications,
)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _compact_sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)[:-1]).hexdigest()


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = value if isinstance(value, bytes) else _canonical(value)
    path.write_bytes(body)
    return path


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _selected_inputs(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[dict[str, str], dict[str, str]]:
    (root / "task.md").write_text("# Task\n\n- Task ID: `task-old`\n", encoding="utf-8")
    goal = root / ".agent_goal/final_goal.md"
    goal.parent.mkdir(parents=True)
    goal.write_text("# Goal\n", encoding="utf-8")
    baseline = build_selection_tick(root)
    goal.write_text("# Goal changed\n", encoding="utf-8")
    trigger = build_selection_tick(root, previous=baseline)
    trigger_path = _write(root / ".task/cycle/cycle-v2/trigger.json", trigger)
    source, _, _ = persisted_selection_synthesis(root, suffix="V2")
    source_path = _write(root / ".task/cycle/cycle-v2/source.json", source)
    trigger_binding = _binding(root, trigger_path)
    source_binding = _binding(root, source_path)
    code = selection_decision_receipt_cli.main(
        [
            "--root",
            str(root),
            "pipeline",
            "--cycle-id",
            "cycle-v2",
            "--source-result-ref",
            source_binding["ref"],
            "--source-result-sha256",
            source_binding["sha256"],
            "--trigger-tick-ref",
            trigger_binding["ref"],
            "--trigger-tick-sha256",
            trigger_binding["sha256"],
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["selected_task_id"] == "task-next"
    return result["receipt"], trigger_binding


def _transition_receipt(
    root: Path, task_path: Path, task_id: str, suffix: str
) -> dict[str, str]:
    task_sha = hashlib.sha256(task_path.read_bytes()).hexdigest()
    index = _write(root / ".task/index.jsonl", f"index-{suffix}\n".encode())
    markdown = _write(root / ".task/index.md", f"index-{suffix}\n".encode())
    plan_id = f"transition-{suffix}"
    request = {"schema_version": 1, "events": [], "render": True}
    event = {
        "schema_version": 1,
        "format_version": 2,
        "event": "upsert",
        "id": task_id,
        "type": "task",
        "status": "active",
        "path": "task.md",
        "content_sha256": task_sha,
        "updated_at": "2026-07-22T00:00:00+09:00",
        "transition_plan_id": plan_id,
    }
    plan_body = {
        "schema_version": 1,
        "plan_kind": "task_state_transition_plan",
        "plan_id": plan_id,
        "created_at": "2026-07-22T00:00:00+09:00",
        "request": request,
        "request_sha256": _compact_sha(request),
        "ledger": {
            "path": ".task/index.jsonl",
            "after_sha256": hashlib.sha256(index.read_bytes()).hexdigest(),
            "event_count": 1,
        },
        "markdown": {
            "path": ".task/index.md",
            "after_sha256": hashlib.sha256(markdown.read_bytes()).hexdigest(),
            "render": True,
        },
        "artifact_anchors": [],
        "events": [event],
    }
    plan = {**plan_body, "plan_sha256": _compact_sha(plan_body)}
    plan_path = _write(root / f".task/transition_plans/{plan_id}.json", plan)
    plan_binding = _binding(root, plan_path)
    receipt_body = {
        "schema_version": 1,
        "receipt_kind": "task_state_transition_apply_receipt",
        "plan_id": plan_id,
        "plan_ref": plan_binding["ref"],
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_binding["sha256"],
        "applied_at": plan["created_at"],
        "ledger_after_sha256": plan["ledger"]["after_sha256"],
        "markdown_after_sha256": plan["markdown"]["after_sha256"],
        "event_count": 1,
    }
    receipt = {
        **receipt_body,
        "receipt_content_sha256": _compact_sha(receipt_body),
    }
    receipt_path = _write(root / f".task/transition_receipts/{plan_id}.json", receipt)
    return _binding(root, receipt_path)


def _intent(
    receipt: dict[str, str], task: dict[str, str], owner: dict[str, str]
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "selection_publication_intent",
        "source_decision": receipt,
        "task_source": task,
        "owner_receipts": [owner],
    }


def test_decision_pipeline_is_content_addressed_and_replayable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    paths = list(
        (tmp_path / ".task/cycle/cycle-v2/agent_receipts/selection").glob("*.json")
    )
    assert len(paths) == 3
    assert receipt["ref"].startswith(
        ".task/cycle/cycle-v2/agent_receipts/selection/receipt-"
    )

    source_path = tmp_path / ".task/cycle/cycle-v2/source.json"
    trigger_path = tmp_path / ".task/cycle/cycle-v2/trigger.json"
    code = selection_decision_receipt_cli.main(
        [
            "--root",
            str(tmp_path),
            "pipeline",
            "--cycle-id",
            "cycle-v2",
            "--source-result-ref",
            _binding(tmp_path, source_path)["ref"],
            "--source-result-sha256",
            _binding(tmp_path, source_path)["sha256"],
            "--trigger-tick-ref",
            _binding(tmp_path, trigger_path)["ref"],
            "--trigger-tick-sha256",
            _binding(tmp_path, trigger_path)["sha256"],
        ]
    )
    replay = json.loads(capsys.readouterr().out)
    assert code == 0
    assert replay["mutation_performed"] is False
    assert replay["receipt"] == receipt


def test_v2_intent_publishes_blob_without_inline_payload(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    task_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    task_binding = _binding(tmp_path, task_path)
    owner = _transition_receipt(tmp_path, task_path, "task-next", "selected")

    prepared = prepare_publication_intent(
        tmp_path, _intent(receipt, task_binding, owner)
    )
    prepare = json.loads((tmp_path / prepared["prepare_ref"]).read_text())
    serialized = json.dumps(prepare)
    assert prepare["schema_version"] == 2
    assert "after_payload_b64" not in serialized
    assert prepare["compiler_metrics"]["inline_payload_bytes"] == 0
    blob = tmp_path / prepare["targets"][0]["payload_ref"]
    assert blob.read_bytes() == task_path.read_bytes()

    committed = publish_prepared(tmp_path, prepared["transaction_id"])
    assert committed["schema_version"] == 2
    assert (tmp_path / "task.md").read_bytes() == task_path.read_bytes()
    assert publication_status(tmp_path)["current_head"]["status"] == "current"


def test_v2_committed_intent_replay_does_not_append_noop_successor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    task_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    intent = _intent(
        receipt,
        _binding(tmp_path, task_path),
        _transition_receipt(tmp_path, task_path, "task-next", "selected"),
    )
    prepared = prepare_publication_intent(tmp_path, intent)
    committed = publish_prepared(tmp_path, prepared["transaction_id"])
    transaction_root = tmp_path / ".task/selection_publication/transactions"
    receipt_root = tmp_path / ".task/selection_publication/receipts"
    state_path = tmp_path / ".task/selection_publication/state.json"
    transaction_count = len(list(transaction_root.glob("selection-*")))
    receipt_count = len(list(receipt_root.glob("selection-*.json")))
    state_inode = state_path.stat().st_ino

    replay = prepare_publication_intent(tmp_path, intent)
    replay_receipt = publish_prepared(tmp_path, replay["transaction_id"])

    assert replay["status"] == "already_committed"
    assert replay["transaction_id"] == prepared["transaction_id"]
    assert replay["mutation_performed"] is False
    assert replay_receipt["transaction_id"] == committed["transaction_id"]
    assert replay_receipt["mutation_performed"] is False
    assert len(list(transaction_root.glob("selection-*"))) == transaction_count
    assert len(list(receipt_root.glob("selection-*.json"))) == receipt_count
    assert state_path.stat().st_ino == state_inode


def test_reconciliation_uses_drifted_head_as_before_digest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    selected_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    selected_owner = _transition_receipt(
        tmp_path, selected_path, "task-next", "selected"
    )
    selected = prepare_publication_intent(
        tmp_path,
        _intent(receipt, _binding(tmp_path, selected_path), selected_owner),
    )
    publish_prepared(tmp_path, selected["transaction_id"])
    selected_sha = hashlib.sha256((tmp_path / "task.md").read_bytes()).hexdigest()

    (tmp_path / "task.md").write_bytes(b"# Task\n\n- Task ID: `task-reconciled`\n")
    reconciliation_source = _transition_receipt(
        tmp_path, tmp_path / "task.md", "task-reconciled", "reconciled"
    )
    current_sha = hashlib.sha256((tmp_path / "task.md").read_bytes()).hexdigest()
    prepared = prepare_publication_intent(
        tmp_path,
        {
            "schema_version": 1,
            "kind": "selection_publication_intent",
            "source_decision": reconciliation_source,
            "task_source": None,
            "owner_receipts": [],
        },
    )
    prepare = json.loads((tmp_path / prepared["prepare_ref"]).read_text())
    target = prepare["targets"][0]
    assert target["before_sha256"] == selected_sha
    assert target["after_sha256"] == current_sha
    publish_prepared(tmp_path, prepared["transaction_id"])
    assert publication_status(tmp_path)["current_head"]["status"] == "current"


def test_exact_replay_requires_explicit_missing_state_migration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    task_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    intent = _intent(
        receipt,
        _binding(tmp_path, task_path),
        _transition_receipt(tmp_path, task_path, "task-next", "selected"),
    )
    prepared = prepare_publication_intent(tmp_path, intent)
    state = tmp_path / ".task/selection_publication/state.json"
    state.unlink()

    with pytest.raises(ValueError, match="migrate-state explicitly"):
        prepare_publication_intent(tmp_path, intent)
    migrate_publication_state(tmp_path)
    replay = prepare_publication_intent(tmp_path, intent)

    assert replay["transaction_id"] == prepared["transaction_id"]
    assert state.is_file()
    publish_prepared(tmp_path, prepared["transaction_id"])
    assert publication_status(tmp_path)["current_head"]["status"] == "current"
    refreshed = migrate_publication_state(tmp_path)
    assert refreshed["idempotent_replay"] is False
    history = tmp_path / ".task/selection_publication/migrations/storage-v4/history"
    assert len(list(history.iterdir())) == 1
    assert publication_status(tmp_path)["current_head"]["status"] == "current"
    state.unlink()
    assert publication_status(tmp_path)["status"] == "migration_required"
    migrate_publication_state(tmp_path)
    replay_receipt = publish_prepared(tmp_path, prepared["transaction_id"])
    assert replay_receipt["mutation_performed"] is False
    assert state.is_file()


def test_completed_migration_allows_new_prepare_and_commit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    first_task = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    first = prepare_publication_intent(
        tmp_path,
        _intent(
            receipt,
            _binding(tmp_path, first_task),
            _transition_receipt(tmp_path, first_task, "task-next", "first"),
        ),
    )
    publish_prepared(tmp_path, first["transaction_id"])
    migrate_publication_state(tmp_path)

    next_task = _write(
        tmp_path / ".task/candidates/task-next-revised.md",
        b"# Task\n\n- Task ID: `task-next`\n\nRevised.\n",
    )
    successor = prepare_publication_intent(
        tmp_path,
        _intent(
            receipt,
            _binding(tmp_path, next_task),
            _transition_receipt(tmp_path, next_task, "task-next", "successor"),
        ),
    )

    active = load_state(tmp_path)
    assert active is not None
    assert active["active_transaction"]["transaction_id"] == successor["transaction_id"]
    publish_prepared(tmp_path, successor["transaction_id"])
    committed = load_state(tmp_path)
    assert committed is not None
    assert committed["head"]["transaction_id"] == successor["transaction_id"]
    assert publication_status(tmp_path)["current_head"]["status"] == "current"


def test_forward_migration_crash_keeps_new_wal_fail_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    task_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    prepared = prepare_publication_intent(
        tmp_path,
        _intent(
            receipt,
            _binding(tmp_path, task_path),
            _transition_receipt(tmp_path, task_path, "task-next", "selected"),
        ),
    )
    migrate_publication_state(tmp_path)
    publish_prepared(tmp_path, prepared["transaction_id"])

    def crash_after_state(stage: str, _path: Path) -> None:
        if stage == "after_state":
            raise RuntimeError("simulated forward migration crash")

    monkeypatch.setattr(migration, "_migration_hook", crash_after_state)
    with pytest.raises(RuntimeError, match="simulated forward migration crash"):
        migrate_publication_state(tmp_path)
    with pytest.raises(ValueError, match="diverges from its WAL"):
        load_state(tmp_path)

    monkeypatch.setattr(migration, "_migration_hook", lambda _stage, _path: None)
    recovered = migrate_publication_state(tmp_path)
    assert recovered["mutation_performed"] is True
    assert load_state(tmp_path) is not None


def test_noncanonical_live_state_is_not_migration_idempotent_replay(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    first = migrate_publication_state(tmp_path)
    assert first["idempotent_replay"] is False
    state_path = tmp_path / ".task/selection_publication/state.json"
    state = json.loads(state_path.read_bytes())
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    refreshed = migrate_publication_state(tmp_path)

    assert refreshed["idempotent_replay"] is False
    assert refreshed["mutation_performed"] is True
    assert state_path.read_bytes() == _canonical(json.loads(state_path.read_bytes()))


def test_symlink_live_state_is_not_migration_idempotent_replay(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    migrate_publication_state(tmp_path)
    state_path = tmp_path / ".task/selection_publication/state.json"
    alternate = tmp_path / "alternate-state.json"
    alternate.write_bytes(state_path.read_bytes())
    state_path.unlink()
    state_path.symlink_to(alternate)

    with pytest.raises(ValueError, match="compact state cannot be a symlink"):
        migrate_publication_state(tmp_path)


def test_deep_status_preserves_schema_v1_migration_debt(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    _write(
        tmp_path / ".task/selection_publication/state.json",
        {
            "schema_version": 1,
            "kind": "selection_publication_state",
            "pending_transaction_ids": [],
            "receipts": [],
            "state_content_sha256": "0" * 64,
        },
    )

    compact = publication_status(tmp_path)
    deep = publication_status(tmp_path, deep=True)

    assert compact["status"] == "migration_required"
    assert deep == compact
    assert deep["current_head"]["lineage_mode"] == "legacy_unscanned"


def test_v2_blob_tamper_fails_before_task_alias_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    task_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    intent = _intent(
        receipt,
        _binding(tmp_path, task_path),
        _transition_receipt(tmp_path, task_path, "task-next", "selected"),
    )
    prepared = prepare_publication_intent(tmp_path, intent)
    prepare = json.loads((tmp_path / prepared["prepare_ref"]).read_text())
    blob = tmp_path / prepare["targets"][0]["payload_ref"]
    blob.write_bytes(b"tampered\n")

    with pytest.raises(ValueError, match="raw SHA-256"):
        publish_prepared(tmp_path, prepared["transaction_id"])
    assert "task-old" in (tmp_path / "task.md").read_text()


def test_v2_compact_status_reopens_only_exact_head_contracts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    task_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    intent = _intent(
        receipt,
        _binding(tmp_path, task_path),
        _transition_receipt(tmp_path, task_path, "task-next", "selected"),
    )
    prepared = prepare_publication_intent(tmp_path, intent)
    recovered = recover_publications(tmp_path, prepared["transaction_id"])
    assert recovered["remaining_pending_transaction_ids"] == []

    original = publication._load_prepare
    opened: list[str] = []

    def tracked_prepare(root: Path, transaction_id: str) -> object:
        opened.append(transaction_id)
        return original(root, transaction_id)

    monkeypatch.setattr(publication, "_load_prepare", tracked_prepare)
    monkeypatch.setattr(
        publication,
        "_transactions_root",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("compact status enumerated history")
        ),
    )
    assert publication_status(tmp_path)["current_head"]["status"] == "current"
    assert opened == [prepared["transaction_id"]]
    with pytest.raises(AssertionError, match="enumerated history"):
        publication_status(tmp_path, deep=True)


def test_state_migration_rebuilds_projection_from_deep_validation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    task_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    prepared = prepare_publication_intent(
        tmp_path,
        _intent(
            receipt,
            _binding(tmp_path, task_path),
            _transition_receipt(tmp_path, task_path, "task-next", "selected"),
        ),
    )
    publish_prepared(tmp_path, prepared["transaction_id"])
    state_path = tmp_path / ".task/selection_publication/state.json"
    state_path.unlink()

    migrated = migrate_publication_state(tmp_path)

    assert migrated["receipt_count"] == 1
    assert state_path.is_file()
    assert publication_status(tmp_path)["selection_consumption_allowed"] is True


def test_state_migration_hides_state_until_completion_receipt_and_recovers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt, _ = _selected_inputs(tmp_path, capsys)
    task_path = _write(
        tmp_path / ".task/candidates/task-next.md",
        b"# Task\n\n- Task ID: `task-next`\n",
    )
    prepared = prepare_publication_intent(
        tmp_path,
        _intent(
            receipt,
            _binding(tmp_path, task_path),
            _transition_receipt(tmp_path, task_path, "task-next", "selected"),
        ),
    )
    publish_prepared(tmp_path, prepared["transaction_id"])
    state_path = tmp_path / ".task/selection_publication/state.json"
    state_path.unlink()
    crashed = False

    def crash_after_state(stage: str, _path: Path) -> None:
        nonlocal crashed
        if stage == "after_state" and not crashed:
            crashed = True
            raise RuntimeError("simulated migration crash after state")

    monkeypatch.setattr(migration, "_migration_hook", crash_after_state)
    with pytest.raises(RuntimeError, match="simulated migration crash"):
        migrate_publication_state(tmp_path)

    assert state_path.is_file()
    with pytest.raises(ValueError, match="completion receipt is absent"):
        load_state(tmp_path)
    assert not (
        tmp_path / ".task/selection_publication/migrations/storage-v4/complete.json"
    ).exists()

    monkeypatch.setattr(migration, "_migration_hook", lambda _stage, _path: None)
    recovered = migrate_publication_state(tmp_path)

    assert recovered["mutation_performed"] is True
    assert recovered["migration_completion"]["ref"].endswith("complete.json")
    assert load_state(tmp_path) is not None


def test_state_migration_fails_before_wal_when_inventory_exceeds_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipts = tmp_path / ".task/selection_publication/receipts"
    receipts.mkdir(parents=True)
    for index in range(3):
        (receipts / f"junk-{index}.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(migration_contract, "MAX_MIGRATION_ENTRIES", 2)

    with pytest.raises(ValueError, match="entry-count bound"):
        migrate_publication_state(tmp_path)

    assert not (
        tmp_path / ".task/selection_publication/migrations/storage-v4/prepare.json"
    ).exists()
    assert not (tmp_path / ".task/selection_publication/state.json").exists()


def test_migration_file_bound_accepts_observed_legacy_size_and_rejects_overflow() -> (
    None
):
    assert migration_contract.MAX_MIGRATION_FILE_BYTES == 32 * 1024 * 1024
    budget = migration_contract.MigrationBudget()
    budget.consume_stat(
        SimpleNamespace(
            st_mode=stat.S_IFREG,
            st_size=migration_contract.MAX_MIGRATION_FILE_BYTES,
        ),
        "legacy prepare",
    )

    with pytest.raises(ValueError, match="file-size bound"):
        migration_contract.MigrationBudget().consume_stat(
            SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_size=migration_contract.MAX_MIGRATION_FILE_BYTES + 1,
            ),
            "oversized prepare",
        )
