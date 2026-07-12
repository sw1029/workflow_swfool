from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


task_pack_queue = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "task_pack_queue.py",
    "task_pack_queue_promotion",
)


def pack_item(item_id: str, order: int) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "order": order,
        "status": "planned",
        "title": item_id,
        "objective": "Perform bounded work.",
        "validation_profile": "current_only",
        "progress_target": "advanced",
    }


def write_pack(root: Path) -> Path:
    path = root / ".task" / "task_pack" / "pack-1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pack_id": "pack-1",
                "status": "active",
                "goal": "Test deterministic promotion.",
                "current_item_id": "item-1",
                "items": [pack_item("item-1", 1), pack_item("item-2", 2)],
                "mutation_log": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def replacement_fixture(root: Path) -> tuple[Path, dict[str, Any]]:
    old_path = root / ".task" / "task_pack" / "pack-old.json"
    old_items = [pack_item(f"tail-{index}", index) for index in range(1, 5)]
    old = {
        "schema_version": 1,
        "pack_id": "pack-old",
        "status": "active",
        "language": "ko",
        "goal": "Preserve the existing successor tail.",
        "current_item_id": "tail-1",
        "items": old_items,
        "mutation_log": [],
        "terminal_blocker": None,
    }
    write_json(old_path, old)
    new_items = [
        {
            **pack_item("repair-a", 1),
            "progress_kind_expected": "governance_only",
            "item_kind": "workflow_capability",
        },
        {
            **pack_item("repair-b", 2),
            "progress_kind_expected": "governance_only",
            "item_kind": "workflow_capability",
        },
        {
            **pack_item("ratify", 3),
            "progress_kind_expected": "governance_only",
            "item_kind": "artifact_truth_ratification",
        },
    ]
    for order, item in enumerate(old_items, start=4):
        carried = json.loads(json.dumps(item))
        carried["order"] = order
        new_items.append(carried)
    successor = {
        "schema_version": 1,
        "pack_id": "pack-successor",
        "status": "active",
        "language": "ko",
        "goal": "Repair workflow capability, ratify truth, then resume the preserved tail.",
        "current_item_id": "repair-a",
        "created_at": "2026-07-12T22:00:00+09:00",
        "updated_at": "2026-07-12T22:00:00+09:00",
        "items": new_items,
        "mutation_log": [],
        "terminal_blocker": None,
        "replacement_contract": {
            "schema_version": 1,
            "predecessor_pack_ref": ".task/task_pack/pack-old.json",
            "predecessor_pack_file_sha256": sha256(old_path),
            "predecessor_pack_canonical_sha256": task_pack_queue.canonical_pack_sha256(old),
            "new_item_ids": ["repair-a", "repair-b", "ratify"],
            "carried_forward_item_ids": ["tail-1", "tail-2", "tail-3", "tail-4"],
        },
    }
    before_ids = [item["item_id"] for item in old_items]
    plan = {
        "action": "replace_pack",
        "actor": "$task-doctor",
        "reason": "insert bounded repair prerequisites while preserving the successor tail",
        "evidence_paths": [],
        "pack_path": ".task/task_pack/pack-old.json",
        "pack_coherence": {
            "schema_version": 1,
            "canonical_pack_ref": ".task/task_pack/pack-old.json",
            "before_pack_sha256": task_pack_queue.canonical_pack_sha256(old),
            "declared_before_item_ids": before_ids,
            "declared_before_order": before_ids,
            "declared_current_item": "tail-1",
            "mutation_kind": "replace",
            "proposed_after_item_ids": before_ids,
            "proposed_after_order": before_ids,
        },
        "pack": successor,
    }
    return old_path, plan


def mutation_args(root: Path, plan: dict[str, Any]) -> argparse.Namespace:
    return argparse.Namespace(
        root=str(root),
        plan=json.dumps(plan),
        action=None,
        pack=None,
        language="ko",
        render=False,
    )


def replacement_transaction_id(root: Path, plan: dict[str, Any]) -> str:
    fingerprint = task_pack_queue.replacement_plan_fingerprint(plan)
    transaction_ids = (
        task_pack_queue.task_pack_replacement.pending_transaction_ids_for_plan(root, fingerprint)
        + task_pack_queue.task_pack_replacement.completed_transaction_ids_for_plan(root, fingerprint)
    )
    assert len(transaction_ids) == 1
    return transaction_ids[0]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def write_creation_snapshot(root: Path, pack_path: Path, data: dict[str, Any], *, state: str = "pre_selection") -> dict[str, Any]:
    payload = (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    file_digest = hashlib.sha256(payload).hexdigest()
    snapshot = root / ".task" / "task_pack" / "creation_snapshots" / f"pack-1-{file_digest[:16]}.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(payload)
    return {
        "pack_creation_snapshot_kind": "workspace_file",
        "pack_creation_snapshot_ref": str(snapshot.relative_to(root)),
        "pack_creation_snapshot_sha256": file_digest,
        "pack_creation_canonical_sha256": task_pack_queue.canonical_pack_sha256(data),
        "pack_creation_canonicalization_version": 1,
        "creation_snapshot_state": state,
    }


def write_authority_receipt(
    root: Path,
    subject: dict[str, Any],
    *,
    operation: str,
    temporality: str,
    selected_at: str,
    receipt_id: str,
) -> tuple[str, str]:
    policy = root / ".agent_goal" / "agent_authority.md"
    source = root / ".task" / "authorization" / f"{receipt_id}.md"
    policy.parent.mkdir(parents=True, exist_ok=True)
    source.parent.mkdir(parents=True, exist_ok=True)
    if not policy.exists():
        policy.write_text("# Agent Authority\n\nCurrent permissions only.\n", encoding="utf-8")
    source.write_text(f"# Explicit Authority Evidence\n\n- source_id: {receipt_id}\n", encoding="utf-8")
    current_ratification = temporality == "current_ratification"
    receipt = {
        "schema_version": 1,
        "receipt_id": receipt_id,
        "receipt_kind": "operation_authority",
        "operation": operation,
        "decision": "allowed",
        "basis_temporality": temporality,
        "issued_at": "2026-07-12T12:00:00+09:00" if current_ratification else "2025-12-31T23:59:00+00:00",
        "effective_at": "2026-07-12T12:00:00+09:00" if current_ratification else "2025-12-31T23:59:00+00:00",
        "subject": subject,
        "authority_basis": {
            "policy_ref": str(policy.relative_to(root)),
            "policy_sha256": sha256(policy),
            "source_kind": "explicit_current_user_instruction",
            "source_id": receipt_id,
            "source_evidence_ref": str(source.relative_to(root)),
            "source_evidence_sha256": sha256(source),
            "integrity_status": "verified",
        },
        "historical_effect": {
            "historical_selection_authority_status": (
                "unverifiable_before_ratification" if current_ratification else "verified"
            ),
            "historical_authority_verdict": "partial" if current_ratification else "pass",
            "retroactive_claim_allowed": False,
        },
        "allowed_effects": [
            "append_initial_selection_normalization_provenance"
            if operation == "task_pack.normalize_initial_selection"
            else "promote_first_pack_item"
        ],
        "forbidden_effects": ["change_item_status", "claim_historical_authority_pass"],
    }
    path = root / ".task" / "authority_receipts" / f"{receipt_id}.json"
    write_json(path, receipt)
    return str(path.relative_to(root)), sha256(path)


def initial_selection_plan(root: Path, pack_path: Path) -> dict[str, Any]:
    data = json.loads(pack_path.read_text(encoding="utf-8"))
    creation = write_creation_snapshot(root, pack_path, data)
    task_path = root / "task.md"
    task_digest = sha256(task_path)
    task_snapshot = (
        root
        / ".task"
        / "task_pack"
        / "task_snapshots"
        / "pack-1"
        / f"item-1-task-1-{task_digest[:16]}.md"
    )
    subject = {
        "pack_ref": str(pack_path.relative_to(root)),
        "pack_creation_snapshot_ref": creation["pack_creation_snapshot_ref"],
        "pack_creation_snapshot_sha256": creation["pack_creation_snapshot_sha256"],
        "initial_item_id": "item-1",
        "initial_order": 1,
        "task_id": "task-1",
        "task_snapshot_ref": str(task_snapshot.relative_to(root)),
        "task_snapshot_sha256": task_digest,
    }
    authority_ref, authority_sha = write_authority_receipt(
        root,
        subject,
        operation="task_pack.initial_selection",
        temporality="contemporaneous_selection_authority",
        selected_at="2026-01-01T00:00:00+00:00",
        receipt_id="authr-initial",
    )
    return {
        "pack_disposition": "promote_next_item",
        "pack_path": str(pack_path.relative_to(root)),
        "item_id": "item-1",
        "task_id": "task-1",
        "task_path": "task.md",
        "promotion_origin": "bootstrap_initial_selection",
        "reason": "initial selection",
        "initial_selection_receipt": {
            "schema_version": 1,
            "pack_ref": str(pack_path.relative_to(root)),
            **creation,
            "initial_item_id": "item-1",
            "initial_order": 1,
            "task_id": "task-1",
            "task_snapshot_ref": str(task_snapshot.relative_to(root)),
            "task_snapshot_sha256": task_digest,
            "authority_receipt_ref": authority_ref,
            "authority_receipt_sha256": authority_sha,
            "authority_mode": "contemporaneous_selection_authority",
            "historical_selection_authority_status": "verified",
            "selection_reason": "initial item",
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        "pack_coherence": current_pack_coherence(root, "promote"),
    }


def authoritative_provenance(
    root: Path,
    *,
    validated_task_id: str = "task-1",
    validation_verdict: str = "complete",
    execution_status: str = "completed",
) -> dict[str, Any]:
    evidence_dir = root / ".task" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for name in ("run.log", "validation.log", "issue.log", "derive.json"):
        (evidence_dir / name).write_text(f"evidence: {name}\n", encoding="utf-8")

    run_path = root / ".task" / "run" / f"{validated_task_id}.json"
    write_json(
        run_path,
        {
            "format_version": 1,
            "step": "run",
            "task_id": validated_task_id,
            "execution_status": execution_status,
            "blockers": [],
            "evidence_paths": [".task/evidence/run.log"],
        },
    )
    validation_path = root / ".task" / "validation" / f"{validated_task_id}.json"
    write_json(
        validation_path,
        {
            "format_version": 1,
            "step": "validate",
            "task_id": validated_task_id,
            "validation_verdict": validation_verdict,
            "progress_verdict": "advanced",
            "blockers": [],
            "evidence_paths": [".task/evidence/validation.log"],
        },
    )
    issue_path = root / ".task" / "issue" / f"{validated_task_id}.json"
    write_json(
        issue_path,
        {
            "format_version": 1,
            "step": "issue",
            "task_id": validated_task_id,
            "issue_packet_id": f"issue-{validated_task_id}",
            "issue_status": "not_applicable",
            "issue_ids": [],
            "issue_skipped_reason": "validation found no implementation issue",
            "issue_provenance": {
                "source_task_id": validated_task_id,
                "validation_report_path": str(validation_path.relative_to(root)),
            },
            "blockers": [],
            "evidence_paths": [".task/evidence/issue.log"],
        },
    )
    return {
        "validated_task_id": validated_task_id,
        "validation_verdict": validation_verdict,
        "run_report_path": str(run_path.relative_to(root)),
        "run_report_sha256": sha256(run_path),
        "validation_report_path": str(validation_path.relative_to(root)),
        "validation_report_sha256": sha256(validation_path),
        "validation_evidence_paths": [
            str(validation_path.relative_to(root)),
            ".task/evidence/validation.log",
        ],
        "issue_packet_path": str(issue_path.relative_to(root)),
        "issue_packet_sha256": sha256(issue_path),
        "evidence_paths": [".task/evidence/derive.json"],
    }


def promotion_plan(root: Path, **overrides: Any) -> dict[str, Any]:
    plan = {
        "pack_disposition": "promote_next_item",
        "pack_path": ".task/task_pack/pack-1.json",
        "item_id": "item-1",
        "task_id": "task-2",
        "task_path": "task.md",
        "reason": "authoritative validation selected the next bounded item",
        **authoritative_provenance(root),
    }
    plan.update(overrides)
    plan["pack_coherence"] = current_pack_coherence(root, "promote")
    return plan


def current_pack_coherence(root: Path, mutation_kind: str) -> dict[str, Any]:
    pack_path = root / ".task" / "task_pack" / "pack-1.json"
    data = json.loads(pack_path.read_text(encoding="utf-8"))
    snapshot = task_pack_queue.pack_snapshot(root, pack_path, data)
    return {
        "schema_version": 1,
        "canonical_pack_ref": str(pack_path.relative_to(root)),
        "before_pack_sha256": snapshot["canonical_pack_sha256"],
        "declared_before_item_ids": snapshot["item_ids"],
        "declared_before_order": snapshot["item_order"],
        "declared_current_item": snapshot["current_item"],
        "mutation_kind": mutation_kind,
        "proposed_after_item_ids": snapshot["item_ids"],
        "proposed_after_order": snapshot["item_order"],
    }


def passing_verdict_axes() -> dict[str, Any]:
    evidence_ref = ".task/evidence/validation.log"
    return {
        "verdict_contract_version": 1,
        "task_acceptance_verdict": {"status": "pass", "evidence_ref": evidence_ref},
        "artifact_truth_verdict": {"status": "pass", "evidence_ref": evidence_ref},
        "artifact_semantic_verdict": {"status": "pass", "evidence_ref": evidence_ref},
        "pack_transition_verdict": {"status": "not_applicable"},
        "historical_index_verdict": {"status": "not_applicable"},
        "goal_readiness_verdict": {"status": "not_applicable"},
    }


def consume_cli(root: Path, provenance: dict[str, Any], *, task_id: str = "task-2") -> int:
    argv = [
        "--root",
        str(root),
        "mark-consumed",
        "--pack",
        ".task/task_pack/pack-1.json",
        "--item-id",
        "item-1",
        "--task-id",
        task_id,
        "--validation-verdict",
        str(provenance["validation_verdict"]),
        "--run-report-path",
        str(provenance["run_report_path"]),
        "--run-report-sha256",
        str(provenance["run_report_sha256"]),
        "--validation-report-path",
        str(provenance["validation_report_path"]),
        "--validation-report-sha256",
        str(provenance["validation_report_sha256"]),
        "--issue-packet-path",
        str(provenance["issue_packet_path"]),
        "--issue-packet-sha256",
        str(provenance["issue_packet_sha256"]),
        "--completion-evidence-path",
        ".task/evidence/derive.json",
        "--pack-coherence-json",
        json.dumps(current_pack_coherence(root, "mark_consumed"), sort_keys=True),
        "--verdict-axes-json",
        json.dumps(passing_verdict_axes(), sort_keys=True),
    ]
    for path in provenance["validation_evidence_paths"]:
        argv.extend(["--validation-evidence-path", str(path)])
    return task_pack_queue.main(argv)


def test_promotion_requires_authoritative_validation_provenance(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = {
        "pack_disposition": "promote_next_item",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_id": "item-1",
        "task_id": "task-2",
        "task_path": "task.md",
        "reason": "validated predecessor",
        "evidence_paths": ["derive.json"],
        "pack_coherence": current_pack_coherence(tmp_path, "promote"),
    }

    with pytest.raises(SystemExit, match="validated_task_id"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_promotion_is_recorded_after_validation_and_advances_queue(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)

    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    first = pack["items"][0]
    assert first["status"] == "promoted"
    assert first["promotion"]["validated_task_id"] == "task-1"
    assert first["promotion"]["validation_verdict"] == "complete"
    assert first["promotion"]["execution_status"] == "completed"
    assert first["promotion"]["issue_status"] == "not_applicable"
    assert first["promotion"]["validation_report_sha256"] == plan["validation_report_sha256"]
    assert (tmp_path / first["promotion"]["task_snapshot_path"]).is_file()
    assert pack["current_item_id"] == "item-2"
    assert pack["status"] == "active"


def test_promotion_rejects_partial_validation(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path, validation_verdict="partial")

    with pytest.raises(SystemExit, match="validation_verdict must"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_promotion_rejects_pending_long_run(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    run_path = tmp_path / plan["run_report_path"]
    run_packet = json.loads(run_path.read_text(encoding="utf-8"))
    run_packet.update({"execution_status": "running", "long_run_branch": True, "long_run_role": "monitor"})
    write_json(run_path, run_packet)
    plan["run_report_sha256"] = sha256(run_path)

    with pytest.raises(SystemExit, match="terminal run report"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_promotion_rejects_run_blockers(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    run_path = tmp_path / plan["run_report_path"]
    run_packet = json.loads(run_path.read_text(encoding="utf-8"))
    run_packet["blockers"] = ["run blocker"]
    write_json(run_path, run_packet)
    plan["run_report_sha256"] = sha256(run_path)

    with pytest.raises(SystemExit, match="empty blockers"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_promotion_rejects_blocked_result_contract_envelope(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    validation_path = tmp_path / plan["validation_report_path"]
    raw = json.loads(validation_path.read_text(encoding="utf-8"))
    write_json(
        validation_path,
        {
            "status": "block",
            "findings": [{"severity": "block", "code": "real_failure"}],
            "result": raw,
        },
    )
    plan["validation_report_sha256"] = sha256(validation_path)

    with pytest.raises(SystemExit, match="envelope must have status"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_promotion_rejects_tampered_validation_packet(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    validation_path = tmp_path / plan["validation_report_path"]
    validation_path.write_text(validation_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(SystemExit, match="SHA-256 does not match"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_pack_validation_rejects_manual_promotion_without_provenance(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["items"][0]["status"] = "promoted"
    pack["items"][0]["promotion"] = {"task_id": "task-2", "task_path": "task.md"}

    findings = task_pack_queue.validate_pack(pack, pack_path)

    assert "promotion_provenance_incomplete" in {finding["code"] for finding in findings}


def test_pack_validation_rechecks_bound_promotion_artifacts(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    validation_path = tmp_path / plan["validation_report_path"]
    validation_path.write_text(validation_path.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    findings = task_pack_queue.validate_pack(pack, pack_path)

    assert "promotion_provenance_invalid" in {finding["code"] for finding in findings}


def test_pack_validation_detects_promoted_task_drift(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    (tmp_path / "task.md").write_text("# unrelated replacement\n", encoding="utf-8")

    findings = task_pack_queue.validate_pack(json.loads(pack_path.read_text(encoding="utf-8")), pack_path)

    assert "promotion_provenance_invalid" in {finding["code"] for finding in findings}


def test_second_promotion_waits_for_in_flight_item_consumption(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, promotion_plan(tmp_path))) == 0
    (tmp_path / "task.md").write_text("# task-3\n", encoding="utf-8")
    second = promotion_plan(tmp_path, item_id="item-2", task_id="task-3")

    with pytest.raises(SystemExit, match="in-flight item"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, second))


def test_consumption_is_hash_bound_and_allows_next_task_snapshot(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, promotion_plan(tmp_path))) == 0
    task_2_completion = authoritative_provenance(tmp_path, validated_task_id="task-2")
    assert consume_cli(tmp_path, task_2_completion) == 0

    (tmp_path / "task.md").write_text("# task-3\n", encoding="utf-8")
    second = {
        "pack_disposition": "promote_next_item",
        "pack_path": ".task/task_pack/pack-1.json",
        "item_id": "item-2",
        "task_id": "task-3",
        "task_path": "task.md",
        "reason": "task-2 completion selected item-2",
        **task_2_completion,
    }
    second["pack_coherence"] = current_pack_coherence(tmp_path, "promote")
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, second)) == 0

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    assert [item["status"] for item in pack["items"]] == ["consumed", "promoted"]
    assert not [finding for finding in task_pack_queue.validate_pack(pack, pack_path) if finding["severity"] == "block"]


def test_promotion_cannot_skip_the_current_queue_item(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-3\n", encoding="utf-8")
    plan = promotion_plan(tmp_path, item_id="item-2", task_id="task-3", reason="attempted out-of-order promotion")

    with pytest.raises(SystemExit, match="current next item"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_create_rejects_traversal_pack_id(tmp_path: Path) -> None:
    plan = {
        "action": "create_pack",
        "pack_id": "../escaped",
        "goal": "must not escape",
        "items": [pack_item("item-1", 1)],
        "reason": "path boundary regression",
        "evidence_paths": ["task.md"],
    }
    with pytest.raises(SystemExit, match="path-safe"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_task_pack_capabilities_keep_progress_and_item_kind_orthogonal() -> None:
    contract = task_pack_queue.capability_contract()
    assert "workflow_capability" not in contract["canonical_progress_kinds"]
    assert "artifact_truth_only" not in contract["canonical_progress_targets"]
    assert contract["item_kind"]["vocabulary"] == "open"
    assert contract["publication"]["replacement_recovery"] == "fail_closed_forward_complete"


def test_create_requires_clean_findings_and_no_active_predecessor(tmp_path: Path) -> None:
    invalid = {
        "action": "create_pack",
        "reason": "invalid publication must fail closed",
        "pack": {
            "schema_version": 1,
            "pack_id": "pack-invalid",
            "status": "active",
            "goal": "invalid",
            "current_item_id": "item-1",
            "items": [
                {**pack_item("item-1", 1), "progress_target": "artifact_truth_only"},
                pack_item("item-2", 2),
            ],
            "mutation_log": [],
        },
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, invalid)) == 2
    assert not (tmp_path / ".task" / "task_pack" / "pack-invalid.json").exists()
    assert not (tmp_path / ".task" / "task_pack" / "creation_snapshots").exists()

    write_pack(tmp_path)
    valid = json.loads(json.dumps(invalid))
    valid["pack"]["pack_id"] = "pack-second"
    valid["pack"]["items"][0]["progress_target"] = "advanced"
    with pytest.raises(SystemExit, match="requires no active task pack"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, valid))


def test_create_dry_run_leaves_no_task_pack_or_lock_residue(tmp_path: Path) -> None:
    plan = {
        "action": "create_pack",
        "reason": "zero-residue publication preflight",
        "pack": {
            "schema_version": 1,
            "pack_id": "pack-clean-dry-run",
            "status": "active",
            "goal": "bounded create",
            "current_item_id": "item-1",
            "items": [pack_item("item-1", 1), pack_item("item-2", 2)],
            "mutation_log": [],
        },
    }
    args = mutation_args(tmp_path, plan)
    args.dry_run = True
    assert task_pack_queue.command_apply_mutation(args) == 0
    assert not (tmp_path / ".task").exists()


@pytest.mark.parametrize("item_count", [1, 6])
def test_create_enforces_new_sequence_bound_without_durable_evidence(
    tmp_path: Path, item_count: int
) -> None:
    plan = {
        "action": "create_pack",
        "reason": "ordinary new sequences are bounded",
        "pack": {
            "schema_version": 1,
            "pack_id": f"pack-{item_count}",
            "status": "active",
            "goal": "bounded create",
            "current_item_id": "item-1",
            "items": [pack_item(f"item-{index}", index) for index in range(1, item_count + 1)],
            "mutation_log": [],
        },
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 2
    assert not (tmp_path / ".task" / "task_pack" / f"pack-{item_count}.json").exists()
    assert not (tmp_path / ".task" / "task_pack" / "creation_snapshots").exists()


def test_create_rejects_invalid_item_kind_without_expanding_progress_enums(tmp_path: Path) -> None:
    plan = {
        "action": "create_pack",
        "reason": "item kind remains an open bounded token",
        "pack": {
            "schema_version": 1,
            "pack_id": "pack-invalid-kind",
            "status": "active",
            "goal": "bounded subtype",
            "current_item_id": "item-1",
            "items": [
                {**pack_item("item-1", 1), "item_kind": "workflow capability"},
                pack_item("item-2", 2),
            ],
            "mutation_log": [],
        },
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 2
    assert not (tmp_path / ".task" / "task_pack" / "pack-invalid-kind.json").exists()


def test_replace_pack_dry_run_is_clean_and_preserves_seven_item_tail(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    before = old_path.read_bytes()
    args = mutation_args(tmp_path, plan)
    args.dry_run = True
    assert task_pack_queue.command_apply_mutation(args) == 0
    assert old_path.read_bytes() == before
    assert not (tmp_path / ".task" / "task_pack" / "pack-successor.json").exists()
    assert not (tmp_path / ".task" / "task_pack" / "replacement_transactions").exists()
    assert not (tmp_path / ".task" / "task_pack" / "creation_snapshots").exists()
    assert not (tmp_path / ".task" / "task_pack" / ".pack-mutation.lock").exists()


def test_replace_pack_render_preflight_handles_missing_predecessor_and_rejects_successor_collision(
    tmp_path: Path,
) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    before = old_path.read_bytes()
    args = mutation_args(tmp_path, plan)
    args.dry_run = True
    args.render = True
    assert task_pack_queue.command_apply_mutation(args) == 0
    assert old_path.read_bytes() == before
    assert not old_path.with_suffix(".md").exists()

    successor_render = tmp_path / ".task" / "task_pack" / "pack-successor.md"
    successor_render.write_text("stale orphan render\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="render path must be absent"):
        task_pack_queue.command_apply_mutation(args)
    assert old_path.read_bytes() == before
    assert successor_render.read_text(encoding="utf-8") == "stale orphan render\n"
    assert not (tmp_path / ".task" / "task_pack" / "creation_snapshots").exists()


def test_replace_pack_rejects_body_bearing_plan_snapshot_fields(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    plan["raw_prompt"] = "must not be persisted in helper-owned evidence"
    before = old_path.read_bytes()
    args = mutation_args(tmp_path, plan)
    args.dry_run = True

    with pytest.raises(SystemExit, match="body-safe"):
        task_pack_queue.command_apply_mutation(args)
    assert old_path.read_bytes() == before
    assert not (tmp_path / ".task" / "task_pack" / "replacement_plan_snapshots").exists()


def test_replace_pack_commits_once_and_exact_replay_is_noop(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    successor_path = tmp_path / ".task" / "task_pack" / "pack-successor.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    successor = json.loads(successor_path.read_text(encoding="utf-8"))
    assert old["status"] == "superseded"
    assert successor["status"] == "active"
    assert len(successor["items"]) == 7
    assert [path.name for path, _data in task_pack_queue.active_pack_candidates(tmp_path)] == ["pack-successor.json"]
    before_old = old_path.read_bytes()
    before_successor = successor_path.read_bytes()
    transaction_id = replacement_transaction_id(tmp_path, plan)
    prepare_path = task_pack_queue.task_pack_replacement.prepare_path(tmp_path, transaction_id)
    receipt_path = task_pack_queue.task_pack_replacement.completion_path(tmp_path, transaction_id)
    before_prepare = prepare_path.read_bytes()
    before_receipt = receipt_path.read_bytes()
    before_transaction_files = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in (tmp_path / ".task" / "task_pack").rglob("*")
        if path.is_file()
    )
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    assert old_path.read_bytes() == before_old
    assert successor_path.read_bytes() == before_successor
    assert prepare_path.read_bytes() == before_prepare
    assert receipt_path.read_bytes() == before_receipt
    assert sorted(
        path.relative_to(tmp_path).as_posix()
        for path in (tmp_path / ".task" / "task_pack").rglob("*")
        if path.is_file()
    ) == before_transaction_files


def test_completed_replacement_does_not_become_pending_after_later_valid_pack_update(tmp_path: Path) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    successor_path = tmp_path / ".task" / "task_pack" / "pack-successor.json"
    successor = json.loads(successor_path.read_text(encoding="utf-8"))
    successor["updated_at"] = "2026-07-12T23:00:00+09:00"
    write_json(successor_path, successor)

    assert task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path) == []
    assert task_pack_queue.task_pack_store_findings(tmp_path) == []


@pytest.mark.parametrize("tampered_field", ["after_payload_b64", "after_sha256"])
def test_replace_pack_recovery_rejects_tampered_prepare_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tampered_field: str,
) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    original_publish = task_pack_queue.task_pack_replacement.publish_transaction

    def stop_after_prepare(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise OSError("stop after durable prepare")

    monkeypatch.setattr(task_pack_queue.task_pack_replacement, "publish_transaction", stop_after_prepare)
    with pytest.raises(OSError, match="stop after durable prepare"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))

    transaction_id = replacement_transaction_id(tmp_path, plan)
    prepare_path = task_pack_queue.task_pack_replacement.prepare_path(tmp_path, transaction_id)
    prepare = json.loads(prepare_path.read_text(encoding="utf-8"))
    target = next(item for item in prepare["targets"] if item["role"] == "successor_pack")
    if tampered_field == "after_payload_b64":
        target[tampered_field] = base64.b64encode(b"tampered successor payload").decode("ascii")
    else:
        target[tampered_field] = "0" * 64
    write_json(prepare_path, prepare)

    monkeypatch.setattr(task_pack_queue.task_pack_replacement, "publish_transaction", original_publish)
    with pytest.raises(SystemExit, match="payload digest is inconsistent"):
        task_pack_queue.command_recover_replacement(argparse.Namespace(root=str(tmp_path)))


def test_replace_pack_recovery_rejects_coherently_rehashed_prepare_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    original_publish = task_pack_queue.task_pack_replacement.publish_transaction

    def stop_after_prepare(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise OSError("stop after durable prepare")

    monkeypatch.setattr(task_pack_queue.task_pack_replacement, "publish_transaction", stop_after_prepare)
    with pytest.raises(OSError, match="stop after durable prepare"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))

    transaction_id = replacement_transaction_id(tmp_path, plan)
    prepare_path = task_pack_queue.task_pack_replacement.prepare_path(tmp_path, transaction_id)
    prepare = json.loads(prepare_path.read_text(encoding="utf-8"))
    target = next(item for item in prepare["targets"] if item["role"] == "successor_pack")
    successor = json.loads(base64.b64decode(target["after_payload_b64"]).decode("utf-8"))
    successor["goal"] = "tampered but internally rehashed goal"
    payload = task_pack_queue.json_bytes(successor)
    target["after_payload_b64"] = base64.b64encode(payload).decode("ascii")
    target["after_sha256"] = hashlib.sha256(payload).hexdigest()
    write_json(prepare_path, prepare)

    monkeypatch.setattr(task_pack_queue.task_pack_replacement, "publish_transaction", original_publish)
    with pytest.raises(SystemExit, match="target binding"):
        task_pack_queue.command_recover_replacement(argparse.Namespace(root=str(tmp_path)))


@pytest.mark.parametrize("evidence_key", ["creation_snapshot_ref", "creation_receipt_ref"])
def test_replace_pack_receipt_validation_requires_creation_evidence_after_commit(
    tmp_path: Path,
    evidence_key: str,
) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    transaction_id = replacement_transaction_id(tmp_path, plan)
    committed = task_pack_queue.task_pack_replacement.validate_completed_transaction(tmp_path, transaction_id)
    prepare = task_pack_queue.task_pack_replacement.load_prepare(tmp_path, transaction_id)[0]
    creation = prepare["metadata"]["creation_snapshot"]
    evidence_path = tmp_path / creation[evidence_key]
    evidence_path.unlink()

    validation = task_pack_queue.validate_replacement_receipt(tmp_path, plan, committed)
    assert validation["status"] == "block"
    assert validation["findings"]


def test_replace_pack_rejects_transaction_id_only_as_supplied_receipt(tmp_path: Path) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    transaction_id = replacement_transaction_id(tmp_path, plan)

    validation = task_pack_queue.validate_replacement_receipt(
        tmp_path,
        plan,
        {"transaction_id": transaction_id},
    )
    assert validation["status"] == "block"
    assert validation["findings"]


def test_replace_pack_receipt_tamper_fails_closed(tmp_path: Path) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    transaction_id = replacement_transaction_id(tmp_path, plan)
    receipt_path = task_pack_queue.task_pack_replacement.completion_path(tmp_path, transaction_id)
    original = json.loads(receipt_path.read_text(encoding="utf-8"))

    changed_target = json.loads(json.dumps(original))
    changed_target["targets"][0]["after_sha256"] = "0" * 64
    write_json(receipt_path, changed_target)
    with pytest.raises(SystemExit, match="target projection"):
        task_pack_queue.task_pack_replacement.validate_completed_transaction(tmp_path, transaction_id)
    assert transaction_id in task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path)
    render_args = argparse.Namespace(
        root=str(tmp_path),
        pack=".task/task_pack/pack-successor.json",
        language="ko",
    )
    assert task_pack_queue.command_render(render_args) == 2
    assert not (tmp_path / ".task" / "task_pack" / "pack-successor.md").exists()
    with pytest.raises(SystemExit, match="forward recovery"):
        task_pack_queue._command_mark_consumed_locked(argparse.Namespace(), tmp_path)

    changed_postcondition = json.loads(json.dumps(original))
    changed_postcondition["postcondition"]["active_pack_count"] = 2
    write_json(receipt_path, changed_postcondition)
    validation = task_pack_queue.validate_replacement_receipt(tmp_path, plan, changed_postcondition)
    assert validation["status"] == "block"
    assert any(
        finding["code"] == "replacement_receipt_invalid"
        for finding in validation["findings"]
    )
    assert transaction_id in task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path)


def test_replace_pack_supports_exact_authorized_initial_selection(tmp_path: Path) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    task_path = tmp_path / "task.md"
    task_path.write_text("# old active verifier task\n", encoding="utf-8")
    old_task_bytes = task_path.read_bytes()
    prospective_task_path = tmp_path / ".task" / "prepublication" / "replacement-task.md"
    prospective_task_path.parent.mkdir(parents=True, exist_ok=True)
    prospective_task_path.write_text("# replacement task\n", encoding="utf-8")
    selected_at = plan["pack"]["created_at"]
    planned = json.loads(json.dumps(plan["pack"]))
    planned["mutation_log"].append(
        {
            "timestamp": selected_at,
            "action": "create",
            "reason": plan["reason"],
            "evidence_paths": [],
            "before_order": [],
            "after_order": [item["item_id"] for item in planned["items"]],
            "actor": "$task-doctor",
            "predecessor_pack_ref": ".task/task_pack/pack-old.json",
        }
    )
    creation_payload = task_pack_queue.json_bytes(planned)
    creation_digest = hashlib.sha256(creation_payload).hexdigest()
    creation_ref = f".task/task_pack/creation_snapshots/pack-successor-{creation_digest[:16]}.json"
    task_digest = sha256(prospective_task_path)
    task_snapshot_ref = f".task/task_pack/task_snapshots/pack-successor/repair-a-task-repair-{task_digest[:16]}.md"
    subject = {
        "pack_ref": ".task/task_pack/pack-successor.json",
        "pack_creation_snapshot_ref": creation_ref,
        "pack_creation_snapshot_sha256": creation_digest,
        "initial_item_id": "repair-a",
        "initial_order": 1,
        "task_id": "task-repair",
        "task_snapshot_ref": task_snapshot_ref,
        "task_snapshot_sha256": task_digest,
    }
    authority_ref, authority_sha = write_authority_receipt(
        tmp_path,
        subject,
        operation="task_pack.initial_selection",
        temporality="contemporaneous_selection_authority",
        selected_at=selected_at,
        receipt_id="authr-replace-selection",
    )
    plan["initial_selection"] = {
        "item_id": "repair-a",
        "task_id": "task-repair",
        "task_path": "task.md",
        "promotion_origin": "authorized_initial_selection",
        "reason": "authorized replacement first selection",
        "prospective_task_ref": prospective_task_path.relative_to(tmp_path).as_posix(),
        "prospective_task_sha256": task_digest,
        "initial_selection_receipt": {
            "schema_version": 1,
            "pack_ref": subject["pack_ref"],
            "pack_creation_snapshot_kind": "workspace_file",
            "pack_creation_snapshot_ref": creation_ref,
            "pack_creation_snapshot_sha256": creation_digest,
            "pack_creation_canonical_sha256": task_pack_queue.canonical_pack_sha256(planned),
            "pack_creation_canonicalization_version": 1,
            "creation_snapshot_state": "pre_selection",
            "initial_item_id": "repair-a",
            "initial_order": 1,
            "task_id": "task-repair",
            "task_snapshot_ref": task_snapshot_ref,
            "task_snapshot_sha256": task_digest,
            "authority_receipt_ref": authority_ref,
            "authority_receipt_sha256": authority_sha,
            "authority_mode": "contemporaneous_selection_authority",
            "historical_selection_authority_status": "verified",
            "selection_reason": "first successor item selected with replacement",
            "created_at": selected_at,
        },
    }
    dry_run_args = mutation_args(tmp_path, plan)
    dry_run_args.dry_run = True
    assert task_pack_queue.command_apply_mutation(dry_run_args) == 0
    assert task_path.read_bytes() == old_task_bytes
    assert not (tmp_path / ".task" / "task_pack" / "creation_snapshots").exists()

    task_path.write_bytes(prospective_task_path.read_bytes())
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    successor = json.loads(
        (tmp_path / ".task" / "task_pack" / "pack-successor.json").read_text(encoding="utf-8")
    )
    assert successor["items"][0]["status"] == "promoted"
    assert successor["items"][0]["promotion"]["task_sha256"] == task_digest
    assert successor["current_item_id"] == "repair-b"


def test_replace_pack_rejects_changed_carried_planning_contract(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    plan["pack"]["items"][3]["objective"] = "Changed carried objective."
    before = old_path.read_bytes()
    args = mutation_args(tmp_path, plan)
    args.dry_run = True
    assert task_pack_queue.command_apply_mutation(args) == 2
    assert old_path.read_bytes() == before
    assert not (tmp_path / ".task" / "task_pack" / "pack-successor.json").exists()


def test_replace_pack_rejects_reclassifying_predecessor_item_as_new(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    contract = plan["pack"]["replacement_contract"]
    contract["carried_forward_item_ids"].remove("tail-1")
    contract["new_item_ids"].append("tail-1")
    before = old_path.read_bytes()
    args = mutation_args(tmp_path, plan)
    args.dry_run = True

    assert task_pack_queue.command_apply_mutation(args) == 2
    assert old_path.read_bytes() == before
    assert not (tmp_path / ".task" / "task_pack" / "pack-successor.json").exists()


def test_replace_pack_rejects_silently_dropped_nonterminal_predecessor_item(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    plan["pack"]["items"] = [
        item for item in plan["pack"]["items"] if item["item_id"] != "tail-4"
    ]
    plan["pack"]["replacement_contract"]["carried_forward_item_ids"].remove("tail-4")
    before = old_path.read_bytes()
    args = mutation_args(tmp_path, plan)
    args.dry_run = True

    assert task_pack_queue.command_apply_mutation(args) == 2
    assert old_path.read_bytes() == before
    assert not (tmp_path / ".task" / "task_pack" / "pack-successor.json").exists()


def test_replace_pack_allows_explicit_hash_bound_predecessor_retirement(tmp_path: Path) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    evidence_path = tmp_path / ".task" / "authorization" / "retire-tail-4.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("# Replacement direction\n\n- source_id: direction-retire-tail-4\n", encoding="utf-8")
    plan["pack"]["items"] = [item for item in plan["pack"]["items"] if item["item_id"] != "tail-4"]
    contract = plan["pack"]["replacement_contract"]
    contract["carried_forward_item_ids"].remove("tail-4")
    contract["retired_items"] = [
        {
            "item_id": "tail-4",
            "reason": "explicit direction replaces this obsolete predecessor item",
            "evidence": [
                {
                    "path": evidence_path.relative_to(tmp_path).as_posix(),
                    "sha256": sha256(evidence_path),
                }
            ],
        }
    ]
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    transaction_id = replacement_transaction_id(tmp_path, plan)
    receipt = task_pack_queue.task_pack_replacement.validate_completed_transaction(tmp_path, transaction_id)
    evidence_path.unlink()
    validation = task_pack_queue.validate_replacement_receipt(tmp_path, plan, receipt)
    assert validation["status"] == "block"
    assert any(
        finding["code"] == "replacement_postcondition_invalid"
        for finding in validation["findings"]
    )


def test_replace_pack_rejects_dependency_on_retired_uncompleted_predecessor(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    predecessor = json.loads(old_path.read_text(encoding="utf-8"))
    predecessor["items"][0]["dependencies"] = ["tail-4"]
    write_json(old_path, predecessor)
    plan["pack_coherence"]["before_pack_sha256"] = task_pack_queue.canonical_pack_sha256(predecessor)
    contract = plan["pack"]["replacement_contract"]
    contract["predecessor_pack_file_sha256"] = sha256(old_path)
    contract["predecessor_pack_canonical_sha256"] = task_pack_queue.canonical_pack_sha256(predecessor)
    plan["pack"]["items"][3]["dependencies"] = ["tail-4"]
    plan["pack"]["items"] = [item for item in plan["pack"]["items"] if item["item_id"] != "tail-4"]
    contract["carried_forward_item_ids"].remove("tail-4")
    evidence_path = tmp_path / ".task" / "authorization" / "retire-dependent.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("# Direction\n\n- source_id: retire-dependent\n", encoding="utf-8")
    contract["retired_items"] = [
        {
            "item_id": "tail-4",
            "reason": "obsolete verifier",
            "evidence": [
                {
                    "path": evidence_path.relative_to(tmp_path).as_posix(),
                    "sha256": sha256(evidence_path),
                }
            ],
        }
    ]
    args = mutation_args(tmp_path, plan)
    args.dry_run = True
    assert task_pack_queue.command_apply_mutation(args) == 2
    assert not (tmp_path / ".task" / "task_pack" / "pack-successor.json").exists()


def test_replace_pack_rejects_retirement_evidence_inside_mutated_pack_store(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    plan["pack"]["items"] = [item for item in plan["pack"]["items"] if item["item_id"] != "tail-4"]
    contract = plan["pack"]["replacement_contract"]
    contract["carried_forward_item_ids"].remove("tail-4")
    contract["retired_items"] = [
        {
            "item_id": "tail-4",
            "reason": "invalid self-referential evidence",
            "evidence": [
                {
                    "path": old_path.relative_to(tmp_path).as_posix(),
                    "sha256": sha256(old_path),
                }
            ],
        }
    ]
    args = mutation_args(tmp_path, plan)
    args.dry_run = True
    assert task_pack_queue.command_apply_mutation(args) == 2


def test_replace_pack_forward_recovers_after_successor_publish_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    original = task_pack_queue.task_pack_replacement.atomic_write_bytes

    def crash_on_successor(path: Path, payload: bytes) -> None:
        if path.name == "pack-successor.json":
            raise OSError("simulated successor publication crash")
        original(path, payload)

    monkeypatch.setattr(task_pack_queue.task_pack_replacement, "atomic_write_bytes", crash_on_successor)
    with pytest.raises(OSError, match="simulated successor"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))
    assert json.loads(old_path.read_text(encoding="utf-8"))["status"] == "superseded"
    assert task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path)
    monkeypatch.setattr(task_pack_queue.task_pack_replacement, "atomic_write_bytes", original)
    dry_run_args = mutation_args(tmp_path, plan)
    dry_run_args.dry_run = True
    assert task_pack_queue.command_apply_mutation(dry_run_args) == 2
    assert not (tmp_path / ".task" / "task_pack" / "pack-successor.json").exists()
    recover_args = argparse.Namespace(root=str(tmp_path))
    assert task_pack_queue.command_recover_replacement(recover_args) == 0
    assert not task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path)
    assert [path.name for path, _data in task_pack_queue.active_pack_candidates(tmp_path)] == ["pack-successor.json"]


def test_active_pack_does_not_fallback_and_multiple_active_is_blocked(tmp_path: Path) -> None:
    first = write_pack(tmp_path)
    body = json.loads(first.read_text(encoding="utf-8"))
    body["status"] = "superseded"
    write_json(first, body)
    assert task_pack_queue.active_pack(tmp_path) == (None, None)
    body["status"] = "active"
    write_json(first, body)
    second = tmp_path / ".task" / "task_pack" / "pack-2.json"
    second_body = json.loads(json.dumps(body))
    second_body["pack_id"] = "pack-2"
    write_json(second, second_body)
    status_args = argparse.Namespace(root=str(tmp_path), format="json")
    assert task_pack_queue.command_status(status_args) == 2


def test_create_with_initial_selection_commits_one_coherent_state(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# task-1\n", encoding="utf-8")
    selected_at = "2026-01-01T00:00:00+00:00"
    pack = {
        "schema_version": 1,
        "pack_id": "pack-atomic",
        "status": "active",
        "language": "ko",
        "goal": "Atomic initial selection.",
        "current_item_id": "item-1",
        "created_at": selected_at,
        "updated_at": selected_at,
        "items": [pack_item("item-1", 1), pack_item("item-2", 2)],
        "mutation_log": [],
        "terminal_blocker": None,
    }
    reason = "create and select first item atomically"
    planned = json.loads(json.dumps(pack))
    planned["mutation_log"].append(
        {
            "timestamp": selected_at,
            "action": "create",
            "reason": reason,
            "evidence_paths": [],
            "before_order": [],
            "after_order": ["item-1", "item-2"],
            "actor": "$derive-improvement-task",
        }
    )
    payload = task_pack_queue.json_bytes(planned)
    snapshot_digest = hashlib.sha256(payload).hexdigest()
    snapshot_ref = f".task/task_pack/creation_snapshots/pack-atomic-{snapshot_digest[:16]}.json"
    task_digest = sha256(tmp_path / "task.md")
    task_snapshot_ref = f".task/task_pack/task_snapshots/pack-atomic/item-1-task-1-{task_digest[:16]}.md"
    subject = {
        "pack_ref": ".task/task_pack/pack-atomic.json",
        "pack_creation_snapshot_ref": snapshot_ref,
        "pack_creation_snapshot_sha256": snapshot_digest,
        "initial_item_id": "item-1",
        "initial_order": 1,
        "task_id": "task-1",
        "task_snapshot_ref": task_snapshot_ref,
        "task_snapshot_sha256": task_digest,
    }
    authority_ref, authority_sha = write_authority_receipt(
        tmp_path,
        subject,
        operation="task_pack.initial_selection",
        temporality="contemporaneous_selection_authority",
        selected_at=selected_at,
        receipt_id="authr-create-atomic",
    )
    initial_receipt = {
        "schema_version": 1,
        "pack_ref": subject["pack_ref"],
        "pack_creation_snapshot_kind": "workspace_file",
        "pack_creation_snapshot_ref": snapshot_ref,
        "pack_creation_snapshot_sha256": snapshot_digest,
        "pack_creation_canonical_sha256": task_pack_queue.canonical_pack_sha256(planned),
        "pack_creation_canonicalization_version": 1,
        "creation_snapshot_state": "pre_selection",
        "initial_item_id": "item-1",
        "initial_order": 1,
        "task_id": "task-1",
        "task_snapshot_ref": task_snapshot_ref,
        "task_snapshot_sha256": task_digest,
        "authority_receipt_ref": authority_ref,
        "authority_receipt_sha256": authority_sha,
        "authority_mode": "contemporaneous_selection_authority",
        "historical_selection_authority_status": "verified",
        "selection_reason": "first task selected with pack creation",
        "created_at": selected_at,
    }
    plan = {
        "action": "create_pack",
        "reason": reason,
        "pack": pack,
        "initial_selection": {
            "item_id": "item-1",
            "task_id": "task-1",
            "task_path": "task.md",
            "promotion_origin": "bootstrap_initial_selection",
            "reason": "initial selection",
            "initial_selection_receipt": initial_receipt,
        },
    }
    dry_run_args = mutation_args(tmp_path, plan)
    dry_run_args.dry_run = True
    assert task_pack_queue.command_apply_mutation(dry_run_args) == 0
    creation_receipt_ref = f".task/task_pack/creation_receipts/pack-atomic-{snapshot_digest[:16]}.json"
    for reference in (
        subject["pack_ref"],
        snapshot_ref,
        creation_receipt_ref,
        task_snapshot_ref,
        ".task/task_pack/pack-atomic.md",
    ):
        assert not (tmp_path / reference).exists()

    invalid = json.loads(json.dumps(plan))
    invalid["initial_selection"]["initial_selection_receipt"]["authority_receipt_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="Authority receipt SHA-256"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, invalid))
    for reference in (
        subject["pack_ref"],
        snapshot_ref,
        creation_receipt_ref,
        task_snapshot_ref,
        ".task/task_pack/pack-atomic.md",
    ):
        assert not (tmp_path / reference).exists()

    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    pack_path = tmp_path / subject["pack_ref"]
    body = json.loads(pack_path.read_text(encoding="utf-8"))
    assert body["items"][0]["status"] == "promoted"
    assert body["items"][1]["status"] == "planned"
    assert body["current_item_id"] == "item-2"
    assert (tmp_path / snapshot_ref).is_file()
    assert (tmp_path / task_snapshot_ref).is_file()
    assert not [finding for finding in task_pack_queue.validate_pack(body, pack_path) if finding["severity"] == "block"]


def test_initial_promotion_dry_run_rolls_back_task_snapshot(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-1\n", encoding="utf-8")
    plan = initial_selection_plan(tmp_path, pack_path)
    task_snapshot = tmp_path / plan["initial_selection_receipt"]["task_snapshot_ref"]
    assert not task_snapshot.exists()
    before = pack_path.read_bytes()

    args = mutation_args(tmp_path, plan)
    args.dry_run = True
    assert task_pack_queue.command_apply_mutation(args) == 0
    assert pack_path.read_bytes() == before
    assert not task_snapshot.exists()


def test_mutation_rejects_pack_path_outside_pack_directory(tmp_path: Path) -> None:
    write_pack(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    plan = {"action": "skip", "pack_path": "outside.json", "item_ids": ["item-1"], "reason": "escape", "evidence_paths": []}

    with pytest.raises(SystemExit, match="Task pack path must stay inside"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_validate_rejects_pack_symlink_escape(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(pack_path.read_text(encoding="utf-8"), encoding="utf-8")
    symlink = pack_path.parent / "symlink.json"
    symlink.symlink_to(outside)
    args = argparse.Namespace(root=str(tmp_path), pack=".task/task_pack/symlink.json")

    with pytest.raises(SystemExit, match="Task pack path must stay inside"):
        task_pack_queue.command_validate(args)


def test_render_rejects_markdown_symlink_escape(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("preserve\n", encoding="utf-8")
    pack_path.with_suffix(".md").symlink_to(outside)
    args = argparse.Namespace(root=str(tmp_path), pack=".task/task_pack/pack-1.json", language="ko")

    with pytest.raises(SystemExit, match="Markdown render path must stay inside"):
        task_pack_queue.command_render(args)
    assert outside.read_text(encoding="utf-8") == "preserve\n"


def test_current_pack_coherence_rejects_stale_unknown_and_incomplete_receipt(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    stale_plan = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_ids": ["item-1"],
        "reason": "skip item_I",
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    changed = json.loads(pack_path.read_text(encoding="utf-8"))
    changed["goal"] = "changed after planning"
    write_json(pack_path, changed)
    before = pack_path.read_bytes()

    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, stale_plan)) == 2
    assert pack_path.read_bytes() == before

    write_pack(tmp_path)
    unknown_plan = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_ids": ["item-1"],
        "reason": "unknown proposed item",
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    unknown_plan["pack_coherence"]["proposed_after_item_ids"] = ["item-1", "item-X"]
    unknown_plan["pack_coherence"]["proposed_after_order"] = ["item-1", "item-X"]
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, unknown_plan)) == 2

    complete_plan = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    incomplete = task_pack_queue.validate_pack_coherence_contract(
        tmp_path,
        complete_plan,
        receipt={"before_pack_sha256": complete_plan["pack_coherence"]["before_pack_sha256"]},
        require_declared=True,
        require_receipt=True,
    )
    assert incomplete["status"] == "block"
    assert any(item["code"] == "pack_mutation_receipt_incomplete" for item in incomplete["findings"])


def test_reorder_uses_declared_order_and_material_noop_is_blocked(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    reorder = {
        "action": "reorder",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_order": ["item-2", "item-1"],
        "reason": "reverse canonical order",
        "pack_coherence": current_pack_coherence(tmp_path, "reorder"),
    }
    reorder["pack_coherence"]["proposed_after_item_ids"] = ["item-2", "item-1"]
    reorder["pack_coherence"]["proposed_after_order"] = ["item-2", "item-1"]
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, reorder)) == 0
    assert [item["item_id"] for item in json.loads(pack_path.read_text(encoding="utf-8"))["items"]] == [
        "item-2",
        "item-1",
    ]

    first_skip = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_ids": ["item-1"],
        "reason": "skip once",
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, first_skip)) == 0
    second_skip = {
        **first_skip,
        "reason": "skip once",
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    before = pack_path.read_bytes()
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, second_skip)) == 2
    assert pack_path.read_bytes() == before


def test_concurrent_mutations_with_one_before_hash_commit_exactly_once(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    coherence = current_pack_coherence(tmp_path, "skip")
    plans = [
        {
            "action": "skip",
            "pack_path": str(pack_path.relative_to(tmp_path)),
            "item_ids": [item_id],
            "reason": f"concurrent skip {item_id}",
            "pack_coherence": coherence,
        }
        for item_id in ("item-1", "item-2")
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda plan: task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)),
                plans,
            )
        )
    assert sorted(results) == [0, 2]
    body = json.loads(pack_path.read_text(encoding="utf-8"))
    assert sum(item["status"] == "skipped" for item in body["items"]) == 1


def test_initial_bootstrap_is_valid_once_and_cannot_disguise_a_successor(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-1\n", encoding="utf-8")
    initial = initial_selection_plan(tmp_path, pack_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, initial)) == 0
    completion = authoritative_provenance(tmp_path, validated_task_id="task-1")
    assert consume_cli(tmp_path, completion, task_id="task-1") == 0

    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    disguised = {
        **initial,
        "item_id": "item-2",
        "task_id": "task-2",
        "reason": "invalid repeated bootstrap",
        "pack_coherence": current_pack_coherence(tmp_path, "promote"),
    }
    disguised["initial_selection_receipt"] = {
        **initial["initial_selection_receipt"],
        "initial_item_id": "item-2",
        "initial_order": 2,
        "task_id": "task-2",
        "task_snapshot_sha256": sha256(tmp_path / "task.md"),
    }
    with pytest.raises(SystemExit, match="first canonical pack item|cannot be reused|deterministic task snapshot"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, disguised))


def test_initial_selection_rejects_bare_or_stale_authority_receipt(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-1\n", encoding="utf-8")
    plan = initial_selection_plan(tmp_path, pack_path)
    plan["initial_selection_receipt"]["authority_receipt_ref"] = "authority_A"
    before = pack_path.read_bytes()
    with pytest.raises(SystemExit, match="does not identify an existing file"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))
    assert pack_path.read_bytes() == before

    plan = initial_selection_plan(tmp_path, pack_path)
    plan["initial_selection_receipt"]["authority_receipt_sha256"] = "0" * 64
    with pytest.raises(SystemExit, match="Authority receipt SHA-256"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))
    assert pack_path.read_bytes() == before

    plan = initial_selection_plan(tmp_path, pack_path)
    authority_path = tmp_path / plan["initial_selection_receipt"]["authority_receipt_ref"]
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["authority_basis"]["source_kind"] = "unknown_source"
    write_json(authority_path, authority)
    plan["initial_selection_receipt"]["authority_receipt_sha256"] = sha256(authority_path)
    with pytest.raises(SystemExit, match="supported source_kind"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))
    assert pack_path.read_bytes() == before


def test_consumed_legacy_initial_selection_normalizes_with_current_ratification(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-1\n", encoding="utf-8")
    initial = initial_selection_plan(tmp_path, pack_path)
    creation = {
        key: initial["initial_selection_receipt"][key]
        for key in (
            "pack_creation_snapshot_kind",
            "pack_creation_snapshot_ref",
            "pack_creation_snapshot_sha256",
            "pack_creation_canonical_sha256",
            "pack_creation_canonicalization_version",
            "creation_snapshot_state",
        )
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, initial)) == 0
    completion = authoritative_provenance(tmp_path, validated_task_id="task-1")
    assert consume_cli(tmp_path, completion, task_id="task-1") == 0
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    second = {
        "pack_disposition": "promote_next_item",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_id": "item-2",
        "task_id": "task-2",
        "task_path": "task.md",
        "reason": "successor",
        **completion,
    }
    second["pack_coherence"] = current_pack_coherence(tmp_path, "promote")
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, second)) == 0

    legacy = json.loads(pack_path.read_text(encoding="utf-8"))
    first_promotion = legacy["items"][0]["promotion"]
    for field in (
        "promotion_origin",
        "initial_selection_receipt",
        "initial_selection_receipt_ref",
        "predecessor_completion_receipt_ref",
    ):
        first_promotion.pop(field, None)
    first_promotion["authority_provenance_status"] = "unverifiable_legacy_user_retarget"
    first_promotion["authority_provenance_reason"] = "no contemporaneous operation receipt"
    first_promotion["promoted_at"] = "2026-01-01T00:00:00+00:00"
    write_json(pack_path, legacy)

    task_snapshot_ref = first_promotion["task_snapshot_path"]
    task_digest = first_promotion["task_sha256"]
    subject = {
        "pack_ref": str(pack_path.relative_to(tmp_path)),
        "pack_creation_snapshot_ref": creation["pack_creation_snapshot_ref"],
        "pack_creation_snapshot_sha256": creation["pack_creation_snapshot_sha256"],
        "initial_item_id": "item-1",
        "initial_order": 1,
        "task_id": "task-1",
        "task_snapshot_ref": task_snapshot_ref,
        "task_snapshot_sha256": task_digest,
    }
    authority_ref, authority_sha = write_authority_receipt(
        tmp_path,
        subject,
        operation="task_pack.normalize_initial_selection",
        temporality="current_ratification",
        selected_at="2026-01-01T00:00:00+00:00",
        receipt_id="authr-normalize",
    )
    normalization_receipt = {
        "schema_version": 1,
        "pack_ref": str(pack_path.relative_to(tmp_path)),
        **creation,
        "initial_item_id": "item-1",
        "initial_order": 1,
        "task_id": "task-1",
        "task_snapshot_ref": task_snapshot_ref,
        "task_snapshot_sha256": task_digest,
        "authority_receipt_ref": authority_ref,
        "authority_receipt_sha256": authority_sha,
        "authority_mode": "current_ratification",
        "historical_selection_authority_status": "unverifiable_before_ratification",
        "selection_reason": "ratify continuation without historical rewrite",
        "created_at": first_promotion["promoted_at"],
    }
    plan = {
        "pack_disposition": "normalize_initial_selection_provenance",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_id": "item-1",
        "promotion_origin": "bootstrap_initial_selection",
        "reason": "bounded legacy provenance normalization",
        "initial_selection_receipt": normalization_receipt,
        "pack_coherence": current_pack_coherence(tmp_path, "normalize_initial_selection_provenance"),
    }
    authority_path = tmp_path / authority_ref
    valid_authority = json.loads(authority_path.read_text(encoding="utf-8"))
    invalid_authorities = []
    backdated = json.loads(json.dumps(valid_authority))
    backdated["issued_at"] = "2025-12-31T23:00:00+00:00"
    backdated["effective_at"] = "2025-12-31T23:00:00+00:00"
    invalid_authorities.append((backdated, "Current ratification requires later"))
    wrong_subject = json.loads(json.dumps(valid_authority))
    wrong_subject["subject"]["initial_item_id"] = "item-X"
    invalid_authorities.append((wrong_subject, "subject does not match"))
    for invalid_authority, expected_message in invalid_authorities:
        write_json(authority_path, invalid_authority)
        invalid_plan = json.loads(json.dumps(plan))
        invalid_plan["initial_selection_receipt"]["authority_receipt_sha256"] = sha256(authority_path)
        before_rejection = pack_path.read_bytes()
        with pytest.raises(SystemExit, match=expected_message):
            task_pack_queue.command_apply_mutation(mutation_args(tmp_path, invalid_plan))
        assert pack_path.read_bytes() == before_rejection
    write_json(authority_path, valid_authority)
    plan["initial_selection_receipt"]["authority_receipt_sha256"] = sha256(authority_path)

    before = json.loads(pack_path.read_text(encoding="utf-8"))
    protected_before = {
        "current_item_id": before["current_item_id"],
        "states": [(item["item_id"], item["order"], item["status"], item.get("result"), item.get("completion")) for item in before["items"]],
        "second": before["items"][1],
        "legacy_status": before["items"][0]["promotion"]["authority_provenance_status"],
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    after = json.loads(pack_path.read_text(encoding="utf-8"))
    protected_after = {
        "current_item_id": after["current_item_id"],
        "states": [(item["item_id"], item["order"], item["status"], item.get("result"), item.get("completion")) for item in after["items"]],
        "second": after["items"][1],
        "legacy_status": after["items"][0]["promotion"]["authority_provenance_status"],
    }
    assert protected_after == protected_before
    normalized = after["items"][0]["promotion"]
    assert normalized["promotion_origin"] == "bootstrap_initial_selection"
    assert normalized["provenance_normalization"]["historical_authority_verdict"] == "partial"
    assert normalized["provenance_normalization"]["retroactive_claim_allowed"] is False
    assert not [finding for finding in task_pack_queue.validate_pack(after, pack_path) if finding["severity"] == "block"]

    before_literal_replay = pack_path.read_bytes()
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    assert pack_path.read_bytes() == before_literal_replay

    conflicting = json.loads(json.dumps(plan))
    conflicting["initial_selection_receipt"]["selection_reason"] = "conflicting replacement"
    before_conflict = pack_path.read_bytes()
    with pytest.raises(SystemExit, match="conflicting receipt"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, conflicting))
    assert pack_path.read_bytes() == before_conflict

    repeated = task_pack_queue.command_apply_mutation(mutation_args(tmp_path, {
        **plan,
        "pack_coherence": current_pack_coherence(tmp_path, "normalize_initial_selection_provenance"),
    }))
    assert repeated == 0

def test_atomic_consume_and_successor_promotion_rejects_partial_then_commits_once(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, promotion_plan(tmp_path))) == 0
    completion = {
        **authoritative_provenance(tmp_path, validated_task_id="task-2"),
        **passing_verdict_axes(),
        "task_id": "task-2",
        "reason": "atomic completion",
    }
    (tmp_path / "task.md").write_text("# task-3\n", encoding="utf-8")
    plan = {
        "pack_disposition": "promote_next_item",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_id": "item-2",
        "task_id": "task-3",
        "task_path": "task.md",
        "validated_task_id": "task-2",
        "validation_verdict": "complete",
        "reason": "atomic successor",
        "consume_current_item": completion,
        **{key: value for key, value in completion.items() if key not in {"task_id", "reason"}},
        "pack_coherence": current_pack_coherence(tmp_path, "promote"),
    }
    partial = json.loads(json.dumps(plan))
    del partial["consume_current_item"]["goal_readiness_verdict"]
    before = pack_path.read_bytes()
    with pytest.raises(SystemExit, match="missing: goal_readiness_verdict"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, partial))
    assert pack_path.read_bytes() == before

    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    assert pack["items"][0]["status"] == "consumed"
    assert pack["items"][1]["status"] == "promoted"
    assert pack["items"][1]["promotion"]["validated_task_id"] == "task-2"


def test_pack_coherence_legacy_requires_explicit_version_zero(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    unversioned = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_ids": ["item-1"],
        "reason": "unversioned legacy caller",
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, unversioned)) == 2

    explicit_legacy = {
        **unversioned,
        "reason": "explicit legacy caller",
        "pack_coherence": {"schema_version": 0},
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, explicit_legacy)) == 0
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    assert pack["items"][0]["status"] == "skipped"
