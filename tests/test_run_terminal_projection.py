from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from run_task_code_and_log import terminal_projection as terminal_projection_module
from run_task_code_and_log.terminal_projection import (
    RunTerminalProjectionError,
    build_run_terminal_projection,
    publish_run_terminal_projection,
    reopen_run_terminal_projection,
    validate_run_terminal_projection,
)


def evidence(
    root: Path | None,
    ref: str,
    *,
    marker: str = "evidence",
) -> dict[str, str]:
    if root is None:
        return {"ref": ref, "sha256": "a" * 64}
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = f"{marker}\n".encode()
    path.write_bytes(payload)
    return {"ref": ref, "sha256": hashlib.sha256(payload).hexdigest()}


def artifact(
    identifier: str,
    safety: str = "safe",
    *,
    root: Path | None = None,
) -> dict:
    return {
        "artifact_id": identifier,
        "binding": evidence(
            root, f"var/{identifier}.json", marker=identifier
        ),
        "safety_status": safety,
    }


def succeeded_projection(root: Path | None = None) -> dict:
    return build_run_terminal_projection(
        cycle_id="cycle-1",
        run_id="run-1",
        status="succeeded",
        monitor={
            "status": "terminal",
            "monitor_command_id": "event-run-1",
            "stop_command_id": None,
        },
        harvest={
            "status": "completed",
            "evidence_binding": evidence(
                root, "var/harvest.json", marker="harvest"
            ),
        },
        safe_surviving_artifacts=[],
        discarded_artifacts=[],
        failure=None,
        next_action="complete",
        retry_policy={"automatic_retry": False},
    )


def test_running_projection_requires_monitor_and_pending_harvest() -> None:
    value = build_run_terminal_projection(
        cycle_id="cycle-1",
        run_id="run-1",
        status="running",
        monitor={
            "status": "pending",
            "monitor_command_id": "monitor-1",
            "stop_command_id": "stop-1",
        },
        harvest={"status": "pending", "evidence_binding": None},
        safe_surviving_artifacts=[],
        discarded_artifacts=[],
        failure=None,
        next_action="monitor",
        retry_policy={"automatic_retry": False},
    )
    assert value["terminal"] is False
    assert validate_run_terminal_projection(value) == value


def test_succeeded_and_failed_closed_are_distinct_terminal_states() -> None:
    succeeded = build_run_terminal_projection(
        cycle_id="cycle-1",
        run_id="run-1",
        status="succeeded",
        monitor={
            "status": "terminal",
            "monitor_command_id": "event-run-1",
            "stop_command_id": None,
        },
        harvest={
            "status": "completed",
            "evidence_binding": {"ref": "var/harvest.json", "sha256": "b" * 64},
        },
        safe_surviving_artifacts=[artifact("candidate")],
        discarded_artifacts=[],
        failure=None,
        next_action="complete",
        retry_policy={"automatic_retry": False},
    )
    failed = build_run_terminal_projection(
        cycle_id="cycle-1",
        run_id="run-2",
        status="failed_closed",
        monitor={
            "status": "terminal",
            "monitor_command_id": "event-run-2",
            "stop_command_id": None,
        },
        harvest={"status": "unavailable", "evidence_binding": None},
        safe_surviving_artifacts=[artifact("log")],
        discarded_artifacts=[artifact("unsafe", "unsafe")],
        failure={
            "reason": "safety_gate",
            "evidence_binding": {"ref": "var/autopsy.json", "sha256": "c" * 64},
        },
        next_action="review",
        retry_policy={"automatic_retry": False},
    )
    assert succeeded["terminal"] is True
    assert failed["terminal"] is True
    assert failed["retry_policy"]["automatic_retry"] is False


def test_succeeded_requires_observation_and_harvest_evidence() -> None:
    fields = {
        "cycle_id": "cycle-1",
        "run_id": "run-1",
        "status": "succeeded",
        "monitor": {
            "status": "terminal",
            "monitor_command_id": None,
            "stop_command_id": None,
        },
        "harvest": {"status": "not_required", "evidence_binding": None},
        "safe_surviving_artifacts": [],
        "discarded_artifacts": [],
        "failure": None,
        "next_action": "complete",
        "retry_policy": {"automatic_retry": False},
    }
    with pytest.raises(RunTerminalProjectionError, match="inconsistent"):
        build_run_terminal_projection(**fields)


def test_failed_closed_rejects_retry_and_unsafe_survivors() -> None:
    fields = {
        "cycle_id": "cycle-1",
        "run_id": "run-2",
        "status": "failed_closed",
        "monitor": {
            "status": "terminal",
            "monitor_command_id": "event-run-2",
            "stop_command_id": None,
        },
        "harvest": {"status": "required", "evidence_binding": None},
        "safe_surviving_artifacts": [],
        "discarded_artifacts": [],
        "failure": {
            "reason": "safety_gate",
            "evidence_binding": {"ref": "var/autopsy.json", "sha256": "c" * 64},
        },
        "next_action": "review",
        "retry_policy": {"automatic_retry": True},
    }
    with pytest.raises(RunTerminalProjectionError, match="unsafe"):
        build_run_terminal_projection(**fields)
    fields["retry_policy"]["automatic_retry"] = False
    fields["safe_surviving_artifacts"] = [artifact("unsafe", "unknown")]
    with pytest.raises(RunTerminalProjectionError, match="only safe"):
        build_run_terminal_projection(**fields)


def test_projection_digest_and_disjoint_artifacts_are_enforced() -> None:
    value = build_run_terminal_projection(
        cycle_id="cycle-1",
        run_id="run-1",
        status="succeeded",
        monitor={
            "status": "terminal",
            "monitor_command_id": "event-run-1",
            "stop_command_id": None,
        },
        harvest={
            "status": "completed",
            "evidence_binding": evidence(None, "var/harvest.json"),
        },
        safe_surviving_artifacts=[artifact("same")],
        discarded_artifacts=[],
        failure=None,
        next_action="complete",
        retry_policy={"automatic_retry": False},
    )
    tampered = deepcopy(value)
    tampered["run_id"] = "run-other"
    with pytest.raises(RunTerminalProjectionError, match="digest"):
        validate_run_terminal_projection(tampered)
    with pytest.raises(RunTerminalProjectionError, match="overlap"):
        build_run_terminal_projection(
            cycle_id="cycle-1",
            run_id="run-1",
            status="succeeded",
            monitor={
                "status": "terminal",
                "monitor_command_id": "event-run-1",
                "stop_command_id": None,
            },
            harvest={
                "status": "completed",
                "evidence_binding": evidence(None, "var/harvest.json"),
            },
            safe_surviving_artifacts=[artifact("same")],
            discarded_artifacts=[artifact("same", "unsafe")],
            failure=None,
            next_action="complete",
            retry_policy={"automatic_retry": False},
        )


def test_terminal_projection_publication_is_canonical_and_idempotent(
    tmp_path,
) -> None:
    value = succeeded_projection(tmp_path)
    first = publish_run_terminal_projection(tmp_path, value)
    second = publish_run_terminal_projection(tmp_path, value)
    assert first["created"] is True
    assert second["created"] is False
    assert first["binding"] == second["binding"]
    assert (tmp_path / first["binding"]["ref"]).is_file()


def test_terminal_projection_reopen_rejects_nonproducer_or_missing_cas(
    tmp_path,
) -> None:
    value = succeeded_projection(tmp_path)
    published = publish_run_terminal_projection(tmp_path, value)
    assert reopen_run_terminal_projection(
        tmp_path,
        value,
        published["binding"],
        expected_cycle_id="cycle-1",
    )["projection"] == value

    with pytest.raises(RunTerminalProjectionError, match="producer CAS"):
        reopen_run_terminal_projection(
            tmp_path,
            value,
            {"ref": "var/forged.json", "sha256": published["binding"]["sha256"]},
            expected_cycle_id="cycle-1",
        )
    with pytest.raises(RunTerminalProjectionError, match="another cycle"):
        reopen_run_terminal_projection(
            tmp_path,
            value,
            published["binding"],
            expected_cycle_id="cycle-2",
        )
    (tmp_path / published["binding"]["ref"]).unlink()
    with pytest.raises(RunTerminalProjectionError, match="unavailable"):
        reopen_run_terminal_projection(
            tmp_path,
            value,
            published["binding"],
            expected_cycle_id="cycle-1",
        )


def test_reopen_rejects_changed_claimed_artifact(tmp_path: Path) -> None:
    candidate = artifact("candidate", root=tmp_path)
    value = build_run_terminal_projection(
        cycle_id="cycle-1",
        run_id="run-1",
        status="succeeded",
        monitor={
            "status": "terminal",
            "monitor_command_id": "event-run-1",
            "stop_command_id": None,
        },
        harvest={
            "status": "completed",
            "evidence_binding": evidence(
                tmp_path, "var/harvest.json", marker="harvest"
            ),
        },
        safe_surviving_artifacts=[candidate],
        discarded_artifacts=[],
        failure=None,
        next_action="complete",
        retry_policy={"automatic_retry": False},
    )
    published = publish_run_terminal_projection(tmp_path, value)
    (tmp_path / candidate["binding"]["ref"]).write_text(
        "changed\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="digest"):
        reopen_run_terminal_projection(
            tmp_path,
            value,
            published["binding"],
            expected_cycle_id="cycle-1",
        )


def test_concurrent_identical_projection_publication_reuses_one_cas_object(
    tmp_path,
) -> None:
    value = succeeded_projection(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda _index: publish_run_terminal_projection(tmp_path, value),
                range(16),
            )
        )
    assert sum(result["created"] is True for result in results) == 1
    assert len(
        {result["binding"]["sha256"] for result in results}
    ) == 1


def test_new_projection_publication_fsyncs_its_cas_directory(
    tmp_path,
    monkeypatch,
) -> None:
    value = succeeded_projection(tmp_path)
    fsynced = []
    monkeypatch.setattr(
        terminal_projection_module,
        "_fsync_directory",
        lambda path: fsynced.append(path),
    )
    publish_run_terminal_projection(tmp_path, value)
    assert fsynced == [
        tmp_path / ".agent_log" / "run-terminal-projections"
    ]
