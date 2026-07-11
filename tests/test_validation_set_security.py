from __future__ import annotations

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


def run_script(name: str, *args: object) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)], cwd=REPO, env=env, text=True, capture_output=True, check=False)


def make_valid_set(root: Path) -> Path:
    set_root = root / "sets" / "secure"
    source = root / "sources" / "item-1.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("secure fixture\n", encoding="utf-8")
    item = {
        "item_id": "item-1",
        "source_class": "test_fixture",
        "evidence_status": "candidate",
        "source_ref": source.relative_to(root).as_posix(),
        "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_binding_type": "local_file",
        "task_family": "parser",
        "oracle_ids": ["oracle-1"],
    }
    write_jsonl(set_root / "validation_set_items.jsonl", [item])
    write_jsonl(set_root / "validation_set_labels.jsonl", [])
    write_json(set_root / "oracle_manifest.json", {"validation_set_id": "secure-1", "oracle_count": 1, "oracles": [{"oracle_id": "oracle-1", "oracle_type": "deterministic", "target": "item", "description": "Trace fields", "required_fields": ["item_id", "source_ref"]}]})
    write_json(set_root / "split_manifest.json", {"validation_set_id": "secure-1", "sealed_holdout_status": "not_applicable", "label_visibility_policy": "dev labels visible", "splits": {"dev": ["item-1"]}})
    write_json(set_root / "leakage_report.json", {"status": "ok", "execution_status": "completed", "item_count": 1, "label_count": 0, "findings": []})
    write_json(
        set_root / "validation_set_manifest.json",
        {
            "manifest_schema_version": 2,
            "validation_set_id": "secure-1",
            "task_id": "task-1",
            "validation_set_status": "candidate_only",
            "quality_tier": "candidate",
            "not_gold": True,
            "created_at": "2026-07-11T00:00:00+00:00",
            "source_class_distribution": {"test_fixture": 1},
            "item_count": 1,
            "label_count": 0,
            "oracle_count": 1,
            "items_path": "sets/secure/validation_set_items.jsonl",
            "labels_path": "sets/secure/validation_set_labels.jsonl",
            "oracle_manifest_path": "sets/secure/oracle_manifest.json",
            "oracle_results_path": "sets/secure/oracle_results.json",
            "split_manifest_path": "sets/secure/split_manifest.json",
            "leakage_report_path": "sets/secure/leakage_report.json",
        },
    )
    write_json(
        set_root / "oracle_results.json",
        {
            "oracle_results_schema_version": 1,
            "runner": "run_validation_oracles.py",
            "validation_set_id": "secure-1",
            "status": "not_evaluated",
            "execution_status": "not_evaluated",
            "items_sha256": hashlib.sha256((set_root / "validation_set_items.jsonl").read_bytes()).hexdigest(),
            "oracle_manifest_sha256": hashlib.sha256((set_root / "oracle_manifest.json").read_bytes()).hexdigest(),
            "item_count": 1,
            "oracle_count": 1,
            "runnable_oracle_count": 0,
            "result_count": 0,
            "failed_count": 0,
            "results": [],
        },
    )
    oracle_run = run_script("run_validation_oracles.py", "--root", root, "--set-root", set_root)
    assert oracle_run.returncode == 0, oracle_run.stdout + oracle_run.stderr
    finalized = run_script("finalize_validation_set.py", "--root", root, "--set-root", set_root)
    assert finalized.returncode == 0, finalized.stdout + finalized.stderr
    return set_root


def codes(report: dict[str, Any]) -> set[str]:
    return {str(finding.get("code")) for finding in report.get("findings", [])}


def freeze(root: Path, set_root: Path) -> subprocess.CompletedProcess[str]:
    return run_script("freeze_validation_set_root.py", "--root", root, "--set-root", set_root)


def verify(root: Path, set_root: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    result = run_script("verify_validation_set_root.py", "--root", root, "--set-root", set_root)
    return result, json.loads(result.stdout)


def canonical_payload(root_doc: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in root_doc.items() if key != "root_sha256"}


def rebind(root_doc: dict[str, Any]) -> None:
    root_doc["root_sha256"] = hashlib.sha256(json.dumps(canonical_payload(root_doc), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def test_freeze_and_verify_valid_minimal_set(tmp_path: Path) -> None:
    set_root = make_valid_set(tmp_path)
    frozen = freeze(tmp_path, set_root)
    assert frozen.returncode == 0, frozen.stdout + frozen.stderr
    root_doc = json.loads((set_root / "validation_set_root.json").read_text(encoding="utf-8"))
    assert root_doc["root_sha256"]
    assert all(entry["sha256"] for entry in root_doc["file_hashes"].values())
    result, report = verify(tmp_path, set_root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert report["status"] == "verified"


def test_verifier_rejects_null_hash_even_with_rebound_root(tmp_path: Path) -> None:
    set_root = make_valid_set(tmp_path)
    assert freeze(tmp_path, set_root).returncode == 0
    root_file = set_root / "validation_set_root.json"
    root_doc = json.loads(root_file.read_text(encoding="utf-8"))
    root_doc["file_hashes"]["items"]["sha256"] = None
    rebind(root_doc)
    write_json(root_file, root_doc)
    result, report = verify(tmp_path, set_root)
    assert result.returncode == 2
    assert "invalid_file_sha256" in codes(report)


def test_verifier_rejects_mutated_bound_file(tmp_path: Path) -> None:
    set_root = make_valid_set(tmp_path)
    assert freeze(tmp_path, set_root).returncode == 0
    with (set_root / "validation_set_items.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"item_id": "item-2"}) + "\n")
    result, report = verify(tmp_path, set_root)
    assert result.returncode == 2
    assert "file_sha256_mismatch" in codes(report)
    assert "bound_validation_set_invalid" in codes(report)


def test_verifier_rejects_mutated_root_metadata(tmp_path: Path) -> None:
    set_root = make_valid_set(tmp_path)
    assert freeze(tmp_path, set_root).returncode == 0
    root_file = set_root / "validation_set_root.json"
    root_doc = json.loads(root_file.read_text(encoding="utf-8"))
    root_doc["validation_set_id"] = "tampered"
    write_json(root_file, root_doc)
    result, report = verify(tmp_path, set_root)
    assert result.returncode == 2
    assert "root_sha256_mismatch" in codes(report)
    assert "root_manifest_metadata_mismatch" in codes(report)


def test_verifier_binds_root_creation_metadata(tmp_path: Path) -> None:
    set_root = make_valid_set(tmp_path)
    assert freeze(tmp_path, set_root).returncode == 0
    root_file = set_root / "validation_set_root.json"
    root_doc = json.loads(root_file.read_text(encoding="utf-8"))
    root_doc["created_at"] = "2099-01-01T00:00:00+00:00"
    write_json(root_file, root_doc)

    result, report = verify(tmp_path, set_root)

    assert result.returncode == 2
    assert "root_sha256_mismatch" in codes(report)


def test_freeze_rejects_missing_and_invalid_inputs(tmp_path: Path) -> None:
    set_root = make_valid_set(tmp_path / "missing")
    (set_root / "validation_set_labels.jsonl").unlink()
    result = freeze(tmp_path / "missing", set_root)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "block"
    assert not (set_root / "validation_set_root.json").exists()

    set_root = make_valid_set(tmp_path / "invalid")
    (set_root / "oracle_manifest.json").write_text("{not-json", encoding="utf-8")
    result = freeze(tmp_path / "invalid", set_root)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "block"


def test_freeze_rejects_manifest_path_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    set_root = make_valid_set(root)
    outside = tmp_path / "outside-items.jsonl"
    write_jsonl(outside, [{"item_id": "outside"}])
    manifest_file = set_root / "validation_set_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest["items_path"] = str(outside)
    write_json(manifest_file, manifest)
    result = freeze(root, set_root)
    assert result.returncode == 2
    assert "escape" in json.loads(result.stdout)["error"] or "invalid" in json.loads(result.stdout)["error"]


def test_freeze_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    set_root = make_valid_set(root)
    outside = tmp_path / "outside-items.jsonl"
    write_jsonl(outside, [{"item_id": "outside"}])
    link = root / "escaped-items.jsonl"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    manifest_file = set_root / "validation_set_manifest.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    manifest["items_path"] = "escaped-items.jsonl"
    write_json(manifest_file, manifest)
    result = freeze(root, set_root)
    assert result.returncode == 2
    assert not (set_root / "validation_set_root.json").exists()


def test_verifier_rejects_rebound_path_and_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    set_root = make_valid_set(root)
    assert freeze(root, set_root).returncode == 0
    outside = tmp_path / "outside-items.jsonl"
    write_jsonl(outside, [{"item_id": "outside"}])
    link = root / "escaped-items.jsonl"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    root_file = set_root / "validation_set_root.json"
    root_doc = json.loads(root_file.read_text(encoding="utf-8"))
    root_doc["file_hashes"]["items"]["path"] = "escaped-items.jsonl"
    root_doc["file_hashes"]["items"]["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    rebind(root_doc)
    write_json(root_file, root_doc)
    result, report = verify(root, set_root)
    assert result.returncode == 2
    assert "hashed_file_unavailable" in codes(report)
