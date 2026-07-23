from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "manage-task-state-index" / "scripts",
    ROOT / "orchestrate-task-cycle" / "scripts",
    ROOT / "record-agent-work-log" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from manage_task_state_index.state.compiler_contract_lint import (  # noqa: E402
    lint_owner_result,
)
from manage_task_state_index.state.scan_result_integrity import (  # noqa: E402
    SCAN_RESULT_FIELDS,
)
from manage_task_state_index.state.transition_plan_contract import (  # noqa: E402
    canonical_bytes,
)
from manage_task_state_index.state.scan_transition import (  # noqa: E402
    apply_scan,
    prepare_scan,
)
from manage_task_state_index.state.prevalidation_compiler import (  # noqa: E402
    audit_projection,
    compile_prevalidation,
    validate_prevalidation_binding,
)
from manage_task_state_index.state import audit_snapshot  # noqa: E402
from manage_task_state_index.state import prevalidation_compiler  # noqa: E402
from manage_task_state_index import index as task_index  # noqa: E402
from orchestrate_task_cycle.stage.native_results import (  # noqa: E402
    normalize_native_owner_result,
)
from orchestrate_task_cycle.cycle_ledger import init_cycle  # noqa: E402


AT = "2026-07-23T10:00:00+09:00"


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _init_cycle(root: Path, cycle_id: str, *, enforced: bool = True) -> None:
    if enforced:
        init_cycle(
            root,
            cycle_id,
            "task-1",
            "compiler contract test",
            stage_compiler_protocol_version=2,
            stage_preparation_schema_version=3,
            workflow_contract_profile="compiler_first_enforced_v1",
        )
        return
    path = root / ".task/cycle" / cycle_id / "initialization.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "cycle_id": cycle_id,
        "task_id": "task-1",
        "stage_compiler_protocol_version": 2,
    }
    if enforced:
        value["workflow_contract_profile"] = "compiler_first_enforced_v1"
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def test_linter_accepts_canonical_schema_v2_scan_owner_result(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    _init_cycle(tmp_path, "cycle-1")
    prepared = prepare_scan(tmp_path, at=AT)
    applied = apply_scan(tmp_path, prepared["compilation_binding"])

    result = lint_owner_result(
        tmp_path,
        owner_result=applied["owner_result_binding"],
        cycle_id="cycle-1",
    )

    assert result["lint_status"] == "pass"
    assert result["compatibility_class"] == "canonical_schema_v2"
    assert result["findings"] == []
    assert result["forbidden_payload_keys"] == []


def test_stage_adapter_rederives_canonical_scan_owner_result(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    _init_cycle(tmp_path, "cycle-1")
    prepared = prepare_scan(tmp_path, at=AT)
    applied = apply_scan(tmp_path, prepared["compilation_binding"])
    binding = applied["owner_result_binding"]
    value = json.loads((tmp_path / binding["ref"]).read_text(encoding="utf-8"))

    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    result = normalize_native_owner_result(
        "index",
        value,
        root=tmp_path,
        cycle_id="cycle-1",
        source_ref=binding["ref"],
    )

    assert result["index_status"] == "snapshot_current"
    assert result["audit_verdict"] == "pass"
    assert result["high_severity_id_blockers"] == []
    assert result["audit_observation_scope"] == (
        "immutable_bounded_input_snapshot"
    )
    assert result["live_revalidation_required"] is True
    assert result["evidence_paths"][0] == binding["ref"]
    assert result["post_audit_owner_result_binding"] is None
    manifest = result["audit_input_manifest"]
    assert not (tmp_path / manifest["ref"]).is_file()
    assert {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before

    applied_result = normalize_native_owner_result(
        "index",
        value,
        root=tmp_path,
        cycle_id="cycle-1",
        source_ref=binding["ref"],
        publish_auxiliary=True,
        include_auxiliary_binding=True,
    )
    post_audit = applied_result["post_audit_owner_result_binding"]
    assert (tmp_path / post_audit["ref"]).is_file()
    assert (tmp_path / applied_result["audit_input_manifest"]["ref"]).is_file()


def test_stage_adapter_projects_real_post_scan_audit_blockers(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n")
    _init_cycle(tmp_path, "cycle-1")
    prepared = prepare_scan(tmp_path, at=AT)
    applied = apply_scan(tmp_path, prepared["compilation_binding"])
    binding = applied["owner_result_binding"]
    value = json.loads((tmp_path / binding["ref"]).read_text(encoding="utf-8"))
    task.write_text("# Changed after scan\n")

    result = normalize_native_owner_result(
        "index",
        value,
        root=tmp_path,
        cycle_id="cycle-1",
        source_ref=binding["ref"],
    )

    assert result["index_status"] == "blocked"
    assert result["audit_verdict"] == "block"
    assert result["audit_blockers"]
    assert result["high_severity_id_blockers"]
    assert {
        blocker["code"] for blocker in result["high_severity_id_blockers"]
    } & {"current_canonical_id_missing", "current_surface_digest_mismatch"}


def test_stage_adapter_rejects_model_authored_index_result(
    tmp_path: Path,
) -> None:
    _init_cycle(tmp_path, "cycle-1")

    try:
        normalize_native_owner_result(
            "index",
            {"index_status": "current", "evidence_paths": ["task.md"]},
            root=tmp_path,
            cycle_id="cycle-1",
            source_ref="model-index.json",
        )
    except ValueError as exc:
        assert "registered artifact_kind" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("model-authored index owner result was accepted")


def test_prevalidation_compiler_publishes_rederivable_stage_owner_result(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    _init_cycle(tmp_path, "cycle-1")

    compiled = compile_prevalidation(tmp_path, at=AT)
    binding = compiled["owner_result_binding"]
    value = json.loads((tmp_path / binding["ref"]).read_text(encoding="utf-8"))
    result = normalize_native_owner_result(
        "index_pre_validate",
        value,
        root=tmp_path,
        cycle_id="cycle-1",
        source_ref=binding["ref"],
    )

    assert result["index_status"] in {"pass", "not_evaluated", "blocked"}
    assert result["index_snapshot_id"].startswith("task-index-snapshot-")
    assert isinstance(result["blockers"], list)
    assert result["audit_observation_scope"] == (
        "immutable_bounded_input_snapshot"
    )
    assert result["live_revalidation_required"] is True
    assert result["prevalidation_owner_result_binding"] == binding


def test_prevalidation_stage_maps_audit_pass_to_snapshot_current(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    _init_cycle(tmp_path, "cycle-1")
    prepared = prepare_scan(tmp_path, at=AT)
    apply_scan(tmp_path, prepared["compilation_binding"])
    compiled = compile_prevalidation(tmp_path, at=AT)
    binding = compiled["owner_result_binding"]
    value = json.loads((tmp_path / binding["ref"]).read_text(encoding="utf-8"))

    result = normalize_native_owner_result(
        "index_pre_validate",
        value,
        root=tmp_path,
        cycle_id="cycle-1",
        source_ref=binding["ref"],
    )

    assert value["result"]["index_status"] == "pass"
    assert result["index_status"] == "snapshot_current"
    assert result["audit_observation_scope"] == (
        "immutable_bounded_input_snapshot"
    )
    assert result["live_revalidation_required"] is True
    assert result["prevalidation_owner_result_binding"] == binding

    verified = validate_prevalidation_binding(tmp_path, binding)
    assert verified["owner_result_binding"] == binding
    assert verified["result"]["index_status"] == "pass"


def test_prevalidation_validator_rejects_noncanonical_source_cas_bytes(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    _init_cycle(tmp_path, "cycle-1")
    compiled = compile_prevalidation(tmp_path, at=AT)
    binding = compiled["owner_result_binding"]
    path = tmp_path / binding["ref"]
    value = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="binding differs from source"):
        normalize_native_owner_result(
            "index_pre_validate",
            value,
            root=tmp_path,
            cycle_id="cycle-1",
            source_ref=binding["ref"],
        )


def test_prevalidation_binds_full_audit_input_manifest(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    goal = tmp_path / ".agent_goal/goal_architecture.md"
    goal.parent.mkdir(parents=True)
    goal.write_text("# Goal\n")
    migration_sidecar = tmp_path / ".task/migrations/mig-1/receipt.json"
    migration_sidecar.parent.mkdir(parents=True)
    migration_sidecar.write_text('{"status":"fixture"}\n')
    _init_cycle(tmp_path, "cycle-1")

    compiled = compile_prevalidation(tmp_path, at=AT)
    binding = compiled["owner_result_binding"]
    value = json.loads((tmp_path / binding["ref"]).read_text(encoding="utf-8"))
    manifest_binding = value["index_snapshot"]["audit_input_manifest"]
    manifest = json.loads(
        (tmp_path / manifest_binding["ref"]).read_text(encoding="utf-8")
    )
    entries = {entry["ref"]: entry for entry in manifest["entries"]}

    assert entries["task.md"]["kind"] == "regular"
    assert entries[".agent_goal/goal_architecture.md"]["kind"] == "regular"
    assert entries[".task/migrations/mig-1/receipt.json"]["kind"] == "regular"
    assert manifest["root_sha256"] == value["index_snapshot"][
        "audit_input_root_sha256"
    ]

    goal.write_text("# Mutated goal\n")
    try:
        normalize_native_owner_result(
            "index_pre_validate",
            value,
            root=tmp_path,
            cycle_id="cycle-1",
            source_ref=binding["ref"],
        )
    except ValueError as exc:
        assert "differs from current" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("stale audit input manifest was accepted")


def test_audit_snapshot_rejects_indexed_parent_symlink_escape(
    tmp_path: Path,
) -> None:
    external = tmp_path.parent / f"{tmp_path.name}-external"
    external.mkdir()
    secret = external / "secret.md"
    secret.write_text("# Outside\n")
    (tmp_path / "escape").symlink_to(external, target_is_directory=True)
    task_index.append_event(
        tmp_path,
        {
            "event": "upsert",
            "id": "val-escape",
            "type": "validation",
            "status": "passed",
            "path": "escape/secret.md",
            "title": "Outside",
            "content_sha256": hashlib.sha256(secret.read_bytes()).hexdigest(),
            "updated_at": AT,
        },
    )

    with pytest.raises(ValueError, match="unsafe ancestor"):
        audit_projection(tmp_path, at=AT)


def test_audit_consumes_captured_bytes_during_live_aba(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n")
    prepared = prepare_scan(tmp_path, at=AT)
    apply_scan(tmp_path, prepared["compilation_binding"])
    invalid = b"# Invalid after scan\n"
    task.write_bytes(invalid)
    original_audit = audit_snapshot._audit_captured

    def attack(
        payloads: dict[str, bytes], *, audited_at: str
    ) -> dict[str, object]:
        task.write_text("# Task\n")
        try:
            return original_audit(payloads, audited_at=audited_at)
        finally:
            task.write_bytes(invalid)

    monkeypatch.setattr(audit_snapshot, "_audit_captured", attack)
    projected = audit_projection(tmp_path, at=AT)

    assert task.read_bytes() == invalid
    assert projected["result"]["index_status"] == "blocked"
    assert projected["result"]["blockers"]


def test_audit_rejects_oversized_index_before_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = tmp_path / ".task/index.jsonl"
    index.parent.mkdir(parents=True)
    index.write_bytes(
        b" " * (audit_snapshot.MAX_AUDIT_INPUT_FILE_BYTES + 1)
    )

    def parsed_too_early(_root: Path) -> tuple[list[object], list[object]]:
        raise AssertionError("oversized index was parsed before its byte cap")

    monkeypatch.setattr(
        audit_snapshot, "load_events_for_audit", parsed_too_early
    )
    with pytest.raises(ValueError, match="byte budget"):
        audit_projection(tmp_path, at=AT)


def test_audit_discovery_budget_is_shared_across_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(audit_snapshot, "MAX_AUDIT_DISCOVERY_ENTRIES", 16)
    for root_ref in (".agent_goal", ".agent_log"):
        directory = tmp_path / root_ref
        directory.mkdir()
        for index in range(9):
            (directory / f"empty-{index}").mkdir()

    with pytest.raises(ValueError, match="global discovery entry budget"):
        audit_projection(tmp_path, at=AT)


def test_prevalidation_rechecks_snapshot_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n")
    original_manifest = prevalidation_compiler.audit_input_manifest
    mutated = False

    def mutate_before_publish(root: Path) -> dict[str, object]:
        nonlocal mutated
        if not mutated:
            task.write_text("# Changed before publish\n")
            mutated = True
        return original_manifest(root)

    monkeypatch.setattr(
        prevalidation_compiler,
        "audit_input_manifest",
        mutate_before_publish,
    )
    with pytest.raises(ValueError, match="changed before result publication"):
        compile_prevalidation(tmp_path, at=AT)
    assert not (tmp_path / ".task/index_prevalidation").exists()


def test_prevalidation_manifest_reader_rejects_parent_symlink_swap(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    compiled = compile_prevalidation(tmp_path, at=AT)
    binding = compiled["owner_result_binding"]
    value = json.loads((tmp_path / binding["ref"]).read_text(encoding="utf-8"))
    owned = tmp_path / ".task/index_prevalidation"
    displaced = tmp_path / ".task/index_prevalidation-original"
    owned.rename(displaced)
    external = tmp_path.parent / f"{tmp_path.name}-manifest-external"
    external.mkdir()
    owned.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="unsafe ancestor"):
        normalize_native_owner_result(
            "index_pre_validate",
            value,
            root=tmp_path,
            cycle_id="cycle-1",
            source_ref=binding["ref"],
        )


def test_prevalidation_manifest_reader_rejects_parent_replacement_during_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    compiled = compile_prevalidation(tmp_path, at=AT)
    binding = compiled["owner_result_binding"]
    value = json.loads((tmp_path / binding["ref"]).read_text(encoding="utf-8"))
    manifest_ref = value["index_snapshot"]["audit_input_manifest"]["ref"]
    manifest_payload = (tmp_path / manifest_ref).read_bytes()
    owned = tmp_path / ".task/index_prevalidation"
    displaced = tmp_path / ".task/index_prevalidation-original"
    original_open_parent = audit_snapshot._open_parent
    swapped = False

    def replace_after_open(root: Path, ref: str) -> tuple[int, str]:
        nonlocal swapped
        parent, leaf = original_open_parent(root, ref)
        if ref == manifest_ref and not swapped:
            owned.rename(displaced)
            owned.mkdir()
            (owned / Path(manifest_ref).name).write_bytes(manifest_payload)
            swapped = True
        return parent, leaf

    monkeypatch.setattr(audit_snapshot, "_open_parent", replace_after_open)
    with pytest.raises(ValueError, match="parent changed during capture"):
        normalize_native_owner_result(
            "index_pre_validate",
            value,
            root=tmp_path,
            cycle_id="cycle-1",
            source_ref=binding["ref"],
        )


def test_snapshot_detects_same_size_rewrite_with_restored_mtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = tmp_path / "task.md"
    task.write_bytes(b"alpha\n")
    initial = task.stat()
    original_read = audit_snapshot.os.read
    changed = False

    def rewrite_on_eof(descriptor: int, size: int) -> bytes:
        nonlocal changed
        payload = original_read(descriptor, size)
        if payload == b"" and not changed:
            task.write_bytes(b"bravo\n")
            os.utime(
                task,
                ns=(initial.st_atime_ns, initial.st_mtime_ns),
            )
            changed = True
        return payload

    monkeypatch.setattr(audit_snapshot.os, "read", rewrite_on_eof)
    with pytest.raises(ValueError, match="changed during capture"):
        audit_snapshot.read_bounded_regular(
            tmp_path, "task.md", max_bytes=1024
        )


def test_prevalidation_adapter_rejects_model_authored_result(
    tmp_path: Path,
) -> None:
    _init_cycle(tmp_path, "cycle-1")

    try:
        normalize_native_owner_result(
            "index_pre_validate",
            {
                "index_status": "pass",
                "index_snapshot_id": "invented",
                "blockers": [],
                "evidence_paths": [],
            },
            root=tmp_path,
            cycle_id="cycle-1",
            source_ref="model-prevalidation.json",
        )
    except ValueError as exc:
        assert "registered artifact_kind" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("model-authored prevalidation result was accepted")


def test_linter_marks_schema_v1_owner_result_historical_only(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".task/history/legacy-owner.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {"schema_version": 1, "status": "recorded"},
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )

    result = lint_owner_result(tmp_path, owner_result=_binding(tmp_path, path))

    assert result["lint_status"] == "warn"
    assert result["compatibility_class"] == "historical_schema_v1"
    assert result["findings"] == ["schema_v1_owner_result_historical_only"]


def test_linter_blocks_schema_v1_for_enforced_cycle(tmp_path: Path) -> None:
    _init_cycle(tmp_path, "cycle-1")
    path = tmp_path / ".task/history/legacy-owner.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"schema_version":1,"status":"recorded"}\n')

    result = lint_owner_result(
        tmp_path,
        owner_result=_binding(tmp_path, path),
        cycle_id="cycle-1",
    )

    assert result["lint_status"] == "block"
    assert "schema_v1_forbidden_in_compiler_first_cycle" in result["findings"]


def test_linter_blocks_embedded_packet_payloads(tmp_path: Path) -> None:
    path = tmp_path / ".task/history/legacy-owner.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "recorded",
                "packet": {"events": [{"id": "model-authored"}]},
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )

    result = lint_owner_result(tmp_path, owner_result=_binding(tmp_path, path))

    assert result["lint_status"] == "block"
    assert result["compatibility_class"] == "historical_schema_v1"
    assert result["forbidden_payload_keys"] == ["events", "packet"]
    assert "embedded_payload_keys_forbidden" in result["findings"]


def test_linter_rejects_exact_digest_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "owner.json"
    path.write_text("{}\n")

    try:
        lint_owner_result(
            tmp_path,
            owner_result={
                "ref": "owner.json",
                "sha256": "a" * 64,
            },
        )
    except ValueError as exc:
        assert "sha256" in str(exc)
    else:  # pragma: no cover - assertion shape is clearer than pytest dependency
        raise AssertionError("digest mismatch was accepted")


def test_linter_rejects_self_hashed_schema_v2_without_compiler_evidence(
    tmp_path: Path,
) -> None:
    _init_cycle(tmp_path, "cycle-1")
    value = {field: None for field in SCAN_RESULT_FIELDS}
    value.update(
        {
            "schema_version": 2,
            "artifact_kind": "task_state_index_scan_result",
            "operation": "scan",
        }
    )
    body = {key: item for key, item in value.items() if key != "result_sha256"}
    value["result_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    path = tmp_path / ".task/scan_receipts/nested/forged.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(canonical_bytes(value) + b"\n")

    result = lint_owner_result(
        tmp_path,
        owner_result=_binding(tmp_path, path),
        cycle_id="cycle-1",
    )

    assert result["lint_status"] == "block"
    assert "schema_v2_evidence_rederivation_failed" in result["findings"]
