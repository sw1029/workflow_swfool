from __future__ import annotations

import argparse
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
    path.parent.mkdir(parents=True)
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


def mutation_args(root: Path, plan: dict[str, Any]) -> argparse.Namespace:
    return argparse.Namespace(
        root=str(root),
        plan=json.dumps(plan),
        action=None,
        pack=None,
        language="ko",
        render=False,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


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
    return plan


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
