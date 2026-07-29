from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from typing import Any

import pytest

from manage_agent_authority.authority_interaction import OPERATION_REGISTRY
from manage_agent_authority.canonical import sha256_file
from manage_agent_authority.session_binding import build_session_binding
from manage_agent_authority.session_binding import session_ref
from manage_agent_authority.session_lease import build_session_lease
from manage_agent_authority.session_store import write_session_lease
from orchestrate_task_cycle import cycle_ledger
from orchestrate_task_cycle.continuation import (
    stage_adapter,
    successor_adapter,
    successor_initialization,
)
from orchestrate_task_cycle.ledger.constants import (
    COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE,
    STAGE_COMPILER_PROTOCOL_VERSION,
    STAGE_PREPARATION_SCHEMA_VERSION,
)
from orchestrate_task_cycle.ledger.support import read_initialization_metadata
from orchestrate_task_cycle.selected_successor_authority_artifacts import load_packet
from orchestrate_task_cycle.selected_successor_execution import (
    execute_selected_successor_bundle,
)
from selected_successor_authority_support import SKILLS_ROOT
from test_selected_successor_authority_preparation import (
    _prepare_authority,
    _prepared,
)


ISSUED_AT = "2026-07-17T09:00:00+09:00"
SETTLED_AT = "2026-07-17T10:04:00+09:00"
SESSION_EXPIRY = "2026-08-17T11:00:00+09:00"


def _binding(root: Path) -> dict[str, Any]:
    return build_session_binding(
        workspace_identity="workspace-successor-proof",
        provider="codex-test",
        thread_binding="thread-successor-proof",
        activation_evidence_id="activation-successor-proof",
        trust_class="platform_host_receipt",
        approval_receipt="host-successor-proof",
    )


def _write_lease(
    root: Path,
    binding: dict[str, Any],
    inputs: dict[str, Any],
    *,
    risk: str,
) -> dict[str, Any]:
    grant_binding = next(iter(inputs["grants"].values()))
    grant = json.loads((root / grant_binding["ref"]).read_text(encoding="utf-8"))
    lease = build_session_lease(
        session_binding=binding,
        goal_id="goal-successor-proof",
        task_family="family-successor-proof",
        activation_mode="governed",
        activation_risk_ceiling=risk,
        allowed_operation_groups=sorted(OPERATION_REGISTRY),
        goal_digest=sha256_file(root / ".agent_goal/goal_architecture.md"),
        policy_digest=grant["policy_snapshot"]["sha256"],
        manifest_digest="f" * 64,
        issued_at=ISSUED_AT,
        expires_at=SESSION_EXPIRY,
    )
    write_session_lease(root, lease)
    return lease


def _settled_successor(
    root: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    *,
    lease_risk: str = "R2",
    initialize_successor: bool = True,
) -> tuple[str, str, dict[str, Any]]:
    binding = _binding(root)
    session_id = binding["session_id"]
    prepared, bundle, inputs = _prepared(
        root, capsys, session_id=session_id
    )
    lease = _write_lease(root, binding, inputs, risk=lease_risk)
    authority = _prepare_authority(root, prepared, inputs)
    _packet_binding, packet = load_packet(root, authority["authority_packet"])
    executed = execute_selected_successor_bundle(
        root,
        bundle_binding=packet["bundle"],
        authority_proofs=packet["authority_proofs"],
        settled_at=SETTLED_AT,
        skills_root=SKILLS_ROOT,
    )
    assert executed["status"] == "complete"
    source_cycles = [
        path.parent.name
        for path in (root / ".task/cycle").glob("*/initialization.json")
    ]
    assert len(source_cycles) == 1
    source_cycle = source_cycles[0]
    if initialize_successor:
        cycle_ledger.init_cycle(
            root,
            "cycle-successor-proof",
            bundle["selected_task_id"],
            "settled selected successor",
        )

    def selected_events(_root: Path, cycle_id: str) -> list[dict[str, Any]]:
        if cycle_id != source_cycle:
            return []
        return [
            {
                "step": "derive",
                "status": "complete",
                "selection_receipt": bundle["source_decision"],
                "next_task_id": bundle["selected_task_id"],
            }
        ]

    monkeypatch.setattr(successor_adapter, "read_events", selected_events)
    return source_cycle, session_id, lease


def test_bridge_requires_exact_session_settlement_before_successor_init(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_cycle, session_id, lease = _settled_successor(
        tmp_path, capsys, monkeypatch
    )

    result = successor_adapter.selected_initialized_successor(
        tmp_path,
        source_cycle,
        session_id=session_id,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        skills_root=SKILLS_ROOT,
    )

    assert result == {
        "outcome": "selected",
        "cycle_id": "cycle-successor-proof",
        "task_id": "task-next",
        "goal_id": lease["goal_id"],
        "task_family": lease["task_family"],
        "risk_envelope_match": True,
    }
    assert successor_initialization.ensure_selected_successor_cycle(
        tmp_path,
        source_cycle,
        session_id=session_id,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        skills_root=SKILLS_ROOT,
    ) == result

    one_lease = next(
        (
            tmp_path
            / ".task/selection_publication/successor_execution_leases/sha256"
        ).glob("*.json")
    )
    one_lease.unlink()
    assert successor_adapter.selected_initialized_successor(
        tmp_path,
        source_cycle,
        session_id=session_id,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        skills_root=SKILLS_ROOT,
    ) is None


def test_bridge_does_not_fabricate_risk_envelope_match(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_cycle, session_id, lease = _settled_successor(
        tmp_path, capsys, monkeypatch, lease_risk="R1"
    )

    assert successor_adapter.selected_initialized_successor(
        tmp_path,
        source_cycle,
        session_id=session_id,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        skills_root=SKILLS_ROOT,
    ) is None


def test_stage_adapter_threads_the_exact_continuation_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, Any] = {}

    def bridge(
        root: Path,
        cycle_id: str,
        **fields: Any,
    ) -> None:
        observed.update({"root": root, "cycle_id": cycle_id, **fields})
        return None

    monkeypatch.setattr(
        stage_adapter, "ensure_selected_successor_cycle", bridge
    )
    adapter = stage_adapter.StageContinuationAdapter(
        tmp_path,
        session_id="session-exact",
        goal_id="goal-exact",
        task_family="family-exact",
    )

    assert adapter.selected_successor("cycle-exact") is None
    assert observed == {
        "root": tmp_path.resolve(),
        "cycle_id": "cycle-exact",
        "session_id": "session-exact",
        "goal_id": "goal-exact",
        "task_family": "family-exact",
    }


def test_ensure_initializes_missing_successor_from_exact_proof(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_cycle, session_id, lease = _settled_successor(
        tmp_path,
        capsys,
        monkeypatch,
        initialize_successor=False,
    )

    result = successor_initialization.ensure_selected_successor_cycle(
        tmp_path,
        source_cycle,
        session_id=session_id,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        skills_root=SKILLS_ROOT,
    )

    assert result is not None
    assert result["cycle_id"].startswith("cycle-successor-")
    assert result["task_id"] == "task-next"
    metadata = read_initialization_metadata(
        tmp_path, result["cycle_id"]
    )
    assert metadata["task_id"] == "task-next"
    assert metadata["reason"].startswith(
        "proof-bound selected successor "
    )
    assert (
        metadata["stage_compiler_protocol_version"]
        == STAGE_COMPILER_PROTOCOL_VERSION
    )
    assert (
        metadata["stage_preparation_schema_version"]
        == STAGE_PREPARATION_SCHEMA_VERSION
    )
    assert (
        metadata["workflow_contract_profile"]
        == COMPILER_FIRST_WORKFLOW_CONTRACT_PROFILE
    )
    assert successor_adapter.selected_initialized_successor(
        tmp_path,
        source_cycle,
        session_id=session_id,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        skills_root=SKILLS_ROOT,
    ) == result


def test_ensure_retry_and_concurrent_calls_converge_on_one_cycle(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_cycle, session_id, lease = _settled_successor(
        tmp_path,
        capsys,
        monkeypatch,
        initialize_successor=False,
    )

    def ensure() -> dict[str, Any] | None:
        return successor_initialization.ensure_selected_successor_cycle(
            tmp_path,
            source_cycle,
            session_id=session_id,
            goal_id=lease["goal_id"],
            task_family=lease["task_family"],
            skills_root=SKILLS_ROOT,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: ensure(), range(2)))

    assert results[0] is not None
    assert results == [results[0], results[0]]
    cycle_id = results[0]["cycle_id"]
    before = (
        tmp_path / ".task" / "cycle" / cycle_id / "initialization.json"
    ).read_bytes()
    assert ensure() == results[0]
    after = (
        tmp_path / ".task" / "cycle" / cycle_id / "initialization.json"
    ).read_bytes()
    assert after == before
    successor_cycles = [
        path.parent.name
        for path in (tmp_path / ".task/cycle").glob(
            "*/initialization.json"
        )
        if path.parent.name != source_cycle
    ]
    assert successor_cycles == [cycle_id]


def test_ensure_invalid_proof_creates_no_successor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_cycle, session_id, lease = _settled_successor(
        tmp_path,
        capsys,
        monkeypatch,
        initialize_successor=False,
    )
    execution_lease = next(
        (
            tmp_path
            / ".task/selection_publication/successor_execution_leases/sha256"
        ).glob("*.json")
    )
    execution_lease.unlink()

    assert successor_initialization.ensure_selected_successor_cycle(
        tmp_path,
        source_cycle,
        session_id=session_id,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        skills_root=SKILLS_ROOT,
    ) is None
    assert [
        path.parent.name
        for path in (tmp_path / ".task/cycle").glob(
            "*/initialization.json"
        )
    ] == [source_cycle]


def test_ensure_stale_session_proof_creates_no_successor(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_cycle, session_id, lease = _settled_successor(
        tmp_path,
        capsys,
        monkeypatch,
        initialize_successor=False,
    )
    real_resolve = successor_initialization._resolve
    calls = 0

    def stale_after_first(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        proof = real_resolve(*args, **kwargs)
        if calls == 1:
            path = tmp_path / session_ref(session_id)
            path.write_text(
                path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
        return proof

    monkeypatch.setattr(
        successor_initialization, "_resolve", stale_after_first
    )
    assert successor_initialization.ensure_selected_successor_cycle(
        tmp_path,
        source_cycle,
        session_id=session_id,
        goal_id=lease["goal_id"],
        task_family=lease["task_family"],
        skills_root=SKILLS_ROOT,
    ) is None
    assert calls == 2
    assert [
        path.parent.name
        for path in (tmp_path / ".task/cycle").glob(
            "*/initialization.json"
        )
    ] == [source_cycle]
