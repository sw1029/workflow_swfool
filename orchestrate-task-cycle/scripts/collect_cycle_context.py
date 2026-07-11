#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from result_contract_lib.session_audit import collect_session_audit_directory  # noqa: E402


GT_FILES = [
    "final_goal.md",
    "conventions.md",
    "goal_architecture.md",
    "goal_theory.md",
    "goal_schema_contract.md",
    "agent_authority.md",
]


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


def count_jsonl_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def read_json_file(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None


def read_jsonl_file(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    records.append(value)
    except OSError:
        return records
    if limit is not None:
        return records[-limit:]
    return records


def limited_files(root: Path, files: list[Path], max_files: int) -> list[dict[str, Any]]:
    ordered = sorted(files, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return [file_info(root, path) for path in ordered[:max_files]]


def files_with_suffixes(directory: Path, suffixes: set[str]) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)


def classify_text_status(path: Path, default: str = "open") -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    if "resolved" in parts or "resolved" in name:
        return "resolved"
    if "deleted" in name:
        return "deleted"
    if "closed" in parts or "closed" in name:
        return "closed"
    if "archived" in parts or "archived" in name:
        return "archived"
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return default
    for status in (
        "failed",
        "partial",
        "blocked",
        "in_progress",
        "still_open",
        "open",
        "resolved",
        "deleted",
        "obsolete",
        "closed",
        "archived",
        "passed",
        "complete",
    ):
        if f"status: {status}" in text or f"validation verdict: {status}" in text:
            return status
    return default


def extract_used_goal_truth_from_value(value: Any) -> list[str]:
    used: list[str] = []
    if isinstance(value, dict):
        for key in ("used_goal_truth", "gt_files", "goal_truth"):
            item = value.get(key)
            if isinstance(item, list):
                used.extend(str(entry) for entry in item)
        packet = value.get("packet")
        if isinstance(packet, dict):
            used.extend(extract_used_goal_truth_from_value(packet))
        for nested_key in ("latest_event", "steps"):
            nested = value.get(nested_key)
            used.extend(extract_used_goal_truth_from_value(nested))
    elif isinstance(value, list):
        for item in value:
            used.extend(extract_used_goal_truth_from_value(item))
    return used


def latest_cycle_dirs(root: Path, max_files: int) -> list[Path]:
    cycle_root = root / ".task" / "cycle"
    if not cycle_root.is_dir():
        return []
    dirs = [path for path in cycle_root.iterdir() if path.is_dir()]
    return sorted(dirs, key=lambda path: path.stat().st_mtime, reverse=True)[:max_files]


def collect_cycle_state(root: Path, max_files: int) -> dict[str, Any]:
    dirs = latest_cycle_dirs(root, max_files)
    latest = dirs[0] if dirs else root / ".task" / "cycle" / "none"
    events = read_jsonl_file(latest / "stage.jsonl", limit=max_files) if dirs else []
    current = read_json_file(latest / "current_stage.json") if dirs else None
    packets = sorted((latest / "packets").glob("*")) if (latest / "packets").is_dir() else []
    used_goal_truth = sorted(set(extract_used_goal_truth_from_value(events) + extract_used_goal_truth_from_value(current)))
    return {
        "directory": file_info(root, root / ".task" / "cycle"),
        "count": len(dirs),
        "latest_cycle_id": latest.name if dirs else None,
        "latest_cycle_dir": file_info(root, latest) if dirs else file_info(root, root / ".task" / "cycle"),
        "latest_events": events,
        "current_stage": current if isinstance(current, dict) else {},
        "packets": limited_files(root, packets, max_files),
        "used_goal_truth": used_goal_truth,
    }


def collect_agent_goal(root: Path, max_files: int) -> dict[str, Any]:
    goal_dir = root / ".agent_goal"
    all_md = sorted(goal_dir.glob("*.md")) if goal_dir.is_dir() else []
    gt = {name: file_info(root, goal_dir / name) for name in GT_FILES}
    available = [info["path"] for info in gt.values() if info.get("exists")]
    cycle_used = collect_cycle_state(root, max_files).get("used_goal_truth") or []
    used = [path for path in cycle_used if path in available or path.startswith(".agent_goal/")]
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
    candidates = sorted((task_dir / "candidate_task").glob("*.md")) if (task_dir / "candidate_task").is_dir() else []
    packs = sorted((task_dir / "task_pack").glob("*.json")) if (task_dir / "task_pack").is_dir() else []
    pack_renders = sorted((task_dir / "task_pack").glob("*.md")) if (task_dir / "task_pack").is_dir() else []
    misses = sorted((task_dir / "task_miss").rglob("*.md")) if (task_dir / "task_miss").is_dir() else []
    validations = sorted((task_dir / "validation").glob("*")) if (task_dir / "validation").is_dir() else []
    validation_sets = sorted((task_dir / "validation_set").glob("*")) if (task_dir / "validation_set").is_dir() else []
    id_audits = sorted((task_dir / "id_audit").glob("*")) if (task_dir / "id_audit").is_dir() else []
    decisions = sorted((task_dir / "decision").glob("*")) if (task_dir / "decision").is_dir() else []
    authorizations = sorted((task_dir / "authorization").glob("*")) if (task_dir / "authorization").is_dir() else []
    cycles = latest_cycle_dirs(root, max_files)
    miss_counts: dict[str, int] = {}
    for path in misses:
        status = classify_text_status(path)
        miss_counts[status] = miss_counts.get(status, 0) + 1
    pack_counts: dict[str, int] = {}
    active_pack: dict[str, Any] | None = None
    for path in packs:
        data = read_json_file(path)
        status = str(data.get("status") if isinstance(data, dict) else "unknown")
        pack_counts[status] = pack_counts.get(status, 0) + 1
        if status == "active" and active_pack is None and isinstance(data, dict):
            items = data.get("items") if isinstance(data.get("items"), list) else []
            next_item = None
            for item in sorted((item for item in items if isinstance(item, dict)), key=lambda item: item.get("order", 0)):
                if item.get("status") in {"planned", "inserted", "reordered"}:
                    next_item = item
                    break
            active_pack = {
                "path": rel_path(root, path),
                "render_path": rel_path(root, path.with_suffix(".md")) if path.with_suffix(".md").is_file() else None,
                "pack_id": data.get("pack_id"),
                "status": status,
                "goal": data.get("goal"),
                "current_item_id": data.get("current_item_id"),
                "next_item": next_item,
                "planned_item_count": sum(1 for item in items if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered"}),
                "terminal_blocker": data.get("terminal_blocker"),
            }
    return {
        "directory": file_info(root, task_dir),
        "index_jsonl": file_info(root, task_dir / "index.jsonl"),
        "index_entries": count_jsonl_lines(task_dir / "index.jsonl"),
        "index_md": file_info(root, task_dir / "index.md"),
        "candidate_task": {"count": len(candidates), "files": limited_files(root, candidates, max_files)},
        "task_pack": {
            "count": len(packs),
            "status_counts": pack_counts,
            "active_count": pack_counts.get("active", 0),
            "active_pack": active_pack,
            "files": limited_files(root, packs, max_files),
            "renders": limited_files(root, pack_renders, max_files),
        },
        "task_miss": {
            "count": len(misses),
            "status_counts": miss_counts,
            "active_count": sum(miss_counts.get(key, 0) for key in ("open", "still_open", "partial", "blocked")),
            "files": limited_files(root, misses, max_files),
        },
        "validation": {"count": len(validations), "files": limited_files(root, validations, max_files)},
        "validation_set": {"count": len(validation_sets), "files": limited_files(root, validation_sets, max_files)},
        "id_audit": {"count": len(id_audits), "files": limited_files(root, id_audits, max_files)},
        "decision": {"count": len(decisions), "files": limited_files(root, decisions, max_files)},
        "authorization": {"count": len(authorizations), "files": limited_files(root, authorizations, max_files)},
        "cycle": {"count": len(cycles), "files": [file_info(root, path) for path in cycles]},
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
        "active_count": sum(counts.get(key, 0) for key in ("open", "blocked", "in_progress", "still_open")),
        "files": limited_files(root, issue_files, max_files),
    }


def collect_agent_log(root: Path, max_files: int) -> dict[str, Any]:
    log_dir = root / ".agent_log"
    markdown = sorted(log_dir.rglob("*.md")) if log_dir.is_dir() else []
    jsonl = sorted(log_dir.rglob("*.jsonl")) if log_dir.is_dir() else []
    return {
        "directory": file_info(root, log_dir),
        "markdown_count": len(markdown),
        "jsonl_count": len(jsonl),
        "latest_markdown": limited_files(root, markdown, max_files),
        "latest_jsonl": limited_files(root, jsonl, max_files),
    }


def collect_contract_dir(root: Path, name: str, max_files: int) -> dict[str, Any]:
    directory = root / name
    suffixes = {".md", ".json", ".jsonl", ".yaml", ".yml"}
    files = files_with_suffixes(directory, suffixes)
    return {"directory": file_info(root, directory), "count": len(files), "files": limited_files(root, files, max_files)}


def collect_external_advice(root: Path, max_files: int) -> dict[str, Any]:
    directory = root / ".agent_advice"
    suffixes = {".md", ".json", ".jsonl"}
    files = files_with_suffixes(directory, suffixes)
    markdown = [path for path in files if path.suffix.lower() == ".md" and path.name.lower() != "index.md"]
    counts: dict[str, int] = {}
    active_files: list[Path] = []
    for path in markdown:
        status = classify_text_status(path, default="active")
        relative_parts = {part.lower() for part in path.relative_to(directory).parts} if directory in path.parents else set()
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
    }


def collect_validation_assets(root: Path, max_files: int) -> dict[str, Any]:
    directory = root / ".validation"
    set_dirs = sorted((directory / "sets").glob("*")) if (directory / "sets").is_dir() else []
    set_dirs = [path for path in set_dirs if path.is_dir()]
    candidate_dirs = sorted((directory / "candidates").glob("*")) if (directory / "candidates").is_dir() else []
    candidate_dirs = [path for path in candidate_dirs if path.is_dir()]
    manifests = sorted((directory / "sets").glob("*/validation_set_manifest.json")) if (directory / "sets").is_dir() else []
    roots = sorted((directory / "sets").glob("*/validation_set_root.json")) if (directory / "sets").is_dir() else []
    reports = sorted((directory / "sets").glob("*/validation_set_report.*")) if (directory / "sets").is_dir() else []
    return {
        "directory": file_info(root, directory),
        "sets": {
            "count": len(set_dirs),
            "directories": [file_info(root, path) for path in sorted(set_dirs, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)[:max_files]],
            "manifests": limited_files(root, manifests, max_files),
            "roots": limited_files(root, roots, max_files),
            "reports": limited_files(root, reports, max_files),
        },
        "candidates": {
            "count": len(candidate_dirs),
            "directories": [file_info(root, path) for path in sorted(candidate_dirs, key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)[:max_files]],
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
    return {"returncode": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


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
        "status_short_branch": [line for line in status.get("stdout", "").splitlines() if line.strip()],
        "diff_name_status": [line for line in diff_names.get("stdout", "").splitlines() if line.strip()],
        "untracked": [line for line in untracked.get("stdout", "").splitlines() if line.strip()],
        "commands": {
            "rev_parse_inside": inside,
            "status_short_branch": status,
            "diff_name_status": diff_names,
            "untracked": untracked,
        },
    }


def collect(root: Path, include_git: bool, max_files: int) -> dict[str, Any]:
    cycle_state = collect_cycle_state(root, max_files)
    data: dict[str, Any] = {
        "schema_version": 2,
        "workspace": str(root.resolve()),
        "collected_at": now_iso(),
        "task_md": file_info(root, root / "task.md"),
        "agent_goal": collect_agent_goal(root, max_files),
        "cycle_state": cycle_state,
        "task_state": collect_task(root, max_files),
        "issue": collect_issue(root, max_files),
        "agent_log": collect_agent_log(root, max_files),
        "session_audit": collect_session_audit_directory(root, max_files),
        "external_advice": collect_external_advice(root, max_files),
        "validation_assets": collect_validation_assets(root, max_files),
        "schema": collect_contract_dir(root, ".schema", max_files),
        "contract": collect_contract_dir(root, ".contract", max_files),
    }
    if include_git:
        data["git"] = collect_git(root)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect compact evidence for an orchestrate-task-cycle run.")
    parser.add_argument("--root", default=".", help="Workspace root to inspect.")
    parser.add_argument("--include-git", action="store_true", help="Include Git worktree and status evidence.")
    parser.add_argument("--max-files", type=int, default=12, help="Maximum recent files per artifact group.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        parser.error(f"--root does not exist: {root}")
    json.dump(collect(root, args.include_git, max(1, args.max_files)), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
