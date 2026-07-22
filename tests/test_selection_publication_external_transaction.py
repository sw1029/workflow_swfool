from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from manage_task_state_index import index as task_state
from orchestrate_task_cycle import cycle_ledger
from orchestrate_task_cycle import selection_publication as publication
from orchestrate_task_cycle import selection_decision_receipt_cli
from orchestrate_task_cycle import selection_publication_cli
from orchestrate_task_cycle.selection_publication import (
    prepare_publication,
    publication_status,
    publish_prepared,
)
from orchestrate_task_cycle.selection_trigger import (
    render_normal_cycle_trigger,
    render_publication_bootstrap,
)
from orchestrate_task_cycle.terminal_wait_baseline import (
    resolve_terminal_wait_baseline,
    retire_terminal_wait_baseline,
)
from orchestrate_task_cycle.terminal_wait_baseline_store import (
    display_bytes,
    sha256_bytes,
    write_current,
    write_once,
)
from selection_synthesis_support import persisted_selection_synthesis


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return path


def _content_sha(value: dict[str, object]) -> str:
    body = {key: item for key, item in value.items() if key != "receipt_content_sha256"}
    return hashlib.sha256(
        json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _initialize_active_task(root: Path) -> dict[str, Any]:
    task = root / "task.md"
    task.write_text("# Task\n\n- Task ID: `task-old`\n", encoding="utf-8")
    return task_state.upsert_item(
        root,
        "task",
        "task.md",
        "active",
        item_id="task-old",
        replace_existing=False,
    )


def _normal_cycle_inputs(root: Path) -> dict[str, Any]:
    goal = root / ".agent_goal/final_goal.md"
    goal.parent.mkdir(parents=True, exist_ok=True)
    goal.write_text("# Goal\n", encoding="utf-8")
    source, _, synthesis = persisted_selection_synthesis(root, suffix="EXTERNAL")
    cycle_id = source["cycle_id"]
    source_path = _write_json(root / f".task/cycle/{cycle_id}/source.json", source)
    cycle_ledger.init_cycle(root, cycle_id, "task-old", "selection trigger fixture")
    operation = cycle_ledger.build_durable_operation(
        target_ref="registry_projection",
        operation_kind="replace_projection",
        attempt_identity="attempt-selection-trigger",
        payload_schema_id="registry-projection-v1",
        payload={"artifact_id": "selection-trigger-fixture"},
    )
    durable_state = cycle_ledger.build_typed_operations_candidate(
        producer="selection-trigger-fixture",
        attempt_identity="attempt-selection-trigger",
        operations=[operation],
    )
    candidate = {
        "schema_version": 1,
        "kind": "cycle_final_candidate",
        "final_candidate": True,
        "cycle_id": cycle_id,
        "attempt_id": "attempt-selection-trigger",
        "expected_previous_revision": None,
        "expected_previous_attempt_id": None,
        "expected_previous_finalization_token": None,
        "verdict_contract_version": 1,
        "durable_state_candidate": durable_state,
    }
    for axis in cycle_ledger.VERDICT_AXES:
        candidate[axis] = {"status": "pass", "evidence_ref": f"{axis}-evidence"}
    candidate["goal_readiness_verdict"] = {
        "status": "blocked",
        "evidence_ref": "selection-publication-gap",
    }
    finalized = cycle_ledger.finalize_candidate(root, cycle_id, candidate)
    assert finalized["receipt"]["authoritative_final"] == "blocked"
    finalization = cycle_ledger.current_finalization_path(root, cycle_id)
    schema_pre = _write_json(
        root / f".task/cycle/{cycle_id}/schema-pre-derive.json",
        {
            "step": "schema_pre_derive",
            "cycle_id": cycle_id,
            "task_id": "task-old",
            "status": "complete",
            "schema_status": "pass",
            "evidence_paths": [],
        },
    )
    task_binding = _binding(root, root / "task.md")
    index_binding = _binding(root, root / ".task/index.jsonl")
    return {
        "cycle_id": cycle_id,
        "source": source,
        "source_binding": _binding(root, source_path),
        "finalization": _binding(root, finalization),
        "schema_pre": _binding(root, schema_pre),
        "current_task": task_binding,
        "task_index": index_binding,
        "input_evidence_manifest_sha256": synthesis[
            "input_evidence_manifest_sha256"
        ],
    }


def _persist_bootstrap(root: Path, inputs: dict[str, Any]) -> dict[str, str]:
    bootstrap = render_publication_bootstrap(
        root,
        cycle_id=inputs["cycle_id"],
        current_task=inputs["current_task"],
        task_index=inputs["task_index"],
    )
    path = _write_json(
        root
        / ".task/cycle"
        / inputs["cycle_id"]
        / "agent_receipts/selection/publication-bootstrap-test.json",
        bootstrap,
    )
    return _binding(root, path)


def _render_trigger(
    root: Path,
    inputs: dict[str, Any],
    *,
    cycle_id: str | None = None,
    finalization: dict[str, str] | None = None,
    schema_pre: dict[str, str] | None = None,
    derive: dict[str, str] | None = None,
    current_task: dict[str, str] | None = None,
    task_index: dict[str, str] | None = None,
    publication_head: dict[str, str] | None = None,
) -> dict[str, Any]:
    return render_normal_cycle_trigger(
        root,
        cycle_id=cycle_id or inputs["cycle_id"],
        cycle_finalization=finalization or inputs["finalization"],
        schema_pre_derive=schema_pre or inputs["schema_pre"],
        derive_result=derive or inputs["source_binding"],
        current_task=current_task or inputs["current_task"],
        task_index=task_index or inputs["task_index"],
        publication_head=publication_head or _persist_bootstrap(root, inputs),
        input_evidence_manifest_sha256=inputs[
            "input_evidence_manifest_sha256"
        ],
    )


def _selected_receipt(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> dict[str, str]:
    inputs = _normal_cycle_inputs(root)
    code = selection_decision_receipt_cli.main(
        [
            "--root",
            str(root),
            "pipeline",
            "--cycle-id",
            str(inputs["cycle_id"]),
            "--trigger-kind",
            "normal_cycle",
            "--source-result-ref",
            inputs["source_binding"]["ref"],
            "--source-result-sha256",
            inputs["source_binding"]["sha256"],
            "--cycle-finalization-ref",
            inputs["finalization"]["ref"],
            "--cycle-finalization-sha256",
            inputs["finalization"]["sha256"],
            "--schema-pre-derive-ref",
            inputs["schema_pre"]["ref"],
            "--schema-pre-derive-sha256",
            inputs["schema_pre"]["sha256"],
            "--current-task-ref",
            inputs["current_task"]["ref"],
            "--current-task-sha256",
            inputs["current_task"]["sha256"],
            "--task-index-ref",
            inputs["task_index"]["ref"],
            "--task-index-sha256",
            inputs["task_index"]["sha256"],
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["trigger_kind"] == "normal_cycle"
    return result["receipt"]


def test_normal_trigger_rejects_arbitrary_publication_head(tmp_path: Path) -> None:
    _initialize_active_task(tmp_path)
    inputs = _normal_cycle_inputs(tmp_path)
    blocker = _write_json(
        tmp_path
        / ".task/cycle"
        / inputs["cycle_id"]
        / "selection-publication-blocker.json",
        {"artifact_kind": "selection_publication_blocker", "status": "blocked"},
    )

    with pytest.raises(ValueError, match="committed receipt or compiler bootstrap"):
        _render_trigger(
            tmp_path, inputs, publication_head=_binding(tmp_path, blocker)
        )


@pytest.mark.parametrize("artifact", ["schema_pre", "derive"])
def test_normal_trigger_rejects_wrong_cycle_stage_result(
    tmp_path: Path, artifact: str
) -> None:
    _initialize_active_task(tmp_path)
    inputs = _normal_cycle_inputs(tmp_path)
    input_key = "source_binding" if artifact == "derive" else artifact
    original = inputs[input_key]
    value = json.loads((tmp_path / original["ref"]).read_text(encoding="utf-8"))
    value["cycle_id"] = "cycle-other"
    path = _write_json(
        tmp_path
        / ".task/cycle"
        / inputs["cycle_id"]
        / f"wrong-cycle-{artifact}.json",
        value,
    )

    with pytest.raises(ValueError, match="wrong-cycle|cycle-bound"):
        _render_trigger(tmp_path, inputs, **{artifact: _binding(tmp_path, path)})


def _publication_plan(before: bytes, after: bytes, suffix: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "selection_publication_plan",
        "selection_id": f"selection-{suffix}",
        "source_decision_id": f"derive-{suffix}",
        "source_decision_sha256": hashlib.sha256(
            f"decision-{suffix}".encode("utf-8")
        ).hexdigest(),
        "targets": [
            {
                "role": "task_alias",
                "target_ref": "task.md",
                "before_sha256": hashlib.sha256(before).hexdigest(),
                "after_payload_b64": base64.b64encode(after).decode("ascii"),
            }
        ],
    }


def test_normal_trigger_rejects_stale_committed_publication_head(
    tmp_path: Path,
) -> None:
    _initialize_active_task(tmp_path)
    inputs = _normal_cycle_inputs(tmp_path)
    old = (tmp_path / "task.md").read_bytes()
    middle = b"# Task\n\n- Task ID: `task-middle`\n"
    current = b"# Task\n\n- Task ID: `task-current`\n"
    first_prepare = prepare_publication(
        tmp_path, _publication_plan(old, middle, "first")
    )
    first = publish_prepared(tmp_path, first_prepare["transaction_id"])
    second_prepare = prepare_publication(
        tmp_path, _publication_plan(middle, current, "second")
    )
    publish_prepared(tmp_path, second_prepare["transaction_id"])
    inputs["current_task"] = _binding(tmp_path, tmp_path / "task.md")
    stale_head = {"ref": first["receipt_ref"], "sha256": first["receipt_sha256"]}

    with pytest.raises(ValueError, match="unique current committed head"):
        _render_trigger(tmp_path, inputs, publication_head=stale_head)


def test_normal_trigger_accepts_unique_current_legacy_publication_head(
    tmp_path: Path,
) -> None:
    _initialize_active_task(tmp_path)
    inputs = _normal_cycle_inputs(tmp_path)
    old = (tmp_path / "task.md").read_bytes()
    current = b"# Task\n\n- Task ID: `task-current`\n"
    prepared = prepare_publication(
        tmp_path, _publication_plan(old, current, "current-head")
    )
    committed = publish_prepared(tmp_path, prepared["transaction_id"])
    inputs["current_task"] = _binding(tmp_path, tmp_path / "task.md")

    trigger = _render_trigger(
        tmp_path,
        inputs,
        publication_head={
            "ref": committed["receipt_ref"],
            "sha256": committed["receipt_sha256"],
        },
    )

    assert trigger["publication_head"]["ref"] == committed["receipt_ref"]


def _write_historical_baseline(root: Path, task_id: str, task_sha: str) -> None:
    snapshot_payload = display_bytes(
        {
            "schema_version": 1,
            "artifact_kind": "historical_terminal_wait_snapshot",
            "task": {"task_id": task_id, "sha256": task_sha},
        }
    )
    snapshot_binding = write_once(
        root,
        "snapshots",
        sha256_bytes(snapshot_payload),
        snapshot_payload,
    )
    historical_binding = {"ref": ".task/historical.json", "sha256": "0" * 64}
    write_current(
        root,
        display_bytes(
            {
                "schema_version": 1,
                "artifact_kind": "terminal_wait_baseline_current",
                "activation": historical_binding,
                "completion": historical_binding,
                "snapshot": snapshot_binding,
                "binding_id": "twbb-historical-predecessor",
                "task_id": task_id,
                "task_sha256": task_sha,
                "predecessor_snapshot_sha256": None,
                "authority_use_receipt": historical_binding,
            }
        ),
    )


def test_historical_predecessor_baseline_retires_while_legacy_head_is_current(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    old = b"# Task\n\n- Task ID: `task-old`\n"
    current = b"# Task\n\n- Task ID: `task-current`\n"
    successor = b"# Task\n\n- Task ID: `task-successor`\n"
    task.write_bytes(old)
    _write_historical_baseline(tmp_path, "task-old", hashlib.sha256(old).hexdigest())

    first_prepare = prepare_publication(
        tmp_path, _publication_plan(old, current, "historical-current")
    )
    first = publish_prepared(tmp_path, first_prepare["transaction_id"])
    retired = retire_terminal_wait_baseline(
        tmp_path,
        {"ref": first["receipt_ref"], "sha256": first["receipt_sha256"]},
    )

    assert retired["status"] == "inactive"
    inactive = resolve_terminal_wait_baseline(tmp_path)
    assert inactive["status"] == "inactive"
    assert inactive["task_sha256"] == hashlib.sha256(old).hexdigest()
    assert inactive["snapshot"]["sha256"]
    assert retired["previous_pointer"]["sha256"]

    # Once the next head is published, the first receipt is historical.  The
    # stale baseline has therefore already been retired at its last safe edge.
    second_prepare = prepare_publication(
        tmp_path, _publication_plan(current, successor, "historical-successor")
    )
    publish_prepared(tmp_path, second_prepare["transaction_id"])
    assert publication_status(tmp_path)["current_head"]["head_transaction_id"] == (
        second_prepare["transaction_id"]
    )
    assert resolve_terminal_wait_baseline(tmp_path)["status"] == "inactive"


def test_real_task_state_owner_applies_before_alias_and_settles_after_cas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n\n- Task ID: `task-old`\n", encoding="utf-8")
    old = task_state.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-old",
        replace_existing=False,
    )
    old_sha = hashlib.sha256(task.read_bytes()).hexdigest()
    snapshot_body = {
        "schema_version": 1,
        "artifact_kind": "historical_terminal_wait_snapshot",
        "task": {"task_id": "task-old", "sha256": old_sha},
    }
    snapshot_payload = display_bytes(snapshot_body)
    snapshot_binding = write_once(
        tmp_path,
        "snapshots",
        sha256_bytes(snapshot_payload),
        snapshot_payload,
    )
    historical_binding = {"ref": ".task/historical.json", "sha256": "0" * 64}
    write_current(
        tmp_path,
        display_bytes(
            {
                "schema_version": 1,
                "artifact_kind": "terminal_wait_baseline_current",
                "activation": historical_binding,
                "completion": historical_binding,
                "snapshot": snapshot_binding,
                "binding_id": "twbb-historical",
                "task_id": "task-old",
                "task_sha256": old_sha,
                "predecessor_snapshot_sha256": None,
                "authority_use_receipt": historical_binding,
            }
        ),
    )
    decision = _selected_receipt(tmp_path, capsys)
    candidate = tmp_path / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    candidate_binding = _binding(tmp_path, candidate)
    request = {
        "schema_version": 2,
        "updated_at": "2026-07-22T20:00:00+09:00",
        "render": True,
        "external_settlement_kind": "selection_publication",
        "artifact_sources": [
            {"target_ref": "task.md", "source": candidate_binding}
        ],
        "events": [
            {
                "event": "upsert",
                "id": old["id"],
                "status": "superseded",
                "links": [{"rel": "superseded_by", "id": "task-next"}],
            },
            {
                "event": "upsert",
                "id": "task-next",
                "type": "task",
                "status": "active",
                "path": "task.md",
                "title": "Next task",
                "content_sha256": candidate_binding["sha256"],
                "links": [{"rel": "supersedes", "id": old["id"]}],
            },
        ],
    }
    plan = task_state.build_transition_plan(tmp_path, request)
    planned = task_state.publish_transition_plan(tmp_path, plan)
    intent = {
        "schema_version": 2,
        "kind": "selection_publication_intent",
        "source_decision": decision,
        "task_source": candidate_binding,
        "task_state_plan": {
            "ref": planned["plan_ref"],
            "sha256": planned["plan_file_sha256"],
        },
    }
    intent_path = _write_json(tmp_path / ".task/selection-intent.json", intent)
    code = selection_publication_cli.main(
        [
            "--root",
            str(tmp_path),
            "prepare-intent",
            "--intent",
            str(intent_path),
        ]
    )
    prepare = json.loads(capsys.readouterr().out)
    assert code == 0
    code = selection_publication_cli.main(
        [
            "--root",
            str(tmp_path),
            "prepare-intent",
            "--intent",
            str(intent_path),
        ]
    )
    prepare_replay = json.loads(capsys.readouterr().out)
    assert code == 0
    assert prepare_replay["transaction_id"] == prepare["transaction_id"]
    assert prepare_replay["prepare_sha256"] == prepare["prepare_sha256"]
    assert prepare_replay["mutation_performed"] is False
    code = task_state.main(
        [
            "--root",
            str(tmp_path),
            "apply-plan",
            "--plan",
            planned["plan_ref"],
            "--external-prepare-ref",
            prepare["prepare_ref"],
            "--external-prepare-sha256",
            prepare["prepare_sha256"],
        ]
    )
    pending = json.loads(capsys.readouterr().out)
    assert code == 0

    assert pending["activation_status"] == "pending_external_settlement"
    assert "task-old" in task.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="Pending task-state transition intent"):
        task_state.append_event(
            tmp_path,
            {
                "event": "link",
                "id": old["id"],
                "updated_at": "2026-07-22T20:00:01+09:00",
                "links": [{"rel": "related_to", "id": old["id"]}],
            },
        )

    code = selection_publication_cli.main(
        [
            "--root",
            str(tmp_path),
            "apply-intent",
            "--intent",
            str(intent_path),
        ]
    )
    committed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert committed["activation_status"] == "pending_external_settlement"
    assert task.read_bytes() == candidate.read_bytes()
    assert publication_status(tmp_path)["status"] == "settlement_required"
    code = task_state.main(
        [
            "--root",
            str(tmp_path),
            "settle-plan-external",
            "--plan",
            planned["plan_ref"],
            "--external-commit-ref",
            committed["receipt_ref"],
            "--external-commit-sha256",
            committed["receipt_sha256"],
        ]
    )
    settled = json.loads(capsys.readouterr().out)
    assert code == 0

    assert settled["status"] == "settled"
    assert settled["selection_consumption_allowed"] is True
    assert publication_status(tmp_path)["selection_consumption_allowed"] is True

    settlement_path = tmp_path / settled["receipt_ref"]
    settlement_bytes = settlement_path.read_bytes()
    settlement_value = json.loads(settlement_bytes)
    stale_integrity = {**settlement_value, "ledger_after_sha256": "0" * 64}
    _write_json(settlement_path, stale_integrity)
    assert publication_status(tmp_path)["status"] == "settlement_conflict"
    with pytest.raises(ValueError, match="external settlement"):
        retire_terminal_wait_baseline(
            tmp_path,
            {"ref": committed["receipt_ref"], "sha256": committed["receipt_sha256"]},
        )
    settlement_path.write_bytes(settlement_bytes)

    resealed = {**settlement_value, "ledger_after_sha256": "0" * 64}
    resealed["receipt_content_sha256"] = _content_sha(resealed)
    _write_json(settlement_path, resealed)
    assert publication_status(tmp_path)["status"] == "settlement_conflict"
    settlement_path.write_bytes(settlement_bytes)

    wrong_commit = {
        **settlement_value,
        "external_commit": {
            **settlement_value["external_commit"],
            "sha256": "0" * 64,
        },
    }
    wrong_commit["receipt_content_sha256"] = _content_sha(wrong_commit)
    _write_json(settlement_path, wrong_commit)
    assert publication_status(tmp_path)["selection_consumption_allowed"] is False
    settlement_path.write_bytes(settlement_bytes)

    pending_path = tmp_path / pending["receipt_ref"]
    pending_bytes = pending_path.read_bytes()
    pending_value = json.loads(pending_bytes)
    _write_json(pending_path, {**pending_value, "event_count": 999})
    assert publication_status(tmp_path)["status"] == "settlement_conflict"
    pending_path.write_bytes(pending_bytes)

    resealed_pending = {**pending_value, "event_count": 999}
    resealed_pending["receipt_content_sha256"] = _content_sha(resealed_pending)
    _write_json(pending_path, resealed_pending)
    assert publication_status(tmp_path)["selection_consumption_allowed"] is False
    with pytest.raises(ValueError):
        retire_terminal_wait_baseline(
            tmp_path,
            {"ref": committed["receipt_ref"], "sha256": committed["receipt_sha256"]},
        )
    pending_path.write_bytes(pending_bytes)

    plan_path = tmp_path / planned["plan_ref"]
    plan_bytes = plan_path.read_bytes()
    plan_value = json.loads(plan_bytes)
    plan_value["events"][0]["status"] = "active"
    _write_json(plan_path, plan_value)
    assert publication_status(tmp_path)["selection_consumption_allowed"] is False
    plan_path.write_bytes(plan_bytes)

    ledger_path = tmp_path / ".task/index.jsonl"
    ledger_bytes = ledger_path.read_bytes()
    ledger_path.write_bytes(ledger_bytes + b"\n")
    assert publication_status(tmp_path)["status"] == "settlement_conflict"
    ledger_path.write_bytes(ledger_bytes)

    markdown_path = tmp_path / ".task/index.md"
    markdown_bytes = markdown_path.read_bytes()
    markdown_path.write_bytes(markdown_bytes + b"\n")
    assert publication_status(tmp_path)["status"] == "settlement_conflict"
    markdown_path.write_bytes(markdown_bytes)

    task_bytes = task.read_bytes()
    task.write_bytes(task_bytes + b"\n")
    drifted = publication_status(tmp_path)
    assert drifted["selection_consumption_allowed"] is False
    with pytest.raises(ValueError):
        retire_terminal_wait_baseline(
            tmp_path,
            {"ref": committed["receipt_ref"], "sha256": committed["receipt_sha256"]},
        )
    task.write_bytes(task_bytes)
    assert publication_status(tmp_path)["selection_consumption_allowed"] is True

    retired = retire_terminal_wait_baseline(
        tmp_path,
        {"ref": committed["receipt_ref"], "sha256": committed["receipt_sha256"]},
    )
    assert retired["status"] == "inactive"
    assert resolve_terminal_wait_baseline(tmp_path)["status"] == "inactive"
    assert task_state.verify_transition_plan(
        tmp_path, planned["plan_ref"]
    )["status"] == "already_applied"
    code = selection_publication_cli.main(
        [
            "--root",
            str(tmp_path),
            "apply-intent",
            "--intent",
            str(intent_path),
        ]
    )
    replay = json.loads(capsys.readouterr().out)
    assert code == 0
    assert replay["mutation_performed"] is False

    modified = {**intent, "task_state_plan": {**intent["task_state_plan"], "sha256": "0" * 64}}
    modified_path = _write_json(tmp_path / ".task/selection-intent-modified.json", modified)
    code = selection_publication_cli.main(
        [
            "--root",
            str(tmp_path),
            "apply-intent",
            "--intent",
            str(modified_path),
        ]
    )
    blocked = json.loads(capsys.readouterr().out)
    assert code == 2
    assert blocked["status"] == "blocked"

    candidate_payload = candidate.read_bytes()
    candidate.write_bytes(b"tampered\n")
    code = selection_publication_cli.main(
        [
            "--root",
            str(tmp_path),
            "apply-intent",
            "--intent",
            str(intent_path),
        ]
    )
    tampered = json.loads(capsys.readouterr().out)
    assert code == 2
    assert tampered["status"] == "blocked"
    candidate.write_bytes(candidate_payload)

    original_prepare = json.loads(
        (tmp_path / prepare["prepare_ref"]).read_text(encoding="utf-8")
    )
    competing = {
        **original_prepare,
        "predecessor_transaction_id": "selection-" + ("f" * 64),
    }
    competing_material = {
        key: value for key, value in competing.items() if key != "transaction_id"
    }
    competing_id = "selection-" + publication._sha256_bytes(
        publication._canonical_json(competing_material)
    )
    competing["transaction_id"] = competing_id
    _write_json(
        tmp_path
        / ".task/selection_publication/transactions"
        / competing_id
        / "prepare.json",
        competing,
    )
    code = selection_publication_cli.main(
        [
            "--root",
            str(tmp_path),
            "apply-intent",
            "--intent",
            str(intent_path),
        ]
    )
    ambiguous = json.loads(capsys.readouterr().out)
    assert code == 2
    assert "ambiguous" in ambiguous["error"]
