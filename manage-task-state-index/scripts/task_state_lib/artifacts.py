"""Artifact metadata extraction and standard workspace discovery."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

AGENT_LOG_SCRIPTS = Path(__file__).resolve().parents[3] / "record-agent-work-log" / "scripts"
if str(AGENT_LOG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AGENT_LOG_SCRIPTS))

from agent_log_integrity import inspect_agent_log_store

from .contracts import NON_ACTIVE_STATUSES
from .storage import read_title, rel_path

def normalize_bounded_markdown_scalar(value: str) -> str:
    """Strip one safe, balanced inline-code wrapper from scalar metadata."""
    normalized = value.strip()
    if (
        len(normalized) >= 3
        and normalized.startswith("`")
        and normalized.endswith("`")
        and normalized.count("`") == 2
        and normalized[1:-1].strip()
    ):
        return normalized[1:-1].strip()
    return normalized


def advice_pointer_file(path: Path) -> bool:
    fields = extract_advice_fields(path)
    return str(fields.get("not_active_record", "")).casefold() == "true"


def select_external_advice_scan_id(
    root: Path, state: dict[str, dict[str, Any]], path_value: str, advice_id: str,
) -> tuple[str, list[str]]:
    """Select canonical advice identity and bounded pointer aliases to retire."""
    exact = state.get(advice_id)
    if exact is not None:
        if exact.get("type") != "external_advice":
            raise ValueError(
                f"Canonical advice id {advice_id!r} is already bound to another artifact path"
            )
        exact_path = str(exact.get("path") or "")
        if exact_path != path_value:
            old_file = root / exact_path
            if old_file.exists() and not advice_pointer_file(old_file):
                raise ValueError(
                    f"Canonical advice id {advice_id!r} is already bound to another artifact path"
                )

    pointer_aliases: list[str] = []
    active_cross_path_aliases: list[str] = []
    for item_id, item in state.items():
        if item_id == advice_id:
            continue
        existing_fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        existing_advice_id = normalize_bounded_markdown_scalar(str(existing_fields.get("advice_id") or ""))
        if not (
            item.get("type") == "external_advice"
            and existing_advice_id == advice_id
            and item.get("path") != path_value
            and item.get("status") not in NON_ACTIVE_STATUSES
        ):
            continue
        alias_file = root / str(item.get("path") or "")
        if alias_file.is_file() and advice_pointer_file(alias_file):
            pointer_aliases.append(item_id)
        else:
            active_cross_path_aliases.append(item_id)
    if active_cross_path_aliases:
        raise ValueError(
            f"Canonical advice id {advice_id!r} has an active cross-path alias"
        )
    return advice_id, sorted(pointer_aliases)

def infer_miss_status(path: Path) -> str:
    name = path.name.lower()
    if "deleted" in name:
        return "deleted"
    if "partially_resolved" in name or "partially-resolved" in name:
        return "partially_resolved"
    if "resolved" in name:
        return "resolved"
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return "open"
    if "partially_resolved" in text or "partially-resolved" in text or "status: partial" in text:
        return "partially_resolved"
    if "resolved_delete" in text or "deleted" in text:
        return "deleted"
    if "resolved_archive" in text or "resolved" in text:
        return "resolved"
    if "obsolete_scope" in text or "obsolete" in text:
        return "obsolete"
    return "open"


def infer_schema_status(path: Path) -> str:
    name = path.name.lower()
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        text = ""
    combined = f"{name}\n{text}"
    if "status: superseded" in combined or '"status": "superseded"' in combined or '"status":"superseded"' in combined:
        return "superseded"
    if "status: deprecated" in combined or '"status": "deprecated"' in combined or '"status":"deprecated"' in combined:
        return "deprecated"
    if "status: needs_review" in combined or '"status": "needs_review"' in combined or '"status":"needs_review"' in combined:
        return "needs_review"
    return "active"


def infer_issue_status(path: Path) -> str:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        text = ""
    combined = f"{name}\n{text}"
    if "closed" in parts or "status: closed" in combined:
        return "closed"
    if "resolved" in parts or "status: resolved" in combined:
        return "resolved"
    if "archived" in parts or "status: archived" in combined:
        return "archived"
    if "status: superseded" in combined:
        return "superseded"
    if "status: blocked" in combined:
        return "blocked"
    if "status: in_progress" in combined or "status: in-progress" in combined:
        return "in_progress"
    return "open"


def infer_advice_status(path: Path) -> str:
    parts = {part.lower() for part in path.parts}
    try:
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        text = ""
    combined = f"{path.name.lower()}\n{text}"
    if "applied" in parts or "status: applied" in combined:
        return "applied"
    if "rejected" in parts or "status: rejected" in combined:
        return "rejected"
    if "deferred" in parts or "status: deferred" in combined:
        return "deferred"
    if "raw" in parts:
        return "raw"
    return "active"


def extract_schema_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    fields: dict[str, str] = {}
    scalar_keys = {
        "contract_id",
        "type",
        "status",
        "version",
        "owner_path",
        "updated_at",
    }
    list_keys = {
        "target_modules",
        "target_scripts",
        "producers",
        "consumers",
        "compatible_with",
    }
    current_list_key: str | None = None
    collected_lists: dict[str, list[str]] = {key: [] for key in list_keys}

    for raw_line in lines:
        line = raw_line.rstrip()
        scalar_match = re.match(r"^-\s+([A-Za-z0-9_]+):\s*(.*)$", line)
        if scalar_match:
            key, value = scalar_match.groups()
            if key in scalar_keys and value:
                fields[key] = value.strip()
                current_list_key = None
                continue
            if key in list_keys:
                current_list_key = key
                if value:
                    collected_lists[key].append(value.strip())
                continue
            current_list_key = None
            continue

        list_match = re.match(r"^\s+-\s+(.+)$", line)
        if current_list_key and list_match:
            collected_lists[current_list_key].append(list_match.group(1).strip())
        elif line and not line.startswith(" "):
            current_list_key = None

    for key, values in collected_lists.items():
        if values:
            fields[key] = ", ".join(values)

    if path.suffix.lower() == ".jsonl" and not fields:
        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                break
            if isinstance(event, dict):
                for key in scalar_keys | list_keys:
                    value = event.get(key)
                    if isinstance(value, list):
                        fields[key] = ", ".join(str(item) for item in value)
                    elif value is not None:
                        fields[key] = str(value)
            break

    return fields


def extract_issue_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    fields: dict[str, str] = {}
    scalar_keys = {
        "issue_id",
        "status",
        "source",
        "remote_url",
        "remote_number",
        "task_id",
        "task_path",
        "priority",
        "goal_fit",
        "branch",
        "worktree_path",
        "validation_status",
        "created_at",
        "updated_at",
    }
    for raw_line in lines:
        match = re.match(r"^-\s+([A-Za-z0-9_]+):\s*(.*)$", raw_line.rstrip())
        if not match:
            continue
        key, value = match.groups()
        if key in scalar_keys and value:
            fields[key] = value.strip()
    return fields


def extract_advice_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}
    fields: dict[str, str] = {}
    scalar_keys = {
        "advice_id",
        "status",
        "not_goal_truth",
        "raw_source_path",
        "received_at",
        "normalized_at",
        "scope",
        "priority",
        "source_label",
        "not_active_record",
    }
    for raw_line in lines:
        match = re.match(r"^-\s+([A-Za-z0-9_]+):\s*(.*)$", raw_line.rstrip())
        if not match:
            continue
        key, value = match.groups()
        if key in scalar_keys and value:
            fields[key] = normalize_bounded_markdown_scalar(value)
    return fields


def extract_task_pack_fields(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    fields: dict[str, str] = {}
    for key in ("pack_id", "status", "language", "goal", "current_item_id"):
        value = data.get(key)
        if value is not None:
            fields[key] = str(value)
    items = data.get("items")
    if isinstance(items, list):
        fields["item_count"] = str(len(items))
        fields["planned_item_count"] = str(sum(1 for item in items if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered"}))
        ordered = sorted(
            (item for item in items if isinstance(item, dict)),
            key=lambda item: item.get("order") if isinstance(item.get("order"), int) else 10**9,
        )
        if ordered:
            promotion = ordered[0].get("promotion")
            if isinstance(promotion, dict):
                for key in ("promotion_origin", "initial_selection_receipt_ref"):
                    if promotion.get(key) is not None:
                        fields[f"initial_{key}"] = str(promotion.get(key))
                receipt = promotion.get("initial_selection_receipt")
                if isinstance(receipt, dict):
                    for key in (
                        "pack_creation_snapshot_ref",
                        "authority_receipt_ref",
                        "authority_receipt_sha256",
                        "authority_mode",
                        "historical_selection_authority_status",
                    ):
                        if receipt.get(key) is not None:
                            fields[f"initial_{key}"] = str(receipt.get(key))
                normalization = promotion.get("provenance_normalization")
                if isinstance(normalization, dict):
                    fields["initial_normalization_mode"] = str(normalization.get("mode") or "")
                    fields["initial_historical_authority_verdict"] = str(
                        normalization.get("historical_authority_verdict") or ""
                    )
    render_path = path.with_suffix(".md")
    if render_path.is_file():
        fields["render_path"] = render_path.as_posix()
    if data.get("terminal_blocker"):
        fields["terminal_blocker"] = "true"
    return fields


def discover_standard_artifacts(root: Path) -> list[tuple[str, str, str, str]]:
    artifacts: list[tuple[str, str, str, str]] = []

    task_md = root / "task.md"
    if task_md.is_file():
        artifacts.append(("task", "task.md", "active", read_title(task_md)))

    candidate_dir = root / ".task" / "candidate_task"
    if candidate_dir.is_dir():
        for path in sorted(candidate_dir.glob("*.md")):
            artifacts.append(("candidate_task", rel_path(root, path), "candidate", read_title(path)))

    task_pack_dir = root / ".task" / "task_pack"
    if task_pack_dir.is_dir():
        for path in sorted(task_pack_dir.glob("*.json")):
            fields = extract_task_pack_fields(path)
            status = fields.get("status", "active")
            title = fields.get("pack_id") or fields.get("goal") or path.stem
            artifacts.append(("task_pack", rel_path(root, path), status, title[:120]))

    miss_dir = root / ".task" / "task_miss"
    if miss_dir.is_dir():
        for path in sorted(miss_dir.rglob("*.md")):
            artifacts.append(("task_miss", rel_path(root, path), infer_miss_status(path), read_title(path)))

    validation_dir = root / ".task" / "validation"
    if validation_dir.is_dir():
        for path in sorted(validation_dir.glob("*.md")):
            status = "partial"
            try:
                text = path.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                text = ""
            if "verdict: complete" in text:
                status = "passed"
            elif "verdict: failed" in text:
                status = "failed"
            artifacts.append(("validation", rel_path(root, path), status, read_title(path)))

    id_audit_dir = root / ".task" / "id_audit"
    if id_audit_dir.is_dir():
        for path in sorted(id_audit_dir.glob("*.md")):
            artifacts.append(("audit", rel_path(root, path), "logged", read_title(path)))

    log_integrity, log_markdown, _ = inspect_agent_log_store(root)
    if log_integrity["status"] in {"valid", "legacy_unverified"}:
        for path in log_markdown:
            title = read_title(path)
            item_type = "past_task" if "past_task" in title.lower() or "past-task" in path.name.lower() else "agent_log"
            artifacts.append((item_type, rel_path(root, path), "logged", title))

    goal_dir = root / ".agent_goal"
    if goal_dir.is_dir():
        for path in sorted(goal_dir.glob("*.md")):
            artifacts.append(("goal", rel_path(root, path), "active", read_title(path)))

    interview_dir = root / ".interview"
    if interview_dir.is_dir():
        for path in sorted(interview_dir.rglob("*.md")):
            artifacts.append(("interview", rel_path(root, path), "active", read_title(path)))

    advice_dir = root / ".agent_advice"
    if advice_dir.is_dir():
        for path in sorted(advice_dir.rglob("*.md")):
            if path.name.lower() == "index.md":
                continue
            if advice_pointer_file(path):
                continue
            artifacts.append(("external_advice", rel_path(root, path), infer_advice_status(path), read_title(path)))

    issue_dir = root / ".issue"
    if issue_dir.is_dir():
        for path in sorted(issue_dir.rglob("*.md")):
            relative_parts = {part.lower() for part in path.relative_to(issue_dir).parts}
            if path.name.lower() == "index.md":
                artifacts.append(("issue_map", rel_path(root, path), "active", read_title(path)))
                continue
            status = infer_issue_status(path)
            item_type = "issue_resolution" if relative_parts & {"resolved", "closed", "archived"} else "issue"
            artifacts.append((item_type, rel_path(root, path), status, read_title(path)))

    schema_dir = root / ".schema"
    if schema_dir.is_dir():
        seen_schema_paths: set[str] = set()

        def add_schema_artifact(item_type: str, path: Path, status: str) -> None:
            relative = rel_path(root, path)
            if relative in seen_schema_paths:
                return
            seen_schema_paths.add(relative)
            artifacts.append((item_type, relative, status, read_title(path)))

        for name in ("index.md", "causal_map.md", "compatibility_map.md", "contracts.jsonl"):
            path = schema_dir / name
            if path.is_file():
                add_schema_artifact("schema_map", path, "active")

        for path in sorted(schema_dir.glob("*.md")) + sorted(schema_dir.glob("*.jsonl")) + sorted(schema_dir.glob("*.json")):
            if path.is_file():
                add_schema_artifact("schema_map", path, "active")

        contract_suffixes = {".md", ".json", ".jsonl", ".yaml", ".yml"}
        for directory_name in ("schemas", "modules", "scripts", "contracts"):
            directory = schema_dir / directory_name
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.suffix.lower() in contract_suffixes:
                    add_schema_artifact("schema_contract", path, infer_schema_status(path))

    contract_dir = root / ".contract"
    if contract_dir.is_dir():
        seen_contract_paths: set[str] = set()

        def add_contract_artifact(item_type: str, path: Path, status: str) -> None:
            relative = rel_path(root, path)
            if relative in seen_contract_paths:
                return
            seen_contract_paths.add(relative)
            artifacts.append((item_type, relative, status, read_title(path)))

        map_names = {"index.md", "causal_map.md", "compatibility_map.md", "contracts.jsonl"}
        for name in sorted(map_names):
            path = contract_dir / name
            if path.is_file():
                add_contract_artifact("schema_map", path, "active")

        contract_suffixes = {".md", ".json", ".jsonl", ".yaml", ".yml"}
        for path in sorted(contract_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in contract_suffixes:
                continue
            item_type = "schema_map" if path.name in map_names else "schema_contract"
            status = "active" if item_type == "schema_map" else infer_schema_status(path)
            add_contract_artifact(item_type, path, status)

    return artifacts
