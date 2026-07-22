from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from orchestrate_task_cycle.selection_decision_receipt import (
    render_preliminary_selection_decision,
    render_selection_decision_receipt,
)
from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.selection_tick_contract import validate_selection_tick_v2
from orchestrate_task_cycle.selection_tick_policy import EVIDENCE_CLASSES
from orchestrate_task_cycle.selection_publication import (
    prepare_publication,
    publish_prepared,
)
from selection_synthesis_support import persisted_selection_synthesis


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _reseal_tick(packet: dict[str, object]) -> None:
    rows = packet["watch_entries"]
    assert isinstance(rows, list)
    rows.sort(key=lambda row: (str(row["kind"]), str(row["watch_id"])))
    packet["observed_input_manifest_sha256"] = hashlib.sha256(
        _canonical(rows)
    ).hexdigest()
    packet["authority_scope_ids"] = sorted(
        str(row["authority_scope_id"])
        for row in rows
        if row.get("kind") == "effective_authority"
    )
    body = {key: value for key, value in packet.items() if key != "packet_id"}
    packet["packet_id"] = (
        "selection-tick-" + hashlib.sha256(_canonical(body)).hexdigest()[:32]
    )


def _repo(tmp_path: Path) -> Path:
    _write(tmp_path / "task.md", "# Task\n")
    _write(tmp_path / ".agent_goal" / "final_goal.md", "# Goal\n")
    manifest = {
        "implementation_path": ".codex/skills/example/scripts/adapter.py",
        "legacy_compatibility_path": ".task/domain_adapter.py",
        "renderer_path": ".codex/skills/example/scripts/render.py",
    }
    _write(
        tmp_path / ".codex/skills/novel-kg-workflow-adapter/adapter.manifest.json",
        json.dumps(manifest),
    )
    _write(tmp_path / ".codex/skills/example/scripts/adapter.py", "VALUE = 1\n")
    _write(tmp_path / ".codex/skills/example/scripts/render.py", "VALUE = 2\n")
    _write(tmp_path / ".task/domain_adapter.py", "VALUE = 3\n")
    return tmp_path


def _selection_receipt(
    root: Path, selected: dict[str, object], suffix: str = "A"
) -> dict[str, str]:
    trigger_path = root / f".task/cycle/cycle-{suffix}/selection-trigger.json"
    _write(
        trigger_path,
        json.dumps(selected, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _, synthesis_binding, _ = persisted_selection_synthesis(
        root,
        suffix=suffix,
        selected_task_id=f"task-next-{suffix}",
    )
    decision = render_preliminary_selection_decision(
        root,
        selected,
        synthesis_binding,
    )
    decision_path = root / f".task/cycle/cycle-{suffix}/selection-decision.json"
    _write(
        decision_path,
        json.dumps(decision, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    decision_binding = {
        "ref": decision_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(decision_path.read_bytes()).hexdigest(),
    }
    trigger_binding = {
        "ref": trigger_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(trigger_path.read_bytes()).hexdigest(),
    }
    receipt = render_selection_decision_receipt(
        root,
        selected,
        trigger_binding,
        decision_binding,
    )
    receipt_path = root / f".task/cycle/cycle-{suffix}/selection-receipt.json"
    _write(
        receipt_path,
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return {
        "ref": receipt_path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
    }


def test_selection_tick_records_baseline_then_noops(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    first = build_selection_tick(root)
    assert first["status"] == "baseline_recorded"
    assert first["agent_fanout_allowed"] is False
    second = build_selection_tick(root, previous=first)
    assert second["status"] == "no_op"
    assert (
        second["observed_input_manifest_sha256"]
        == first["observed_input_manifest_sha256"]
    )
    assert second["mutation_performed"] is False


def test_selection_tick_acknowledges_selection_receipt(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    _write(root / ".agent_goal/final_goal.md", "# Changed Goal\n")
    selected = build_selection_tick(root, previous=baseline)
    assert selected["status"] == "selection_required"
    receipt_binding = _selection_receipt(root, selected)

    with pytest.raises(ValueError, match="exact packet ID acknowledgement"):
        build_selection_tick(root, previous=selected)
    with pytest.raises(ValueError, match="persisted decision receipt"):
        build_selection_tick(
            root,
            previous=selected,
            acknowledge_selection_tick_id=selected["packet_id"],
        )
    with pytest.raises(ValueError, match="persisted decision receipt"):
        build_selection_tick(
            root,
            previous=selected,
            acknowledge_selection_tick_id=selected["packet_id"],
            selection_receipt_ref="missing/selection-receipt-A.json",
            selection_receipt_sha256="a" * 63,
        )
    with pytest.raises(ValueError, match="exact packet ID acknowledgement"):
        build_selection_tick(
            root,
            previous=selected,
            acknowledge_selection_tick_id="selection-tick-" + "0" * 32,
            selection_receipt_ref=receipt_binding["ref"],
            selection_receipt_sha256=receipt_binding["sha256"],
        )
    rebased = build_selection_tick(
        root,
        previous=selected,
        acknowledge_selection_tick_id=selected["packet_id"],
        selection_receipt_ref=receipt_binding["ref"],
        selection_receipt_sha256=receipt_binding["sha256"],
    )
    assert rebased["status"] == "baseline_recorded"
    assert rebased["baseline_rebased"] is True
    assert rebased["selection_acknowledgement_status"] == "accepted"
    assert rebased["acknowledged_selection_tick_id"] == selected["packet_id"]
    acknowledgement = rebased["selection_acknowledgement_binding"]
    assert acknowledgement["trigger_tick_id"] == selected["packet_id"]
    assert acknowledgement["selection_receipt_ref"] == receipt_binding["ref"]
    assert acknowledgement["selection_receipt_sha256"] == receipt_binding["sha256"]

    omitted = build_selection_tick(root, previous=rebased)
    assert omitted["status"] == "no_op"


def test_selection_tick_rejects_raw_exact_premise_wake(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    premise = root / "processed/candidate/coverage.json"
    _write(premise, '{"coverage": 0.2}\n')
    with pytest.raises(ValueError, match="cannot open selection re-entry"):
        build_selection_tick(
            root,
            premise_paths=["processed/candidate/coverage.json"],
            premise_ids=["premise-coverage-A"],
            premise_contract="raw_exact_file_v1",
        )


def test_selection_tick_acknowledgement_carries_effective_authority(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    _write(root / ".agent_goal/final_goal.md", "# Changed Goal\n")
    selected = build_selection_tick(root, previous=baseline)
    scope_id = "authority-scope-" + "b" * 32
    selected["watch_entries"].append(
        {
            "watch_id": "watch-"
            + hashlib.sha256(scope_id.encode("utf-8")).hexdigest()[:24],
            "kind": "effective_authority",
            "evidence_class": "authority",
            "authority_scope_id": scope_id,
            "effective_authority_fingerprint": "c" * 64,
            "decision": "approval_required",
            "axis_statuses": {"authority": "approval_required"},
        }
    )
    _reseal_tick(selected)
    receipt_binding = _selection_receipt(root, selected, "authority")
    rebased = build_selection_tick(
        root,
        previous=selected,
        acknowledge_selection_tick_id=selected["packet_id"],
        selection_receipt_ref=receipt_binding["ref"],
        selection_receipt_sha256=receipt_binding["sha256"],
    )

    omitted = build_selection_tick(root, previous=rebased)
    assert omitted["status"] == "no_op"
    assert omitted["authority_scope_ids"] == rebased["authority_scope_ids"]
    assert omitted["authority_scope_ids"] == [scope_id]


def test_selection_tick_acknowledgement_rejects_nonsticky_drift(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    _write(root / ".agent_goal/final_goal.md", "# Changed Goal\n")
    selected = build_selection_tick(root, previous=baseline)
    receipt_binding = _selection_receipt(root, selected, "drift")
    _write(root / ".agent_goal/final_goal.md", "# Drifted Again\n")

    rejected = build_selection_tick(
        root,
        previous=selected,
        acknowledge_selection_tick_id=selected["packet_id"],
        selection_receipt_ref=receipt_binding["ref"],
        selection_receipt_sha256=receipt_binding["sha256"],
    )

    assert rejected["status"] == "selection_required"
    assert rejected["reason"] == "selection_inputs_changed_during_acknowledgement"
    assert rejected["baseline_rebased"] is False
    assert rejected["selection_acknowledgement_status"] == "rejected_input_drift"
    assert rejected["acknowledged_selection_tick_id"] is None


def test_selection_tick_consumes_terminal_wait_embedded_baseline(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)

    packet = build_selection_tick(
        root,
        previous={"terminal_wait": {"selection_tick_baseline": baseline}},
    )

    assert packet["status"] == "no_op"


def test_selection_tick_rejects_tampered_or_nonbaseline_previous_packet(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    baseline["agent_fanout_allowed"] = True

    with pytest.raises(ValueError, match="valid terminal-wait baseline"):
        build_selection_tick(root, previous=baseline)


def test_rebased_previous_must_descend_exactly_from_receipt_trigger(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    _write(root / ".agent_goal/final_goal.md", "# Changed Goal\n")
    selected = build_selection_tick(root, previous=baseline)
    receipt = _selection_receipt(root, selected, "lineage")
    rebased = build_selection_tick(
        root,
        previous=selected,
        acknowledge_selection_tick_id=selected["packet_id"],
        selection_receipt_ref=receipt["ref"],
        selection_receipt_sha256=receipt["sha256"],
    )
    forged = json.loads(json.dumps(rebased))
    workflow_row = next(
        row for row in forged["watch_entries"] if row["kind"] == "workflow_input"
    )
    workflow_row["sha256"] = "f" * 64
    _reseal_tick(forged)
    assert validate_selection_tick_v2(forged) == forged

    with pytest.raises(ValueError, match="not a valid terminal-wait baseline"):
        build_selection_tick(root, previous=forged)


def test_selection_tick_opens_derive_for_content_delta(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    first = build_selection_tick(root)
    _write(root / ".agent_goal/final_goal.md", "# Changed Goal\n")
    changed = build_selection_tick(root, previous=first)
    assert changed["status"] == "selection_required"
    assert changed["reason"] == "material_wake_predicate_satisfied"
    assert changed["agent_fanout_allowed"] is True
    assert changed["full_cycle_allowed"] is False


def test_explicit_raw_exact_premise_cannot_open_selection(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    premise = root / "processed/candidate/coverage.json"
    _write(premise, '{"coverage": 0.2}\n')
    with pytest.raises(ValueError, match="cannot open selection re-entry"):
        build_selection_tick(
            root,
            premise_paths=["processed/candidate/coverage.json"],
            premise_ids=["premise-coverage-A"],
            premise_contract="raw_exact_file_v1",
        )


def test_selection_tick_rejects_external_or_missing_explicit_path(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    with pytest.raises(ValueError, match="outside repository"):
        build_selection_tick(
            root,
            premise_paths=[str(tmp_path.parent / "outside.json")],
            premise_ids=["premise-outside"],
        )
    with pytest.raises(ValueError, match="does not exist"):
        build_selection_tick(
            root,
            premise_paths=["processed/missing.json"],
            premise_ids=["premise-missing"],
        )
    with pytest.raises(ValueError, match="requires one unique"):
        build_selection_tick(root, premise_paths=["task.md"])
    with pytest.raises(ValueError, match="parent traversal"):
        build_selection_tick(root, watch_paths=["../missing.json"])


def test_non_active_pack_static_change_is_observed_without_semantic_wake(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    pack = root / ".task/task_pack/pack-A.json"
    _write(pack, '{"pack_id":"pack-A","status":"completed","items":[]}\n')
    baseline = build_selection_tick(root)
    _write(pack, '{"pack_id":"pack-A","status":"active","items":[]}\n')

    changed = build_selection_tick(root, previous=baseline)

    assert changed["status"] == "no_op"
    assert changed["material_changed_watch_entries"] == []
    assert any(
        row["path"] == ".task/task_pack/pack-A.json" for row in changed["watch_entries"]
    )


def test_task_pack_watch_separates_current_pointer_from_completed_history(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _write(
        root / "task.md",
        "# Task\n\n- Status: `active`\n- Executable: `true`\n- Task Pack: `pack-current`\n",
    )
    current = root / ".task/task_pack/pack-current.json"
    history = root / ".task/task_pack/pack-history.json"
    _write(current, '{"pack_id":"pack-current","status":"active","items":[]}\n')
    _write(history, '{"pack_id":"pack-history","status":"completed","items":[]}\n')
    baseline = build_selection_tick(
        root,
        watched_evidence_classes=["task_pack"],
        wake_predicates=["current-task-pack-changed"],
    )
    rows = {row.get("path"): row for row in baseline["watch_entries"]}
    assert rows[".task/task_pack/pack-current.json"]["evidence_class"] == "task_pack"
    assert rows[".task/task_pack/pack-history.json"]["evidence_class"] == "task_state"

    _write(history, '{"pack_id":"pack-history","status":"completed","items":[{}]}\n')
    historical_change = build_selection_tick(root, previous=baseline)
    assert historical_change["status"] == "no_op"
    assert historical_change["material_changed_watch_entries"] == []

    history.unlink()
    historical_removal = build_selection_tick(root, previous=historical_change)
    assert historical_removal["status"] == "no_op"
    assert historical_removal["material_changed_watch_entries"] == []

    _write(current, '{"pack_id":"pack-current","status":"active","items":[{}]}\n')
    current_change = build_selection_tick(root, previous=historical_removal)
    assert current_change["status"] == "selection_required"
    assert current_change["material_changed_watch_entries"]


def test_bound_current_pack_and_custom_watch_deletion_are_material(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _write(
        root / "task.md",
        "# Task\n\n- Status: `active`\n- Executable: `true`\n- Task Pack: `pack-current`\n",
    )
    pack = root / ".task/task_pack/pack-current.json"
    _write(pack, '{"pack_id":"pack-current","status":"active","items":[]}\n')
    pack_baseline = build_selection_tick(
        root,
        watched_evidence_classes=["task_pack"],
        wake_predicates=["current-task-pack-changed"],
    )
    pack.unlink()
    removed_pack = build_selection_tick(root, previous=pack_baseline)
    assert removed_pack["status"] == "selection_required"
    assert removed_pack["material_changed_watch_entries"][0]["change_kind"] == "removed"

    custom = root / "residual/current-input.json"
    _write(custom, '{"residual":"open"}\n')
    custom_baseline = build_selection_tick(
        root,
        watch_paths=["residual/current-input.json"],
        watched_evidence_classes=["custom_watch"],
        wake_predicates=["current-residual-input-changed"],
    )
    custom.unlink()
    removed_custom = build_selection_tick(root, previous=custom_baseline)
    assert removed_custom["status"] == "selection_required"
    assert removed_custom["material_changed_watch_entries"][0]["change_kind"] == "removed"


def test_current_pack_completion_remains_material_when_pointer_moves_to_history(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    pack = root / ".task/task_pack/pack-current.json"
    _write(
        root / "task.md",
        "# Task\n\n- Status: `active`\n- Executable: `true`\n- Task Pack: `pack-current`\n",
    )
    _write(pack, '{"pack_id":"pack-current","status":"active","items":[]}\n')
    baseline = build_selection_tick(
        root,
        watched_evidence_classes=["task_pack"],
        wake_predicates=["current-task-pack-changed"],
    )
    _write(
        root / "task.md",
        "# Task\n\n- Status: `completed`\n- Executable: `false`\n- Task Pack: `none`\n",
    )
    _write(pack, '{"pack_id":"pack-current","status":"completed","items":[]}\n')

    completed = build_selection_tick(root, previous=baseline)

    assert completed["status"] == "selection_required"
    assert any(
        row["evidence_class"] == "task_pack"
        for row in completed["material_changed_watch_entries"]
    )
    assert validate_selection_tick_v2(completed) == completed


def test_retirement_settlement_surface_is_history_not_semantic_wake(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    activation = root / ".task/task_pack_retirement/activations/lgra-test.json"
    _write(
        activation,
        '{"artifact_kind":"legacy_task_pack_retirement_activation"}\n',
    )

    changed = build_selection_tick(root, previous=baseline)

    assert changed["status"] == "no_op"
    assert changed["material_changed_watch_entries"] == []
    assert any(
        row.get("path") == ".task/task_pack_retirement/activations/lgra-test.json"
        for row in changed["watch_entries"]
    )


def test_selection_tick_discovers_adapter_manifests_without_repo_specific_skill_name(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    manifest = {
        "implementation_path": ".codex/skills/second/scripts/adapter.py",
        "legacy_compatibility_path": ".task/second_adapter.py",
        "renderer_path": ".codex/skills/second/scripts/render.py",
    }
    _write(root / ".codex/skills/second/adapter.manifest.json", json.dumps(manifest))
    _write(root / ".codex/skills/second/scripts/adapter.py", "VALUE = 4\n")
    _write(root / ".codex/skills/second/scripts/render.py", "VALUE = 5\n")
    _write(root / ".task/second_adapter.py", "VALUE = 6\n")

    baseline = build_selection_tick(root)
    _write(root / ".codex/skills/second/scripts/adapter.py", "VALUE = 7\n")
    changed = build_selection_tick(root, previous=baseline)

    assert changed["status"] == "no_op"
    assert changed["material_changed_watch_entries"] == []
    assert any(
        row["path"] == ".codex/skills/second/adapter.manifest.json"
        for row in changed["watch_entries"]
    )
    assert any(
        row["path"] == ".codex/skills/second/scripts/adapter.py"
        for row in changed["watch_entries"]
    )
    assert next(
        row
        for row in changed["watch_entries"]
        if row.get("path") == ".task/second_adapter.py"
    )["evidence_class"] == "adapter"

    custom_baseline = build_selection_tick(
        root,
        watched_evidence_classes=["custom_watch"],
        wake_predicates=["custom-runtime-input-changed"],
    )
    _write(root / ".task/second_adapter.py", "VALUE = 7\n")
    custom_change = build_selection_tick(root, previous=custom_baseline)
    assert custom_change["status"] == "no_op"
    assert custom_change["material_changed_watch_entries"] == []

    adapter_baseline = build_selection_tick(
        root,
        watched_evidence_classes=["adapter"],
        wake_predicates=["required-adapter-revision-changed"],
    )
    _write(root / ".task/second_adapter.py", "VALUE = 8\n")
    adapter_change = build_selection_tick(root, previous=adapter_baseline)
    assert adapter_change["status"] == "selection_required"
    assert adapter_change["material_changed_watch_entries"]

    broad_baseline = build_selection_tick(
        root,
        watched_evidence_classes=sorted(EVIDENCE_CLASSES),
    )
    _write(root / ".codex/skills/second/scripts/adapter.py", "VALUE = 8\n")
    broad_change = build_selection_tick(root, previous=broad_baseline)
    assert broad_change["status"] == "no_op"
    assert broad_change["material_changed_watch_entries"] == []

    relevant_baseline = build_selection_tick(
        root,
        watched_evidence_classes=["adapter"],
        wake_predicates=["required-adapter-revision-changed"],
        minimum_material_delta="one-required-adapter-revision-change",
    )
    _write(root / ".codex/skills/second/scripts/adapter.py", "VALUE = 9\n")
    relevant_change = build_selection_tick(root, previous=relevant_baseline)

    assert relevant_change["status"] == "selection_required"
    assert relevant_change["changed_evidence_classes"] == ["adapter"]
    assert relevant_change["material_changed_watch_entries"]


def test_task_rename_archive_and_index_render_are_nonmaterial(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    watch_paths = [".task/archive/task-old.md", ".task/index.md"]
    baseline = build_selection_tick(
        root,
        watch_paths=watch_paths,
        watched_evidence_classes=["custom_watch", "task_state"],
    )
    _write(root / "task.md", "# Renamed Task\n")
    _write(root / ".task/archive/task-old.md", "# Historical Task\n")
    _write(root / ".task/index.md", "# Rendered Index\n")

    changed = build_selection_tick(
        root,
        previous=baseline,
        watch_paths=watch_paths,
    )

    assert changed["status"] == "no_op"
    assert changed["selection_required"] is False
    assert changed["agent_fanout_allowed"] is False
    assert changed["material_changed_watch_entries"] == []
    assert set(changed["changed_evidence_classes"]) == {"task_state"}


def test_acknowledgement_absorbs_only_nonmaterial_workflow_drift(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    baseline = build_selection_tick(root)
    _write(root / ".agent_goal/final_goal.md", "# Changed Goal\n")
    selected = build_selection_tick(root, previous=baseline)
    receipt = _selection_receipt(root, selected, "nonmaterial-drift")
    _write(root / "task.md", "# Renamed During Selection\n")

    rebased = build_selection_tick(
        root,
        previous=selected,
        acknowledge_selection_tick_id=selected["packet_id"],
        selection_receipt_ref=receipt["ref"],
        selection_receipt_sha256=receipt["sha256"],
    )
    replay = build_selection_tick(root, previous=rebased)

    assert rebased["status"] == "baseline_recorded"
    assert rebased["selection_acknowledgement_status"] == "accepted"
    assert rebased["material_changed_watch_entries"] == []
    assert rebased["changed_evidence_classes"] == ["task_state"]
    assert replay["status"] == "no_op"


def test_selection_tick_routes_pending_publication_to_recovery(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    task = (root / "task.md").read_bytes()

    prepare_publication(
        root,
        {
            "schema_version": 1,
            "kind": "selection_publication_plan",
            "selection_id": "selection-A",
            "source_decision_id": "derive-A",
            "source_decision_sha256": "a" * 64,
            "targets": [
                {
                    "role": "task_alias",
                    "target_ref": "task.md",
                    "before_sha256": hashlib.sha256(task).hexdigest(),
                    "after_payload_b64": base64.b64encode(b"# Selected\n").decode(
                        "ascii"
                    ),
                }
            ],
        },
    )

    packet = build_selection_tick(root)

    assert packet["status"] == "recovery_required"
    assert packet["selection_required"] is False
    assert packet["agent_fanout_allowed"] is False
    assert packet["next_action"] == "recover_selection_publication"
    assert len(packet["pending_selection_publication_ids"]) == 1


def test_selection_tick_blocks_committed_selection_head_drift(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    task = (root / "task.md").read_bytes()
    prepared = prepare_publication(
        root,
        {
            "schema_version": 1,
            "kind": "selection_publication_plan",
            "selection_id": "selection-A",
            "source_decision_id": "derive-A",
            "source_decision_sha256": "a" * 64,
            "targets": [
                {
                    "role": "task_alias",
                    "target_ref": "task.md",
                    "before_sha256": hashlib.sha256(task).hexdigest(),
                    "after_payload_b64": base64.b64encode(b"# Selected\n").decode(
                        "ascii"
                    ),
                }
            ],
        },
    )
    publish_prepared(root, prepared["transaction_id"])
    _write(root / "task.md", "# Drifted\n")

    packet = build_selection_tick(root)

    assert packet["status"] == "drift_blocked"
    assert packet["selection_required"] is False
    assert packet["next_action"] == "repair_selection_publication_drift"


def test_custom_watch_paths_extend_defaults_and_nonmaterial_delta_does_not_fan_out(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _write(root / "notes/cosmetic.md", "one\n")
    baseline = build_selection_tick(
        root,
        watch_paths=["notes/cosmetic.md"],
        watched_evidence_classes=["goal_truth"],
        wake_predicates=["goal-truth-digest-changed"],
        minimum_material_delta="one-goal-truth-digest-change",
    )
    assert any(row.get("path") == "task.md" for row in baseline["watch_entries"])
    _write(root / "notes/cosmetic.md", "two\n")

    packet = build_selection_tick(
        root, previous=baseline, watch_paths=["notes/cosmetic.md"]
    )

    assert packet["status"] == "no_op"
    assert packet["reason"] == "changed_inputs_outside_watched_evidence_classes"
    assert packet["changed_evidence_classes"] == ["custom_watch"]
    assert packet["agent_fanout_allowed"] is False
