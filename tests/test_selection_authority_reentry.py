from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from manage_agent_authority.artifact_store import (
    snapshot_file,
    update_current_policy,
)
from manage_agent_authority.canonical import object_sha256, sha256_file
from manage_agent_authority.decision_integrity import (
    effective_authority_fingerprint,
)
from manage_agent_authority.decision_publication import evaluate_and_publish
from manage_agent_authority.operation_batch import (
    load_operation_batch,
    publish_operation_batch,
    publish_operation_set,
)
from manage_agent_authority.root_grant import (
    compile_root_decision_seed,
    materialize_exact_echo_root_grant,
    prepare_root_approval_plan,
)
from manage_agent_authority.semantic_context import (
    publish_shared_semantic_context,
)
from manage_task_state_index import index as task_state
from manage_task_state_index.state.selected_successor import _decision_task_id
from orchestrate_task_cycle import selection_authority_reentry as reentry
from orchestrate_task_cycle import (
    selection_authority_reentry_artifacts as reentry_artifacts,
)
from orchestrate_task_cycle import selection_authority_reentry_cli as reentry_cli
from orchestrate_task_cycle.authority_packet import build_authority_packet
from orchestrate_task_cycle import selection_decision_receipt_v3 as receipt_v3
from orchestrate_task_cycle import selected_successor_provenance as provenance
from orchestrate_task_cycle import selection_publication_v2 as publication_v2
from orchestrate_task_cycle.selection_authority_reentry_contracts import (
    _request_semantic_sha256,
)
from orchestrate_task_cycle.selected_successor import (
    load_selected_successor_bundle,
    prepare_selected_successor_bundle,
)
from orchestrate_task_cycle.selected_successor_provenance import (
    validate_selected_source_for_prepared_successor,
)
from orchestrate_task_cycle.selection_publication_v2 import _selected_source
from orchestrate_task_cycle.selection_publication_producer_manifest import (
    registered_producer_inventory,
    valid_producer_inventory,
)
from orchestrate_task_cycle.result_contract.derive_advice_artifacts import (
    advice_lens_receipt_projection,
)
from orchestrate_task_cycle.result_contract.advice_runtime_artifacts import (
    canonical_json_bytes,
)
from selection_synthesis_support import persisted_selection_synthesis
from root_authorization_test_support import (
    install_test_trust_anchor,
    signed_root_authorization,
)


SKILLS_ROOT = Path(__file__).resolve().parents[1]
ROOT_PLAN_AT = "2026-07-24T02:00:00+09:00"
ROOT_DECIDED_AT = "2026-07-24T02:05:00+09:00"
ROOT_REENTRY_AT = "2026-07-24T03:00:00+09:00"
ROOT_EXPIRES_AT = "2026-07-24T04:00:00+09:00"


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return path


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


@pytest.fixture
def real_root_authority_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Build a signed, materialized schema-v3 grant and its real allowed decision."""

    install_test_trust_anchor(monkeypatch, tmp_path)
    subject_path = _write_json(
        tmp_path / "plans/task-transition.json",
        {"plan": "authority-reentry"},
    )
    risk_path = _write_json(
        tmp_path / "evidence/risk.json",
        {"accepted": True},
    )
    goal_path = tmp_path / ".agent_goal/goal_architecture.md"
    goal_path.parent.mkdir(parents=True, exist_ok=True)
    goal_path.write_text("# Goal\n", encoding="utf-8")
    initialization_path = _write_json(
        tmp_path / ".task/cycle/cycle-source/initialization.json",
        {
            "format_version": 1,
            "cycle_id": "cycle-source",
            "task_id": "task-old",
        },
    )
    initialization_binding = _binding(tmp_path, initialization_path)
    subject_digest = hashlib.sha256(subject_path.read_bytes()).hexdigest()
    semantic_input = {
        "actor_rank": "S0",
        "request_context": {
            "external_input_status": "not_required",
            "goal_truth_status": "aligned",
            "risk_acceptance_status": "resolved",
            "design_selection_status": "resolved",
            "risk_acceptance_evidence_ref": risk_path.relative_to(tmp_path).as_posix(),
            "design_selection_evidence_ref": subject_path.relative_to(
                tmp_path
            ).as_posix(),
        },
        "session_ceiling": {
            "capabilities": ["task.scope.mutate"],
            "risk_ceiling": "R3",
            "mutation_classes": ["local_mutation"],
            "evidence_id": "session-reentry",
        },
        "goal_autonomy_envelope": {
            "envelope_id": "goal-envelope-reentry",
            "capabilities": ["task.scope.mutate"],
            "risk_ceiling": "R3",
            "decision_classes": ["D2"],
            "subjects": [subject_digest],
            "operations": ["task-doctor:2.2.0:mutate_task_scope:1"],
            "source_ref": goal_path.relative_to(tmp_path).as_posix(),
        },
    }
    semantic_result = publish_shared_semantic_context(
        tmp_path,
        initialization_binding,
        semantic_input,
    )
    operation_set = publish_operation_set(
        tmp_path,
        [
            {
                "skill_id": "task-doctor",
                "operation_id": "mutate_task_scope",
                "subject": {
                    "ref": subject_path.relative_to(tmp_path).as_posix(),
                    "revision": "candidate-authority-reentry",
                },
                "scope": {"task_id": "task-old", "pack_id": None},
            }
        ],
    )
    batch_result = publish_operation_batch(
        tmp_path,
        semantic_result["semantic_context"],
        operation_set["operation_set"],
        compiled_at=ROOT_PLAN_AT,
        skills_root=SKILLS_ROOT,
    )
    policy_path = tmp_path / ".agent_goal/agent_authority.md"
    policy_path.write_text("# Authority\n", encoding="utf-8")
    policy_binding = snapshot_file(
        tmp_path,
        policy_path.relative_to(tmp_path).as_posix(),
        "policy",
    )
    update_current_policy(tmp_path, policy_binding, expected_version=0)
    _batch_binding, _batch, compilations = load_operation_batch(
        tmp_path,
        batch_result["operation_batch"],
        skills_root=SKILLS_ROOT,
    )
    compilation = compilations[0]
    historical = evaluate_and_publish(
        tmp_path,
        compilation["request"],
        compilation["evaluation_context"],
        evaluated_at=ROOT_PLAN_AT,
        skills_root=SKILLS_ROOT,
    )
    historical_path = tmp_path / historical["decision_ref"]
    assert historical["decision"] == "approval_required"
    historical_packet = build_authority_packet(
        tmp_path,
        {
            "ref": historical["decision_ref"],
            "sha256": sha256_file(historical_path),
        },
    )
    prepared = prepare_root_approval_plan(
        tmp_path,
        batch_result["operation_batch"],
        policy_binding,
        {
            "source_kind": "explicit_user_instruction",
            "holder_rank": "S0",
            "expires_at": ROOT_EXPIRES_AT,
            "session_id": "session-reentry",
        },
        prepared_at=ROOT_PLAN_AT,
        skills_root=SKILLS_ROOT,
    )
    plan_binding = prepared["root_approval_plan"]
    decision_seed = compile_root_decision_seed(
        tmp_path,
        plan_binding,
        authorization_evidence=signed_root_authorization(
            tmp_path,
            plan_binding,
            decided_at=ROOT_DECIDED_AT,
            evidence_id="authority-reentry-root-decision",
            skills_root=SKILLS_ROOT,
        ),
        skills_root=SKILLS_ROOT,
    )["decision_seed"]
    materialized = materialize_exact_echo_root_grant(
        tmp_path,
        plan_binding,
        decision_seed,
        skills_root=SKILLS_ROOT,
    )
    decision = evaluate_and_publish(
        tmp_path,
        compilation["request"],
        compilation["evaluation_context"],
        evaluated_at=ROOT_DECIDED_AT,
        skills_root=SKILLS_ROOT,
    )
    decision_path = tmp_path / decision["decision_ref"]
    grant_id = decision["selected_grants"][0]["grant_id"]
    grant_path = tmp_path / ".task/authorization/grants" / f"{grant_id}.json"
    state_path = tmp_path / ".task/authorization/state/grants" / f"{grant_id}.json"
    return {
        "root": tmp_path,
        "decision": {
            "ref": decision["decision_ref"],
            "sha256": sha256_file(decision_path),
        },
        "request": compilation["request"],
        "historical_packet": historical_packet,
        "required_operation": reentry._operation(compilation["request"]),
        "subject": compilation["request"]["subject"],
        "materialization": materialized["root_grant_materialization"],
        "grant_id": grant_id,
        "grant_path": grant_path,
        "state_path": state_path,
        "initialization_binding": initialization_binding,
        "operation_set": operation_set["operation_set"],
        "policy_binding": policy_binding,
        "semantic_input": semantic_input,
    }


def _validate_real_root_authority_decision(
    fixture: dict[str, Any],
    *,
    decision: dict[str, str] | None = None,
    at: str = ROOT_REENTRY_AT,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, str]],
    dict[str, str],
    str,
]:
    return reentry._validated_authority_decisions(
        fixture["root"],
        [decision or fixture["decision"]],
        skills_root=SKILLS_ROOT,
        subject=fixture["subject"],
        source_cycle_id="cycle-source",
        source_task_id="task-old",
        required_operation=fixture["required_operation"],
        required_request_semantic_sha256=_request_semantic_sha256(fixture["request"]),
        at=at,
    )


def test_authority_reentry_accepts_exact_active_signed_root_lineage(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision

    entries, operations, source_approval, materialization_ref = (
        _validate_real_root_authority_decision(fixture)
    )

    assert len(entries) == 1
    assert operations == [fixture["required_operation"]]
    assert source_approval["ref"].startswith(".task/authorization/source_snapshots/")
    assert materialization_ref == fixture["materialization"]["ref"]


def test_authority_reentry_reopens_exact_frozen_historical_request(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision

    _subject, _operation, _approval, _scope, frozen = reentry._old_authority_scope(
        fixture["root"],
        {"authority_packet": fixture["historical_packet"]},
    )

    packet_binding = fixture["historical_packet"]["decision_binding"]
    assert frozen == {
        "decision": {
            "ref": packet_binding["artifact_ref"],
            "sha256": packet_binding["artifact_sha256"],
        },
        "request_sha256": packet_binding["request_sha256"],
        "request_semantic_sha256": _request_semantic_sha256(fixture["request"]),
    }


def test_authority_reentry_rejects_frozen_packet_request_binding_drift(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    packet = deepcopy(fixture["historical_packet"])
    packet["decision_binding"]["request_sha256"] = "f" * 64

    with pytest.raises(
        ValueError,
        match="source authority packet is invalid|exact request binding differs",
    ):
        reentry._old_authority_scope(fixture["root"], {"authority_packet": packet})


def test_authority_reentry_semantic_projection_excludes_only_allocation_ids(
    real_root_authority_decision: dict[str, Any],
) -> None:
    request = real_root_authority_decision["request"]
    reallocated = deepcopy(request)
    reallocated.update(
        {
            "request_id": "authr-reallocated",
            "attempt_id": "attempt-reallocated",
            "idempotency_key": "request-reallocated",
        }
    )

    assert _request_semantic_sha256(reallocated) == _request_semantic_sha256(request)

    reallocated["use_budget_requested"] = 2
    assert _request_semantic_sha256(reallocated) != _request_semantic_sha256(request)


def test_authority_reentry_rejects_fully_signed_semantic_request_drift(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    root = fixture["root"]
    semantic_input = deepcopy(fixture["semantic_input"])
    drift_evidence = _write_json(
        root / "evidence/risk-semantic-drift.json",
        {"accepted": True, "scope": "different-signed-evidence"},
    )
    semantic_input["request_context"]["risk_acceptance_evidence_ref"] = (
        drift_evidence.relative_to(root).as_posix()
    )
    semantic = publish_shared_semantic_context(
        root,
        fixture["initialization_binding"],
        semantic_input,
    )
    batch = publish_operation_batch(
        root,
        semantic["semantic_context"],
        fixture["operation_set"],
        compiled_at=ROOT_PLAN_AT,
        skills_root=SKILLS_ROOT,
    )
    prepared = prepare_root_approval_plan(
        root,
        batch["operation_batch"],
        fixture["policy_binding"],
        {
            "source_kind": "explicit_user_instruction",
            "holder_rank": "S0",
            "expires_at": ROOT_EXPIRES_AT,
            "session_id": "session-reentry",
        },
        prepared_at=ROOT_PLAN_AT,
        skills_root=SKILLS_ROOT,
    )
    plan = prepared["root_approval_plan"]
    seed = compile_root_decision_seed(
        root,
        plan,
        authorization_evidence=signed_root_authorization(
            root,
            plan,
            decided_at=ROOT_DECIDED_AT,
            evidence_id="semantic-drift-root-decision",
            skills_root=SKILLS_ROOT,
        ),
        skills_root=SKILLS_ROOT,
    )["decision_seed"]
    materialize_exact_echo_root_grant(
        root,
        plan,
        seed,
        skills_root=SKILLS_ROOT,
    )
    _binding_value, _batch_value, compilations = load_operation_batch(
        root,
        batch["operation_batch"],
        skills_root=SKILLS_ROOT,
    )
    compilation = compilations[0]
    decision = evaluate_and_publish(
        root,
        compilation["request"],
        compilation["evaluation_context"],
        evaluated_at=ROOT_DECIDED_AT,
        skills_root=SKILLS_ROOT,
    )
    assert decision["decision"] == "allowed", decision["reason_codes"]
    decision_path = root / decision["decision_ref"]

    with pytest.raises(ValueError, match="semantically differs"):
        _validate_real_root_authority_decision(
            fixture,
            decision=_binding(root, decision_path),
        )


def _clear_publication_status(transaction_id: str) -> dict[str, Any]:
    return {
        "status": "clear",
        "current_head": {
            "status": "current",
            "head_count": 1,
            "head_transaction_id": transaction_id,
        },
    }


def _publication_state(
    transaction_id: str,
    binding: dict[str, str],
) -> dict[str, Any]:
    return {
        "head": {
            "transaction_id": transaction_id,
            "receipt": binding,
        }
    }


def test_authority_reentry_publication_head_is_exact_bounded_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction_id = "selection-" + "1" * 64
    ref = f".task/selection_publication/receipts/{transaction_id}.json"
    path = tmp_path / ref
    payload = b'{"kind":"selection_publication_receipt"}\n'
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    monkeypatch.setattr(
        reentry_artifacts,
        "publication_status",
        lambda _root: _clear_publication_status(transaction_id),
    )
    binding = {"ref": ref, "sha256": hashlib.sha256(payload).hexdigest()}
    monkeypatch.setattr(
        reentry_artifacts,
        "load_state",
        lambda _root: _publication_state(transaction_id, binding),
    )

    assert reentry_artifacts._current_publication_head(tmp_path) == binding


def test_authority_reentry_publication_head_rejects_symlink_and_oversize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction_id = "selection-" + "2" * 64
    ref = f".task/selection_publication/receipts/{transaction_id}.json"
    path = tmp_path / ref
    path.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    path.symlink_to(outside)
    monkeypatch.setattr(
        reentry_artifacts,
        "publication_status",
        lambda _root: _clear_publication_status(transaction_id),
    )
    binding = {
        "ref": ref,
        "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        reentry_artifacts,
        "load_state",
        lambda _root: _publication_state(transaction_id, binding),
    )

    with pytest.raises(ValueError, match="non-symlink"):
        reentry_artifacts._current_publication_head(tmp_path)

    path.unlink()
    oversized = b"x" * (reentry_artifacts.MAX_REENTRY_ARTIFACT_BYTES + 1)
    path.write_bytes(oversized)
    binding["sha256"] = hashlib.sha256(oversized).hexdigest()
    with pytest.raises(ValueError, match="byte bound"):
        reentry_artifacts._current_publication_head(tmp_path)


def test_authority_reentry_publication_head_rejects_state_binding_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transaction_id = "selection-" + "3" * 64
    ref = f".task/selection_publication/receipts/{transaction_id}.json"
    path = tmp_path / ref
    path.parent.mkdir(parents=True)
    path.write_bytes(b"receipt\n")
    monkeypatch.setattr(
        reentry_artifacts,
        "publication_status",
        lambda _root: _clear_publication_status(transaction_id),
    )
    monkeypatch.setattr(
        reentry_artifacts,
        "load_state",
        lambda _root: _publication_state(
            transaction_id,
            {"ref": ref, "sha256": "0" * 64},
        ),
    )

    with pytest.raises(ValueError, match="differs from its state binding"):
        reentry_artifacts._current_publication_head(tmp_path)


def test_authority_reentry_rejects_missing_root_materialization_receipt(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    (fixture["root"] / fixture["materialization"]["ref"]).unlink()

    with pytest.raises(ValueError, match="materialization lineage is invalid"):
        _validate_real_root_authority_decision(fixture)


def test_authority_reentry_rejects_tampered_root_materialization_receipt(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    receipt_path = fixture["root"] / fixture["materialization"]["ref"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["receipt_id"] = "authrgm-tampered"
    _write_json(receipt_path, receipt)

    with pytest.raises(ValueError, match="materialization lineage is invalid"):
        _validate_real_root_authority_decision(fixture)


def test_authority_reentry_rejects_draft_root_materialized_grant(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    state = json.loads(fixture["state_path"].read_text(encoding="utf-8"))
    state["status"] = "draft"
    _write_json(fixture["state_path"], state)

    with pytest.raises(ValueError, match="active root-materialized grant"):
        _validate_real_root_authority_decision(fixture)


def test_authority_reentry_rejects_grant_bound_to_wrong_root_receipt(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    root = fixture["root"]
    receipt_path = root / fixture["materialization"]["ref"]
    wrong_receipt_path = (
        root / ".task/authorization/root_grant_materializations/wrong/receipt.json"
    )
    wrong_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    wrong_receipt_path.write_bytes(receipt_path.read_bytes())

    grant = json.loads(fixture["grant_path"].read_text(encoding="utf-8"))
    grant["root_materialization_ref"] = wrong_receipt_path.relative_to(root).as_posix()
    _write_json(fixture["grant_path"], grant)
    grant_sha256 = sha256_file(fixture["grant_path"])
    state = json.loads(fixture["state_path"].read_text(encoding="utf-8"))
    state["grant_sha256"] = grant_sha256
    _write_json(fixture["state_path"], state)

    original_decision_path = root / fixture["decision"]["ref"]
    decision = json.loads(original_decision_path.read_text(encoding="utf-8"))
    for field in ("selected_grants", "lineage_grants"):
        for record in decision[field]:
            if record["grant_id"] == fixture["grant_id"]:
                record["grant_sha256"] = grant_sha256
    decision["effective_authority_fingerprint"] = effective_authority_fingerprint(
        decision["request"],
        decision["evaluation_context"],
        decision["operation_manifest"],
        decision["selected_grants"],
        decision["lineage_grants"],
    )
    core = {key: value for key, value in decision.items() if key != "decision_id"}
    decision["decision_id"] = f"authd-{object_sha256(core)[:24]}"
    decision_path = (
        root / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    )
    _write_json(decision_path, decision)

    with pytest.raises(ValueError, match="materialization lineage is invalid"):
        _validate_real_root_authority_decision(
            fixture,
            decision=_binding(root, decision_path),
        )


def test_authority_reentry_rejects_forged_cross_request_allowed_decision(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    root = fixture["root"]
    original_decision_path = root / fixture["decision"]["ref"]
    decision = json.loads(original_decision_path.read_text(encoding="utf-8"))
    decision["request"]["attempt_id"] = "attempt-cross-request"
    decision["request_sha256"] = object_sha256(decision["request"])
    core = {key: value for key, value in decision.items() if key != "decision_id"}
    decision["decision_id"] = f"authd-{object_sha256(core)[:24]}"
    decision_path = (
        root / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    )
    _write_json(decision_path, decision)

    with pytest.raises(ValueError, match="exact request"):
        _validate_real_root_authority_decision(
            fixture,
            decision=_binding(root, decision_path),
        )


def test_authority_reentry_rejects_allowed_decision_with_drifted_context(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    root = fixture["root"]
    original_path = root / fixture["decision"]["ref"]
    decision = json.loads(original_path.read_text(encoding="utf-8"))
    context = decision["evaluation_context"]
    context["session_ceiling"]["capabilities"] = ["task.scope.read"]
    context["session_ceiling"]["risk_ceiling"] = "R0"
    context["session_ceiling"]["mutation_classes"] = ["observe"]
    decision["evaluation_context_sha256"] = object_sha256(context)
    decision["effective_authority_fingerprint"] = effective_authority_fingerprint(
        decision["request"],
        decision["evaluation_context"],
        decision["operation_manifest"],
        decision["selected_grants"],
        decision["lineage_grants"],
    )
    core = {key: value for key, value in decision.items() if key != "decision_id"}
    decision["decision_id"] = f"authd-{object_sha256(core)[:24]}"
    decision_path = (
        root / ".task/authorization/decisions" / f"{decision['decision_id']}.json"
    )
    _write_json(decision_path, decision)

    with pytest.raises(ValueError, match="no longer currently allowed"):
        _validate_real_root_authority_decision(
            fixture,
            decision=_binding(root, decision_path),
            at="2026-07-24T03:00:00+09:00",
        )


def test_authority_reentry_rejects_grant_expired_at_bound_reentry_time(
    real_root_authority_decision: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="no longer currently allowed|expired"):
        _validate_real_root_authority_decision(
            real_root_authority_decision,
            at=ROOT_EXPIRES_AT,
        )


def test_authority_reentry_rejects_time_before_bound_decision(
    real_root_authority_decision: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        _validate_real_root_authority_decision(
            real_root_authority_decision,
            at=ROOT_PLAN_AT,
        )


def test_authority_reentry_rejects_current_grant_state_version_drift(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    state = json.loads(fixture["state_path"].read_text(encoding="utf-8"))
    state["version"] += 1
    _write_json(fixture["state_path"], state)

    with pytest.raises(ValueError, match="selected_grants_changed"):
        _validate_real_root_authority_decision(fixture)


def test_authority_reentry_rejects_insufficient_unreserved_budget(
    real_root_authority_decision: dict[str, Any],
) -> None:
    fixture = real_root_authority_decision
    state = json.loads(fixture["state_path"].read_text(encoding="utf-8"))
    state["reserved_uses"] = state["remaining_uses"]
    _write_json(fixture["state_path"], state)

    with pytest.raises(ValueError, match="no longer currently allowed"):
        _validate_real_root_authority_decision(fixture)


def _source(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    source, _, _ = persisted_selection_synthesis(
        root, outcome="user_escalation", suffix="REENTRY"
    )
    analysis = source["improvement_analysis_manifest"]
    candidate = deepcopy(analysis["lens_results"][0]["output"]["candidates"][0])
    candidate["actionability"] = "blocked_authority"
    candidate["exact_subject_work_id"] = "work-A"
    for lens in analysis["lens_results"]:
        lens["output"]["candidates"] = [deepcopy(candidate)]
        lens["output"]["rejection_inventory"] = []
        lens["output_sha256"] = hashlib.sha256(
            json.dumps(
                lens["output"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        (root / lens["output_ref"]).write_bytes(
            canonical_json_bytes(advice_lens_receipt_projection(lens))
        )
    source["authority_packet"] = {"fixture": True}
    path = _write_json(root / ".task/cycle/cycle-A/derive-user-escalation.json", source)
    return source, _binding(root, path)


def _patch_closed_owners(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    source_binding: dict[str, str],
) -> dict[str, Any]:
    subject_path = _write_json(
        root / ".task/cycle/cycle-A/authority-request-subject.json",
        {
            "schema_version": 1,
            "artifact_kind": "fixture_authority_request",
            "candidate_id": "candidate-A",
            "exact_subject_work_id": "work-A",
            "task_kind": "producer_repair",
            "expected_blocker_transition": "blocked-to-measured",
            "cycle_id": "cycle-A",
            "task_id": "task-old",
        },
    )
    subject = {
        "kind": "task",
        "ref": subject_path.relative_to(root).as_posix(),
        "digest": hashlib.sha256(subject_path.read_bytes()).hexdigest(),
        "revision": "candidate-A",
    }
    required_operation = {
        "skill_id": "orchestrate-task-cycle",
        "skill_version": "2.0.0",
        "operation_id": "dispatch_local_worker",
        "operation_version": "1",
    }
    extra_operation = {
        "skill_id": "orchestrate-task-cycle",
        "skill_version": "2.0.0",
        "operation_id": "run_long",
        "operation_version": "1",
    }
    approval = {
        "scope": {"cycle_id": "cycle-A", "task_id": "task-old"},
        "excluded_effects": [
            "broaden_subject_or_operation",
            "change_goal_truth",
        ],
    }
    scope = {"cycle_id": "cycle-A", "task_id": "task-old"}
    source_authority_request = {
        "decision": {
            "ref": ".task/authorization/decisions/authd-fixture-source.json",
            "sha256": "9" * 64,
        },
        "request_sha256": "8" * 64,
        "request_semantic_sha256": "7" * 64,
    }

    def old_scope(
        _root: Path, _source: dict[str, Any]
    ) -> tuple[
        dict[str, str],
        dict[str, str],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]:
        return (
            subject,
            required_operation,
            approval,
            scope,
            source_authority_request,
        )

    def decisions(
        _root: Path,
        values: object,
        **_kwargs: object,
    ) -> tuple[
        list[dict[str, Any]],
        list[dict[str, str]],
        dict[str, str],
        str,
    ]:
        bindings = list(values)  # type: ignore[arg-type]
        operations = [required_operation, extra_operation]
        entries = [
            {
                "decision": bindings[index],
                "decision_id": f"authd-fixture-{index}",
                "request_sha256": str(index + 1) * 64,
                "request_semantic_sha256": (
                    str(_kwargs["required_request_semantic_sha256"])
                    if index == 0
                    else "6" * 64
                ),
                "operation": operation,
            }
            for index, operation in enumerate(operations)
        ]
        return (
            entries,
            operations,
            {"ref": ".task/authorization/source.json", "sha256": "a" * 64},
            ".task/authorization/root_grant_materializations/root/receipt.json",
        )

    def trigger(_root: Path, **kwargs: Any) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact_kind": "normal_cycle_selection_trigger",
            "trigger_kind": "normal_cycle",
            "trigger_id": "normal-selection-trigger-fixture",
            "cycle_id": kwargs["cycle_id"],
            "derive_result": kwargs["derive_result"],
            "input_evidence_manifest_sha256": kwargs["input_evidence_manifest_sha256"],
        }

    observed_active_prepares: list[Any] = []

    def validate_trigger(_root: Path, value: Any, **kwargs: Any) -> dict[str, Any]:
        observed_active_prepares.append(kwargs.get("expected_active_prepare"))
        if (
            not isinstance(value, dict)
            or value.get("artifact_kind") != "normal_cycle_selection_trigger"
        ):
            raise ValueError("fixture trigger is invalid")
        return value

    monkeypatch.setattr(reentry, "_old_authority_scope", old_scope)
    monkeypatch.setattr(reentry, "_validated_authority_decisions", decisions)
    monkeypatch.setattr(reentry, "render_normal_cycle_trigger", trigger)
    monkeypatch.setattr(reentry, "validate_normal_cycle_trigger", validate_trigger)
    monkeypatch.setattr(receipt_v3, "validate_normal_cycle_trigger", validate_trigger)
    return {
        "subject": subject,
        "required_operation": required_operation,
        "extra_operation": extra_operation,
        "approval": approval,
        "scope": scope,
        "source_authority_request": source_authority_request,
        "observed_active_prepares": observed_active_prepares,
    }


def _compile(
    root: Path,
    source_binding: dict[str, str],
) -> dict[str, Any]:
    placeholder = {"ref": "fixture.json", "sha256": "f" * 64}
    decisions = [
        {"ref": "decision-a.json", "sha256": "1" * 64},
        {"ref": "decision-b.json", "sha256": "2" * 64},
    ]
    return reentry.compile_authority_reentry(
        root,
        cycle_id="cycle-A",
        source_result=source_binding,
        cycle_finalization=placeholder,
        schema_pre_derive=placeholder,
        current_task={"ref": "task.md", "sha256": "e" * 64},
        task_index={"ref": ".task/index.jsonl", "sha256": "d" * 64},
        publication_head=placeholder,
        authority_decisions=decisions,
        skills_root=Path(__file__).resolve().parents[1],
        at=ROOT_REENTRY_AT,
    )


def _published_v3_selected_source(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    (root / "task.md").write_text("# Task\n\n- Task ID: `task-old`\n", encoding="utf-8")
    task_state.upsert_item(
        root,
        "task",
        "task.md",
        "active",
        item_id="task-old",
        replace_existing=False,
    )
    _source_value, source_binding = _source(root)
    _patch_closed_owners(monkeypatch, root, source_binding)
    return reentry.publish_authority_reentry(root, _compile(root, source_binding))


def test_authority_reentry_publishes_exact_replayable_v3_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "task.md").write_text(
        "# Task\n\n- Task ID: `task-old`\n", encoding="utf-8"
    )
    source, source_binding = _source(tmp_path)
    owners = _patch_closed_owners(monkeypatch, tmp_path, source_binding)
    historical = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task/cycle/cycle-A").rglob("*")
        if path.is_file()
    }

    plan = _compile(tmp_path, source_binding)

    assert not (tmp_path / ".task/selection_reentry").exists()
    result = reentry.publish_authority_reentry(tmp_path, plan)
    reopened_path = tmp_path / result["receipt"]["ref"]
    reopened = json.loads(reopened_path.read_text(encoding="utf-8"))
    assert (
        receipt_v3.validate_selection_decision_receipt_v3(tmp_path, reopened)
        == reopened
    )
    copied_dependency = deepcopy(reopened)
    copied_dependency["selection_decision"] = {
        **copied_dependency["selection_decision"],
        "ref": ".task/copied-selection-decision.json",
    }
    with pytest.raises(ValueError, match="exact authority-reentry CAS path"):
        receipt_v3.validate_selection_decision_receipt_v3(tmp_path, copied_dependency)
    expected_active_prepare = {
        "ref": ".task/selection_publication/transactions/prepare.json",
        "sha256": "9" * 64,
    }
    owners["observed_active_prepares"].clear()
    assert (
        receipt_v3.validate_selection_decision_receipt_v3(
            tmp_path,
            reopened,
            expected_active_prepare=expected_active_prepare,
        )
        == reopened
    )
    assert owners["observed_active_prepares"]
    assert all(
        observed == expected_active_prepare
        for observed in owners["observed_active_prepares"]
    )
    assert result["selected_task_id"] == "task-A"
    assert result["published_count"] == 6
    assert result["effect_boundary"] == "preparation_only"
    task_source = (tmp_path / result["task_source"]["ref"]).read_text(encoding="utf-8")
    assert task_source.count("- Task ID:") == 1
    assert "does not itself grant authority" in task_source
    assert {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in (tmp_path / ".task/cycle/cycle-A").rglob("*")
        if path.is_file()
    } == historical

    replay = reentry.publish_authority_reentry(tmp_path, plan)

    assert replay["mutation_performed"] is False
    assert replay["published_count"] == 0
    assert replay["reused_count"] == 6


def test_authority_reentry_is_a_closed_registered_producer() -> None:
    inventory = registered_producer_inventory()

    assert valid_producer_inventory(inventory)
    reentry_producer = next(
        row
        for row in inventory["producers"]
        if row["producer_id"] == "selection-authority-reentry"
    )
    assert reentry_producer["source_file"] == "selection_authority_reentry.py"
    assert reentry_producer["entrypoints"] == [
        "compile_and_publish_authority_reentry",
        "publish_authority_reentry",
    ]


def test_authority_reentry_rejects_nonidentical_lens_candidate_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "task.md").write_text(
        "# Task\n\n- Task ID: `task-old`\n", encoding="utf-8"
    )
    source, source_binding = _source(tmp_path)
    _patch_closed_owners(monkeypatch, tmp_path, source_binding)
    analysis = source["improvement_analysis_manifest"]
    analysis["lens_results"][1]["output"]["candidates"][0][
        "expected_blocker_transition"
    ] = "different-transition"
    path = tmp_path / source_binding["ref"]
    _write_json(path, source)
    drifted_binding = _binding(tmp_path, path)

    with pytest.raises(ValueError, match="canonical-identical|analysis contract"):
        _compile(tmp_path, drifted_binding)

    assert not (tmp_path / ".task/selection_reentry").exists()


def test_authority_reentry_rejects_candidate_a_with_authority_subject_b(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "task.md").write_text(
        "# Task\n\n- Task ID: `task-old`\n", encoding="utf-8"
    )
    _source_value, source_binding = _source(tmp_path)
    owners = _patch_closed_owners(monkeypatch, tmp_path, source_binding)
    subject_path = tmp_path / owners["subject"]["ref"]
    subject_payload = json.loads(subject_path.read_text(encoding="utf-8"))
    subject_payload.update(
        {
            "candidate_id": "candidate-B",
            "exact_subject_work_id": "work-B",
            "task_kind": "different_repair",
            "expected_blocker_transition": "different-transition",
        }
    )
    _write_json(subject_path, subject_payload)
    owners["subject"]["digest"] = hashlib.sha256(subject_path.read_bytes()).hexdigest()
    owners["subject"]["revision"] = "candidate-B"

    with pytest.raises(ValueError, match="frozen candidate"):
        _compile(tmp_path, source_binding)

    assert not (tmp_path / ".task/selection_reentry").exists()


@pytest.mark.parametrize("scope_owner", ["scope", "approval"])
def test_authority_reentry_rejects_source_authority_scope_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scope_owner: str,
) -> None:
    (tmp_path / "task.md").write_text(
        "# Task\n\n- Task ID: `task-old`\n", encoding="utf-8"
    )
    _source_value, source_binding = _source(tmp_path)
    owners = _patch_closed_owners(monkeypatch, tmp_path, source_binding)
    target = owners["scope"] if scope_owner == "scope" else owners["approval"]["scope"]
    target["task_id"] = "task-other"

    with pytest.raises(ValueError, match="frozen derive predecessor"):
        _compile(tmp_path, source_binding)

    assert not (tmp_path / ".task/selection_reentry").exists()


def test_authority_reentry_cli_dry_run_is_body_free_and_write_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    placeholder = {"ref": "fixture.json", "sha256": "f" * 64}
    plan = {
        "selected_task_id": "task-successor",
        "trigger": placeholder,
        "synthesis": placeholder,
        "task_source": {"ref": "successor.md", "sha256": "e" * 64},
        "resolution": placeholder,
        "decision": placeholder,
        "receipt": placeholder,
        "artifacts": [{"payload": b"must-not-leak"}],
    }

    def compile_fixture(_root: Path, **_kwargs: Any) -> dict[str, Any]:
        return plan

    monkeypatch.setattr(reentry_cli, "compile_authority_reentry", compile_fixture)
    before = {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    binding_arguments = [
        "--source-result",
        "--cycle-finalization",
        "--schema-pre-derive",
        "--current-task",
        "--task-index",
    ]
    argv = [
        "--root",
        str(tmp_path),
        "publish",
        "--cycle-id",
        "cycle-A",
        "--at",
        ROOT_REENTRY_AT,
    ]
    for option in binding_arguments:
        argv.extend((f"{option}-ref", "fixture.json"))
        argv.extend((f"{option}-sha256", "f" * 64))
    argv.extend(
        (
            "--authority-decision-ref",
            "decision.json",
            "--authority-decision-sha256",
            "d" * 64,
            "--dry-run",
        )
    )

    assert reentry_cli.main(argv) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ready"
    assert output["selected_task_id"] == "task-successor"
    assert output["mutation_performed"] is False
    assert "artifacts" not in output
    assert "must-not-leak" not in json.dumps(output)
    assert {
        path.relative_to(tmp_path).as_posix(): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == before


def test_v3_selected_source_rejects_same_task_id_with_different_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = _published_v3_selected_source(tmp_path, monkeypatch)
    alternate = tmp_path / ".task/candidates/task-A-different.md"
    alternate.parent.mkdir(parents=True, exist_ok=True)
    alternate.write_text(
        "# Different task body\n\n- Task ID: `task-A`\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="exact receipt task source"):
        prepare_selected_successor_bundle(
            tmp_path,
            source_decision=published["receipt"],
            task_source=_binding(tmp_path, alternate),
            at="2026-07-24T03:00:00+09:00",
        )

    assert not (tmp_path / ".task/transition_plans").exists()


def test_v3_selected_source_rejects_same_digest_at_different_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = _published_v3_selected_source(tmp_path, monkeypatch)
    original = tmp_path / published["task_source"]["ref"]
    alternate = tmp_path / ".task/candidates/task-A-copy.md"
    alternate.parent.mkdir(parents=True, exist_ok=True)
    alternate.write_bytes(original.read_bytes())
    alternate_binding = _binding(tmp_path, alternate)
    assert alternate_binding["sha256"] == published["task_source"]["sha256"]

    with pytest.raises(ValueError, match="exact receipt task source"):
        prepare_selected_successor_bundle(
            tmp_path,
            source_decision=published["receipt"],
            task_source=alternate_binding,
            at="2026-07-24T03:00:00+09:00",
        )

    assert not (tmp_path / ".task/transition_plans").exists()


def test_v3_compile_intent_independently_requires_exact_task_source_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / ".task/selection_reentry/task_sources/source.md"
    alternate = tmp_path / ".task/candidates/source-copy.md"
    original.parent.mkdir(parents=True, exist_ok=True)
    alternate.parent.mkdir(parents=True, exist_ok=True)
    original.write_text("# Task A\n\n- Task ID: `task-A`\n", encoding="utf-8")
    alternate.write_bytes(original.read_bytes())
    original_binding = _binding(tmp_path, original)
    alternate_binding = _binding(tmp_path, alternate)
    source_binding = {"ref": "receipt.json", "sha256": "1" * 64}
    monkeypatch.setattr(
        publication_v2,
        "_selected_source",
        lambda *_args, **_kwargs: (
            source_binding,
            {
                "schema_version": 3,
                "receipt_id": "selection-decision-v3-fixture",
                "selected_task_id": "task-A",
                "task_source": original_binding,
            },
        ),
    )

    with pytest.raises(ValueError, match="exact receipt task source"):
        publication_v2.compile_intent(
            tmp_path,
            {
                "schema_version": 2,
                "kind": "selection_publication_intent",
                "source_decision": source_binding,
                "task_source": alternate_binding,
                "task_state_plan": {"ref": "plan.json", "sha256": "2" * 64},
            },
        )


def test_selected_source_rejects_unknown_receipt_schema(
    tmp_path: Path,
) -> None:
    receipt_path = _write_json(
        tmp_path / ".task/selection_reentry/receipts/unknown.json",
        {
            "schema_version": 99,
            "artifact_kind": "selection_decision_receipt",
        },
    )

    with pytest.raises(ValueError, match="schema_version is unsupported"):
        _selected_source(tmp_path, _binding(tmp_path, receipt_path))


def test_v3_selected_source_rejects_receipt_outside_exact_cas_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = _published_v3_selected_source(tmp_path, monkeypatch)
    source = tmp_path / published["receipt"]["ref"]
    alternate = tmp_path / ".task/candidates/receipt-copy.json"
    alternate.parent.mkdir(parents=True, exist_ok=True)
    alternate.write_bytes(source.read_bytes())
    alternate_binding = _binding(tmp_path, alternate)
    assert alternate_binding["sha256"] == published["receipt"]["sha256"]

    with pytest.raises(ValueError, match="exact CAS path"):
        _selected_source(tmp_path, alternate_binding)


def test_task_state_owner_rejects_resealed_open_v3_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = _published_v3_selected_source(tmp_path, monkeypatch)
    receipt = json.loads(
        (tmp_path / published["receipt"]["ref"]).read_text(encoding="utf-8")
    )
    body = {
        **{key: value for key, value in receipt.items() if key != "receipt_sha256"},
        "unexpected": True,
    }
    forged = {
        **body,
        "receipt_sha256": hashlib.sha256(
            (
                json.dumps(
                    body,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        ).hexdigest(),
    }
    payload = (
        json.dumps(
            forged,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")

    with pytest.raises(ValueError, match="not a closed selected decision"):
        _decision_task_id(payload)


def test_v3_selected_source_prepares_and_reopens_active_prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    published = _published_v3_selected_source(tmp_path, monkeypatch)
    prepared = prepare_selected_successor_bundle(
        tmp_path,
        source_decision=published["receipt"],
        task_source=published["task_source"],
        at="2026-07-24T03:00:00+09:00",
    )
    bundle = load_selected_successor_bundle(tmp_path, prepared["bundle"])

    binding, receipt = validate_selected_source_for_prepared_successor(
        tmp_path,
        bundle["source_decision"],
        bundle["task_source"],
        bundle["selection_prepare"],
    )

    assert binding == published["receipt"]
    assert receipt["schema_version"] == 3
    assert receipt["task_source"] == bundle["task_source"]
    prepare = json.loads(
        (tmp_path / bundle["selection_prepare"]["ref"]).read_text(encoding="utf-8")
    )
    assert prepare["targets"][0]["after_sha256"] == bundle["task_source"]["sha256"]

    replay = prepare_selected_successor_bundle(
        tmp_path,
        source_decision=published["receipt"],
        task_source=published["task_source"],
        at="2026-07-24T03:00:00+09:00",
    )
    assert replay["bundle"] == prepared["bundle"]
    assert replay["mutation_performed"] is False


def test_active_prepare_rejects_task_source_after_digest_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n\n- Task ID: `task-old`\n", encoding="utf-8")
    task_source = tmp_path / ".task/task_sources/task-A.md"
    task_source.parent.mkdir(parents=True, exist_ok=True)
    task_source.write_text("# Task A\n\n- Task ID: `task-A`\n", encoding="utf-8")
    task_binding = _binding(tmp_path, task_source)
    source_binding = {
        "ref": ".task/selection_reentry/receipts/sha256/" + "1" * 64 + ".json",
        "sha256": "1" * 64,
    }
    wrong_sha = "0" * 64
    prepare = {
        "schema_version": 3,
        "kind": "selection_publication_prepare",
        "selection_id": "task-A",
        "source_decision_id": "selection-decision-v3-fixture",
        "source_decision_sha256": source_binding["sha256"],
        "source_decision": source_binding,
        "publication_mode": "selected_successor_external_settlement",
        "owner_assertions": [],
        "task_state_plan": {"ref": ".task/plan.json", "sha256": "2" * 64},
        "intent_sha256": "3" * 64,
        "targets": [
            {
                "role": "task_alias",
                "target_ref": "task.md",
                "before_sha256": hashlib.sha256(task.read_bytes()).hexdigest(),
                "after_sha256": wrong_sha,
                "payload_ref": (
                    ".task/selection_publication/blobs/sha256/" + wrong_sha
                ),
                "payload_sha256": wrong_sha,
                "payload_size": len(task_source.read_bytes()),
            }
        ],
        "compiler_metrics": {
            "inline_payload_bytes": 0,
            "model_authored_mechanical_bytes": 0,
            "task_payload_bytes": len(task_source.read_bytes()),
        },
    }
    prepare_path = _write_json(
        tmp_path / ".task/selection_publication/forged-prepare.json",
        prepare,
    )
    prepare_binding = _binding(tmp_path, prepare_path)
    monkeypatch.setattr(
        provenance,
        "load_state",
        lambda _root: {
            "active_transaction": {
                "prepare": prepare_binding,
                "receipt": None,
            }
        },
    )
    monkeypatch.setattr(
        provenance,
        "_selected_source",
        lambda *_args, **_kwargs: (
            source_binding,
            {
                "schema_version": 3,
                "receipt_id": "selection-decision-v3-fixture",
                "selected_task_id": "task-A",
                "task_source": task_binding,
            },
        ),
    )

    with pytest.raises(ValueError, match="provenance differs"):
        validate_selected_source_for_prepared_successor(
            tmp_path,
            source_binding,
            task_binding,
            prepare_binding,
        )
