from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "build-validation-set-with-agents" / "scripts"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in values), encoding="utf-8")


def run_module(command: str, *args: object) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(SCRIPTS)
    return subprocess.run(
        [sys.executable, "-m", "build_validation_set_with_agents", command, *(str(arg) for arg in args)],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def make_set(root: Path, *, status: str = "complete", items: list[dict[str, Any]] | None = None) -> tuple[Path, dict[str, Any]]:
    set_root = root / "sets" / "minimal"
    default_items = items is None
    if default_items:
        source = root / "sources" / "item-1.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("fixture item 1\n", encoding="utf-8")
        items = [
            {
                "item_id": "item-1",
                "source_class": "test_fixture",
                "evidence_status": "candidate",
                "source_ref": source.relative_to(root).as_posix(),
                "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
                "source_binding_type": "local_file",
                "task_family": "parser",
                "oracle_ids": ["oracle-1"],
            }
        ]
    else:
        items = copy.deepcopy(items)
    labels: list[dict[str, Any]] = []
    oracles = {
        "validation_set_id": "set-1",
        "oracle_count": 1,
        "oracles": [
            {
                "oracle_id": "oracle-1",
                "oracle_type": "deterministic",
                "target": "item",
                "description": "Require traceability fields.",
                "required_fields": ["item_id", "source_class", "evidence_status", "source_ref", "task_family"],
            }
        ],
    }
    splits = {
        "validation_set_id": "set-1",
        "sealed_holdout_status": "not_applicable",
        "label_visibility_policy": "dev labels visible",
        "splits": {"dev": [item["item_id"] for item in items if "item_id" in item]},
    }
    leakage = {
        "status": "ok" if items else "not_evaluated",
        "execution_status": "completed" if items else "not_evaluated",
        "item_count": len(items),
        "label_count": len(labels),
        "findings": [],
    }
    paths = {
        "items_path": "sets/minimal/validation_set_items.jsonl",
        "labels_path": "sets/minimal/validation_set_labels.jsonl",
        "oracle_manifest_path": "sets/minimal/oracle_manifest.json",
        "split_manifest_path": "sets/minimal/split_manifest.json",
        "leakage_report_path": "sets/minimal/leakage_report.json",
        "oracle_results_path": "sets/minimal/oracle_results.json",
    }
    manifest = {
        "manifest_schema_version": 2,
        "validation_set_id": "set-1",
        "task_id": "task-1",
        "validation_set_status": "candidate_only" if status == "complete" and default_items else status,
        "quality_tier": "candidate",
        "not_gold": True,
        "created_at": "2026-07-11T00:00:00+00:00",
        "source_class_distribution": {"test_fixture": len(items)} if items else {},
        "item_count": len(items),
        "label_count": len(labels),
        "oracle_count": 1,
        **paths,
    }
    write_jsonl(set_root / "validation_set_items.jsonl", items)
    write_jsonl(set_root / "validation_set_labels.jsonl", labels)
    write_json(set_root / "oracle_manifest.json", oracles)
    write_json(set_root / "split_manifest.json", splits)
    write_json(set_root / "leakage_report.json", leakage)
    write_json(
        set_root / "oracle_results.json",
        {
            "oracle_results_schema_version": 1,
            "runner": "run_validation_oracles.py",
            "validation_set_id": "set-1",
            "status": "not_evaluated",
            "execution_status": "not_evaluated",
            "items_sha256": hashlib.sha256((set_root / "validation_set_items.jsonl").read_bytes()).hexdigest(),
            "oracle_manifest_sha256": hashlib.sha256((set_root / "oracle_manifest.json").read_bytes()).hexdigest(),
            "item_count": len(items),
            "oracle_count": 1,
            "runnable_oracle_count": 0,
            "result_count": 0,
            "failed_count": 0,
            "results": [],
        },
    )
    write_json(set_root / "validation_set_manifest.json", manifest)
    if status == "complete" and default_items:
        oracle_run = run_module("run-oracles", "--root", root, "--set-root", set_root)
        assert oracle_run.returncode == 0, oracle_run.stdout + oracle_run.stderr
        finalized = run_module("finalize", "--root", root, "--set-root", set_root)
        assert finalized.returncode == 0, finalized.stdout + finalized.stderr
        manifest = json.loads((set_root / "validation_set_manifest.json").read_text(encoding="utf-8"))
    return set_root, manifest


def validate(root: Path, set_root: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    result = run_module("validate", "--root", root, "--set-root", set_root)
    return result, json.loads(result.stdout)


def finding_codes(report: dict[str, Any]) -> set[str]:
    return {str(finding.get("code")) for finding in report.get("findings", [])}


def test_valid_minimal_consumable_set_passes(tmp_path: Path) -> None:
    set_root, _ = make_set(tmp_path)
    result, report = validate(tmp_path, set_root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "ok"
    assert report["readiness"] == "consumable"


def test_empty_complete_set_is_blocked_but_empty_candidate_is_explicit(tmp_path: Path) -> None:
    complete_root, _ = make_set(tmp_path / "complete", items=[])
    result, report = validate(tmp_path / "complete", complete_root)
    assert result.returncode == 2
    assert "empty_consumable_validation_set" in finding_codes(report)
    assert report["status"] != "ok"

    candidate_root, _ = make_set(tmp_path / "candidate", status="candidate_only", items=[])
    result, report = validate(tmp_path / "candidate", candidate_root)
    assert result.returncode == 0
    assert report["status"] == "warn"
    assert report["readiness"] == "candidate"
    assert "leakage_not_evaluated" in finding_codes(report)


def test_empty_packager_output_remains_a_frozen_candidate_not_consumable_evidence(tmp_path: Path) -> None:
    built = run_module("build", "--root", tmp_path, "--set-id", "empty-candidate")
    assert built.returncode == 0, built.stdout + built.stderr
    build_report = json.loads(built.stdout)
    assert build_report["status"] == "candidate_only"
    assert build_report["readiness"] == "not_evaluated"
    set_root = tmp_path / ".validation" / "sets" / "empty-candidate"
    result, report = validate(tmp_path, set_root)
    assert result.returncode == 0
    assert report["status"] == "warn"
    assert report["readiness"] == "candidate"
    frozen = run_module("freeze", "--root", tmp_path, "--set-root", set_root)
    assert frozen.returncode == 0, frozen.stdout + frozen.stderr
    verified = run_module("verify-root", "--root", tmp_path, "--set-root", set_root)
    verify_report = json.loads(verified.stdout)
    assert verified.returncode == 0
    assert verify_report["status"] == "verified"
    assert verify_report["readiness"] == "candidate"
    assert verify_report["validation_set_status"] == "candidate_only"


def test_empty_oracle_and_leakage_runs_never_pass_or_report_ok(tmp_path: Path) -> None:
    items = tmp_path / "items.jsonl"
    oracle_manifest = tmp_path / "oracles.json"
    labels = tmp_path / "labels.jsonl"
    write_jsonl(items, [])
    write_jsonl(labels, [])
    write_json(oracle_manifest, {"oracles": []})

    oracle_result = run_module("run-oracles", "--items", items, "--oracle-manifest", oracle_manifest)
    oracle_report = json.loads(oracle_result.stdout)
    assert oracle_result.returncode == 3
    assert oracle_report["status"] == "not_evaluated"
    assert oracle_report["execution_status"] == "not_evaluated"

    leakage_result = run_module("leakage", "--items", items, "--labels", labels)
    leakage_report = json.loads(leakage_result.stdout)
    assert leakage_result.returncode == 3
    assert leakage_report["status"] == "not_evaluated"
    assert leakage_report["execution_status"] == "not_evaluated"


def test_labels_without_items_block_leakage_instead_of_becoming_not_evaluated(tmp_path: Path) -> None:
    items = tmp_path / "items.jsonl"
    labels = tmp_path / "labels.jsonl"
    write_jsonl(items, [])
    write_jsonl(labels, [{"label_id": "label-1", "item_id": "missing"}])
    result = run_module("leakage", "--items", items, "--labels", labels)
    report = json.loads(result.stdout)
    assert result.returncode == 2
    assert report["status"] == "block"
    assert any(finding.get("code") == "label_references_missing_item" for finding in report["findings"])


@pytest.mark.parametrize(
    "field",
    [
        "validation_set_id",
        "validation_set_status",
        "quality_tier",
        "not_gold",
        "created_at",
        "source_class_distribution",
        "item_count",
        "label_count",
        "oracle_count",
        "items_path",
        "labels_path",
        "oracle_manifest_path",
        "split_manifest_path",
        "leakage_report_path",
    ],
)
def test_every_required_manifest_field_is_enforced(tmp_path: Path, field: str) -> None:
    set_root, manifest = make_set(tmp_path)
    manifest.pop(field)
    write_json(set_root / "validation_set_manifest.json", manifest)
    result, report = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert "missing_manifest_field" in finding_codes(report)


@pytest.mark.parametrize("missing", ["item_id", "source_class", "evidence_status", "source_trace", "task_classification"])
def test_every_required_item_field_or_alternative_is_enforced(tmp_path: Path, missing: str) -> None:
    item = {
        "item_id": "item-1",
        "source_class": "test_fixture",
        "evidence_status": "candidate",
        "source_ref": "fixture:item-1",
        "task_family": "parser",
    }
    if missing == "source_trace":
        item.pop("source_ref")
    elif missing == "task_classification":
        item.pop("task_family")
    else:
        item.pop(missing)
    set_root, _ = make_set(tmp_path, items=[item])
    result, report = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert finding_codes(report) & {"missing_item_field", "missing_item_source_trace", "missing_item_task_classification"}


@pytest.mark.parametrize("field", ["label_id", "item_id", "label_type", "label_status"])
def test_every_required_label_field_is_enforced(tmp_path: Path, field: str) -> None:
    set_root, manifest = make_set(tmp_path)
    label = {"label_id": "label-1", "item_id": "item-1", "label_type": "deterministic", "label_status": "accepted"}
    label.pop(field)
    write_jsonl(set_root / "validation_set_labels.jsonl", [label])
    manifest["label_count"] = 1
    write_json(set_root / "validation_set_manifest.json", manifest)
    leakage = json.loads((set_root / "leakage_report.json").read_text(encoding="utf-8"))
    leakage["label_count"] = 1
    write_json(set_root / "leakage_report.json", leakage)
    result, report = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert "missing_label_field" in finding_codes(report)


def test_truthy_false_strings_are_not_json_booleans(tmp_path: Path) -> None:
    set_root, manifest = make_set(tmp_path)
    manifest["not_gold"] = "false"
    manifest["fully_deterministic_authoritative_oracle"] = "false"
    items = [json.loads((set_root / "validation_set_items.jsonl").read_text(encoding="utf-8"))]
    items[0]["premise_satisfied"] = "false"
    write_jsonl(set_root / "validation_set_items.jsonl", items)
    write_json(set_root / "validation_set_manifest.json", manifest)
    result, report = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert "invalid_boolean_type" in finding_codes(report)


def test_count_mismatch_blocks_complete_but_warns_candidate(tmp_path: Path) -> None:
    set_root, manifest = make_set(tmp_path / "complete")
    manifest["item_count"] = 2
    write_json(set_root / "validation_set_manifest.json", manifest)
    result, report = validate(tmp_path / "complete", set_root)
    assert result.returncode == 2
    assert "manifest_count_mismatch" in finding_codes(report)

    set_root, manifest = make_set(tmp_path / "candidate", status="candidate_only")
    manifest["item_count"] = 2
    write_json(set_root / "validation_set_manifest.json", manifest)
    result, report = validate(tmp_path / "candidate", set_root)
    assert result.returncode == 0
    assert report["status"] == "warn"


def test_complete_requires_executed_leakage_and_integral_splits(tmp_path: Path) -> None:
    set_root, _ = make_set(tmp_path)
    write_json(set_root / "leakage_report.json", {"status": "not_run", "execution_status": "not_evaluated", "item_count": 1, "label_count": 0, "findings": []})
    split = json.loads((set_root / "split_manifest.json").read_text(encoding="utf-8"))
    split["splits"] = {"dev": [], "regression": ["missing-item"]}
    write_json(set_root / "split_manifest.json", split)
    result, report = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert {"leakage_not_evaluated", "split_references_unknown_item", "items_missing_from_splits"} <= finding_codes(report)


def test_raw_body_field_name_is_forbidden_even_when_empty(tmp_path: Path) -> None:
    set_root, _ = make_set(tmp_path)
    item = json.loads((set_root / "validation_set_items.jsonl").read_text(encoding="utf-8"))
    item["rawBody"] = ""
    write_jsonl(set_root / "validation_set_items.jsonl", [item])
    result, report = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert "raw_body_field_persisted" in finding_codes(report)


def test_gold_requires_concrete_human_or_authoritative_oracle_evidence(tmp_path: Path) -> None:
    set_root, manifest = make_set(tmp_path / "invalid")
    manifest.update({"quality_tier": "gold", "not_gold": False, "fully_deterministic_authoritative_oracle": True, "authoritative_oracle_ids": ["oracle-1"]})
    write_json(set_root / "validation_set_manifest.json", manifest)
    result, report = validate(tmp_path / "invalid", set_root)
    assert result.returncode == 2
    assert "gold_without_concrete_authoritative_evidence" in finding_codes(report)

    set_root, manifest = make_set(tmp_path / "valid")
    manifest.update({"quality_tier": "gold", "not_gold": False, "fully_deterministic_authoritative_oracle": True, "authoritative_oracle_ids": ["oracle-1"]})
    oracle_manifest = json.loads((set_root / "oracle_manifest.json").read_text(encoding="utf-8"))
    oracle_manifest["oracles"][0].update({"authoritative": True, "evidence_paths": ["evidence/oracle-run.json"]})
    write_json(set_root / "oracle_manifest.json", oracle_manifest)
    write_json(set_root / "validation_set_manifest.json", manifest)
    oracle_run = run_module("run-oracles", "--root", tmp_path / "valid", "--set-root", set_root)
    assert oracle_run.returncode == 0, oracle_run.stdout + oracle_run.stderr
    finalized = run_module("finalize", "--root", tmp_path / "valid", "--set-root", set_root)
    assert finalized.returncode == 0, finalized.stdout + finalized.stderr
    result, report = validate(tmp_path / "valid", set_root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "ok"
