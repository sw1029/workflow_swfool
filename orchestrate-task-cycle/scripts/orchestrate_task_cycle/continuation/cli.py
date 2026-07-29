"""User-facing session continuation commands with compact interaction cards."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

from ..ledger.support import read_initialization_metadata
from .actions import validate_action
from .contracts import ContinuationContractError, digest
from .lifecycle import start_session, status_card, stop_session
from .safe_files import scan_session_files
from .service import accept_action, continue_session, recover_session
from .session_envelope import (
    current_session_lease,
    live_session_lease_candidates,
    verify_live_state_lease,
)
from .state import evolve, load_state, state_ref, validate_state, write_state


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(value: str) -> dict[str, Any]:
    raw = sys.stdin.read() if value == "-" else (
        Path(value).read_text(encoding="utf-8")
        if Path(value).is_file()
        else value
    )
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ContinuationContractError("JSON input must be an object")
    return parsed


def _current_cycle(root: Path, requested: str | None) -> tuple[str, str]:
    if requested:
        metadata = read_initialization_metadata(root, requested)
        task_id = str(metadata.get("task_id") or "")
        if not task_id:
            raise ContinuationContractError("cycle initialization lacks task_id")
        return requested, task_id
    cycle_root = root / ".task" / "cycle"
    rows: list[tuple[str, str, str]] = []
    if cycle_root.is_dir():
        for path in cycle_root.glob("*/initialization.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(value, dict) or not value.get("task_id"):
                continue
            rows.append(
                (
                    str(value.get("initialized_at") or ""),
                    path.parent.name,
                    str(value["task_id"]),
                )
            )
    if not rows:
        raise ContinuationContractError("no initialized task cycle was found")
    _created, cycle_id, task_id = sorted(rows)[-1]
    return cycle_id, task_id


def _state_candidates(root: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for _path, payload in scan_session_files(root, "workflow-session.json"):
        try:
            state = validate_state(json.loads(payload))
        except (ValueError, json.JSONDecodeError):
            continue
        values.append(state)
    return values


def _current_state(root: Path) -> dict[str, Any]:
    lease_candidates = live_session_lease_candidates(root)
    live_ids = {
        item[1]["session_binding"]["session_id"] for item in lease_candidates
    }
    states = [
        state
        for state in _state_candidates(root)
        if state["session_id"] in live_ids
    ]
    if not states:
        all_states = _state_candidates(root)
        active = [
            state
            for state in all_states
            if state["status"] not in {"complete", "stopped"}
        ]
        if len(active) == 1:
            states = active
        elif len(all_states) == 1:
            states = all_states
        else:
            states = []
    if len(states) != 1:
        raise ContinuationContractError(
            "exactly one current workflow session is required"
        )
    return load_state(root, states[0]["session_id"])


def _compact(
    state: dict[str, Any],
    action: dict[str, Any] | None = None,
    *,
    emit_action: bool = False,
) -> dict[str, Any]:
    output: dict[str, Any] = {"interaction": status_card(state)}
    if action:
        output["next_action"] = {
            key: action.get(key)
            for key in ("action_id", "actor", "kind", "target", "owner_skill", "reason")
        }
        if emit_action:
            output["internal_action"] = action
    return output


def _refresh_liveness(
    state: dict[str, Any], *, live: bool, at: str
) -> dict[str, Any]:
    """Recheck real boundaries without accepting or replaying an effect."""

    pending = state.get("pending_action") or {}
    boundary_actor = pending.get("actor") in {"user", "external"}
    if (
        live
        and state["status"] == "host_boundary"
        and pending.get("actor") == "agent"
    ):
        # Keep the host-loss marker until the continuation service has
        # recovered the preserved possible effect.
        if state["host_session_live"]:
            return state
        return evolve(
            state,
            at=at,
            host_session_live=True,
        )
    if live and (
        state["status"] == "host_boundary"
        or state["host_session_live"] is False
    ):
        return evolve(
            state,
            at=at,
            status="waiting" if boundary_actor else "active",
            host_session_live=True,
            pending_action=pending or None,
            last_stop_reason=(
                pending.get("reason") if boundary_actor else None
            ),
        )
    if not live and (
        state["host_session_live"]
        or state["last_stop_reason"] != "host_session_not_live"
    ):
        return evolve(
            state,
            at=at,
            host_session_live=False,
            last_stop_reason="host_session_not_live",
        )
    return state


def _refresh_authority_usage(
    root: Path,
    state: dict[str, Any],
    *,
    at: str,
) -> dict[str, Any]:
    """Merge direct session-child usage before issuing another agent action."""

    if state["pending_action"] is not None:
        return state
    from manage_agent_authority.session_store import (
        session_child_grant_count,
    )

    direct_actions = session_child_grant_count(root, state["session_id"])
    if direct_actions <= state["usage"]["agent_actions"]:
        return state
    usage = {
        **state["usage"],
        "agent_actions": direct_actions,
    }
    return evolve(state, at=at, usage=usage)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m orchestrate_task_cycle session"
    )
    commands = parser.add_subparsers(dest="session_command", required=True)
    start = commands.add_parser("start")
    start.add_argument("--root", default=".")
    start.add_argument("--cycle-id")
    start.add_argument("--at")
    advance = commands.add_parser("continue")
    advance.add_argument("--root", default=".")
    advance.add_argument("--at")
    advance.add_argument(
        "--emit-action",
        action="store_true",
        help="include the sealed action for the host dispatch adapter",
    )
    status = commands.add_parser("status")
    status.add_argument("--root", default=".")
    stop = commands.add_parser("stop")
    stop.add_argument("--root", default=".")
    stop.add_argument("--at")
    accept = commands.add_parser("accept-action")
    accept.add_argument("--root", default=".")
    accept.add_argument("--action-id", required=True)
    accept.add_argument("--result", required=True)
    accept.add_argument("--at")
    accept.add_argument(
        "--emit-action",
        action="store_true",
        help="include the next sealed action for the host dispatch adapter",
    )
    recover = commands.add_parser("recover")
    recover.add_argument("--root", default=".")
    recover.add_argument("--at")
    return parser


def _start(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    lease_path, lease, lease_sha = current_session_lease(root)
    lease_binding = {
        "ref": lease_path.relative_to(root).as_posix(),
        "sha256": lease_sha,
    }
    existing_path = root / state_ref(
        lease["session_binding"]["session_id"]
    )
    if existing_path.exists() or existing_path.is_symlink():
        existing = load_state(
            root, lease["session_binding"]["session_id"]
        )
        if existing["session_lease_binding"] != lease_binding:
            raise ContinuationContractError(
                "the session already has state bound to another lease"
            )
        if args.cycle_id and args.cycle_id not in existing["cycle_ids"]:
            raise ContinuationContractError(
                "the session is already bound to a different cycle"
            )
        return _compact(existing)
    cycle_id, task_id = _current_cycle(root, args.cycle_id)
    state = start_session(
        session_lease=lease,
        session_lease_binding=lease_binding,
        cycle_id=cycle_id,
        task_id=task_id,
        created_at=args.at or _now(),
    )
    write_state(root, state)
    return _compact(state)


def _continue(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    from .stage_adapter import StageContinuationAdapter

    original = _current_state(root)
    state = original
    observed_at = args.at or _now()
    thread = os.environ.get("CODEX_THREAD_ID")
    leases = live_session_lease_candidates(root) if thread else []
    lease_live = verify_live_state_lease(
        root, state, leases, at=observed_at
    )
    state = _refresh_liveness(
        state,
        live=lease_live,
        at=observed_at,
    )
    state = _refresh_authority_usage(root, state, at=observed_at)
    adapter = StageContinuationAdapter(
        root,
        session_id=state["session_id"],
        goal_id=state["goal_id"],
        task_family=state["task_family"],
    )
    state, action = continue_session(
        state,
        adapter,
        at=observed_at,
    )
    write_state(
        root,
        state,
        expected_state_sha256=original["state_sha256"],
    )
    return _compact(state, action, emit_action=args.emit_action)


def _accept(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    from .stage_adapter import StageContinuationAdapter

    original = _current_state(root)
    state = original
    observed_at = args.at or _now()
    result = _load_json(args.result)
    prior_result_sha = state["accepted_actions"].get(args.action_id)
    if prior_result_sha is not None:
        if prior_result_sha != digest(result):
            raise ContinuationContractError(
                "accepted action replay changed its result"
            )
        return _compact(
            state,
            state.get("pending_action"),
            emit_action=args.emit_action,
        )
    if not verify_live_state_lease(
        root, state, live_session_lease_candidates(root), at=observed_at
    ):
        raise ContinuationContractError(
            "the host session lease is not live; result acceptance is blocked"
        )
    pending = state.get("pending_action")
    if not isinstance(pending, dict) or pending.get("action_id") != args.action_id:
        raise ContinuationContractError("action-id is not the pending action")
    validate_action(pending)
    adapter = StageContinuationAdapter(
        root,
        session_id=state["session_id"],
        goal_id=state["goal_id"],
        task_family=state["task_family"],
    )
    state, _outcome = accept_action(
        state,
        action=pending,
        result=result,
        adapter=adapter,
        at=observed_at,
    )
    state = _refresh_authority_usage(root, state, at=observed_at)
    state, action = continue_session(state, adapter, at=observed_at)
    write_state(
        root,
        state,
        expected_state_sha256=original["state_sha256"],
    )
    return _compact(state, action, emit_action=args.emit_action)


def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve(strict=True)
    if args.session_command == "start":
        return _start(args, root)
    if args.session_command == "continue":
        return _continue(args, root)
    if args.session_command == "status":
        return _compact(_current_state(root))
    if args.session_command == "stop":
        stopped_at = args.at or _now()
        original = _current_state(root)
        thread = os.environ.get("CODEX_THREAD_ID")
        if thread:
            from manage_agent_authority.session_store import (
                stop_matching_session,
            )

            stop_matching_session(
                root, thread_binding=thread, stopped_at=stopped_at
            )
        state = stop_session(original, at=stopped_at)
        write_state(
            root,
            state,
            expected_state_sha256=original["state_sha256"],
        )
        return _compact(state)
    if args.session_command == "accept-action":
        return _accept(args, root)
    from .stage_adapter import StageContinuationAdapter

    original = _current_state(root)
    if original["status"] == "stopped":
        raise ContinuationContractError(
            "a stopped session cannot be recovered"
        )
    observed_at = args.at or _now()
    if not verify_live_state_lease(
        root, original, live_session_lease_candidates(root), at=observed_at
    ):
        raise ContinuationContractError(
            "the host session lease is not live; recovery is blocked"
        )
    state = original
    state, outcome = recover_session(
        state,
        StageContinuationAdapter(
            root,
            session_id=state["session_id"],
            goal_id=state["goal_id"],
            task_family=state["task_family"],
        ),
        at=observed_at,
    )
    write_state(
        root,
        state,
        expected_state_sha256=original["state_sha256"],
    )
    return {"interaction": status_card(state), "recovery": outcome}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        output = _run(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


__all__ = ("main",)
