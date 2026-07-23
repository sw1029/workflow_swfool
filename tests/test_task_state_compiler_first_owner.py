from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "manage-task-state-index" / "scripts",
    ROOT / "record-agent-work-log" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from manage_task_state_index import index as task_index  # noqa: E402
from manage_task_state_index.state import transition_apply  # noqa: E402
from manage_task_state_index.state import scan_transition as scan_transition_module  # noqa: E402
from manage_task_state_index.state.owner_validation import (  # noqa: E402
    validate_external_transition_receipt,
    validate_owner_result,
)
from manage_task_state_index.state.scan_transition import (  # noqa: E402
    apply_scan,
    load_scan_compilation,
    prepare_scan,
)
from manage_task_state_index.state.scan_projection_repair import (  # noqa: E402
    expected_projection_sha256,
)
from manage_task_state_index.state.selected_successor import (  # noqa: E402
    prepare_selected_successor,
)


AT = "2026-07-23T10:00:00+09:00"


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return path


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _tree_snapshot(root: Path) -> dict[str, tuple[object, ...]]:
    snapshot: dict[str, tuple[object, ...]] = {}
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        if path.is_symlink():
            body: object = ("symlink", path.readlink().as_posix())
        elif path.is_file():
            body = ("file", path.read_bytes())
        else:
            body = ("directory", None)
        snapshot[path.relative_to(root).as_posix()] = (
            metadata.st_mode, metadata.st_mtime_ns, body,
        )
    return snapshot


def _reseal_compilation(value: dict[str, object]) -> None:
    body = {key: item for key, item in value.items()
            if key != "compilation_sha256"}
    value["compilation_sha256"] = hashlib.sha256(
        json.dumps(
            body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


def _authority_inputs(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    reservation = _write_json(root / ".task/authorization/reservation.json", {})
    precommit = _write_json(
        root / ".task/authorization/precommit.json", {"verified_at": AT}
    )
    return _binding(root, reservation), _binding(root, precommit)


def test_scan_compiler_separates_logical_updates_from_exact_event_batch(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / ".task/validation/result.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Before\n", encoding="utf-8")
    digest = task_index.sha256_file(artifact)
    for item_id, updated in (("val-a", "2026-07-22T01:00:00+09:00"),
                             ("val-b", "2026-07-22T02:00:00+09:00")):
        task_index.append_event(tmp_path, {
            "event": "upsert", "id": item_id, "type": "validation",
            "status": "passed", "path": ".task/validation/result.md",
            "title": "Before", "content_sha256": digest, "updated_at": updated,
        })
    task_index.rebuild_markdown(tmp_path)
    before_count = len(task_index.load_events(tmp_path))
    artifact.write_text("# After\n", encoding="utf-8")

    prepared = prepare_scan(tmp_path, at=AT)
    assert prepared["logical_update_count"] == 1
    assert prepared["event_count"] == 3
    applied = apply_scan(tmp_path, prepared["compilation_binding"])
    assert applied["event_count"] == 3
    assert len(task_index.load_events(tmp_path)) == before_count + 3
    owner = json.loads((tmp_path / applied["owner_result_binding"]["ref"]).read_text())
    assert owner["logical_update_count"] == 1
    assert owner["event_batch"]["event_count"] == 3
    assert owner["post_check"]["would_change"] is False
    assert apply_scan(tmp_path, prepared["compilation_binding"])["status"] == "already_applied"


def test_apply_scan_recovers_committed_transition_before_scan_receipt(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "task.md"
    artifact.write_text("# Task\n", encoding="utf-8")
    prepared = prepare_scan(tmp_path, at=AT)
    compilation = json.loads(
        (tmp_path / prepared["compilation_binding"]["ref"]).read_text()
    )
    snapshot = tmp_path / compilation["snapshot_materializations"][0]["target_ref"]
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(artifact.read_bytes())

    transition = task_index.apply_transition_plan(
        tmp_path, prepared["plan_binding"]["ref"]
    )
    scan_receipt = (
        tmp_path / ".task/scan_receipts" / f"{prepared['compilation_id']}.json"
    )
    assert transition["status"] == "applied"
    assert snapshot.read_bytes() == artifact.read_bytes()
    assert not scan_receipt.exists()
    committed_ledger = (tmp_path / ".task/index.jsonl").read_bytes()
    committed_projection = (tmp_path / ".task/index.md").read_bytes()

    recovered = apply_scan(tmp_path, prepared["compilation_binding"])

    assert recovered["status"] == "applied"
    assert snapshot.read_bytes() == artifact.read_bytes()
    assert (tmp_path / ".task/index.jsonl").read_bytes() == committed_ledger
    assert (tmp_path / ".task/index.md").read_bytes() == committed_projection
    owner_result = json.loads(scan_receipt.read_text(encoding="utf-8"))
    assert owner_result["transition_receipt"] == transition[
        "execution_result_binding"
    ]


def test_apply_scan_recovers_batch_committed_before_transition_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / ".task/validation/result.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Result\n", encoding="utf-8")
    prepared = prepare_scan(tmp_path, at=AT)
    plan_path = tmp_path / prepared["plan_binding"]["ref"]
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    transition_receipt = (
        tmp_path / ".task/transition_receipts" / f"{plan['plan_id']}.json"
    )
    scan_receipt = (
        tmp_path / ".task/scan_receipts" / f"{prepared['compilation_id']}.json"
    )

    publish_receipt = transition_apply._publish_receipt

    def interrupt_after_canonical_commit(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated crash before transition receipt publication")

    monkeypatch.setattr(
        transition_apply, "_publish_receipt", interrupt_after_canonical_commit
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        apply_scan(tmp_path, prepared["compilation_binding"])

    assert len(task_index.load_events(tmp_path)) == prepared["event_count"]
    assert not transition_receipt.exists()
    assert not scan_receipt.exists()
    committed_ledger = (tmp_path / ".task/index.jsonl").read_bytes()
    committed_projection = (tmp_path / ".task/index.md").read_bytes()

    monkeypatch.setattr(transition_apply, "_publish_receipt", publish_receipt)
    recovered = apply_scan(tmp_path, prepared["compilation_binding"])

    assert recovered["status"] == "applied"
    assert recovered["event_count"] == prepared["event_count"]
    assert transition_receipt.is_file()
    assert scan_receipt.is_file()
    assert (tmp_path / ".task/index.jsonl").read_bytes() == committed_ledger
    assert (tmp_path / ".task/index.md").read_bytes() == committed_projection
    owner_result = json.loads(scan_receipt.read_text(encoding="utf-8"))
    assert owner_result["transition_receipt"] == _binding(
        tmp_path, transition_receipt
    )
    assert owner_result["event_batch"]["event_count"] == prepared["event_count"]

    replay = apply_scan(tmp_path, prepared["compilation_binding"])
    assert replay["status"] == "already_applied"
    assert replay["mutation_performed"] is False
    assert (tmp_path / ".task/index.jsonl").read_bytes() == committed_ledger
    assert (tmp_path / ".task/index.md").read_bytes() == committed_projection


def test_apply_scan_recovers_projection_repair_before_scan_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = prepare_scan(tmp_path, at=AT)
    assert prepared["effect_mode"] == "projection_repair"
    compilation = json.loads(
        (tmp_path / prepared["compilation_binding"]["ref"]).read_text()
    )
    publish_result = scan_transition_module._publish_scan_result

    def interrupt_before_scan_receipt(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated crash after projection repair")

    monkeypatch.setattr(
        scan_transition_module, "_publish_scan_result", interrupt_before_scan_receipt
    )
    with pytest.raises(RuntimeError, match="after projection repair"):
        apply_scan(tmp_path, prepared["compilation_binding"])

    projection = tmp_path / ".task/index.md"
    expected_after = expected_projection_sha256([], compilation["created_at"])
    assert task_index.sha256_file(projection) == expected_after
    assert (
        tmp_path / ".task/scan_projection_intents"
        / f"{prepared['compilation_id']}.json"
    ).is_file()
    assert (
        tmp_path / ".task/scan_projection_receipts"
        / f"{prepared['compilation_id']}.json"
    ).is_file()
    assert not (
        tmp_path / ".task/scan_receipts" / f"{prepared['compilation_id']}.json"
    ).exists()
    repaired_bytes = projection.read_bytes()

    monkeypatch.setattr(
        scan_transition_module, "_publish_scan_result", publish_result
    )
    recovered = apply_scan(tmp_path, prepared["compilation_binding"])

    assert recovered["status"] == "applied"
    assert projection.read_bytes() == repaired_bytes
    owner = json.loads(
        (tmp_path / recovered["owner_result_binding"]["ref"]).read_text()
    )
    assert owner["projection"]["after_sha256"] == expected_after
    assert owner["transition_receipt"]["ref"].startswith(
        ".task/scan_projection_receipts/"
    )


def test_apply_scan_materializes_historical_receipt_after_task_descendant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original\n", encoding="utf-8")
    prepared = prepare_scan(tmp_path, at=AT)
    compilation_path = tmp_path / prepared["compilation_binding"]["ref"]
    compilation = json.loads(compilation_path.read_text(encoding="utf-8"))
    plan = json.loads(
        (tmp_path / prepared["plan_binding"]["ref"]).read_text(encoding="utf-8")
    )
    original_id = next(
        event["id"] for event in plan["events"]
        if event.get("type") == "task" and event.get("path") == "task.md"
    )
    original_snapshot = (
        tmp_path / compilation["snapshot_materializations"][0]["target_ref"]
    )
    publish_result = scan_transition_module._publish_scan_result

    def interrupt_before_scan_receipt(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("simulated crash before scan receipt publication")

    monkeypatch.setattr(
        scan_transition_module, "_publish_scan_result", interrupt_before_scan_receipt
    )
    with pytest.raises(RuntimeError, match="simulated crash"):
        apply_scan(tmp_path, prepared["compilation_binding"])
    monkeypatch.setattr(
        scan_transition_module, "_publish_scan_result", publish_result
    )
    assert original_snapshot.read_text(encoding="utf-8") == "# Original\n"

    task.write_text("# Later\n", encoding="utf-8")
    later_digest = task_index.sha256_file(task)
    later_snapshot = tmp_path / ".task/snapshots/task-later.md"
    later_snapshot.write_bytes(task.read_bytes())
    task_index.append_event(tmp_path, {
        "event": "upsert", "id": original_id, "status": "superseded",
        "updated_at": "2026-07-23T10:01:00+09:00",
    })
    task_index.append_event(tmp_path, {
        "event": "upsert", "id": "task-later", "type": "task",
        "status": "active", "path": "task.md", "title": "Later",
        "content_sha256": later_digest,
        "fields": {
            "record_class": "mutable_alias", "snapshot_digest": later_digest,
            "snapshot_path": ".task/snapshots/task-later.md",
            "canonical_id": "task-later", "alias_path": "task.md",
        },
        "updated_at": "2026-07-23T10:01:00+09:00",
    })
    task_index.rebuild_markdown(tmp_path)

    recovered = apply_scan(tmp_path, prepared["compilation_binding"])

    assert recovered["status"] == "applied"
    owner = json.loads(
        (tmp_path / recovered["owner_result_binding"]["ref"]).read_text()
    )
    assert owner["post_check"]["would_change"] is False
    assert original_snapshot.read_text(encoding="utf-8") == "# Original\n"
    assert task.read_text(encoding="utf-8") == "# Later\n"


def test_apply_scan_rejects_foreign_ledger_drift_before_batch(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "task.md"
    artifact.write_text("# Task\n", encoding="utf-8")
    prepared = prepare_scan(tmp_path, at=AT)
    compilation = json.loads(
        (tmp_path / prepared["compilation_binding"]["ref"]).read_text()
    )
    snapshot = tmp_path / compilation["snapshot_materializations"][0]["target_ref"]
    task_index.append_event(tmp_path, {
        "event": "upsert", "id": "task-foreign", "type": "task",
        "status": "active", "path": "task.md",
        "title": "Foreign", "content_sha256": task_index.sha256_file(artifact),
        "updated_at": "2026-07-23T10:01:00+09:00",
    })
    before = _tree_snapshot(tmp_path)

    with pytest.raises(ValueError, match="CAS mismatch"):
        apply_scan(tmp_path, prepared["compilation_binding"])

    assert _tree_snapshot(tmp_path) == before
    assert not snapshot.exists()
    assert not (
        tmp_path / ".task/scan_receipts" / f"{prepared['compilation_id']}.json"
    ).exists()


@pytest.mark.parametrize("effect_mode", ("projection_repair", "no_effect"))
def test_apply_scan_rejects_non_event_projection_drift_without_writes(
    tmp_path: Path, effect_mode: str,
) -> None:
    projection = tmp_path / ".task/index.md"
    if effect_mode == "no_effect":
        task_index.rebuild_markdown(tmp_path)
    prepared = prepare_scan(tmp_path, at=AT)
    assert prepared["effect_mode"] == effect_mode
    projection.parent.mkdir(parents=True, exist_ok=True)
    projection.write_text("# Foreign projection\n", encoding="utf-8")
    before = _tree_snapshot(tmp_path)

    with pytest.raises(ValueError, match="projection prestate changed"):
        apply_scan(tmp_path, prepared["compilation_binding"])

    assert _tree_snapshot(tmp_path) == before


@pytest.mark.parametrize(
    ("effect_mode", "outcome"),
    (("projection_repair", "confirmed_effect"),
     ("no_effect", "confirmed_no_effect")),
)
def test_non_event_scan_owner_validation_recomputes_current_evidence(
    tmp_path: Path, effect_mode: str, outcome: str,
) -> None:
    if effect_mode == "no_effect":
        task_index.rebuild_markdown(tmp_path)
    prepared = prepare_scan(tmp_path, at=AT)
    assert prepared["effect_mode"] == effect_mode
    applied = apply_scan(tmp_path, prepared["compilation_binding"])
    reservation, precommit = _authority_inputs(tmp_path)

    validated = validate_owner_result(
        tmp_path,
        owner_result=applied["owner_result_binding"],
        reservation=reservation,
        pre_commit_verification=precommit,
    )

    assert validated["outcome"] == outcome
    assert validated["validation_status"] == "valid"
    replay = apply_scan(tmp_path, prepared["compilation_binding"])
    assert replay["status"] == "already_applied"
    assert replay["mutation_performed"] is False


@pytest.mark.parametrize(
    ("effect_mode", "outcome"),
    (("projection_repair", "confirmed_effect"),
     ("no_effect", "confirmed_no_effect")),
)
def test_non_event_scan_receipt_accepts_legal_descendant_suffix(
    tmp_path: Path, effect_mode: str, outcome: str,
) -> None:
    if effect_mode == "no_effect":
        task_index.rebuild_markdown(tmp_path)
    prepared = prepare_scan(tmp_path, at=AT)
    applied = apply_scan(tmp_path, prepared["compilation_binding"])
    later = tmp_path / "later.md"
    later.write_text("# Later\n", encoding="utf-8")
    task_index.upsert_item(
        tmp_path, "validation", "later.md", "passed", item_id="val-later"
    )

    replay = apply_scan(tmp_path, prepared["compilation_binding"])
    assert replay["status"] == "already_applied"
    assert replay["mutation_performed"] is False
    reservation, precommit = _authority_inputs(tmp_path)
    validated = validate_owner_result(
        tmp_path,
        owner_result=applied["owner_result_binding"],
        reservation=reservation,
        pre_commit_verification=precommit,
        phase="historical",
    )
    assert validated["outcome"] == outcome
    # Historical authority receipts prove the suffix without sealing its
    # mutable length, so later append-only descendants preserve exact replay.
    assert validated["descendant_event_count"] == 0


def test_unapplied_self_sealed_projection_result_fails_replay_and_owner_validation(
    tmp_path: Path,
) -> None:
    prepared = prepare_scan(tmp_path, at=AT)
    assert prepared["effect_mode"] == "projection_repair"
    compilation = json.loads(
        (tmp_path / prepared["compilation_binding"]["ref"]).read_text()
    )
    empty_digest = hashlib.sha256(b"").hexdigest()
    expected_after = expected_projection_sha256([], compilation["created_at"])
    body = {
        "schema_version": 2,
        "artifact_kind": "task_state_index_scan_result",
        "operation": "scan",
        "effect_status": "confirmed_effect",
        "completed_at": compilation["created_at"],
        "compilation": prepared["compilation_binding"],
        "plan": None,
        "transition_receipt": None,
        "subject": {
            "kind": "task_index", "ref": ".task/index.jsonl",
            "before_sha256": empty_digest, "after_sha256": empty_digest,
        },
        "projection": {
            "ref": ".task/index.md",
            "before_sha256": compilation["projection_revision"]["sha256"],
            "after_sha256": expected_after,
        },
        "logical_update_count": 0,
        "event_batch": {
            "plan_id": compilation["compilation_id"],
            "before_event_count": 0,
            "event_count": 0,
            "event_payload_sha256": empty_digest,
        },
        "focus_results": compilation["focus_results"],
        "post_check": {
            "would_change": False, "logical_update_count": 0,
            "event_count": 0,
            "inventory_sha256": compilation["inventory"]["sha256"],
        },
    }
    forged = {
        **body,
        "result_sha256": hashlib.sha256(json.dumps(
            body, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")).hexdigest(),
    }
    receipt = _write_json(
        tmp_path / ".task/scan_receipts"
        / f"{compilation['compilation_id']}.json",
        forged,
    )
    before = _tree_snapshot(tmp_path)

    with pytest.raises(ValueError, match="current projection is stale"):
        apply_scan(tmp_path, prepared["compilation_binding"])
    assert _tree_snapshot(tmp_path) == before

    reservation, precommit = _authority_inputs(tmp_path)
    with pytest.raises(ValueError, match="current projection is stale"):
        validate_owner_result(
            tmp_path,
            owner_result=_binding(tmp_path, receipt),
            reservation=reservation,
            pre_commit_verification=precommit,
        )

    later = tmp_path / "later.md"
    later.write_text("# Later\n", encoding="utf-8")
    task_index.upsert_item(
        tmp_path, "validation", "later.md", "passed", item_id="val-later"
    )
    task_index.rebuild_markdown(tmp_path)
    descendant_before = _tree_snapshot(tmp_path)

    with pytest.raises(ValueError, match="projection repair receipt"):
        apply_scan(tmp_path, prepared["compilation_binding"])
    with pytest.raises(ValueError, match="projection repair receipt"):
        validate_owner_result(
            tmp_path,
            owner_result=_binding(tmp_path, receipt),
            reservation=reservation,
            pre_commit_verification=precommit,
            phase="historical",
        )
    assert _tree_snapshot(tmp_path) == descendant_before


def test_scan_compilation_rejects_raw_self_sealed_forged_id(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / ".task/validation/result.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Result\n", encoding="utf-8")
    prepared = prepare_scan(tmp_path, at=AT)
    source = tmp_path / prepared["compilation_binding"]["ref"]
    forged = json.loads(source.read_text(encoding="utf-8"))
    forged["compilation_id"] = "scan-" + "f" * 32
    _reseal_compilation(forged)
    path = _write_json(
        tmp_path / ".task/scan_compilations" / f"{forged['compilation_id']}.json",
        forged,
    )

    with pytest.raises(ValueError, match="deterministic identity"):
        load_scan_compilation(tmp_path, _binding(tmp_path, path))


@pytest.mark.parametrize("defect", ("effect_mode", "projection_revision"))
def test_scan_compilation_identity_binds_non_event_projection(
    tmp_path: Path, defect: str,
) -> None:
    task_index.rebuild_markdown(tmp_path)
    prepared = prepare_scan(tmp_path, at=AT)
    assert prepared["effect_mode"] == "no_effect"
    path = tmp_path / prepared["compilation_binding"]["ref"]
    forged = json.loads(path.read_text(encoding="utf-8"))
    if defect == "effect_mode":
        forged["effect_mode"] = "projection_repair"
    else:
        forged["projection_revision"]["sha256"] = "a" * 64
    _reseal_compilation(forged)
    _write_json(path, forged)

    with pytest.raises(ValueError, match="deterministic identity"):
        load_scan_compilation(tmp_path, _binding(tmp_path, path))


@pytest.mark.parametrize(
    ("defect", "message"),
    (
        ("inventory_digest", "inventory digest"),
        ("request_digest", "request digest"),
        ("event_count", "event count"),
        ("logical_count", "logical update count"),
        ("missing_plan", "plan binding"),
        ("non_event_request", "non-event bindings"),
    ),
)
def test_scan_compilation_rejects_self_sealed_derived_field_defects(
    tmp_path: Path, defect: str, message: str,
) -> None:
    artifact = tmp_path / ".task/validation/result.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("# Result\n", encoding="utf-8")
    prepared = prepare_scan(tmp_path, at=AT)
    path = tmp_path / prepared["compilation_binding"]["ref"]
    forged = json.loads(path.read_text(encoding="utf-8"))
    if defect == "inventory_digest":
        forged["inventory"]["sha256"] = "a" * 64
    elif defect == "request_digest":
        forged["request_sha256"] = "a" * 64
    elif defect == "event_count":
        forged["event_count"] += 1
    elif defect == "logical_count":
        forged["logical_update_count"] += 1
    elif defect == "missing_plan":
        forged["plan_binding"] = None
    else:
        forged["effect_mode"] = "no_effect"
    _reseal_compilation(forged)
    _write_json(path, forged)

    with pytest.raises(ValueError, match=message):
        load_scan_compilation(tmp_path, _binding(tmp_path, path))


def test_scan_owner_validation_accepts_valid_descendants_and_is_deterministic(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    prepared = prepare_scan(tmp_path, at=AT)
    applied = apply_scan(tmp_path, prepared["compilation_binding"])
    later = tmp_path / "later.md"
    later.write_text("# Later\n", encoding="utf-8")
    task_index.upsert_item(
        tmp_path, "validation", "later.md", "passed", item_id="val-later"
    )
    reservation, precommit = _authority_inputs(tmp_path)
    kwargs = {
        "owner_result": applied["owner_result_binding"],
        "reservation": reservation,
        "pre_commit_verification": precommit,
        "phase": "historical",
    }
    first = validate_owner_result(tmp_path, **kwargs)
    second = validate_owner_result(tmp_path, **kwargs)
    assert first == second
    assert first["outcome"] == "confirmed_effect"
    assert first["descendant_event_count"] == 0
    assert first["event_batch"]["event_count"] == 1
    assert first["validated_at"] == AT


def test_legacy_opaque_scan_result_is_unknown_effect(tmp_path: Path) -> None:
    legacy = _write_json(
        tmp_path / ".task/authorization/legacy-owner-result.json",
        {
            "schema_version": 1,
            "artifact_kind": "task_state_index_scan_result",
            "effect_status": "confirmed_effect",
            "completed_at": AT,
            "subject": {"kind": "task_index", "ref": ".task/index.jsonl",
                        "before_sha256": "a" * 64, "after_sha256": "b" * 64},
        },
    )
    reservation, precommit = _authority_inputs(tmp_path)
    result = validate_owner_result(
        tmp_path,
        owner_result=_binding(tmp_path, legacy),
        reservation=reservation,
        pre_commit_verification=precommit,
    )
    assert result["validation_status"] == "legacy_opaque"
    assert result["outcome"] == "unknown_effect"


def _selection_decision(path: Path, task_id: str) -> Path:
    core = {
        "schema_version": 2,
        "artifact_kind": "selection_decision_receipt",
        "receipt_id": "selection-decision-v2-test",
        "outcome": "selected",
        "selected_task_id": task_id,
        "not_authority": True,
        "mutation_performed": False,
    }
    return _write_json(path, {
        **core,
        "receipt_sha256": hashlib.sha256(
            (json.dumps(core, ensure_ascii=False, separators=(",", ":"),
                        sort_keys=True) + "\n").encode()
        ).hexdigest(),
    })


def test_selected_successor_renderer_derives_plan_without_writing_on_dry_run(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Old\n", encoding="utf-8")
    task_index.upsert_item(
        tmp_path, "task", "task.md", "active", item_id="task-old"
    )
    source = tmp_path / ".task/candidates/task-new.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# New\n\n- Task ID: `task-new`\n", encoding="utf-8")
    decision = _selection_decision(
        tmp_path / ".task/cycle/cycle-A/decision.json", "task-new"
    )
    result = prepare_selected_successor(
        tmp_path,
        source_decision=_binding(tmp_path, decision),
        task_source=_binding(tmp_path, source),
        at=AT,
        publish=False,
    )
    assert result["selected_task_id"] == "task-new"
    assert result["event_count"] == 2
    assert result["mutation_performed"] is False
    assert not (tmp_path / ".task/transition_plans" / f"{result['plan_id']}.json").exists()


def test_external_validator_allows_historical_task_drift_after_settlement(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Old\n", encoding="utf-8")
    task_index.upsert_item(
        tmp_path, "task", "task.md", "active", item_id="task-old"
    )
    source = tmp_path / ".task/candidates/task-new.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# New\n\n- Task ID: `task-new`\n", encoding="utf-8")
    decision = _selection_decision(
        tmp_path / ".task/cycle/cycle-A/decision.json", "task-new"
    )
    selected = prepare_selected_successor(
        tmp_path,
        source_decision=_binding(tmp_path, decision),
        task_source=_binding(tmp_path, source),
        at=AT,
    )
    plan = json.loads((tmp_path / selected["plan_binding"]["ref"]).read_text())
    transaction_id = "selection-test"
    prepare = {
        "schema_version": 3, "kind": "selection_publication_prepare",
        "transaction_id": transaction_id,
        "task_state_plan": selected["plan_binding"],
        "targets": [{
            "role": "task_alias", "target_ref": "task.md",
            "before_sha256": plan["artifact_anchors"][0]["before_sha256"],
            "after_sha256": _binding(tmp_path, source)["sha256"],
            "payload_sha256": _binding(tmp_path, source)["sha256"],
        }],
    }
    prepare_path = _write_json(
        tmp_path / f".task/selection_publication/transactions/{transaction_id}/prepare.json",
        prepare,
    )
    context, replay = transition_apply._preflight(
        tmp_path,
        selected["plan_binding"]["ref"],
        _binding(tmp_path, prepare_path),
        transition_apply._default_rebuild_markdown,
    )
    assert replay is None
    pending = transition_apply._result(
        context, transition_apply._apply_locked(context)
    )
    task.write_bytes(source.read_bytes())
    commit = {
        "schema_version": 3, "kind": "selection_publication_receipt",
        "status": "committed",
        "prepare_ref": _binding(tmp_path, prepare_path)["ref"],
        "prepare_sha256": _binding(tmp_path, prepare_path)["sha256"],
        "external_settlement_plan_id": plan["plan_id"],
        "owner_pending_receipt": pending["execution_result_binding"],
        "targets": [{
            "role": "task_alias", "target_ref": "task.md",
            "before_sha256": plan["artifact_anchors"][0]["before_sha256"],
            "after_sha256": _binding(tmp_path, source)["sha256"],
        }],
    }
    commit_path = _write_json(
        tmp_path / ".task/selection_publication/commit.json", commit
    )
    from manage_task_state_index.state import transition_external

    pending_value, pending_binding = transition_external.load_pending_receipt(
        tmp_path,
        plan,
        selected["plan_binding"]["ref"],
        selected["plan_binding"]["sha256"],
    )
    commit_binding = _binding(tmp_path, commit_path)
    settled_value = transition_external.settled_receipt_for_plan(
        plan,
        selected["plan_binding"]["ref"],
        selected["plan_binding"]["sha256"],
        pending_binding,
        pending_value["external_prepare"],
        commit_binding,
    )
    settled_path = _write_json(
        tmp_path / f".task/transition_receipts/{plan['plan_id']}.json",
        settled_value,
    )
    receipt = _binding(tmp_path, settled_path)
    assert validate_external_transition_receipt(tmp_path, receipt)["status"] == "valid"
    task.write_text("# Later successor\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no longer matches"):
        validate_external_transition_receipt(tmp_path, receipt, phase="current")
    historical = validate_external_transition_receipt(
        tmp_path, receipt, phase="historical"
    )
    assert historical["selection_consumption_allowed"] is True
