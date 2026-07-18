from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.selection_tick_premise import (
    RAW_PREMISE_CONTRACT,
    VERIFIED_PREMISE_CONTRACT,
)
from orchestrate_task_cycle import terminal_wait_baseline as owner
from orchestrate_task_cycle import terminal_wait_baseline_cli as owner_cli
from orchestrate_task_cycle import terminal_wait_baseline_contract as contract
from orchestrate_task_cycle import terminal_wait_baseline_store as store
from orchestrate_task_cycle import terminal_wait_baseline_validation as validation


AUTHORITY_SCRIPTS = (
    Path(__file__).resolve().parents[1] / "manage-agent-authority" / "scripts"
)
if str(AUTHORITY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTHORITY_SCRIPTS))

from manage_agent_authority.lifecycle_preflight import subject_preflight  # noqa: E402


AT = "2026-07-18T12:00:00+09:00"


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    return _write(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _workspace(root: Path, suffix: str = "A") -> dict[str, Any]:
    task = _write(
        root / "task.md",
        "# Task\n\n- Status: `completed`\n- Executable: `false`\n- Task Pack: `none`\n",
    )
    derive = _write_json(
        root / f".task/cycle/cycle-{suffix}/derive.json",
        {"result": {"selected_task_source": "terminal_wait"}},
    )
    transition = _write_json(
        root / f".task/cycle/cycle-{suffix}/transition.json",
        {"transition_id": f"transition-{suffix}", "status": "completed_local"},
    )
    baseline = build_selection_tick(
        root,
        wake_predicates=["fresh-exact-subject-or-authority"],
        watched_evidence_classes=["exact_subject", "authority"],
        minimum_material_delta="fresh-exact-subject-or-authority-delta",
        premise_contract=VERIFIED_PREMISE_CONTRACT,
    )
    baseline_path = _write_json(
        root / f".task/cycle/cycle-{suffix}/selection-tick.json", baseline
    )
    packet_path = _write_json(
        root / f".task/cycle/cycle-{suffix}/authority-packet.json",
        {
            "packet_id": f"authop-{suffix}",
            "reservation_binding": {"reservation_id": f"authz-{suffix}"},
        },
    )
    verification_path = _write_json(
        root / f".task/authorization/verifications/authv-{suffix}.json",
        {"verification_id": f"authv-{suffix}", "stage": "pre_commit"},
    )
    source_core = {
        "schema_version": 1,
        "artifact_kind": "terminal_wait_baseline_authority_subject",
        "task": {
            "task_id": f"task-{suffix}",
            **_binding(root, task),
        },
        "source_derive": _binding(root, derive),
        "transition_evidence": _binding(root, transition),
        "selection_baseline": _binding(root, baseline_path),
        "expected_current_snapshot_sha256": None,
    }
    subject = owner.materialize_terminal_wait_authority_subject(root, source_core)
    return {
        **source_core,
        "artifact_kind": "terminal_wait_baseline_plan",
        "authority_subject": subject["authority_subject_binding"],
        "authority_packet": _binding(root, packet_path),
        "pre_commit_verification": _binding(root, verification_path),
        "consume_idempotency_key": f"terminal-wait-baseline:task-{suffix}:consume",
        "prepared_at": AT,
    }


def _patch_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        owner,
        "validate_authority_phase",
        lambda root, plan: (
            {
                "reservation_binding": {"reservation_id": "authz-test"},
            },
            {"verification_id": "authv-test"},
        ),
    )
    monkeypatch.setattr(
        owner, "validate_authority_use_receipt_settlement", lambda *a, **k: []
    )
    monkeypatch.setattr(
        validation,
        "validate_authority_use_receipt_settlement",
        lambda *a, **k: [],
    )


def _use_receipt(root: Path, suffix: str = "A") -> dict[str, str]:
    path = _write_json(
        root / f".task/authorization/use_receipts/authu-{suffix}.json",
        {
            "schema_version": 2,
            "artifact_kind": "authority_use_receipt",
            "receipt_id": f"authu-{suffix}",
            "consumed_at": AT,
        },
    )
    return _binding(root, path)


def test_prepare_stays_inactive_until_settled_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _workspace(tmp_path)
    _patch_authority(monkeypatch)

    prepared = owner.prepare_terminal_wait_baseline(tmp_path, plan)

    assert prepared["status"] == "pending_settlement"
    assert prepared["current_pointer_exposed"] is False
    assert not (tmp_path / ".task/terminal_wait_baseline/current.json").exists()
    assert owner.resolve_terminal_wait_baseline(tmp_path)["status"] == "empty"

    activated = owner.activate_terminal_wait_baseline(
        tmp_path, prepared["execution_result"], _use_receipt(tmp_path)
    )
    resolved = owner.resolve_terminal_wait_baseline(tmp_path)
    current_tick = owner.current_selection_tick_packet(tmp_path)

    assert activated["status"] == "active"
    assert activated["current_pointer_exposed"] is True
    assert resolved["binding_id"] == prepared["binding_id"]
    assert current_tick is not None
    assert current_tick["packet_id"].startswith("selection-tick-")
    assert set(resolved["source_derive"]) == {"ref", "sha256"}
    assert set(resolved["selection_baseline"]) == {
        "ref",
        "sha256",
        "packet_id",
        "observed_input_manifest_sha256",
    }
    assert "selected_task_source" not in json.dumps(resolved)
    replay = owner.activate_terminal_wait_baseline(
        tmp_path, prepared["execution_result"], _use_receipt(tmp_path)
    )
    assert replay["idempotent"] is True
    assert replay["current_pointer"] == resolved["current_pointer"]


def test_dry_run_does_not_create_owner_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _workspace(tmp_path)
    _patch_authority(monkeypatch)

    result = owner.prepare_terminal_wait_baseline(tmp_path, plan, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["mutation_performed"] is False
    store = tmp_path / ".task/terminal_wait_baseline"
    assert not (store / "prepares").exists()
    assert not (store / "snapshots").exists()
    assert not (store / "completions").exists()
    assert not (store / "current.json").exists()


def test_invalid_settlement_never_exposes_current_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _workspace(tmp_path)
    _patch_authority(monkeypatch)
    prepared = owner.prepare_terminal_wait_baseline(tmp_path, plan)
    monkeypatch.setattr(
        owner,
        "validate_authority_use_receipt_settlement",
        lambda *a, **k: [{"code": "forged_use_receipt"}],
    )

    with pytest.raises(ValueError, match="forged_use_receipt"):
        owner.activate_terminal_wait_baseline(
            tmp_path, prepared["execution_result"], _use_receipt(tmp_path)
        )

    assert not (tmp_path / ".task/terminal_wait_baseline/current.json").exists()


def test_authority_phase_binds_all_baseline_sources_into_exact_subject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _workspace(tmp_path)
    normalized = contract.normalize_plan(plan)
    packet = {
        "decision_binding": {"decision": "allowed"},
        "operation_binding": {
            "skill_id": "orchestrate-task-cycle",
            "skill_version": "2.0.0",
            "operation_id": "publish_terminal_wait_baseline_binding",
            "operation_version": "1",
            "mutation_class": "local_mutation",
        },
        "subject": contract.validate_authority_subject_binding(tmp_path, normalized),
        "scope": {"task_id": normalized["task"]["task_id"]},
    }
    packet_path = _write_json(
        tmp_path / ".task/cycle/cycle-A/authority-packet-exact.json", packet
    )
    normalized["authority_packet"] = _binding(tmp_path, packet_path)
    monkeypatch.setattr(
        contract,
        "project_authority_packet",
        lambda value: SimpleNamespace(valid=True, findings=[]),
    )
    monkeypatch.setattr(contract, "validate_authority_artifacts", lambda *a: [])
    monkeypatch.setattr(
        contract, "validate_authority_verification_binding", lambda *a, **k: []
    )

    checked, _ = contract.validate_authority_phase(tmp_path, normalized)
    subject_preflight(tmp_path, {"subject": checked["subject"]})
    assert checked["subject"]["digest"] == contract.subject_digest(normalized)
    assert checked["subject"]["digest"] != normalized["task"]["sha256"]
    assert checked["subject"]["kind"] == "terminal_wait_baseline_binding"

    checked["subject"]["digest"] = "0" * 64
    _write_json(packet_path, checked)
    normalized["authority_packet"] = _binding(tmp_path, packet_path)
    with pytest.raises(ValueError, match="exact baseline binding"):
        contract.validate_authority_phase(tmp_path, normalized)


def test_authority_subject_is_non_circular_content_addressed_and_fail_closed(
    tmp_path: Path,
) -> None:
    plan = _workspace(tmp_path)
    normalized = contract.normalize_plan(plan)
    identity = contract.validate_authority_subject_binding(tmp_path, normalized)
    subject_path = tmp_path / identity["ref"]
    subject = json.loads(subject_path.read_text(encoding="utf-8"))

    assert set(subject) == contract.AUTHORITY_SUBJECT_KEYS
    assert "authority_packet" not in subject
    assert "pre_commit_verification" not in subject
    subject_preflight(tmp_path, {"subject": identity})
    replay = owner.materialize_terminal_wait_authority_subject(tmp_path, subject)
    assert replay["status"] == "already_materialized"
    assert replay["mutation_performed"] is False
    assert replay["prepare_only"] is True
    assert replay["current_pointer_exposed"] is False
    assert not (tmp_path / ".task/terminal_wait_baseline/current.json").exists()

    subject["expected_current_snapshot_sha256"] = "1" * 64
    _write_json(subject_path, subject)
    with pytest.raises(SystemExit, match="subject changed"):
        subject_preflight(tmp_path, {"subject": identity})
    with pytest.raises(ValueError, match="bound SHA-256"):
        contract.validate_authority_subject_binding(tmp_path, normalized)


def test_authority_subject_rejects_source_binding_drift_without_packet_changes(
    tmp_path: Path,
) -> None:
    plan = _workspace(tmp_path)
    changed = json.loads(json.dumps(plan))
    changed["expected_current_snapshot_sha256"] = "2" * 64
    normalized = contract.normalize_plan(changed)

    with pytest.raises(ValueError, match="does not bind this exact"):
        contract.validate_authority_subject_binding(tmp_path, normalized)


def test_materialize_subject_dry_run_is_non_mutating(tmp_path: Path) -> None:
    plan = _workspace(tmp_path)
    binding = plan["authority_subject"]
    subject_path = tmp_path / binding["ref"]
    subject = json.loads(subject_path.read_text(encoding="utf-8"))
    subject_path.unlink()

    result = owner.materialize_terminal_wait_authority_subject(
        tmp_path, subject, dry_run=True
    )

    assert result["status"] == "dry_run"
    assert result["mutation_performed"] is False
    assert result["authority_subject_binding"] == binding
    assert result["prepare_only"] is True
    assert result["current_pointer_exposed"] is False
    assert not subject_path.exists()


def test_materialize_subject_cli_creates_preflight_ready_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _workspace(tmp_path)
    binding = plan["authority_subject"]
    subject_path = tmp_path / binding["ref"]
    subject = json.loads(subject_path.read_text(encoding="utf-8"))
    subject_path.unlink()
    input_path = _write_json(tmp_path / "authority-subject-input.json", subject)

    code = owner_cli.main(
        [
            "--root",
            str(tmp_path),
            "materialize-subject",
            "--subject",
            input_path.relative_to(tmp_path).as_posix(),
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 0
    assert result["authority_subject_binding"] == binding
    assert result["authority_subject"]["digest"] == binding["sha256"]
    subject_preflight(tmp_path, {"subject": result["authority_subject"]})


def test_new_baseline_publication_requires_verified_premise_contract(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "task.md",
        "# Task\n\n- Status: `completed`\n- Executable: `false`\n",
    )
    raw_packet = build_selection_tick(
        tmp_path,
        wake_predicates=["fresh-exact-subject-or-authority"],
        watched_evidence_classes=["exact_subject", "authority"],
        premise_contract=RAW_PREMISE_CONTRACT,
    )

    with pytest.raises(ValueError, match="verified exact-subject"):
        contract.validate_selection_packet(raw_packet)


def test_legacy_v1_selection_packet_is_historical_only(tmp_path: Path) -> None:
    _write(
        tmp_path / "task.md",
        "# Task\n\n- Status: `completed`\n- Executable: `false`\n",
    )
    packet = build_selection_tick(
        tmp_path,
        wake_predicates=["fresh-exact-subject-or-authority"],
        watched_evidence_classes=["exact_subject", "authority"],
        premise_contract=VERIFIED_PREMISE_CONTRACT,
    )
    packet["format_version"] = 1
    packet["packet_id"] = (
        "selection-tick-"
        + contract.canonical_sha256(
            {key: value for key, value in packet.items() if key != "packet_id"}
        )[:32]
    )

    with pytest.raises(ValueError, match="historical-only"):
        contract.validate_selection_packet(packet)
    projection = contract.validate_selection_packet(packet, allow_legacy_v1=True)
    assert projection["packet_id"] == packet["packet_id"]


def test_current_pointer_cas_rejects_competing_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_a = _workspace(tmp_path, "A")
    plan_b = _workspace(tmp_path, "B")
    _patch_authority(monkeypatch)
    prepared_a = owner.prepare_terminal_wait_baseline(tmp_path, plan_a)
    prepared_b = owner.prepare_terminal_wait_baseline(tmp_path, plan_b)
    owner.activate_terminal_wait_baseline(
        tmp_path, prepared_a["execution_result"], _use_receipt(tmp_path, "A")
    )

    with pytest.raises(ValueError, match="CAS conflict"):
        owner.activate_terminal_wait_baseline(
            tmp_path, prepared_b["execution_result"], _use_receipt(tmp_path, "B")
        )

    assert (
        owner.resolve_terminal_wait_baseline(tmp_path)["binding_id"]
        == prepared_a["binding_id"]
    )


def test_resolve_fails_closed_on_bound_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _workspace(tmp_path)
    _patch_authority(monkeypatch)
    prepared = owner.prepare_terminal_wait_baseline(tmp_path, plan)
    owner.activate_terminal_wait_baseline(
        tmp_path, prepared["execution_result"], _use_receipt(tmp_path)
    )
    _write(
        tmp_path / "task.md",
        "# Drift\n\n- Status: `completed`\n- Executable: `false`\n",
    )

    with pytest.raises(ValueError, match="bound SHA-256"):
        owner.resolve_terminal_wait_baseline(tmp_path)
    audit = owner.audit_terminal_wait_baseline(tmp_path)
    assert audit["status"] == "block"
    assert audit["findings"][0]["code"] == "current_pointer_invalid"


@pytest.mark.parametrize(
    ("value", "match"),
    [
        ({"ref": 7, "sha256": "0" * 64}, "lowercase SHA-256"),
        ({"ref": "artifact.json", "sha256": True}, "lowercase SHA-256"),
        ({"ref": "artifact.json", "sha256": "A" * 64}, "lowercase SHA-256"),
        ({"ref": "../artifact.json", "sha256": "0" * 64}, "normalized"),
        ({"ref": "/artifact.json", "sha256": "0" * 64}, "normalized"),
        ({"ref": "dir\\artifact.json", "sha256": "0" * 64}, "lowercase"),
    ],
)
def test_terminal_binding_rejects_coercion_and_unsafe_refs(
    value: object, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        contract.binding(value, "test binding")


def test_terminal_cli_rejects_absolute_subject_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = _write_json(tmp_path / "subject.json", {"value": "opaque"})

    code = owner_cli.main(
        [
            "--root",
            str(tmp_path),
            "materialize-subject",
            "--subject",
            str(outside),
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 2
    assert result["status"] == "block"
    assert "workspace-relative" in result["error"] or "unsafe" in result["error"]
    assert result["mutation_performed"] is False


def test_terminal_cli_rejects_symlinked_subject_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _write_json(tmp_path / "target.json", {"value": "opaque"})
    link = tmp_path / "subject.json"
    link.symlink_to(target)

    code = owner_cli.main(
        [
            "--root",
            str(tmp_path),
            "materialize-subject",
            "--subject",
            link.relative_to(tmp_path).as_posix(),
        ]
    )
    result = json.loads(capsys.readouterr().out)

    assert code == 2
    assert result["status"] == "block"
    assert "symlink" in result["error"]
    assert result["mutation_performed"] is False


def test_terminal_store_category_scan_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = store.category_dir(tmp_path, "snapshots", create=True)
    monkeypatch.setattr(store, "MAX_CATEGORY_ARTIFACTS", 2)
    for index in range(3):
        _write_json(directory / (f"{index:064x}.json"), {"index": index})

    with pytest.raises(ValueError, match="entry limit"):
        store.scan_category(tmp_path, "snapshots")
