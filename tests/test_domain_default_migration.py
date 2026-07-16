from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LOOPBACK_SCRIPTS = ROOT / "audit-cycle-loopback" / "scripts"
ORCHESTRATE_SCRIPTS = ROOT / "orchestrate-task-cycle" / "scripts"


for package_root in (LOOPBACK_SCRIPTS, ORCHESTRATE_SCRIPTS):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

import audit_cycle_loopback as loopback  # noqa: E402
from orchestrate_task_cycle import detect_gt_constraint_conflict as gt_conflict  # noqa: E402
from orchestrate_task_cycle import output_delta_contract as output_delta  # noqa: E402
from orchestrate_task_cycle.progress import api as progress_loop  # noqa: E402


LEGACY_METRIC_KEYS = {
    "event_named_ratio",
    "proper_noun_character_ratio",
    "coreference_resolved_ratio",
    "causal_edge_count",
    "windows_covered",
}


def run_loopback(root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "audit_cycle_loopback",
            "evaluate",
            "--root",
            str(root),
            "--cycle-id",
            "cycle-domain-default",
            "--task-id",
            "task-domain-default",
            "--artifact-family",
            "primary_output",
            "--semantic-signature",
            "generic_output",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=root,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(
                item
                for item in (
                    str(LOOPBACK_SCRIPTS),
                    str(ORCHESTRATE_SCRIPTS),
                    os.environ.get("PYTHONPATH", ""),
                )
                if item
            ),
        },
    )


def test_generic_quality_gates_do_not_inherit_domain_metrics(tmp_path: Path) -> None:
    assert loopback.QUALITY_DELTA_KEYS == ()
    assert loopback.FRONTIER_CHECK_KEYS == set()
    assert loopback.LADDER_RANK == {}
    assert progress_loop.QUALITY_DELTA_KEYS == ()
    assert loopback.infer_ladder_rung("domain-specific capability wording") is None
    assert loopback.normalize_ladder_rung("adapter-rung-a") == "adapter_rung_a"

    direct_gate = loopback.coverage_quality_delta_gate(
        {"quality_score": 1},
        {},
        0,
        1e-9,
    )
    progress_gate = progress_loop.coverage_quality_delta_gate(
        {
            "quality_vector": {"quality_score": 1},
            "previous_quality_vector": {"quality_score": 0},
        }
    )
    contract_gate = output_delta.quality_delta_gate(
        {"quality_score": 1},
        {"quality_score": 0},
    )

    for gate in (direct_gate, progress_gate, contract_gate):
        assert gate["status"] == "not_evaluated"
        assert gate["quality_delta_pass"] is False
        assert gate["current_quality_vector"] == {}
        assert not (LEGACY_METRIC_KEYS & set(gate["current_quality_vector"]))

    proc = run_loopback(tmp_path)
    assert proc.returncode == 2
    packet = json.loads(proc.stdout)
    serialized = json.dumps(packet, sort_keys=True)
    assert packet["quality_delta_policy"]["supplied"] is False
    assert packet["coverage_quality_delta_gate"]["status"] == "not_evaluated"
    assert packet["high_water_mark"] == {"ever_provider_dispatch": False}
    assert not any(metric in serialized for metric in LEGACY_METRIC_KEYS)


def test_explicit_adapter_policy_supplies_metric_keys_and_aliases(tmp_path: Path) -> None:
    policy = {
        "keys": ["quality_score"],
        "aliases": {"quality_score": ["score_alias"]},
    }
    direct_gate = loopback.coverage_quality_delta_gate(
        {"score_alias": 2},
        {"quality_score": 1},
        0,
        1e-9,
        policy,
    )
    progress_gate = progress_loop.coverage_quality_delta_gate(
        {
            "quality_vector": {"score_alias": 2},
            "previous_quality_vector": {"quality_score": 1},
            "quality_delta_policy": policy,
        }
    )
    contract_gate = output_delta.quality_delta_gate(
        {"score_alias": 2},
        {"quality_score": 1},
        quality_delta_policy=policy,
    )
    for gate in (direct_gate, progress_gate, contract_gate):
        assert gate["status"] == "pass"
        assert gate["improved_fields"] == ["quality_score"]
        assert gate["current_quality_vector"] == {"quality_score": 2.0}

    adapter = tmp_path / "domain_adapter.py"
    artifact = tmp_path / "artifact_A.json"
    artifact.write_text('{"artifact_id":"artifact_A"}\n', encoding="utf-8")
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    adapter.write_text(
        "\n".join(
            [
                "def quality_vector(**kwargs):",
                "    ref = kwargs.get('decision_artifact_ref') or {}",
                "    return {'quality_vector': {'score_alias': 2, 'current_output_fingerprint': 'fp-generic', 'artifact_id': ref.get('artifact_id'), 'artifact_sha256': ref.get('artifact_sha256'), 'production_lane_identity': ref.get('production_lane_identity'), 'body_projection_fingerprint': ref.get('body_projection_fingerprint'), 'verification_input_ids': ref.get('verification_input_ids')}}",
                "def quality_delta_policy(**kwargs):",
                "    return {'keys': ['quality_score'], 'aliases': {'quality_score': ['score_alias']}}",
                "def substance_metrics(**kwargs):",
                "    return {'substance_metrics': {'output_rows': 1}}",
                "def facet_root_map(**kwargs):",
                "    return {'generic_output': 'generic_output'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    proc = run_loopback(
        tmp_path,
        "--domain-adapter",
        str(adapter),
        "--artifact-path",
        artifact.name,
        "--artifact-ref-json",
        json.dumps(
            {
                "artifact_id": "artifact_A",
                "artifact_class": "primary_output",
                "artifact_path_or_store_ref": artifact.name,
                "artifact_sha256": artifact_sha256,
                "production_lane_identity": "lane_L",
                "body_projection_fingerprint": artifact_sha256,
                "verification_input_ids": ["source_cohort_C"],
            },
            sort_keys=True,
        ),
    )
    assert proc.returncode == 0, proc.stderr
    packet = json.loads(proc.stdout)
    assert packet["quality_delta_policy"] == {
        "aliases": {"quality_score": ["quality_score", "score_alias"]},
        "keys": ["quality_score"],
        "supplied": True,
    }
    assert packet["coverage_quality_delta_gate"]["quality_delta_pass"] is True
    assert packet["high_water_mark"]["quality_score"] == 2.0


def test_explicit_adapter_can_restore_legacy_domain_metrics_and_ladder() -> None:
    keys = [
        "event_named_ratio",
        "proper_noun_character_ratio",
        "coreference_resolved_ratio",
        "causal_edge_count",
        "windows_covered",
    ]
    policy = {
        "keys": keys,
        "aliases": {
            "causal_edge_count": ["causal_or_temporal_edge_count"],
            "windows_covered": ["source_windows_covered"],
        },
    }
    gate = loopback.coverage_quality_delta_gate(
        {
            "event_named_ratio": 1,
            "proper_noun_character_ratio": 1,
            "coreference_resolved_ratio": 1,
            "causal_or_temporal_edge_count": 1,
            "source_windows_covered": 1,
        },
        {},
        0,
        1e-9,
        policy,
    )
    assert gate["improved_fields"] == keys
    option = loopback.first_actionable_capability_ladder_option(
        {
            "rungs": [
                {
                    "rung": "M0_single_work_full_window",
                    "selected_task_kind": "bounded_extraction",
                    "satisfied": False,
                    "actionable": True,
                }
            ]
        }
    )
    assert option is not None
    assert option["rung"] == "M0_single_work_full_window"
    assert option["selected_task_kind"] == "bounded_extraction"


def test_output_delta_contract_requires_explicit_policy(tmp_path: Path) -> None:
    payload = {
        "produced_domain_delta": True,
        "changed_vs_previous": True,
        "semantic_progress": True,
        "quality_vector": {"score_alias": 2},
        "previous_quality_vector": {"quality_score": 1},
    }
    generic = output_delta.normalize_provider_result(
        tmp_path,
        None,
        {},
        payload,
        "complete",
    )
    assert generic["coverage_quality_delta_gate"]["status"] == "not_evaluated"

    adapted = output_delta.normalize_provider_result(
        tmp_path,
        None,
        {
            "quality_delta_policy": {
                "keys": ["quality_score"],
                "aliases": {"quality_score": ["score_alias"]},
            }
        },
        payload,
        "complete",
    )
    assert adapted["coverage_quality_delta_gate"]["status"] == "pass"
    assert adapted["coverage_quality_delta_gate"]["improved_fields"] == ["quality_score"]


def test_generalization_conflict_is_adapter_policy_owned(tmp_path: Path) -> None:
    goal_dir = tmp_path / ".agent_goal"
    goal_dir.mkdir()
    (goal_dir / "final_goal.md").write_text("Generalize across units.\n", encoding="utf-8")
    task = tmp_path / "task.md"
    task.write_text("single_unit=true\n", encoding="utf-8")
    behavior = {"selected_unit_count": 1, "target_unit_count": 3}

    generic = gt_conflict.analyze(tmp_path, task, behavior)
    assert generic["generalization_policy_supplied"] is False
    assert generic["generalization_sources"] == []
    assert generic["status"] == "ok"

    policy = {
        "generalization": {
            "required_patterns": ["generalize across units"],
            "single_unit_patterns": ["single_unit\\s*=\\s*true"],
            "selected_count_paths": ["selected_unit_count"],
            "target_count_paths": ["target_unit_count"],
            "single_unit_flag_paths": ["single_unit"],
        }
    }
    adapted = gt_conflict.analyze(tmp_path, task, behavior, policy)
    assert adapted["generalization_policy_supplied"] is True
    assert adapted["status"] == "block"
    assert adapted["conflicts"][0]["reason"] == "single_unit_invariant_blocks_generalization"


def test_global_docs_define_no_fixed_domain_ladder() -> None:
    paths = [
        ROOT / "derive-improvement-task" / "SKILL.md",
        ROOT / "orchestrate-task-cycle" / "references" / "anti-loop-progress-gates.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "M0_single_work_full_window" not in text
    assert "M4_unseen_15" not in text
    assert "corpus-scale ladder" not in text


def test_durable_loopback_output_emits_hash_bound_adjacent_handoff(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact_A.json"
    artifact.write_text('{"artifact_id":"artifact_A"}\n', encoding="utf-8")
    artifact_sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    packet_path = tmp_path / "packet_K.json"
    proc = run_loopback(
        tmp_path,
        "--artifact-family",
        "family_F",
        "--artifact-path",
        artifact.name,
        "--artifact-ref-json",
        json.dumps(
            {
                "artifact_id": "artifact_A",
                "artifact_class": "family_F",
                "artifact_path_or_store_ref": artifact.name,
                "artifact_sha256": artifact_sha256,
                "production_lane_identity": "lane_L",
            },
            sort_keys=True,
        ),
        "--blocker-signature",
        "blocker_A",
        "--output",
        packet_path.name,
    )

    assert proc.returncode == 2
    emitted = json.loads(proc.stdout)
    durable = json.loads(packet_path.read_text(encoding="utf-8"))
    handoff = emitted["anti_loop_handoff"]
    assert handoff["handoff_contract_version"] == 1
    assert handoff["applicability"] == "required"
    assert handoff["packet_ref"] == packet_path.name
    assert handoff["packet_sha256"] == hashlib.sha256(packet_path.read_bytes()).hexdigest()
    assert handoff["artifact_id"] == durable["artifact_id"] == "artifact_A"
    assert handoff["artifact_sha256"] == durable["artifact_sha256"] == artifact_sha256
    assert handoff["blocker_signature"] == durable["blocker_signature"] == "blocker_A"
    assert "anti_loop_handoff" not in durable
