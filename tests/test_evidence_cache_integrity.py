from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evidence_cache = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "evidence_cache.py",
    "evidence_cache_integrity",
)


def args_for(
    root: Path,
    *,
    command: str | None = "python check.py",
    inputs: list[str] | None = None,
    evidence_paths: list[str] | None = None,
    task_id: str | None = "task-1",
    result_status: str = "passed",
) -> argparse.Namespace:
    return argparse.Namespace(
        root=str(root),
        command=command,
        profile="current_only",
        input=list(inputs or []),
        schema=[],
        dependency=[],
        validation_set_root=[],
        oracle_manifest=[],
        split_manifest=[],
        leakage_report=[],
        source_artifact=[],
        schema_contract_version=[],
        env=[],
        extra_json=None,
        result_status=result_status,
        evidence_path=list(evidence_paths or []),
        task_id=task_id,
        cycle_id="cycle-1",
    )


def create_source_and_evidence(root: Path) -> tuple[Path, Path]:
    source = root / "input.json"
    evidence = root / "proof.json"
    source.write_text('{"input": 1}\n', encoding="utf-8")
    evidence.write_text('{"passed": true}\n', encoding="utf-8")
    return source, evidence


def test_fingerprint_requires_command_and_hashed_context(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty command"):
        evidence_cache.build_fingerprint(args_for(tmp_path, command=None))

    with pytest.raises(ValueError, match="at least one hashed"):
        evidence_cache.build_fingerprint(args_for(tmp_path))

    with pytest.raises(ValueError, match="must exist and be hashable"):
        evidence_cache.build_fingerprint(args_for(tmp_path, inputs=["missing.json"]))

    source = tmp_path / "input.json"
    source.write_text("{}\n", encoding="utf-8")
    fingerprint = evidence_cache.build_fingerprint(args_for(tmp_path, inputs=["input.json"]))
    assert fingerprint["format_version"] == evidence_cache.CACHE_FORMAT_VERSION
    assert fingerprint["details"]["inputs"][0]["sha256"]


def test_relative_custom_cache_path_is_root_relative(tmp_path: Path) -> None:
    assert evidence_cache.cache_path(tmp_path, "var/cache.jsonl") == (tmp_path / "var" / "cache.jsonl").resolve()
    with pytest.raises(ValueError, match="escapes workspace root"):
        evidence_cache.cache_path(tmp_path, "../outside.jsonl")


def test_cli_store_and_check_use_root_relative_custom_cache(tmp_path: Path) -> None:
    create_source_and_evidence(tmp_path)
    script = ROOT / "orchestrate-task-cycle" / "scripts" / "evidence_cache.py"
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    common = [
        sys.executable,
        "-B",
        str(script),
        "--root",
        str(tmp_path),
        "--command",
        "python check.py",
        "--input",
        "input.json",
    ]
    stored = subprocess.run(
        [
            sys.executable,
            "-B",
            str(script),
            "store",
            "--root",
            str(tmp_path),
            "--command",
            "python check.py",
            "--input",
            "input.json",
            "--cache",
            "var/cache.jsonl",
            "--result-status",
            "passed",
            "--evidence-path",
            "proof.json",
        ],
        cwd=tmp_path.parent,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    stored_json = json.loads(stored.stdout)
    assert Path(stored_json["cache_path"]) == tmp_path / "var" / "cache.jsonl"

    checked = subprocess.run(
        [common[0], common[1], common[2], "check", *common[3:], "--cache", "var/cache.jsonl"],
        cwd=tmp_path.parent,
        env=environment,
        check=True,
        text=True,
        capture_output=True,
    )
    assert json.loads(checked.stdout)["classification"] == "reuse"


def test_exact_match_reuses_only_while_stored_evidence_hash_matches(tmp_path: Path) -> None:
    _, evidence = create_source_and_evidence(tmp_path)
    args = args_for(tmp_path, inputs=["input.json"], evidence_paths=["proof.json"])
    fingerprint = evidence_cache.build_fingerprint(args)
    path = evidence_cache.cache_path(tmp_path, None)
    stored = evidence_cache.store_record(path, fingerprint, args)

    reusable = evidence_cache.classify_candidate(fingerprint, evidence_cache.read_records(path), False, tmp_path)
    assert reusable["classification"] == "reuse"
    assert reusable["evidence_verification"]["valid"] is True
    assert stored["evidence_refs"][0]["sha256"]

    evidence.write_text('{"passed": false}\n', encoding="utf-8")
    changed = evidence_cache.classify_candidate(fingerprint, evidence_cache.read_records(path), False, tmp_path)
    assert changed["classification"] == "unsafe_to_reuse"
    assert changed["reason"] == "stored_evidence_missing_or_changed"

    evidence.unlink()
    missing = evidence_cache.classify_candidate(fingerprint, evidence_cache.read_records(path), False, tmp_path)
    assert missing["classification"] == "unsafe_to_reuse"


def test_store_requires_existing_hashed_evidence(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text("{}\n", encoding="utf-8")
    args = args_for(tmp_path, inputs=["input.json"])
    fingerprint = evidence_cache.build_fingerprint(args)

    with pytest.raises(ValueError, match="at least one --evidence-path"):
        evidence_cache.store_record(evidence_cache.cache_path(tmp_path, None), fingerprint, args)

    args.evidence_path = ["missing-proof.json"]
    with pytest.raises(ValueError, match="must exist and be hashable"):
        evidence_cache.store_record(evidence_cache.cache_path(tmp_path, None), fingerprint, args)


def test_changed_fingerprint_is_stale_only_when_prior_evidence_is_intact(tmp_path: Path) -> None:
    source, _ = create_source_and_evidence(tmp_path)
    args = args_for(tmp_path, inputs=["input.json"], evidence_paths=["proof.json"])
    first = evidence_cache.build_fingerprint(args)
    path = evidence_cache.cache_path(tmp_path, None)
    evidence_cache.store_record(path, first, args)

    source.write_text('{"input": 2}\n', encoding="utf-8")
    second = evidence_cache.build_fingerprint(args)
    result = evidence_cache.classify_candidate(second, evidence_cache.read_records(path), False, tmp_path)
    assert result["classification"] == "stale"


def test_malformed_or_unknown_version_cache_fails_closed_without_append(tmp_path: Path) -> None:
    create_source_and_evidence(tmp_path)
    args = args_for(tmp_path, inputs=["input.json"], evidence_paths=["proof.json"])
    fingerprint = evidence_cache.build_fingerprint(args)
    path = evidence_cache.cache_path(tmp_path, None)
    evidence_cache.store_record(path, fingerprint, args)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{\n")
    before = path.read_bytes()

    with pytest.raises(ValueError, match="malformed evidence cache JSON"):
        evidence_cache.read_records(path)
    with pytest.raises(ValueError, match="malformed evidence cache JSON"):
        evidence_cache.store_record(path, fingerprint, args)
    assert path.read_bytes() == before

    path.write_text(
        json.dumps(
            {
                "format_version": evidence_cache.CACHE_FORMAT_VERSION + 1,
                "fingerprint": "x",
                "details": {},
                "result_status": "passed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported evidence cache format_version"):
        evidence_cache.read_records(path)


def test_versionless_legacy_record_without_evidence_hashes_is_unsafe(tmp_path: Path) -> None:
    create_source_and_evidence(tmp_path)
    args = args_for(tmp_path, inputs=["input.json"], evidence_paths=["proof.json"])
    fingerprint = evidence_cache.build_fingerprint(args)
    path = evidence_cache.cache_path(tmp_path, None)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "fingerprint": fingerprint["fingerprint"],
                "details": fingerprint["details"],
                "result_status": "passed",
                "evidence_paths": ["proof.json"],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    records = evidence_cache.read_records(path)
    result = evidence_cache.classify_candidate(fingerprint, records, False, tmp_path)
    assert result["classification"] == "unsafe_to_reuse"
    assert result["reason"] == "evidence_hashes_missing"


def test_concurrent_stores_produce_complete_unique_records(tmp_path: Path) -> None:
    create_source_and_evidence(tmp_path)
    base_args = args_for(tmp_path, inputs=["input.json"], evidence_paths=["proof.json"])
    fingerprint = evidence_cache.build_fingerprint(base_args)
    path = evidence_cache.cache_path(tmp_path, None)

    def store(index: int) -> str:
        args = args_for(
            tmp_path,
            inputs=["input.json"],
            evidence_paths=["proof.json"],
            task_id=f"task-{index}",
        )
        return str(evidence_cache.store_record(path, fingerprint, args)["record_id"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        record_ids = list(executor.map(store, range(32)))

    records = evidence_cache.read_records(path)
    assert len(records) == 32
    assert len(set(record_ids)) == 32
    assert len({record["record_id"] for record in records}) == 32
    assert all(record["format_version"] == evidence_cache.CACHE_FORMAT_VERSION for record in records)
