#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


VALID_PROFILES = {"current_only", "affected_chain", "full_chain"}
VALIDATION_SET_PROFILES = {"none", "plan", "build", "refresh", "consume", "seal"}


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    if path_value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    stripped = path_value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    path = Path(path_value)
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw) if raw.strip() else {}
    except OSError:
        pass
    return json.loads(stripped)


def choose_profile(surfaces: list[str], requested: str | None, issue_closure: bool, live_dispatch: bool) -> tuple[str, str]:
    if requested:
        return requested, "explicit_request"
    surface_set = set(surfaces)
    if issue_closure or live_dispatch:
        return "full_chain", "issue_closure_or_live_dispatch"
    if surface_set & {"runtime_config"}:
        return "full_chain", "runtime_or_environment_surface_changed"
    if surface_set & {"schema", "contract", "validation_set"}:
        return "affected_chain", "schema_contract_or_validation_set_surface_changed"
    if surface_set & {"source", "tests"}:
        return "current_only", "current_task_source_or_test_surface"
    if surface_set & {"task_state", "issue", "docs", "goal_or_advice"}:
        return "current_only", "workflow_or_documentation_surface"
    return "current_only", "no_changed_surface_requires_escalation"


def build_manifest(surface_data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    surfaces = [str(item) for item in surface_data.get("surfaces") or []]
    profile, reason = choose_profile(surfaces, args.requested_profile, args.issue_closure, args.live_dispatch)
    commands = args.command or []
    return {
        "created_at": now_iso(),
        "validation_profile": profile,
        "validation_set_profile": args.validation_set_profile,
        "changed_surfaces": surfaces,
        "changed_files": surface_data.get("changed_files") or [],
        "required_commands": commands,
        "reused_prerequisites": args.reused_prerequisite or [],
        "escalation_reason": args.escalation_reason or reason,
        "manifest_type": "validation_scope",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a validation-scope manifest.")
    parser.add_argument("--changed-surface-json", required=True, help="Output from changed_surface.py, or '-' for stdin.")
    parser.add_argument("--requested-profile", choices=sorted(VALID_PROFILES))
    parser.add_argument("--validation-set-profile", choices=sorted(VALIDATION_SET_PROFILES), default="none")
    parser.add_argument("--command", action="append", default=[])
    parser.add_argument("--reused-prerequisite", action="append", default=[])
    parser.add_argument("--escalation-reason")
    parser.add_argument("--issue-closure", action="store_true")
    parser.add_argument("--live-dispatch", action="store_true")
    parser.add_argument("--write", help="Optional path to write the manifest JSON.")
    args = parser.parse_args(argv)

    manifest = build_manifest(load_json(args.changed_surface_json), args)
    if args.write:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest["path"] = str(path)
    json.dump(manifest, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
