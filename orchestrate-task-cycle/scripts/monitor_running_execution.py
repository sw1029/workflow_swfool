#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any


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
        "modified_at": dt.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        "tail": tail,
    }


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


def monitor(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    pid_raw = args.pid if args.pid is not None else first_value(data, "pid", "run.pid", "pid_or_session")
    pid: int | None = None
    try:
        pid = int(pid_raw) if pid_raw is not None and str(pid_raw).isdigit() else None
    except (TypeError, ValueError):
        pid = None
    log_path = args.log_path or first_value(data, "log_path", "run.log_path")
    monitor_command = args.monitor_command or first_value(data, "monitor_command", "run.monitor_command")
    stop_command = args.stop_command or first_value(data, "stop_command", "run.stop_command")
    heartbeat = args.heartbeat or first_value(data, "startup_or_heartbeat_evidence", "heartbeat", "startup_evidence")
    remaining = args.remaining_validation or first_value(data, "remaining_validation", "run.remaining_validation")
    missing = [
        name
        for name, value in (
            ("pid_or_session", pid_raw),
            ("log_path", log_path),
            ("startup_or_heartbeat_evidence", heartbeat),
            ("monitor_command", monitor_command),
            ("stop_command", stop_command),
            ("remaining_validation", remaining),
        )
        if value in (None, "", [])
    ]
    alive = pid_alive(pid)
    status = "running" if alive is True else "not_running" if alive is False else "missing_details"
    if missing:
        status = "missing_details"
    return {
        "checked_at": now_iso(),
        "status": status,
        "pid": pid,
        "pid_alive": alive,
        "log": log_info(str(log_path) if log_path else None),
        "monitor_command": monitor_command,
        "stop_command": stop_command,
        "startup_or_heartbeat_evidence": heartbeat,
        "remaining_validation": remaining,
        "missing_fields": missing,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect long-running execution state without converting it to success.")
    parser.add_argument("--run-json", help="Run result JSON path, JSON string, or '-' for stdin.")
    parser.add_argument("--pid")
    parser.add_argument("--log-path")
    parser.add_argument("--monitor-command")
    parser.add_argument("--stop-command")
    parser.add_argument("--heartbeat")
    parser.add_argument("--remaining-validation")
    args = parser.parse_args(argv)

    output = monitor(load_json(args.run_json), args)
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "missing_details" else 2


if __name__ == "__main__":
    raise SystemExit(main())
