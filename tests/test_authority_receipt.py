from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manage-agent-authority" / "scripts"))
from manage_agent_authority import authority_receipt  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def setup_evidence(root: Path) -> tuple[Path, Path]:
    policy = root / ".agent_goal" / "agent_authority.md"
    source = root / ".task" / "authorization" / "instruction-I.md"
    policy.parent.mkdir(parents=True, exist_ok=True)
    source.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("# Agent Authority\n\nCurrent permissions only.\n", encoding="utf-8")
    source.write_text("# Explicit Instruction\n\n- source_id: instruction-I\n", encoding="utf-8")
    return policy, source


def receipt_body(root: Path) -> dict[str, Any]:
    policy, source = setup_evidence(root)
    return {
        "schema_version": 1,
        "receipt_id": "authr-R",
        "receipt_kind": "operation_authority",
        "operation": "task_pack.normalize_initial_selection",
        "decision": "allowed",
        "basis_temporality": "current_ratification",
        "issued_at": "2026-07-12T12:00:00+09:00",
        "effective_at": "2026-07-12T12:00:00+09:00",
        "subject": {
            "pack_ref": ".task/task_pack/pack-P.json",
            "pack_creation_snapshot_ref": "git:abc:snapshot.json",
            "pack_creation_snapshot_sha256": "a" * 64,
            "initial_item_id": "item-I",
            "initial_order": 1,
            "task_id": "task-T",
            "task_snapshot_ref": ".task/task_pack/task_snapshots/task-T.md",
            "task_snapshot_sha256": "b" * 64,
        },
        "authority_basis": {
            "policy_ref": str(policy.relative_to(root)),
            "policy_sha256": digest(policy),
            "source_kind": "explicit_current_user_instruction",
            "source_id": "instruction-I",
            "source_evidence_ref": str(source.relative_to(root)),
            "source_evidence_sha256": digest(source),
            "integrity_status": "verified",
        },
        "historical_effect": {
            "historical_selection_authority_status": "unverifiable_before_ratification",
            "historical_authority_verdict": "partial",
            "retroactive_claim_allowed": False,
        },
        "allowed_effects": ["append_initial_selection_normalization_provenance"],
        "forbidden_effects": ["change_item_status", "claim_historical_authority_pass"],
    }


def test_current_ratification_receipt_issues_and_validates(tmp_path: Path) -> None:
    body = receipt_body(tmp_path)
    args = argparse.Namespace(
        root=str(tmp_path),
        plan=json.dumps(body),
        output=".task/authority_receipts/authr-R.json",
    )
    assert authority_receipt.command_issue(args) == 0
    path = tmp_path / args.output
    assert path.is_file()
    validate_args = argparse.Namespace(
        root=str(tmp_path),
        receipt=args.output,
        receipt_sha256=digest(path),
        expected_subject_json=json.dumps(body["subject"]),
    )
    assert authority_receipt.command_validate(validate_args) == 0


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda body: body["authority_basis"].update(source_kind="external_advice"), "supported source_kind"),
        (
            lambda body: body["historical_effect"].update(historical_authority_verdict="pass"),
            "historical pass",
        ),
        (
            lambda body: body["historical_effect"].update(retroactive_claim_allowed=True),
            "retroactive authority",
        ),
        (lambda body: body.update(raw_prompt="forbidden"), "forbidden sensitive"),
        (lambda body: body.update(bounded_quote="forbidden"), "forbidden sensitive"),
        (lambda body: body["authority_basis"].update(source_kind="unknown_source"), "supported source_kind"),
        (lambda body: body.update(allowed_effects=["promote_successor"]), "provenance-only"),
    ],
)
def test_current_ratification_rejects_unsafe_claims(tmp_path: Path, mutator: Any, message: str) -> None:
    body = receipt_body(tmp_path)
    mutator(body)
    with pytest.raises(SystemExit, match=message):
        authority_receipt.validate_receipt(tmp_path, body)


def test_receipt_rejects_policy_digest_and_subject_mismatch(tmp_path: Path) -> None:
    body = receipt_body(tmp_path)
    body["authority_basis"]["policy_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="policy SHA-256"):
        authority_receipt.validate_receipt(tmp_path, body)

    body = receipt_body(tmp_path)
    expected = dict(body["subject"])
    expected["initial_item_id"] = "item-X"
    with pytest.raises(SystemExit, match="expected operation subject"):
        authority_receipt.validate_receipt(tmp_path, body, expected)


def test_noncurrent_temporalities_require_verified_source_semantics(tmp_path: Path) -> None:
    body = receipt_body(tmp_path)
    body["basis_temporality"] = "contemporaneous_selection_authority"
    body["authority_basis"]["source_kind"] = "effective_authority_policy"
    body["historical_effect"] = {
        "historical_selection_authority_status": "verified",
        "historical_authority_verdict": "pass",
        "retroactive_claim_allowed": False,
    }
    assert authority_receipt.validate_receipt(tmp_path, body)["status"] == "valid"

    body["basis_temporality"] = "retrospective_evidence_assessment"
    with pytest.raises(SystemExit, match="contemporaneous authority record"):
        authority_receipt.validate_receipt(tmp_path, body)
    body["authority_basis"]["source_kind"] = "contemporaneous_authority_record"
    assert authority_receipt.validate_receipt(tmp_path, body)["status"] == "valid"

    body["operation"] = "task_pack.initial_selection"
    body["allowed_effects"] = ["promote_first_pack_item"]
    with pytest.raises(SystemExit, match="only normalize"):
        authority_receipt.validate_receipt(tmp_path, body)


def test_standalone_temporality_binding_rejects_backdated_ratification(tmp_path: Path) -> None:
    body = receipt_body(tmp_path)
    verified = authority_receipt.validate_receipt(
        tmp_path,
        body,
        selected_at="2026-01-01T00:00:00+09:00",
    )
    assert verified["temporality_binding_status"] == "verified"

    body["issued_at"] = "2025-12-31T23:00:00+09:00"
    body["effective_at"] = "2025-12-31T23:00:00+09:00"
    with pytest.raises(SystemExit, match="after the original selection"):
        authority_receipt.validate_receipt(
            tmp_path,
            body,
            selected_at="2026-01-01T00:00:00+09:00",
        )
