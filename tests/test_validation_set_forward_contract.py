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
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS / name), *(str(arg) for arg in args)],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def report(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(result.stdout)


def codes(value: dict[str, Any]) -> set[str]:
    return {str(finding.get("code")) for finding in value.get("findings", [])}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def build_candidate(root: Path, *, set_id: str = "forward", items: list[dict[str, Any]]) -> Path:
    candidate_path = root / "input" / f"{set_id}-items.jsonl"
    write_jsonl(candidate_path, items)
    result = run_script(
        "build_validation_set.py",
        "--root",
        root,
        "--set-id",
        set_id,
        "--task-id",
        "task-forward-contract",
        "--items",
        candidate_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert report(result)["status"] == "candidate_only"
    return root / ".validation" / "sets" / set_id


def local_candidate(root: Path, *, set_id: str = "forward") -> Path:
    source = root / "source" / f"{set_id}.rec"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("acct_1|1250|USD\n", encoding="utf-8")
    return build_candidate(
        root,
        set_id=set_id,
        items=[
            {
                "item_id": f"{set_id}-item",
                "source_class": "synthetic_fixture",
                "evidence_status": "candidate",
                "source_ref": source.relative_to(root).as_posix(),
                "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
                "task_family": "pipe_record_parser",
            }
        ],
    )


def run_leakage(root: Path, set_root: Path) -> None:
    result = run_script(
        "leakage_check.py",
        "--items",
        set_root / "validation_set_items.jsonl",
        "--labels",
        set_root / "validation_set_labels.jsonl",
        "--output",
        set_root / "leakage_report.json",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def run_oracles(root: Path, set_root: Path) -> None:
    result = run_script("run_validation_oracles.py", "--root", root, "--set-root", set_root)
    assert result.returncode == 0, result.stdout + result.stderr


def finalize(root: Path, set_root: Path) -> subprocess.CompletedProcess[str]:
    return run_script("finalize_validation_set.py", "--root", root, "--set-root", set_root)


def complete_local_set(root: Path, *, set_id: str = "forward") -> Path:
    set_root = local_candidate(root, set_id=set_id)
    run_leakage(root, set_root)
    run_oracles(root, set_root)
    finalized = finalize(root, set_root)
    assert finalized.returncode == 0, finalized.stdout + finalized.stderr
    return set_root


def validate(root: Path, set_root: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    result = run_script("validate_validation_set.py", "--root", root, "--set-root", set_root)
    return result, report(result)


def test_forward_pipeline_binds_source_results_finalization_and_root(tmp_path: Path) -> None:
    set_root = complete_local_set(tmp_path)
    result, validation = validate(tmp_path, set_root)
    assert result.returncode == 0
    assert validation["status"] == "ok"
    assert validation["readiness"] == "consumable"

    manifest = json.loads((set_root / "validation_set_manifest.json").read_text(encoding="utf-8"))
    oracle_results = json.loads((set_root / "oracle_results.json").read_text(encoding="utf-8"))
    assert manifest["manifest_schema_version"] == 2
    assert manifest["oracle_results_path"].endswith("oracle_results.json")
    assert manifest["finalization_record"]["oracle_status"] == "passed"
    assert oracle_results["execution_status"] == "completed"
    assert oracle_results["items_sha256"] == hashlib.sha256((set_root / "validation_set_items.jsonl").read_bytes()).hexdigest()

    frozen = run_script("freeze_validation_set_root.py", "--root", tmp_path, "--set-root", set_root)
    assert frozen.returncode == 0, frozen.stdout + frozen.stderr
    root_doc = report(frozen)
    assert root_doc["root_schema_version"] == 2
    assert set(root_doc["file_hashes"]) == {"manifest", "items", "labels", "oracle_manifest", "oracle_results", "split_manifest", "leakage_report"}
    verified = run_script("verify_validation_set_root.py", "--root", tmp_path, "--set-root", set_root)
    assert verified.returncode == 0
    assert report(verified)["readiness"] == "consumable"


def test_local_source_drift_blocks_validation_and_verified_root(tmp_path: Path) -> None:
    set_root = complete_local_set(tmp_path)
    assert run_script("freeze_validation_set_root.py", "--root", tmp_path, "--set-root", set_root).returncode == 0
    (tmp_path / "source" / "forward.rec").write_text("acct_9|1250|USD\n", encoding="utf-8")

    result, validation = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert "local_source_hash_mismatch" in codes(validation)
    assert validation["readiness"] == "blocked"

    verified = run_script("verify_validation_set_root.py", "--root", tmp_path, "--set-root", set_root)
    verify_report = report(verified)
    assert verified.returncode == 2
    assert verify_report["status"] == "block"
    assert verify_report["readiness"] == "blocked"
    assert verify_report["validation_status"] == "block"


def test_local_source_parent_and_symlink_escape_are_blocked(tmp_path: Path) -> None:
    outside = tmp_path / "outside.rec"
    outside.write_text("outside\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    traversal_root = build_candidate(
        root,
        set_id="traversal",
        items=[
            {
                "item_id": "traversal-item",
                "source_class": "synthetic_fixture",
                "evidence_status": "candidate",
                "source_ref": "../outside.rec",
                "source_hash": hashlib.sha256(outside.read_bytes()).hexdigest(),
                "source_binding_type": "local_file",
                "task_family": "parser",
            }
        ],
    )
    result, validation = validate(root, traversal_root)
    assert result.returncode == 2
    assert "local_source_path_escape" in codes(validation)

    link = root / "source-link.rec"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    symlink_root = build_candidate(
        root,
        set_id="symlink",
        items=[
            {
                "item_id": "symlink-item",
                "source_class": "synthetic_fixture",
                "evidence_status": "candidate",
                "source_ref": "source-link.rec",
                "source_hash": hashlib.sha256(outside.read_bytes()).hexdigest(),
                "source_binding_type": "local_file",
                "task_family": "parser",
            }
        ],
    )
    result, validation = validate(root, symlink_root)
    assert result.returncode == 2
    assert "local_source_path_escape" in codes(validation)


def test_opaque_candidate_requires_authoritative_attestation_to_finalize(tmp_path: Path) -> None:
    digest = "a" * 64
    set_root = build_candidate(
        tmp_path,
        set_id="opaque",
        items=[
            {
                "item_id": "opaque-item",
                "source_class": "external_metadata",
                "evidence_status": "candidate",
                "source_ref": "https://example.invalid/records/1",
                "source_hash": digest,
                "task_family": "parser",
            }
        ],
    )
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)
    blocked = finalize(tmp_path, set_root)
    assert blocked.returncode == 2
    assert "opaque_source_binding_unverified" in report(blocked)["error"]

    item = json.loads((set_root / "validation_set_items.jsonl").read_text(encoding="utf-8"))
    item["source_binding_type"] = "authoritative_attestation"
    item["source_attestation"] = {
        "authoritative": True,
        "authority_ref": "registry:review-board",
        "attestation_ref": "attestation:opaque-item-v1",
        "attested_sha256": digest,
    }
    write_jsonl(set_root / "validation_set_items.jsonl", [item])
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)
    finalized = finalize(tmp_path, set_root)
    assert finalized.returncode == 0, finalized.stdout + finalized.stderr
    assert validate(tmp_path, set_root)[1]["readiness"] == "consumable"


def test_stale_or_failed_oracle_results_block_finalization_and_consumption(tmp_path: Path) -> None:
    set_root = local_candidate(tmp_path)
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)
    oracle_manifest = json.loads((set_root / "oracle_manifest.json").read_text(encoding="utf-8"))
    oracle_manifest["oracles"][0]["description"] = "Changed after execution"
    write_json(set_root / "oracle_manifest.json", oracle_manifest)
    stale = finalize(tmp_path, set_root)
    assert stale.returncode == 2
    assert "oracle_results_input_hash_mismatch" in report(stale)["error"]

    run_oracles(tmp_path, set_root)
    assert finalize(tmp_path, set_root).returncode == 0
    oracle_results = json.loads((set_root / "oracle_results.json").read_text(encoding="utf-8"))
    oracle_results["status"] = "failed"
    oracle_results["failed_count"] = 1
    oracle_results["results"][0]["status"] = "failed"
    oracle_results["results"][0]["failures"] = ["forced_failure"]
    write_json(set_root / "oracle_results.json", oracle_results)
    result, validation = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert {"oracle_results_not_completed_nonblocking", "finalization_record_mismatch"} <= codes(validation)


def test_manual_complete_and_versionless_legacy_cannot_bypass_finalizer(tmp_path: Path) -> None:
    set_root = local_candidate(tmp_path)
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)
    manifest_path = set_root / "validation_set_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validation_set_status"] = "complete"
    write_json(manifest_path, manifest)
    result, validation = validate(tmp_path, set_root)
    assert result.returncode == 2
    assert "missing_finalization_record" in codes(validation)
    assert run_script("freeze_validation_set_root.py", "--root", tmp_path, "--set-root", set_root).returncode == 2

    manifest.pop("manifest_schema_version")
    manifest.pop("oracle_results_path")
    manifest.pop("finalization_record", None)
    write_json(manifest_path, manifest)
    result, validation = validate(tmp_path, set_root)
    assert result.returncode == 0
    assert validation["status"] == "warn"
    assert validation["readiness"] == "migration_required"
    assert "legacy_manifest_migration_required" in codes(validation)
    frozen = run_script("freeze_validation_set_root.py", "--root", tmp_path, "--set-root", set_root)
    assert frozen.returncode == 2
    assert "migration_required" in report(frozen)["error"]


def test_build_custom_oracle_ids_fail_closed_without_plan_inputs(tmp_path: Path) -> None:
    source = tmp_path / "source.rec"
    source.write_text("record\n", encoding="utf-8")
    items = [
        {
            "item_id": "custom-item",
            "source_class": "synthetic_fixture",
            "evidence_status": "candidate",
            "source_ref": "source.rec",
            "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
            "task_family": "parser",
            "oracle_ids": ["custom-oracle"],
        }
    ]
    items_path = tmp_path / "items.jsonl"
    write_jsonl(items_path, items)
    blocked = run_script("build_validation_set.py", "--root", tmp_path, "--set-id", "missing-plan", "--items", items_path)
    assert blocked.returncode == 2
    assert "custom item oracle_ids require --oracle-manifest" in report(blocked)["error"]

    oracle_path = tmp_path / "custom-oracles.json"
    split_path = tmp_path / "custom-split.json"
    write_json(
        oracle_path,
        {
            "validation_set_id": "planned",
            "oracle_count": 1,
            "oracles": [
                {
                    "oracle_id": "custom-oracle",
                    "oracle_type": "deterministic",
                    "target": "item",
                    "description": "Require item identity",
                    "required_fields": ["item_id"],
                }
            ],
        },
    )
    write_json(
        split_path,
        {
            "validation_set_id": "planned",
            "sealed_holdout_status": "not_applicable",
            "label_visibility_policy": "public deterministic fixture",
            "splits": {"public_test": ["custom-item"]},
        },
    )
    built = run_script(
        "build_validation_set.py",
        "--root",
        tmp_path,
        "--set-id",
        "planned",
        "--items",
        items_path,
        "--oracle-manifest",
        oracle_path,
        "--split-manifest",
        split_path,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    validation = validate(tmp_path, tmp_path / ".validation" / "sets" / "planned")[1]
    assert validation["readiness"] == "candidate"
    assert "unresolved_oracle_reference" not in codes(validation)


def test_integrity_finding_forces_consistent_blocked_verify_status(tmp_path: Path) -> None:
    set_root = complete_local_set(tmp_path)
    assert run_script("freeze_validation_set_root.py", "--root", tmp_path, "--set-root", set_root).returncode == 0
    split = set_root / "split_manifest.json"
    split.write_text(split.read_text(encoding="utf-8") + " \n", encoding="utf-8")
    verified = run_script("verify_validation_set_root.py", "--root", tmp_path, "--set-root", set_root)
    value = report(verified)
    assert verified.returncode == 2
    assert value["status"] == "block"
    assert value["readiness"] == "blocked"
    assert value["validation_status"] == "block"
    assert value["bound_validation_status"] == "block"
    assert "file_sha256_mismatch" in codes(value)


def test_changed_predicate_cannot_be_forged_pass_by_updating_result_hashes(tmp_path: Path) -> None:
    set_root = local_candidate(tmp_path)
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)

    oracle_path = set_root / "oracle_manifest.json"
    results_path = set_root / "oracle_results.json"
    oracle_manifest = json.loads(oracle_path.read_text(encoding="utf-8"))
    oracle_manifest["oracles"][0]["required_fields"].append("new_required_predicate_field")
    write_json(oracle_path, oracle_manifest)
    oracle_results = json.loads(results_path.read_text(encoding="utf-8"))
    oracle_results["oracle_manifest_sha256"] = hashlib.sha256(oracle_path.read_bytes()).hexdigest()
    write_json(results_path, oracle_results)

    hash_only = finalize(tmp_path, set_root)
    assert hash_only.returncode == 2
    assert "oracle_result_definition_hash_mismatch" in report(hash_only)["error"]

    oracle_results = json.loads(results_path.read_text(encoding="utf-8"))
    oracle_results["results"][0]["oracle_definition_sha256"] = canonical_hash(oracle_manifest["oracles"][0])
    write_json(results_path, oracle_results)
    forged_content_hash = finalize(tmp_path, set_root)
    assert forged_content_hash.returncode == 2
    assert "oracle_result_semantic_mismatch" in report(forged_content_hash)["error"]

    rerun = run_script("run_validation_oracles.py", "--root", tmp_path, "--set-root", set_root)
    assert rerun.returncode == 1
    assert report(rerun)["status"] == "failed"


def test_unsupported_item_oracle_pair_requires_authoritative_human_adjudication(tmp_path: Path) -> None:
    sources: list[Path] = []
    items: list[dict[str, Any]] = []
    for index in (1, 2):
        source = tmp_path / "source" / f"item-{index}.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"item {index}\n", encoding="utf-8")
        sources.append(source)
        items.append(
            {
                "item_id": f"item-{index}",
                "source_class": "synthetic_fixture",
                "evidence_status": "candidate",
                "source_ref": source.relative_to(tmp_path).as_posix(),
                "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
                "task_family": "parser",
            }
        )
    set_root = build_candidate(tmp_path, set_id="mixed-oracles", items=items)
    built_items = [json.loads(line) for line in (set_root / "validation_set_items.jsonl").read_text(encoding="utf-8").splitlines()]
    built_items[0]["oracle_ids"] = ["deterministic-oracle"]
    built_items[1]["oracle_ids"] = ["human-oracle"]
    write_jsonl(set_root / "validation_set_items.jsonl", built_items)
    write_json(
        set_root / "oracle_manifest.json",
        {
            "validation_set_id": "mixed-oracles",
            "oracle_count": 2,
            "oracles": [
                {
                    "oracle_id": "deterministic-oracle",
                    "oracle_type": "deterministic",
                    "target": "item",
                    "description": "Require item identity",
                    "required_fields": ["item_id"],
                },
                {
                    "oracle_id": "human-oracle",
                    "oracle_type": "human_reviewed",
                    "target": "item",
                    "description": "Human adjudication for semantic correctness",
                },
            ],
        },
    )
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)
    results = json.loads((set_root / "oracle_results.json").read_text(encoding="utf-8"))
    assert results["executed_pair_count"] == 1
    assert results["unsupported_pair_count"] == 1

    blocked = finalize(tmp_path, set_root)
    assert blocked.returncode == 2
    assert "oracle_pair_coverage_incomplete" in report(blocked)["error"]

    write_jsonl(
        set_root / "validation_set_labels.jsonl",
        [
            {
                "label_id": "human-item-2",
                "item_id": "item-2",
                "label_type": "human_reviewed",
                "label_status": "accepted",
                "authoritative": True,
                "human_reviewer_ref": "reviewer:validation-board",
                "evidence_refs": ["attestation:item-2-human-review-v1"],
                "oracle_ids": ["human-oracle"],
            }
        ],
    )
    run_leakage(tmp_path, set_root)
    finalized = finalize(tmp_path, set_root)
    assert finalized.returncode == 0, finalized.stdout + finalized.stderr
    assert validate(tmp_path, set_root)[1]["readiness"] == "consumable"


def test_false_premise_scenario_cannot_be_claimed_as_covered(tmp_path: Path) -> None:
    set_root = local_candidate(tmp_path, set_id="scenario-set")
    items_path = set_root / "validation_set_items.jsonl"
    manifest_path = set_root / "validation_set_manifest.json"
    item = json.loads(items_path.read_text(encoding="utf-8"))
    oracle_id = item["oracle_ids"][0]
    item.update(
        {
            "acceptance_scenario_id": "scenario-false",
            "premise_satisfied": False,
            "expected_terminal_state": "accepted",
            "observed_terminal_state": "accepted",
        }
    )
    write_jsonl(items_path, [item])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scenario_coverage"] = [
        {
            "acceptance_scenario_id": "scenario-false",
            "coverage_status": "covered",
            "premise_satisfied": False,
            "expected_terminal_state": "accepted",
            "observed_terminal_state": "accepted",
            "evidence_path": item["source_ref"],
            "oracle_id": oracle_id,
        }
    ]
    write_json(manifest_path, manifest)
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)

    blocked = finalize(tmp_path, set_root)
    assert blocked.returncode == 2
    assert "scenario_coverage_without_satisfied_premise" in report(blocked)["error"]

    item["premise_satisfied"] = True
    write_jsonl(items_path, [item])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scenario_coverage"][0]["premise_satisfied"] = True
    manifest["scenario_coverage"][0]["evidence_sha256"] = hashlib.sha256((tmp_path / item["source_ref"]).read_bytes()).hexdigest()
    write_json(manifest_path, manifest)
    oracle_path = set_root / "oracle_manifest.json"
    oracle_manifest = json.loads(oracle_path.read_text(encoding="utf-8"))
    oracle_manifest["oracles"][0]["required_fields"].extend(["expected_terminal_state", "observed_terminal_state"])
    write_json(oracle_path, oracle_manifest)
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)
    finalized = finalize(tmp_path, set_root)
    assert finalized.returncode == 0, finalized.stdout + finalized.stderr
    assert validate(tmp_path, set_root)[1]["readiness"] == "consumable"


def test_scenario_coverage_requires_observing_oracle_and_hashed_evidence(tmp_path: Path) -> None:
    set_root = local_candidate(tmp_path, set_id="scenario-evidence")
    items_path = set_root / "validation_set_items.jsonl"
    manifest_path = set_root / "validation_set_manifest.json"
    oracle_path = set_root / "oracle_manifest.json"
    item = json.loads(items_path.read_text(encoding="utf-8"))
    item.update(
        {
            "acceptance_scenario_id": "scenario-observed",
            "premise_satisfied": True,
            "expected_terminal_state": "accepted",
            "observed_terminal_state": "accepted",
        }
    )
    write_jsonl(items_path, [item])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scenario_coverage"] = [
        {
            "acceptance_scenario_id": "scenario-observed",
            "coverage_status": "covered",
            "premise_satisfied": True,
            "expected_terminal_state": "accepted",
            "observed_terminal_state": "accepted",
            "evidence_path": item["source_ref"],
            "evidence_sha256": "0" * 64,
            "oracle_id": item["oracle_ids"][0],
        }
    ]
    write_json(manifest_path, manifest)
    run_leakage(tmp_path, set_root)
    run_oracles(tmp_path, set_root)

    blocked = finalize(tmp_path, set_root)
    assert blocked.returncode == 2
    error = report(blocked)["error"]
    assert "scenario_evidence_hash_mismatch" in error
    assert "scenario_oracle_does_not_observe_terminal_state" in error

    manifest["scenario_coverage"][0]["evidence_sha256"] = hashlib.sha256((tmp_path / item["source_ref"]).read_bytes()).hexdigest()
    write_json(manifest_path, manifest)
    still_unobserved = finalize(tmp_path, set_root)
    assert still_unobserved.returncode == 2
    assert "scenario_oracle_does_not_observe_terminal_state" in report(still_unobserved)["error"]

    oracle_manifest = json.loads(oracle_path.read_text(encoding="utf-8"))
    oracle_manifest["oracles"][0]["required_fields"].extend(["expected_terminal_state", "observed_terminal_state"])
    write_json(oracle_path, oracle_manifest)
    run_oracles(tmp_path, set_root)
    finalized = finalize(tmp_path, set_root)
    assert finalized.returncode == 0, finalized.stdout + finalized.stderr
    assert validate(tmp_path, set_root)[1]["readiness"] == "consumable"


def test_atomic_json_writer_ignores_precreated_predictable_temp_symlink(tmp_path: Path) -> None:
    sys.path.insert(0, str(SCRIPTS))
    try:
        from validation_set_contract import atomic_write_json
    finally:
        sys.path.pop(0)
    target = tmp_path / "artifact.json"
    outside = tmp_path / "outside-sentinel.json"
    outside.write_text("sentinel\n", encoding="utf-8")
    predictable = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    try:
        predictable.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")

    atomic_write_json(target, {"safe": True}, root=tmp_path)

    assert outside.read_text(encoding="utf-8") == "sentinel\n"
    assert json.loads(target.read_text(encoding="utf-8")) == {"safe": True}


def test_builder_replaces_child_output_symlink_without_overwriting_target(tmp_path: Path) -> None:
    root = tmp_path / "root"
    set_root = root / ".validation" / "sets" / "child-link"
    set_root.mkdir(parents=True)
    outside = tmp_path / "outside-items.jsonl"
    outside.write_text("sentinel\n", encoding="utf-8")
    linked_items = set_root / "validation_set_items.jsonl"
    try:
        linked_items.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    source = root / "source.txt"
    source.write_text("source\n", encoding="utf-8")
    candidate = root / "items.jsonl"
    write_jsonl(
        candidate,
        [
            {
                "item_id": "safe-item",
                "source_class": "synthetic_fixture",
                "evidence_status": "candidate",
                "source_ref": "source.txt",
                "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
                "task_family": "parser",
            }
        ],
    )

    built = run_script("build_validation_set.py", "--root", root, "--set-id", "child-link", "--items", candidate)

    assert built.returncode == 0, built.stdout + built.stderr
    assert outside.read_text(encoding="utf-8") == "sentinel\n"
    assert not linked_items.is_symlink()
    assert json.loads(linked_items.read_text(encoding="utf-8"))["item_id"] == "safe-item"


def test_freeze_ignores_precreated_pid_temp_symlink(tmp_path: Path) -> None:
    set_root = complete_local_set(tmp_path)
    outside = tmp_path / "outside-root.json"
    outside.write_text("sentinel\n", encoding="utf-8")
    code = "\n".join(
        [
            "import os, sys",
            "from pathlib import Path",
            f"sys.path.insert(0, {str(SCRIPTS)!r})",
            "from freeze_validation_set_root import main",
            f"set_root = Path({str(set_root)!r})",
            f"outside = Path({str(outside)!r})",
            "link = set_root / f'.validation_set_root.json.tmp-{os.getpid()}'",
            "link.symlink_to(outside)",
            f"raise SystemExit(main(['--root', {str(tmp_path)!r}, '--set-root', {str(set_root)!r}]))",
        ]
    )
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    frozen = subprocess.run([sys.executable, "-B", "-c", code], cwd=REPO, env=env, text=True, capture_output=True, check=False)

    assert frozen.returncode == 0, frozen.stdout + frozen.stderr
    assert outside.read_text(encoding="utf-8") == "sentinel\n"
    assert (set_root / "validation_set_root.json").is_file()
