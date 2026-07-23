from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from orchestrate_task_cycle.prerequisite_chain_contract import receipt_sha256
from orchestrate_task_cycle.task_pack import api as task_pack_queue
from orchestrate_task_cycle.task_pack import consumption as task_pack_consumption
from orchestrate_task_cycle.task_pack import (
    creation as task_pack_creation,
    mutation_create,
    mutation_finalize,
    mutation_replace_draft,
)
from orchestrate_task_cycle.task_pack.mutation_actions import apply_terminal_block


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


def bounded_chain(position: int, **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "applicability": "applicable",
        "stable_root_id": "root-A",
        "item_owner_id": "owner-A",
        "prerequisite_relation_id": "relation-A",
        "strict_local_reduction": True,
        "semantic_high_water_moved": False,
        "chain_budget_status": "within",
        "mandatory_successor_kind": "producer",
        "chain_position": position,
        "chain_cap": 2,
        "residual_before": 3 - position + 1,
        "residual_after": 3 - position,
    }
    value.update(updates)
    if (
        value.get("strict_local_reduction") is True
        and "reduction_observation_receipt" not in value
    ):
        receipt: dict[str, object] = {
            "contract_version": "prerequisite-reduction-observation-v1",
            "receipt_id": f"receipt-{position}",
            "stable_root_id": value["stable_root_id"],
            "prerequisite_relation_id": value["prerequisite_relation_id"],
            "residual_basis_id": "basis-A",
            "observation_kind": "residual",
            "before_observation": {
                "observation_id": f"observation-before-{position}",
                "revision_id": f"revision-before-{position}",
                "value": value.get("residual_before"),
                "evidence_ref_id": f"evidence-before-{position}",
                "evidence_sha256": "a" * 64,
            },
            "after_observation": {
                "observation_id": f"observation-after-{position}",
                "revision_id": f"revision-after-{position}",
                "value": value.get("residual_after"),
                "evidence_ref_id": f"evidence-after-{position}",
                "evidence_sha256": "b" * 64,
            },
            "source_kind": "task_pack_projection",
            "source_revision_sha256": "c" * 64,
            "source_snapshot_sha256": "d" * 64,
            "observer_id": "observer-A",
            "invariant_owner_id": "owner-invariant-A",
            "provenance_status": "independently_observed",
        }
        receipt["receipt_sha256"] = receipt_sha256(receipt)
        value["reduction_observation_receipt"] = receipt
    return value


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
            "predecessor_pack_canonical_sha256": task_pack_queue.canonical_pack_sha256(
                old
            ),
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
        task_pack_queue.task_pack_replacement.pending_transaction_ids_for_plan(
            root, fingerprint
        )
        + task_pack_queue.task_pack_replacement.completed_transaction_ids_for_plan(
            root, fingerprint
        )
    )
    assert len(transaction_ids) == 1
    return transaction_ids[0]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def write_creation_snapshot(
    root: Path, pack_path: Path, data: dict[str, Any], *, state: str = "pre_selection"
) -> dict[str, Any]:
    payload = (
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    file_digest = hashlib.sha256(payload).hexdigest()
    snapshot = (
        root
        / ".task"
        / "task_pack"
        / "creation_snapshots"
        / f"pack-1-{file_digest[:16]}.json"
    )
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
        policy.write_text(
            "# Agent Authority\n\nCurrent permissions only.\n", encoding="utf-8"
        )
    source.write_text(
        f"# Explicit Authority Evidence\n\n- source_id: {receipt_id}\n",
        encoding="utf-8",
    )
    current_ratification = temporality == "current_ratification"
    receipt = {
        "schema_version": 1,
        "receipt_id": receipt_id,
        "receipt_kind": "operation_authority",
        "operation": operation,
        "decision": "allowed",
        "basis_temporality": temporality,
        "issued_at": "2026-07-12T12:00:00+09:00"
        if current_ratification
        else "2025-12-31T23:59:00+00:00",
        "effective_at": "2026-07-12T12:00:00+09:00"
        if current_ratification
        else "2025-12-31T23:59:00+00:00",
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
                "unverifiable_before_ratification"
                if current_ratification
                else "verified"
            ),
            "historical_authority_verdict": "partial"
            if current_ratification
            else "pass",
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


def consume_cli(
    root: Path,
    provenance: dict[str, Any],
    *,
    task_id: str = "task-2",
    coherence: dict[str, Any] | None = None,
    render: bool = False,
) -> int:
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
        json.dumps(
            coherence or current_pack_coherence(root, "mark_consumed"),
            sort_keys=True,
        ),
        "--verdict-axes-json",
        json.dumps(passing_verdict_axes(), sort_keys=True),
    ]
    for path in provenance["validation_evidence_paths"]:
        argv.extend(["--validation-evidence-path", str(path)])
    if render:
        argv.append("--render")
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


def test_promotion_is_recorded_after_validation_and_advances_queue(
    tmp_path: Path,
) -> None:
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
    assert (
        first["promotion"]["validation_report_sha256"]
        == plan["validation_report_sha256"]
    )
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
    run_packet.update(
        {
            "execution_status": "running",
            "long_run_branch": True,
            "long_run_role": "monitor",
        }
    )
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
    validation_path.write_text(
        validation_path.read_text(encoding="utf-8") + " ", encoding="utf-8"
    )

    with pytest.raises(SystemExit, match="SHA-256 does not match"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))


def test_pack_validation_rejects_manual_promotion_without_provenance(
    tmp_path: Path,
) -> None:
    pack_path = write_pack(tmp_path)
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["items"][0]["status"] = "promoted"
    pack["items"][0]["promotion"] = {"task_id": "task-2", "task_path": "task.md"}

    findings = task_pack_queue.validate_pack(pack, pack_path)

    assert "promotion_provenance_incomplete" in {
        finding["code"] for finding in findings
    }


def test_pack_validation_rechecks_bound_promotion_artifacts(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    validation_path = tmp_path / plan["validation_report_path"]
    validation_path.write_text(
        validation_path.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8"
    )

    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    findings = task_pack_queue.validate_pack(pack, pack_path)

    assert "promotion_provenance_invalid" in {finding["code"] for finding in findings}


def test_pack_validation_detects_promoted_task_drift(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    (tmp_path / "task.md").write_text("# unrelated replacement\n", encoding="utf-8")

    findings = task_pack_queue.validate_pack(
        json.loads(pack_path.read_text(encoding="utf-8")), pack_path
    )

    assert "promotion_provenance_invalid" in {finding["code"] for finding in findings}


def test_second_promotion_waits_for_in_flight_item_consumption(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    assert (
        task_pack_queue.command_apply_mutation(
            mutation_args(tmp_path, promotion_plan(tmp_path))
        )
        == 0
    )
    (tmp_path / "task.md").write_text("# task-3\n", encoding="utf-8")
    second = promotion_plan(tmp_path, item_id="item-2", task_id="task-3")

    with pytest.raises(SystemExit, match="in-flight item"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, second))


def test_consumption_is_hash_bound_and_allows_next_task_snapshot(
    tmp_path: Path,
) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    assert (
        task_pack_queue.command_apply_mutation(
            mutation_args(tmp_path, promotion_plan(tmp_path))
        )
        == 0
    )
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
    assert not [
        finding
        for finding in task_pack_queue.validate_pack(pack, pack_path)
        if finding["severity"] == "block"
    ]


def test_promotion_cannot_skip_the_current_queue_item(tmp_path: Path) -> None:
    write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-3\n", encoding="utf-8")
    plan = promotion_plan(
        tmp_path,
        item_id="item-2",
        task_id="task-3",
        reason="attempted out-of-order promotion",
    )

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
    assert (
        contract["publication"]["replacement_recovery"]
        == "fail_closed_forward_complete"
    )


def test_create_requires_clean_findings_and_no_active_predecessor(
    tmp_path: Path,
) -> None:
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
            "items": [
                pack_item(f"item-{index}", index) for index in range(1, item_count + 1)
            ],
            "mutation_log": [],
        },
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 2
    assert not (tmp_path / ".task" / "task_pack" / f"pack-{item_count}.json").exists()
    assert not (tmp_path / ".task" / "task_pack" / "creation_snapshots").exists()


def test_create_rejects_invalid_item_kind_without_expanding_progress_enums(
    tmp_path: Path,
) -> None:
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


def test_replace_pack_dry_run_is_clean_and_preserves_seven_item_tail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    before = old_path.read_bytes()
    args = mutation_args(tmp_path, plan)
    args.dry_run = True
    monkeypatch.setattr(
        mutation_replace_draft,
        "persist_creation_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("replace dry-run reached creation snapshot writer")
        ),
    )
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
    assert not (
        tmp_path / ".task" / "task_pack" / "replacement_plan_snapshots"
    ).exists()


def test_replace_pack_commits_once_and_exact_replay_is_noop(tmp_path: Path) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    successor_path = tmp_path / ".task" / "task_pack" / "pack-successor.json"
    old = json.loads(old_path.read_text(encoding="utf-8"))
    successor = json.loads(successor_path.read_text(encoding="utf-8"))
    assert old["status"] == "superseded"
    assert successor["status"] == "active"
    assert len(successor["items"]) == 7
    assert [
        path.name for path, _data in task_pack_queue.active_pack_candidates(tmp_path)
    ] == ["pack-successor.json"]
    before_old = old_path.read_bytes()
    before_successor = successor_path.read_bytes()
    transaction_id = replacement_transaction_id(tmp_path, plan)
    prepare_path = task_pack_queue.task_pack_replacement.prepare_path(
        tmp_path, transaction_id
    )
    receipt_path = task_pack_queue.task_pack_replacement.completion_path(
        tmp_path, transaction_id
    )
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
    assert (
        sorted(
            path.relative_to(tmp_path).as_posix()
            for path in (tmp_path / ".task" / "task_pack").rglob("*")
            if path.is_file()
        )
        == before_transaction_files
    )


def test_completed_replacement_does_not_become_pending_after_later_valid_pack_update(
    tmp_path: Path,
) -> None:
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

    monkeypatch.setattr(
        task_pack_queue.task_pack_replacement, "publish_transaction", stop_after_prepare
    )
    with pytest.raises(OSError, match="stop after durable prepare"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))

    transaction_id = replacement_transaction_id(tmp_path, plan)
    prepare_path = task_pack_queue.task_pack_replacement.prepare_path(
        tmp_path, transaction_id
    )
    prepare = json.loads(prepare_path.read_text(encoding="utf-8"))
    target = next(
        item for item in prepare["targets"] if item["role"] == "successor_pack"
    )
    if tampered_field == "after_payload_b64":
        target[tampered_field] = base64.b64encode(b"tampered successor payload").decode(
            "ascii"
        )
    else:
        target[tampered_field] = "0" * 64
    write_json(prepare_path, prepare)

    monkeypatch.setattr(
        task_pack_queue.task_pack_replacement, "publish_transaction", original_publish
    )
    with pytest.raises(SystemExit, match="payload digest is inconsistent"):
        task_pack_queue.command_recover_replacement(
            argparse.Namespace(root=str(tmp_path))
        )


def test_replace_pack_recovery_rejects_coherently_rehashed_prepare_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    original_publish = task_pack_queue.task_pack_replacement.publish_transaction

    def stop_after_prepare(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise OSError("stop after durable prepare")

    monkeypatch.setattr(
        task_pack_queue.task_pack_replacement, "publish_transaction", stop_after_prepare
    )
    with pytest.raises(OSError, match="stop after durable prepare"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))

    transaction_id = replacement_transaction_id(tmp_path, plan)
    prepare_path = task_pack_queue.task_pack_replacement.prepare_path(
        tmp_path, transaction_id
    )
    prepare = json.loads(prepare_path.read_text(encoding="utf-8"))
    target = next(
        item for item in prepare["targets"] if item["role"] == "successor_pack"
    )
    successor = json.loads(
        base64.b64decode(target["after_payload_b64"]).decode("utf-8")
    )
    successor["goal"] = "tampered but internally rehashed goal"
    payload = task_pack_queue.json_bytes(successor)
    target["after_payload_b64"] = base64.b64encode(payload).decode("ascii")
    target["after_sha256"] = hashlib.sha256(payload).hexdigest()
    write_json(prepare_path, prepare)

    monkeypatch.setattr(
        task_pack_queue.task_pack_replacement, "publish_transaction", original_publish
    )
    with pytest.raises(SystemExit, match="target binding"):
        task_pack_queue.command_recover_replacement(
            argparse.Namespace(root=str(tmp_path))
        )


@pytest.mark.parametrize(
    "evidence_key", ["creation_snapshot_ref", "creation_receipt_ref"]
)
def test_replace_pack_receipt_validation_requires_creation_evidence_after_commit(
    tmp_path: Path,
    evidence_key: str,
) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    transaction_id = replacement_transaction_id(tmp_path, plan)
    committed = task_pack_queue.task_pack_replacement.validate_completed_transaction(
        tmp_path, transaction_id
    )
    prepare = task_pack_queue.task_pack_replacement.load_prepare(
        tmp_path, transaction_id
    )[0]
    creation = prepare["metadata"]["creation_snapshot"]
    evidence_path = tmp_path / creation[evidence_key]
    evidence_path.unlink()

    validation = task_pack_queue.validate_replacement_receipt(tmp_path, plan, committed)
    assert validation["status"] == "block"
    assert validation["findings"]


def test_replace_pack_rejects_transaction_id_only_as_supplied_receipt(
    tmp_path: Path,
) -> None:
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
    receipt_path = task_pack_queue.task_pack_replacement.completion_path(
        tmp_path, transaction_id
    )
    original = json.loads(receipt_path.read_text(encoding="utf-8"))

    changed_target = json.loads(json.dumps(original))
    changed_target["targets"][0]["after_sha256"] = "0" * 64
    write_json(receipt_path, changed_target)
    with pytest.raises(SystemExit, match="target projection"):
        task_pack_queue.task_pack_replacement.validate_completed_transaction(
            tmp_path, transaction_id
        )
    assert (
        transaction_id
        in task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path)
    )
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
    validation = task_pack_queue.validate_replacement_receipt(
        tmp_path, plan, changed_postcondition
    )
    assert validation["status"] == "block"
    assert any(
        finding["code"] == "replacement_receipt_invalid"
        for finding in validation["findings"]
    )
    assert (
        transaction_id
        in task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path)
    )


def test_replace_pack_supports_exact_authorized_initial_selection(
    tmp_path: Path,
) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    task_path = tmp_path / "task.md"
    task_path.write_text("# old active verifier task\n", encoding="utf-8")
    old_task_bytes = task_path.read_bytes()
    prospective_task_path = (
        tmp_path / ".task" / "prepublication" / "replacement-task.md"
    )
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
    creation_ref = (
        f".task/task_pack/creation_snapshots/pack-successor-{creation_digest[:16]}.json"
    )
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
            "pack_creation_canonical_sha256": task_pack_queue.canonical_pack_sha256(
                planned
            ),
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
        (tmp_path / ".task" / "task_pack" / "pack-successor.json").read_text(
            encoding="utf-8"
        )
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


def test_replace_pack_rejects_reclassifying_predecessor_item_as_new(
    tmp_path: Path,
) -> None:
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


def test_replace_pack_rejects_silently_dropped_nonterminal_predecessor_item(
    tmp_path: Path,
) -> None:
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


def test_replace_pack_allows_explicit_hash_bound_predecessor_retirement(
    tmp_path: Path,
) -> None:
    _old_path, plan = replacement_fixture(tmp_path)
    evidence_path = tmp_path / ".task" / "authorization" / "retire-tail-4.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        "# Replacement direction\n\n- source_id: direction-retire-tail-4\n",
        encoding="utf-8",
    )
    plan["pack"]["items"] = [
        item for item in plan["pack"]["items"] if item["item_id"] != "tail-4"
    ]
    contract = plan["pack"]["replacement_contract"]
    contract["carried_forward_item_ids"].remove("tail-4")
    contract["retired_items"] = [
        {
            "item_id": "tail-4",
            "reason": "explicit direction replaces this obsolete predecessor item",
            "retirement_basis": "explicit_user_exclusion",
            "predecessor_pack_sha256": contract["predecessor_pack_canonical_sha256"],
            "decision_evidence": [
                {
                    "path": evidence_path.relative_to(tmp_path).as_posix(),
                    "sha256": sha256(evidence_path),
                }
            ],
        }
    ]
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    transaction_id = replacement_transaction_id(tmp_path, plan)
    receipt = task_pack_queue.task_pack_replacement.validate_completed_transaction(
        tmp_path, transaction_id
    )
    evidence_path.unlink()
    validation = task_pack_queue.validate_replacement_receipt(tmp_path, plan, receipt)
    assert validation["status"] == "block"
    assert any(
        finding["code"] == "replacement_postcondition_invalid"
        for finding in validation["findings"]
    )


def test_replace_pack_rejects_dependency_on_retired_uncompleted_predecessor(
    tmp_path: Path,
) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    predecessor = json.loads(old_path.read_text(encoding="utf-8"))
    predecessor["items"][0]["dependencies"] = ["tail-4"]
    write_json(old_path, predecessor)
    plan["pack_coherence"]["before_pack_sha256"] = (
        task_pack_queue.canonical_pack_sha256(predecessor)
    )
    contract = plan["pack"]["replacement_contract"]
    contract["predecessor_pack_file_sha256"] = sha256(old_path)
    contract["predecessor_pack_canonical_sha256"] = (
        task_pack_queue.canonical_pack_sha256(predecessor)
    )
    plan["pack"]["items"][3]["dependencies"] = ["tail-4"]
    plan["pack"]["items"] = [
        item for item in plan["pack"]["items"] if item["item_id"] != "tail-4"
    ]
    contract["carried_forward_item_ids"].remove("tail-4")
    evidence_path = tmp_path / ".task" / "authorization" / "retire-dependent.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        "# Direction\n\n- source_id: retire-dependent\n", encoding="utf-8"
    )
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


def test_replace_pack_rejects_retirement_evidence_inside_mutated_pack_store(
    tmp_path: Path,
) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    plan["pack"]["items"] = [
        item for item in plan["pack"]["items"] if item["item_id"] != "tail-4"
    ]
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


def test_replace_pack_forward_recovers_after_successor_publish_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_path, plan = replacement_fixture(tmp_path)
    original = task_pack_queue.task_pack_replacement.atomic_write_bytes

    def crash_on_successor(path: Path, payload: bytes) -> None:
        if path.name == "pack-successor.json":
            raise OSError("simulated successor publication crash")
        original(path, payload)

    monkeypatch.setattr(
        task_pack_queue.task_pack_replacement, "atomic_write_bytes", crash_on_successor
    )
    with pytest.raises(OSError, match="simulated successor"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))
    assert json.loads(old_path.read_text(encoding="utf-8"))["status"] == "superseded"
    assert task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path)
    monkeypatch.setattr(
        task_pack_queue.task_pack_replacement, "atomic_write_bytes", original
    )
    dry_run_args = mutation_args(tmp_path, plan)
    dry_run_args.dry_run = True
    assert task_pack_queue.command_apply_mutation(dry_run_args) == 2
    assert not (tmp_path / ".task" / "task_pack" / "pack-successor.json").exists()
    recover_args = argparse.Namespace(root=str(tmp_path))
    assert task_pack_queue.command_recover_replacement(recover_args) == 0
    assert not task_pack_queue.task_pack_replacement.pending_transaction_ids(tmp_path)
    assert [
        path.name for path, _data in task_pack_queue.active_pack_candidates(tmp_path)
    ] == ["pack-successor.json"]


def test_active_pack_does_not_fallback_and_multiple_active_is_blocked(
    tmp_path: Path,
) -> None:
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


def test_terminal_block_closes_all_residual_items_without_input_delta_warning(
    tmp_path: Path,
) -> None:
    path = write_pack(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    body["items"][0]["positive_input_delta_required"] = True
    body["items"][0]["required_new_input_kinds"] = ["exact-subject"]
    plan = {
        "action": "terminal_blocked",
        "reason": "bounded alternatives exhausted without a new input delta",
        "evidence_paths": [".task/evidence/terminal-A.json"],
        "terminal_blocker": {
            "reason_code": "alternatives-exhausted",
            "evidence_ids": ["evidence-terminal-A"],
            "semantic_signature": "terminal-family-A",
            "blocker_signature": "terminal-blocker-A",
            "required_handoff": "wait-for-new-exact-subject",
            "evidence_paths": [".task/evidence/terminal-A.json"],
        },
    }

    apply_terminal_block(body, body["items"], plan, ["item-1", "item-2"])
    body["current_item_id"] = None
    write_json(path, body)
    findings = task_pack_queue.validate_pack(body, path)

    assert body["status"] == "terminal_blocked"
    assert {item["status"] for item in body["items"]} == {"terminal_blocked"}
    assert "consumed_item_missing_supplied_input_delta" not in {
        finding["code"] for finding in findings
    }
    assert not [finding for finding in findings if finding["severity"] == "block"]


def test_status_reports_closed_pack_terminal_blocker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_pack(tmp_path)
    body = json.loads(path.read_text(encoding="utf-8"))
    plan = {
        "action": "terminal_blocked",
        "reason": "bounded alternatives exhausted",
        "evidence_paths": [],
        "terminal_blocker": {
            "reason_code": "alternatives-exhausted",
            "evidence_ids": ["evidence-terminal-A"],
            "semantic_signature": "terminal-family-A",
            "blocker_signature": "terminal-blocker-A",
            "required_handoff": "wait-for-material-delta",
            "evidence_paths": [".task/evidence/terminal-A.json"],
        },
    }
    apply_terminal_block(body, body["items"], plan, ["item-1", "item-2"])
    body["current_item_id"] = None
    write_json(path, body)

    assert (
        task_pack_queue.command_status(
            argparse.Namespace(root=str(tmp_path), format="json")
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "not_applicable"
    assert output["closed_packs"][0]["pack_status"] == "terminal_blocked"
    assert (
        output["closed_packs"][0]["terminal_blocker"]["reason_code"]
        == "alternatives-exhausted"
    )


def test_create_with_initial_selection_commits_one_coherent_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    snapshot_ref = (
        f".task/task_pack/creation_snapshots/pack-atomic-{snapshot_digest[:16]}.json"
    )
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
        "pack_creation_canonical_sha256": task_pack_queue.canonical_pack_sha256(
            planned
        ),
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
    with monkeypatch.context() as dry_run_patch:
        dry_run_patch.setattr(
            mutation_create,
            "persist_creation_snapshot",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("create dry-run reached creation snapshot writer")
            ),
        )
        dry_run_patch.setattr(
            task_pack_creation,
            "write_content_addressed_file",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("create dry-run reached task snapshot writer")
            ),
        )
        assert task_pack_queue.command_apply_mutation(dry_run_args) == 0
    creation_receipt_ref = (
        f".task/task_pack/creation_receipts/pack-atomic-{snapshot_digest[:16]}.json"
    )
    for reference in (
        subject["pack_ref"],
        snapshot_ref,
        creation_receipt_ref,
        task_snapshot_ref,
        ".task/task_pack/pack-atomic.md",
    ):
        assert not (tmp_path / reference).exists()

    invalid = json.loads(json.dumps(plan))
    invalid["initial_selection"]["initial_selection_receipt"][
        "authority_receipt_sha256"
    ] = "0" * 64
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
    assert not [
        finding
        for finding in task_pack_queue.validate_pack(body, pack_path)
        if finding["severity"] == "block"
    ]


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
    plan = {
        "action": "skip",
        "pack_path": "outside.json",
        "item_ids": ["item-1"],
        "reason": "escape",
        "evidence_paths": [],
    }

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
    args = argparse.Namespace(
        root=str(tmp_path), pack=".task/task_pack/pack-1.json", language="ko"
    )

    with pytest.raises(SystemExit, match="Markdown render path must stay inside"):
        task_pack_queue.command_render(args)
    assert outside.read_text(encoding="utf-8") == "preserve\n"


def test_current_pack_coherence_rejects_stale_unknown_and_incomplete_receipt(
    tmp_path: Path,
) -> None:
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

    assert (
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, stale_plan)) == 2
    )
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
    assert (
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, unknown_plan))
        == 2
    )

    complete_plan = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    incomplete = task_pack_queue.validate_pack_coherence_contract(
        tmp_path,
        complete_plan,
        receipt={
            "before_pack_sha256": complete_plan["pack_coherence"]["before_pack_sha256"]
        },
        require_declared=True,
        require_receipt=True,
    )
    assert incomplete["status"] == "block"
    assert any(
        item["code"] == "pack_mutation_receipt_incomplete"
        for item in incomplete["findings"]
    )


def test_reorder_uses_declared_order_and_material_noop_is_blocked(
    tmp_path: Path,
) -> None:
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
    assert [
        item["item_id"]
        for item in json.loads(pack_path.read_text(encoding="utf-8"))["items"]
    ] == [
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
    assert (
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, first_skip)) == 0
    )
    second_skip = {
        **first_skip,
        "reason": "skip once",
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    before = pack_path.read_bytes()
    assert (
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, second_skip))
        == 2
    )
    assert pack_path.read_bytes() == before


def test_concurrent_mutations_with_one_before_hash_commit_exactly_once(
    tmp_path: Path,
) -> None:
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
                lambda plan: task_pack_queue.command_apply_mutation(
                    mutation_args(tmp_path, plan)
                ),
                plans,
            )
        )
    assert sorted(results) == [0, 2]
    body = json.loads(pack_path.read_text(encoding="utf-8"))
    assert sum(item["status"] == "skipped" for item in body["items"]) == 1


def test_initial_bootstrap_is_valid_once_and_cannot_disguise_a_successor(
    tmp_path: Path,
) -> None:
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
    with pytest.raises(
        SystemExit,
        match="first canonical pack item|cannot be reused|deterministic task snapshot",
    ):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, disguised))


def test_initial_selection_rejects_bare_or_stale_authority_receipt(
    tmp_path: Path,
) -> None:
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
    authority_path = (
        tmp_path / plan["initial_selection_receipt"]["authority_receipt_ref"]
    )
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    authority["authority_basis"]["source_kind"] = "unknown_source"
    write_json(authority_path, authority)
    plan["initial_selection_receipt"]["authority_receipt_sha256"] = sha256(
        authority_path
    )
    with pytest.raises(SystemExit, match="supported source_kind"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))
    assert pack_path.read_bytes() == before


def test_consumed_legacy_initial_selection_normalizes_with_current_ratification(
    tmp_path: Path,
) -> None:
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
    first_promotion["authority_provenance_reason"] = (
        "no contemporaneous operation receipt"
    )
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
        "pack_coherence": current_pack_coherence(
            tmp_path, "normalize_initial_selection_provenance"
        ),
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
        invalid_plan["initial_selection_receipt"]["authority_receipt_sha256"] = sha256(
            authority_path
        )
        before_rejection = pack_path.read_bytes()
        with pytest.raises(SystemExit, match=expected_message):
            task_pack_queue.command_apply_mutation(
                mutation_args(tmp_path, invalid_plan)
            )
        assert pack_path.read_bytes() == before_rejection
    write_json(authority_path, valid_authority)
    plan["initial_selection_receipt"]["authority_receipt_sha256"] = sha256(
        authority_path
    )

    before = json.loads(pack_path.read_text(encoding="utf-8"))
    protected_before = {
        "current_item_id": before["current_item_id"],
        "states": [
            (
                item["item_id"],
                item["order"],
                item["status"],
                item.get("result"),
                item.get("completion"),
            )
            for item in before["items"]
        ],
        "second": before["items"][1],
        "legacy_status": before["items"][0]["promotion"]["authority_provenance_status"],
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    after = json.loads(pack_path.read_text(encoding="utf-8"))
    protected_after = {
        "current_item_id": after["current_item_id"],
        "states": [
            (
                item["item_id"],
                item["order"],
                item["status"],
                item.get("result"),
                item.get("completion"),
            )
            for item in after["items"]
        ],
        "second": after["items"][1],
        "legacy_status": after["items"][0]["promotion"]["authority_provenance_status"],
    }
    assert protected_after == protected_before
    normalized = after["items"][0]["promotion"]
    assert normalized["promotion_origin"] == "bootstrap_initial_selection"
    assert (
        normalized["provenance_normalization"]["historical_authority_verdict"]
        == "partial"
    )
    assert normalized["provenance_normalization"]["retroactive_claim_allowed"] is False
    assert not [
        finding
        for finding in task_pack_queue.validate_pack(after, pack_path)
        if finding["severity"] == "block"
    ]

    before_literal_replay = pack_path.read_bytes()
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    assert pack_path.read_bytes() == before_literal_replay

    conflicting = json.loads(json.dumps(plan))
    conflicting["initial_selection_receipt"]["selection_reason"] = (
        "conflicting replacement"
    )
    before_conflict = pack_path.read_bytes()
    with pytest.raises(SystemExit, match="conflicting receipt"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, conflicting))
    assert pack_path.read_bytes() == before_conflict

    repeated = task_pack_queue.command_apply_mutation(
        mutation_args(
            tmp_path,
            {
                **plan,
                "pack_coherence": current_pack_coherence(
                    tmp_path, "normalize_initial_selection_provenance"
                ),
            },
        )
    )
    assert repeated == 0


def test_atomic_consume_and_successor_promotion_rejects_partial_then_commits_once(
    tmp_path: Path,
) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    assert (
        task_pack_queue.command_apply_mutation(
            mutation_args(tmp_path, promotion_plan(tmp_path))
        )
        == 0
    )
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
        **{
            key: value
            for key, value in completion.items()
            if key not in {"task_id", "reason"}
        },
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
    assert (
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, unversioned))
        == 2
    )

    explicit_legacy = {
        **unversioned,
        "reason": "explicit legacy caller",
        "pack_coherence": {"schema_version": 0},
    }
    assert (
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, explicit_legacy))
        == 0
    )
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    assert pack["items"][0]["status"] == "skipped"


def test_completed_pack_rejects_blocked_residual_and_waiting_projection_stays_blocked() -> (
    None
):
    pack = {
        "schema_version": 1,
        "pack_id": "pack-waiting",
        "status": "completed",
        "goal": "Do not hide a blocked residual.",
        "current_item_id": None,
        "items": [{**pack_item("blocked-item", 1), "status": "blocked"}],
        "mutation_log": [],
    }
    codes = {finding["code"] for finding in task_pack_queue.validate_pack(pack)}
    assert "completed_pack_has_noncompleted_items" in codes
    assert "pack_operational_status_mismatch" in codes

    pack["status"] = "active"
    task_pack_queue.refresh_current_item(pack)
    assert pack["status"] == "blocked"
    assert pack["current_item_id"] is None


def test_task_pack_accepts_monotonic_reducing_prerequisite_chain() -> None:
    pack = {
        "schema_version": 1,
        "pack_id": "pack-prerequisite",
        "status": "active",
        "goal": "Bound prerequisite work before direct implementation.",
        "current_item_id": "item-1",
        "items": [
            {**pack_item("item-1", 1), "bounded_prerequisite_chain": bounded_chain(1)},
            {**pack_item("item-2", 2), "bounded_prerequisite_chain": bounded_chain(2)},
        ],
        "mutation_log": [],
    }

    observed = {finding["code"] for finding in task_pack_queue.validate_pack(pack)}

    assert (
        not {
            "prerequisite_chain_reduction_unsubstantiated",
            "prerequisite_chain_position_not_monotonic",
            "prerequisite_chain_position_reset",
        }
        & observed
    )


def test_task_pack_rejects_prerequisite_chain_root_or_position_reset() -> None:
    pack = {
        "schema_version": 1,
        "pack_id": "pack-prerequisite-reset",
        "status": "active",
        "goal": "Do not reset a recurring prerequisite chain.",
        "current_item_id": "item-1",
        "items": [
            {**pack_item("item-1", 1), "bounded_prerequisite_chain": bounded_chain(2)},
            {
                **pack_item("item-2", 2),
                "bounded_prerequisite_chain": bounded_chain(1, stable_root_id="root-B"),
            },
        ],
        "mutation_log": [],
    }

    observed = {finding["code"] for finding in task_pack_queue.validate_pack(pack)}

    assert "prerequisite_chain_root_drift" in observed
    assert "prerequisite_chain_position_not_monotonic" in observed
    assert "prerequisite_chain_position_reset" in observed


def test_task_pack_rejects_unsubstantiated_reduction_and_capped_none_successor() -> (
    None
):
    pack = {
        "schema_version": 1,
        "pack_id": "pack-prerequisite-invalid",
        "status": "active",
        "goal": "Reject vacuous prerequisite completion.",
        "current_item_id": "item-1",
        "items": [
            {
                **pack_item("item-1", 1),
                "bounded_prerequisite_chain": bounded_chain(
                    2,
                    mandatory_successor_kind="none",
                    residual_before=1,
                    residual_after=1,
                ),
            }
        ],
        "mutation_log": [],
    }

    observed = {finding["code"] for finding in task_pack_queue.validate_pack(pack)}

    assert "prerequisite_chain_reduction_unsubstantiated" in observed
    assert "prerequisite_chain_cap_without_successor" in observed


def test_task_pack_rejects_decreasing_scalars_without_observation_receipt() -> None:
    chain = bounded_chain(1)
    chain.pop("reduction_observation_receipt")
    pack = {
        "schema_version": 1,
        "pack_id": "pack-prerequisite-unbound",
        "status": "active",
        "goal": "Reject caller-authored reduction claims.",
        "current_item_id": "item-1",
        "items": [{**pack_item("item-1", 1), "bounded_prerequisite_chain": chain}],
        "mutation_log": [],
    }

    observed = {finding["code"] for finding in task_pack_queue.validate_pack(pack)}

    assert "prerequisite_chain_reduction_unsubstantiated" in observed


def test_store_routes_declared_completed_live_residual_to_repair(
    tmp_path: Path,
) -> None:
    pack_path = tmp_path / ".task" / "task_pack" / "pack-residual.json"
    pack = {
        "schema_version": 1,
        "pack_id": "pack-residual",
        "status": "completed",
        "goal": "Do not treat live residual work as absent.",
        "current_item_id": "item-1",
        "items": [pack_item("item-1", 1)],
        "mutation_log": [],
    }
    write_json(pack_path, pack)

    assert task_pack_queue.active_pack_candidates(tmp_path) == []
    findings = task_pack_queue.task_pack_store_findings(tmp_path)
    finding = next(
        item for item in findings if item["code"] == "task_pack_state_invalid"
    )
    assert finding["evidence"]["declared_status"] == "completed"
    assert finding["evidence"]["operational_status"] == "active"
    assert "pack_operational_status_mismatch" in finding["evidence"]["finding_codes"]
    with pytest.raises(SystemExit, match="requires lifecycle or contract repair"):
        task_pack_queue.active_pack(tmp_path)


def test_dependency_graph_rejects_unknown_self_cycle_topology_and_consumption_bypass() -> (
    None
):
    items = [
        {**pack_item("blocked-root", 1), "status": "blocked", "dependencies": []},
        {
            **pack_item("bypassed", 2),
            "status": "consumed",
            "dependencies": ["blocked-root"],
        },
        {**pack_item("self", 3), "dependencies": ["self"]},
        {**pack_item("cycle-a", 4), "dependencies": ["cycle-b"]},
        {**pack_item("cycle-b", 5), "dependencies": ["cycle-a", "unknown"]},
    ]
    pack = {
        "schema_version": 1,
        "pack_id": "pack-dependencies",
        "status": "completed",
        "goal": "Reject dependency bypass.",
        "current_item_id": None,
        "items": items,
        "mutation_log": [],
    }
    codes = {finding["code"] for finding in task_pack_queue.validate_pack(pack)}
    assert {
        "unknown_item_dependency",
        "self_item_dependency",
        "cyclic_item_dependency",
        "item_dependency_not_topological",
        "item_dependency_bypassed",
        "completed_pack_has_noncompleted_items",
    }.issubset(codes)


def test_blocked_promotion_requires_hash_bound_unblock_receipt(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    body = json.loads(pack_path.read_text(encoding="utf-8"))
    body["status"] = "blocked"
    body["current_item_id"] = None
    body["items"][0]["status"] = "blocked"
    body["items"][0]["blocker_signature"] = "blocked-signature"
    body["items"][1]["dependencies"] = ["item-1"]
    write_json(pack_path, body)
    selected_path, selected_body = task_pack_queue.active_pack(tmp_path)
    assert selected_path == pack_path
    assert selected_body["status"] == "blocked"
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    plan = promotion_plan(tmp_path)
    with pytest.raises(SystemExit, match="unblock_receipt"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))

    evidence = tmp_path / ".task" / "evidence" / "unblock.json"
    write_json(evidence, {"decision": "unblocked", "item_id": "item-1"})
    plan["unblock_receipt"] = {
        "schema_version": 1,
        "item_id": "item-1",
        "decision": "unblocked",
        "blocker_signature": "blocked-signature",
        "before_pack_sha256": plan["pack_coherence"]["before_pack_sha256"],
        "decision_evidence": [
            {
                "path": evidence.relative_to(tmp_path).as_posix(),
                "sha256": sha256(evidence),
            }
        ],
    }
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    promoted = json.loads(pack_path.read_text(encoding="utf-8"))["items"][0]
    assert promoted["status"] == "promoted"
    assert promoted["promotion"]["unblock_receipt"]["decision"] == "unblocked"


def test_insert_rejects_caller_owned_lifecycle_and_skip_rejects_consumed(
    tmp_path: Path,
) -> None:
    pack_path = write_pack(tmp_path)
    insert = {
        "action": "insert",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "items": [{**pack_item("injected", 3), "status": "consumed"}],
        "reason": "attempt lifecycle injection",
        "pack_coherence": current_pack_coherence(tmp_path, "insert"),
    }
    insert["pack_coherence"]["proposed_after_item_ids"] = [
        "item-1",
        "item-2",
        "injected",
    ]
    insert["pack_coherence"]["proposed_after_order"] = ["item-1", "item-2", "injected"]
    with pytest.raises(SystemExit, match="planning fields only"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, insert))

    body = json.loads(pack_path.read_text(encoding="utf-8"))
    body["items"][0]["status"] = "consumed"
    body["current_item_id"] = "item-2"
    write_json(pack_path, body)
    skip = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_ids": ["item-1"],
        "reason": "attempt history rewrite",
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    with pytest.raises(SystemExit, match="closed or in-flight"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, skip))


def test_reorder_freezes_closed_prefix_and_reorders_only_open_suffix(
    tmp_path: Path,
) -> None:
    pack_path = write_pack(tmp_path)
    body = json.loads(pack_path.read_text(encoding="utf-8"))
    body["items"][0]["status"] = "skipped"
    body["items"].append(pack_item("item-3", 3))
    body["current_item_id"] = "item-2"
    write_json(pack_path, body)
    reorder = {
        "action": "reorder",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_order": ["item-1", "item-3", "item-2"],
        "reason": "prioritize the open residual suffix",
        "pack_coherence": current_pack_coherence(tmp_path, "reorder"),
    }
    reorder["pack_coherence"]["proposed_after_item_ids"] = reorder["item_order"]
    reorder["pack_coherence"]["proposed_after_order"] = reorder["item_order"]
    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, reorder)) == 0

    illegal = {
        "action": "reorder",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_order": ["item-3", "item-1", "item-2"],
        "reason": "attempt to move closed history",
        "pack_coherence": current_pack_coherence(tmp_path, "reorder"),
    }
    illegal["pack_coherence"]["proposed_after_item_ids"] = illegal["item_order"]
    illegal["pack_coherence"]["proposed_after_order"] = illegal["item_order"]
    with pytest.raises(SystemExit, match="open residual suffix"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, illegal))


@pytest.mark.parametrize("in_flight_status", ["promoted", "in_progress"])
def test_reorder_freezes_in_flight_position_with_zero_durable_mutation(
    tmp_path: Path,
    in_flight_status: str,
) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-1\n", encoding="utf-8")
    assert (
        task_pack_queue.command_apply_mutation(
            mutation_args(tmp_path, initial_selection_plan(tmp_path, pack_path))
        )
        == 0
    )
    if in_flight_status == "in_progress":
        body = json.loads(pack_path.read_text(encoding="utf-8"))
        body["items"][0]["status"] = in_flight_status
        write_json(pack_path, body)

    before_pack = pack_path.read_bytes()
    before_durable_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task").rglob("*")
        if path.is_file()
    }
    reorder = {
        "action": "reorder",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_order": ["item-2", "item-1"],
        "reason": "attempt to move work around the active item",
        "pack_coherence": current_pack_coherence(tmp_path, "reorder"),
    }
    reorder["pack_coherence"]["proposed_after_item_ids"] = reorder["item_order"]
    reorder["pack_coherence"]["proposed_after_order"] = reorder["item_order"]

    with pytest.raises(SystemExit, match="open residual suffix"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, reorder))

    after_durable_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task").rglob("*")
        if path.is_file()
    }
    assert pack_path.read_bytes() == before_pack
    assert after_durable_files == before_durable_files


@pytest.mark.parametrize("in_flight_status", ["promoted", "in_progress"])
def test_insert_cannot_move_in_flight_position_and_leaves_no_durable_mutation(
    tmp_path: Path,
    in_flight_status: str,
) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-1\n", encoding="utf-8")
    assert (
        task_pack_queue.command_apply_mutation(
            mutation_args(tmp_path, initial_selection_plan(tmp_path, pack_path))
        )
        == 0
    )
    if in_flight_status == "in_progress":
        body = json.loads(pack_path.read_text(encoding="utf-8"))
        body["items"][0]["status"] = in_flight_status
        write_json(pack_path, body)

    before_pack = pack_path.read_bytes()
    before_durable_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task").rglob("*")
        if path.is_file()
    }
    insert = {
        "action": "insert",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "insert_before_item_id": "item-1",
        "items": [
            {
                "item_id": "item-new",
                "title": "item-new",
                "objective": "Perform bounded work.",
                "validation_profile": "current_only",
                "progress_target": "advanced",
            }
        ],
        "reason": "attempt to place planning work ahead of active execution",
        "pack_coherence": current_pack_coherence(tmp_path, "insert"),
    }
    proposed = ["item-new", "item-1", "item-2"]
    insert["pack_coherence"]["proposed_after_item_ids"] = proposed
    insert["pack_coherence"]["proposed_after_order"] = proposed

    with pytest.raises(SystemExit, match="after closed/in-flight history"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, insert))

    after_durable_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task").rglob("*")
        if path.is_file()
    }
    assert pack_path.read_bytes() == before_pack
    assert after_durable_files == before_durable_files


def test_insert_after_in_flight_item_preserves_active_position(tmp_path: Path) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-1\n", encoding="utf-8")
    assert (
        task_pack_queue.command_apply_mutation(
            mutation_args(tmp_path, initial_selection_plan(tmp_path, pack_path))
        )
        == 0
    )
    before = json.loads(pack_path.read_text(encoding="utf-8"))
    before_active = copy.deepcopy(before["items"][0])
    insert = {
        "action": "insert",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "insert_before_item_id": "item-2",
        "items": [
            {
                "item_id": "item-new",
                "title": "item-new",
                "objective": "Perform bounded work.",
                "validation_profile": "current_only",
                "progress_target": "advanced",
            }
        ],
        "reason": "add planning work after active execution",
        "pack_coherence": current_pack_coherence(tmp_path, "insert"),
    }
    proposed = ["item-1", "item-new", "item-2"]
    insert["pack_coherence"]["proposed_after_item_ids"] = proposed
    insert["pack_coherence"]["proposed_after_order"] = proposed

    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, insert)) == 0

    after = json.loads(pack_path.read_text(encoding="utf-8"))
    assert [item["item_id"] for item in after["items"]] == proposed
    assert after["items"][0] == before_active
    assert after["items"][1]["status"] == "inserted"


def test_insert_rejects_unknown_explicit_anchor_without_durable_mutation(
    tmp_path: Path,
) -> None:
    pack_path = write_pack(tmp_path)
    before_pack = pack_path.read_bytes()
    before_durable_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task").rglob("*")
        if path.is_file()
    }
    insert = {
        "action": "insert",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "insert_before_item_id": "item-does-not-exist",
        "items": [
            {
                "item_id": "item-new",
                "title": "item-new",
                "objective": "Perform bounded work.",
                "validation_profile": "current_only",
                "progress_target": "advanced",
            }
        ],
        "reason": "attempt insertion against a stale prerequisite anchor",
        "pack_coherence": current_pack_coherence(tmp_path, "insert"),
    }
    proposed = ["item-1", "item-2", "item-new"]
    insert["pack_coherence"]["proposed_after_item_ids"] = proposed
    insert["pack_coherence"]["proposed_after_order"] = proposed

    with pytest.raises(SystemExit, match="Explicit insert anchor does not resolve"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, insert))

    after_durable_files = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task").rglob("*")
        if path.is_file()
    }
    assert pack_path.read_bytes() == before_pack
    assert after_durable_files == before_durable_files


def test_ordinary_mutation_forward_recovers_write_before_receipt_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_path = write_pack(tmp_path)
    plan = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_ids": ["item-1"],
        "reason": "durably skip one item",
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    original_write_once = task_pack_queue.task_pack_mutation_journal._write_once
    failed = False

    def crash_once(path: Path, payload: bytes, label: str) -> str:
        nonlocal failed
        if label == "Task-pack mutation completion receipt" and not failed:
            failed = True
            raise RuntimeError("simulated receipt publication crash")
        return original_write_once(path, payload, label)

    monkeypatch.setattr(
        task_pack_queue.task_pack_mutation_journal, "_write_once", crash_once
    )
    with pytest.raises(RuntimeError, match="simulated receipt"):
        task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan))
    assert (
        json.loads(pack_path.read_text(encoding="utf-8"))["items"][0]["status"]
        == "skipped"
    )
    assert task_pack_queue.task_pack_mutation_journal.pending_transaction_ids(tmp_path)

    assert task_pack_queue.command_apply_mutation(mutation_args(tmp_path, plan)) == 0
    assert (
        task_pack_queue.task_pack_mutation_journal.pending_transaction_ids(tmp_path)
        == []
    )
    receipts = task_pack_queue.task_pack_mutation_journal.completed_for_plan(
        tmp_path, plan
    )
    assert len(receipts) == 1
    assert receipts[0]["status"] == "committed"
    coherence_receipt = {
        **receipts[0]["coherence_receipt"],
        "durable_receipt_ref": receipts[0]["receipt_ref"],
        "durable_receipt_sha256": receipts[0]["receipt_sha256"],
    }
    verified = task_pack_queue.task_pack_mutation_journal.validate_receipt_binding(
        tmp_path,
        plan,
        coherence_receipt,
    )
    assert verified["transaction_id"] == receipts[0]["transaction_id"]


def test_create_replay_recovers_requested_render_after_commit_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = {
        "action": "create_pack",
        "reason": "create a render-recovery fixture",
        "pack": {
            "schema_version": 1,
            "pack_id": "pack-render-create",
            "status": "active",
            "language": "ko",
            "goal": "Recover the requested Markdown projection.",
            "current_item_id": "item-1",
            "items": [pack_item("item-1", 1), pack_item("item-2", 2)],
            "mutation_log": [],
            "terminal_blocker": None,
        },
    }
    args = mutation_args(tmp_path, plan)
    args.render = True
    original = mutation_create.write_render

    def crash_after_commit(*_args: object, **_kwargs: object) -> Path:
        raise RuntimeError("simulated create render crash")

    monkeypatch.setattr(mutation_create, "write_render", crash_after_commit)
    with pytest.raises(RuntimeError, match="create render"):
        task_pack_queue.command_apply_mutation(args)

    pack_path = tmp_path / ".task/task_pack/pack-render-create.json"
    render_path = pack_path.with_suffix(".md")
    assert pack_path.is_file()
    assert not render_path.exists()
    monkeypatch.setattr(mutation_create, "write_render", original)

    assert task_pack_queue.command_apply_mutation(args) == 0
    assert render_path.is_file()


def test_existing_mutation_replay_recovers_requested_render_after_commit_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_path = write_pack(tmp_path)
    plan = {
        "action": "skip",
        "pack_path": str(pack_path.relative_to(tmp_path)),
        "item_ids": ["item-1"],
        "reason": "commit JSON before a simulated render crash",
        "pack_coherence": current_pack_coherence(tmp_path, "skip"),
    }
    args = mutation_args(tmp_path, plan)
    args.render = True
    original = mutation_finalize.write_render

    def crash_after_commit(*_args: object, **_kwargs: object) -> Path:
        raise RuntimeError("simulated mutation render crash")

    monkeypatch.setattr(mutation_finalize, "write_render", crash_after_commit)
    with pytest.raises(RuntimeError, match="mutation render"):
        task_pack_queue.command_apply_mutation(args)

    render_path = pack_path.with_suffix(".md")
    assert not render_path.exists()
    monkeypatch.setattr(mutation_finalize, "write_render", original)

    assert task_pack_queue.command_apply_mutation(args) == 0
    assert render_path.is_file()


def test_consumption_replay_recovers_requested_render_after_commit_crash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_path = write_pack(tmp_path)
    (tmp_path / "task.md").write_text("# task-2\n", encoding="utf-8")
    assert (
        task_pack_queue.command_apply_mutation(
            mutation_args(tmp_path, promotion_plan(tmp_path))
        )
        == 0
    )
    provenance = authoritative_provenance(tmp_path, validated_task_id="task-2")
    coherence = current_pack_coherence(tmp_path, "mark_consumed")
    original = task_pack_consumption.write_render

    def crash_after_commit(*_args: object, **_kwargs: object) -> Path:
        raise RuntimeError("simulated consumption render crash")

    monkeypatch.setattr(task_pack_consumption, "write_render", crash_after_commit)
    with pytest.raises(RuntimeError, match="consumption render"):
        consume_cli(
            tmp_path,
            provenance,
            coherence=coherence,
            render=True,
        )

    render_path = pack_path.with_suffix(".md")
    assert not render_path.exists()
    monkeypatch.setattr(task_pack_consumption, "write_render", original)

    assert (
        consume_cli(
            tmp_path,
            provenance,
            coherence=coherence,
            render=True,
        )
        == 0
    )
    assert render_path.is_file()
