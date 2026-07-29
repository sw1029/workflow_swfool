from __future__ import annotations

from argparse import Namespace
from copy import deepcopy
import json
import os
from pathlib import Path
import stat
from typing import Any

import pytest

from manage_agent_authority.session_binding import build_session_binding
from manage_agent_authority.session_lease import build_session_lease
from orchestrate_task_cycle.continuation.actions import (
    ContinuationContractError,
    validate_action,
)
from orchestrate_task_cycle.continuation.applicability import (
    compile_applicability_plan,
)
from orchestrate_task_cycle.continuation.applicability_facts import (
    derive_applicability_facts,
)
from orchestrate_task_cycle.continuation import cli as continuation_cli
from orchestrate_task_cycle.continuation.cli import (
    _accept,
    _continue,
    _refresh_liveness,
    _state_candidates,
)
from orchestrate_task_cycle.continuation.session_envelope import (
    live_session_lease_candidates,
    verify_live_state_lease,
)
from orchestrate_task_cycle.continuation import state as continuation_state
from orchestrate_task_cycle.continuation.service import (
    accept_action,
    continue_session,
    recover_session,
    start_session,
    status_card,
    stop_session,
)
from orchestrate_task_cycle.continuation.not_applicable import (
    AUTO_SETTLE_TARGETS,
    _owner_result as not_applicable_owner_result,
)
from orchestrate_task_cycle.continuation.state import load_state, write_state
from orchestrate_task_cycle.continuation.terminal import (
    build_run_terminal_intake,
)
from orchestrate_task_cycle.continuation import stage_adapter
from orchestrate_task_cycle.continuation import stage_advancement
from orchestrate_task_cycle.continuation import successor_adapter
from orchestrate_task_cycle.stage.input_compilers import (
    _owner_validation_body,
)
from orchestrate_task_cycle.stage.executor_registry import (
    OWNER_EFFECT_MATRIX,
    executor_spec,
    owner_recovery_strategy,
)
from orchestrate_task_cycle.stage.preparation_v3 import render_preparation
from orchestrate_task_cycle.stage.specs import TARGET_COMPILE_SPECS
from run_task_code_and_log.terminal_projection import (
    build_run_terminal_projection,
)


NOW = "2026-07-29T00:00:00Z"
SHA = "a" * 64


def session_lease() -> dict[str, Any]:
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
        allowed_operation_groups=[
            "local_git_commit",
            "local_long_run",
            "task_topology",
        ],
        goal_digest="goal-digest",
        policy_digest="policy-digest",
        manifest_digest="manifest-digest",
        issued_at=NOW,
        expires_at="2026-07-30T00:00:00Z",
    )


def session() -> dict[str, Any]:
    lease = session_lease()
    return start_session(
        session_lease=lease,
        session_lease_binding={
            "ref": lease["session_binding"]["session_ref"],
            "sha256": lease["state_sha256"],
        },
        cycle_id="cycle-1",
        task_id="task-1",
        created_at=NOW,
    )


def preparation(
    target: str = "acceptance", kind: str | None = None
) -> dict[str, Any]:
    registered = executor_spec(target)
    selected_kind = kind or registered.executor_kind
    return {
        "target": target,
        "executor_kind": selected_kind,
        "executor_spec": {
            "executor_kind": selected_kind,
            "owner_id": registered.owner_id,
            "allowed_routing_profiles": list(
                registered.allowed_routing_profiles
            ),
            "side_effect_class": registered.side_effect_class,
        },
        "work_order_binding": {
            "artifact_type": "work_order",
            "ref": ".task/cycles/cycle-1/work-order.json",
            "sha256": SHA,
            "size_bytes": 100,
        },
        "result_contract": {"required_fields": ["acceptance_status"]},
    }


class FakeAdapter:
    def __init__(self, advances: list[dict[str, Any]]) -> None:
        self.advances = list(advances)
        self.accepted: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.recovery = {"status": "not_dispatched"}
        self.successor: dict[str, Any] | None = None

    def advance(self, cycle_id: str, *, closure_only: bool) -> dict[str, Any]:
        assert cycle_id
        return self.advances.pop(0)

    def accept(
        self, action: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        self.accepted.append((action, result))
        return {"status": "accepted", "effect_status": "settled"}

    def recover(self, action: dict[str, Any]) -> dict[str, Any]:
        return self.recovery

    def selected_successor(self, cycle_id: str) -> dict[str, Any] | None:
        return self.successor


def owner_wait() -> dict[str, Any]:
    return {
        "status": "waiting",
        "stop_reason": "awaiting_owner_result",
        "preparation": preparation(),
        "preparation_publication": {
            "preparation_ref": ".task/cycles/cycle-1/preparation.json",
            "preparation_sha256": SHA,
        },
    }


def test_driver_yields_closed_agent_action_and_accepts_once() -> None:
    adapter = FakeAdapter([owner_wait(), {"status": "complete"}])
    waiting, action = continue_session(session(), adapter, at=NOW)
    assert action["actor"] == "agent"
    assert action["kind"] == "run_owner"
    assert action["owner_skill"] == "normalize-acceptance-and-demo"
    assert validate_action(action) == action
    accepted, outcome = accept_action(
        waiting,
        action=action,
        result={"acceptance_status": "complete"},
        adapter=adapter,
        at=NOW,
    )
    assert outcome["status"] == "accepted"
    replayed, replay = accept_action(
        accepted,
        action=action,
        result={"acceptance_status": "complete"},
        adapter=adapter,
        at=NOW,
    )
    assert replayed == accepted
    assert replay["status"] == "reused"
    with pytest.raises(ContinuationContractError, match="changed"):
        accept_action(
            accepted,
            action=action,
            result={"acceptance_status": "other"},
            adapter=adapter,
            at=NOW,
        )


def test_driver_closes_at_real_user_external_and_host_boundaries() -> None:
    for reason, actor in (
        ("awaiting_exact_approval", "user"),
        ("awaiting_external_input", "external"),
    ):
        state, action = continue_session(
            session(),
            FakeAdapter([{"status": "block", "stop_reason": reason}]),
            at=NOW,
        )
        assert state["status"] == "waiting"
        assert action["actor"] == actor
    stopped = stop_session(session(), at=NOW)
    card = status_card(stopped)
    assert card["status"] == "stopped"
    assert card["next_actor"] is None


def test_stop_preserves_pending_effect_recovery_handle() -> None:
    effectful = owner_wait()
    waiting, action = continue_session(
        session(), FakeAdapter([effectful]), at=NOW
    )

    stopped = stop_session(waiting, at=NOW)

    assert stopped["status"] == "stopped"
    assert stopped["host_session_live"] is False
    assert stopped["pending_action"] == action
    assert stopped["accepted_actions"] == {}
    assert status_card(stopped)["next_actor"] is None


def test_continue_preserves_user_and_external_boundaries_for_recheck() -> None:
    for reason in ("awaiting_exact_approval", "awaiting_external_input"):
        waiting, action = continue_session(
            session(),
            FakeAdapter([{"status": "block", "stop_reason": reason}]),
            at=NOW,
        )
        refreshed = _refresh_liveness(waiting, live=True, at=NOW)
        assert action["actor"] in {"user", "external"}
        assert refreshed["status"] == "waiting"
        assert refreshed["pending_action"] == action
        assert refreshed["accepted_actions"] == {}


def test_monitor_actions_consume_the_shared_agent_action_budget() -> None:
    waiting, action = continue_session(
        session(),
        FakeAdapter(
            [{"status": "block", "stop_reason": "awaiting_running_execution"}]
        ),
        at=NOW,
    )
    assert action["kind"] == "monitor_run"
    assert waiting["usage"]["agent_actions"] == 1


def test_ambiguous_monitor_result_keeps_the_long_run_slot() -> None:
    run_wait = owner_wait()
    run_wait["preparation"] = preparation("run")
    waiting, run_action = continue_session(
        session(),
        FakeAdapter([run_wait]),
        at=NOW,
    )
    active, _outcome = accept_action(
        waiting,
        action=run_action,
        result={"run_id": "run-1", "execution_status": "running"},
        adapter=FakeAdapter([]),
        at=NOW,
    )
    assert active["usage"]["active_long_runs"] == ["run-1"]

    monitoring, monitor = continue_session(
        active,
        FakeAdapter(
            [{"status": "block", "stop_reason": "awaiting_running_execution"}]
        ),
        at=NOW,
    )
    observed, _outcome = accept_action(
        monitoring,
        action=monitor,
        result={"run_id": "run-1", "status": "partial"},
        adapter=FakeAdapter([]),
        at=NOW,
    )
    assert observed["usage"]["active_long_runs"] == ["run-1"]


def test_unresolved_external_or_long_run_effect_stops_before_agent_dispatch() -> None:
    run_wait = owner_wait()
    run_wait["preparation"] = preparation("run")
    run_wait["preparation"]["executor_spec"]["side_effect_class"] = (
        "external_or_long_running_effect"
    )
    waiting, action = continue_session(
        session(),
        FakeAdapter([run_wait]),
        at=NOW,
    )
    assert action["actor"] == "user"
    assert action["kind"] == "request_approval"
    assert action["target"] == "run"
    assert action["reason"] == "awaiting_effect_classification"
    assert waiting["usage"]["agent_actions"] == 0


def test_failed_terminal_monitor_result_enters_closure_without_retry() -> None:
    class TrustedTerminalAdapter(FakeAdapter):
        def accept(
            self, action: dict[str, Any], result: dict[str, Any]
        ) -> dict[str, Any]:
            self.accepted.append((action, result))
            return {
                "status": "accepted",
                "effect_status": "settled",
                "run_terminal_status": "failed_closed",
                "run_terminal_run_id": "run-1",
            }

    adapter = TrustedTerminalAdapter(
        [{"status": "block", "stop_reason": "awaiting_running_execution"}]
    )
    waiting, action = continue_session(
        session(),
        adapter,
        at=NOW,
    )
    projection = build_run_terminal_projection(
        cycle_id="cycle-1",
        run_id="run-1",
        status="failed_closed",
        monitor={
            "status": "terminal",
            "monitor_command_id": "event-run-1",
            "stop_command_id": None,
        },
        harvest={"status": "unavailable", "evidence_binding": None},
        safe_surviving_artifacts=[],
        discarded_artifacts=[],
        failure={
            "reason": "safety_gate",
            "evidence_binding": {
                "ref": ".agent_log/autopsy.json",
                "sha256": SHA,
            },
        },
        next_action="review",
        retry_policy={"automatic_retry": False},
    )
    accepted, _outcome = accept_action(
        waiting,
        action=action,
        result={
            "projection": projection,
            "binding": {
                "ref": (
                    ".agent_log/run-terminal-projections/"
                    f"{projection['projection_id']}.json"
                ),
                "sha256": SHA,
            },
        },
        adapter=adapter,
        at=NOW,
    )
    assert accepted["closure_only"] is True
    assert accepted["usage"]["active_long_runs"] == []


def test_raw_terminal_claim_without_adapter_verification_is_not_accepted_as_closure() -> None:
    adapter = FakeAdapter(
        [{"status": "block", "stop_reason": "awaiting_running_execution"}]
    )
    waiting, action = continue_session(session(), adapter, at=NOW)
    accepted, _outcome = accept_action(
        waiting,
        action=action,
        result={
            "run_id": "run-1",
            "run_disposition": "failed_closed",
            "run_terminal_projection": {"status": "failed_closed"},
        },
        adapter=adapter,
        at=NOW,
    )
    assert accepted["closure_only"] is False
    assert accepted["usage"]["active_long_runs"] == ["run-1"]


def test_live_adapter_accepts_only_a_sealed_monitor_observation(
    tmp_path: Path, monkeypatch
) -> None:
    _waiting, action = continue_session(
        session(),
        FakeAdapter(
            [{"status": "block", "stop_reason": "awaiting_running_execution"}]
        ),
        at=NOW,
    )
    event = {
        "event_id": "event-monitor-1",
        "step": "run",
        "status": "partial",
        "run_id": "run-1",
    }
    monkeypatch.setattr(stage_adapter, "read_events", lambda root, cycle: [event])
    adapter = stage_adapter.StageContinuationAdapter(tmp_path)
    accepted = adapter.accept(
        action,
        {"run_id": "run-1", "ledger_append": {"event": event}},
    )
    assert accepted["status"] == "accepted"
    with pytest.raises(ContinuationContractError, match="missing or changed"):
        adapter.accept(
            action,
            {
                "run_id": "run-1",
                "ledger_append": {"event": {**event, "status": "completed"}},
            },
        )


def test_missing_lease_hides_agent_action_and_host_boundary_replays_stably(
    tmp_path: Path,
) -> None:
    waiting, agent_action = continue_session(
        session(),
        FakeAdapter([owner_wait()]),
        at=NOW,
    )
    write_state(tmp_path, waiting)
    args = Namespace(at=NOW, emit_action=True)

    first = _continue(args, tmp_path)
    first_state = load_state(tmp_path, waiting["session_id"])

    assert agent_action["actor"] == "agent"
    assert first["next_action"]["actor"] == "host"
    assert first["next_action"]["kind"] == "request_host_approval"
    assert first["internal_action"]["actor"] == "host"
    assert first_state["pending_action"] == agent_action
    assert first["interaction"]["next_actor"] == "host"
    first_version = first_state["state_version"]
    first_sha256 = first_state["state_sha256"]
    first_action_id = first["next_action"]["action_id"]

    second = _continue(args, tmp_path)
    second_state = load_state(tmp_path, waiting["session_id"])

    assert second["next_action"]["action_id"] == first_action_id
    assert second_state["state_version"] == first_version
    assert second_state["state_sha256"] == first_sha256


def test_live_state_lease_requires_the_exact_state_bound_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = session()
    lease = session_lease()
    path = tmp_path / state["session_lease_binding"]["ref"]
    reopened: list[str] = []
    monkeypatch.setattr(
        "orchestrate_task_cycle.continuation.session_envelope."
        "reopen_session_envelope",
        lambda root, value, *, at: reopened.append(at),
    )

    assert verify_live_state_lease(
        tmp_path,
        state,
        [(path, lease, state["session_lease_binding"]["sha256"])],
        at=NOW,
    )
    assert reopened == [NOW]
    with pytest.raises(ContinuationContractError, match="binding changed"):
        verify_live_state_lease(
            tmp_path,
            state,
            [(path, lease, "b" * 64)],
            at=NOW,
        )


def test_continue_accept_and_recover_share_the_lease_reopener(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    waiting, action = continue_session(
        session(), FakeAdapter([owner_wait()]), at=NOW
    )
    write_state(tmp_path, waiting)

    def drift(*_args: object, **_kwargs: object) -> bool:
        raise ContinuationContractError("signed activation drift")

    monkeypatch.setattr(continuation_cli, "verify_live_state_lease", drift)
    with pytest.raises(ContinuationContractError, match="activation drift"):
        _continue(Namespace(at=NOW, emit_action=True), tmp_path)
    with pytest.raises(ContinuationContractError, match="activation drift"):
        _accept(
            Namespace(
                action_id=action["action_id"],
                result=json.dumps({"acceptance_status": "complete"}),
                at=NOW,
                emit_action=True,
            ),
            tmp_path,
        )
    with pytest.raises(ContinuationContractError, match="activation drift"):
        continuation_cli._run(
            Namespace(
                session_command="recover",
                root=str(tmp_path),
                at=NOW,
            )
        )


def test_recover_never_resurrects_a_stopped_session(tmp_path: Path) -> None:
    stopped = stop_session(session(), at=NOW)
    write_state(tmp_path, stopped)
    with pytest.raises(ContinuationContractError, match="stopped session"):
        continuation_cli._run(
            Namespace(
                session_command="recover",
                root=str(tmp_path),
                at=NOW,
            )
        )


def test_host_return_recovers_preserved_effect_before_reissuing() -> None:
    effectful = owner_wait()
    waiting, original_action = continue_session(
        session(), FakeAdapter([effectful]), at=NOW
    )
    offline = _refresh_liveness(waiting, live=False, at=NOW)
    boundary, host_action = continue_session(
        offline, FakeAdapter([]), at=NOW
    )
    assert host_action["actor"] == "host"
    assert boundary["pending_action"] == original_action

    restored = _refresh_liveness(boundary, live=True, at=NOW)
    adapter = FakeAdapter([])
    adapter.recovery = {"status": "unknown_effect"}
    quarantined, action = continue_session(restored, adapter, at=NOW)
    assert quarantined["status"] == "quarantined"
    assert quarantined["pending_action"] is None
    assert action["kind"] == "complete"
    assert action["reason"] == "unknown_effect"


def test_host_return_rebinds_proved_not_dispatched_action() -> None:
    waiting, original_action = continue_session(
        session(), FakeAdapter([owner_wait()]), at=NOW
    )
    offline = _refresh_liveness(waiting, live=False, at=NOW)
    boundary, _host_action = continue_session(
        offline, FakeAdapter([]), at=NOW
    )
    restored = _refresh_liveness(boundary, live=True, at=NOW)
    adapter = FakeAdapter([])
    resumed, reissued = continue_session(restored, adapter, at=NOW)

    assert resumed["pending_action"] == reissued
    assert reissued["action_id"] != original_action["action_id"]
    assert (
        reissued["preparation_binding"]
        == original_action["preparation_binding"]
    )
    accepted, outcome = accept_action(
        resumed,
        action=reissued,
        result={"acceptance_status": "complete"},
        adapter=adapter,
        at=NOW,
    )
    assert accepted["pending_action"] is None
    assert outcome["status"] == "accepted"


def test_host_return_accepts_recovered_result_without_relaunch() -> None:
    waiting, original_action = continue_session(
        session(), FakeAdapter([owner_wait()]), at=NOW
    )
    offline = _refresh_liveness(waiting, live=False, at=NOW)
    boundary, _host_action = continue_session(
        offline, FakeAdapter([]), at=NOW
    )
    restored = _refresh_liveness(boundary, live=True, at=NOW)
    adapter = FakeAdapter([{"status": "complete"}])
    adapter.recovery = {
        "status": "result_found",
        "result": {"acceptance_status": "complete"},
    }
    completed, action = continue_session(restored, adapter, at=NOW)

    assert completed["status"] == "complete"
    assert completed["pending_action"] is None
    assert action["kind"] == "complete"
    assert len(adapter.accepted) == 1
    assert adapter.accepted[0][0]["action_id"] != original_action["action_id"]


def test_host_return_keeps_pending_effect_in_recovery_wait() -> None:
    effectful = owner_wait()
    waiting, original_action = continue_session(
        session(), FakeAdapter([effectful]), at=NOW
    )
    offline = _refresh_liveness(waiting, live=False, at=NOW)
    boundary, _host_action = continue_session(
        offline, FakeAdapter([]), at=NOW
    )
    restored = _refresh_liveness(boundary, live=True, at=NOW)
    adapter = FakeAdapter([])
    adapter.recovery = {"status": "pending"}
    recovering, action = continue_session(restored, adapter, at=NOW)

    assert recovering["status"] == "host_boundary"
    assert recovering["pending_action"] == original_action
    assert recovering["last_stop_reason"] == "awaiting_effect_settlement"
    assert action["actor"] == "external"
    assert action["kind"] == "wait_external"
    assert status_card(recovering)["next_actor"] == "external"


def test_continuation_state_uses_compare_and_swap_and_cannot_restart(
    tmp_path: Path,
) -> None:
    initial = session()
    write_state(tmp_path, initial)
    stopped = stop_session(initial, at=NOW)
    write_state(
        tmp_path,
        stopped,
        expected_state_sha256=initial["state_sha256"],
    )
    competing = stop_session(initial, at=NOW, reason="competing_stop")
    with pytest.raises(ContinuationContractError, match="compare-and-swap"):
        write_state(
            tmp_path,
            competing,
            expected_state_sha256=initial["state_sha256"],
        )
    with pytest.raises(ContinuationContractError, match="already exists"):
        write_state(tmp_path, initial)


def test_accept_cli_replays_exact_persisted_action_result_without_a_lease(
    tmp_path: Path,
) -> None:
    waiting, action = continue_session(
        session(), FakeAdapter([owner_wait()]), at=NOW
    )
    result = {"acceptance_status": "complete"}
    accepted, _outcome = accept_action(
        waiting,
        action=action,
        result=result,
        adapter=FakeAdapter([]),
        at=NOW,
    )
    write_state(tmp_path, accepted)
    args = Namespace(
        action_id=action["action_id"],
        result=json.dumps(result),
        at=NOW,
        emit_action=True,
    )

    before = load_state(tmp_path, accepted["session_id"])
    output = _accept(args, tmp_path)
    after = load_state(tmp_path, accepted["session_id"])

    assert output["interaction"]["session"] == accepted["session_id"]
    assert "next_action" not in output
    assert after == before

    changed = Namespace(
        action_id=action["action_id"],
        result=json.dumps({"acceptance_status": "changed"}),
        at=NOW,
        emit_action=False,
    )
    with pytest.raises(ContinuationContractError, match="changed its result"):
        _accept(changed, tmp_path)


def test_session_scanners_reject_symlinked_session_parent(
    tmp_path: Path,
) -> None:
    sessions = tmp_path / ".task" / "authorization" / "sessions"
    sessions.mkdir(parents=True)
    outside = tmp_path / "outside-session"
    outside.mkdir()
    (sessions / "session-link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ContinuationContractError, match="must not be a symlink"):
        _state_candidates(tmp_path)
    with pytest.raises(ContinuationContractError, match="must not be a symlink"):
        live_session_lease_candidates(tmp_path)


def test_state_rejects_symlink_target_and_fsyncs_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_fsync_kinds: list[bool] = []
    real_fsync = continuation_state.os.fsync

    def recording_fsync(descriptor: int) -> None:
        observed_fsync_kinds.append(
            stat.S_ISDIR(os.fstat(descriptor).st_mode)
        )
        real_fsync(descriptor)

    monkeypatch.setattr(continuation_state.os, "fsync", recording_fsync)
    initial = session()
    path = write_state(tmp_path, initial)
    assert observed_fsync_kinds[-1] is True

    path.unlink()
    outside = tmp_path / "outside-state.json"
    outside.write_text(json.dumps(initial), encoding="utf-8")
    path.symlink_to(outside)
    with pytest.raises(ContinuationContractError, match="must not be a symlink"):
        load_state(tmp_path, initial["session_id"])


def test_unknown_effect_recovery_quarantines_without_relaunch() -> None:
    adapter = FakeAdapter([owner_wait()])
    waiting, action = continue_session(session(), adapter, at=NOW)
    action = dict(action)
    action["effect_class"] = "local_reversible"
    # Rebuild the pending state with a valid content-bound action by producing
    # an effectful preparation instead of tampering with the action identity.
    effectful = owner_wait()
    waiting, action = continue_session(session(), FakeAdapter([effectful]), at=NOW)
    adapter.recovery = {"status": "unknown_effect"}
    quarantined, result = recover_session(waiting, adapter, at=NOW)
    assert quarantined["status"] == "quarantined"
    assert result["reason"] == "unknown_effect"


def test_owner_effect_matrix_never_reissues_unproved_mutations() -> None:
    safe_reissue = {
        target
        for target, policy in OWNER_EFFECT_MATRIX.items()
        if owner_recovery_strategy(
            target, policy.action_effect_classes[0]
        )
        == "safe_reissue"
    }
    assert safe_reissue == {"qualitative_review"}
    assert (
        owner_recovery_strategy("closeout_commit", "local_commit")
        == "verify_closeout_anchor"
    )
    assert (
        owner_recovery_strategy("acceptance", "local_reversible")
        == "uncertain"
    )
    assert owner_recovery_strategy("acceptance", "observe_only") == "uncertain"
    assert owner_recovery_strategy("future_target", "observe_only") == "uncertain"


def test_effectful_owner_action_uses_local_effect_not_observe_only() -> None:
    waiting, action = continue_session(
        session(), FakeAdapter([owner_wait()]), at=NOW
    )
    assert waiting["pending_action"] == action
    assert action["target"] == "acceptance"
    assert action["effect_class"] == "local_reversible"


def test_real_adapter_quarantines_unproved_owner_recovery(
    tmp_path: Path,
) -> None:
    waiting, _action = continue_session(
        session(), FakeAdapter([owner_wait()]), at=NOW
    )
    adapter = stage_adapter.StageContinuationAdapter(
        tmp_path,
        session_id=waiting["session_id"],
        goal_id=waiting["goal_id"],
        task_family=waiting["task_family"],
    )
    quarantined, outcome = recover_session(waiting, adapter, at=NOW)
    assert quarantined["status"] == "quarantined"
    assert quarantined["pending_action"] is None
    assert outcome == {
        "status": "quarantined",
        "reason": "unknown_effect",
    }


def test_cross_cycle_continuation_is_same_envelope_and_budgeted() -> None:
    adapter = FakeAdapter([{"status": "complete"}, {"status": "complete"}])
    adapter.successor = {
        "outcome": "selected",
        "cycle_id": "cycle-2",
        "task_id": "task-2",
        "goal_id": "goal-1",
        "task_family": "family-1",
        "risk_envelope_match": True,
    }
    completed, action = continue_session(session(), adapter, at=NOW)
    assert completed["active_cycle_id"] == "cycle-2"
    assert completed["usage"]["cycles"] == 2
    assert action["kind"] == "complete"


def test_live_successor_bridge_never_infers_an_unbound_session(
    tmp_path: Path,
) -> None:
    assert successor_adapter.selected_initialized_successor(
        tmp_path,
        "cycle-1",
        goal_id="goal-1",
        task_family="family-1",
    ) is None


def test_adaptive_plan_defers_normal_commit_and_escalates_unknown() -> None:
    facts = {
        "needs_validation_set": False,
        "adapter_changed": None,
        "code_surface_changed": True,
        "user_visible_delta": False,
        "repeated_friction": False,
        "issue_context": False,
        "schema_impact": False,
        "tracked_delta": True,
    }
    plan = compile_applicability_plan(
        cycle_id="cycle-1",
        evidence_binding={"ref": ".task/evidence.json", "sha256": SHA},
        facts=facts,
    )
    rows = {row["step"]: row for row in plan["decisions"]}
    assert rows["commit"]["disposition"] == "not_applicable"
    assert rows["commit"]["reason"] == "deferred_to_batched_closeout"
    assert rows["closeout_commit"]["disposition"] == "required"
    assert rows["repo_skill_adapter_validate"]["disposition"] == "required"
    assert (
        rows["repo_skill_adapter_validate"]["reason"]
        == "unknown_escalated_to_required"
    )


def test_live_applicability_facts_use_only_closed_context_evidence() -> None:
    model = {
        "git": {
            "changed_paths": {
                "total_count": 2,
                "included_count": 2,
                "truncated": False,
                "items": ["src/app.py", ".schema/model.json"],
            },
            "worktree_identity": {"binding_status": "exact"},
        },
        "cycle": {
            "steps": {
                "validation_set_plan": {
                    "decision_scalars": {"validation_set_need": "not_required"}
                },
                "qualitative_review": {
                    "decision_scalars": {
                        "changed_vs_previous": True,
                        "produced_domain_delta": True,
                    }
                },
                "loopback_audit": {
                    "status": "complete",
                    "decision_scalars": {
                        "same_family_micro_hardening_count": 0,
                        "hard_stop_required": False,
                        "recommended_disposition": "continue",
                    },
                },
                "validate": {
                    "blockers": [],
                    "decision_scalars": {"validation_verdict": "pass"},
                },
            }
        },
    }
    facts = derive_applicability_facts(model)
    assert facts == {
        "needs_validation_set": False,
        "adapter_changed": False,
        "code_surface_changed": True,
        "user_visible_delta": True,
        "repeated_friction": False,
        "issue_context": False,
        "schema_impact": True,
        "tracked_delta": True,
    }
    model["git"]["changed_paths"]["truncated"] = True
    incomplete = derive_applicability_facts(model)
    assert incomplete["adapter_changed"] is None
    assert incomplete["tracked_delta"] is None


def test_optional_owner_receipts_are_target_specific_and_evidence_bound() -> None:
    plan = {
        "plan_sha256": SHA,
        "evidence_binding": {"ref": ".task/context.json", "sha256": SHA},
    }
    decision = {"reason": "predicate_false"}
    visible = not_applicable_owner_result(
        preparation("visible_increment"), plan, decision
    )
    assert visible["delta_types"] == ["none"]
    assert visible["evidence_paths"] == [".task/context.json"]
    issue_preparation = {
        **preparation("issue"),
        "derived_values": {"task_id": "task-1"},
    }
    issue = not_applicable_owner_result(issue_preparation, plan, decision)
    assert issue["issue_status"] == "not_applicable"
    assert issue["issue_provenance"]["source_task_id"] == "task-1"
    schema = not_applicable_owner_result(
        preparation("schema_pre_derive"), plan, decision
    )
    assert schema == {
        "schema_status": "not_applicable",
        "schema_skipped_reason": "predicate_false",
        "evidence_paths": [],
    }


def test_every_automatic_na_receipt_satisfies_its_owner_field_contract(
    tmp_path: Path,
) -> None:
    model = {
        "projection_status": "ready",
        "goal_truth": {"used_goal_truth": []},
        "advice": {"items": []},
    }
    metrics = {"collection_limits": {"max_files": 12, "max_paths": 40}}
    bindings = {
        "context_binding": {
            "artifact_type": "context",
            "ref": ".task/context.json",
            "sha256": "b" * 64,
            "size_bytes": 1,
        },
        "work_order_binding": {
            "artifact_type": "work_order",
            "ref": ".task/work-order.json",
            "sha256": "c" * 64,
            "size_bytes": 1,
        },
    }
    plan = {
        "plan_sha256": "d" * 64,
        "evidence_binding": {
            "ref": ".task/evidence.json",
            "sha256": "e" * 64,
        },
    }
    for target in sorted(AUTO_SETTLE_TARGETS):
        spec = TARGET_COMPILE_SPECS[target]
        fingerprints = {
            selector: "f" * 64 for selector in spec.dependency_selectors
        }
        prepared = render_preparation(
            "cycle-1",
            target,
            "normal",
            "task-1",
            model,
            metrics,
            bindings,
            fingerprints,
            schema_version=3,
        )
        body = not_applicable_owner_result(
            prepared, plan, {"reason": "predicate_false"}
        )
        assert set(spec.owner_receipt_fields) <= set(body)
        assert _owner_validation_body(tmp_path, prepared, body) == body


def test_consecutive_false_optional_stages_settle_before_required_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    targets = iter(
        (
            "validation_set_build",
            "visible_increment",
            "validation_scope_finalize",
        )
    )
    advances = iter(
        (
            {
                "status": "waiting",
                "preparation": preparation("validation_set_build"),
            },
            {
                "status": "waiting",
                "preparation": preparation("visible_increment"),
            },
            {
                "status": "waiting",
                "preparation": preparation("validation_scope_finalize"),
            },
        )
    )
    facts = {
        "needs_validation_set": False,
        "adapter_changed": False,
        "code_surface_changed": False,
        "user_visible_delta": False,
        "repeated_friction": False,
        "issue_context": False,
        "schema_impact": False,
        "tracked_delta": False,
    }
    plan = compile_applicability_plan(
        cycle_id="cycle-1",
        evidence_binding={"ref": ".task/evidence.json", "sha256": SHA},
        facts=facts,
    )
    decisions = {row["step"]: row for row in plan["decisions"]}
    settled: list[str] = []
    monkeypatch.setattr(stage_advancement, "read_events", lambda *_args: [])
    monkeypatch.setattr(
        stage_advancement, "_next_target", lambda *_args, **_kwargs: next(targets)
    )
    monkeypatch.setattr(
        stage_advancement,
        "advance_stage",
        lambda *_args, **_kwargs: next(advances),
    )
    monkeypatch.setattr(
        stage_advancement,
        "_applicability_decision",
        lambda _root, _cycle, target, preparation=None: (
            plan,
            decisions[target],
        ),
    )
    monkeypatch.setattr(
        stage_advancement,
        "publish_preparation",
        lambda _root, value: {
            "preparation_ref": f".task/{value['target']}.json",
            "preparation_sha256": SHA,
        },
    )

    def settle(
        _root: Path,
        prepared: dict[str, Any],
        _publication: dict[str, Any],
        _plan: dict[str, Any],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        assert decision["disposition"] == "not_applicable"
        settled.append(str(prepared["target"]))
        return {"status": "passed", "applied": True}

    monkeypatch.setattr(stage_advancement, "settle_not_applicable", settle)
    result = stage_advancement.advance(
        tmp_path, "normal", "cycle-1", closure_only=False
    )
    assert settled == ["validation_set_build", "visible_increment"]
    assert result["status"] == "waiting"
    assert result["preparation"]["target"] == "validation_scope_finalize"
    assert result["preparation_publication"]["preparation_ref"] == (
        ".task/validation_scope_finalize.json"
    )


@pytest.mark.parametrize(
    ("target", "fact_name", "fact_value", "reason"),
    (
        (
            "validation_set_build",
            "needs_validation_set",
            None,
            "unknown_escalated_to_required",
        ),
        (
            "visible_increment",
            "user_visible_delta",
            True,
            "user_visible_delta",
        ),
    ),
)
def test_required_or_unknown_optional_owner_is_not_auto_settled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    fact_name: str,
    fact_value: bool | None,
    reason: str,
) -> None:
    facts: dict[str, bool | None] = {
        "needs_validation_set": False,
        "adapter_changed": False,
        "code_surface_changed": False,
        "user_visible_delta": False,
        "repeated_friction": False,
        "issue_context": False,
        "schema_impact": False,
        "tracked_delta": False,
    }
    facts[fact_name] = fact_value
    plan = compile_applicability_plan(
        cycle_id="cycle-1",
        evidence_binding={"ref": ".task/evidence.json", "sha256": SHA},
        facts=facts,
    )
    decision = next(row for row in plan["decisions"] if row["step"] == target)
    assert decision == {
        "step": target,
        "disposition": "required",
        "reason": reason,
        "inputs_sha256": plan["inputs_sha256"],
    }
    monkeypatch.setattr(stage_advancement, "read_events", lambda *_args: [])
    monkeypatch.setattr(
        stage_advancement, "_next_target", lambda *_args, **_kwargs: target
    )
    monkeypatch.setattr(
        stage_advancement,
        "advance_stage",
        lambda *_args, **_kwargs: {
            "status": "waiting",
            "preparation": preparation(target),
        },
    )
    monkeypatch.setattr(
        stage_advancement,
        "_applicability_decision",
        lambda *_args, **_kwargs: (plan, decision),
    )
    monkeypatch.setattr(
        stage_advancement,
        "publish_preparation",
        lambda *_args: {
            "preparation_ref": f".task/{target}.json",
            "preparation_sha256": SHA,
        },
    )
    monkeypatch.setattr(
        stage_advancement,
        "settle_not_applicable",
        lambda *_args, **_kwargs: pytest.fail(
            "required owner stage was auto-settled"
        ),
    )
    result = stage_advancement.advance(
        tmp_path, "normal", "cycle-1", closure_only=False
    )
    assert result["status"] == "waiting"
    assert result["preparation"]["target"] == target


def test_closure_allowlist_blocks_run_before_stage_advancement(
    tmp_path: Path, monkeypatch
) -> None:
    called = False

    def unexpected_advance(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {"status": "waiting"}

    monkeypatch.setattr(stage_advancement, "read_events", lambda root, cycle: [])
    monkeypatch.setattr(
        stage_advancement, "_next_target", lambda *args, **kwargs: "run"
    )
    monkeypatch.setattr(
        stage_advancement, "advance_stage", unexpected_advance
    )
    result = stage_advancement.advance(
        tmp_path, "normal", "cycle-1", closure_only=True
    )
    assert result["status"] == "block"
    assert result["stop_reason"] == "closure_target_not_safe"
    assert result["blocked_target"] == "run"
    assert called is False


def test_normal_commit_is_settled_not_applicable_before_owner_dispatch(
    tmp_path: Path, monkeypatch
) -> None:
    commit_preparation = preparation("commit")
    targets = iter(("commit", "dashboard"))
    advances = iter(
        (
            {
                "status": "waiting",
                "stop_reason": "awaiting_owner_result",
                "preparation": commit_preparation,
            },
            {"status": "complete", "stop_reason": "complete"},
        )
    )
    settlement_calls: list[dict[str, Any]] = []
    plan = {
        "evidence_binding": {
            "ref": ".task/cycle/cycle-1/initialization.json",
            "sha256": SHA,
        }
    }
    decision = {
        "step": "commit",
        "disposition": "not_applicable",
        "reason": "deferred_to_batched_closeout",
    }

    monkeypatch.setattr(stage_advancement, "read_events", lambda root, cycle: [])
    monkeypatch.setattr(
        stage_advancement, "_next_target", lambda *args, **kwargs: next(targets)
    )
    monkeypatch.setattr(
        stage_advancement,
        "advance_stage",
        lambda *args, **kwargs: next(advances),
    )
    monkeypatch.setattr(
        stage_advancement,
        "_applicability_decision",
        lambda root, cycle, target, preparation=None: (plan, decision),
    )
    monkeypatch.setattr(
        stage_advancement,
        "publish_preparation",
        lambda root, value: {
            "preparation_ref": ".task/preparation.json",
            "preparation_sha256": SHA,
        },
    )

    def settle(
        root: Path,
        prepared: dict[str, Any],
        publication: dict[str, Any],
        compiled_plan: dict[str, Any],
        compiled_decision: dict[str, Any],
    ) -> dict[str, Any]:
        settlement_calls.append(
            {
                "target": prepared["target"],
                "publication": publication,
                "plan": compiled_plan,
                "decision": compiled_decision,
            }
        )
        return {"status": "passed", "applied": True}

    monkeypatch.setattr(
        stage_advancement, "_settle_deferred_commit", settle
    )
    result = stage_advancement.advance(
        tmp_path, "normal", "cycle-1", closure_only=False
    )
    assert result["status"] == "complete"
    assert settlement_calls == [
        {
            "target": "commit",
            "publication": {
                "preparation_ref": ".task/preparation.json",
                "preparation_sha256": SHA,
            },
            "plan": plan,
            "decision": decision,
        }
    ]


def test_failed_closed_intake_never_retries_or_reuses_discarded_output() -> None:
    intake = build_run_terminal_intake(
        cycle_id="cycle-1",
        task_id="task-1",
        run_id="run-1",
        disposition="failed_closed",
        failure_reason="safety_gate",
        safe_surviving_artifacts=[{"ref": ".agent_log/run.json", "sha256": SHA}],
        discarded_artifacts=[{"ref": "var/output.bin", "sha256": "b" * 64}],
        autopsy_binding={"ref": ".agent_log/autopsy.json", "sha256": "c" * 64},
    )
    assert intake["closure_only"] is True
    assert intake["automatic_retry"] is False
    assert intake["next_stage"] == "qualitative_review"


def test_action_and_state_tampering_are_rejected() -> None:
    adapter = FakeAdapter([owner_wait()])
    waiting, action = continue_session(session(), adapter, at=NOW)
    tampered = deepcopy(action)
    tampered["target"] = "run"
    with pytest.raises(ContinuationContractError, match="identity"):
        validate_action(tampered)
    broken = deepcopy(waiting)
    broken["usage"]["agent_actions"] = 99
    with pytest.raises(ContinuationContractError, match="digest"):
        status_card(broken)
