from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import orchestrate_task_cycle.exact_subject_premise_cli as premise_cli
from orchestrate_task_cycle.cli import main as orchestrator_main
from orchestrate_task_cycle.exact_subject_premise import (
    validate_exact_subject_premise_receipt,
)
from orchestrate_task_cycle.exact_subject_premise_cli import main
from orchestrate_task_cycle.exact_subject_premise_v2 import (
    validate_artifact_verified_exact_subject_premise_receipt,
)


def _write_bytes(path: Path, body: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _canonical_sha256(value: object) -> str:
    body = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(body).hexdigest()


def _bound_case(tmp_path: Path) -> tuple[list[str], dict[str, object]]:
    task_path = tmp_path / "task.md"
    task_sha256 = _write_bytes(task_path, b"# terminal task\n")
    baseline_path = tmp_path / "prior-subject.bin"
    baseline_sha256 = _write_bytes(baseline_path, b"prior exact subject")
    subject_path = tmp_path / "current-subject.bin"
    subject_sha256 = _write_bytes(subject_path, b"current exact subject")

    artifacts: dict[str, tuple[Path, str]] = {}
    for evidence_id in ("failure-A", "producer-A", "verifier-A", "replay-A"):
        path = tmp_path / "evidence" / f"{evidence_id}.json"
        digest = _write_bytes(path, f'{{"id":"{evidence_id}"}}'.encode())
        artifacts[evidence_id] = (path, digest)

    binding = {
        "binding_kind": "terminal_task",
        "terminal_task_sha256": task_sha256,
    }
    owner = {
        "owner_id": "owner-A",
        "writable_surface_id": "surface-A",
        "authority_scope_id": "authority-A",
        "writable": True,
    }
    baseline_subject = {
        "subject_id": "subject-A",
        "revision_id": "revision-1",
        "content_sha256": baseline_sha256,
    }
    context = {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_context",
        "current_binding": binding,
        "freshness_baseline": {
            "baseline_id": "baseline-A",
            "subject": baseline_subject,
        },
        "canonical_owner": owner,
        "first_failing_invariant_id": "invariant-A",
    }
    submission = {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_submission",
        "premise_id": "premise-A",
        "binding": binding,
        "freshness_baseline_id": "baseline-A",
        "subject": {
            "subject_id": "subject-A",
            "revision_id": "revision-2",
            "content_sha256": subject_sha256,
        },
        "canonical_owner": owner,
        "first_failing_invariant": {
            "invariant_id": "invariant-A",
            "status": "failing",
            "evidence_id": "failure-A",
            "evidence_sha256": artifacts["failure-A"][1],
        },
        "evidence": {
            "mode": "producer_verifier_replay",
            "producer_receipt_id": "producer-A",
            "producer_receipt_sha256": artifacts["producer-A"][1],
            "producer_subject_sha256": subject_sha256,
            "verifier_receipt_id": "verifier-A",
            "verifier_receipt_sha256": artifacts["verifier-A"][1],
            "verified_subject_sha256": subject_sha256,
            "replay_receipt_id": "replay-A",
            "replay_receipt_sha256": artifacts["replay-A"][1],
            "replayed_subject_sha256": subject_sha256,
        },
    }
    context_path = tmp_path / "context.json"
    submission_path = tmp_path / "submission.json"
    _write_json(context_path, context)
    _write_json(submission_path, submission)
    args = [
        "--root",
        str(tmp_path),
        "--context",
        str(context_path),
        "--submission",
        str(submission_path),
        "--binding-artifact",
        str(task_path),
        "--subject-artifact",
        str(subject_path),
        "--baseline-subject-artifact",
        str(baseline_path),
    ]
    for evidence_id, (path, _) in artifacts.items():
        args.extend(("--evidence-artifact", f"{evidence_id}={path}"))
    return args, submission


def _source_bound_case(tmp_path: Path) -> list[str]:
    args, submission = _bound_case(tmp_path)
    source_path = tmp_path / "source-subject.bin"
    source_sha256 = _write_bytes(source_path, b"source-side exact subject")
    evidence_artifacts: dict[str, tuple[Path, str]] = {}
    for evidence_id in ("source-receipt-A", "current-receipt-A", "comparison-A"):
        path = tmp_path / "evidence" / f"{evidence_id}.json"
        digest = _write_bytes(path, f'{{"id":"{evidence_id}"}}'.encode())
        evidence_artifacts[evidence_id] = (path, digest)
    subject_sha256 = submission["subject"]["content_sha256"]
    submission["evidence"] = {
        "mode": "source_separated_current_body",
        "source_channel_id": "source-channel-A",
        "source_receipt_id": "source-receipt-A",
        "source_receipt_sha256": evidence_artifacts["source-receipt-A"][1],
        "source_revision_id": "source-revision-A",
        "source_content_sha256": source_sha256,
        "current_body_channel_id": "current-channel-A",
        "current_body_receipt_id": "current-receipt-A",
        "current_body_receipt_sha256": evidence_artifacts["current-receipt-A"][1],
        "current_body_revision_id": "revision-2",
        "current_body_content_sha256": subject_sha256,
        "comparison_receipt_id": "comparison-A",
        "comparison_receipt_sha256": evidence_artifacts["comparison-A"][1],
    }
    _write_json(tmp_path / "submission.json", submission)
    args = args[: args.index("--evidence-artifact")]
    args.extend(("--source-subject-artifact", str(source_path)))
    evidence_paths = {
        "failure-A": tmp_path / "evidence/failure-A.json",
        **{key: value[0] for key, value in evidence_artifacts.items()},
    }
    for evidence_id, path in evidence_paths.items():
        args.extend(("--evidence-artifact", f"{evidence_id}={path}"))
    return args


def test_cli_emits_direct_consumed_receipt_from_all_bound_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, _ = _bound_case(tmp_path)

    assert main(args) == 0
    serialized = capsys.readouterr().out
    receipt = json.loads(serialized)

    assert receipt["status"] == "consumed"
    assert receipt["schema_version"] == 2
    assert validate_artifact_verified_exact_subject_premise_receipt(receipt) == receipt
    assert "current exact subject" not in serialized
    assert str(tmp_path) not in serialized
    assert receipt["source_body_persisted"] is False
    assert receipt["source_path_persisted"] is False


def test_cli_verifies_complete_source_separated_artifact_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _source_bound_case(tmp_path)

    assert main(args) == 0
    serialized = capsys.readouterr().out
    receipt = json.loads(serialized)
    verified = validate_artifact_verified_exact_subject_premise_receipt(receipt)

    attestation = verified["artifact_verification"]
    assert attestation["source_subject"]["source_identity"] == "source-channel-A"
    assert [row["role"] for row in attestation["evidence_receipts"]] == [
        "source",
        "current_body",
        "comparison",
    ]
    assert "source-side exact subject" not in serialized
    assert str(tmp_path) not in serialized


def test_cli_binds_selection_baseline_canonical_and_raw_digests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, submission = _bound_case(tmp_path)
    baseline = {
        "z_field": "last-in-source-order",
        "artifact_kind": "selection_tick",
        "packet_id": "selection-tick-" + "1" * 32,
    }
    baseline_path = tmp_path / "selection-baseline.json"
    _write_json(baseline_path, baseline)
    binding = {
        "binding_kind": "selection_baseline",
        "selection_baseline_id": baseline["packet_id"],
        "selection_baseline_sha256": _canonical_sha256(baseline),
    }
    context = json.loads((tmp_path / "context.json").read_text(encoding="utf-8"))
    context["current_binding"] = binding
    submission["binding"] = binding
    _write_json(tmp_path / "context.json", context)
    _write_json(tmp_path / "submission.json", submission)
    args[args.index("--binding-artifact") + 1] = str(baseline_path)

    assert main(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    artifact = receipt["artifact_verification"]["current_binding_artifact"]

    assert artifact["digest_mode"] == "canonical_json_sha256"
    assert artifact["binding_sha256"] == _canonical_sha256(baseline)
    assert (
        artifact["raw_sha256"] == hashlib.sha256(baseline_path.read_bytes()).hexdigest()
    )
    assert validate_artifact_verified_exact_subject_premise_receipt(receipt) == receipt


def test_cli_rejected_receipt_is_closed_and_drops_body_and_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, submission = _bound_case(tmp_path)
    submission["source_body"] = "sensitive-source-body"
    submission["source_path"] = "/sensitive/source/path"
    _write_json(tmp_path / "submission.json", submission)

    assert main(args[:6]) == 0
    serialized = capsys.readouterr().out
    receipt = json.loads(serialized)

    assert receipt["status"] == "rejected"
    assert receipt["reason_code"] == "submission_schema_invalid"
    assert "sensitive-source-body" not in serialized
    assert "/sensitive/source/path" not in serialized
    assert validate_exact_subject_premise_receipt(receipt) == receipt


def test_cli_exact_replay_reemits_same_immutable_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, _ = _bound_case(tmp_path)
    assert main(args) == 0
    first = json.loads(capsys.readouterr().out)
    prior_path = tmp_path / "prior-receipt.json"
    _write_json(prior_path, first)

    assert main([*args, "--prior-receipt", str(prior_path)]) == 0
    replay = json.loads(capsys.readouterr().out)

    assert replay == first
    assert (
        replay["legacy_receipt"]["replay_identity_sha256"]
        == first["legacy_receipt"]["replay_identity_sha256"]
    )

    legacy_path = tmp_path / "legacy-prior-receipt.json"
    _write_json(legacy_path, first["legacy_receipt"])
    assert main([*args, "--prior-receipt", str(legacy_path)]) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["reason_code"] == "consumed_prior_requires_artifact_verified_v2"


def test_cli_fails_closed_on_unbound_or_unverifiable_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, submission = _bound_case(tmp_path)
    evidence_path = tmp_path / "evidence" / "producer-A.json"
    evidence_path.write_bytes(b"tampered")

    assert main(args) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["reason_code"] == "evidence_artifact_digest_mismatch"
    assert str(evidence_path) not in json.dumps(blocked)

    _, submission = _bound_case(tmp_path)
    subject_sha256 = submission["subject"]["content_sha256"]
    submission["evidence"] = {
        "mode": "source_separated_current_body",
        "source_channel_id": "source-channel-A",
        "source_receipt_id": "source-receipt-A",
        "source_revision_id": "source-revision-A",
        "source_content_sha256": "9" * 64,
        "current_body_channel_id": "current-channel-A",
        "current_body_receipt_id": "current-receipt-A",
        "current_body_revision_id": "revision-2",
        "current_body_content_sha256": subject_sha256,
        "comparison_receipt_id": "comparison-A",
        "comparison_receipt_sha256": "a" * 64,
    }
    _write_json(tmp_path / "submission.json", submission)

    assert main(args) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["reason_code"] == "evidence_mode_not_artifact_verifiable"
    assert blocked["source_body_persisted"] is False
    assert blocked["source_path_persisted"] is False


def test_cli_rejects_outside_parent_and_symlink_inputs_without_path_leak(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args, _ = _bound_case(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    _write_json(outside, {"outside": True})

    outside_args = [*args]
    outside_args[outside_args.index("--context") + 1] = str(outside)
    assert main(outside_args) == 2
    serialized = capsys.readouterr().out
    assert json.loads(serialized)["reason_code"] == "workspace_path_invalid"
    assert str(outside) not in serialized

    parent_args = [*args]
    parent_args[parent_args.index("--context") + 1] = f"../{outside.name}"
    assert main(parent_args) == 2
    assert json.loads(capsys.readouterr().out)["reason_code"] == (
        "workspace_path_invalid"
    )

    link = tmp_path / "context-link.json"
    link.symlink_to(outside)
    link_args = [*args]
    link_args[link_args.index("--context") + 1] = "context-link.json"
    assert main(link_args) == 2
    serialized = capsys.readouterr().out
    assert json.loads(serialized)["reason_code"] == "context_input_unreadable"
    assert str(outside) not in serialized


def test_cli_bounds_streamed_subject_and_evidence_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _ = _bound_case(tmp_path)
    monkeypatch.setattr(premise_cli, "MAX_ARTIFACT_BYTES", 18)

    assert main(args) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["reason_code"] == "subject_artifact_unreadable"
    assert blocked["source_body_persisted"] is False
    assert blocked["source_path_persisted"] is False


def test_cli_bounds_serialized_inputs_before_json_decode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    args, _ = _bound_case(tmp_path)
    monkeypatch.setattr(premise_cli, "MAX_SERIALIZED_INPUT_BYTES", 18)

    assert main(args) == 2
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["reason_code"] == "context_input_unreadable"
    assert blocked["source_body_persisted"] is False
    assert blocked["source_path_persisted"] is False


def test_public_command_help_exposes_closed_artifact_binding_interface(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert orchestrator_main(["--help"]) == 0
    assert "exact-subject-premise" in capsys.readouterr().out

    with pytest.raises(SystemExit) as raised:
        orchestrator_main(["exact-subject-premise", "--help"])
    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    assert "--binding-artifact" in help_text
    assert "--root" in help_text
    assert "--subject-artifact" in help_text
    assert "--source-subject-artifact" in help_text
    assert "--evidence-artifact" in help_text
