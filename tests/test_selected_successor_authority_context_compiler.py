from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from manage_agent_authority.operations import load_operation
from orchestrate_task_cycle.selected_successor import (
    load_selected_successor_bundle,
    prepare_selected_successor_bundle,
)
from orchestrate_task_cycle.selected_successor_authority import (
    prepare_selected_successor_authority,
)
from orchestrate_task_cycle.selected_successor_authority_artifacts import load_packet
from orchestrate_task_cycle.selected_successor_authority_context import (
    MAX_SEMANTIC_INPUT_BYTES,
    load_evaluation_context,
    load_request_context,
)
from orchestrate_task_cycle.selected_successor_authority_context_compiler import (
    prepare_selected_successor_authority_contexts,
)
from orchestrate_task_cycle.selected_successor_cli import main as successor_cli
from selected_successor_authority_support import (
    AT,
    SKILLS_ROOT,
    prepare_authority_inputs,
)
from test_selection_publication_external_transaction import (
    _binding,
    _initialize_active_task,
    _selected_receipt,
)


REQUEST_STORE = "successor_authority_request_contexts"
EVALUATION_STORE = "successor_authority_evaluation_contexts"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _prepared_bundle(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[dict[str, str], dict[str, Any]]:
    _initialize_active_task(root)
    decision = _selected_receipt(root, capsys)
    candidate = root / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    result = prepare_selected_successor_bundle(
        root,
        source_decision=decision,
        task_source=_binding(root, candidate),
        at=AT,
    )
    binding = result["bundle"]
    return binding, load_selected_successor_bundle(root, binding)


def _operation_key(identity: dict[str, str]) -> str:
    return ":".join(
        identity[key]
        for key in (
            "skill_id",
            "skill_version",
            "operation_id",
            "operation_version",
        )
    )


def _semantic_inputs(
    root: Path, bundle: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifests = [
        load_operation(
            row["operation"]["skill_id"],
            row["operation"]["skill_version"],
            row["operation"]["operation_id"],
            row["operation"]["operation_version"],
            skills_root=SKILLS_ROOT,
        )[0]
        for row in bundle["execution_order"]
    ]
    required_capabilities = {
        capability
        for manifest in manifests
        for capability in manifest["required_capabilities"]
    }
    goal_source = root / ".agent_goal/selected-successor-context-source.md"
    goal_source.parent.mkdir(parents=True, exist_ok=True)
    goal_source.write_text("# Selected-successor authority scope\n", encoding="utf-8")
    source_binding = _binding(root, goal_source)
    request = {
        "external_input_status": "not_required",
        "goal_truth_status": "aligned",
        "risk_acceptance_status": "not_required",
        "design_selection_status": "not_required",
        "external_input_evidence": None,
        "risk_acceptance_evidence": None,
        "design_selection_evidence": None,
    }
    session = {
        "capabilities": sorted(
            required_capabilities | {"caller.actual.session.capability"}
        ),
        "risk_ceiling": "R3",
        "mutation_classes": ["local_mutation", "observe"],
        "evidence_id": "actual-session-ceiling",
    }
    envelope = {
        "envelope_id": "actual-goal-envelope",
        "capabilities": sorted(
            required_capabilities | {"caller.actual.goal.capability"}
        ),
        "risk_ceiling": "R3",
        "decision_classes": ["D2", "D3"],
        "subjects": sorted(
            {
                *(row["subject"]["digest"] for row in bundle["execution_order"]),
                "f" * 64,
            }
        ),
        "operations": sorted(
            {
                *(
                    _operation_key(row["operation"])
                    for row in bundle["execution_order"]
                ),
                "caller-skill:1.0.0:observe:1",
            }
        ),
        "source_binding": source_binding,
    }
    return request, session, envelope


def _prepare_contexts(
    root: Path,
    bundle_binding: dict[str, str],
    request: dict[str, Any],
    session: dict[str, Any],
    envelope: dict[str, Any],
) -> dict[str, Any]:
    return prepare_selected_successor_authority_contexts(
        root,
        bundle_binding=bundle_binding,
        actor_rank="S0",
        request_context=request,
        session_ceiling=session,
        goal_autonomy_envelope=envelope,
        skills_root=SKILLS_ROOT,
    )


def _store(root: Path, name: str) -> Path:
    return root / ".task/selection_publication" / name / "sha256"


def _assert_no_context_store(root: Path) -> None:
    assert not _store(root, REQUEST_STORE).exists()
    assert not _store(root, EVALUATION_STORE).exists()


def test_api_publishes_canonical_loader_consumable_contexts_and_replays(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)

    result = _prepare_contexts(
        tmp_path, bundle_binding, request, session, envelope
    )

    assert set(result) == {
        "result_kind",
        "schema_version",
        "status",
        "bundle",
        "request_context",
        "evaluation_context",
        "operation_manifests",
        "authority_effects_applied",
        "idempotent_replay",
        "mutation_performed",
        "model_authored_mechanical_bytes",
    }
    assert result["result_kind"] == (
        "selected_successor_authority_context_preparation_result"
    )
    assert result["status"] == "prepared"
    assert result["bundle"] == bundle_binding
    assert result["authority_effects_applied"] is False
    assert result["model_authored_mechanical_bytes"] == 0
    assert result["idempotent_replay"] is False
    assert result["mutation_performed"] is True

    request_binding, request_value, compiler_context, rank = load_request_context(
        tmp_path, result["request_context"], bundle_binding
    )
    evaluation_binding, evaluation_value, loaded_session, loaded_envelope = (
        load_evaluation_context(tmp_path, result["evaluation_context"])
    )
    assert request_binding == result["request_context"]
    assert evaluation_binding == result["evaluation_context"]
    assert compiler_context["external_input_status"] == "not_required"
    assert rank == "S0"
    assert loaded_session == session
    assert loaded_envelope == {
        **{key: value for key, value in envelope.items() if key != "source_binding"},
        "source_ref": envelope["source_binding"]["ref"],
    }
    assert "caller.actual.session.capability" in loaded_session["capabilities"]
    assert "caller.actual.goal.capability" in loaded_envelope["capabilities"]

    request_path = tmp_path / request_binding["ref"]
    evaluation_path = tmp_path / evaluation_binding["ref"]
    assert request_path.read_bytes() == _canonical(request_value)
    assert evaluation_path.read_bytes() == _canonical(evaluation_value)
    assert request_path.stem == request_value["context_content_sha256"]
    assert evaluation_path.stem == evaluation_binding["sha256"]
    assert hashlib.sha256(request_path.read_bytes()).hexdigest() == request_binding[
        "sha256"
    ]
    assert set(result["operation_manifests"]) == {
        row["action"] for row in bundle["execution_order"]
    }
    assert not (tmp_path / ".task/authorization/decisions").exists()
    assert not (tmp_path / ".task/authorization/reservations").exists()

    replay = _prepare_contexts(
        tmp_path, bundle_binding, request, session, envelope
    )
    assert replay["request_context"] == result["request_context"]
    assert replay["evaluation_context"] == result["evaluation_context"]
    assert replay["idempotent_replay"] is True
    assert replay["mutation_performed"] is False


def test_cli_accepts_only_full_explicit_semantic_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    arguments = [
        "--root",
        str(tmp_path),
        "prepare-authority-context",
        "--bundle-ref",
        bundle_binding["ref"],
        "--bundle-sha256",
        bundle_binding["sha256"],
        "--actor-rank",
        "S0",
        "--external-input-status",
        request["external_input_status"],
        "--goal-truth-status",
        request["goal_truth_status"],
        "--risk-acceptance-status",
        request["risk_acceptance_status"],
        "--design-selection-status",
        request["design_selection_status"],
        "--session-risk-ceiling",
        session["risk_ceiling"],
        "--session-evidence-id",
        session["evidence_id"],
        "--goal-envelope-id",
        envelope["envelope_id"],
        "--goal-risk-ceiling",
        envelope["risk_ceiling"],
        "--goal-source-ref",
        envelope["source_binding"]["ref"],
        "--goal-source-sha256",
        envelope["source_binding"]["sha256"],
        "--skills-root",
        str(SKILLS_ROOT),
    ]
    for flag, values in (
        ("--session-capability", session["capabilities"]),
        ("--session-mutation-class", session["mutation_classes"]),
        ("--goal-capability", envelope["capabilities"]),
        ("--goal-decision-class", envelope["decision_classes"]),
        ("--goal-subject-digest", envelope["subjects"]),
        ("--goal-operation", envelope["operations"]),
    ):
        for value in values:
            arguments.extend((flag, value))

    assert successor_cli(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "prepared"
    _request_binding, _request_value, _compiler_context, rank = load_request_context(
        tmp_path, result["request_context"], bundle_binding
    )
    _evaluation_binding, _value, loaded_session, loaded_envelope = (
        load_evaluation_context(tmp_path, result["evaluation_context"])
    )
    assert rank == "S0"
    assert loaded_session == session
    assert loaded_envelope["capabilities"] == envelope["capabilities"]
    assert loaded_envelope["subjects"] == envelope["subjects"]
    assert loaded_envelope["operations"] == envelope["operations"]


def test_context_loaders_reject_canonical_payloads_copied_outside_owner_cas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    result = _prepare_contexts(
        tmp_path, bundle_binding, request, session, envelope
    )
    copied_directory = tmp_path / ".task/authorization/copied-contexts"
    copied_directory.mkdir(parents=True)
    request_copy = copied_directory / "request.json"
    evaluation_copy = copied_directory / "evaluation.json"
    request_copy.write_bytes(
        (tmp_path / result["request_context"]["ref"]).read_bytes()
    )
    evaluation_copy.write_bytes(
        (tmp_path / result["evaluation_context"]["ref"]).read_bytes()
    )

    with pytest.raises(ValueError):
        load_request_context(
            tmp_path, _binding(tmp_path, request_copy), bundle_binding
        )
    with pytest.raises(ValueError):
        load_evaluation_context(tmp_path, _binding(tmp_path, evaluation_copy))


def test_context_loader_rejects_leaf_swap_at_descriptor_open(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    result = _prepare_contexts(
        tmp_path, bundle_binding, request, session, envelope
    )
    target = tmp_path / result["request_context"]["ref"]
    outside = tmp_path / "same-context-bytes.json"
    outside.write_bytes(target.read_bytes())
    import orchestrate_task_cycle.selection_decision_store as decision_store

    real_open = decision_store.os.open
    swapped = False

    def swap_then_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal swapped
        if Path(path) == target and not swapped:
            swapped = True
            target.unlink()
            target.symlink_to(outside)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(decision_store.os, "open", swap_then_open)
    with pytest.raises(ValueError, match="changed during acquisition"):
        load_request_context(
            tmp_path, result["request_context"], bundle_binding
        )

    assert swapped is True


def test_prepare_authority_consumes_the_producer_bindings_directly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    authority_inputs = prepare_authority_inputs(
        tmp_path, bundle, bundle_binding
    )
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    contexts = _prepare_contexts(
        tmp_path, bundle_binding, request, session, envelope
    )

    result = prepare_selected_successor_authority(
        tmp_path,
        bundle_binding=bundle_binding,
        request_context_binding=contexts["request_context"],
        evaluation_context_binding=contexts["evaluation_context"],
        grants=authority_inputs["grants"],
        at=AT,
        skills_root=SKILLS_ROOT,
    )

    assert result["status"] == "prepared"
    _packet_binding, packet = load_packet(tmp_path, result["authority_packet"])
    assert packet["request_context"] == contexts["request_context"]
    assert packet["evaluation_context"] == contexts["evaluation_context"]


def test_missing_or_bad_required_evidence_writes_no_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    request["external_input_status"] = "available"

    with pytest.raises(ValueError, match="required for the asserted status"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)
    _assert_no_context_store(tmp_path)

    request["external_input_evidence"] = {
        "ref": ".task/evidence/does-not-exist.json",
        "sha256": "0" * 64,
    }
    with pytest.raises(ValueError, match="does not exist"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)
    _assert_no_context_store(tmp_path)


def test_bundle_coverage_mismatch_writes_no_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    session["capabilities"] = ["caller.actual.session.capability"]

    with pytest.raises(ValueError, match="does not cover the selected-successor"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)

    _assert_no_context_store(tmp_path)


def test_oversized_second_payload_fails_before_either_store_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    extras = {f"caller.oversized.capability.{index:05d}" for index in range(3000)}
    session["capabilities"] = sorted(set(session["capabilities"]) | extras)
    envelope["capabilities"] = sorted(set(envelope["capabilities"]) | extras)

    with pytest.raises(ValueError, match="evaluation context exceeds 64 KiB"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)

    _assert_no_context_store(tmp_path)


def test_oversized_goal_source_fails_before_context_store_resolution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    source_path = tmp_path / envelope["source_binding"]["ref"]
    assert MAX_SEMANTIC_INPUT_BYTES == 1024 * 1024
    source_path.write_bytes(b"g" * (MAX_SEMANTIC_INPUT_BYTES + 1))
    envelope["source_binding"] = _binding(tmp_path, source_path)

    with pytest.raises(ValueError, match="exceed|size|MiB"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)

    _assert_no_context_store(tmp_path)


def test_oversized_optional_evidence_fails_before_context_store_resolution(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    evidence = tmp_path / ".task/evidence/oversized-external-input.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    assert MAX_SEMANTIC_INPUT_BYTES == 1024 * 1024
    evidence.write_bytes(b"e" * (MAX_SEMANTIC_INPUT_BYTES + 1))
    request["external_input_status"] = "available"
    request["external_input_evidence"] = _binding(tmp_path, evidence)

    with pytest.raises(ValueError, match="exceed|size|MiB"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)

    _assert_no_context_store(tmp_path)


def test_existing_context_cas_bytes_remain_bounded_on_load(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    result = _prepare_contexts(
        tmp_path, bundle_binding, request, session, envelope
    )
    oversized = b"{" + b" " * (64 * 1024 + 1) + b"}"
    request_path = tmp_path / result["request_context"]["ref"]
    evaluation_path = tmp_path / result["evaluation_context"]["ref"]
    request_path.unlink()
    evaluation_path.write_bytes(oversized)
    import orchestrate_task_cycle.selected_successor_authority_context_compiler as compiler

    def bounded_hash_was_reached(
        _path: Path, _expected_size: int, _label: str
    ) -> str:
        raise AssertionError("oversized existing CAS must be rejected before hashing")

    monkeypatch.setattr(
        compiler, "_bounded_file_sha256", bounded_hash_was_reached
    )
    with pytest.raises(ValueError, match="conflicts with immutable"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)
    assert not request_path.exists()
    assert evaluation_path.read_bytes() == oversized

    request_path.write_bytes(oversized)
    with pytest.raises(ValueError, match="size limit"):
        load_request_context(
            tmp_path, _binding(tmp_path, request_path), bundle_binding
        )
    with pytest.raises(ValueError, match="size limit"):
        load_evaluation_context(tmp_path, _binding(tmp_path, evaluation_path))


def test_symlinked_context_store_fails_without_writing_peer_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    backing = tmp_path / "context-store-backing"
    backing.mkdir()
    request_store = _store(tmp_path, REQUEST_STORE).parent
    request_store.symlink_to(backing, target_is_directory=True)

    with pytest.raises(ValueError, match="cannot be a symlink"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)

    assert list(backing.iterdir()) == []
    assert not _store(tmp_path, EVALUATION_STORE).exists()


def test_conflicting_second_artifact_fails_before_recreating_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bundle_binding, bundle = _prepared_bundle(tmp_path, capsys)
    request, session, envelope = _semantic_inputs(tmp_path, bundle)
    result = _prepare_contexts(
        tmp_path, bundle_binding, request, session, envelope
    )
    request_path = tmp_path / result["request_context"]["ref"]
    evaluation_path = tmp_path / result["evaluation_context"]["ref"]
    request_path.unlink()
    evaluation_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="conflicts with immutable"):
        _prepare_contexts(tmp_path, bundle_binding, request, session, envelope)

    assert not request_path.exists()
    assert evaluation_path.read_text(encoding="utf-8") == "{}\n"


def test_context_compiler_stays_within_leaf_module_bounds() -> None:
    path = (
        SKILLS_ROOT
        / "orchestrate-task-cycle/scripts/orchestrate_task_cycle"
        / "selected_successor_authority_context_compiler.py"
    )
    source = path.read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 500
    tree = ast.parse(source, filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.end_lineno is not None
            assert node.end_lineno - node.lineno + 1 <= 140, node.name
