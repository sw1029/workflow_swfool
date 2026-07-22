from __future__ import annotations

import json
import ast
import copy
import subprocess
from pathlib import Path

import pytest

from orchestrate_task_cycle.collect_cycle_context import collect_agent_goal
from orchestrate_task_cycle.cycle_ledger import append_event, init_cycle, read_events
from orchestrate_task_cycle.model_context import project_model_context
from orchestrate_task_cycle.packet.registry import TARGET_BUILDERS
from orchestrate_task_cycle.result_contract.configuration import COMMON_FIELDS, TARGETS
from orchestrate_task_cycle.stage.builder import ResultBuilder
from orchestrate_task_cycle.stage.contracts import (
    canonical_sha256,
    preparation_identity,
    state_fingerprint,
)
from orchestrate_task_cycle.stage.cli import _parser as stage_parser, _run as stage_run
from orchestrate_task_cycle.stage.packet_projection import MAX_MODEL_PACKET_BYTES
from orchestrate_task_cycle.stage.preparation_store import (
    load_published_preparation,
    publish_preparation,
)
from orchestrate_task_cycle.stage.service import (
    _model_packet,
    advance_stage,
    prepare_stage,
    submit_stage,
)
from orchestrate_task_cycle.stage.specs import TARGET_COMPILE_SPECS
from orchestrate_task_cycle.transition.constants import ORDER


def _base_context() -> dict:
    authority = {
        "step": "authority",
        "status": "completed",
        "event_id": "authority-event",
        "axes": {
            "external_input": {
                "status": "satisfied",
                "evidence_ids": ["evidence-external"],
            },
            "goal_truth": {"status": "not_required", "evidence_ids": []},
            "risk_acceptance": {
                "status": "required",
                "evidence_ids": ["evidence-risk"],
            },
            "design_selection": {"status": "not_required", "evidence_ids": []},
        },
        "scope": {"task_id": "task-1", "cycle_id": "cycle-1"},
        "full_body_sentinel": "must-not-survive",
    }
    packet = {
        "actionable_clause_ids": ["directive-1", "directive-2"],
        "canonical_clause_ids": ["directive-1", "directive-2"],
        "source_digests": {"advice-1": "a" * 64},
        "clause_source_digests": {
            "directive-1": "a" * 64,
            "directive-2": "a" * 64,
        },
        "advice_packet_digest": "b" * 64,
        "normalized_packet_use": "direction_evidence_only",
        "used_advice": [
            {
                "advice_id": "advice-1",
                "path": ".agent_advice/active/advice-1.md",
                "raw_source_path": ".agent_advice/raw/sensitive-source.md",
                "source_digest": "a" * 64,
                "content_sha256": "c" * 64,
                "fields": {
                    "fidelity_status": "ok",
                    "directives": [
                        {
                            "directive_id": "directive-1",
                            "directive_state": "pending",
                            "directive_text": "Preserve the exact first directive.",
                        },
                        {
                            "directive_id": "directive-2",
                            "directive_state": "pending",
                            "directive_text": "Preserve the exact second directive.",
                        },
                    ],
                },
            }
        ],
    }
    return {
        "workspace": "/workspace",
        "collected_at": "volatile",
        "task_md": {
            "path": "task.md",
            "exists": True,
            "is_file": True,
            "sha256": "d" * 64,
            "size_bytes": 40,
        },
        "agent_goal": {
            "available_goal_truth": [".agent_goal/final_goal.md"],
            "used_goal_truth": [".agent_goal/final_goal.md"],
            "goal_truth_files": {
                "final_goal.md": {
                    "path": ".agent_goal/final_goal.md",
                    "exists": True,
                    "is_file": True,
                    "sha256": "e" * 64,
                    "size_bytes": 20,
                }
            },
        },
        "external_advice": {
            "active_count": 1,
            "normalized_packet_status": "available",
            "normalized_packet": packet,
        },
        "cycle_state": {
            "latest_cycle_id": "cycle-1",
            "packets": [],
            "current_stage": {
                "event_count": 1,
                "status": "completed",
                "steps": {"authority": authority},
                "latest_event": authority,
            },
        },
        "task_state": {"task_pack": {}, "task_miss": {}},
        "selection_publication": {"status": "clear"},
        "git": {
            "inside_work_tree": True,
            "head": "abc123",
            "diff_name_status": ["M\tfile-a.py", "M\tfile-b.py"],
            "untracked": ["file-c.py"],
            "status_short_branch": ["## main", " M file-a.py"],
            "commands": {"secret": "raw-git-output-must-not-survive"},
        },
        "issue": {
            "files": [
                {"path": ".issue/a.json", "exists": True, "sha256": "f" * 64},
                {"path": ".issue/b.json", "exists": True, "sha256": "1" * 64},
            ]
        },
    }


def _initialized_workspace(root: Path) -> str:
    (root / "task.md").write_text("# Task\n\nDo bounded work.\n", encoding="utf-8")
    cycle_id = "cycle-stage-test"
    init_cycle(
        root,
        cycle_id,
        "task-stage",
        "stage compiler test",
        stage_compiler_protocol_version=1,
        stage_preparation_schema_version=1,
    )
    advance = advance_stage(root, cycle_id, apply=True, max_steps=2)
    assert advance["stop_reason"] == "awaiting_authority"
    assert read_events(root, cycle_id)[0]["step"] == "context"
    return cycle_id


def _prime_until(root: Path, cycle_id: str, target: str) -> None:
    existing = {event["step"] for event in read_events(root, cycle_id)}
    for step in ORDER:
        if step == target:
            return
        if step in existing:
            continue
        append_event(
            root,
            cycle_id,
            {
                "step": step,
                "status": "completed",
                "event_id": f"fixture-{step}",
                "reason": "dependency-ready stage fixture",
                "task_id": "task-stage",
            },
        )


def _prime_compiled_targets_only(root: Path, cycle_id: str, target: str) -> None:
    existing = {event["step"] for event in read_events(root, cycle_id)}
    for step in ORDER:
        if step == target:
            return
        if step not in TARGET_COMPILE_SPECS or step in existing:
            continue
        append_event(
            root,
            cycle_id,
            {
                "step": step,
                "status": "completed",
                "event_id": f"compiled-only-{step}",
                "reason": "compiled target fixture",
                "task_id": "task-stage",
            },
        )


def test_target_compile_specs_cover_every_packet_and_result_target() -> None:
    assert set(TARGET_COMPILE_SPECS) == TARGETS
    assert set(TARGET_BUILDERS) < set(TARGET_COMPILE_SPECS)
    for target, spec in TARGET_COMPILE_SPECS.items():
        expected = {"step", *COMMON_FIELDS[target]}
        classified = [
            *spec.derived_fields,
            *spec.semantic_fields,
            *spec.owner_receipt_fields,
            *spec.reasoned_not_applicable_fields,
        ]
        assert set(classified) == expected
        assert len(classified) == len(set(classified))
        semantic = set(spec.semantic_fields) | set(spec.optional_semantic_fields)
        owner = set(spec.owner_receipt_fields) | set(spec.optional_owner_fields)
        assert semantic.isdisjoint(owner)
    assert "next_task_id" in TARGET_COMPILE_SPECS["derive"].optional_semantic_fields


def test_stage_advance_dry_run_does_not_append_context(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    cycle_id = "cycle-dry-run"
    init_cycle(tmp_path, cycle_id, "task-dry-run", "dry run")

    output = advance_stage(tmp_path, cycle_id, apply=False)

    assert output["status"] == "ready"
    assert output["actions"][0]["kind"] == "append_system_context"
    assert read_events(tmp_path, cycle_id) == []


def test_model_projection_preserves_exact_directives_and_authority_axes() -> None:
    projected = project_model_context(_base_context(), max_paths=1)

    assert projected["projection_status"] == "ready"
    assert projected["semantic_context_binding"]["ref"] is None
    assert projected["semantic_context_binding"]["binding_scope"] == (
        "model_projection_without_binding_and_metrics"
    )
    assert projected["semantic_context_binding"]["excluded_observation_fields"] == [
        "collected_at"
    ]
    assert projected["advice"]["actionable_clause_ids"] == [
        "directive-1",
        "directive-2",
    ]
    assert [
        row["directive_id"] for row in projected["advice"]["items"][0]["directives"]
    ] == ["directive-1", "directive-2"]
    assert (
        projected["authority"]["axes"]
        == _base_context()["cycle_state"]["current_stage"]["steps"]["authority"]["axes"]
    )
    assert projected["cycle"]["latest_event"] is None
    assert projected["cycle"]["latest_event_ref"] == {
        "step": "authority",
        "event_id": "authority-event",
    }
    assert projected["git"]["changed_paths"]["truncated"] is True
    assert projected["diagnostic_artifacts"]["truncated"] is True
    encoded = json.dumps(projected, sort_keys=True)
    assert "raw-git-output-must-not-survive" not in encoded
    assert "must-not-survive" not in encoded
    assert "sensitive-source.md" not in encoded

    changed_timestamp = _base_context()
    changed_timestamp["collected_at"] = "another-volatile-time"
    changed_projection = project_model_context(changed_timestamp, max_paths=1)
    assert projected == changed_projection
    assert state_fingerprint(projected) == state_fingerprint(changed_projection)


def test_model_projection_fails_closed_when_required_payload_is_too_large() -> None:
    context = _base_context()
    context["external_advice"]["normalized_packet"]["used_advice"][0]["fields"][
        "directives"
    ][0]["directive_text"] = "x" * 300_000

    projected = project_model_context(context, max_paths=40)

    assert projected["projection_status"] == "block"
    assert projected["stop_reason"] == "model_context_budget_exceeded"
    assert projected["compiler_metrics"]["essential_projected_bytes"] > 262_144


def test_model_packet_reuses_only_compact_advice_projection() -> None:
    full = _base_context()
    model = project_model_context(full, max_paths=40)

    packet = _model_packet("acceptance", full, model, "normal")

    encoded = json.dumps(packet, sort_keys=True)
    assert packet["used_advice"] == model["advice"]["items"]
    assert "raw_source_path" not in encoded
    assert "sensitive-source.md" not in encoded
    assert all("fields" not in item for item in packet["used_advice"])


def test_model_packet_does_not_reimport_large_legacy_context() -> None:
    full = _base_context()
    sentinel = "large-legacy-active-pack-sentinel"
    full["task_state"]["task_pack"]["active_pack"] = {
        "unbounded_body": sentinel + ("x" * 800_000)
    }
    model = project_model_context(full, max_paths=40)

    packet = _model_packet("acceptance", full, model, "normal")
    encoded = json.dumps(packet, ensure_ascii=False, sort_keys=True).encode("utf-8")

    assert sentinel.encode("utf-8") not in encoded
    assert "task_pack_packet" not in packet
    assert len(encoded) < MAX_MODEL_PACKET_BYTES


def test_model_packet_fails_closed_above_hard_byte_budget() -> None:
    full = _base_context()
    model = project_model_context(full, max_paths=40)
    model["advice"]["items"][0]["directives"][0]["directive_text"] = "x" * (
        MAX_MODEL_PACKET_BYTES + 1
    )

    with pytest.raises(ValueError, match="model_packet_budget_exceeded"):
        _model_packet("acceptance", full, model, "normal")


def test_goal_collector_reuses_supplied_cycle_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_collection(*_args, **_kwargs):
        raise AssertionError("cycle state was collected twice")

    monkeypatch.setattr(
        "orchestrate_task_cycle.collect_cycle_context.collect_cycle_state",
        unexpected_collection,
    )
    goal = collect_agent_goal(
        tmp_path,
        12,
        {"used_goal_truth": [".agent_goal/final_goal.md"]},
    )
    assert goal["used_goal_truth"] == [".agent_goal/final_goal.md"]


def test_stage_submit_dry_run_apply_and_replay_are_idempotent(
    tmp_path: Path,
) -> None:
    cycle_id = _initialized_workspace(tmp_path)
    _prime_until(tmp_path, cycle_id, "visible_increment")
    preparation = prepare_stage(tmp_path, cycle_id, "visible_increment")
    assert not (tmp_path / ".agent_advice").exists()
    judgment = {
        "semantic": {
            "status": "recorded",
            "summary": "Recorded one bounded workflow increment.",
            "delta_types": ["workflow_artifact"],
            "not_validation_evidence": True,
            "blockers": [],
        },
        "owner_result": {
            "changed_files": [],
            "artifacts": [],
            "evidence_paths": ["task.md"],
        },
    }

    before = len(read_events(tmp_path, cycle_id))
    dry_run = submit_stage(tmp_path, preparation, judgment, mode="block")
    assert dry_run["status"] != "block", dry_run
    assert dry_run["applied"] is False
    assert len(read_events(tmp_path, cycle_id)) == before
    assert not (tmp_path / dry_run["result_artifact_ref"]).exists()

    applied = submit_stage(tmp_path, preparation, judgment, mode="block", apply=True)
    assert applied["applied"] is True
    assert applied["event_duplicate"] is False
    assert (tmp_path / applied["result_artifact_ref"]).is_file()
    assert len(read_events(tmp_path, cycle_id)) == before + 1

    replay = submit_stage(tmp_path, preparation, judgment, mode="block", apply=True)
    assert replay["applied"] is True
    assert replay["event_duplicate"] is True
    assert len(read_events(tmp_path, cycle_id)) == before + 1


def test_transition_failure_precedes_result_artifact_write(tmp_path: Path) -> None:
    cycle_id = _initialized_workspace(tmp_path)
    _prime_compiled_targets_only(tmp_path, cycle_id, "visible_increment")
    preparation = prepare_stage(tmp_path, cycle_id, "visible_increment")
    judgment = {
        "semantic": {
            "status": "recorded",
            "summary": "Transition validation must run first.",
            "delta_types": ["workflow_artifact"],
            "not_validation_evidence": True,
            "blockers": [],
        },
        "owner_result": {
            "changed_files": [],
            "artifacts": [],
            "evidence_paths": ["task.md"],
        },
    }
    before = len(read_events(tmp_path, cycle_id))

    output = submit_stage(tmp_path, preparation, judgment, mode="block", apply=True)

    assert output["status"] == "block"
    assert output["stop_reason"] == "blocked_transition"
    assert output["transition_validation"]["status"] == "block"
    assert len(read_events(tmp_path, cycle_id)) == before
    packet_dir = tmp_path / ".task" / "cycle" / cycle_id / "packets"
    assert not list(packet_dir.glob("result-*.json"))


def test_unrelated_git_change_does_not_stale_non_git_target(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    cycle_id = _initialized_workspace(tmp_path)
    _prime_until(tmp_path, cycle_id, "acceptance")
    first = prepare_stage(tmp_path, cycle_id, "acceptance")

    (tmp_path / "unrelated.tmp").write_text("unrelated\n", encoding="utf-8")
    second = prepare_stage(tmp_path, cycle_id, "acceptance")

    assert "git" not in first["fingerprint_roles"]
    assert first["state_fingerprint"] == second["state_fingerprint"]
    assert first["preparation_id"] == second["preparation_id"]


def test_prepare_and_publication_are_stable_across_observation_times(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle_id = _initialized_workspace(tmp_path)
    _prime_until(tmp_path, cycle_id, "acceptance")
    observed_at = iter(("2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"))
    monkeypatch.setattr(
        "orchestrate_task_cycle.collect_cycle_context.now_iso",
        lambda: next(observed_at),
    )

    first = prepare_stage(tmp_path, cycle_id, "acceptance")
    first_publication = publish_preparation(tmp_path, first)
    second = prepare_stage(tmp_path, cycle_id, "acceptance")
    second_publication = publish_preparation(tmp_path, second)

    assert first == second
    assert (
        first_publication["preparation_sha256"]
        == second_publication["preparation_sha256"]
    )
    assert second_publication["artifact_duplicate"] is True


def test_result_builder_rejects_derived_override_and_owner_bypass(
    tmp_path: Path,
) -> None:
    cycle_id = _initialized_workspace(tmp_path)
    _prime_until(tmp_path, cycle_id, "visible_increment")
    preparation = prepare_stage(tmp_path, cycle_id, "visible_increment")

    with pytest.raises(ValueError, match="conflicting_derived_field"):
        ResultBuilder().build(
            preparation,
            {"semantic": {"task_id": "forged-task"}},
        )
    with pytest.raises(ValueError, match="owner_result contains unclassified"):
        ResultBuilder().build(
            preparation,
            {"owner_result": {"status": "recorded"}},
        )


def test_submit_recompiles_and_rejects_self_hashed_preparation_tamper(
    tmp_path: Path,
) -> None:
    cycle_id = _initialized_workspace(tmp_path)
    _prime_until(tmp_path, cycle_id, "visible_increment")
    preparation = prepare_stage(tmp_path, cycle_id, "visible_increment")
    tampered = copy.deepcopy(preparation)
    tampered["derived_values"]["task_id"] = "forged-task"
    tampered["preparation_id"] = (
        "stageprep-" + canonical_sha256(preparation_identity(tampered))[:32]
    )
    judgment = {
        "semantic": {
            "status": "recorded",
            "summary": "Tampered preparation must fail.",
            "delta_types": ["workflow_artifact"],
            "not_validation_evidence": True,
            "blockers": [],
        },
        "owner_result": {
            "changed_files": [],
            "artifacts": [],
            "evidence_paths": ["task.md"],
        },
    }
    before = len(read_events(tmp_path, cycle_id))

    with pytest.raises(ValueError, match="preparation_tampered"):
        submit_stage(tmp_path, tampered, judgment, mode="block", apply=True)

    assert len(read_events(tmp_path, cycle_id)) == before
    packet_dir = tmp_path / ".task" / "cycle" / cycle_id / "packets"
    assert not list(packet_dir.glob("result-*.json"))


def test_submit_rejects_stale_preparation_without_writes(tmp_path: Path) -> None:
    cycle_id = _initialized_workspace(tmp_path)
    _prime_until(tmp_path, cycle_id, "visible_increment")
    preparation = prepare_stage(tmp_path, cycle_id, "visible_increment")
    (tmp_path / "task.md").write_text(
        "# Task\n\nChanged after prepare.\n", encoding="utf-8"
    )
    judgment = {
        "semantic": {
            "status": "recorded",
            "summary": "This must not publish.",
            "delta_types": ["workflow_artifact"],
            "not_validation_evidence": True,
            "blockers": [],
        },
        "owner_result": {
            "changed_files": [],
            "artifacts": [],
            "evidence_paths": ["task.md"],
        },
    }
    before = len(read_events(tmp_path, cycle_id))

    output = submit_stage(tmp_path, preparation, judgment, mode="block", apply=True)

    assert output["status"] == "block"
    assert output["stop_reason"] == "stale_preparation"
    assert output["applied"] is False
    assert len(read_events(tmp_path, cycle_id)) == before


def test_published_preparation_is_compact_exact_and_replay_safe(
    tmp_path: Path,
) -> None:
    cycle_id = _initialized_workspace(tmp_path)
    _prime_until(tmp_path, cycle_id, "visible_increment")
    preparation = prepare_stage(tmp_path, cycle_id, "visible_increment")

    publication = publish_preparation(tmp_path, preparation)
    replay = publish_preparation(tmp_path, preparation)

    assert publication["status"] == "ok"
    assert publication["applied"] is True
    assert publication["artifact_duplicate"] is False
    assert replay["artifact_duplicate"] is True
    assert "model_context" not in publication
    assert "model_packet" not in publication
    assert (
        load_published_preparation(
            tmp_path,
            publication["preparation_ref"],
            publication["preparation_sha256"],
        )
        == preparation
    )
    with pytest.raises(ValueError, match="file digest does not match exact input"):
        load_published_preparation(
            tmp_path,
            publication["preparation_ref"],
            "0" * 64,
        )
    with pytest.raises(ValueError, match="content address"):
        load_published_preparation(
            tmp_path,
            "./" + publication["preparation_ref"],
            publication["preparation_sha256"],
        )
    alias = tmp_path / "preparation-alias.json"
    alias.symlink_to(tmp_path / publication["preparation_ref"])
    with pytest.raises(ValueError, match="must not traverse a symlink"):
        load_published_preparation(
            tmp_path,
            alias.name,
            publication["preparation_sha256"],
        )


def test_stage_submit_cli_consumes_exact_published_preparation_ref(
    tmp_path: Path,
) -> None:
    cycle_id = _initialized_workspace(tmp_path)
    _prime_until(tmp_path, cycle_id, "visible_increment")
    publication = publish_preparation(
        tmp_path, prepare_stage(tmp_path, cycle_id, "visible_increment")
    )
    judgment = {
        "semantic": {
            "status": "recorded",
            "summary": "Exact preparation reference is consumed.",
            "delta_types": ["workflow_artifact"],
            "not_validation_evidence": True,
            "blockers": [],
        },
        "owner_result": {
            "changed_files": [],
            "artifacts": [],
            "evidence_paths": ["task.md"],
        },
    }
    args = stage_parser().parse_args(
        [
            "submit",
            "--root",
            str(tmp_path),
            "--preparation-ref",
            publication["preparation_ref"],
            "--preparation-sha256",
            publication["preparation_sha256"],
            "--judgment",
            json.dumps(judgment),
        ]
    )

    output = stage_run(args)

    assert output["status"] != "block", output
    assert output["preparation_id"] == publication["preparation_id"]
    assert output["applied"] is False


def test_new_production_modules_remain_bounded() -> None:
    package = (
        Path(__file__).resolve().parents[2]
        / "orchestrate-task-cycle"
        / "scripts"
        / "orchestrate_task_cycle"
    )
    paths = [
        package / "collect_cycle_context.py",
        package / "context_support.py",
        package / "context_cli.py",
        package / "model_context.py",
        *(package / "stage").glob("*.py"),
    ]
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        tree = ast.parse("\n".join(lines))
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert len(lines) < 500, path
        assert all(node.end_lineno - node.lineno + 1 <= 140 for node in functions), path
