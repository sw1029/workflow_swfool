from __future__ import annotations

from pathlib import Path

import pytest

from orchestrate_task_cycle.cycle_ledger import append_event, init_cycle, read_events_raw
from orchestrate_task_cycle.cycle_efficiency.compiler_metrics import (
    compiler_efficiency_projection,
)
from orchestrate_task_cycle.stage import publication as stage_publication
from orchestrate_task_cycle.stage import artifact_store as stage_artifact_store
from orchestrate_task_cycle.stage import preparation_store as stage_preparation_store
from orchestrate_task_cycle.stage import publication_origin as stage_publication_origin
from orchestrate_task_cycle.stage.artifact_store import compiler_artifact_binding
from orchestrate_task_cycle.stage.contracts import canonical_bytes, canonical_sha256
from orchestrate_task_cycle.stage.deterministic_dispatch import dispatch_deterministic
from orchestrate_task_cycle.stage.preparation_store import (
    load_published_preparation,
    publish_preparation,
)
from orchestrate_task_cycle.stage.publication import publish_result
from orchestrate_task_cycle.stage.service import (
    advance_stage,
    prepare_stage,
    submit_stage,
)


def _origin_intent_paths(root: Path, cycle_id: str) -> list[Path]:
    directory = (
        root
        / ".task"
        / "cycle"
        / cycle_id
        / "compiler"
        / "publication-origin"
    )
    return sorted(directory.rglob("*.intent.json")) if directory.is_dir() else []


def _origin_totals(
    root: Path,
    cycle_id: str,
    preparation: dict,
    publication: dict,
    binding_fields: tuple[str, ...],
) -> tuple[int, int]:
    target_bytes = sum(
        int(preparation[field]["size_bytes"]) for field in binding_fields
    )
    intent_paths = _origin_intent_paths(root, cycle_id)
    total_bytes = (
        target_bytes
        + int(publication["preparation_bytes"])
        + int(publication["preparation_publication_receipt_binding"]["size_bytes"])
        + sum(path.stat().st_size for path in intent_paths)
    )
    total_files = len(binding_fields) + 2 + len(intent_paths)
    return total_bytes, total_files


def test_compiler_cas_receipt_reports_actual_new_and_reused_bytes(
    tmp_path: Path,
) -> None:
    value = {"schema_version": 1, "artifact_kind": "machine", "value": 7}
    size = len(canonical_bytes(value)) + 1

    dry = compiler_artifact_binding(
        tmp_path, "cycle-cas-metrics", "machine_input", value
    )
    first = compiler_artifact_binding(
        tmp_path,
        "cycle-cas-metrics",
        "machine_input",
        value,
        persist=True,
    )
    replay = compiler_artifact_binding(
        tmp_path,
        "cycle-cas-metrics",
        "machine_input",
        value,
        persist=True,
    )

    assert dry["write_receipt"] == {
        "write_attempted": False,
        "mutation_performed": False,
        "cas_newly_written_bytes": 0,
        "cas_reused_bytes": 0,
        "files_written_count": 0,
    }
    assert first["write_receipt"]["mutation_performed"] is True
    assert first["write_receipt"]["cas_newly_written_bytes"] == size
    assert first["write_receipt"]["cas_reused_bytes"] == 0
    assert first["write_receipt"]["files_written_count"] == 1
    assert replay["write_receipt"]["mutation_performed"] is False
    assert replay["write_receipt"]["cas_newly_written_bytes"] == 0
    assert replay["write_receipt"]["cas_reused_bytes"] == size
    assert replay["write_receipt"]["files_written_count"] == 0


def test_result_cas_metrics_add_to_prior_io_and_crash_retry_is_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nI/O metrics.\n", encoding="utf-8")
    cycle_id = "cycle-result-io"
    init_cycle(tmp_path, cycle_id, "task-result-io", "result I/O metrics")
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "context",
            "status": "completed",
            "event_id": "context-io",
            "task_id": "task-result-io",
        },
    )
    preparation = {
        "schema_version": 2,
        "artifact_kind": "orchestrate_stage_preparation",
        "cycle_id": cycle_id,
        "target": "repo_skill_adapter_scan",
        "workflow_mode": "normal",
        "preparation_id": "stageprep-result-io",
    }
    result = {"step": "repo_skill_adapter_scan", "adapter_scan_status": "pass"}
    result_size = len(canonical_bytes(result)) + 1
    prior = {
        "cas_newly_written_bytes": 101,
        "cas_reused_bytes": 17,
        "files_written_count": 2,
    }

    def fail_before_append(*_args, **_kwargs):
        raise RuntimeError("injected post-CAS crash")

    monkeypatch.setattr(stage_publication, "append_event", fail_before_append)
    with pytest.raises(RuntimeError, match="post-CAS crash"):
        publish_result(
            tmp_path,
            cycle_id,
            preparation,
            result,
            canonical_sha256(result),
            prior,
        )
    assert not [
        event
        for event in read_events_raw(tmp_path, cycle_id)
        if event.get("step") == "repo_skill_adapter_scan"
    ]

    monkeypatch.setattr(stage_publication, "append_event", append_event)
    replay = publish_result(
        tmp_path,
        cycle_id,
        preparation,
        result,
        canonical_sha256(result),
        prior,
    )
    metrics = replay["compiler_metrics"]

    assert replay["result_write_receipt"]["mutation_performed"] is False
    assert metrics["cas_newly_written_bytes"] == 101
    assert metrics["cas_reused_bytes"] == 17 + result_size
    assert metrics["files_written_count"] == 2


@pytest.mark.parametrize(
    ("target", "binding_fields"),
    (
        ("authority", ("context_binding", "work_order_binding")),
        ("repo_skill_adapter_scan", ("machine_input_binding",)),
    ),
)
def test_preparation_publication_accumulates_actual_cas_io_and_replays_stably(
    tmp_path: Path, target: str, binding_fields: tuple[str, ...]
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nPreparation I/O.\n", encoding="utf-8")
    cycle_id = f"cycle-preparation-io-{target}"
    init_cycle(tmp_path, cycle_id, "task-preparation-io", "preparation I/O")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    if target != "authority":
        append_event(
            tmp_path,
            cycle_id,
            {
                "step": "authority",
                "status": "completed",
                "event_id": f"authority-{target}",
                "task_id": "task-preparation-io",
            },
        )

    first = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    binding_bytes = sum(first[field]["size_bytes"] for field in binding_fields)
    artifact_intent_bytes = sum(
        path.stat().st_size for path in _origin_intent_paths(tmp_path, cycle_id)
    )
    assert first["compiler_metrics"]["cas_newly_written_bytes"] == (
        binding_bytes + artifact_intent_bytes
    )
    assert first["compiler_metrics"]["cas_reused_bytes"] == 0
    assert first["compiler_metrics"]["files_written_count"] == 2 * len(
        binding_fields
    )

    first_publication = publish_preparation(tmp_path, first)
    receipt_bytes = first_publication[
        "preparation_publication_receipt_binding"
    ]["size_bytes"]
    assert first_publication["preparation_write_receipt"]["mutation_performed"] is True
    origin_bytes, origin_files = _origin_totals(
        tmp_path, cycle_id, first, first_publication, binding_fields
    )
    assert first_publication["compiler_metrics"]["cas_newly_written_bytes"] == (
        origin_bytes
    )
    assert first_publication["compiler_metrics"]["files_written_count"] == origin_files
    assert first_publication["preparation_publication_receipt_binding"]["ref"]

    replay = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    assert replay["preparation_id"] == first["preparation_id"]
    assert replay["compiler_metrics"]["cas_newly_written_bytes"] == 0
    assert replay["compiler_metrics"]["cas_reused_bytes"] == (
        binding_bytes + artifact_intent_bytes
    )
    assert replay["compiler_metrics"]["files_written_count"] == 0

    replay_publication = publish_preparation(tmp_path, replay)
    assert replay_publication["preparation_sha256"] == first_publication[
        "preparation_sha256"
    ]
    assert replay_publication["artifact_duplicate"] is True
    assert replay_publication["compiler_metrics"]["cas_newly_written_bytes"] == 0
    assert replay_publication["compiler_metrics"]["cas_reused_bytes"] == (
        origin_bytes
    )
    assert replay_publication["compiler_metrics"]["files_written_count"] == 0

    loaded = load_published_preparation(
        tmp_path,
        replay_publication["preparation_ref"],
        replay_publication["preparation_sha256"],
    )
    assert loaded["compiler_metrics"]["cas_newly_written_bytes"] == (
        origin_bytes
    )
    assert loaded["compiler_metrics"]["cas_reused_bytes"] == (
        binding_bytes + replay_publication["preparation_bytes"] + receipt_bytes
    )
    assert loaded["compiler_metrics"]["files_written_count"] == origin_files


@pytest.mark.parametrize(
    ("target", "crash_after", "binding_fields"),
    (
        ("authority", 1, ("context_binding", "work_order_binding")),
        ("authority", 2, ("context_binding", "work_order_binding")),
        ("repo_skill_adapter_scan", 1, ("machine_input_binding",)),
    ),
)
def test_origin_metrics_recover_after_each_compiler_artifact_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    crash_after: int,
    binding_fields: tuple[str, ...],
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nArtifact crash.\n", encoding="utf-8")
    cycle_id = f"cycle-artifact-origin-crash-{crash_after}"
    init_cycle(tmp_path, cycle_id, "task-artifact-crash", "artifact crash")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    if target != "authority":
        append_event(
            tmp_path,
            cycle_id,
            {
                "step": "authority",
                "status": "completed",
                "event_id": "authority-artifact-crash",
                "task_id": "task-artifact-crash",
            },
        )
    original_publish = stage_artifact_store.publish_origin_object
    call_count = 0

    def crash_after_object(*args, **kwargs):
        nonlocal call_count
        result = original_publish(*args, **kwargs)
        call_count += 1
        if call_count == crash_after:
            raise RuntimeError("injected post-artifact crash")
        return result

    monkeypatch.setattr(
        stage_artifact_store, "publish_origin_object", crash_after_object
    )
    with pytest.raises(RuntimeError, match="post-artifact crash"):
        prepare_stage(
            tmp_path,
            cycle_id,
            target,
            persist_compiler_artifacts=True,
        )
    monkeypatch.setattr(
        stage_artifact_store, "publish_origin_object", original_publish
    )

    replay = prepare_stage(
        tmp_path,
        cycle_id,
        target,
        persist_compiler_artifacts=True,
    )
    publication = publish_preparation(tmp_path, replay)
    loaded = load_published_preparation(
        tmp_path,
        publication["preparation_ref"],
        publication["preparation_sha256"],
    )
    expected_bytes, expected_files = _origin_totals(
        tmp_path,
        cycle_id,
        replay,
        publication,
        binding_fields,
    )

    assert loaded["preparation_id"] == replay["preparation_id"]
    assert loaded["compiler_metrics"]["cas_newly_written_bytes"] == expected_bytes
    assert loaded["compiler_metrics"]["files_written_count"] == expected_files


def test_origin_metrics_recover_after_preparation_write_before_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nPreparation crash.\n", encoding="utf-8")
    cycle_id = "cycle-preparation-origin-crash"
    init_cycle(tmp_path, cycle_id, "task-preparation-crash", "preparation crash")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    prepared = prepare_stage(
        tmp_path, cycle_id, "authority", persist_compiler_artifacts=True
    )
    original_ensure = stage_preparation_store.ensure_receipt

    def fail_before_receipt(*_args, **_kwargs):
        raise RuntimeError("injected pre-receipt crash")

    monkeypatch.setattr(stage_preparation_store, "ensure_receipt", fail_before_receipt)
    with pytest.raises(RuntimeError, match="pre-receipt crash"):
        publish_preparation(tmp_path, prepared)
    monkeypatch.setattr(stage_preparation_store, "ensure_receipt", original_ensure)

    replay = prepare_stage(
        tmp_path, cycle_id, "authority", persist_compiler_artifacts=True
    )
    assert replay["preparation_id"] == prepared["preparation_id"]
    publication = publish_preparation(tmp_path, replay)
    loaded = load_published_preparation(
        tmp_path,
        publication["preparation_ref"],
        publication["preparation_sha256"],
    )
    expected_bytes, expected_files = _origin_totals(
        tmp_path,
        cycle_id,
        replay,
        publication,
        ("context_binding", "work_order_binding"),
    )

    assert loaded["compiler_metrics"]["cas_newly_written_bytes"] == expected_bytes
    assert loaded["compiler_metrics"]["files_written_count"] == expected_files


def test_origin_intent_recovers_crash_before_object_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nIntent recovery.\n", encoding="utf-8")
    cycle_id = "cycle-origin-intent-recovery"
    init_cycle(tmp_path, cycle_id, "task-intent-recovery", "intent recovery")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-intent-recovery",
            "task_id": "task-intent-recovery",
        },
    )
    original_write = stage_publication_origin.immutable_write_bytes
    write_count = 0

    def crash_before_target(path: Path, payload: bytes) -> bool:
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            raise RuntimeError("injected post-intent crash")
        return original_write(path, payload)

    monkeypatch.setattr(
        stage_publication_origin, "immutable_write_bytes", crash_before_target
    )
    with pytest.raises(RuntimeError, match="post-intent crash"):
        prepare_stage(
            tmp_path,
            cycle_id,
            "repo_skill_adapter_scan",
            persist_compiler_artifacts=True,
        )
    monkeypatch.setattr(
        stage_publication_origin, "immutable_write_bytes", original_write
    )

    replay = prepare_stage(
        tmp_path,
        cycle_id,
        "repo_skill_adapter_scan",
        persist_compiler_artifacts=True,
    )
    publication = publish_preparation(tmp_path, replay)
    loaded = load_published_preparation(
        tmp_path,
        publication["preparation_ref"],
        publication["preparation_sha256"],
    )
    expected_bytes, expected_files = _origin_totals(
        tmp_path,
        cycle_id,
        replay,
        publication,
        ("machine_input_binding",),
    )

    assert loaded["compiler_metrics"]["cas_newly_written_bytes"] == expected_bytes
    assert loaded["compiler_metrics"]["files_written_count"] == expected_files


def test_published_preparation_origin_io_survives_separate_submit_process(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nCycle-wide I/O.\n", encoding="utf-8")
    cycle_id = "cycle-cross-process-io"
    init_cycle(tmp_path, cycle_id, "task-cross-process", "cross-process I/O")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    append_event(
        tmp_path,
        cycle_id,
        {
            "step": "authority",
            "status": "completed",
            "event_id": "authority-cross-process-io",
            "task_id": "task-cross-process",
        },
    )
    prepared = prepare_stage(
        tmp_path,
        cycle_id,
        "repo_skill_adapter_scan",
        persist_compiler_artifacts=True,
    )
    publication = publish_preparation(tmp_path, prepared)
    loaded = load_published_preparation(
        tmp_path,
        publication["preparation_ref"],
        publication["preparation_sha256"],
    )
    owner = dispatch_deterministic(tmp_path, loaded)["owner_result_binding"]

    output = submit_stage(
        tmp_path,
        loaded,
        owner_result_ref=owner["ref"],
        owner_result_sha256=owner["sha256"],
        apply=True,
    )
    event = next(
        item
        for item in read_events_raw(tmp_path, cycle_id)
        if item.get("step") == "repo_skill_adapter_scan"
    )
    metrics = event["compiler_metrics"]
    origin = publication["compiler_metrics"]
    consumed_bytes = (
        prepared["machine_input_binding"]["size_bytes"]
        + publication["preparation_bytes"]
        + publication["preparation_publication_receipt_binding"]["size_bytes"]
    )

    assert output["applied"] is True
    assert metrics["cas_newly_written_bytes"] == (
        origin["cas_newly_written_bytes"] + metrics["result_bytes"]
    )
    assert metrics["cas_reused_bytes"] == consumed_bytes
    assert metrics["files_written_count"] == origin["files_written_count"] + 1
    totals = compiler_efficiency_projection(tmp_path, [event])["structural_totals"]
    assert totals["cas_newly_written_bytes"] == metrics["cas_newly_written_bytes"]
    assert totals["cas_reused_bytes"] == metrics["cas_reused_bytes"]
    assert totals["files_written_count"] == metrics["files_written_count"]


def test_published_preparation_origin_receipt_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nReceipt tamper.\n", encoding="utf-8")
    cycle_id = "cycle-preparation-receipt-tamper"
    init_cycle(tmp_path, cycle_id, "task-receipt", "receipt tamper")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    prepared = prepare_stage(
        tmp_path, cycle_id, "authority", persist_compiler_artifacts=True
    )
    publication = publish_preparation(tmp_path, prepared)
    receipt = tmp_path / publication["preparation_publication_receipt_binding"]["ref"]
    receipt.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="receipt scope is invalid"):
        load_published_preparation(
            tmp_path,
            publication["preparation_ref"],
            publication["preparation_sha256"],
        )


def test_published_preparation_origin_intent_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nIntent tamper.\n", encoding="utf-8")
    cycle_id = "cycle-preparation-intent-tamper"
    init_cycle(tmp_path, cycle_id, "task-intent", "intent tamper")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    prepared = prepare_stage(
        tmp_path, cycle_id, "authority", persist_compiler_artifacts=True
    )
    publication = publish_preparation(tmp_path, prepared)
    intent = _origin_intent_paths(tmp_path, cycle_id)[0]
    intent.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="origin intent"):
        load_published_preparation(
            tmp_path,
            publication["preparation_ref"],
            publication["preparation_sha256"],
        )


def test_published_preparation_origin_receipt_symlink_fails_closed(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nReceipt symlink.\n", encoding="utf-8")
    cycle_id = "cycle-preparation-receipt-symlink"
    init_cycle(tmp_path, cycle_id, "task-receipt-link", "receipt symlink")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    prepared = prepare_stage(
        tmp_path, cycle_id, "authority", persist_compiler_artifacts=True
    )
    publication = publish_preparation(tmp_path, prepared)
    receipt = tmp_path / publication["preparation_publication_receipt_binding"]["ref"]
    relocated = receipt.with_suffix(".relocated")
    receipt.rename(relocated)
    receipt.symlink_to(relocated.name)

    with pytest.raises(ValueError, match="receipt is missing or oversized"):
        load_published_preparation(
            tmp_path,
            publication["preparation_ref"],
            publication["preparation_sha256"],
        )


def test_schema_v1_preparation_origin_receipt_remains_readable(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nLegacy receipt.\n", encoding="utf-8")
    cycle_id = "cycle-preparation-receipt-v1"
    init_cycle(tmp_path, cycle_id, "task-receipt-v1", "legacy receipt")
    advance_stage(tmp_path, cycle_id, apply=True, max_steps=1)
    prepared = prepare_stage(
        tmp_path, cycle_id, "authority", persist_compiler_artifacts=True
    )
    publication = publish_preparation(tmp_path, prepared)
    bound = {
        field: prepared[field]
        for field in ("context_binding", "work_order_binding")
    }
    scope = {
        "schema_version": 1,
        "artifact_kind": "orchestrate_stage_preparation_publication_receipt",
        "cycle_id": cycle_id,
        "target": "authority",
        "preparation_id": prepared["preparation_id"],
        "preparation_binding": {
            "ref": publication["preparation_ref"],
            "sha256": publication["preparation_sha256"],
            "body_sha256": publication["preparation_body_sha256"],
            "size_bytes": publication["preparation_bytes"],
        },
        "bound_compiler_artifacts": bound,
    }
    base_bytes = int(publication["preparation_bytes"]) + sum(
        int(binding["size_bytes"]) for binding in bound.values()
    )
    metrics = {
        "cas_newly_written_bytes": base_bytes,
        "cas_reused_bytes": 0,
        "files_written_count": len(bound) + 1,
    }
    for _attempt in range(8):
        payload = canonical_bytes({**scope, "compiler_io_metrics": metrics}) + b"\n"
        updated = {
            "cas_newly_written_bytes": base_bytes + len(payload),
            "cas_reused_bytes": 0,
            "files_written_count": len(bound) + 2,
        }
        if updated == metrics:
            break
        metrics = updated
    else:
        raise AssertionError("legacy receipt size did not converge")
    payload = canonical_bytes({**scope, "compiler_io_metrics": metrics}) + b"\n"
    receipt = tmp_path / publication["preparation_publication_receipt_binding"]["ref"]
    receipt.write_bytes(payload)

    loaded = load_published_preparation(
        tmp_path,
        publication["preparation_ref"],
        publication["preparation_sha256"],
    )

    assert loaded["preparation_id"] == prepared["preparation_id"]
    assert loaded["compiler_metrics"]["cas_newly_written_bytes"] == metrics[
        "cas_newly_written_bytes"
    ]
    assert loaded["compiler_metrics"]["files_written_count"] == metrics[
        "files_written_count"
    ]
