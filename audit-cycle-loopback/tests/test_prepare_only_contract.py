#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = SKILL_ROOT.parent
SCRIPT_DIR = SKILL_ROOT / "scripts"
ORCHESTRATE_SCRIPTS = SKILLS_ROOT / "orchestrate-task-cycle" / "scripts"

for path in (SCRIPT_DIR, ORCHESTRATE_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def load_provider() -> Any:
    return importlib.import_module("audit_cycle_loopback")


def load_cycle_ledger() -> Any:
    return importlib.import_module("orchestrate_task_cycle.cycle_ledger")


def test_provider_public_export_surface_remains_compatible() -> None:
    provider = load_provider()
    exports = provider.__all__

    assert len(exports) == 266
    assert hashlib.sha256("\n".join(exports).encode("utf-8")).hexdigest() == (
        "fa8723502375d4b0c10e63f508539dfe00970bb5bcb231fe0ea300ddb027b14b"
    )


def test_public_facade_uses_static_exports_and_command_registry() -> None:
    provider_dir = SCRIPT_DIR / "audit_cycle_loopback"
    facade_sources = "\n".join(
        (provider_dir / name).read_text(encoding="utf-8")
        for name in ("__init__.py", "api.py", "commands.py", "runtime_dependencies.py")
    )

    assert "globals()" not in facade_sources
    assert "__dict__" not in facade_sources
    assert "__getattr__" not in facade_sources
    assert "import *" not in facade_sources

    commands = importlib.import_module("audit_cycle_loopback.commands")
    assert tuple(commands.COMMAND_INDEX) == ("evaluate",)
    with pytest.raises(ValueError, match="duplicate loopback command"):
        commands._index_commands((commands.COMMANDS[0], commands.COMMANDS[0]))


def test_module_entrypoint_forwards_help_and_rejects_unknown_command(
    tmp_path: Path,
) -> None:
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            (str(SCRIPT_DIR), str(ORCHESTRATE_SCRIPTS))
        ),
    }
    help_result = subprocess.run(
        [sys.executable, "-m", "audit_cycle_loopback", "evaluate", "--help"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
    )
    unknown_result = subprocess.run(
        [sys.executable, "-m", "audit_cycle_loopback", "unknown"],
        check=False,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
    )

    assert help_result.returncode == 0
    assert "--cycle-id" in help_result.stdout
    assert unknown_result.returncode == 2
    assert "invalid choice" in unknown_result.stderr


def test_function_gate_uses_an_injected_strategy() -> None:
    gates = importlib.import_module("audit_cycle_loopback.gates")
    received: list[dict[str, Any]] = []

    def strategy(**context: Any) -> dict[str, Any]:
        received.append(context)
        return {"status": "pass", "value": context["value"]}

    gate = gates.FunctionGate("injected_gate", strategy)

    assert gate.evaluate({"value": 7}) == {"status": "pass", "value": 7}
    assert received == [{"value": 7}]


def test_evaluator_runtime_modules_stay_bounded_and_use_explicit_state() -> None:
    provider_dir = SCRIPT_DIR / "audit_cycle_loopback"
    runtime_modules = set(provider_dir.rglob("*.py"))

    for path in sorted(runtime_modules):
        source = path.read_text(encoding="utf-8")
        logical_lines = [
            line
            for line in source.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        assert len(logical_lines) < 500, path.name
        assert "globals()" not in source, path.name
        assert "__dict__" not in source, path.name
        assert "__getattr__" not in source, path.name
        assert "locals()" not in source, path.name
        assert "import *" not in source, path.name
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 <= 140, (
                    path.name,
                    node.name,
                )


def test_generic_material_delta_is_the_positive_observed_class() -> None:
    provider = load_provider()
    material = {
        "observed_output_class": "material_delta",
        "changed_vs_previous": True,
        "semantic_progress": True,
    }
    unmapped = {
        "observed_output_class": "adapter_class_A",
        "changed_vs_previous": True,
        "semantic_progress": True,
    }

    assert provider.terminal_outcome_changed(material, False, False) is True
    assert provider.terminal_outcome_changed(unmapped, False, False) is False


def test_root_cause_equivalence_uses_exact_normalized_identity_without_global_similarity_threshold() -> None:
    provider = load_provider()
    base = {
        "target_surface": "surface_A",
        "observed_delta_class": "material_delta",
    }

    assert provider.equivalent_root_cause(
        {**base, "hypothesized_root_cause": "cause_A_v2"},
        {**base, "hypothesized_root_cause": "cause_A_v1"},
    ) is True
    assert provider.equivalent_root_cause(
        {**base, "hypothesized_root_cause": "cause_A"},
        {**base, "hypothesized_root_cause": "cause_B"},
    ) is False


def write_adapter(
    path: Path,
    *,
    metric_value: int = 1,
    previous_metric_value: int | None = None,
    provenance_label: str = "independently_verified",
    primary_metric_value: int | None = None,
) -> None:
    previous_lines = (
        [
            "",
            "def previous_accepted_fp(**kwargs):",
            f"    return {{'previous_quality_vector': {{'metric_A': {previous_metric_value}}}}}",
        ]
        if previous_metric_value is not None
        else []
    )
    primary_metric_expression = (
        str(primary_metric_value)
        if primary_metric_value is not None
        else "quality.get('metric_A')"
    )
    path.write_text(
        "\n".join(
            [
                "def quality_vector(decision_artifact_ref=None, **kwargs):",
                "    ref = decision_artifact_ref or {}",
                f"    return {{'quality_vector': {{'metric_A': {metric_value}, 'quality_signal_confidence': 'high', 'current_output_fingerprint': 'fingerprint_A', 'artifact_id': ref.get('artifact_id'), 'artifact_sha256': ref.get('artifact_sha256'), 'production_lane_identity': ref.get('production_lane_identity'), 'body_projection_fingerprint': ref.get('body_projection_fingerprint'), 'verification_input_ids': ref.get('verification_input_ids')}}}}",
                "",
                "def quality_delta_policy(**kwargs):",
                "    return {'keys': ['metric_A']}",
                "",
                "def substance_metrics(**kwargs):",
                "    return {'substance_metrics': {'axis_A': 1}}",
                "",
                "def evidence_provenance(**kwargs):",
                f"    return {{'evidence_provenance': {{'metric_A': '{provenance_label}', 'axis_A': '{provenance_label}', 'axis_G': '{provenance_label}'}}, 'verification_input_paths': ['source_cohort_D.json'], 'verification_input_ids': ['source_cohort_D'], 'producer_input_ids': ['artifact_A'], 'verified_artifact_ids': ['artifact_A'], 'input_fingerprints': {{'producer_inputs': ['body_fp_A'], 'verification_inputs': ['input_delta_D']}}, 'producer_function_id': 'consumer_C', 'verifier_function_id': 'consumer_D'}}",
                "",
                "def primary_metric(decision_artifact_ref=None, quality_vector=None, **kwargs):",
                "    ref = decision_artifact_ref or {}",
                "    quality = quality_vector or {}",
                f"    return {{'goal_axis_id': 'axis_G', 'value': {primary_metric_expression}, 'artifact_id': ref.get('artifact_id'), 'artifact_sha256': ref.get('artifact_sha256'), 'production_lane_identity': ref.get('production_lane_identity'), 'body_projection_fingerprint': ref.get('body_projection_fingerprint'), 'verification_input_ids': ref.get('verification_input_ids')}}",
                "",
                "def facet_root_map(**kwargs):",
                "    return {'axis_A': 'axis_A', 'family_A': 'axis_A', 'class_A': 'axis_A'}",
                "",
                "def gate_artifact_compatibility(artifact_ref=None, **kwargs):",
                "    ref = artifact_ref or {}",
                "    return {'compatible': True, 'artifact_id': ref.get('artifact_id'), 'artifact_sha256': ref.get('artifact_sha256'), 'evidence_ref': 'evidence_A'}",
                *previous_lines,
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_provider(
    root: Path,
    *extra: str,
    metric_value: int = 1,
    previous_metric_value: int | None = None,
    provenance_label: str = "independently_verified",
    primary_metric_value: int | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    artifact = root / "artifact_A.json"
    artifact.write_text('{"artifact_id":"artifact_A"}\n', encoding="utf-8")
    (root / "source_cohort_D.json").write_text(
        '{"source_cohort":"source_cohort_D"}\n', encoding="utf-8"
    )
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    adapter = root / "adapter_A.py"
    write_adapter(
        adapter,
        metric_value=metric_value,
        previous_metric_value=previous_metric_value,
        provenance_label=provenance_label,
        primary_metric_value=primary_metric_value,
    )
    output = root / "candidate_A.json"
    artifact_ref = {
        "artifact_id": "artifact_A",
        "artifact_class": "class_A",
        "artifact_path_or_store_ref": artifact.name,
        "artifact_sha256": artifact_sha256,
        "production_lane_identity": "lane_A",
        "body_projection_fingerprint": artifact_sha256,
        "verification_input_ids": ["source_cohort_C"],
    }
    command = [
        sys.executable,
        "-m",
        "audit_cycle_loopback",
        "evaluate",
        "--root",
        str(root),
        "--cycle-id",
        "cycle_A",
        "--task-id",
        "task_A",
        "--artifact-family",
        "class_A",
        "--semantic-signature",
        "family_A",
        "--root-key",
        "axis_A",
        "--domain-adapter",
        str(adapter),
        "--artifact-path",
        artifact.name,
        "--artifact-ref-json",
        json.dumps(artifact_ref, sort_keys=True),
        "--blocker-signature",
        "blocker_A",
        "--output",
        output.name,
        *extra,
    ]
    env = dict(os.environ)
    module_paths = os.pathsep.join((str(SCRIPT_DIR), str(ORCHESTRATE_SCRIPTS)))
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (module_paths, env.get("PYTHONPATH", "")) if item
    )
    return (
        subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            cwd=root,
            env=env,
        ),
        output,
    )


def test_write_registry_prepares_positive_candidate_without_mutating_state(tmp_path: Path) -> None:
    registry = tmp_path / ".task" / "anti_loop" / "family_progress_registry.jsonl"
    ledger = tmp_path / ".task" / "anti_loop" / "root_cause_ledger.jsonl"
    seal = tmp_path / ".task" / "sealed_blocker_families.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "cycle_id": "cycle_prior",
                "family_key": "family_prior",
                    "primary_metric_gate": {
                        "primary_metric_scope_key": "primary_goal_axis:axis_g",
                        "artifact_binding_status": "exact",
                        "evidence_provenance": "independently_verified",
                        "independent_source_separation_status": "pass",
                        "decision_contribution_allowed": True,
                    "primary_metric_high_water": 0,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    ledger.write_text('{"cycle_id":"cycle_prior","root_key":"axis_prior"}\n', encoding="utf-8")
    seal.write_text('{"schema_version":"sealed-blocker-families-v1","families":[]}\n', encoding="utf-8")
    advice = tmp_path / "skill_advice.md"
    advice.write_text("pending proposal\n", encoding="utf-8")
    before = {path: path.read_bytes() for path in (registry, ledger, seal, advice)}

    process, output = run_provider(
        tmp_path,
        "--hypothesized-root-cause",
        "cause_A",
        "--write-registry",
    )

    assert process.returncode == 0, process.stderr
    emitted = json.loads(process.stdout)
    candidate = json.loads(output.read_text(encoding="utf-8"))
    assert candidate["semantic_progress"] is True
    assert candidate["progress_verdict"] == "advanced"
    assert candidate["registry_updated"] is False
    assert candidate["registry_update_candidate"] is True
    assert candidate["registry_update_status"] == "prepared_not_finalized"
    assert candidate["write_registry_deferred"] is True
    assert candidate["finalization_required"] is True
    assert candidate["finalization_state"] == "candidate"
    assert candidate["authoritative_consumption_allowed"] is False
    assert candidate["root_cause_ledger_status"] == "prepared_not_finalized"
    assert candidate["root_cause_ledger_updated"] is False
    mutation = candidate["durable_mutation_candidate"]
    assert mutation["status"] == "prepared_not_finalized"
    assert mutation["legacy_write_requested"] is True
    assert {row["target_id"] for row in mutation["operations"]} == {
        "family_progress_registry",
        "root_cause_ledger",
        "sealed_blocker_families",
    }
    hash_body = dict(mutation)
    candidate_sha256 = hash_body.pop("candidate_sha256")
    assert candidate_sha256 == hashlib.sha256(
        json.dumps(hash_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    for operation in mutation["operations"]:
        assert operation["payload_sha256"] == hashlib.sha256(
            json.dumps(
                operation["payload"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    durable_payload_text = json.dumps(mutation["operations"], ensure_ascii=False, sort_keys=True)
    assert "artifact_A.json" not in durable_payload_text
    assert "adapter_A.py" not in durable_payload_text
    assert "skill_advice.md" not in durable_payload_text
    assert str(tmp_path) not in durable_payload_text
    assert emitted["anti_loop_handoff"]["finalization_required"] is True
    assert emitted["anti_loop_handoff"]["authoritative_consumption_allowed"] is False
    assert any(
        finding.get("code") == "orphan_advice_not_intaken"
        and finding.get("severity") == "warn"
        for finding in candidate.get("findings", [])
        if isinstance(finding, dict)
    )
    assert all(path.read_bytes() == content for path, content in before.items())


def test_retired_direct_write_helpers_fail_closed_without_mutating_state(
    tmp_path: Path,
) -> None:
    provider = load_provider()
    registry = tmp_path / ".task" / "anti_loop" / "family_progress_registry.jsonl"
    ledger = tmp_path / ".task" / "anti_loop" / "root_cause_ledger.jsonl"
    seal = tmp_path / ".task" / "sealed_blocker_families.json"
    registry.parent.mkdir(parents=True)
    registry.write_text('{"row_id":"row_A"}\n', encoding="utf-8")
    ledger.write_text('{"row_id":"row_B"}\n', encoding="utf-8")
    seal.write_text('{"families":[]}\n', encoding="utf-8")
    before = {path: path.read_bytes() for path in (registry, ledger, seal)}

    with pytest.raises(RuntimeError, match="direct anti-loop registry writes"):
        provider.write_registry(registry, [{"row_id": "row_C"}])
    with pytest.raises(RuntimeError, match="direct root-cause ledger writes"):
        provider.append_root_cause_ledger(ledger, [{"row_id": "row_D"}])
    with pytest.raises(RuntimeError, match="direct family-seal writes"):
        provider.feed_exhausted_family_seal(tmp_path, {"root_key": "axis_A"})

    assert all(path.read_bytes() == content for path, content in before.items())


def test_exhaustion_prepares_family_seal_without_writing_it(tmp_path: Path) -> None:
    ledger = tmp_path / ".task" / "anti_loop" / "root_cause_ledger.jsonl"
    seal = tmp_path / ".task" / "sealed_blocker_families.json"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        json.dumps(
            {
                "schema_version": "root-cause-hypothesis-ledger-v1",
                "cycle_id": "cycle_prior",
                "family_key": "class_a|family_a",
                "root_key": "axis_A",
                "root_family_key": "axis_a",
                "hypothesized_root_cause": "cause_prior",
                "target_surface": "surface_A",
                "observed_delta_class": "no_delta",
                "repair_attempted": True,
                "attempt_count": 2,
                "vacuous_attempt_count": 2,
                "terminal_outcome_changed": False,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    seal.write_text(
        '{"schema_version":"sealed-blocker-families-v1","families":[{"root_key":"axis_prior"}]}\n',
        encoding="utf-8",
    )
    before_ledger = ledger.read_bytes()
    before_seal = seal.read_bytes()

    process, output = run_provider(
        tmp_path,
        "--untried-promotion-budget",
        "2",
        "--write-registry",
    )

    assert process.returncode == 0, process.stderr
    candidate = json.loads(output.read_text(encoding="utf-8"))
    assert candidate["hypothesis_exhausted"] is True
    assert candidate["hypothesis_exhaustion_seal_status"] == "prepared_not_finalized"
    assert candidate["hypothesis_exhaustion_seal_candidate"]["root_key"] == "axis_a"
    mutation_kinds = {
        row["target_id"]
        for row in candidate["durable_mutation_candidate"]["operations"]
    }
    assert "sealed_blocker_families" in mutation_kinds
    assert ledger.read_bytes() == before_ledger
    assert seal.read_bytes() == before_seal


def test_label_correction_preserves_logical_attempt_and_revision_lineage() -> None:
    provider = load_provider()
    fingerprint = "f" * 64
    attempt_old = provider.content_bound_attempt_identity(
        "cycle_A", "family_old", "blocker_old", fingerprint
    )
    attempt_corrected = provider.content_bound_attempt_identity(
        "cycle_A", "family_corrected", "blocker_corrected", fingerprint
    )
    legacy_old = provider.legacy_content_bound_attempt_identity(
        "cycle_A", "family_old", "blocker_old", fingerprint
    )
    legacy_corrected = provider.legacy_content_bound_attempt_identity(
        "cycle_A", "family_corrected", "blocker_corrected", fingerprint
    )
    rows = provider.compact_registry(
        [
            {
                "cycle_id": "cycle_A",
                "input_state_fingerprint": fingerprint,
                "attempt_identity": attempt_old,
                "attempt_revision": 2,
                "family_key": "family_old",
                "root_key": "root_old",
                "root_family_key": "root_old",
                "blocker_signature": "blocker_old",
            },
            {
                "cycle_id": "cycle_A",
                "input_state_fingerprint": fingerprint,
                "attempt_identity": attempt_corrected,
                "attempt_revision_candidate": 3,
                "family_key": "family_corrected",
                "root_key": "root_corrected",
                "root_family_key": "root_corrected",
                "blocker_signature": "blocker_corrected",
            },
        ],
        10,
    )

    assert attempt_old == attempt_corrected
    assert legacy_old != legacy_corrected
    assert len(rows) == 1
    assert rows[0]["registry_label_correction"] is True
    assert rows[0]["attempt_revision_candidate"] == 3
    assert rows[0]["supersedes_attempt_revision_candidate"] == 2
    assert rows[0]["supersedes_attempt_identity_candidate"] == attempt_old


def test_primary_metric_requires_exact_source_separation_for_high_water() -> None:
    provider = load_provider()
    artifact_ref = {
        "artifact_id": "artifact_A",
        "artifact_sha256": "a" * 64,
        "production_lane_identity": "lane_L",
        "body_projection_fingerprint": "b" * 64,
        "verification_input_ids": ["source_cohort_C"],
    }
    metric = {
        "goal_axis_id": "axis_G",
        "value": 2,
        **artifact_ref,
    }
    prior = {
        "primary_metric_gate": {
            "primary_metric_scope_key": "primary_goal_axis:axis_g",
            "artifact_binding_status": "exact",
            "evidence_provenance": "independently_verified",
            "independent_source_separation_status": "pass",
            "decision_contribution_allowed": True,
            "primary_metric_high_water": 1,
        }
    }
    overlapping = provider.normalize_primary_metric_gate(
        metric,
        rows=[prior],
        cap=None,
        epsilon=0.0,
        provenance={"axis_g": "independently_verified"},
        provenance_hook_provided=True,
        source_separation_gate={
            "independent_source_separation_status": "overlap",
            "verification_axes": [
                {
                    "axis_id": "axis_G",
                    "evidence_provenance": "producer_attested",
                }
            ],
        },
        expected_artifact_ref=artifact_ref,
    )
    separated = provider.normalize_primary_metric_gate(
        metric,
        rows=[prior],
        cap=None,
        epsilon=0.0,
        provenance={"axis_g": "independently_verified"},
        provenance_hook_provided=True,
        source_separation_gate={
            "independent_source_separation_status": "pass",
            "verification_axes": [
                {
                    "axis_id": "axis_G",
                    "evidence_provenance": "independently_verified",
                }
            ],
        },
        expected_artifact_ref=artifact_ref,
    )

    assert overlapping["raw_primary_metric_high_water_moved"] is True
    assert overlapping["primary_metric_high_water_moved"] is False
    assert overlapping["evidence_provenance"] == "producer_attested"
    assert separated["primary_metric_high_water_moved"] is True
    assert separated["evidence_provenance"] == "independently_verified"


def test_terminal_self_resolution_rechecks_final_disposition() -> None:
    provider = load_provider()
    missing = provider.terminal_self_resolution_gate(
        {"recommended_disposition": "terminal_blocked"}
    )
    local = provider.terminal_self_resolution_gate(
        {
            "recommended_disposition": "terminal_blocked",
            "residuals": [
                {
                    "residual_id": "residual_A",
                    "classification": "local_deterministic_repair_possible",
                }
            ],
        }
    )
    external = provider.terminal_self_resolution_gate(
        {
            "recommended_disposition": "terminal_blocked",
            "residuals": [
                {
                    "residual_id": "residual_A",
                    "classification": "new_external_input_required",
                }
            ],
        }
    )

    assert missing["goal_terminal_prohibited"] is True
    assert missing["offline_scope_unverified"] is True
    assert local["goal_terminal_prohibited"] is True
    assert external["goal_terminal_prohibited"] is False
    assert external["status"] == "pass"


def test_next_cycle_consumes_only_helper_verified_finalized_projection(tmp_path: Path) -> None:
    cycle_ledger = load_cycle_ledger()
    prior_cycle_id = "cycle_prior"
    cycle_ledger.init_cycle(tmp_path, prior_cycle_id, "task_prior", "prepare replay state")
    axes = {
        axis: {"status": "pass", "evidence_ref": f"evidence_{index}"}
        for index, axis in enumerate(cycle_ledger.VERDICT_AXES, start=1)
    }
    finalized_candidate = {
        "schema_version": 1,
        "kind": "cycle_final_candidate",
        "final_candidate": True,
        "cycle_id": prior_cycle_id,
        "attempt_id": "attempt_prior",
        "expected_previous_revision": None,
        "expected_previous_attempt_id": None,
        "expected_previous_finalization_token": None,
        "verdict_contract_version": 1,
        **axes,
        "durable_state_candidate": {
            "mode": "typed_operations",
            "operations": [
                {
                    "operation_type": "replace_projection",
                    "target_id": "family_progress_registry",
                    "payload": {
                        "rows": [
                            {
                                "cycle_id": prior_cycle_id,
                                "family_key": "class_a|family_a",
                                "root_key": "axis_A",
                                "root_family_key": "axis_a",
                                "high_water_mark": {"metric_A": 1},
                                "substance_metrics": {"axis_A": 1},
                                "current_output_fingerprint": "fingerprint_A",
                                "micro_hardening_count": 0,
                            }
                        ]
                    },
                },
                {
                    "operation_type": "replace_projection",
                    "target_id": "root_cause_ledger",
                    "payload": {"rows": [{"cycle_id": prior_cycle_id, "root_key": "axis_prior"}]},
                },
                {
                    "operation_type": "replace_projection",
                    "target_id": "sealed_blocker_families",
                    "payload": {
                        "state": {
                            "schema_version": "sealed-blocker-families-v1",
                            "families": [],
                        }
                    },
                },
            ],
        },
    }
    cycle_ledger.finalize_candidate(tmp_path, prior_cycle_id, finalized_candidate)

    process, output = run_provider(
        tmp_path,
        "--finalized-cycle-id",
        prior_cycle_id,
    )

    assert process.returncode == 0, process.stderr
    candidate = json.loads(output.read_text(encoding="utf-8"))
    assert candidate["finalized_state_status"] == "verified"
    assert candidate["registry_state_source"] == "verified_finalization"
    assert candidate["root_cause_ledger_state_source"] == "verified_finalization"
    assert candidate["sealed_blocker_families_state_source"] == "verified_finalization"
    assert candidate["previous_high_water_mark"]["metric_A"] == 1
    assert candidate["semantic_progress"] is False
    assert not (tmp_path / ".task" / "anti_loop" / "family_progress_registry.jsonl").exists()

    pointer_path = (
        tmp_path / ".task" / "cycle" / prior_cycle_id / "current_finalization.json"
    )
    tampered_pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    tampered_pointer["receipt_hash"] = "0" * 64
    pointer_path.write_text(json.dumps(tampered_pointer, sort_keys=True) + "\n", encoding="utf-8")
    rejected_process, rejected_output = run_provider(
        tmp_path,
        "--finalized-cycle-id",
        prior_cycle_id,
    )
    assert rejected_process.returncode == 0, rejected_process.stderr
    rejected = json.loads(rejected_output.read_text(encoding="utf-8"))
    assert rejected["finalized_state_status"] == "invalid"
    assert rejected["registry_state_source"] == "invalid_finalized_state"
    assert rejected["root_cause_ledger_state_source"] == "invalid_finalized_state"
    assert rejected["sealed_blocker_families_state_source"] == "invalid_finalized_state"
    assert rejected["finalized_state_error"]
    assert "metric_A" not in rejected["previous_high_water_mark"]


def test_missing_budget_observes_stall_without_progress_credit_or_threshold_stop(
    tmp_path: Path,
) -> None:
    process, output = run_provider(
        tmp_path,
        metric_value=1,
        previous_metric_value=1,
    )

    assert process.returncode == 0, process.stderr
    candidate = json.loads(output.read_text(encoding="utf-8"))
    same_family_budget = candidate["same_family_budget_evaluation"]
    assert same_family_budget["budget_evaluation_status"] == "budget_unverified"
    assert same_family_budget["budget_value"] is None
    assert candidate["semantic_progress"] is False
    assert candidate["authoritative_semantic_progress"] is False
    assert candidate["same_family_micro_hardening_count"] == 1
    assert candidate["recommended_disposition"] == "prefer_provider_or_semantic"
    assert candidate["hard_stop_required"] is False
    assert "same_family_nonsemantic_attempts" in candidate["budget_unverified"]


def test_explicit_same_family_budget_retains_configured_threshold_behavior(
    tmp_path: Path,
) -> None:
    process, output = run_provider(
        tmp_path,
        "--threshold",
        "1",
        metric_value=1,
        previous_metric_value=1,
    )

    assert process.returncode == 0, process.stderr
    candidate = json.loads(output.read_text(encoding="utf-8"))
    same_family_budget = candidate["same_family_budget_evaluation"]
    assert same_family_budget["budget_evaluation_status"] == "evaluated"
    assert same_family_budget["budget_value"] == 1
    assert candidate["same_family_micro_hardening_count"] == 1
    assert candidate["recommended_disposition"] == "provider_or_semantic_transition_or_terminal"
    assert candidate["hard_stop_required"] is True


def test_default_adapter_location_is_not_auto_registered(tmp_path: Path) -> None:
    provider = load_provider()
    default_adapter = tmp_path / ".task" / "domain_adapter.py"
    default_adapter.parent.mkdir(parents=True)
    default_adapter.write_text("raise RuntimeError('must not auto-load')\n", encoding="utf-8")

    assert provider.domain_adapter_candidate_paths(tmp_path, None) == []
    assert provider.domain_adapter_candidate_paths(tmp_path, str(default_adapter)) == [
        default_adapter
    ]


def test_forced_retarget_uses_explicit_stall_budget_without_multiplier() -> None:
    provider = load_provider()
    gate = provider.chain_stall_forced_retarget_gate(
        {
            "cumulative_goal_distance_stalled": True,
            "cumulative_goal_distance_stall_streak": 3,
            "cumulative_goal_distance_stall_cap": 3,
        },
        blocker_mutation="lateral",
        adapter_gate={},
        capability_ladder_option={
            "selected_task_kind": "task_kind_A",
            "task_kind": "task_kind_A",
            "source": "capability_ladder",
        },
    )

    assert gate["chain_stall_force_retarget"] is True
    assert gate["forced_selected_task"]["selected_task_kind"] == "task_kind_A"


def test_portfolio_restriction_requires_content_bound_external_budget() -> None:
    provider = load_provider()
    unverified, unverified_contract = provider.normalize_portfolio_budget_gate(
        {
            "portfolio_quota_exceeded": True,
            "portfolio_quota_mode": "restrict",
            "constrains_disposition": True,
            "hard_stop_required": True,
            "status": "block",
        }
    )

    assert unverified_contract["budget_evaluation_status"] == "budget_unverified"
    assert unverified["observed_portfolio_quota_exceeded"] is True
    assert unverified["status"] == "not_evaluated"
    assert unverified["constrains_disposition"] is False
    assert unverified["hard_stop_required"] is False

    evaluated, evaluated_contract = provider.normalize_portfolio_budget_gate(
        {
            "portfolio_budget_id": "budget_A",
            "budget_source": "authority_contract",
            "threshold_ratio": 1.5,
            "portfolio_quota_exceeded": True,
            "portfolio_quota_mode": "restrict",
            "constrains_disposition": True,
            "status": "block",
        }
    )

    assert evaluated_contract["budget_evaluation_status"] == "evaluated"
    assert evaluated_contract["budget_id"] == "budget_A"
    assert evaluated["status"] == "block"
    assert evaluated["constrains_disposition"] is True


def test_durable_projection_drops_free_text_locators_and_volatile_trace() -> None:
    provider = load_provider()
    projected = provider.bounded_durable_projection(
        {
            "artifact_id": "artifact_A",
            "evidence_id": "evidence_A",
            "reason_code": "reason_A",
            "direct_quote": "quoted surface",
            "title": "surface title",
            "locator": "segment_A",
            "message": "free-form message",
            "raw": "raw surface",
            "source_text": "source surface",
            "exact_character_count": 42,
            "offset": 7,
            "updated_at": "time_A",
            "generated_at": "time_B",
            "task_id": "task_A",
            "task_family_label": "family_trace_A",
            "legacy_family_key": "family_legacy",
        }
    )

    assert projected == {
        "artifact_id": "artifact_A",
        "evidence_id": "evidence_A",
        "reason_code": "reason_A",
    }


def test_late_provenance_and_primary_inputs_change_attempt_identity(
    tmp_path: Path,
) -> None:
    first_process, first_output = run_provider(
        tmp_path,
        provenance_label="independently_verified",
        primary_metric_value=1,
    )
    assert first_process.returncode == 0, first_process.stderr
    first = json.loads(first_output.read_text(encoding="utf-8"))

    provenance_process, provenance_output = run_provider(
        tmp_path,
        provenance_label="producer_attested",
        primary_metric_value=1,
    )
    assert provenance_process.returncode == 0, provenance_process.stderr
    provenance_changed = json.loads(provenance_output.read_text(encoding="utf-8"))
    assert provenance_changed["input_state_fingerprint"] != first["input_state_fingerprint"]
    assert provenance_changed["attempt_identity"] != first["attempt_identity"]

    primary_process, primary_output = run_provider(
        tmp_path,
        provenance_label="independently_verified",
        primary_metric_value=2,
    )
    assert primary_process.returncode == 0, primary_process.stderr
    primary_changed = json.loads(primary_output.read_text(encoding="utf-8"))
    assert primary_changed["input_state_fingerprint"] != first["input_state_fingerprint"]
    assert primary_changed["attempt_identity"] != first["attempt_identity"]


def test_identical_prepare_only_evaluation_has_stable_mutation_hash(
    tmp_path: Path,
) -> None:
    first_process, first_output = run_provider(
        tmp_path,
        metric_value=1,
        previous_metric_value=1,
    )
    assert first_process.returncode == 0, first_process.stderr
    first = json.loads(first_output.read_text(encoding="utf-8"))
    second_process, second_output = run_provider(
        tmp_path,
        metric_value=1,
        previous_metric_value=1,
    )
    assert second_process.returncode == 0, second_process.stderr
    second = json.loads(second_output.read_text(encoding="utf-8"))

    assert (
        first["durable_mutation_candidate"]["candidate_sha256"]
        == second["durable_mutation_candidate"]["candidate_sha256"]
    )
    assert (
        first["durable_mutation_candidate"]["operations"]
        == second["durable_mutation_candidate"]["operations"]
    )
