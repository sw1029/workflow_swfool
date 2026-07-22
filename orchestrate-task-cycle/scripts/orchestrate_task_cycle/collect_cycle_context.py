#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from record_agent_work_log.integrity import inspect_agent_log_store

from .cycle_ledger import read_current_expanded
from .result_contract.session_audit import collect_session_audit_directory
from .selection_publication import publication_status
from .task_pack.context_projection import collect_task_pack_projection
from .context_support import (
    classify_text_status,
    count_jsonl_lines,
    extract_used_goal_truth_from_value,
    file_info,
    files_with_suffixes,
    latest_cycle_dirs,
    limited_files,
    now_iso,
    read_jsonl_file,
)


GT_FILES = [
    "final_goal.md",
    "conventions.md",
    "goal_architecture.md",
    "goal_theory.md",
    "goal_schema_contract.md",
    "agent_authority.md",
]


def collect_cycle_state(
    root: Path,
    max_files: int,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    dirs = latest_cycle_dirs(root, max_files)
    requested = root / ".task" / "cycle" / str(cycle_id) if cycle_id else None
    latest = requested or (dirs[0] if dirs else root / ".task" / "cycle" / "none")
    events = (
        read_jsonl_file(latest / "stage.jsonl", limit=max_files)
        if latest.is_dir()
        else []
    )
    current = (
        read_current_expanded(root, latest.name)
        if latest.is_dir() and (latest / "current_stage.json").is_file()
        else None
    )
    packets = (
        sorted((latest / "packets").glob("*")) if (latest / "packets").is_dir() else []
    )
    used_goal_truth = sorted(
        set(
            extract_used_goal_truth_from_value(events)
            + extract_used_goal_truth_from_value(current)
        )
    )
    return {
        "directory": file_info(root, root / ".task" / "cycle"),
        "count": len(dirs),
        "latest_cycle_id": latest.name if latest.is_dir() else None,
        "latest_cycle_dir": file_info(root, latest)
        if latest.is_dir()
        else file_info(root, root / ".task" / "cycle"),
        "latest_events": events,
        "current_stage": current if isinstance(current, dict) else {},
        "packets": limited_files(root, packets, max_files),
        "used_goal_truth": used_goal_truth,
    }


def collect_agent_goal(
    root: Path,
    max_files: int,
    cycle_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    goal_dir = root / ".agent_goal"
    all_md = sorted(goal_dir.glob("*.md")) if goal_dir.is_dir() else []
    gt = {name: file_info(root, goal_dir / name) for name in GT_FILES}
    available = [info["path"] for info in gt.values() if info.get("exists")]
    effective_cycle_state = (
        cycle_state if cycle_state is not None else collect_cycle_state(root, max_files)
    )
    cycle_used = effective_cycle_state.get("used_goal_truth") or []
    used = [
        path
        for path in cycle_used
        if path in available or path.startswith(".agent_goal/")
    ]
    extra = [path for path in all_md if path.name not in set(GT_FILES)]
    return {
        "directory": file_info(root, goal_dir),
        "goal_truth_files": gt,
        "available_goal_truth": available,
        "used_goal_truth": used,
        "extra_markdown": limited_files(root, extra, max_files),
    }


def collect_task(root: Path, max_files: int) -> dict[str, Any]:
    task_dir = root / ".task"
    candidates = (
        sorted((task_dir / "candidate_task").glob("*.md"))
        if (task_dir / "candidate_task").is_dir()
        else []
    )
    packs = (
        sorted((task_dir / "task_pack").glob("*.json"))
        if (task_dir / "task_pack").is_dir()
        else []
    )
    pack_renders = (
        sorted((task_dir / "task_pack").glob("*.md"))
        if (task_dir / "task_pack").is_dir()
        else []
    )
    misses = (
        sorted((task_dir / "task_miss").rglob("*.md"))
        if (task_dir / "task_miss").is_dir()
        else []
    )
    validations = (
        sorted((task_dir / "validation").glob("*"))
        if (task_dir / "validation").is_dir()
        else []
    )
    validation_sets = (
        sorted((task_dir / "validation_set").glob("*"))
        if (task_dir / "validation_set").is_dir()
        else []
    )
    id_audits = (
        sorted((task_dir / "id_audit").glob("*"))
        if (task_dir / "id_audit").is_dir()
        else []
    )
    decisions = (
        sorted((task_dir / "decision").glob("*"))
        if (task_dir / "decision").is_dir()
        else []
    )
    authorizations = (
        sorted((task_dir / "authorization").glob("*"))
        if (task_dir / "authorization").is_dir()
        else []
    )
    cycles = latest_cycle_dirs(root, max_files)
    miss_counts: dict[str, int] = {}
    for path in misses:
        status = classify_text_status(path)
        miss_counts[status] = miss_counts.get(status, 0) + 1
    pack_projection = collect_task_pack_projection(root, packs, max_files)
    return {
        "directory": file_info(root, task_dir),
        "index_jsonl": file_info(root, task_dir / "index.jsonl"),
        "index_entries": count_jsonl_lines(task_dir / "index.jsonl"),
        "index_md": file_info(root, task_dir / "index.md"),
        "candidate_task": {
            "count": len(candidates),
            "files": limited_files(root, candidates, max_files),
        },
        "task_pack": {
            "count": len(packs),
            **pack_projection,
            "files": limited_files(root, packs, max_files),
            "renders": limited_files(root, pack_renders, max_files),
        },
        "task_miss": {
            "count": len(misses),
            "status_counts": miss_counts,
            "active_count": sum(
                miss_counts.get(key, 0)
                for key in ("open", "still_open", "partial", "blocked")
            ),
            "files": limited_files(root, misses, max_files),
        },
        "validation": {
            "count": len(validations),
            "files": limited_files(root, validations, max_files),
        },
        "validation_set": {
            "count": len(validation_sets),
            "files": limited_files(root, validation_sets, max_files),
        },
        "id_audit": {
            "count": len(id_audits),
            "files": limited_files(root, id_audits, max_files),
        },
        "decision": {
            "count": len(decisions),
            "files": limited_files(root, decisions, max_files),
        },
        "authorization": {
            "count": len(authorizations),
            "files": limited_files(root, authorizations, max_files),
        },
        "cycle": {
            "count": len(cycles),
            "files": [file_info(root, path) for path in cycles],
        },
    }


def collect_issue(root: Path, max_files: int) -> dict[str, Any]:
    issue_dir = root / ".issue"
    files = files_with_suffixes(issue_dir, {".md", ".json", ".jsonl"})
    issue_files = [path for path in files if path.name.lower() != "index.md"]
    counts: dict[str, int] = {}
    for path in issue_files:
        status = classify_text_status(path)
        counts[status] = counts.get(status, 0) + 1
    return {
        "directory": file_info(root, issue_dir),
        "count": len(issue_files),
        "status_counts": counts,
        "active_count": sum(
            counts.get(key, 0)
            for key in ("open", "blocked", "in_progress", "still_open")
        ),
        "files": limited_files(root, issue_files, max_files),
    }


def collect_agent_log(root: Path, max_files: int) -> dict[str, Any]:
    integrity, markdown, jsonl = inspect_agent_log_store(root)
    return {
        "directory": integrity["directory"],
        "markdown_count": len(markdown),
        "jsonl_count": len(jsonl),
        "latest_markdown": limited_files(root, markdown, max_files),
        "latest_jsonl": limited_files(root, jsonl, max_files),
        "integrity": integrity,
    }


def collect_contract_dir(root: Path, name: str, max_files: int) -> dict[str, Any]:
    directory = root / name
    suffixes = {".md", ".json", ".jsonl", ".yaml", ".yml"}
    files = files_with_suffixes(directory, suffixes)
    return {
        "directory": file_info(root, directory),
        "count": len(files),
        "files": limited_files(root, files, max_files),
    }


def collect_external_advice(root: Path, max_files: int) -> dict[str, Any]:
    directory = root / ".agent_advice"
    suffixes = {".md", ".json", ".jsonl"}
    files = files_with_suffixes(directory, suffixes)
    markdown = [
        path
        for path in files
        if path.suffix.lower() == ".md" and path.name.lower() != "index.md"
    ]
    counts: dict[str, int] = {}
    active_files: list[Path] = []
    for path in markdown:
        status = classify_text_status(path, default="active")
        relative_parts = (
            {part.lower() for part in path.relative_to(directory).parts}
            if directory in path.parents
            else set()
        )
        if "active" in relative_parts:
            status = "active"
        elif "applied" in relative_parts:
            status = "applied"
        elif "deferred" in relative_parts:
            status = "deferred"
        elif "rejected" in relative_parts:
            status = "rejected"
        elif "raw" in relative_parts:
            status = "raw"
        counts[status] = counts.get(status, 0) + 1
        if status == "active":
            active_files.append(path)
    normalized_packet: dict[str, Any] | None = None
    normalization_error: str | None = None
    if (directory / "index.jsonl").is_file():
        try:
            from manage_external_advice.rendering import advice_packet

            normalized_packet = advice_packet(root)
        except (ImportError, OSError, SystemExit, ValueError) as exc:
            normalization_error = type(exc).__name__
    return {
        "directory": file_info(root, directory),
        "index_jsonl": file_info(root, directory / "index.jsonl"),
        "index_entries": count_jsonl_lines(directory / "index.jsonl"),
        "index_md": file_info(root, directory / "index.md"),
        "count": len(markdown),
        "status_counts": counts,
        "active_count": len(active_files),
        "active_files": limited_files(root, active_files, max_files),
        "latest_files": limited_files(root, markdown, max_files),
        "normalized_packet": normalized_packet,
        "normalized_packet_status": (
            "available"
            if normalized_packet is not None
            else ("not_applicable" if not active_files else "unavailable")
        ),
        "normalization_error_class": normalization_error,
    }


def collect_validation_assets(root: Path, max_files: int) -> dict[str, Any]:
    directory = root / ".validation"
    set_dirs = (
        sorted((directory / "sets").glob("*")) if (directory / "sets").is_dir() else []
    )
    set_dirs = [path for path in set_dirs if path.is_dir()]
    candidate_dirs = (
        sorted((directory / "candidates").glob("*"))
        if (directory / "candidates").is_dir()
        else []
    )
    candidate_dirs = [path for path in candidate_dirs if path.is_dir()]
    manifests = (
        sorted((directory / "sets").glob("*/validation_set_manifest.json"))
        if (directory / "sets").is_dir()
        else []
    )
    roots = (
        sorted((directory / "sets").glob("*/validation_set_root.json"))
        if (directory / "sets").is_dir()
        else []
    )
    reports = (
        sorted((directory / "sets").glob("*/validation_set_report.*"))
        if (directory / "sets").is_dir()
        else []
    )
    return {
        "directory": file_info(root, directory),
        "sets": {
            "count": len(set_dirs),
            "directories": [
                file_info(root, path)
                for path in sorted(
                    set_dirs,
                    key=lambda path: path.stat().st_mtime if path.exists() else 0,
                    reverse=True,
                )[:max_files]
            ],
            "manifests": limited_files(root, manifests, max_files),
            "roots": limited_files(root, roots, max_files),
            "reports": limited_files(root, reports, max_files),
        },
        "candidates": {
            "count": len(candidate_dirs),
            "directories": [
                file_info(root, path)
                for path in sorted(
                    candidate_dirs,
                    key=lambda path: path.stat().st_mtime if path.exists() else 0,
                    reverse=True,
                )[:max_files]
            ],
        },
        "registry_jsonl": file_info(root, directory / "registry.jsonl"),
        "registry_entries": count_jsonl_lines(directory / "registry.jsonl"),
        "index_md": file_info(root, directory / "index.md"),
    }


def run_git(root: Path, args: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc)}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def collect_git(root: Path) -> dict[str, Any]:
    inside = run_git(root, ["rev-parse", "--is-inside-work-tree"])
    status = run_git(root, ["status", "--short", "--branch"])
    diff_names = run_git(root, ["diff", "--name-status"])
    untracked = run_git(root, ["ls-files", "--others", "--exclude-standard"])
    top = run_git(root, ["rev-parse", "--show-toplevel"])
    head = run_git(root, ["rev-parse", "--short", "HEAD"])
    return {
        "inside_work_tree": inside.get("stdout") == "true",
        "worktree_root": top.get("stdout") or None,
        "head": head.get("stdout") or None,
        "status_short_branch": [
            line for line in status.get("stdout", "").splitlines() if line.strip()
        ],
        "diff_name_status": [
            line for line in diff_names.get("stdout", "").splitlines() if line.strip()
        ],
        "untracked": [
            line for line in untracked.get("stdout", "").splitlines() if line.strip()
        ],
        "commands": {
            "rev_parse_inside": inside,
            "status_short_branch": status,
            "diff_name_status": diff_names,
            "untracked": untracked,
        },
    }


def collect(
    root: Path,
    include_git: bool,
    max_files: int,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    cycle_state = collect_cycle_state(root, max_files, cycle_id)
    external_advice = collect_external_advice(root, max_files)
    data: dict[str, Any] = {
        "schema_version": 2,
        "workspace": str(root.resolve()),
        "collected_at": now_iso(),
        "task_md": file_info(root, root / "task.md"),
        "agent_goal": collect_agent_goal(root, max_files, cycle_state),
        "cycle_state": cycle_state,
        "selection_publication": publication_status(root),
        "task_state": collect_task(root, max_files),
        "issue": collect_issue(root, max_files),
        "agent_log": collect_agent_log(root, max_files),
        "session_audit": collect_session_audit_directory(root, max_files),
        "external_advice": external_advice,
        "validation_assets": collect_validation_assets(root, max_files),
        "schema": collect_contract_dir(root, ".schema", max_files),
        "contract": collect_contract_dir(root, ".contract", max_files),
    }
    if include_git:
        data["git"] = collect_git(root)
    return data


def main(argv: list[str] | None = None) -> int:
    from .context_cli import main as context_main

    return context_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
