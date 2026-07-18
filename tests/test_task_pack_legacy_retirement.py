from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from orchestrate_task_cycle.task_pack import legacy_retirement_commands as commands
from orchestrate_task_cycle.task_pack import legacy_retirement_contract as contract
from orchestrate_task_cycle.task_pack import legacy_retirement_validation as validation
from orchestrate_task_cycle.task_pack.legacy_retirement import (
    require_pack_not_retired,
    retirement_store_projection,
)
from orchestrate_task_cycle.task_pack.presentation import (
    _command_status_locked,
    _command_validate_locked,
)
from orchestrate_task_cycle.task_pack.storage import canonical_pack_sha256
from orchestrate_task_cycle.task_pack.store import task_pack_store_findings


AT = "2026-07-18T10:00:00+09:00"


def _write_json(
    path: Path, value: dict[str, Any], root: Path | None = None
) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "ref": path.relative_to(root).as_posix()
        if root is not None
        else path.as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _workspace(
    root: Path, *, pack_id: str = "pack-legacy"
) -> tuple[Path, dict[str, Any]]:
    (root / ".task/task_pack").mkdir(parents=True)
    task = (
        "# Task\n\n- Status: `completed`\n- Executable: `false`\n- Task Pack: `none`\n"
    )
    (root / "task.md").write_text(task, encoding="utf-8")
    pack = {
        "schema_version": 1,
        "pack_id": pack_id,
        "status": "completed",
        "goal": "Historical goal.",
        "current_item_id": None,
        "items": [
            {
                "item_id": "item-legacy",
                "order": 1,
                "status": "consumed",
                "title": "Historical item",
                "objective": "Historical objective.",
                "acceptance": ["Historical acceptance."],
                "validation_profile": "current_only",
                "progress_target": "advanced",
            }
        ],
        "mutation_log": [],
    }
    pack_path = root / f".task/task_pack/{pack_id}.json"
    _write_json(pack_path, pack)
    return pack_path, pack


def _plan(
    root: Path, pack_path: Path, pack: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    packet = {
        "packet_id": "authop-test",
        "reservation_binding": {"reservation_id": "authz-test"},
    }
    verification = {
        "verification_id": "authv-test",
        "stage": "pre_commit",
    }
    packet_path = root / ".task/cycle/authority.json"
    verification_path = root / ".task/authorization/verifications/authv-test.json"
    packet_binding = _write_json(packet_path, packet, root)
    verification_binding = _write_json(verification_path, verification, root)
    plan = {
        "schema_version": 1,
        "artifact_kind": "legacy_task_pack_retirement_plan",
        "source_pack": {
            "ref": pack_path.relative_to(root).as_posix(),
            "file_sha256": hashlib.sha256(pack_path.read_bytes()).hexdigest(),
            "canonical_pack_sha256": canonical_pack_sha256(pack),
            "pack_id": pack["pack_id"],
        },
        "task_binding": {
            "ref": "task.md",
            "sha256": hashlib.sha256((root / "task.md").read_bytes()).hexdigest(),
        },
        "authority_packet": packet_binding,
        "pre_commit_verification": verification_binding,
        "consume_idempotency_key": f"task-pack-retire:{pack['pack_id']}:authority-consume",
        "prepared_at": AT,
        "reason_code": contract.REASON_CODE,
    }
    return plan, packet, verification


def _retire(
    root: Path,
    plan: dict[str, Any],
    packet: dict[str, Any],
    verification: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    monkeypatch.setattr(
        commands,
        "validate_authority_phase",
        lambda _root, _plan: (packet, verification),
    )
    result = commands.command_retire_legacy(
        argparse.Namespace(root=str(root), plan=json.dumps(plan), dry_run=False)
    )
    output = json.loads(capsys.readouterr().out)
    assert result == 0, output
    assert output["status"] == "pending_settlement"
    return output


def _activate(
    root: Path,
    retired: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    use_path = root / ".task/authorization/use_receipts/authu-test.json"
    use_binding = _write_json(
        use_path,
        {
            "schema_version": 2,
            "artifact_kind": "authority_use_receipt",
            "receipt_id": "authu-test",
            "consumed_at": AT,
        },
        root,
    )
    monkeypatch.setattr(
        commands, "validate_authority_use_receipt_settlement", lambda *a, **k: []
    )
    monkeypatch.setattr(
        validation, "validate_authority_use_receipt_settlement", lambda *a, **k: []
    )
    completion = retired["execution_result"]
    result = commands.command_activate_legacy_retirement(
        argparse.Namespace(
            root=str(root),
            completion_ref=completion["ref"],
            completion_sha256=completion["sha256"],
            use_receipt_ref=use_binding["ref"],
            use_receipt_sha256=use_binding["sha256"],
        )
    )
    output = json.loads(capsys.readouterr().out)
    assert result == 0
    assert output["status"] == "active"
    return output


def test_retirement_is_inactive_until_settled_and_preserves_raw_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, pack = _workspace(tmp_path)
    original = pack_path.read_bytes()
    plan, packet, verification = _plan(tmp_path, pack_path, pack)

    retired = _retire(tmp_path, plan, packet, verification, monkeypatch, capsys)

    projection = retirement_store_projection(tmp_path)
    assert projection["active_count"] == 0
    assert projection["pending_count"] == 1
    assert any(
        row["code"] == "authority_settlement_pending" for row in projection["findings"]
    )
    assert task_pack_store_findings(tmp_path)
    assert pack_path.read_bytes() == original

    _activate(tmp_path, retired, monkeypatch, capsys)

    projection = retirement_store_projection(tmp_path)
    assert projection["status"] == "ok"
    assert projection["active_count"] == 1
    assert task_pack_store_findings(tmp_path) == []
    assert pack_path.read_bytes() == original


def test_status_and_validate_separate_operational_retirement_from_raw_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, pack = _workspace(tmp_path)
    plan, packet, verification = _plan(tmp_path, pack_path, pack)
    retired = _retire(tmp_path, plan, packet, verification, monkeypatch, capsys)
    _activate(tmp_path, retired, monkeypatch, capsys)

    assert _command_status_locked(tmp_path) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "not_applicable"
    assert status["legacy_retired_pack_count"] == 1
    assert status["closed_packs"][0]["operational_disposition"] == "retired_legacy"

    args = argparse.Namespace(pack=None, strict_findings=False)
    assert _command_validate_locked(tmp_path, args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    assert report["results"][0]["operational_status"] == "retired_legacy"
    assert report["results"][0]["raw_status"] == "block"
    assert report["raw_finding_count"] > 0

    args.strict_findings = True
    assert _command_validate_locked(tmp_path, args) == 2
    strict = json.loads(capsys.readouterr().out)
    assert strict["status"] == "ok"
    assert strict["raw_finding_count"] > 0


def test_activated_raw_pack_is_immutable_and_drift_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, pack = _workspace(tmp_path)
    plan, packet, verification = _plan(tmp_path, pack_path, pack)
    retired = _retire(tmp_path, plan, packet, verification, monkeypatch, capsys)
    _activate(tmp_path, retired, monkeypatch, capsys)

    changed = json.loads(pack_path.read_text(encoding="utf-8"))
    changed["goal"] = "Drifted goal."
    _write_json(pack_path, changed)

    projection = retirement_store_projection(tmp_path)
    assert projection["status"] == "block"
    assert projection["active_count"] == 0
    assert any(
        row["code"] == "legacy_retirement_artifact_invalid"
        for row in projection["findings"]
    )


def test_clean_or_unknown_invalid_pack_cannot_be_retired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack_path, pack = _workspace(tmp_path)
    plan, _packet, _verification = _plan(tmp_path, pack_path, pack)
    monkeypatch.setattr(contract, "validate_pack", lambda *_args: [])
    with pytest.raises(ValueError, match="clean task pack"):
        contract.validate_target(tmp_path, contract.normalize_plan(plan))

    monkeypatch.setattr(
        contract,
        "validate_pack",
        lambda *_args: [{"severity": "block", "code": "new_unknown_contract_failure"}],
    )
    with pytest.raises(ValueError, match="outside the legacy eligibility contract"):
        contract.validate_target(tmp_path, contract.normalize_plan(plan))


def test_direct_mutation_guard_names_retired_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, pack = _workspace(tmp_path)
    plan, packet, verification = _plan(tmp_path, pack_path, pack)
    retired = _retire(tmp_path, plan, packet, verification, monkeypatch, capsys)
    _activate(tmp_path, retired, monkeypatch, capsys)

    with pytest.raises(SystemExit, match="immutable retired legacy artifact"):
        require_pack_not_retired(tmp_path, pack_path)


def test_retired_pack_cannot_be_rebound_as_current_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack_path, pack = _workspace(tmp_path)
    plan, packet, verification = _plan(tmp_path, pack_path, pack)
    retired = _retire(tmp_path, plan, packet, verification, monkeypatch, capsys)
    _activate(tmp_path, retired, monkeypatch, capsys)
    (tmp_path / "task.md").write_text(
        "# Task\n\n"
        "- Status: `active`\n"
        "- Executable: `true`\n"
        "- Task Pack: `pack-legacy`\n",
        encoding="utf-8",
    )

    projection = retirement_store_projection(tmp_path)

    assert projection["status"] == "block"
    assert projection["active_count"] == 0
    assert "current task is bound" in projection["findings"][0]["message"]
