from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from manage_agent_authority.session_binding import build_session_binding
from manage_agent_authority.session_lease import build_session_lease
from orchestrate_task_cycle.continuation import local_run_dispatch
from orchestrate_task_cycle.continuation.lifecycle import start_session
from orchestrate_task_cycle.continuation.service import continue_session
from orchestrate_task_cycle.stage.executor_registry import executor_spec
from orchestrate_task_cycle.stage.v2_context import (
    selected_state_fingerprint,
    selector_fingerprints,
)


AT = "2026-07-29T00:00:00Z"
SHA = "a" * 64


def _lease(*, groups: list[str] | None = None) -> dict[str, Any]:
    binding = build_session_binding(
        workspace_identity="workspace-1",
        provider="codex",
        thread_binding="thread-value",
        activation_evidence_id="activation-1",
        trust_class="platform_host_receipt",
        approval_receipt="receipt-value",
    )
    return build_session_lease(
        session_binding=binding,
        goal_id="goal-1",
        task_family="family-1",
        activation_mode="governed",
        activation_risk_ceiling="R2",
        allowed_operation_groups=groups or ["local_long_run"],
        goal_digest="goal-digest",
        policy_digest="policy-digest",
        manifest_digest="manifest-digest",
        issued_at=AT,
        expires_at="2026-07-30T00:00:00Z",
    )


def _state(lease: dict[str, Any], *, raw_sha: str | None = None) -> dict[str, Any]:
    return start_session(
        session_lease=lease,
        session_lease_binding={
            "ref": lease["session_binding"]["session_ref"],
            "sha256": raw_sha or lease["state_sha256"],
        },
        cycle_id="cycle-1",
        task_id="task-1",
        created_at=AT,
    )


def _run_preparation() -> dict[str, Any]:
    return {
        "target": "run",
        "executor_kind": "owner",
        "executor_spec": {
            "executor_kind": "owner",
            "owner_id": "run-task-code-and-log",
            "allowed_routing_profiles": [],
            "side_effect_class": "external_or_long_running_effect",
        },
        "work_order_binding": {
            "artifact_type": "work_order",
            "ref": ".task/cycle/cycle-1/work-order.json",
            "sha256": SHA,
            "size_bytes": 100,
        },
        "result_contract": {"required_fields": ["execution_status"]},
    }


class _Adapter:
    def __init__(self, classification: str) -> None:
        self.classification = classification

    def advance(self, cycle_id: str, *, closure_only: bool) -> dict[str, Any]:
        assert cycle_id == "cycle-1"
        assert closure_only is False
        return {
            "status": "waiting",
            "stop_reason": "awaiting_owner_result",
            "preparation": _run_preparation(),
            "preparation_publication": {
                "preparation_ref": ".task/cycle/cycle-1/preparation.json",
                "preparation_sha256": SHA,
            },
        }

    def classify_effect(
        self,
        state: dict[str, Any],
        preparation: dict[str, Any],
        *,
        at: str,
    ) -> str:
        assert state["session_id"]
        assert preparation["target"] == "run"
        assert at == AT
        return self.classification

    def accept(
        self, action: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        raise AssertionError("not used")

    def recover(self, action: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("not used")

    def selected_successor(self, cycle_id: str) -> dict[str, Any] | None:
        return None


class _SequenceAdapter(_Adapter):
    def __init__(
        self,
        advances: list[dict[str, Any]],
        classifications: list[str] | None = None,
    ) -> None:
        super().__init__("unknown")
        self.advances = list(advances)
        self.classifications = list(classifications or [])
        self.advance_count = 0

    def advance(self, cycle_id: str, *, closure_only: bool) -> dict[str, Any]:
        assert cycle_id == "cycle-1"
        assert closure_only is False
        self.advance_count += 1
        return self.advances.pop(0)

    def classify_effect(
        self,
        state: dict[str, Any],
        preparation: dict[str, Any],
        *,
        at: str,
    ) -> str:
        assert state["session_id"]
        assert at == AT
        return self.classifications.pop(0)


def test_only_exact_local_long_run_classification_dispatches_agent() -> None:
    active, action = continue_session(
        _state(_lease()), _Adapter("local_long_run"), at=AT
    )
    assert active["status"] == "waiting"
    assert active["usage"]["agent_actions"] == 1
    assert action["actor"] == "agent"
    assert action["target"] == "run"
    assert action["effect_class"] == "local_long_run"
    forged = dict(action)
    forged["owner_skill"] = "other-owner"
    from orchestrate_task_cycle.continuation.actions import validate_action

    with pytest.raises(ValueError, match="registered run owner"):
        validate_action(forged)

    waiting, boundary = continue_session(
        _state(_lease()), _Adapter("external"), at=AT
    )
    assert waiting["usage"]["agent_actions"] == 0
    assert boundary["actor"] == "user"
    assert boundary["reason"] == "awaiting_effect_classification"


@pytest.mark.parametrize(
    ("reason", "actor"),
    [
        ("awaiting_exact_approval", "user"),
        ("awaiting_external_input", "external"),
    ],
)
def test_unchanged_boundary_recheck_preserves_state_and_action(
    reason: str, actor: str
) -> None:
    result = {
        "status": "block",
        "stop_reason": reason,
        "blocked_target": "authority",
    }
    adapter = _SequenceAdapter([result, dict(result)])
    waiting, action = continue_session(_state(_lease()), adapter, at=AT)
    state_sha = waiting["state_sha256"]

    unchanged, replay = continue_session(waiting, adapter, at=AT)

    assert action["actor"] == actor
    assert action["routing"]["boundary_evidence_sha256"]
    assert unchanged == waiting
    assert unchanged["state_sha256"] == state_sha
    assert replay == action
    assert adapter.advance_count == 2


def test_materialized_approval_rechecks_and_progresses_without_deadlock() -> None:
    approval_wait = {
        "status": "block",
        "stop_reason": "awaiting_exact_approval",
        "blocked_target": "authority",
    }
    owner_ready = {
        "status": "waiting",
        "stop_reason": "awaiting_owner_result",
        "preparation": {
            **_run_preparation(),
            "target": "acceptance",
            "executor_spec": {
                "executor_kind": "owner",
                "owner_id": "normalize-acceptance-and-demo",
                "allowed_routing_profiles": [],
                "side_effect_class": executor_spec(
                    "acceptance"
                ).side_effect_class,
            },
        },
        "preparation_publication": {
            "preparation_ref": ".task/cycle/cycle-1/acceptance.json",
            "preparation_sha256": SHA,
        },
    }
    adapter = _SequenceAdapter([approval_wait, owner_ready])
    waiting, boundary = continue_session(_state(_lease()), adapter, at=AT)
    progressed, action = continue_session(waiting, adapter, at=AT)

    assert boundary["actor"] == "user"
    assert action["actor"] == "agent"
    assert action["target"] == "acceptance"
    assert progressed["pending_action"] == action
    assert progressed["usage"]["agent_actions"] == 1
    assert adapter.advance_count == 2


def test_new_local_run_proof_clears_effect_boundary_without_reprompt() -> None:
    run_wait = {
        "status": "waiting",
        "stop_reason": "awaiting_owner_result",
        "preparation": _run_preparation(),
        "preparation_publication": {
            "preparation_ref": ".task/cycle/cycle-1/run.json",
            "preparation_sha256": SHA,
        },
    }
    adapter = _SequenceAdapter(
        [run_wait, run_wait],
        classifications=["unknown", "local_long_run"],
    )
    waiting, boundary = continue_session(_state(_lease()), adapter, at=AT)
    progressed, action = continue_session(waiting, adapter, at=AT)

    assert boundary["actor"] == "user"
    assert action["actor"] == "agent"
    assert action["effect_class"] == "local_long_run"
    assert progressed["usage"]["agent_actions"] == 1


def test_session_lease_must_be_exact_and_include_local_long_run(
    tmp_path: Path,
) -> None:
    lease = _lease()
    path = tmp_path / lease["session_binding"]["session_ref"]
    path.parent.mkdir(parents=True)
    payload = (
        json.dumps(lease, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    path.write_bytes(payload)
    state = _state(lease, raw_sha=hashlib.sha256(payload).hexdigest())
    loaded, raw = local_run_dispatch._session_lease(tmp_path, state)
    assert loaded == lease
    assert raw == payload

    changed = bytearray(payload)
    changed[-2] = ord(" ")
    path.write_bytes(changed)
    with pytest.raises(ValueError, match="bytes changed"):
        local_run_dispatch._session_lease(tmp_path, state)

    denied = _lease(groups=["local_git_commit"])
    denied_payload = (
        json.dumps(denied, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    denied_path = tmp_path / denied["session_binding"]["session_ref"]
    denied_path.write_bytes(denied_payload)
    denied_state = _state(
        denied, raw_sha=hashlib.sha256(denied_payload).hexdigest()
    )
    with pytest.raises(ValueError, match="does not cover"):
        local_run_dispatch._session_lease(tmp_path, denied_state)


def test_sealed_preparation_binds_authority_projection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    authority = {
        "event_id": "authority-event",
        "status": "complete",
        "operation_binding": dict(local_run_dispatch._OPERATION),
    }
    model = {"authority": authority}
    state_fingerprint = selected_state_fingerprint(model, ["authority"])
    preconditions = selector_fingerprints(
        {}, model, ("authority",)
    )
    registered = executor_spec("run").projection()
    prepared = {
        "schema_version": 3,
        "cycle_id": "cycle-1",
        "target": "run",
        "executor_kind": "owner",
        "executor_spec": registered,
        "context_binding": {"artifact_type": "context"},
        "work_order_binding": {"artifact_type": "work_order"},
        "state_fingerprint": state_fingerprint,
        "fingerprint_roles": ["authority"],
        "precondition_fingerprints": preconditions,
    }
    context = {
        "cycle_id": "cycle-1",
        "target": "run",
        "state_fingerprint": state_fingerprint,
        "precondition_fingerprints": preconditions,
        "model_context": model,
    }
    work_order = {
        "cycle_id": "cycle-1",
        "target": "run",
        "executor_spec": registered,
        "context_binding": prepared["context_binding"],
        "state_fingerprint": state_fingerprint,
        "precondition_fingerprints": preconditions,
    }
    monkeypatch.setattr(
        local_run_dispatch, "validate_preparation", lambda value: value
    )
    monkeypatch.setattr(
        local_run_dispatch,
        "load_compiler_artifact",
        lambda _root, _cycle, _binding, kind: (
            context if kind == "context" else work_order
        ),
    )
    assert (
        local_run_dispatch._sealed_authority_projection(tmp_path, prepared)
        == authority
    )

    prepared["precondition_fingerprints"] = {
        **preconditions,
        "authority": "b" * 64,
    }
    with pytest.raises(ValueError):
        local_run_dispatch._sealed_authority_projection(tmp_path, prepared)


def _packet_and_decision(
    state: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    operation = dict(local_run_dispatch._OPERATION)
    packet = {
        "decision_binding": {"decision": "allowed"},
        "operation_binding": {
            **operation,
            "mutation_class": "local_mutation",
        },
        "axes": {
            "authority": {"status": "granted"},
            "local_resolution": {"status": "available"},
            "external_input": {"status": "not_required"},
        },
        "scope": {
            "cycle_id": state["active_cycle_id"],
            "task_id": state["active_task_id"],
        },
        "reservation_binding": {
            "applicability": "required",
            "status": "reserved",
        },
        "dispatch_preflight": {
            "status": "verified",
            "stage": "pre_dispatch",
        },
        "selected_grants": [
            {"grant_id": "grant-1", "grant_sha256": "grant-sha"}
        ],
    }
    decision = {
        "request": {
            **operation,
            "effect_class": "run_long",
            "mutation_class": "local_mutation",
            "data_class": "runtime_state",
            "risk_tier": "R2",
            "cycle_id": state["active_cycle_id"],
            "task_id": state["active_task_id"],
        },
        "evaluation_context": {
            "session_ceiling": {"evidence_id": state["session_id"]},
            "goal_autonomy_envelope": {
                "source_binding": {"sha256": "goal-digest"}
            },
        },
    }
    return packet, decision


def test_external_or_cross_session_authority_never_qualifies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lease = _lease()
    state = _state(lease)
    packet, decision = _packet_and_decision(state)
    grant = {
        "session_id": state["session_id"],
        "task_id": state["active_task_id"],
        "risk_ceiling": "R2",
        "operations": [dict(local_run_dispatch._OPERATION)],
        "policy_snapshot": {"sha256": "policy-digest"},
    }
    monkeypatch.setattr(
        local_run_dispatch, "_active_plan", lambda _root, _lease: {}
    )
    import manage_agent_authority.authority_interaction
    import manage_agent_authority.authority_interaction_broker as broker
    import manage_agent_authority.projection_io as projection_io

    monkeypatch.setattr(
        broker,
        "_session_scope",
        lambda *args, **kwargs: (state["session_id"], None),
    )
    monkeypatch.setattr(
        projection_io,
        "load_grant_artifact",
        lambda *args, **kwargs: (grant, "grant-sha"),
    )
    assert local_run_dispatch._request_matches_session(
        tmp_path, state, lease, packet, decision, at=AT
    )

    external_packet = json.loads(json.dumps(packet))
    external_decision = json.loads(json.dumps(decision))
    external_packet["operation_binding"].update(
        {
            "operation_id": "call_provider",
            "mutation_class": "external_mutation",
        }
    )
    external_decision["request"].update(
        {
            "operation_id": "call_provider",
            "effect_class": "call_provider",
            "mutation_class": "external_mutation",
            "risk_tier": "R3",
        }
    )
    assert not local_run_dispatch._request_matches_session(
        tmp_path,
        state,
        lease,
        external_packet,
        external_decision,
        at=AT,
    )

    grant["session_id"] = "session-other"
    assert not local_run_dispatch._request_matches_session(
        tmp_path, state, lease, packet, decision, at=AT
    )
