#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from orchestrate_task_cycle.result_contract.session_audit import collect_session_audit_directory
from record_agent_work_log.integrity import inspect_agent_log_store


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_info(root: Path, path: Path) -> dict[str, Any]:
    info: dict[str, Any] = {
        "path": rel_path(root, path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
    }
    if path.exists():
        stat = path.stat()
        info.update(
            {
                "size_bytes": stat.st_size,
                "modified_at": dt.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            }
        )
    if path.is_file():
        info["sha256"] = sha256_file(path)
        info["title"] = read_title(path)
    return info


def read_title(path: Path) -> str:
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    return stripped.lstrip("#").strip()[:120] or path.stem
                if stripped:
                    return stripped[:120]
        except OSError:
            pass
    return path.stem.replace("-", " ").replace("_", " ")


def count_jsonl_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def classify_text_status(path: Path, default: str = "open") -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    for status in ("resolved", "closed", "archived", "applied", "deferred", "rejected", "raw"):
        if status in parts or status in name:
            return status
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return default
    for status in ("failed", "partial", "blocked", "in_progress", "open", "resolved", "closed", "archived", "applied", "deferred", "rejected"):
        if f"status: {status}" in text:
            return status
    return default


def classify_miss(path: Path) -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    if "resolved" in parts or "resolved" in name:
        return "resolved"
    if "deleted" in name:
        return "deleted"
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return "open"
    if "resolved_delete" in text or "task-miss-deleted" in name:
        return "deleted"
    if "resolved_archive" in text or "resolved" in text:
        return "resolved"
    if "partially_resolved" in text or "partial" in text:
        return "partially_resolved"
    if "obsolete_scope" in text or "obsolete" in text:
        return "obsolete"
    if "still_open" in text or "confirmed misses" in text or "generalization gaps" in text:
        return "open"
    return "open"


def classify_issue(path: Path) -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    if "closed" in parts or "closed" in name:
        return "closed"
    if "resolved" in parts or "resolved" in name:
        return "resolved"
    if "archived" in parts or "archived" in name:
        return "archived"
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return "open"
    for status in ("closed", "resolved", "archived", "superseded", "blocked", "in_progress"):
        if f"status: {status}" in text:
            return status
    return "open"


def limited_files(root: Path, files: list[Path], max_files: int) -> list[dict[str, Any]]:
    sorted_files = sorted(files, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return [file_info(root, path) for path in sorted_files[:max_files]]


def files_with_suffixes(directory: Path, suffixes: set[str]) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def collect_task_miss(root: Path, max_files: int) -> dict[str, Any]:
    miss_dir = root / ".task" / "task_miss"
    files = sorted(miss_dir.rglob("*.md")) if miss_dir.is_dir() else []
    classified = []
    counts = {"open": 0, "partially_resolved": 0, "resolved": 0, "deleted": 0, "obsolete": 0}
    for path in files:
        status = classify_miss(path)
        counts[status] = counts.get(status, 0) + 1
        if len(classified) < max_files:
            entry = file_info(root, path)
            entry["status"] = status
            classified.append(entry)
    active_count = counts.get("open", 0) + counts.get("partially_resolved", 0)
    return {"count": len(files), "active_count": active_count, "status_counts": counts, "files": classified}


def collect_issues(root: Path, max_files: int) -> dict[str, Any]:
    issue_dir = root / ".issue"
    files = sorted(issue_dir.rglob("*.md")) if issue_dir.is_dir() else []
    classified = []
    counts = {"open": 0, "blocked": 0, "in_progress": 0, "resolved": 0, "closed": 0, "archived": 0, "superseded": 0}
    for path in files:
        if path.name.lower() == "index.md":
            continue
        status = classify_issue(path)
        counts[status] = counts.get(status, 0) + 1
        if len(classified) < max_files:
            entry = file_info(root, path)
            entry["status"] = status
            classified.append(entry)
    active_count = counts.get("open", 0) + counts.get("blocked", 0) + counts.get("in_progress", 0)
    return {
        "directory": file_info(root, issue_dir),
        "count": len([path for path in files if path.name.lower() != "index.md"]),
        "active_count": active_count,
        "status_counts": counts,
        "files": classified,
    }


def collect_agent_log(root: Path, max_files: int) -> dict[str, Any]:
    integrity, markdown_files, jsonl_files = inspect_agent_log_store(root)
    index_jsonl = root / ".agent_log" / "index.jsonl"
    if index_jsonl in jsonl_files:
        index_projection = file_info(root, index_jsonl)
    else:
        index_projection = {
            "path": ".agent_log/index.jsonl",
            "exists": index_jsonl.exists() or index_jsonl.is_symlink(),
            "is_file": False,
            "is_dir": False,
            "is_symlink": index_jsonl.is_symlink(),
        }
    return {
        "directory": integrity["directory"],
        "index_jsonl": index_projection,
        "index_entries": integrity["indexed_count"],
        "markdown_count": len(markdown_files),
        "latest_markdown": limited_files(root, markdown_files, max_files),
        "integrity": integrity,
    }


def collect_agent_goal(root: Path, max_files: int) -> dict[str, Any]:
    goal_dir = root / ".agent_goal"
    markdown_files = sorted(goal_dir.glob("*.md")) if goal_dir.is_dir() else []
    return {
        "directory": file_info(root, goal_dir),
        "count": len(markdown_files),
        "goal_schema_contract": file_info(root, goal_dir / "goal_schema_contract.md"),
        "files": limited_files(root, markdown_files, max_files),
    }


def collect_external_advice(root: Path, max_files: int) -> dict[str, Any]:
    advice_dir = root / ".agent_advice"
    files = files_with_suffixes(advice_dir, {".md", ".json", ".jsonl"})
    markdown = [path for path in files if path.suffix.lower() == ".md" and path.name.lower() != "index.md"]
    counts: dict[str, int] = {}
    active: list[Path] = []
    for path in markdown:
        relative_parts = {part.lower() for part in path.relative_to(advice_dir).parts} if advice_dir in path.parents else set()
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
        else:
            status = classify_text_status(path, default="active")
        counts[status] = counts.get(status, 0) + 1
        if status == "active":
            active.append(path)
    return {
        "directory": file_info(root, advice_dir),
        "index_jsonl": file_info(root, advice_dir / "index.jsonl"),
        "index_entries": count_jsonl_lines(advice_dir / "index.jsonl"),
        "index_md": file_info(root, advice_dir / "index.md"),
        "count": len(markdown),
        "status_counts": counts,
        "active_count": len(active),
        "active_files": limited_files(root, active, max_files),
        "latest_files": limited_files(root, markdown, max_files),
    }


def collect_contract_directory(root: Path, directory_name: str, max_files: int) -> dict[str, Any]:
    directory = root / directory_name
    contract_suffixes = {".md", ".json", ".jsonl", ".yaml", ".yml"}
    files = (
        sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in contract_suffixes)
        if directory.is_dir()
        else []
    )
    return {
        "directory": file_info(root, directory),
        "count": len(files),
        "files": limited_files(root, files, max_files),
    }


def collect_schema_contracts(root: Path, max_files: int) -> dict[str, Any]:
    return {
        "schema": collect_contract_directory(root, ".schema", max_files),
        "contract": collect_contract_directory(root, ".contract", max_files),
    }


def collect_git_status(root: Path) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": str(exc)}
    return {
        "available": result.returncode == 0,
        "returncode": result.returncode,
        "entries": [line for line in result.stdout.splitlines() if line.strip()],
        "stderr": result.stderr.strip(),
    }


def collect(root: Path, include_git: bool, max_files: int) -> dict[str, Any]:
    candidate_dir = root / ".task" / "candidate_task"
    candidate_files = sorted(candidate_dir.glob("*.md")) if candidate_dir.is_dir() else []
    validation_dir = root / ".task" / "validation"
    validation_files = sorted(validation_dir.glob("*.md")) if validation_dir.is_dir() else []

    evidence: dict[str, Any] = {
        "workspace": str(root),
        "collected_at": now_iso(),
        "task_md": file_info(root, root / "task.md"),
        "task_index": {
            "jsonl": file_info(root, root / ".task" / "index.jsonl"),
            "jsonl_entries": count_jsonl_lines(root / ".task" / "index.jsonl"),
            "markdown": file_info(root, root / ".task" / "index.md"),
        },
        "candidate_task": {
            "directory": file_info(root, candidate_dir),
            "count": len(candidate_files),
            "files": limited_files(root, candidate_files, max_files),
        },
        "task_miss": collect_task_miss(root, max_files),
        "issues": collect_issues(root, max_files),
        "agent_log": collect_agent_log(root, max_files),
        "session_audit": collect_session_audit_directory(root, max_files),
        "agent_goal": collect_agent_goal(root, max_files),
        "external_advice": collect_external_advice(root, max_files),
        "schema_contracts": collect_schema_contracts(root, max_files),
        "validation_reports": {
            "directory": file_info(root, validation_dir),
            "count": len(validation_files),
            "latest": limited_files(root, validation_files, max_files),
        },
    }
    if include_git:
        evidence["git_status"] = collect_git_status(root)
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect local evidence for task completion validation.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    parser.add_argument("--include-git", action="store_true", help="Include git status --short output.")
    parser.add_argument("--max-files", type=int, default=25, help="Maximum files per evidence category.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    evidence = collect(root, include_git=args.include_git, max_files=args.max_files)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
