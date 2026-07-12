from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from task_state_migration_verifier_fixtures import (
    SCRIPT_DIR,
    assert_pass_result,
    build_fixture_plan,
    canonical,
    committed_fixture,
    file_tree,
    make_workspace,
    migration,
    mutate_graph_target,
    sha,
    task_index,
    verifier,
    verifier_evidence,
    verify,
    write_json,
)


def test_verifier_source_is_read_only_and_does_not_import_producer_truth() -> None:
    forbidden_imports = {"task_state_migration", "task_state_index"}
    forbidden_calls = {
        "apply_plan",
        "recover_transaction",
        "validate_migration",
        "load_sealed_events_if_present",
        "write_bytes",
        "write_text",
        "unlink",
        "rename",
        "truncate",
    }
    paths = sorted(SCRIPT_DIR.glob("task_state_migration_verifier*.py"))
    assert paths
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        called: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name):
                    called.add(function.id)
                elif isinstance(function, ast.Attribute):
                    called.add(function.attr)
        assert imported.isdisjoint(forbidden_imports), path
        assert called.isdisjoint(forbidden_calls), path


def test_complete_synthetic_graph_passes_repeatably_without_any_write(
    tmp_path: Path,
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    before = file_tree(fixture["root"])
    first = verify(fixture["root"], receipt, expected_mapping)
    second = verify(fixture["root"], receipt, expected_mapping)
    after = file_tree(fixture["root"])
    assert_pass_result(first)
    assert first == second
    assert after == before
    assert first["historical_boundary_identity_sha256"]
    assert first["post_migration_current_identity_sha256"]
    assert first["recovery_owned_write_set_sha256"]
    assert first["recovery_owned_write_path_count"] > 0


def test_producer_only_success_and_unsealed_malformed_prefix_cannot_pass(
    tmp_path: Path,
) -> None:
    fixture = make_workspace(tmp_path)
    transaction = fixture["root"] / ".task" / "migrations" / ("tsm-" + "a" * 24)
    transaction.mkdir(parents=True)
    receipt = transaction / "receipt.json"
    write_json(
        receipt,
        {
            "schema_version": 2,
            "kind": "task_state_index_migration",
            "transaction_id": "tsm-" + "a" * 24,
            "status": "committed",
            "strict_reader_status": "pass",
            "prefix_preserved": True,
        },
    )
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, fixture["mapping"])


@pytest.mark.parametrize(
    "mutation", ["byte", "remove", "reorder", "truncate"]
)
def test_immutable_prefix_mutation_removal_reorder_and_truncation_fail_closed(
    tmp_path: Path, mutation: str
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    payload = fixture["index"].read_bytes()
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    prefix_length = receipt_value["source_prefix_byte_length"]
    prefix = payload[:prefix_length]
    tail = payload[prefix_length:]
    lines = prefix.splitlines(keepends=True)
    if mutation == "byte":
        changed = bytearray(prefix)
        changed[0] = ord("[") if changed[0] != ord("[") else ord("{")
        prefix = bytes(changed)
    elif mutation == "remove":
        prefix = b"".join(lines[1:])
    elif mutation == "reorder":
        assert len(lines) >= 2
        prefix = b"".join([lines[1], lines[0], *lines[2:]])
    else:
        prefix = prefix[:-1]
    fixture["index"].write_bytes(prefix + tail)
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, expected_mapping)


@pytest.mark.parametrize(
    "target",
    [
        "receipt",
        "plan",
        "mapping",
        "resolution",
        "correction_suffix",
        "seal",
        "rendered_snapshot",
        "prepare_journal",
        "final_journal",
        "completion_marker",
        "anchor",
    ],
)
def test_every_transaction_graph_edge_tamper_fails_closed(
    tmp_path: Path, target: str
) -> None:
    fixture, plan, receipt, expected_mapping = committed_fixture(tmp_path)
    mutate_graph_target(fixture, plan, receipt, target)
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, expected_mapping)


def test_otherwise_valid_graph_with_missing_seal_fails_closed(
    tmp_path: Path,
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    start = receipt_value["seal_offset"]
    end = start + receipt_value["seal_byte_length"]
    payload = fixture["index"].read_bytes()
    assert sha(payload[start:end]) == receipt_value["seal_sha256"]
    fixture["index"].write_bytes(payload[:start] + payload[end:])

    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, expected_mapping)


def test_unknown_graph_field_and_boolean_integer_alias_fail_closed(
    tmp_path: Path,
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    transaction = receipt.parent
    plan_path = transaction / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["source_prefix"]["byte_length"] = True
    plan["unexpected_future_field"] = "coherently producer-declared"
    plan_path.write_bytes(canonical(plan))
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, expected_mapping)


@pytest.mark.parametrize("defect", ["bool_version", "unknown_status", "unknown_field"])
def test_post_seal_current_schema_alias_status_and_unknown_field_fail_closed(
    tmp_path: Path, defect: str
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    event = {
        "format_version": 2, "schema_version": 1, "event": "upsert",
        "id": "val-current-contract-defect", "type": "validation", "status": "complete",
        "path": ".task/validation/contract-defect.md", "title": "Contract defect",
        "updated_at": "2026-07-12T02:30:00+09:00",
    }
    if defect == "bool_version":
        event["schema_version"] = True
    elif defect == "unknown_status":
        event["status"] = "repository-private-status"
    else:
        event["unexpected_future_field"] = True
    fixture["index"].write_bytes(fixture["index"].read_bytes() + canonical(event))
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, expected_mapping)


def test_invalid_current_status_is_reclassified_with_exact_producer_reason_parity(
    tmp_path: Path,
) -> None:
    fixture = make_workspace(tmp_path, malformed=False)
    row = {
        "format_version": 2, "schema_version": 1, "event": "upsert",
        "id": "miss-private-status", "type": "task_miss", "status": "private-status",
        "path": ".task/task_miss/private.md", "title": "Private status",
        "updated_at": "2026-07-11T00:00:00+09:00",
    }
    fixture["prefix"] += canonical(row)
    fixture["index"].write_bytes(fixture["prefix"])
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    mapping["row_resolutions"] = [{
        "line": len(fixture["prefix"].splitlines()), "raw_line_sha256": sha(canonical(row)),
        "disposition": "quarantined_historical", "projection_impact": "independent",
        "reason_code": "historical_malformed", "deterministic_identity": row["id"],
        "resolution": "historical_only",
    }]
    write_json(fixture["mapping"], mapping)
    plan_path = tmp_path / "caller-plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    migration.apply_plan(fixture["root"], plan_path, sha(plan_path.read_bytes()), sha(fixture["prefix"]))
    result = verify(fixture["root"], fixture["root"] / plan["receipt_ref"], fixture["mapping"])
    assert_pass_result(result)


@pytest.mark.parametrize(
    ("defect", "axis"),
    [
        ("nonhex_sha", None), ("bool_line", None), ("identity_type", None),
        ("resolution_type", None), ("invalid_target", "event_mappings"),
        ("invalid_target", "status_mappings"), ("invalid_target", "type_mappings"),
    ],
)
def test_mapping_nested_types_hashes_and_axis_targets_are_exact(
    tmp_path: Path, defect: str, axis: str | None
) -> None:
    fixture = make_workspace(tmp_path)
    mapping = json.loads(fixture["mapping"].read_text(encoding="utf-8"))
    if defect == "nonhex_sha":
        mapping["row_resolutions"][0]["raw_line_sha256"] = "z" * 64
    elif defect == "bool_line":
        mapping["row_resolutions"][0]["line"] = True
    elif defect == "identity_type":
        mapping["row_resolutions"][0]["deterministic_identity"] = []
    elif defect == "resolution_type":
        mapping["row_resolutions"][0]["resolution"] = []
    elif axis == "event_mappings":
        mapping[axis]["upsert"]["to"] = "not-an-event"
    elif axis == "status_mappings":
        mapping[axis]["active"]["to"] = "not-a-status"
    else:
        assert axis == "type_mappings"
        mapping[axis]["task"]["to"] = "not-a-type"
    with pytest.raises(verifier.VerificationError):
        verifier_evidence._validate_mapping(mapping)


def test_anchor_must_immediately_follow_sealed_commit_boundary(tmp_path: Path) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    receipt_value = json.loads(receipt.read_text(encoding="utf-8"))
    offset = receipt_value["commit_boundary_length"]
    payload = fixture["index"].read_bytes()
    inserted = canonical({
        "format_version": 2, "schema_version": 1, "event": "upsert",
        "id": "val-before-anchor", "type": "validation", "status": "complete",
        "path": ".task/validation/before-anchor.md", "title": "Before anchor",
        "updated_at": "2026-07-12T02:40:00+09:00",
    })
    fixture["index"].write_bytes(payload[:offset] + inserted + payload[offset:])
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, expected_mapping)


@pytest.mark.parametrize("artifact", ["task", "pack"])
def test_current_task_or_pack_path_through_symlink_parent_fails_closed(
    tmp_path: Path, artifact: str
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = fixture["root"] / "linked"
    link.symlink_to(outside, target_is_directory=True)
    old_id = fixture["task_id"] if artifact == "task" else fixture["pack_id"]
    task_index.append_event(fixture["root"], migration._versioned({
        "event": "upsert", "id": old_id, "status": "superseded",
        "updated_at": "2026-07-12T02:50:00+09:00",
    }))
    path = "linked/current.md" if artifact == "task" else "linked/current-pack.json"
    (outside / Path(path).name).write_text("{}\n", encoding="utf-8")
    task_index.append_event(fixture["root"], migration._versioned({
        "event": "upsert", "id": f"{artifact}-symlink-current",
        "type": artifact if artifact == "task" else "task_pack", "status": "active",
        "path": path, "title": "Symlink current", "updated_at": "2026-07-12T02:50:01+09:00",
    }))
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, expected_mapping)


def test_legitimate_post_migration_identity_switch_is_not_receipt_corruption(
    tmp_path: Path,
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    before = verify(fixture["root"], receipt, expected_mapping)
    new_task_id = "task-successor-fixture"
    new_pack_id = "pack-successor-fixture"
    successor_pack = fixture["root"] / ".task/task_pack/pack-successor.json"
    write_json(
        successor_pack,
        {"schema_version": 1, "pack_id": new_pack_id, "status": "active", "items": []},
    )
    successor_task = fixture["root"] / "task.md"
    successor_task.write_text("# Successor fixture task\n", encoding="utf-8")
    events = [
        migration._versioned({
            "event": "upsert", "id": fixture["task_id"], "status": "superseded",
            "updated_at": "2026-07-12T01:00:00+09:00",
        }),
        migration._versioned({
            "event": "upsert", "id": fixture["pack_id"], "status": "superseded",
            "updated_at": "2026-07-12T01:00:01+09:00",
        }),
        migration._versioned({
            "event": "upsert", "id": new_pack_id, "type": "task_pack", "status": "active",
            "path": ".task/task_pack/pack-successor.json", "title": "Successor pack",
            "content_sha256": sha(successor_pack.read_bytes()),
            "updated_at": "2026-07-12T01:00:02+09:00",
        }),
        migration._versioned({
            "event": "upsert", "id": new_task_id, "type": "task", "status": "active",
            "path": "task.md", "title": "Successor task",
            "content_sha256": sha(successor_task.read_bytes()),
            "updated_at": "2026-07-12T01:00:03+09:00",
            "links": [{"rel": "pack_for_task", "id": new_pack_id}],
        }),
    ]
    for event in events:
        task_index.append_event(fixture["root"], event)
    after = verify(fixture["root"], receipt, expected_mapping)
    assert_pass_result(after)
    assert after["historical_boundary_identity_sha256"] == before[
        "historical_boundary_identity_sha256"
    ]
    assert after["post_migration_current_identity_sha256"] != before[
        "post_migration_current_identity_sha256"
    ]
    assert after["current_event_count"] > before["current_event_count"]


@pytest.mark.parametrize("sparse_kind", ["status", "fields"])
def test_legitimate_sparse_tail_for_known_id_passes(
    tmp_path: Path, sparse_kind: str
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    event: dict[str, Any] = {
        "format_version": 2,
        "schema_version": 1,
        "event": "upsert",
        "id": "task-stale",
        "updated_at": "2026-07-12T02:00:00+09:00",
    }
    if sparse_kind == "status":
        event["status"] = "archived"
    else:
        event["fields"] = {"body_free_note": "fixture"}
    task_index.append_event(fixture["root"], event)
    assert_pass_result(verify(fixture["root"], receipt, expected_mapping))


def test_sparse_tail_for_unknown_identity_fails_closed(tmp_path: Path) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    fixture["index"].write_bytes(
        fixture["index"].read_bytes()
        + canonical(
            {
                "format_version": 2,
                "schema_version": 1,
                "event": "upsert",
                "id": "unknown-sparse-id",
                "status": "archived",
                "updated_at": "2026-07-12T02:00:00+09:00",
            }
        )
    )
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, expected_mapping)
