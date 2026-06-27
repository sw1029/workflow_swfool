#!/usr/bin/env python3
"""Write a standardized agent work log entry under .agent_log."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def slugify(value: str, fallback: str = "agent-log") -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9가-힣._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text[:80] or fallback


def git_value(root: Path, args: List[str]) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            text=True,
            capture_output=True,
            timeout=5,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def list_values(items: List[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def paragraph(value: str) -> str:
    return value.strip() or "Not specified"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a .agent_log entry and append index.jsonl.")
    parser.add_argument("--root", default=".", help="Workspace/repository root.")
    parser.add_argument("--title", default="", help="Short entry title.")
    parser.add_argument("--status", default="completed", choices=["completed", "partial", "blocked", "failed", "informational"])
    parser.add_argument("--intent", required=True, help="Task intent.")
    parser.add_argument("--work", required=True, help="Work performed.")
    parser.add_argument("--result", required=True, help="Result.")
    parser.add_argument("--shortcomings", required=True, help="Shortcomings, gaps, or None identified.")
    parser.add_argument("--agent-note", action="append", default=[], help="Normalization agent note. Repeatable.")
    parser.add_argument("--command", action="append", default=[], help="Command or validation run. Repeatable.")
    parser.add_argument("--changed-file", action="append", default=[], help="Changed file path. Repeatable.")
    parser.add_argument("--follow-up", action="append", default=[], help="Follow-up action. Repeatable.")
    parser.add_argument("--tag", action="append", default=[], help="Short tag. Repeatable.")
    parser.add_argument("--actor", default=os.environ.get("USER", "codex"), help="Actor name.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    now = datetime.now().astimezone()
    date = now.strftime("%Y-%m-%d")
    time_part = now.strftime("%H%M%S")
    title = args.title.strip() or args.intent.strip().splitlines()[0][:80] or "Agent work log"
    slug = slugify(title)

    log_dir = root / ".agent_log" / date
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{time_part}-{slug}.md"
    counter = 1
    while path.exists():
        path = log_dir / f"{time_part}-{slug}-{counter}.md"
        counter += 1

    branch = git_value(root, ["branch", "--show-current"])
    commit = git_value(root, ["rev-parse", "--short", "HEAD"])

    rel_path = path.relative_to(root)
    content = f"""# {title}

- Timestamp: {now.isoformat()}
- Status: {args.status}
- Workspace: {root}
- Actor: {args.actor}
- Git branch: {branch or "N/A"}
- Git commit: {commit or "N/A"}

## Task Intent

{paragraph(args.intent)}

## Work Performed

{paragraph(args.work)}

## Result

{paragraph(args.result)}

## Shortcomings

{paragraph(args.shortcomings)}

## Commands / Validation

{list_values(args.command)}

## Changed Files

{list_values(args.changed_file)}

## Agent Notes

{list_values(args.agent_note)}

## Follow-ups

{list_values(args.follow_up)}

## Tags

{list_values(args.tag)}
"""
    path.write_text(content, encoding="utf-8")

    record: Dict[str, Any] = {
        "timestamp": now.isoformat(),
        "status": args.status,
        "title": title,
        "path": str(rel_path),
        "workspace": str(root),
        "actor": args.actor,
        "git_branch": branch or None,
        "git_commit": commit or None,
        "task_intent": args.intent,
        "work_performed": args.work,
        "result": args.result,
        "shortcomings": args.shortcomings,
        "commands": args.command,
        "changed_files": args.changed_file,
        "agent_notes": args.agent_note,
        "follow_ups": args.follow_up,
        "tags": args.tag,
    }
    index_path = root / ".agent_log" / "index.jsonl"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    print(json.dumps({"path": str(path), "index": str(index_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
