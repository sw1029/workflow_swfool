from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any

import pytest

from test_agent_log_migration import (
    apply_store,
    basic_legacy_store,
    body,
    integrity,
    migration,
    plan_store,
    put_body,
    put_index,
    put_status_map,
    writer,
    writer_args,
)

from record_agent_work_log.verifier import cli as migration_verifier  # noqa: E402


def verify_migration(
    root: Path,
    receipt: Path,
    *,
    expected_recovery_status: str = "not_needed",
    **kwargs: Any,
) -> dict[str, Any]:
    return migration_verifier.verify_migration(
        root,
        receipt,
        expected_recovery_status=expected_recovery_status,
        **kwargs,
    )


def committed_verifier_fixture(root: Path) -> tuple[Path, dict[str, Any]]:
    _, status_map = basic_legacy_store(root)
    inspection, plan_path, plan_sha, _ = plan_store(root, status_map)
    result = apply_store(root, inspection, plan_path, plan_sha)
    return Path(result["receipt"]), result


def rewrite_transaction_documents(
    root: Path,
    receipt_path: Path,
    *,
    plan_mutator: Any | None = None,
    manifest_mutator: Any | None = None,
    source_mutator: Any | None = None,
    status_mutator: Any | None = None,
) -> None:
    """Rewrite declared hashes so verifier semantic checks, not producer hashes, decide."""

    transaction = receipt_path.parent
    plan_path = transaction / "plan.json"
    manifest_path = transaction / "resolution-manifest.json"
    source_path = transaction / "source-index.snapshot"
    status_path = transaction / "status-map.json"
    journal_path = transaction / "journal.json"
    marker_path = root / ".agent_log" / "migrations" / "active.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    status_map = json.loads(status_path.read_text(encoding="utf-8"))
    if manifest_mutator is not None:
        manifest_mutator(manifest)
    if source_mutator is not None:
        source_path.write_bytes(source_mutator(source_path.read_bytes()))
    if status_mutator is not None:
        status_mutator(status_map)
        status_path.write_bytes(migration._canonical_json_bytes(status_map))
    if isinstance(plan.get("status_map"), dict):
        plan["status_map"].update(
            sha256=hashlib.sha256(status_path.read_bytes()).hexdigest(),
            schema_version=status_map["schema_version"],
            mapping_policy_id=status_map["mapping_policy_id"],
            version=status_map["version"],
        )
    if plan_mutator is not None:
        plan_mutator(plan)
    plan_path.write_bytes(migration._canonical_json_bytes(plan))
    manifest_path.write_bytes(migration._canonical_json_bytes(manifest))

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    status_sha = hashlib.sha256(status_path.read_bytes()).hexdigest()
    receipt.update(
        plan_sha256=plan_sha,
        resolution_manifest_sha256=manifest_sha,
        source_snapshot_sha256=source_sha,
        status_map_sha256=status_sha,
    )
    journal.update(
        plan_sha256=plan_sha,
        manifest_sha256=manifest_sha,
        source_snapshot_sha256=source_sha,
        status_map_sha256=status_sha,
    )
    marker["plan_sha256"] = plan_sha
    receipt_path.write_bytes(migration._canonical_json_bytes(receipt))
    journal["receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    journal_path.write_bytes(migration._canonical_json_bytes(journal))
    marker["receipt_sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    marker["journal_sha256"] = hashlib.sha256(journal_path.read_bytes()).hexdigest()
    marker_path.write_bytes(migration._canonical_json_bytes(marker))


def test_independent_verifier_rejects_producer_only_success(tmp_path: Path) -> None:
    migration_id = "agent-log-migration-producer-only"
    transaction = tmp_path / ".agent_log" / "migrations" / migration_id
    transaction.mkdir(parents=True)
    receipt = transaction / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "agent_log_legacy_migration",
                "migration_id": migration_id,
                "transaction_status": "committed",
                "status": "success",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(migration_verifier.VerificationError):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_passes_complete_graph_and_is_repeatable(
    tmp_path: Path,
) -> None:
    receipt, result = committed_verifier_fixture(tmp_path)
    first = verify_migration(
        tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
    )
    second = verify_migration(
        tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
    )
    assert first == second
    assert first["status"] == "pass"
    assert first["schema_version"] == 1
    assert first["kind"] == "agent_log_migration_independent_verification"
    assert first["evaluation_status"] == "pass"
    assert first["source_separated"] is True
    assert first["read_only"] is True
    assert first["migration_id"] == result["migration_id"]


def test_independent_verifier_reconstructs_full_committed_record_bytes(
    tmp_path: Path,
) -> None:
    receipt_path, _ = committed_verifier_fixture(tmp_path)
    transaction = receipt_path.parent
    index_path = tmp_path / ".agent_log" / "index.jsonl"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()]
    records[0]["source_line"] = 999
    records[0]["record_id"] = integrity.expected_record_id(records[0])
    forged_prefix = b"".join(migration._canonical_json_bytes(record) for record in records)
    forged_sha = hashlib.sha256(forged_prefix).hexdigest()
    index_path.write_bytes(forged_prefix)
    (transaction / "staged-index.snapshot").write_bytes(forged_prefix)

    plan_path = transaction / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["expected_after_index_sha256"] = forged_sha
    plan["expected_after_index_size"] = len(forged_prefix)
    plan_path.write_bytes(migration._canonical_json_bytes(plan))
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.update(
        plan_sha256=plan_sha,
        after_index_sha256=forged_sha,
        after_index_size=len(forged_prefix),
    )
    receipt_path.write_bytes(migration._canonical_json_bytes(receipt))
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()

    journal_path = transaction / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal.update(
        plan_sha256=plan_sha,
        after_index_sha256=forged_sha,
        after_index_size=len(forged_prefix),
        receipt_sha256=receipt_sha,
    )
    journal_path.write_bytes(migration._canonical_json_bytes(journal))
    journal_sha = hashlib.sha256(journal_path.read_bytes()).hexdigest()

    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker.update(
        plan_sha256=plan_sha,
        after_index_sha256=forged_sha,
        after_index_size=len(forged_prefix),
        receipt_sha256=receipt_sha,
        journal_sha256=journal_sha,
    )
    marker_path.write_bytes(migration._canonical_json_bytes(marker))

    with pytest.raises(
        migration_verifier.VerificationError,
        match="independent source reconstruction",
    ):
        verify_migration(
            tmp_path,
            receipt_path,
            expected_status_map_raw=tmp_path / "status-map.json",
        )


@pytest.mark.parametrize(
    "artifact",
    [
        "plan.json",
        "status-map.json",
        "source-index.snapshot",
        "resolution-manifest.json",
        "journal.json",
        "receipt.json",
        "staged-index.snapshot",
    ],
)
def test_independent_verifier_fails_closed_on_each_tampered_edge(
    tmp_path: Path, artifact: str
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    target = receipt.parent / artifact
    target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises((migration_verifier.VerificationError, json.JSONDecodeError)):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_recomputes_status_and_source_classification(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def change_plan(plan: dict[str, Any]) -> None:
        row = next(item for item in plan["rows"] if item["classification"] == "canonical_log")
        row["normalized_status"] = "informational"

    def change_manifest(manifest: dict[str, Any]) -> None:
        row = next(item for item in manifest["source_rows"] if item["classification"] == "canonical_log")
        row["normalized_status"] = "informational"

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=change_plan,
        manifest_mutator=change_manifest,
    )
    with pytest.raises(migration_verifier.VerificationError, match="exact-map bound"):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_recomputes_canonical_duplicate_selection(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def swap_selection(rows: list[dict[str, Any]]) -> None:
        canonical = next(item for item in rows if item["classification"] == "canonical_log")
        alias = next(
            item
            for item in rows
            if item["classification"] == "duplicate_alias"
            and item["source_path"] == canonical["source_path"]
        )
        canonical.update(
            classification="duplicate_alias",
            disposition="retain_as_alias_evidence",
            canonical_target_source_line=alias["source_line"],
        )
        alias.update(
            classification="canonical_log",
            disposition="bind_existing_body",
            canonical_target_source_line=alias["source_line"],
            canonical_target_path=alias["source_path"],
        )

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: swap_selection(plan["rows"]),
        manifest_mutator=lambda manifest: swap_selection(manifest["source_rows"]),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="independent source classification mismatch",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_external_exact_status_map_rejects_coherently_rebound_sidecar(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def change_status_map(status_map: dict[str, Any]) -> None:
        status_map["entries"][0]["reason"] = "producer-rebound reason"

    def change_rows(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if row.get("original_status") == "partial":
                row["status_mapping_reason"] = "producer-rebound reason"

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        status_mutator=change_status_map,
        plan_mutator=lambda plan: change_rows(plan["rows"]),
        manifest_mutator=lambda manifest: change_rows(manifest["source_rows"]),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="status-map source differs|external exact status map",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_published_status_sidecar_cannot_pose_as_external_map(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    with pytest.raises(
        migration_verifier.VerificationError,
        match="caller-owned outside migration sidecars",
    ):
        verify_migration(
            tmp_path,
            receipt,
            expected_status_map_raw=receipt.parent / "status-map.json",
        )


def test_external_status_map_cannot_hardlink_published_sidecar(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    external = tmp_path / "status-map.json"
    external.unlink()
    os.link(receipt.parent / "status-map.json", external)
    with pytest.raises(
        migration_verifier.VerificationError,
        match="must not alias the published sidecar|must not be hard-linked",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=external
        )


def test_distinct_file_inside_transaction_is_not_an_external_status_map(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    forged_external = receipt.parent / "caller-owned-status-map.json"
    shutil.copyfile(tmp_path / "status-map.json", forged_external)
    forged_ref = forged_external.relative_to(tmp_path).as_posix()
    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: plan["status_map"].update(ref=forged_ref),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="inside the current migration transaction",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=forged_external
        )


def test_tool_version_lineage_is_exact(tmp_path: Path) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["tool_version"] = "incompatible-future"
    marker_path.write_bytes(migration._canonical_json_bytes(marker))
    with pytest.raises(migration_verifier.VerificationError, match="tool version"):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_unknown_publication_marker_field_is_rejected(tmp_path: Path) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["tampered"] = True
    marker_path.write_bytes(migration._canonical_json_bytes(marker))
    with pytest.raises(
        migration_verifier.VerificationError,
        match="exact schema-v1 projection",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


@pytest.mark.parametrize("document", ["plan", "manifest", "receipt", "journal"])
def test_unknown_governed_document_field_is_rejected(
    tmp_path: Path, document: str
) -> None:
    receipt_path, _ = committed_verifier_fixture(tmp_path)
    transaction = receipt_path.parent
    journal_path = transaction / "journal.json"
    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    if document == "plan":
        rewrite_transaction_documents(
            tmp_path,
            receipt_path,
            plan_mutator=lambda plan: plan.update(tampered=True),
        )
    elif document == "manifest":
        rewrite_transaction_documents(
            tmp_path,
            receipt_path,
            manifest_mutator=lambda manifest: manifest.update(tampered=True),
        )
    else:
        target = receipt_path if document == "receipt" else journal_path
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["tampered"] = True
        target.write_bytes(migration._canonical_json_bytes(payload))
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if document == "receipt":
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            journal["receipt_sha256"] = receipt_sha
            journal_path.write_bytes(migration._canonical_json_bytes(journal))
            marker["receipt_sha256"] = receipt_sha
        marker["journal_sha256"] = hashlib.sha256(
            journal_path.read_bytes()
        ).hexdigest()
        marker_path.write_bytes(migration._canonical_json_bytes(marker))
    with pytest.raises(
        migration_verifier.VerificationError,
        match="exact schema-v1 projection",
    ):
        verify_migration(
            tmp_path,
            receipt_path,
            expected_status_map_raw=tmp_path / "status-map.json",
        )


def test_forward_recovery_claim_requires_prior_boundary_observation(
    tmp_path: Path,
) -> None:
    receipt_path, _ = committed_verifier_fixture(tmp_path)
    journal_path = receipt_path.parent / "journal.json"
    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    receipt["recovery_status"] = "forward_completed"
    journal["recovery_status"] = "forward_completed"
    journal["recovered_at"] = journal.pop("committed_at")
    receipt_path.write_bytes(migration._canonical_json_bytes(receipt))
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    journal["receipt_sha256"] = receipt_sha
    journal_path.write_bytes(migration._canonical_json_bytes(journal))
    marker["receipt_sha256"] = receipt_sha
    marker["journal_sha256"] = hashlib.sha256(journal_path.read_bytes()).hexdigest()
    marker_path.write_bytes(migration._canonical_json_bytes(marker))
    with pytest.raises(
        migration_verifier.VerificationError,
        match="independent pre-recovery boundary observation",
    ):
        verify_migration(
            tmp_path,
            receipt_path,
            expected_status_map_raw=tmp_path / "status-map.json",
            expected_recovery_status="forward_completed",
        )


def test_forward_recovery_cannot_downgrade_caller_expectation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    monkeypatch.setenv("AGENT_LOG_MIGRATION_FAILPOINT", "after_switch")
    with pytest.raises(RuntimeError):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    monkeypatch.delenv("AGENT_LOG_MIGRATION_FAILPOINT")
    crashed = migration_verifier.inspect_transaction_boundary(
        tmp_path, plan["migration_id"]
    )
    recovered = migration.recover(tmp_path, plan["migration_id"])
    receipt_path = Path(recovered["receipt"])
    journal_path = receipt_path.parent / "journal.json"
    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    receipt["recovery_status"] = "not_needed"
    journal["recovery_status"] = "not_needed"
    journal["committed_at"] = journal.pop("recovered_at")
    receipt_path.write_bytes(migration._canonical_json_bytes(receipt))
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    journal["receipt_sha256"] = receipt_sha
    journal_path.write_bytes(migration._canonical_json_bytes(journal))
    marker["receipt_sha256"] = receipt_sha
    marker["journal_sha256"] = hashlib.sha256(journal_path.read_bytes()).hexdigest()
    marker_path.write_bytes(migration._canonical_json_bytes(marker))
    with pytest.raises(
        migration_verifier.VerificationError,
        match="differs from the caller expectation",
    ):
        verify_migration(
            tmp_path,
            receipt_path,
            expected_status_map_raw=status_map,
            expected_recovery_status="forward_completed",
            recovery_observation=crashed,
            expected_recovery_observation_sha256=crashed["observation_sha256"],
        )


def test_after_journal_commit_crash_has_verifiable_recovery_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    monkeypatch.setenv("AGENT_LOG_MIGRATION_FAILPOINT", "after_journal_commit")
    with pytest.raises(RuntimeError):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    monkeypatch.delenv("AGENT_LOG_MIGRATION_FAILPOINT")
    observed = migration_verifier.inspect_transaction_boundary(
        tmp_path, plan["migration_id"]
    )
    assert observed["journal_phase"] == "committed"
    assert observed["publication_state"] == "post_switch_incomplete"
    assert observed["receipt_present"] is True
    assert observed["marker_present"] is False
    recovered = migration.recover(tmp_path, plan["migration_id"])
    receipt = Path(recovered["receipt"])
    verified = verify_migration(
        tmp_path,
        receipt,
        expected_status_map_raw=status_map,
        expected_recovery_status="forward_completed",
        recovery_observation=observed,
        expected_recovery_observation_sha256=observed["observation_sha256"],
    )
    assert verified["status"] == "pass"
    assert verified["recovery_status"] == "forward_completed"


@pytest.mark.parametrize("omission", ["duplicate", "orphan"])
def test_independent_verifier_rejects_missing_duplicate_or_orphan_disposition(
    tmp_path: Path, omission: str
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def change_plan(plan: dict[str, Any]) -> None:
        if omission == "duplicate":
            row = next(item for item in plan["rows"] if item["classification"] == "duplicate_alias")
            row["canonical_target_source_line"] = None
        else:
            plan["orphans"] = []

    def change_manifest(manifest: dict[str, Any]) -> None:
        if omission == "duplicate":
            row = next(item for item in manifest["source_rows"] if item["classification"] == "duplicate_alias")
            row["canonical_target_source_line"] = None
        else:
            manifest["orphans"] = []

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=change_plan,
        manifest_mutator=change_manifest,
    )
    with pytest.raises(migration_verifier.VerificationError):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_recomputes_orphan_body_canonical_selection(
    tmp_path: Path,
) -> None:
    payload = body("Identical orphan body")
    first_path = ".agent_log/orphans/a.md"
    second_path = ".agent_log/orphans/b.md"
    put_body(tmp_path, first_path, payload)
    put_body(tmp_path, second_path, payload)
    put_index(tmp_path, [])
    status_map = put_status_map(tmp_path, [])
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)
    receipt = Path(apply_store(tmp_path, inspection, plan_path, plan_sha)["receipt"])

    def swap_orphans(document: dict[str, Any], resolution_key: str) -> None:
        by_path = {entry["path"]: entry for entry in document["orphans"]}
        by_path[first_path].update(
            disposition="quarantine_nonlog_body",
            canonical_target_path=second_path,
            alias_reason="byte_identical_body_different_path",
        )
        by_path[second_path]["disposition"] = "bind_as_legacy_import"
        by_path[second_path].pop("canonical_target_path", None)
        by_path[second_path].pop("alias_reason", None)
        resolutions = {entry["path"]: entry for entry in document[resolution_key]}
        resolutions[first_path]["disposition"] = "quarantine_nonlog_body"
        resolutions[second_path]["disposition"] = "bind_as_legacy_import"

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: swap_orphans(plan, "body_resolutions"),
        manifest_mutator=lambda manifest: swap_orphans(
            manifest, "markdown_resolutions"
        ),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="independent orphan disposition mismatch",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_rejects_plan_controlled_orphan_order(
    tmp_path: Path,
) -> None:
    put_body(tmp_path, ".agent_log/orphans/a.md", body("Orphan A"))
    put_body(tmp_path, ".agent_log/orphans/b.md", body("Orphan B"))
    put_index(tmp_path, [])
    status_map = put_status_map(tmp_path, [])
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)
    receipt = Path(apply_store(tmp_path, inspection, plan_path, plan_sha)["receipt"])
    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: plan["orphans"].reverse(),
        manifest_mutator=lambda manifest: manifest["orphans"].reverse(),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="orphan inventory order is not independently reproducible",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


@pytest.mark.parametrize("collection", ["rows", "body_resolutions"])
def test_independent_verifier_rejects_plan_controlled_projection_order(
    tmp_path: Path, collection: str
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    manifest_key = (
        "source_rows" if collection == "rows" else "markdown_resolutions"
    )
    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: plan[collection].reverse(),
        manifest_mutator=lambda manifest: manifest[manifest_key].reverse(),
    )
    expected = (
        "plan source-row order"
        if collection == "rows"
        else "body resolution order"
    )
    with pytest.raises(migration_verifier.VerificationError, match=expected):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_rejects_rehashed_stale_source_snapshot(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    rewrite_transaction_documents(
        tmp_path,
        receipt,
        source_mutator=lambda payload: payload + b"{}\n",
    )
    with pytest.raises(migration_verifier.VerificationError, match="plan source snapshot"):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_rejects_rehashed_source_index_path_tamper(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: plan["source_index"].update(
            path="different/source.jsonl"
        ),
    )
    with pytest.raises(migration_verifier.VerificationError, match="source index path"):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


@pytest.mark.parametrize("tamper", ["schema_bool", "status_map_null"])
def test_independent_verifier_rejects_malformed_nested_plan_types(
    tmp_path: Path, tamper: str
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def mutate(plan: dict[str, Any]) -> None:
        if tamper == "schema_bool":
            plan["schema_version"] = True
        else:
            plan["status_map"] = None

    rewrite_transaction_documents(tmp_path, receipt, plan_mutator=mutate)
    with pytest.raises(migration_verifier.VerificationError):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_empty_source_size_and_count_reject_boolean_aliases(tmp_path: Path) -> None:
    put_body(tmp_path, ".agent_log/orphans/one.md", body("One orphan"))
    put_index(tmp_path, [])
    status_map = put_status_map(tmp_path, [])
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)
    receipt = Path(apply_store(tmp_path, inspection, plan_path, plan_sha)["receipt"])
    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: plan["source_index"].update(
            size=False, raw_row_count=False
        ),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="source snapshot binding",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=status_map
        )


def test_independent_verifier_rejects_boolean_source_line_alias(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def mutate_rows(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if row.get("source_line") == 1:
                row["source_line"] = True
            if row.get("canonical_target_source_line") == 1:
                row["canonical_target_source_line"] = True

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: mutate_rows(plan["rows"]),
        manifest_mutator=lambda manifest: mutate_rows(manifest["source_rows"]),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="source-row order|line is missing, duplicate, or stale",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_plan_status_map_integer_version_rejects_boolean_alias(
    tmp_path: Path,
) -> None:
    _, status_path = basic_legacy_store(tmp_path)
    status_map = json.loads(status_path.read_text(encoding="utf-8"))
    status_map["version"] = 1
    status_path.write_bytes(migration._canonical_json_bytes(status_map))
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_path)
    receipt = Path(apply_store(tmp_path, inspection, plan_path, plan_sha)["receipt"])
    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: plan["status_map"].update(version=True),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="version type mismatch",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=status_path
        )


def test_source_body_declaration_is_exactly_recomputed(tmp_path: Path) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def mutate(rows: list[dict[str, Any]]) -> None:
        rows[0]["source_body_sha256"] = "0" * 64

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: mutate(plan["rows"]),
        manifest_mutator=lambda manifest: mutate(manifest["source_rows"]),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="source body declaration mismatch",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


@pytest.mark.parametrize(
    "tamper", ["foreign_target", "unresolved_reason", "duplicate_score"]
)
def test_source_row_projection_fields_are_exact(
    tmp_path: Path, tamper: str
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def mutate(rows: list[dict[str, Any]]) -> None:
        if tamper == "foreign_target":
            row = next(item for item in rows if item["classification"] == "foreign_event")
            row["canonical_target_source_line"] = 999
        elif tamper == "unresolved_reason":
            row = next(item for item in rows if item["classification"] == "canonical_log")
            row["unresolved_reason"] = "forged"
        else:
            row = next(item for item in rows if item["classification"] == "duplicate_alias")
            row["duplicate_candidate_score"] = [999]

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: mutate(plan["rows"]),
        manifest_mutator=lambda manifest: mutate(manifest["source_rows"]),
    )
    with pytest.raises(migration_verifier.VerificationError):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


@pytest.mark.parametrize("tamper", ["candidate_count", "score_component"])
def test_duplicate_evidence_rejects_boolean_integer_aliases(
    tmp_path: Path, tamper: str
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)

    def mutate(rows: list[dict[str, Any]]) -> None:
        if tamper == "candidate_count":
            row = next(item for item in rows if item["duplicate_candidate_count"] == 1)
            row["duplicate_candidate_count"] = True
        else:
            row = next(
                item
                for item in rows
                if 0 in item["duplicate_candidate_score"]
            )
            index = row["duplicate_candidate_score"].index(0)
            row["duplicate_candidate_score"][index] = False

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: mutate(plan["rows"]),
        manifest_mutator=lambda manifest: mutate(manifest["source_rows"]),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="duplicate evidence projection mismatch",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


@pytest.mark.parametrize("tamper", ["size_bool", "structured_status"])
def test_orphan_schema_and_no_overclaim_fields_are_exact(
    tmp_path: Path, tamper: str
) -> None:
    orphan_path = ".agent_log/orphans/one.md"
    put_body(tmp_path, orphan_path, b"x")
    put_index(tmp_path, [])
    status_map = put_status_map(tmp_path, [])
    inspection, plan_path, plan_sha, _ = plan_store(tmp_path, status_map)
    receipt = Path(apply_store(tmp_path, inspection, plan_path, plan_sha)["receipt"])

    def mutate(document: dict[str, Any], resolution_key: str) -> None:
        if tamper == "size_bool":
            document["orphans"][0]["size"] = True
            document[resolution_key][0]["size"] = True
        else:
            document["orphans"][0]["structured_fields_status"] = "evaluated"

    rewrite_transaction_documents(
        tmp_path,
        receipt,
        plan_mutator=lambda plan: mutate(plan, "body_resolutions"),
        manifest_mutator=lambda manifest: mutate(
            manifest, "markdown_resolutions"
        ),
    )
    with pytest.raises(migration_verifier.VerificationError):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=status_map
        )


def test_independent_verifier_recomputes_migration_identity(
    tmp_path: Path,
) -> None:
    receipt_path, _ = committed_verifier_fixture(tmp_path)
    transaction = receipt_path.parent
    plan_path = transaction / "plan.json"
    journal_path = transaction / "journal.json"
    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    forged_basis = {
        "resolved_path": plan["root_identity"]["resolved_path"] + "-forged",
        "device": plan["root_identity"]["device"],
        "inode": plan["root_identity"]["inode"],
    }
    forged_identity = {
        **forged_basis,
        "sha256": hashlib.sha256(
            migration._canonical_json_bytes(forged_basis)
        ).hexdigest(),
    }
    plan["root_identity"] = forged_identity
    journal["root_identity"] = forged_identity
    plan_path.write_bytes(migration._canonical_json_bytes(plan))
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["plan_sha256"] = plan_sha
    receipt_path.write_bytes(migration._canonical_json_bytes(receipt))
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    journal["plan_sha256"] = plan_sha
    journal["receipt_sha256"] = receipt_sha
    journal_path.write_bytes(migration._canonical_json_bytes(journal))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker.update(
        plan_sha256=plan_sha,
        receipt_sha256=receipt_sha,
        journal_sha256=hashlib.sha256(journal_path.read_bytes()).hexdigest(),
    )
    marker_path.write_bytes(migration._canonical_json_bytes(marker))
    with pytest.raises(
        migration_verifier.VerificationError,
        match="migration identity is not independently reproducible",
    ):
        verify_migration(
            tmp_path,
            receipt_path,
            expected_status_map_raw=tmp_path / "status-map.json",
        )


def test_root_identity_unknown_field_is_rejected(tmp_path: Path) -> None:
    receipt_path, _ = committed_verifier_fixture(tmp_path)
    transaction = receipt_path.parent
    plan_path = transaction / "plan.json"
    journal_path = transaction / "journal.json"
    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    plan["root_identity"]["tampered"] = True
    journal["root_identity"]["tampered"] = True
    plan_path.write_bytes(migration._canonical_json_bytes(plan))
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["plan_sha256"] = plan_sha
    receipt_path.write_bytes(migration._canonical_json_bytes(receipt))
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    journal["plan_sha256"] = plan_sha
    journal["receipt_sha256"] = receipt_sha
    journal_path.write_bytes(migration._canonical_json_bytes(journal))
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker.update(
        plan_sha256=plan_sha,
        receipt_sha256=receipt_sha,
        journal_sha256=hashlib.sha256(journal_path.read_bytes()).hexdigest(),
    )
    marker_path.write_bytes(migration._canonical_json_bytes(marker))
    with pytest.raises(
        migration_verifier.VerificationError,
        match="root identity is not the exact schema-v1 projection",
    ):
        verify_migration(
            tmp_path,
            receipt_path,
            expected_status_map_raw=tmp_path / "status-map.json",
        )


def generalized_store(root: Path, *, status: str, relative: str) -> Path:
    payload = body("Generalized fixture", log_id=f"log-{status}", status=status)
    put_body(root, relative, payload)
    put_index(
        root,
        [
            {
                "timestamp": "2026-02-01T00:00:00Z",
                "status": status,
                "path": relative,
                "log_id": f"log-{status}",
                "title": "Generalized fixture",
            }
        ],
    )
    status_map = put_status_map(
        root,
        [(status, "partial", f"exact fixture mapping for {status}", None)],
    )
    inspection, plan_path, plan_sha, _ = plan_store(root, status_map)
    return Path(apply_store(root, inspection, plan_path, plan_sha)["receipt"])


@pytest.mark.parametrize(
    ("status", "relative"),
    [
        ("queued-by-alpha", ".agent_log/team-alpha/deep/one.md"),
        ("awaiting-beta", ".agent_log/other-vocabulary/two.md"),
    ],
)
def test_independent_verifier_generalizes_across_vocabularies_and_paths(
    tmp_path: Path, status: str, relative: str
) -> None:
    receipt = generalized_store(tmp_path, status=status, relative=relative)
    assert verify_migration(
        tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
    )["status"] == "pass"


def test_copied_committed_graph_verifies_without_original_root_identity(
    tmp_path: Path,
) -> None:
    original = tmp_path / "original"
    copied = tmp_path / "copied"
    receipt, _ = committed_verifier_fixture(original)
    relative_receipt = receipt.relative_to(original)
    shutil.copytree(original, copied)
    result = verify_migration(
        copied,
        copied / relative_receipt,
        expected_status_map_raw=copied / "status-map.json",
    )
    assert result["status"] == "pass"
    assert result["read_only"] is True


def test_independent_verifier_rejects_unindexed_post_migration_markdown(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    put_body(
        tmp_path,
        ".agent_log/post-migration/unindexed.md",
        body("Unindexed post-migration body"),
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="post-migration Markdown/index accounting mismatch",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_rejects_migration_identity_in_appended_tail(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    writer.write_log(writer_args(tmp_path))
    index_path = tmp_path / ".agent_log" / "index.jsonl"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()]
    records[-1]["migration_id"] = "agent-log-migration-forged-tail"
    records[-1]["record_id"] = integrity.expected_record_id(records[-1])
    put_index(tmp_path, records)
    with pytest.raises(
        migration_verifier.VerificationError,
        match="after the sealed boundary",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_independent_verifier_rejects_missing_tail_timestamp(
    tmp_path: Path,
) -> None:
    receipt, _ = committed_verifier_fixture(tmp_path)
    writer.write_log(writer_args(tmp_path))
    index_path = tmp_path / ".agent_log" / "index.jsonl"
    records = [json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines()]
    records[-1].pop("timestamp")
    records[-1]["record_id"] = integrity.expected_record_id(records[-1])
    put_index(tmp_path, records)
    with pytest.raises(
        migration_verifier.VerificationError,
        match="missing non-empty timestamp",
    ):
        verify_migration(
            tmp_path, receipt, expected_status_map_raw=tmp_path / "status-map.json"
        )


def test_recovered_graph_and_exact_replay_have_one_stable_verifier_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    monkeypatch.setenv("AGENT_LOG_MIGRATION_FAILPOINT", "after_switch")
    with pytest.raises(RuntimeError, match="injected migration crash"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    monkeypatch.delenv("AGENT_LOG_MIGRATION_FAILPOINT")
    crashed = migration_verifier.inspect_transaction_boundary(
        tmp_path, plan["migration_id"]
    )
    assert crashed["publication_state"] == "post_switch_incomplete"
    assert crashed["forward_recovery_required"] is True
    assert crashed["exact_replay_noop_eligible"] is False
    recovered = migration.recover(tmp_path, plan["migration_id"])
    receipt = Path(recovered["receipt"])
    verified = verify_migration(
        tmp_path,
        receipt,
        expected_status_map_raw=tmp_path / "status-map.json",
        expected_recovery_status="forward_completed",
        recovery_observation=crashed,
        expected_recovery_observation_sha256=crashed["observation_sha256"],
    )
    tampered_observation = {**crashed, "tampered": True}
    with pytest.raises(
        migration_verifier.VerificationError,
        match="unknown or missing fields",
    ):
        verify_migration(
            tmp_path,
            receipt,
            expected_status_map_raw=tmp_path / "status-map.json",
            expected_recovery_status="forward_completed",
            recovery_observation=tampered_observation,
            expected_recovery_observation_sha256=crashed["observation_sha256"],
        )
    coherently_rehashed = {**crashed, "journal_sha256": "0" * 64}
    coherently_rehashed["observation_sha256"] = (
        migration_verifier._boundary_observation_sha256(coherently_rehashed)
    )
    with pytest.raises(
        migration_verifier.VerificationError,
        match="external hash anchor",
    ):
        verify_migration(
            tmp_path,
            receipt,
            expected_status_map_raw=tmp_path / "status-map.json",
            expected_recovery_status="forward_completed",
            recovery_observation=coherently_rehashed,
            expected_recovery_observation_sha256=crashed["observation_sha256"],
        )
    replay = apply_store(tmp_path, inspection, plan_path, plan_sha)
    repeated = verify_migration(
        tmp_path,
        receipt,
        expected_status_map_raw=tmp_path / "status-map.json",
        expected_recovery_status="forward_completed",
        recovery_observation=crashed,
        expected_recovery_observation_sha256=crashed["observation_sha256"],
    )
    committed = migration_verifier.inspect_transaction_boundary(
        tmp_path,
        plan["migration_id"],
        expected_status_map_raw=tmp_path / "status-map.json",
        expected_recovery_status="forward_completed",
        recovery_observation=crashed,
        expected_recovery_observation_sha256=crashed["observation_sha256"],
    )
    assert recovered["status"] == "forward_completed"
    assert verified["recovery_status"] == "forward_completed"
    assert replay["status"] == "already_committed"
    assert replay["idempotent"] is True
    assert committed["publication_state"] == "committed"
    assert committed["forward_recovery_required"] is False
    assert committed["exact_replay_noop_eligible"] is True
    assert repeated == verified


def test_crash_observer_rejects_pre_switch_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, status_map = basic_legacy_store(tmp_path)
    inspection, plan_path, plan_sha, plan = plan_store(tmp_path, status_map)
    monkeypatch.setenv("AGENT_LOG_MIGRATION_FAILPOINT", "after_prepare")
    with pytest.raises(RuntimeError, match="injected migration crash"):
        apply_store(tmp_path, inspection, plan_path, plan_sha)
    monkeypatch.delenv("AGENT_LOG_MIGRATION_FAILPOINT")
    index_path = tmp_path / ".agent_log" / "index.jsonl"
    index_path.write_bytes(index_path.read_bytes() + b"{}\n")
    with pytest.raises(
        migration_verifier.VerificationError,
        match="neither the pre-switch source nor committed prefix",
    ):
        migration_verifier.inspect_transaction_boundary(
            tmp_path, plan["migration_id"]
        )


def test_committed_boundary_observer_rejects_unbound_marker(
    tmp_path: Path,
) -> None:
    receipt, result = committed_verifier_fixture(tmp_path)
    marker_path = tmp_path / ".agent_log" / "migrations" / "active.json"
    marker_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(migration_verifier.VerificationError):
        migration_verifier.inspect_transaction_boundary(
            tmp_path,
            result["migration_id"],
            expected_status_map_raw=tmp_path / "status-map.json",
        )
    assert receipt.exists()
