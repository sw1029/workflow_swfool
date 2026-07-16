"""Shared semantic fixtures for independent task-state migration verifier tests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable


SKILLS_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SKILLS_ROOT / "manage-task-state-index" / "scripts"
AGENT_LOG_SCRIPT_DIR = SKILLS_ROOT / "record-agent-work-log" / "scripts"
for package_root in (SCRIPT_DIR, AGENT_LOG_SCRIPT_DIR):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


from manage_task_state_index import index as task_index  # noqa: E402
from manage_task_state_index.migration import api as migration  # noqa: E402
from manage_task_state_index.verifier import cli as verifier  # noqa: E402
from manage_task_state_index.verifier import evidence as verifier_evidence  # noqa: E402

__all__ = ["task_index", "verifier_evidence"]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def mapping_manifest(
    *, row_resolutions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    reason_codes = {
        "legacy_shape": "Unambiguous legacy event shape.",
        "exact_status": "Caller-owned exact status mapping.",
        "exact_type": "Caller-owned exact type mapping.",
        "historical_malformed": "Exact historical row is independent.",
    }
    return {
        "schema_version": 1,
        "mapping_policy_id": "fixture-exact-policy",
        "mapping_method": "exact_token_review",
        "pattern_inference_used": False,
        "effective_at": "2026-07-12T00:00:00+09:00",
        "event_mappings": {
            "__MISSING__": {"to": "__INFER__", "reason_code": "legacy_shape"},
            "upsert": {"to": "upsert", "reason_code": "legacy_shape"},
            "link": {"to": "link", "reason_code": "legacy_shape"},
            "legacy_upsert": {"to": "upsert", "reason_code": "legacy_shape"},
        },
        "status_mappings": {
            "active": {"to": "active", "reason_code": "exact_status"},
            "partial": {"to": "partial", "reason_code": "exact_status"},
            "old_active": {"to": "active", "reason_code": "exact_status"},
            "__MISSING__": {"to": "informational", "reason_code": "exact_status"},
        },
        "type_mappings": {
            "task": {"to": "task", "reason_code": "exact_type"},
            "task_pack": {"to": "task_pack", "reason_code": "exact_type"},
            "old_task": {"to": "task", "reason_code": "exact_type"},
            "__MISSING__": {"to": "schema_contract", "reason_code": "exact_type"},
        },
        "reason_codes": reason_codes,
        "row_resolutions": row_resolutions or [],
    }


def make_workspace(
    base: Path, *, malformed: bool = True, missing_status: bool = False
) -> dict[str, Any]:
    root = base / "workspace"
    root.mkdir(parents=True)
    task_id = "task-current"
    pack_id = "pack-current"
    task = root / "task.md"
    task.write_text("# Current task\n", encoding="utf-8")
    pack_path = ".task/task_pack/pack-current.json"
    pack = root / pack_path
    write_json(
        pack,
        {
            "schema_version": 1,
            "pack_id": pack_id,
            "status": "active",
            "items": [],
        },
    )
    task_row: dict[str, Any] = {
        "id": task_id,
        "type": "old_task",
        "status": "old_active",
        "path": "task.md",
        "title": "Current task",
        "links": ["broken:missing-id", "promoted_from_pack:pack-old"],
        "updated_at": "2026-07-01T00:00:00+09:00",
    }
    if missing_status:
        task_row.pop("status")
    values = [
        task_row,
        {
            "id": "task-stale",
            "type": "task",
            "status": "active",
            "path": "task.md",
            "title": "Stale",
            "updated_at": "2026-07-01T00:00:01+09:00",
        },
        {
            "id": "pack-old",
            "type": "task_pack",
            "status": "active",
            "path": ".task/task_pack/old.json",
            "title": "Old",
            "updated_at": "2026-07-01T00:00:02+09:00",
        },
        {
            "id": pack_id,
            "event": "legacy_upsert",
            "type": "task_pack",
            "status": "old_active",
            "path": pack_path,
            "title": "Current pack",
            "updated_at": "2026-07-01T00:00:03+09:00",
        },
    ]
    rows = [canonical(value) for value in values]
    malformed_line = b"{malformed historical row}\n"
    if malformed:
        rows.append(malformed_line)
    index = root / ".task/index.jsonl"
    index.parent.mkdir(parents=True, exist_ok=True)
    prefix = b"".join(rows)
    index.write_bytes(prefix)
    mapping = mapping_manifest()
    if malformed:
        mapping["row_resolutions"] = [
            {
                "line": len(rows),
                "raw_line_sha256": sha(malformed_line),
                "disposition": "quarantined_historical",
                "projection_impact": "independent",
                "reason_code": "historical_malformed",
                "deterministic_identity": "historical-row",
                "resolution": "historical_only",
            }
        ]
    mapping_path = base / "mapping.json"
    write_json(mapping_path, mapping)
    return {
        "root": root,
        "prefix": prefix,
        "index": index,
        "mapping": mapping_path,
        "task_id": task_id,
        "task_path": "task.md",
        "task_sha": sha(task.read_bytes()),
        "pack_id": pack_id,
        "pack_path": pack_path,
        "pack_sha": sha(pack.read_bytes()),
    }


def build_fixture_plan(fixture: dict[str, Any], output: Path) -> dict[str, Any]:
    plan = migration.build_plan(
        fixture["root"],
        sha(fixture["prefix"]),
        fixture["task_id"],
        fixture["task_path"],
        fixture["task_sha"],
        fixture["pack_id"],
        fixture["pack_path"],
        fixture["pack_sha"],
        fixture["mapping"],
    )
    output.write_bytes(migration._canonical_bytes(plan))
    return plan


def make_vocabulary_workspace(
    base: Path,
    *,
    token: str,
    task_id: str,
    pack_id: str,
    task_path: str,
    pack_path: str,
) -> dict[str, Any]:
    root = base / f"workspace-{token}"
    root.mkdir(parents=True)
    task = root / task_path
    task.parent.mkdir(parents=True, exist_ok=True)
    task.write_text(f"# Caller fixture {token}\n", encoding="utf-8")
    pack = root / pack_path
    write_json(
        pack,
        {
            "schema_version": 1,
            "pack_id": pack_id,
            "status": "active",
            "items": [],
        },
    )
    legacy_event = f"write-{token}"
    legacy_status = f"selected-{token}"
    legacy_task_type = f"work-{token}"
    legacy_pack_type = f"queue-{token}"
    values = [
        {
            "event": legacy_event,
            "id": task_id,
            "type": legacy_task_type,
            "status": legacy_status,
            "path": task_path,
            "title": f"Task {token}",
            "updated_at": "2026-07-12T00:00:00+09:00",
        },
        {
            "event": legacy_event,
            "id": f"stale-{task_id}",
            "type": legacy_task_type,
            "status": legacy_status,
            "path": task_path,
            "title": f"Stale task {token}",
            "updated_at": "2026-07-12T00:00:01+09:00",
        },
        {
            "event": legacy_event,
            "id": f"stale-{pack_id}",
            "type": legacy_pack_type,
            "status": legacy_status,
            "path": f".task/retired/{token}.json",
            "title": f"Stale pack {token}",
            "updated_at": "2026-07-12T00:00:02+09:00",
        },
        {
            "event": legacy_event,
            "id": pack_id,
            "type": legacy_pack_type,
            "status": legacy_status,
            "path": pack_path,
            "title": f"Pack {token}",
            "updated_at": "2026-07-12T00:00:03+09:00",
        },
    ]
    prefix = b"".join(canonical(value) for value in values)
    index = root / ".task/index.jsonl"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_bytes(prefix)
    reason_codes = {
        "event": f"Exact event mapping for {token}.",
        "status": f"Exact status mapping for {token}.",
        "task_type": f"Exact task type mapping for {token}.",
        "pack_type": f"Exact pack type mapping for {token}.",
    }
    mapping = {
        "schema_version": 1,
        "mapping_policy_id": f"caller-policy-{token}",
        "mapping_method": "exact_token_review",
        "pattern_inference_used": False,
        "effective_at": "2026-07-12T00:00:00+09:00",
        "event_mappings": {
            legacy_event: {"to": "upsert", "reason_code": "event"}
        },
        "status_mappings": {
            legacy_status: {"to": "active", "reason_code": "status"}
        },
        "type_mappings": {
            legacy_task_type: {"to": "task", "reason_code": "task_type"},
            legacy_pack_type: {"to": "task_pack", "reason_code": "pack_type"},
        },
        "reason_codes": reason_codes,
        "row_resolutions": [],
    }
    mapping_path = base / f"caller-mapping-{token}.json"
    write_json(mapping_path, mapping)
    return {
        "root": root,
        "prefix": prefix,
        "index": index,
        "mapping": mapping_path,
        "task_id": task_id,
        "task_path": task_path,
        "task_sha": sha(task.read_bytes()),
        "pack_id": pack_id,
        "pack_path": pack_path,
        "pack_sha": sha(pack.read_bytes()),
    }


def commit_vocabulary_workspace(
    fixture: dict[str, Any], base: Path
) -> tuple[dict[str, Any], Path]:
    plan_path = base / "caller-plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    migration.apply_plan(
        fixture["root"],
        plan_path,
        sha(plan_path.read_bytes()),
        sha(fixture["prefix"]),
    )
    return plan, fixture["root"] / plan["receipt_ref"]


def committed_fixture(
    base: Path, *, malformed: bool = True
) -> tuple[dict[str, Any], dict[str, Any], Path, Path]:
    fixture = make_workspace(base, malformed=malformed)
    plan_path = base / "caller-plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    migration.apply_plan(
        fixture["root"],
        plan_path,
        sha(plan_path.read_bytes()),
        sha(fixture["prefix"]),
    )
    receipt = fixture["root"] / plan["receipt_ref"]
    expected_mapping = fixture["mapping"]
    assert expected_mapping.parent != receipt.parent
    assert not os.path.samefile(
        expected_mapping,
        fixture["root"] / plan["mapping_manifest"]["snapshot_ref"],
    )
    return fixture, plan, receipt, expected_mapping


def verify(
    root: Path,
    receipt: Path,
    expected_mapping: Path | None,
    *,
    recovery_status: str = "not_required",
    recovery_observation: dict[str, Any] | None = None,
    recovery_observation_sha256: str | None = None,
) -> dict[str, Any]:
    return verifier.verify_migration(
        root,
        receipt,
        expected_mapping_raw=expected_mapping,
        expected_recovery_status=recovery_status,
        recovery_observation=recovery_observation,
        expected_recovery_observation_sha256=recovery_observation_sha256,
    )


def assert_pass_result(result: dict[str, Any]) -> None:
    assert result["schema_version"] == 1
    assert result["kind"] == "task_state_migration_independent_verification"
    assert result["status"] == "pass"
    assert result["evaluation_status"] == "pass"
    assert result["verifier"] == (
        "task_state_migration_sealed_reader_recovery_boundary_independent_verifier"
    )
    assert result["source_separated"] is True
    assert result["read_only"] is True
    assert result["semantic_progress"] is False
    assert result["artifact_truth_completion"] is False


def mutate_anchor(root: Path, mutate: Callable[[dict[str, Any]], None]) -> None:
    index = root / ".task/index.jsonl"
    lines = index.read_bytes().splitlines(keepends=True)
    for position in range(len(lines) - 1, -1, -1):
        try:
            value = json.loads(lines[position].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        fields = value.get("fields") if isinstance(value, dict) else None
        if (
            isinstance(fields, dict)
            and fields.get("task_state_migration_event")
            == "task_state_migration_receipt_anchor"
        ):
            mutate(value)
            lines[position] = canonical(value)
            index.write_bytes(b"".join(lines))
            return
    raise AssertionError("fixture has no receipt anchor")


def mutate_graph_target(
    fixture: dict[str, Any], plan: dict[str, Any], receipt_path: Path, target: str
) -> None:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    root = fixture["root"]
    refs = {
        "plan": "plan_ref",
        "mapping": "mapping_manifest_ref",
        "resolution": "resolution_manifest_ref",
        "correction_suffix": "correction_suffix_ref",
        "rendered_snapshot": "rendered_index_ref",
        "prepare_journal": "prepare_journal_ref",
        "final_journal": "journal_ref",
        "completion_marker": "completion_marker_ref",
    }
    if target == "receipt":
        receipt_path.write_bytes(receipt_path.read_bytes() + b" ")
    elif target in refs:
        sidecar = root / receipt[refs[target]]
        sidecar.write_bytes(sidecar.read_bytes() + b" ")
    elif target == "seal":
        payload = bytearray(fixture["index"].read_bytes())
        offset = receipt["seal_offset"]
        payload[offset] = ord("[") if payload[offset] != ord("[") else ord("{")
        fixture["index"].write_bytes(bytes(payload))
    elif target == "anchor":
        mutate_anchor(
            root,
            lambda value: value["fields"].update(receipt_sha256="0" * 64),
        )
    else:
        raise AssertionError(f"unknown graph target {target}")


def crash_fixture(
    base: Path, monkeypatch: Any, *, crash_point: str = "after_partial_suffix"
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    fixture = make_workspace(base)
    plan_path = base / "caller-plan.json"
    plan = build_fixture_plan(fixture, plan_path)
    monkeypatch.setenv("TASK_STATE_MIGRATION_CRASH_AT", crash_point)
    try:
        migration.apply_plan(
            fixture["root"],
            plan_path,
            sha(plan_path.read_bytes()),
            sha(fixture["prefix"]),
        )
    except RuntimeError as exc:
        assert "injected crash" in str(exc)
    else:
        raise AssertionError(f"crash point did not interrupt apply: {crash_point}")
    finally:
        monkeypatch.delenv("TASK_STATE_MIGRATION_CRASH_AT")
    return fixture, plan, plan_path


def observe_and_recover(
    base: Path, monkeypatch: Any, *, crash_point: str = "after_partial_suffix"
) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    fixture, plan, _plan_path = crash_fixture(
        base, monkeypatch, crash_point=crash_point
    )
    observation = verifier.inspect_transaction_boundary(
        fixture["root"], plan["migration_id"]
    )
    migration.recover_transaction(fixture["root"], plan["migration_id"])
    return fixture, plan, fixture["root"] / plan["receipt_ref"], observation


def rehash_observation(
    observation: dict[str, Any], field: str, value: Any
) -> dict[str, Any]:
    forged = dict(observation)
    forged[field] = value
    forged["observation_sha256"] = verifier._boundary_observation_sha256(forged)
    return forged


def assert_forward_recovery_fails(
    fixture: dict[str, Any],
    receipt: Path,
    observation: dict[str, Any],
    *,
    expected_sha: str | None = None,
) -> None:
    try:
        verify(
            fixture["root"],
            receipt,
            fixture["mapping"],
            recovery_status="forward_completed",
            recovery_observation=observation,
            recovery_observation_sha256=(
                expected_sha
                if expected_sha is not None
                else observation["observation_sha256"]
            ),
        )
    except verifier.VerificationError:
        return
    raise AssertionError("forged recovery evidence unexpectedly passed")


def run_verifier_cli(
    root: Path,
    receipt: Path,
    expected_mapping: Path,
    *,
    recovery_status: str = "not_required",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "manage_task_state_index",
            "verify-migration",
            "--root",
            str(root),
            "--receipt",
            str(receipt),
            "--expected-mapping-manifest",
            str(expected_mapping),
            "--expected-recovery-status",
            recovery_status,
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join((str(SCRIPT_DIR), str(AGENT_LOG_SCRIPT_DIR))),
        },
    )
