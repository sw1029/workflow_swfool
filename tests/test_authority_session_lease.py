from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from manage_agent_authority import session_approval
from manage_agent_authority.session_binding import (
    SessionBindingError,
    build_session_binding,
    validate_session_binding,
)
from manage_agent_authority.session_child import grant_reuse_disposition
from manage_agent_authority.session_lease import (
    SessionLeaseError,
    assert_dispatch_allowed,
    build_session_lease,
    consume_budget,
    settle_long_run,
    update_liveness,
)
from manage_agent_authority import session_store


NOW = "2026-07-29T00:00:00Z"
LATER = "2026-07-29T01:00:00Z"


def tracked_plan() -> dict:
    return {
        "goal_policy_snapshot": {
            "final_goal_sha256": "1" * 64,
            "authority_policy_sha256": "2" * 64,
            "goal_contract_sha256": "3" * 64,
        },
        "manifest_bindings": [{"ref": "manifest", "sha256": "4" * 64}],
        "limits": {
            "max_total_uses": 512,
            "max_concurrent_long_runs": 1,
        },
        "profile": {
            "max_risk": "R2",
            "operation_groups": [
                "local_git_commit",
                "local_long_run",
                "task_topology",
            ],
        },
        "authority_interaction_mode": "governed",
        "expires_at": LATER,
    }


def patch_activation(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        session_store,
        "_eligible_activation",
        lambda root: (
            {"activation_id": "activation-1"},
            tracked_plan(),
        ),
    )
    monkeypatch.setattr(
        session_store.interaction,
        "workspace_identity",
        lambda root: {"workspace": str(root)},
    )


def binding(trust_class: str = "platform_host_receipt") -> dict:
    return build_session_binding(
        workspace_identity="workspace-1",
        provider="codex",
        thread_binding="raw-thread-value",
        activation_evidence_id="activation-1",
        trust_class=trust_class,
        approval_receipt="opaque-host-receipt",
    )


def lease(trust_class: str = "platform_host_receipt") -> dict:
    return build_session_lease(
        session_binding=binding(trust_class),
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
        expires_at=LATER,
    )


def test_binding_is_derived_and_does_not_retain_raw_values() -> None:
    value = binding()
    assert value["session_id"].startswith("session-")
    assert "raw-thread-value" not in repr(value)
    assert "opaque-host-receipt" not in repr(value)
    assert validate_session_binding(value) == value
    with pytest.raises(SessionBindingError, match="producer-derived"):
        build_session_binding(
            workspace_identity="workspace-1",
            provider="codex",
            thread_binding="thread",
            activation_evidence_id="activation-1",
            trust_class="platform_host_receipt",
            approval_receipt="receipt",
            session_id="caller-session",
        )


def test_cross_thread_and_workspace_bindings_are_distinct() -> None:
    first = binding()
    second = build_session_binding(
        workspace_identity="workspace-1",
        provider="codex",
        thread_binding="other-thread",
        activation_evidence_id="activation-1",
        trust_class="platform_host_receipt",
        approval_receipt="opaque-host-receipt",
    )
    third = build_session_binding(
        workspace_identity="workspace-2",
        provider="codex",
        thread_binding="raw-thread-value",
        activation_evidence_id="activation-1",
        trust_class="platform_host_receipt",
        approval_receipt="opaque-host-receipt",
    )
    assert len({first["session_id"], second["session_id"], third["session_id"]}) == 3


def test_agent_tty_can_only_narrow_existing_authority() -> None:
    narrowed = build_session_lease(
        session_binding=binding("agent_mediated_tty_narrowing"),
        goal_id="goal-1",
        task_family="family-1",
        activation_mode="governed",
        activation_risk_ceiling="R3",
        allowed_operation_groups=["local_git_commit"],
        goal_digest="goal-digest",
        policy_digest="policy-digest",
        manifest_digest="manifest-digest",
        issued_at=NOW,
        expires_at=LATER,
    )
    assert narrowed["risk_ceiling"] == "R2"
    with pytest.raises(SessionLeaseError, match="cannot authorize"):
        build_session_lease(
            session_binding=binding("agent_mediated_tty_narrowing"),
            goal_id="goal-1",
            task_family="family-1",
            activation_mode="governed",
            activation_risk_ceiling="R3",
            allowed_operation_groups=["push_git"],
            goal_digest="goal-digest",
            policy_digest="policy-digest",
            manifest_digest="manifest-digest",
            issued_at=NOW,
            expires_at=LATER,
        )
    host = build_session_lease(
        session_binding=binding("platform_host_receipt"),
        goal_id="goal-1",
        task_family="family-1",
        activation_mode="governed",
        activation_risk_ceiling="R3",
        allowed_operation_groups=["local_git_commit"],
        goal_digest="goal-digest",
        policy_digest="policy-digest",
        manifest_digest="manifest-digest",
        issued_at=NOW,
        expires_at=LATER,
    )
    assert host["risk_ceiling"] == "R2"
    with pytest.raises(SessionLeaseError, match="cannot authorize"):
        build_session_lease(
            session_binding=binding("platform_host_receipt"),
            goal_id="goal-1",
            task_family="family-1",
            activation_mode="governed",
            activation_risk_ceiling="R3",
            allowed_operation_groups=["push_git"],
            goal_digest="goal-digest",
            policy_digest="policy-digest",
            manifest_digest="manifest-digest",
            issued_at=NOW,
            expires_at=LATER,
        )


def test_dispatch_requires_live_exact_envelope() -> None:
    value = lease()
    assert_dispatch_allowed(
        value,
        at=NOW,
        goal_digest="goal-digest",
        policy_digest="policy-digest",
        manifest_digest="manifest-digest",
        operation_group="local_git_commit",
        risk_tier="R2",
    )
    with pytest.raises(SessionLeaseError, match="drifted"):
        assert_dispatch_allowed(
            value,
            at=NOW,
            goal_digest="other",
            policy_digest="policy-digest",
            manifest_digest="manifest-digest",
            operation_group="local_git_commit",
            risk_tier="R2",
        )
    with pytest.raises(SessionLeaseError, match="expired"):
        assert_dispatch_allowed(
            value,
            at=LATER,
            goal_digest="goal-digest",
            policy_digest="policy-digest",
            manifest_digest="manifest-digest",
            operation_group="local_git_commit",
            risk_tier="R2",
        )
    stopped = update_liveness(value, at=NOW, host_receipt_live=True, stop=True)
    with pytest.raises(SessionLeaseError, match="new dispatch"):
        assert_dispatch_allowed(
            stopped,
            at=NOW,
            goal_digest="goal-digest",
            policy_digest="policy-digest",
            manifest_digest="manifest-digest",
            operation_group="local_git_commit",
            risk_tier="R2",
        )


def test_cycle_action_long_run_and_commit_budgets_are_enforced() -> None:
    value = lease()
    for _ in range(3):
        value = consume_budget(value, kind="cycle")
    with pytest.raises(SessionLeaseError, match="cycle budget"):
        consume_budget(value, kind="cycle")
    action_budget = value["budgets"]["max_agent_actions"]
    assert action_budget == 72
    for _ in range(action_budget):
        value = consume_budget(value, kind="agent_action")
    with pytest.raises(SessionLeaseError, match="agent-action"):
        consume_budget(value, kind="agent_action")
    value = consume_budget(value, kind="long_run", identifier="run-1")
    assert consume_budget(value, kind="long_run", identifier="run-1") == value
    with pytest.raises(SessionLeaseError, match="long-run"):
        consume_budget(value, kind="long_run", identifier="run-2")
    value = settle_long_run(value, "run-1")
    value = consume_budget(value, kind="long_run", identifier="run-2")
    value = consume_budget(value, kind="commit", identifier="cycle-1")
    with pytest.raises(SessionLeaseError, match="commit budget"):
        consume_budget(value, kind="commit", identifier="cycle-1")


def test_state_tamper_and_legacy_null_session_fail_closed() -> None:
    value = lease()
    tampered = deepcopy(value)
    tampered["usage"]["cycles"] = 2
    with pytest.raises(SessionLeaseError, match="digest mismatch"):
        assert_dispatch_allowed(
            tampered,
            at=NOW,
            goal_digest="goal-digest",
            policy_digest="policy-digest",
            manifest_digest="manifest-digest",
            operation_group="local_git_commit",
            risk_tier="R2",
        )
    assert grant_reuse_disposition({"session_id": None}, value["session_binding"]["session_id"]) == "legacy_reader_only"
    assert grant_reuse_disposition({"session_id": "other"}, value["session_binding"]["session_id"]) == "session_mismatch"


def test_tracked_session_store_is_thread_bound_and_stoppable(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    patch_activation(monkeypatch, tmp_path)
    value = session_store.build_tty_session_lease(
        tmp_path,
        thread_binding="thread-1",
        provider="codex",
        approval_receipt="tty-receipt",
        issued_at=NOW,
    )
    path = tmp_path / value["session_binding"]["session_ref"]
    assert path.is_file()
    assert len(
        session_store.matching_session_leases(
            tmp_path, thread_binding="thread-1"
        )
    ) == 1
    assert (
        session_store.matching_session_leases(
            tmp_path, thread_binding="thread-2"
        )
        == []
    )
    reused = session_store.build_tty_session_lease(
        tmp_path,
        thread_binding="thread-1",
        provider="codex",
        approval_receipt="tty-receipt",
        issued_at="2026-07-29T00:05:00Z",
    )
    assert reused == value
    stopped = session_store.stop_matching_session(
        tmp_path, thread_binding="thread-1", stopped_at=NOW
    )
    assert stopped["lifecycle"]["status"] == "stopped"
    with pytest.raises(session_store.SessionStoreError, match="terminal"):
        session_store.build_tty_session_lease(
            tmp_path,
            thread_binding="thread-1",
            provider="codex",
            approval_receipt="tty-receipt",
            issued_at="2026-07-29T00:10:00Z",
        )


def test_host_receipt_is_the_no_prompt_primary_session_path(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    plan = tracked_plan()
    plan["limits"]["max_total_uses"] = 24
    plan["profile"]["max_risk"] = "R3"
    plan["profile"]["operation_groups"] = [
        "local_git_commit",
        "local_long_run",
    ]
    monkeypatch.setattr(
        session_store,
        "_eligible_activation",
        lambda root: ({"activation_id": "activation-1"}, plan),
    )
    monkeypatch.setattr(
        session_store.interaction,
        "workspace_identity",
        lambda root: {"workspace": str(root)},
    )
    value = session_store.build_host_session_lease(
        tmp_path,
        thread_binding="thread-1",
        provider="codex",
        approval_receipt="host-receipt",
        issued_at=NOW,
    )
    assert value["session_binding"]["trust_class"] == "platform_host_receipt"
    assert value["risk_ceiling"] == "R2"
    assert value["budgets"]["max_agent_actions"] == 24
    assert "host-receipt" not in repr(value)


def test_repeated_tty_start_reuses_live_lease_without_prompt_or_reset(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    patch_activation(monkeypatch, tmp_path)
    confirmations: list[str] = []
    monkeypatch.setattr(
        session_approval,
        "confirm_exact",
        lambda summary, expected: confirmations.append(expected),
    )
    monkeypatch.setattr(session_approval, "_utc_now", lambda: NOW)

    first = session_approval.start_tty_session(
        tmp_path, thread_binding="thread-1"
    )
    consumed = consume_budget(first, kind="cycle")
    session_store.write_session_lease(
        tmp_path,
        consumed,
        expected_state_sha256=first["state_sha256"],
    )
    reused = session_approval.start_tty_session(
        tmp_path, thread_binding="thread-1"
    )

    assert reused == consumed
    assert reused["usage"]["cycles"] == 1
    assert len(confirmations) == 1
    assert len(
        session_store.matching_session_leases(
            tmp_path, thread_binding="thread-1"
        )
    ) == 1


def test_terminal_scope_cannot_be_revived_by_a_fresh_tty_receipt(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    patch_activation(monkeypatch, tmp_path)
    original = session_store.build_tty_session_lease(
        tmp_path,
        thread_binding="thread-1",
        provider="codex",
        approval_receipt="tty-receipt-1",
        issued_at=NOW,
    )
    session_store.stop_matching_session(
        tmp_path, thread_binding="thread-1", stopped_at=NOW
    )

    with pytest.raises(session_store.SessionStoreError, match="terminal"):
        session_store.build_tty_session_lease(
            tmp_path,
            thread_binding="thread-1",
            provider="codex",
            approval_receipt="tty-receipt-2",
            issued_at=NOW,
        )
    rows = session_store.matching_session_leases(
        tmp_path, thread_binding="thread-1"
    )
    assert len(rows) == 1
    assert rows[0][1]["session_binding"]["session_id"] == original[
        "session_binding"
    ]["session_id"]
    assert rows[0][1]["lifecycle"]["status"] == "stopped"


def test_competing_tty_creation_serializes_to_one_live_lease(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    patch_activation(monkeypatch, tmp_path)

    def create(index: int) -> dict:
        return session_store.build_tty_session_lease(
            tmp_path,
            thread_binding="thread-1",
            provider="codex",
            approval_receipt=f"tty-receipt-{index}",
            issued_at=NOW,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(pool.map(create, (1, 2)))

    assert created[0] == created[1]
    rows = session_store.matching_session_leases(
        tmp_path, thread_binding="thread-1"
    )
    assert len(rows) == 1
    assert rows[0][1]["lifecycle"]["status"] == "live"


def test_different_host_receipt_cannot_rebind_a_live_scope(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    patch_activation(monkeypatch, tmp_path)
    first = session_store.build_host_session_lease(
        tmp_path,
        thread_binding="thread-1",
        provider="codex",
        approval_receipt="host-receipt-1",
        issued_at=NOW,
    )
    with pytest.raises(
        session_store.SessionStoreError, match="differently bound"
    ):
        session_store.build_host_session_lease(
            tmp_path,
            thread_binding="thread-1",
            provider="codex",
            approval_receipt="host-receipt-2",
            issued_at=NOW,
        )
    rows = session_store.matching_session_leases(
        tmp_path, thread_binding="thread-1"
    )
    assert [lease for _path, lease in rows] == [first]


def test_legacy_live_scope_ambiguity_fails_closed(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    patch_activation(monkeypatch, tmp_path)
    workspace_id = session_store._workspace_id(tmp_path)
    for receipt in ("legacy-receipt-1", "legacy-receipt-2"):
        legacy = build_session_lease(
            session_binding=build_session_binding(
                workspace_identity=workspace_id,
                provider="codex",
                thread_binding="thread-1",
                activation_evidence_id="activation-1",
                trust_class="agent_mediated_tty_narrowing",
                approval_receipt=receipt,
            ),
            goal_id="goal-1",
            task_family="family-1",
            activation_mode="governed",
            activation_risk_ceiling="R2",
            allowed_operation_groups=["local_git_commit"],
            goal_digest="1" * 64,
            policy_digest="2" * 64,
            manifest_digest="3" * 64,
            issued_at=NOW,
            expires_at=LATER,
        )
        session_store.write_session_lease(tmp_path, legacy)

    with pytest.raises(
        session_store.SessionStoreError, match="multiple live"
    ):
        session_store.build_tty_session_lease(
            tmp_path,
            thread_binding="thread-1",
            provider="codex",
            approval_receipt="new-receipt",
            issued_at=NOW,
        )
    with pytest.raises(
        session_store.SessionStoreError, match="exactly one"
    ):
        session_store.stop_matching_session(
            tmp_path, thread_binding="thread-1", stopped_at=NOW
        )


def test_session_status_reports_remaining_budget(tmp_path, monkeypatch) -> None:
    (tmp_path / ".git").mkdir()
    patch_activation(monkeypatch, tmp_path)
    created = session_store.build_tty_session_lease(
        tmp_path,
        thread_binding="thread-1",
        provider="codex",
        approval_receipt="tty-receipt",
        issued_at=NOW,
    )
    status = session_store.session_status(
        tmp_path, thread_binding="thread-1"
    )
    assert status["sessions"][0]["session_id"] == created[
        "session_binding"
    ]["session_id"]
    assert status["sessions"][0]["remaining"]["cycles"] == 3


def test_matching_sessions_rejects_symlinked_session_parent(
    tmp_path,
) -> None:
    (tmp_path / ".git").mkdir()
    sessions = tmp_path / ".task" / "authorization" / "sessions"
    sessions.mkdir(parents=True)
    external = tmp_path / "external-session"
    external.mkdir()
    (sessions / "session-attacker").symlink_to(
        external, target_is_directory=True
    )
    with pytest.raises(
        session_store.SessionStoreError, match="must not be a symlink"
    ):
        session_store.matching_session_leases(
            tmp_path, thread_binding="thread-1"
        )


def test_matching_sessions_reads_lease_leaf_without_following_symlink(
    tmp_path,
) -> None:
    (tmp_path / ".git").mkdir()
    parent = (
        tmp_path
        / ".task"
        / "authorization"
        / "sessions"
        / "session-attacker"
    )
    parent.mkdir(parents=True)
    external = tmp_path / "external-lease.json"
    external.write_text("{}\n", encoding="utf-8")
    (parent / "session-lease.json").symlink_to(external)
    with pytest.raises(
        session_store.SessionStoreError, match="non-symlink"
    ):
        session_store.matching_session_leases(
            tmp_path, thread_binding="thread-1"
        )
