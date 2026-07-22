from __future__ import annotations

import json
import hashlib
import inspect
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manage-agent-authority" / "scripts"))

from manage_agent_authority import authority_cli  # noqa: E402
from manage_agent_authority.decision_publication import (  # noqa: E402
    evaluate_and_publish,
)
from manage_agent_authority.operation_compiler import (  # noqa: E402
    compilation_inputs,
    compile_operation,
    validate_compilation,
)
from manage_agent_authority.operation_request import build_request  # noqa: E402


AT = "2026-07-19T10:00:00+09:00"


def _seed(root: Path) -> dict[str, object]:
    subject = root / "plans/task-transition.json"
    subject.parent.mkdir(parents=True, exist_ok=True)
    subject.write_text('{"plan":true}\n', encoding="utf-8")
    goal = root / ".agent_goal/goal_architecture.md"
    goal.parent.mkdir(parents=True, exist_ok=True)
    goal.write_text("# Goal\n", encoding="utf-8")
    return {
        "skill_id": "task-doctor",
        "operation_id": "mutate_task_scope",
        "subject": {"ref": "plans/task-transition.json", "revision": "plan-1"},
        "scope": {"cycle_id": "cycle-1", "task_id": "task-1", "pack_id": None},
        "actor_rank": "S0",
        "context": {
            "external_input_status": "not_required",
            "goal_truth_status": "aligned",
            "risk_acceptance_status": "not_required",
            "design_selection_status": "not_required",
        },
        "session_ceiling": {
            "capabilities": ["task.scope.mutate"],
            "risk_ceiling": "R3",
            "mutation_classes": ["local_mutation"],
            "evidence_id": "session-1",
        },
        "goal_autonomy_envelope": {
            "envelope_id": "envelope-1",
            "capabilities": ["task.scope.mutate"],
            "risk_ceiling": "R3",
            "decision_classes": ["D2"],
            "subjects": [hashlib.sha256(subject.read_bytes()).hexdigest()],
            "operations": ["task-doctor:2.2.0:mutate_task_scope:1"],
            "source_ref": ".agent_goal/goal_architecture.md",
        },
    }


def test_compiler_derives_closed_inputs_deterministically(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    first = compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)
    second = compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)

    assert first == second
    assert validate_compilation(first) == first
    assert first["request"]["required_capabilities"] == ["task.scope.mutate"]
    assert first["request"]["effect_class"] == "retarget_or_replace_task"
    assert first["request"]["subject"]["kind"] == "task_transition_plan"
    assert first["source_and_grant_requirements"] == {
        "authority_applicability": "required",
        "authorization_mechanism": "grant",
        "source_rank_floor": "S2",
        "requires_source_approval": True,
        "requires_grant": True,
        "self_authorizing": False,
    }
    request, context = compilation_inputs(tmp_path, first, skills_root=ROOT)
    assert request == first["request"]
    assert context == first["evaluation_context"]


def test_compiler_legacy_idempotency_contract_is_unchanged(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    compiled = compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)

    assert compiled["request"]["idempotency_key"] == (
        f"request-{compiled['seed_fingerprint'][:24]}"
    )
    assert compiled["field_provenance"]["seed_bound"] == [
        "operation identity",
        "subject.ref",
        "subject.revision",
        "scope",
        "independent decision axes",
        "session and goal ceilings",
    ]

    seed["trusted_request_idempotency_key"] = "selected-successor-exact"
    with pytest.raises(SystemExit, match="unknown fields"):
        compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)


def test_compiler_accepts_only_trusted_exact_idempotency_override(
    tmp_path: Path,
) -> None:
    assert inspect.signature(compile_operation).parameters[
        "trusted_request_idempotency_key"
    ].kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.signature(build_request).parameters[
        "trusted_request_idempotency_key"
    ].kind is inspect.Parameter.KEYWORD_ONLY
    seed = _seed(tmp_path)
    legacy = compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)
    arguments = {
        "compiled_at": AT,
        "trusted_request_idempotency_key": "selected-successor-exact",
        "skills_root": ROOT,
    }

    first = compile_operation(tmp_path, seed, **arguments)
    second = compile_operation(tmp_path, seed, **arguments)

    assert first == second
    assert first["request"]["idempotency_key"] == "selected-successor-exact"
    assert first["seed_fingerprint"] != legacy["seed_fingerprint"]
    assert first["compilation_fingerprint"] != legacy["compilation_fingerprint"]
    assert "request.idempotency_key (trusted owner binding)" in first[
        "field_provenance"
    ]["seed_bound"]
    with pytest.raises(SystemExit, match="trusted request idempotency key"):
        compile_operation(
            tmp_path,
            seed,
            compiled_at=AT,
            trusted_request_idempotency_key="wild*",
            skills_root=ROOT,
        )


def test_evaluate_and_publish_derives_decision_and_replays(tmp_path: Path) -> None:
    compiled = compile_operation(
        tmp_path, _seed(tmp_path), compiled_at=AT, skills_root=ROOT
    )

    first = evaluate_and_publish(
        tmp_path,
        compiled["request"],
        compiled["evaluation_context"],
        evaluated_at=AT,
        skills_root=ROOT,
    )
    second = evaluate_and_publish(
        tmp_path,
        compiled["request"],
        compiled["evaluation_context"],
        evaluated_at=AT,
        skills_root=ROOT,
    )

    assert first == second
    assert first["decision"] == "approval_required"
    assert hashlib.sha256((tmp_path / first["decision_ref"]).read_bytes()).hexdigest() == (
        first["decision_sha256"]
    )
    assert len(list((tmp_path / ".task/authorization/decisions").glob("*.json"))) == 1


def test_evaluate_and_publish_cannot_accept_caller_decision(tmp_path: Path) -> None:
    compiled = compile_operation(
        tmp_path, _seed(tmp_path), compiled_at=AT, skills_root=ROOT
    )

    assert "decision" not in inspect.signature(evaluate_and_publish).parameters
    with pytest.raises(TypeError, match="decision"):
        evaluate_and_publish(
            tmp_path,
            compiled["request"],
            compiled["evaluation_context"],
            evaluated_at=AT,
            skills_root=ROOT,
            **{"decision": {"decision": "allowed"}},
        )


def test_compiler_rejects_manifest_downgrades_and_stale_subject(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    seed["classification"] = {"risk_tier": "R0"}
    with pytest.raises(SystemExit, match="cannot lower"):
        compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)

    seed.pop("classification")
    compiled = compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)
    (tmp_path / "plans/task-transition.json").write_text(
        '{"plan":false}\n', encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="recompile required"):
        compilation_inputs(tmp_path, compiled, skills_root=ROOT)


def test_compiler_does_not_expand_asserted_session_or_goal_ceiling(
    tmp_path: Path,
) -> None:
    seed = _seed(tmp_path)
    seed["session_ceiling"]["capabilities"] = ["task.scope.read"]
    with pytest.raises(SystemExit, match="session ceiling does not cover"):
        compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)

    seed = _seed(tmp_path)
    seed["goal_autonomy_envelope"]["subjects"] = ["0" * 64]
    with pytest.raises(SystemExit, match="exact subject digest"):
        compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)


def test_compiler_rejects_malformed_nested_ceiling_without_type_error(
    tmp_path: Path,
) -> None:
    seed = _seed(tmp_path)
    seed["session_ceiling"]["capabilities"] = "task.scope.mutate"
    with pytest.raises(SystemExit, match="capabilities must be a non-empty list"):
        compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)

    seed = _seed(tmp_path)
    seed["goal_autonomy_envelope"]["operations"] = {"operation": "wild"}
    with pytest.raises(SystemExit, match="operations must contain exact"):
        compile_operation(tmp_path, seed, compiled_at=AT, skills_root=ROOT)


def test_cli_evaluate_accepts_compiled_operation_without_full_json_reentry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    compiled = compile_operation(
        tmp_path, _seed(tmp_path), compiled_at=AT, skills_root=ROOT
    )
    compiled_path = tmp_path / "compiled.json"
    compiled_path.write_text(json.dumps(compiled), encoding="utf-8")

    result = authority_cli.main(
        [
            "evaluate",
            "--root", str(tmp_path),
            "--at", AT,
            "--skills-root", str(ROOT),
            "--compiled-operation", str(compiled_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert result == 0
    assert payload["request_sha256"] == compiled["request_sha256"]
    assert payload["decision"] == "approval_required"


def test_cli_publish_compilation_replays_compact_binding_and_fails_on_conflict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    seed_path = tmp_path / "seed.json"
    seed_path.write_text(json.dumps(_seed(tmp_path)), encoding="utf-8")
    arguments = [
        "compile-operation",
        "--root", str(tmp_path),
        "--at", AT,
        "--skills-root", str(ROOT),
        "--seed", str(seed_path),
        "--publish",
    ]

    assert authority_cli.main(arguments) == 0
    first = json.loads(capsys.readouterr().out)
    assert set(first) == {"ref", "sha256", "compilation_fingerprint"}
    published = tmp_path / first["ref"]
    assert published.name == (
        f"operation_compilation-{first['compilation_fingerprint']}.json"
    )
    assert hashlib.sha256(published.read_bytes()).hexdigest() == first["sha256"]
    compilation = json.loads(published.read_text(encoding="utf-8"))
    assert compilation["artifact_kind"] == "authority_operation_compilation"
    assert compilation["source_and_grant_requirements"]["self_authorizing"] is False

    assert authority_cli.main(arguments) == 0
    assert json.loads(capsys.readouterr().out) == first

    published.write_text('{"tampered":true}\n', encoding="utf-8")
    assert authority_cli.main(arguments) == 2
    conflict = json.loads(capsys.readouterr().out)
    assert conflict["status"] == "error"
    assert "Conflicting operation compilation" in conflict["error"]["message"]


def test_cli_does_not_treat_compilation_as_source_approval() -> None:
    parser = authority_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["register-grant", "--compiled-operation", "{}"])
