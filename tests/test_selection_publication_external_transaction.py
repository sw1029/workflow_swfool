from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from selection_publication_legacy_support import (
    prepare_legacy_publication as prepare_publication,
)

from manage_task_state_index import index as task_state
from manage_task_state_index.state.selected_successor_guard import (
    _SELECTED_SUCCESSOR_EXECUTION_TOKEN,
)
from manage_task_state_index.state.transition_plan import (
    apply_transition_plan,
    settle_transition_external,
)
from orchestrate_task_cycle import cycle_ledger
from orchestrate_task_cycle import selection_publication as publication
from orchestrate_task_cycle import selection_decision_receipt_cli
from orchestrate_task_cycle import selection_publication_cli
from orchestrate_task_cycle.selected_successor import (
    load_selected_successor_bundle,
    prepare_selected_successor_bundle,
)
from orchestrate_task_cycle.selected_successor_execution import (
    execute_selected_successor_bundle,
)
from selected_successor_authority_support import (
    AT as AUTHORITY_AT,
    LATER as AUTHORITY_LATER,
    SKILLS_ROOT,
    prepare_authority_proofs,
)
from orchestrate_task_cycle.selection_publication import (
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


def test_selected_successor_prepare_renders_body_free_authority_bundle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _initialize_active_task(tmp_path)
    decision = _selected_receipt(tmp_path, capsys)
    candidate = tmp_path / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    task_binding = _binding(tmp_path, candidate)

    prepared = prepare_selected_successor_bundle(
        tmp_path,
        source_decision=decision,
        task_source=task_binding,
        at="2026-07-22T20:00:00+09:00",
    )
    replay = prepare_selected_successor_bundle(
        tmp_path,
        source_decision=decision,
        task_source=task_binding,
        at="2026-07-22T20:00:00+09:00",
    )
    bundle = load_selected_successor_bundle(tmp_path, prepared["bundle"])

    assert prepared["storage_schema_version"] == 4
    assert replay["bundle"] == prepared["bundle"]
    assert replay["mutation_performed"] is False
    assert [row["step"] for row in bundle["execution_order"]] == [1, 2, 3]
    assert [
        row["operation"]["operation_id"] for row in bundle["execution_order"]
    ] == [
        "mutate_task_state_index",
        "publish_selected_successor_topology",
        "settle_selected_successor_task_state",
    ]
    assert all(
        set(row["expected_result"]) == {"ref", "sha256"}
        and row["authority_bindings"][
            "must_be_validated_before_first_effect"
        ]
        is True
        for row in bundle["execution_order"]
    )
    serialized = json.dumps(bundle, sort_keys=True)
    assert "events" not in serialized
    assert "after_payload_b64" not in serialized
    assert bundle["recovery"]["next_step"] == "apply_task_state_plan_pending"
    assert "task-old" in (tmp_path / "task.md").read_text(encoding="utf-8")


def test_selected_successor_rejects_self_sealed_forgery_before_plan_write(
    tmp_path: Path,
) -> None:
    _initialize_active_task(tmp_path)
    candidate = tmp_path / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    body = {
        "schema_version": 2,
        "artifact_kind": "selection_decision_receipt",
        "outcome": "selected",
        "selected_task_id": "task-next",
        "receipt_id": "forged-selection",
        "not_authority": True,
        "mutation_performed": False,
    }
    canonical = (
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    forged = _write_json(
        tmp_path / ".task/forged-selection-receipt.json",
        {**body, "receipt_sha256": hashlib.sha256(canonical).hexdigest()},
    )
    plan_root = tmp_path / ".task/transition_plans"
    before = set(plan_root.glob("*.json")) if plan_root.exists() else set()

    with pytest.raises(ValueError):
        prepare_selected_successor_bundle(
            tmp_path,
            source_decision=_binding(tmp_path, forged),
            task_source=_binding(tmp_path, candidate),
            at="2026-07-22T20:00:00+09:00",
        )

    after = set(plan_root.glob("*.json")) if plan_root.exists() else set()
    assert after == before
    assert not (tmp_path / ".task/selection_publication/successor_bundles").exists()


def test_selected_successor_rejects_malformed_raw_cas_bundle_without_effect(
    tmp_path: Path,
) -> None:
    from orchestrate_task_cycle.selection_publication_store import (
        _canonical_json,
        _sha256_bytes,
        _successor_bundle_path,
    )

    tmp_path.mkdir(exist_ok=True)
    body = {
        "schema_version": 999,
        "artifact_kind": "wrong_bundle_kind",
        "extra": "workspace-controlled",
        "execution_order": [
            {
                "step": index,
                "action": action,
                "operation": {"operation_id": "different"},
            }
            for index, action in enumerate(
                (
                    "apply_task_state_plan_pending",
                    "publish_selected_successor_topology",
                    "settle_selected_successor_task_state",
                ),
                start=1,
            )
        ],
    }
    content_sha256 = _sha256_bytes(_canonical_json(body))
    value = {**body, "bundle_content_sha256": content_sha256}
    path = _successor_bundle_path(tmp_path, content_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(value))
    binding = {
        "ref": path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }

    with pytest.raises(ValueError):
        load_selected_successor_bundle(tmp_path, binding)

    assert not (tmp_path / "task.md").exists()
    assert not list((tmp_path / ".task").glob("transition_*receipts/*.json"))
    assert not (tmp_path / ".task/authorization").exists()


def test_selected_successor_rejects_noncanonical_raw_bundle_even_when_rebound(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, bundle, _proofs = _authorized_successor(tmp_path, capsys)
    path = tmp_path / prepared["bundle"]["ref"]
    path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    adjusted_binding = {
        "ref": prepared["bundle"]["ref"],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }

    with pytest.raises(ValueError, match="not canonical JSON"):
        load_selected_successor_bundle(tmp_path, adjusted_binding)


@pytest.mark.parametrize("forged_field", ("prepare", "receipt"))
def test_selected_successor_intent_index_rejects_forged_artifact_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    forged_field: str,
) -> None:
    from orchestrate_task_cycle.selection_publication_intent_index import (
        load_intent_index,
    )
    from orchestrate_task_cycle.selection_publication_store import _canonical_json

    prepared, bundle, proofs = _authorized_successor(tmp_path, capsys)
    if forged_field == "receipt":
        execute_selected_successor_bundle(
            tmp_path,
            bundle_binding=prepared["bundle"],
            authority_proofs=proofs,
            settled_at=AUTHORITY_LATER,
            skills_root=SKILLS_ROOT,
        )
    prepare = json.loads(
        (tmp_path / bundle["selection_prepare"]["ref"]).read_text(encoding="utf-8")
    )
    intent_sha256 = prepare["intent_sha256"]
    index_path = (
        tmp_path
        / ".task/selection_publication/intents/sha256"
        / intent_sha256
        / ("commit.json" if forged_field == "receipt" else "prepare.json")
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    original = tmp_path / index[forged_field]["ref"]
    forged = tmp_path / ".task/selection_publication/forged" / original.name
    forged.parent.mkdir(parents=True, exist_ok=True)
    forged.write_bytes(original.read_bytes())
    index[forged_field] = _binding(tmp_path, forged)
    body = {
        key: value
        for key, value in index.items()
        if key != "index_content_sha256"
    }
    index["index_content_sha256"] = hashlib.sha256(_canonical_json(body)).hexdigest()
    index_path.write_bytes(_canonical_json(index))

    with pytest.raises(ValueError, match=f"{forged_field} path differs"):
        load_intent_index(
            tmp_path, intent_sha256, committed=forged_field == "receipt"
        )


def _authorized_successor(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    _initialize_active_task(root)
    decision = _selected_receipt(root, capsys)
    candidate = root / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    prepared = prepare_selected_successor_bundle(
        root,
        source_decision=decision,
        task_source=_binding(root, candidate),
        at=AUTHORITY_AT,
    )
    bundle = load_selected_successor_bundle(root, prepared["bundle"])
    return prepared, bundle, prepare_authority_proofs(root, bundle)


@pytest.mark.parametrize("checkpoint", ("before_effect", "after_step1", "complete"))
def test_selected_successor_prepare_exact_replay_avoids_current_state_recompile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    checkpoint: str,
) -> None:
    prepared, bundle, proofs = _authorized_successor(tmp_path, capsys)
    if checkpoint == "after_step1":
        import orchestrate_task_cycle.selected_successor_execution as execution

        with monkeypatch.context() as crash:
            crash.setattr(
                execution,
                "publish_prepared",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("stop after step1")
                ),
            )
            with pytest.raises(RuntimeError, match="stop after step1"):
                execute_selected_successor_bundle(
                    tmp_path,
                    bundle_binding=prepared["bundle"],
                    authority_proofs=proofs,
                    settled_at=AUTHORITY_LATER,
                    skills_root=SKILLS_ROOT,
                )
    elif checkpoint == "complete":
        execute_selected_successor_bundle(
            tmp_path,
            bundle_binding=prepared["bundle"],
            authority_proofs=proofs,
            settled_at=AUTHORITY_LATER,
            skills_root=SKILLS_ROOT,
        )

    replay = prepare_selected_successor_bundle(
        tmp_path,
        source_decision=bundle["source_decision"],
        task_source=bundle["task_source"],
        at=bundle["created_at"],
    )

    assert replay["bundle"] == prepared["bundle"]
    assert replay["task_state_plan"] == prepared["task_state_plan"]
    assert replay["selection_prepare"] == prepared["selection_prepare"]
    assert replay["transaction_id"] == prepared["transaction_id"]
    assert replay["mutation_performed"] is False


@pytest.mark.parametrize("entrypoint", ("prepare_replay", "execute"))
def test_pristine_selected_successor_reopens_source_before_any_effect(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    entrypoint: str,
) -> None:
    import orchestrate_task_cycle.selected_successor_provenance as provenance

    prepared, bundle, proofs = _authorized_successor(tmp_path, capsys)
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        provenance,
        "validate_selected_source_for_prepared_successor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("forged prepared-source provenance")
        ),
    )

    with pytest.raises(ValueError, match="forged prepared-source provenance"):
        if entrypoint == "prepare_replay":
            prepare_selected_successor_bundle(
                tmp_path,
                source_decision=bundle["source_decision"],
                task_source=bundle["task_source"],
                at=bundle["created_at"],
            )
        else:
            execute_selected_successor_bundle(
                tmp_path,
                bundle_binding=prepared["bundle"],
                authority_proofs=proofs,
                settled_at=AUTHORITY_LATER,
                skills_root=SKILLS_ROOT,
            )

    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not list(
        (tmp_path / ".task/selection_publication/successor_authority_gates").glob(
            "**/*.json"
        )
    )


@pytest.mark.parametrize(
    ("tamper", "message"),
    (
        ("content", "index integrity failed"),
        ("bundle_path", "bundle integrity failed"),
        ("canonical", "not canonical JSON"),
    ),
)
def test_selected_successor_prepare_index_tamper_fails_before_recompile(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
    message: str,
) -> None:
    from orchestrate_task_cycle.selected_successor_index import (
        prepare_input_identity,
    )
    from orchestrate_task_cycle.selection_publication_store import (
        _canonical_json,
        _successor_prepare_index_path,
    )
    import manage_task_state_index.state.selected_successor as task_owner

    prepared, bundle, _proofs = _authorized_successor(tmp_path, capsys)
    _identity, input_sha256 = prepare_input_identity(
        bundle["source_decision"], bundle["task_source"], bundle["created_at"]
    )
    index_path = _successor_prepare_index_path(tmp_path, input_sha256)
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if tamper == "content":
        index["created_at"] = "2026-07-22T20:00:01+09:00"
        index_path.write_bytes(_canonical_json(index))
    elif tamper == "bundle_path":
        source = tmp_path / prepared["bundle"]["ref"]
        forged = tmp_path / ".task/selection_publication/forged/bundle.json"
        forged.parent.mkdir(parents=True, exist_ok=True)
        forged.write_bytes(source.read_bytes())
        index["bundle"] = _binding(tmp_path, forged)
        body = {
            key: value
            for key, value in index.items()
            if key != "index_content_sha256"
        }
        index["index_content_sha256"] = hashlib.sha256(
            _canonical_json(body)
        ).hexdigest()
        index_path.write_bytes(_canonical_json(index))
    else:
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task").rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(
        task_owner,
        "prepare_selected_successor",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("tampered index reached current-state compilation")
        ),
    )

    with pytest.raises(ValueError, match=message):
        prepare_selected_successor_bundle(
            tmp_path,
            source_decision=bundle["source_decision"],
            task_source=bundle["task_source"],
            at=bundle["created_at"],
        )

    after = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task").rglob("*")
        if path.is_file()
    }
    assert after == before


def test_selected_successor_prepare_index_rechecks_exact_source_bytes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared, bundle, _proofs = _authorized_successor(tmp_path, capsys)
    bundle_path = tmp_path / prepared["bundle"]["ref"]
    bundle_bytes = bundle_path.read_bytes()
    task_source = tmp_path / bundle["task_source"]["ref"]
    task_source.write_bytes(task_source.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="raw SHA-256"):
        prepare_selected_successor_bundle(
            tmp_path,
            source_decision=bundle["source_decision"],
            task_source=bundle["task_source"],
            at=bundle["created_at"],
        )

    assert bundle_path.read_bytes() == bundle_bytes


@pytest.mark.parametrize(
    "crash_state",
    ("blob_only", "prepare_only", "prepare_index_only", "active_without_index"),
)
def test_selected_successor_exact_intent_repairs_prepare_crash_matrix_o1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    crash_state: str,
) -> None:
    from orchestrate_task_cycle.selection_publication import (
        prepare_publication_intent,
    )
    from orchestrate_task_cycle.selection_publication_state import write_empty_state

    _initialize_active_task(tmp_path)
    decision = _selected_receipt(tmp_path, capsys)
    candidate = tmp_path / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    prepared = prepare_selected_successor_bundle(
        tmp_path,
        source_decision=decision,
        task_source=_binding(tmp_path, candidate),
        at="2026-07-22T20:00:00+09:00",
    )
    bundle = load_selected_successor_bundle(tmp_path, prepared["bundle"])
    intent = {
        "schema_version": 2,
        "kind": "selection_publication_intent",
        "source_decision": bundle["source_decision"],
        "task_source": bundle["task_source"],
        "task_state_plan": bundle["task_state_plan"],
    }
    prepare_path = tmp_path / bundle["selection_prepare"]["ref"]
    prepare_value = json.loads(prepare_path.read_text(encoding="utf-8"))
    index_path = (
        tmp_path
        / ".task/selection_publication/intents/sha256"
        / prepare_value["intent_sha256"]
        / "prepare.json"
    )
    if crash_state == "blob_only":
        prepare_path.unlink()
        index_path.unlink()
        write_empty_state(tmp_path)
    elif crash_state == "prepare_only":
        index_path.unlink()
        write_empty_state(tmp_path)
    elif crash_state == "prepare_index_only":
        write_empty_state(tmp_path)
    else:
        index_path.unlink()

    with monkeypatch.context() as bounded:
        bounded.setattr(
            publication,
            "_transactions_root",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("exact retry enumerated transaction history")
            ),
        )
        repaired = prepare_publication_intent(tmp_path, intent)

    assert repaired["transaction_id"] == bundle["transaction_id"]
    assert repaired["mutation_performed"] is True
    assert prepare_path.is_file()
    assert index_path.is_file()
    state = json.loads(
        (tmp_path / ".task/selection_publication/state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["active_transaction"]["transaction_id"] == bundle["transaction_id"]


def test_selected_successor_incomplete_authority_gate_has_zero_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, proofs = _authorized_successor(tmp_path, capsys)
    invalid = {
        **proofs,
        "settle_selected_successor_task_state": {
            **proofs["settle_selected_successor_task_state"],
            "pre_commit_verification": {
                **proofs["settle_selected_successor_task_state"][
                    "pre_commit_verification"
                ],
                "sha256": "0" * 64,
            },
        },
    }

    with pytest.raises(SystemExit, match="pre_commit_verification"):
        execute_selected_successor_bundle(
            tmp_path,
            bundle_binding=prepared["bundle"],
            authority_proofs=invalid,
            settled_at=AUTHORITY_LATER,
            skills_root=SKILLS_ROOT,
        )

    assert "task-old" in (tmp_path / "task.md").read_text(encoding="utf-8")
    assert not list((tmp_path / ".task").glob("transition_pending_receipts/*.json"))
    assert not list(
        (tmp_path / ".task/selection_publication/receipts").glob("*.json")
    )
    assert not list(
        (tmp_path / ".task/selection_publication/successor_authority_gates").glob(
            "**/*.json"
        )
    )


def test_selected_successor_recovers_after_publication_checkpoint(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, bundle, proofs = _authorized_successor(tmp_path, capsys)
    import manage_task_state_index.state.transition_plan as transition_plan

    with monkeypatch.context() as crash:
        crash.setattr(
            transition_plan,
            "settle_transition_external",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("crash after publication")
            ),
        )
        with pytest.raises(RuntimeError, match="crash after publication"):
            execute_selected_successor_bundle(
                tmp_path,
                bundle_binding=prepared["bundle"],
                authority_proofs=proofs,
                settled_at=AUTHORITY_LATER,
                skills_root=SKILLS_ROOT,
            )

    assert (tmp_path / bundle["execution_order"][0]["expected_result"]["ref"]).is_file()
    assert (tmp_path / bundle["execution_order"][1]["expected_result"]["ref"]).is_file()
    assert not (tmp_path / bundle["execution_order"][2]["expected_result"]["ref"]).exists()
    assert list(
        (tmp_path / ".task/selection_publication/successor_authority_gates").glob(
            "**/*.json"
        )
    )

    recovered = execute_selected_successor_bundle(
        tmp_path,
        bundle_binding=prepared["bundle"],
        authority_proofs=proofs,
        settled_at=AUTHORITY_LATER,
        skills_root=SKILLS_ROOT,
    )
    assert recovered["status"] == "complete"
    assert recovered["initial_checkpoints"] == {
        "apply_task_state_plan_pending": "exact",
        "publish_selected_successor_topology": "exact",
        "settle_selected_successor_task_state": "missing",
    }
    assert recovered["effect_actions"] == [
        "settle_selected_successor_task_state"
    ]


@pytest.mark.parametrize("crash_target", ("record_committed", "write_commit_index"))
def test_selected_successor_repairs_publication_commit_crash_points(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    crash_target: str,
) -> None:
    prepared, bundle, proofs = _authorized_successor(tmp_path, capsys)
    original = getattr(publication, crash_target)
    calls = 0

    def crash_once(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(f"crash at {crash_target}")
        return original(*args, **kwargs)

    with monkeypatch.context() as crash:
        crash.setattr(publication, crash_target, crash_once)
        with pytest.raises(RuntimeError, match=crash_target):
            execute_selected_successor_bundle(
                tmp_path,
                bundle_binding=prepared["bundle"],
                authority_proofs=proofs,
                settled_at=AUTHORITY_LATER,
                skills_root=SKILLS_ROOT,
            )

    receipt = bundle["execution_order"][1]["expected_result"]
    assert _binding(tmp_path, tmp_path / receipt["ref"]) == receipt
    prepare_value = json.loads(
        (tmp_path / bundle["selection_prepare"]["ref"]).read_text(encoding="utf-8")
    )
    commit_index = (
        tmp_path
        / ".task/selection_publication/intents/sha256"
        / prepare_value["intent_sha256"]
        / "commit.json"
    )
    assert not commit_index.exists()

    recovered = execute_selected_successor_bundle(
        tmp_path,
        bundle_binding=prepared["bundle"],
        authority_proofs=proofs,
        settled_at=AUTHORITY_LATER,
        skills_root=SKILLS_ROOT,
    )
    assert recovered["status"] == "complete"
    assert commit_index.is_file()
    assert "publish_selected_successor_topology" in recovered["effect_actions"]
    state = json.loads(
        (tmp_path / ".task/selection_publication/state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state["head"]["transaction_id"] == bundle["transaction_id"]


def test_historical_v3_intent_replay_does_not_roll_back_compact_head(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, bundle, proofs = _authorized_successor(tmp_path, capsys)
    execute_selected_successor_bundle(
        tmp_path,
        bundle_binding=prepared["bundle"],
        authority_proofs=proofs,
        settled_at=AUTHORITY_LATER,
        skills_root=SKILLS_ROOT,
    )
    historical_intent = {
        "schema_version": 2,
        "kind": "selection_publication_intent",
        "source_decision": bundle["source_decision"],
        "task_source": bundle["task_source"],
        "task_state_plan": bundle["task_state_plan"],
    }
    current = (tmp_path / "task.md").read_bytes()
    newer = b"# Task\n\n- Task ID: `task-newer`\n"
    successor = prepare_publication(
        tmp_path, _publication_plan(current, newer, "newer-head")
    )
    publish_prepared(tmp_path, successor["transaction_id"])
    state_path = tmp_path / ".task/selection_publication/state.json"
    before_state = state_path.read_bytes()

    replay = publication.prepare_publication_intent(tmp_path, historical_intent)

    assert replay["status"] == "already_committed"
    assert replay["mutation_performed"] is False
    assert state_path.read_bytes() == before_state
    assert publication_status(tmp_path)["current_head"]["head_transaction_id"] == successor[
        "transaction_id"
    ]
    assert (tmp_path / "task.md").read_bytes() == newer


def test_selected_successor_replays_partial_authority_consumption(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _bundle, proofs = _authorized_successor(tmp_path, capsys)
    import manage_agent_authority.settlement as authority_settlement

    original = authority_settlement.settle_owner_result
    calls = 0

    def crash_on_second(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("crash during authority settlement")
        return original(*args, **kwargs)

    with monkeypatch.context() as crash:
        crash.setattr(authority_settlement, "settle_owner_result", crash_on_second)
        with pytest.raises(RuntimeError, match="crash during authority settlement"):
            execute_selected_successor_bundle(
                tmp_path,
                bundle_binding=prepared["bundle"],
                authority_proofs=proofs,
                settled_at=AUTHORITY_LATER,
                skills_root=SKILLS_ROOT,
            )

    states = []
    for proof in proofs.values():
        reservation = json.loads(
            (tmp_path / proof["reservation"]["ref"]).read_text(encoding="utf-8")
        )
        states.append(
            json.loads(
                (
                    tmp_path
                    / ".task/authorization/state/reservations"
                    / f"{reservation['reservation_id']}.json"
                ).read_text(encoding="utf-8")
            )["status"]
        )
    assert states == ["consumed", "reserved", "reserved"]

    recovered = execute_selected_successor_bundle(
        tmp_path,
        bundle_binding=prepared["bundle"],
        authority_proofs=proofs,
        settled_at=AUTHORITY_LATER,
        skills_root=SKILLS_ROOT,
    )
    assert recovered["status"] == "complete"
    assert recovered["authority_preflight"][0][
        "exact_v3_settlement_replayed"
    ] is True
    replay = execute_selected_successor_bundle(
        tmp_path,
        bundle_binding=prepared["bundle"],
        authority_proofs=proofs,
        settled_at=AUTHORITY_LATER,
        skills_root=SKILLS_ROOT,
    )
    assert replay["idempotent_replay"] is True
    publication_use = recovered["authority_settlements"][1]["use_receipt"]
    use_value = json.loads(
        (tmp_path / publication_use["ref"]).read_text(encoding="utf-8")
    )
    execution_binding = use_value["execution_result"]
    execution = json.loads(
        (tmp_path / execution_binding["ref"]).read_text(encoding="utf-8")
    )
    assert execution["schema_version"] == 3
    assert execution["subject_after"] == {
        "ref": "task.md",
        "sha256": hashlib.sha256((tmp_path / "task.md").read_bytes()).hexdigest(),
    }


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
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
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
    assert prepare["storage_schema_version"] == 4
    assert prepare_replay["storage_schema_version"] == 4
    compact_state = json.loads(
        (tmp_path / ".task/selection_publication/state.json").read_text()
    )
    assert set(compact_state) == {
        "schema_version",
        "storage_schema_version",
        "kind",
        "head",
        "active_transaction",
        "state_content_sha256",
    }
    assert "receipts" not in compact_state
    prepare_value = json.loads((tmp_path / prepare["prepare_ref"]).read_text())
    intent_digest = prepare_value["intent_sha256"]
    assert (
        tmp_path
        / ".task/selection_publication/intents/sha256"
        / intent_digest
        / "prepare.json"
    ).is_file()
    apply_args = [
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
    task_before = task.read_bytes()
    ledger_before = (tmp_path / ".task/index.jsonl").read_bytes()
    markdown_before = (tmp_path / ".task/index.md").read_bytes()
    with pytest.raises(SystemExit, match="guarded all-three authority gate"):
        task_state.main(apply_args)
    assert task.read_bytes() == task_before
    assert (tmp_path / ".task/index.jsonl").read_bytes() == ledger_before
    assert (tmp_path / ".task/index.md").read_bytes() == markdown_before
    assert not list(
        (tmp_path / ".task/transition_pending_receipts").glob("*.json")
    )

    pending = apply_transition_plan(
        tmp_path,
        planned["plan_ref"],
        external_prepare={
            "ref": prepare["prepare_ref"],
            "sha256": prepare["prepare_sha256"],
        },
        _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
    )

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
    blocked = json.loads(capsys.readouterr().out)
    assert code == 2
    assert "guarded all-three authority gate" in blocked["error"]
    assert task.read_bytes() == task_before
    assert not (
        tmp_path
        / f".task/selection_publication/receipts/{prepare['transaction_id']}.json"
    ).exists()

    committed = publish_prepared(
        tmp_path,
        prepare["transaction_id"],
        _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
    )
    assert committed["activation_status"] == "pending_external_settlement"
    assert task.read_bytes() == candidate.read_bytes()
    assert publication_status(tmp_path)["status"] == "settlement_required"
    settle_args = [
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
    with pytest.raises(SystemExit, match="guarded all-three authority gate"):
        task_state.main(settle_args)
    assert not (
        tmp_path / f".task/transition_receipts/{plan['plan_id']}.json"
    ).exists()

    settled = settle_transition_external(
        tmp_path,
        planned["plan_ref"],
        {"ref": committed["receipt_ref"], "sha256": committed["receipt_sha256"]},
        _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
    )

    assert settled["status"] == "settled"
    assert settled["selection_consumption_allowed"] is True
    assert publication_status(tmp_path)["selection_consumption_allowed"] is True
    assert (
        tmp_path
        / ".task/selection_publication/intents/sha256"
        / intent_digest
        / "commit.json"
    ).is_file()
    task_state.append_event(
        tmp_path,
        {
            "event": "link",
            "id": old["id"],
            "updated_at": "2026-07-22T20:00:01+09:00",
            "links": [{"rel": "related_to", "id": "task-next"}],
        },
    )
    task_state.rebuild_markdown(tmp_path)
    from orchestrate_task_cycle.selection_publication_v2 import (
        validate_external_settlement_assertion,
    )

    validate_external_settlement_assertion(
        tmp_path,
        json.loads((tmp_path / committed["receipt_ref"]).read_text()),
        {"ref": committed["receipt_ref"], "sha256": committed["receipt_sha256"]},
    )
    descendant_status = publication_status(tmp_path)
    assert descendant_status["status"] == "clear"
    assert descendant_status["selection_consumption_allowed"] is True

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
    replay = publish_prepared(
        tmp_path,
        prepare["transaction_id"],
        _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
    )
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
    with monkeypatch.context() as bounded:
        bounded.setattr(
            publication,
            "_transactions_root",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("normal replay enumerated transaction history")
            ),
        )
        replay_without_historical_body = publish_prepared(
            tmp_path,
            prepare["transaction_id"],
            _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
        )
    assert replay_without_historical_body["status"] == "committed"
    assert replay_without_historical_body["mutation_performed"] is False
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
    bounded_replay = publish_prepared(
        tmp_path,
        prepare["transaction_id"],
        _selected_successor_execution_token=_SELECTED_SUCCESSOR_EXECUTION_TOKEN,
    )
    assert bounded_replay["mutation_performed"] is False
    assert publication_status(tmp_path, deep=True)["status"] == "recovery_required"
