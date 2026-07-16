#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


VALID_TYPES = {"cli", "api", "workflow_artifact", "schema_contract", "dashboard", "report", "none"}
PROGRESS_KINDS = {"goal_productive", "governance_only"}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# Visible Delta: {data['cycle_id']}",
        "",
        f"- task_id: {data.get('task_id') or 'unknown'}",
        f"- not_validation_evidence: {str(data['not_validation_evidence']).lower()}",
        f"- summary: {data.get('summary') or 'none'}",
        "",
        "## Delta Types",
    ]
    lines.extend(f"- {item}" for item in data.get("delta_types") or ["none"])
    for title, key in (("Changed Files", "changed_files"), ("Artifacts", "artifacts")):
        lines.extend(["", f"## {title}"])
        values = data.get(key) or []
        lines.extend([f"- {item}" for item in values] or ["- 없음"])
    if data.get("before"):
        lines.extend(["", "## Before", str(data["before"])])
    if data.get("after"):
        lines.extend(["", "## After", str(data["after"])])
    return "\n".join(lines).rstrip() + "\n"


def bounded_path(boundary: Path, path: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(boundary.resolve())
    except ValueError as exc:
        raise SystemExit(f"{label} must stay inside its allowed directory, including through symlinks") from exc
    return resolved


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build(args: argparse.Namespace) -> dict[str, Any]:
    if not ID_PATTERN.fullmatch(str(args.cycle_id or "")):
        raise SystemExit("cycle_id must be one path-safe token of at most 128 characters")
    if not str(args.task_id or "").strip():
        raise SystemExit("task_id must be non-empty")
    delta_types = sorted(set(args.delta_type or ["none"]))
    invalid = sorted(set(delta_types) - VALID_TYPES)
    if invalid:
        raise SystemExit(f"invalid delta type(s): {', '.join(invalid)}")
    effective_progress_kind = args.effective_progress_kind
    if effective_progress_kind and effective_progress_kind not in PROGRESS_KINDS:
        raise SystemExit(f"invalid effective progress kind: {effective_progress_kind}")
    produced_domain_delta = None if args.produced_domain_delta is None else args.produced_domain_delta == "true"
    metadata_only = None if args.metadata_only is None else args.metadata_only == "true"
    return {
        "format_version": 1,
        "step": "visible_increment",
        "status": "recorded",
        "created_at": now_iso(),
        "cycle_id": args.cycle_id,
        "task_id": args.task_id,
        "summary": args.summary or "",
        "delta_types": delta_types,
        "before": args.before,
        "after": args.after,
        "changed_files": args.changed_file or [],
        "artifacts": args.artifact or [],
        "output_delta_status": args.output_delta_status,
        "produced_domain_delta": produced_domain_delta,
        "metadata_only": metadata_only,
        "effective_progress_kind": effective_progress_kind,
        "not_validation_evidence": True,
        "blockers": [],
        "evidence_paths": ["stdout:visible_increment"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create visible increment artifacts that cannot substitute for validation evidence.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--summary")
    parser.add_argument("--delta-type", action="append", choices=sorted(VALID_TYPES), default=[])
    parser.add_argument("--before")
    parser.add_argument("--after")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--output-delta-status")
    parser.add_argument("--produced-domain-delta", choices=["true", "false"])
    parser.add_argument("--metadata-only", choices=["true", "false"])
    parser.add_argument("--effective-progress-kind", choices=sorted(PROGRESS_KINDS))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    data = build(args)
    if args.write:
        out_dir = bounded_path(root, root / ".task" / "delta", "visible-increment output directory")
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = bounded_path(out_dir, out_dir / f"{args.cycle_id}-visible-delta.json", "visible-increment JSON path")
        md_path = bounded_path(out_dir, out_dir / f"{args.cycle_id}-visible-delta.md", "visible-increment Markdown path")
        data["json_path"] = rel_path(root, json_path)
        data["markdown_path"] = rel_path(root, md_path)
        data["evidence_paths"] = [data["json_path"], data["markdown_path"]]
        atomic_write(json_path, (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        atomic_write(md_path, render_markdown(data).encode("utf-8"))
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
