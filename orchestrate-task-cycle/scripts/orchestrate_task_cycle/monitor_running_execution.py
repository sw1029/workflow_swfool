#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .result_contract.cycle_reachability import assess_launch_contract


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    if path_value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    path = Path(path_value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(path_value)


def pid_alive(pid: int | None) -> bool | None:
    if pid is None:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def log_info(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {"exists": False}
    path = Path(path_value)
    if not path.is_file():
        return {"path": path_value, "exists": False}
    stat = path.stat()
    tail = ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
        tail = "\n".join(data.splitlines()[-8:])
    except OSError:
        pass
    return {
        "path": path_value,
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_at": dt.datetime.fromtimestamp(stat.st_mtime)
        .astimezone()
        .isoformat(timespec="seconds"),
        "tail": tail,
    }


def path_exists(path_value: str | None) -> bool:
    return bool(path_value and Path(path_value).exists())


def tmux_session_alive(session: str | None) -> bool | None:
    if not session:
        return None
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return None
    return result.returncode == 0


def first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
        current: Any = data
        ok = True
        for part in key.split("."):
            if not isinstance(current, dict) or part not in current:
                ok = False
                break
            current = current[part]
        if ok and current not in (None, ""):
            return current
    return None


def list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _monitor_inputs(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    pid_raw = (
        args.pid
        if args.pid is not None
        else first_value(data, "pid", "run.pid", "pid_or_session")
    )
    pid: int | None = None
    try:
        pid = int(pid_raw) if pid_raw is not None and str(pid_raw).isdigit() else None
    except (TypeError, ValueError):
        pid = None
    log_path = args.log_path or first_value(data, "log_path", "run.log_path")
    command_argv = args.command_arg or first_value(
        data, "command_argv", "run.command_argv"
    )
    workdir = args.workdir or first_value(
        data, "workdir", "cwd", "run.workdir", "run.cwd"
    )
    monitor_command = args.monitor_command or first_value(
        data, "monitor_command", "run.monitor_command"
    )
    stop_command = args.stop_command or first_value(
        data, "stop_command", "run.stop_command"
    )
    heartbeat = args.heartbeat or first_value(
        data, "startup_or_heartbeat_evidence", "heartbeat", "startup_evidence"
    )
    remaining = args.remaining_validation or first_value(
        data, "remaining_validation", "run.remaining_validation"
    )
    run_id = args.run_id or first_value(data, "run_id", "run.run_id")
    owner_task_id = args.task_id or first_value(
        data, "owner_task_id", "task_id", "run.owner_task_id"
    )
    launch_cycle_id = args.launch_cycle_id or first_value(
        data, "launch_cycle_id", "cycle_id", "run.launch_cycle_id"
    )
    output_dir = args.output_dir or first_value(data, "output_dir", "run.output_dir")
    expected_completion_signal = args.expected_completion_signal or first_value(
        data,
        "expected_completion_signal",
        "run.expected_completion_signal",
    )
    tmux_session = args.tmux_session or first_value(
        data, "tmux_session", "run.tmux_session"
    )
    tmux_window = args.tmux_window or first_value(
        data, "tmux_window", "run.tmux_window"
    )
    tmux_pane = args.tmux_pane or first_value(data, "tmux_pane", "run.tmux_pane")
    expected_completion_paths = list_value(
        args.expected_completion_path
        or first_value(
            data,
            "expected_completion_artifacts",
            "expected_completion_paths",
            "run.expected_completion_artifacts",
        )
    )
    return {
        "pid_raw": pid_raw,
        "pid": pid,
        "log_path": log_path,
        "command_argv": command_argv,
        "workdir": workdir,
        "monitor_command": monitor_command,
        "stop_command": stop_command,
        "heartbeat": heartbeat,
        "remaining": remaining,
        "run_id": run_id,
        "owner_task_id": owner_task_id,
        "launch_cycle_id": launch_cycle_id,
        "output_dir": output_dir,
        "expected_completion_signal": expected_completion_signal,
        "tmux_session": tmux_session,
        "tmux_window": tmux_window,
        "tmux_pane": tmux_pane,
        "expected_completion_paths": expected_completion_paths,
        "long_run": args.long_run_branch
        or bool(first_value(data, "long_run_branch", "run.long_run_branch")),
        "long_run_role": args.long_run_role
        or first_value(data, "long_run_role", "run.long_run_role")
        or "monitor",
    }


def _reachability_transport(data: dict[str, Any], run_id: object) -> dict[str, Any]:
    aliases = {
        "cycle_reachability_gate": (
            "cycle_reachability_gate",
            "run.cycle_reachability_gate",
            "monitor_result.cycle_reachability_gate",
        ),
        "residual_acceptance": (
            "residual_acceptance",
            "run.residual_acceptance",
            "monitor_result.residual_acceptance",
        ),
        "harvest_validation_plan": (
            "harvest_validation_plan",
            "run.harvest_validation_plan",
            "monitor_result.harvest_validation_plan",
        ),
        "harvest_validation_receipt": (
            "harvest_validation_receipt",
            "run.harvest_validation_receipt",
            "monitor_result.harvest_validation_receipt",
        ),
        "recomputed_cycle_reachability_gate": (
            "recomputed_cycle_reachability_gate",
            "run.recomputed_cycle_reachability_gate",
            "monitor_result.recomputed_cycle_reachability_gate",
        ),
    }
    return {
        "run_id": run_id,
        "unreachable_within_cycle": first_value(
            data,
            "unreachable_within_cycle",
            "run.unreachable_within_cycle",
            "monitor_result.unreachable_within_cycle",
        ),
        **{field: first_value(data, *paths) for field, paths in aliases.items()},
    }


def _missing_monitor_fields(
    inputs: dict[str, Any], transport: dict[str, Any]
) -> list[str]:
    missing = [
        name
        for name, value in (
            ("pid_or_session", inputs["pid_raw"] or inputs["tmux_session"]),
            ("log_path", inputs["log_path"]),
            ("startup_or_heartbeat_evidence", inputs["heartbeat"]),
            ("monitor_command", inputs["monitor_command"]),
            ("stop_command", inputs["stop_command"]),
            ("remaining_validation", inputs["remaining"]),
        )
        if value in (None, "", [])
    ]
    if inputs["long_run"]:
        for name, value in (
            ("run_id", inputs["run_id"]),
            ("owner_task_id", inputs["owner_task_id"]),
            ("launch_cycle_id", inputs["launch_cycle_id"]),
            ("command_argv", inputs["command_argv"]),
            ("workdir", inputs["workdir"]),
            ("output_dir", inputs["output_dir"]),
            ("expected_completion_signal", inputs["expected_completion_signal"]),
            ("expected_completion_artifacts", inputs["expected_completion_paths"]),
        ):
            if value in (None, "", []):
                missing.append(name)
    reachability_assessment = assess_launch_contract(transport)
    if reachability_assessment.applicable:
        missing.extend(
            f"cycle_reachability:{issue}" for issue in reachability_assessment.issues
        )
    return missing


def _monitor_status(
    *,
    alive: bool | None,
    tmux_alive: bool | None,
    completion_seen: bool,
    long_run: bool,
    missing: list[str],
) -> str:
    if completion_seen:
        status = "completed_pending_validation"
    elif alive is True or tmux_alive is True:
        status = "running"
    elif alive is False or tmux_alive is False:
        status = "stale" if long_run else "not_running"
    else:
        status = "missing_details"
    if missing:
        status = "missing_details"
    return status


def monitor(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    inputs = _monitor_inputs(data, args)
    transport = _reachability_transport(data, inputs["run_id"])
    missing = _missing_monitor_fields(inputs, transport)
    alive = pid_alive(inputs["pid"])
    tmux_session = inputs["tmux_session"]
    tmux_alive = tmux_session_alive(str(tmux_session) if tmux_session else None)
    completion_artifacts = [
        {"path": path, "exists": path_exists(path)}
        for path in inputs["expected_completion_paths"]
    ]
    completion_seen = bool(
        completion_artifacts and all(item["exists"] for item in completion_artifacts)
    )
    status = _monitor_status(
        alive=alive,
        tmux_alive=tmux_alive,
        completion_seen=completion_seen,
        long_run=inputs["long_run"],
        missing=missing,
    )
    return {
        "checked_at": now_iso(),
        "status": status,
        "execution_status": status,
        "event_kind": args.event_kind,
        "long_run_branch": inputs["long_run"],
        "long_run_role": inputs["long_run_role"],
        "run_id": inputs["run_id"],
        "owner_task_id": inputs["owner_task_id"],
        "launch_cycle_id": inputs["launch_cycle_id"],
        "command_argv": inputs["command_argv"],
        "workdir": inputs["workdir"],
        "pid": inputs["pid"],
        "pid_alive": alive,
        "tmux_session": tmux_session,
        "tmux_window": inputs["tmux_window"],
        "tmux_pane": inputs["tmux_pane"],
        "tmux_session_alive": tmux_alive,
        "output_dir": inputs["output_dir"],
        "log": log_info(str(inputs["log_path"]) if inputs["log_path"] else None),
        "log_path": inputs["log_path"],
        "monitor_command": inputs["monitor_command"],
        "stop_command": inputs["stop_command"],
        "startup_or_heartbeat_evidence": inputs["heartbeat"],
        "remaining_validation": inputs["remaining"],
        "expected_completion_signal": inputs["expected_completion_signal"],
        "expected_completion_artifacts": inputs["expected_completion_paths"],
        "completion_artifacts": completion_artifacts,
        **{key: value for key, value in transport.items() if key != "run_id"},
        "missing_fields": missing,
    }


def append_ledger(root: Path, cycle_id: str, event: dict[str, Any]) -> dict[str, Any]:
    from .cycle_ledger import append_event
    from .ledger.compiled_events import append_compiled_stage_observation
    from .ledger.semantic_seeds import make_stage_observation_seed
    from .ledger.support import read_initialization_metadata
    from .ledger.workflow_contract import workflow_contract_state

    metadata = read_initialization_metadata(root, cycle_id)
    state = workflow_contract_state(metadata)
    if state == "protocol_v1_unchanged":
        return append_event(root, cycle_id, event)
    if state != "enforced":
        raise ValueError(
            "historical unmarked protocol-v2 cycles are read-only; "
            "initialize a new compiler-first cycle"
        )
    semantic = dict(event)
    semantic["observation_kind"] = semantic.pop(
        "event_kind", "long_run_monitor"
    )
    for field in (
        "cycle_id",
        "event_id",
        "format_version",
        "step",
        "status",
        "created_at",
        "producer_kind",
        "request_fingerprint",
        "ledger_sequence",
    ):
        semantic.pop(field, None)
    return append_compiled_stage_observation(
        root, cycle_id, make_stage_observation_seed(semantic)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect long-running execution state without converting it to success."
    )
    parser.add_argument(
        "--run-json", help="Run result JSON path, JSON string, or '-' for stdin."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id")
    parser.add_argument("--task-id")
    parser.add_argument("--run-id")
    parser.add_argument("--launch-cycle-id")
    parser.add_argument("--long-run-branch", action="store_true")
    parser.add_argument(
        "--long-run-role", choices=("launch", "monitor", "harvest", "finalize")
    )
    parser.add_argument("--event-kind", default="long_run_monitor")
    parser.add_argument("--pid")
    parser.add_argument("--tmux-session")
    parser.add_argument("--tmux-window")
    parser.add_argument("--tmux-pane")
    parser.add_argument("--command-arg", action="append")
    parser.add_argument("--workdir")
    parser.add_argument("--log-path")
    parser.add_argument("--output-dir")
    parser.add_argument("--expected-completion-signal")
    parser.add_argument("--expected-completion-path", action="append")
    parser.add_argument("--monitor-command")
    parser.add_argument("--stop-command")
    parser.add_argument("--heartbeat")
    parser.add_argument("--remaining-validation")
    parser.add_argument("--append-ledger", action="store_true")
    args = parser.parse_args(argv)

    output = monitor(load_json(args.run_json), args)
    if args.append_ledger:
        if not args.cycle_id:
            raise SystemExit("--append-ledger requires --cycle-id")
        event = {
            "step": "run",
            "status": "partial",
            "source_status": output["status"],
            "execution_status": output["status"],
            "event_kind": args.event_kind,
            "long_run_branch": output["long_run_branch"],
            "long_run_role": output["long_run_role"],
            "task_id": args.task_id or output.get("owner_task_id"),
            "run_id": output.get("run_id"),
            "command_argv": output.get("command_argv"),
            "workdir": output.get("workdir"),
            "output_dir": output.get("output_dir"),
            "log_path": output.get("log_path"),
            "startup_or_heartbeat_evidence": output.get(
                "startup_or_heartbeat_evidence"
            ),
            "monitor_command": output.get("monitor_command"),
            "stop_command": output.get("stop_command"),
            "remaining_validation": output.get("remaining_validation"),
            "expected_completion_signal": output.get("expected_completion_signal"),
            "expected_completion_artifacts": output.get(
                "expected_completion_artifacts"
            ),
            "cycle_reachability_gate": output.get("cycle_reachability_gate"),
            "unreachable_within_cycle": output.get("unreachable_within_cycle"),
            "residual_acceptance": output.get("residual_acceptance"),
            "harvest_validation_plan": output.get("harvest_validation_plan"),
            "harvest_validation_receipt": output.get("harvest_validation_receipt"),
            "recomputed_cycle_reachability_gate": output.get(
                "recomputed_cycle_reachability_gate"
            ),
            "reason": "long-running execution monitor event recorded without success promotion",
            "artifacts": [
                item["path"]
                for item in output.get("completion_artifacts", [])
                if item.get("exists")
            ],
            "blockers": output.get("missing_fields") or [],
            "monitor_result": output,
        }
        output["ledger_append"] = append_ledger(
            Path(args.root).resolve(), args.cycle_id, event
        )
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "missing_details" else 2


if __name__ == "__main__":
    raise SystemExit(main())
