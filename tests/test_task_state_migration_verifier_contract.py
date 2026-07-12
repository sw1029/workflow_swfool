from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil

import pytest

from task_state_migration_verifier_fixtures import (
    assert_pass_result,
    canonical,
    commit_vocabulary_workspace,
    committed_fixture,
    file_tree,
    make_vocabulary_workspace,
    run_verifier_cli,
    verifier,
    verify,
    write_json,
)


@pytest.mark.parametrize(
    ("token", "task_id", "pack_id", "task_path", "pack_path"),
    [
        (
            "alpha",
            "work-alpha-17",
            "queue-alpha-23",
            "flows/alpha/current-work.md",
            ".task/task_pack/alpha/queue.json",
        ),
        (
            "beta",
            "ticket-beta-x",
            "bundle-beta-y",
            "nested/beta/active.md",
            ".task/task_pack/nested/beta.json",
        ),
    ],
)
def test_generalizes_across_legacy_vocabularies_ids_and_path_layouts(
    tmp_path: Path,
    token: str,
    task_id: str,
    pack_id: str,
    task_path: str,
    pack_path: str,
) -> None:
    fixture = make_vocabulary_workspace(
        tmp_path,
        token=token,
        task_id=task_id,
        pack_id=pack_id,
        task_path=task_path,
        pack_path=pack_path,
    )
    _plan, receipt = commit_vocabulary_workspace(fixture, tmp_path)
    assert_pass_result(verify(fixture["root"], receipt, fixture["mapping"]))


@pytest.mark.parametrize(
    "expectation_kind",
    ["missing", "published_sidecar", "hardlink", "symlink", "different_bytes"],
)
def test_caller_mapping_expectation_must_be_external_distinct_and_exact(
    tmp_path: Path, expectation_kind: str
) -> None:
    fixture, plan, receipt, expected_mapping = committed_fixture(tmp_path)
    published = fixture["root"] / plan["mapping_manifest"]["snapshot_ref"]
    supplied: Path | None
    if expectation_kind == "missing":
        supplied = None
    elif expectation_kind == "published_sidecar":
        supplied = published
    elif expectation_kind == "hardlink":
        supplied = tmp_path / "hardlinked-mapping.json"
        os.link(published, supplied)
    elif expectation_kind == "symlink":
        supplied = tmp_path / "symlinked-mapping.json"
        supplied.symlink_to(expected_mapping)
    else:
        supplied = tmp_path / "different-mapping.json"
        supplied.write_bytes(expected_mapping.read_bytes() + b" ")
    with pytest.raises(verifier.VerificationError):
        verify(fixture["root"], receipt, supplied)


def test_regular_copy_of_producer_snapshot_proves_only_physical_separation(
    tmp_path: Path,
) -> None:
    fixture, plan, receipt, _expected_mapping = committed_fixture(tmp_path)
    published = fixture["root"] / plan["mapping_manifest"]["snapshot_ref"]
    governance_selected_copy = tmp_path / "governance-selected-mapping.json"
    shutil.copyfile(published, governance_selected_copy)

    result = verify(fixture["root"], receipt, governance_selected_copy)

    # Ordinary copies are mechanically distinct. Their caller-owned provenance
    # remains an external governance assertion rather than verifier evidence.
    assert_pass_result(result)
    assert result["source_separated"] is True
    assert not os.path.samefile(published, governance_selected_copy)


def test_relocated_copy_ignores_historical_absolute_root_and_stale_source_ref(
    tmp_path: Path,
) -> None:
    original_dir = tmp_path / "original"
    fixture, _plan, receipt, expected_mapping = committed_fixture(original_dir)
    original = verify(fixture["root"], receipt, expected_mapping)
    copied_root = tmp_path / "relocated/workspace-copy"
    copied_root.parent.mkdir(parents=True)
    shutil.copytree(fixture["root"], copied_root)
    copied_mapping = tmp_path / "relocated/caller-owned-mapping.json"
    shutil.copyfile(expected_mapping, copied_mapping)
    copied_receipt = copied_root / receipt.relative_to(fixture["root"])

    copied = verify(copied_root, copied_receipt, copied_mapping)

    assert_pass_result(copied)
    assert copied["graph_sha256"] == original["graph_sha256"]
    assert copied["historical_boundary_identity_sha256"] == original[
        "historical_boundary_identity_sha256"
    ]
    assert copied["post_migration_current_identity_sha256"] == original[
        "post_migration_current_identity_sha256"
    ]


def test_body_like_safe_ids_are_emitted_only_as_opaque_digest_tokens(
    tmp_path: Path,
) -> None:
    raw_task_id = "BODY-MUST-NOT-LEAK-SOURCE-SENTENCE"
    raw_pack_id = "CREDENTIAL-MUST-NOT-LEAK-PRIVATE-VALUE"
    fixture = make_vocabulary_workspace(
        tmp_path,
        token="opaque",
        task_id=raw_task_id,
        pack_id=raw_pack_id,
        task_path="opaque/current.md",
        pack_path=".task/task_pack/opaque/current.json",
    )
    _plan, receipt = commit_vocabulary_workspace(fixture, tmp_path)

    result = verify(fixture["root"], receipt, fixture["mapping"])
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True)

    assert_pass_result(result)
    assert raw_task_id not in encoded
    assert raw_pack_id not in encoded
    for field in ("historical_boundary_task_id", "post_migration_current_task_id"):
        assert re.fullmatch(r"task-sha256-[0-9a-f]{64}", result[field])
    for field in ("historical_boundary_pack_id", "post_migration_current_pack_id"):
        assert re.fullmatch(r"pack-sha256-[0-9a-f]{64}", result[field])


@pytest.mark.parametrize(
    ("artifact", "unsafe_id"),
    [
        ("task", "task-line-one\nBODY-MUST-NOT-LEAK"),
        ("pack", "pack-" + "x" * 161),
    ],
)
def test_control_or_oversized_task_pack_ids_fail_closed(
    tmp_path: Path, artifact: str, unsafe_id: str
) -> None:
    task_id = unsafe_id if artifact == "task" else "task-safe-id"
    pack_id = unsafe_id if artifact == "pack" else "pack-safe-id"
    fixture = make_vocabulary_workspace(
        tmp_path,
        token="unsafe-id",
        task_id=task_id,
        pack_id=pack_id,
        task_path="unsafe/current.md",
        pack_path=".task/task_pack/unsafe/current.json",
    )
    _plan, receipt = commit_vocabulary_workspace(fixture, tmp_path)

    with pytest.raises(verifier.VerificationError) as captured:
        verify(fixture["root"], receipt, fixture["mapping"])

    assert captured.value.error_code == "unsafe_output_identity"
    assert unsafe_id not in str(captured.value)


def test_cli_failure_uses_allowlisted_code_without_raw_mapping_token(
    tmp_path: Path,
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    raw_token = "RAW-SOURCE-SENTENCE-MUST-NOT-LEAK"
    mapping = json.loads(expected_mapping.read_text(encoding="utf-8"))
    mapping["event_mappings"] = {raw_token: {"unexpected": "shape"}}
    malformed_expectation = tmp_path / "malformed-caller-expectation.json"
    write_json(malformed_expectation, mapping)

    completed = run_verifier_cli(
        fixture["root"], receipt, malformed_expectation
    )
    result = json.loads(completed.stdout)

    assert completed.returncode == 1
    assert set(result) == {"status", "error_code"}
    assert result["status"] == "fail"
    assert re.fullmatch(r"[a-z0-9_]+", result["error_code"])
    assert raw_token not in completed.stdout
    assert raw_token not in completed.stderr


def test_cli_is_read_only_and_emits_body_free_bounded_json(tmp_path: Path) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    before = file_tree(fixture["root"])

    completed = run_verifier_cli(fixture["root"], receipt, expected_mapping)
    result = json.loads(completed.stdout)

    assert completed.returncode == 0, completed.stderr
    assert_pass_result(result)
    assert result["operation_scope"] == "verifier_process"
    assert result["verifier_migration_apply_count"] == 0
    assert result["verifier_migration_recover_count"] == 0
    assert result["verifier_migration_replay_count"] == 0
    assert result["issue_state_evaluation"] == "external_cycle_evidence_required"
    assert "issue_remains_open" not in result
    assert "Current task" not in completed.stdout
    assert "malformed historical row" not in completed.stdout
    assert str(fixture["root"]) not in completed.stdout
    assert len(completed.stdout.encode("utf-8")) < 8192
    assert file_tree(fixture["root"]) == before


def test_large_legitimate_tail_keeps_output_body_free_and_bounded(
    tmp_path: Path,
) -> None:
    fixture, _plan, receipt, expected_mapping = committed_fixture(tmp_path)
    tail = b"".join(
        canonical(
            {
                "format_version": 2,
                "schema_version": 1,
                "event": "upsert",
                "id": f"val-fixture-{position:05d}",
                "type": "validation",
                "status": "complete",
                "path": f".task/validation/fixture-{position:05d}.md",
                "title": "BODY-FREE-SCALAR-ONLY",
                "updated_at": "2026-07-12T03:00:00+09:00",
            }
        )
        for position in range(2500)
    )
    fixture["index"].write_bytes(fixture["index"].read_bytes() + tail)

    result = verify(fixture["root"], receipt, expected_mapping)

    assert_pass_result(result)
    assert result["current_event_count"] >= 2500
    assert "BODY-FREE-SCALAR-ONLY" not in json.dumps(result, ensure_ascii=False)
    assert len(canonical(result)) < 8192
