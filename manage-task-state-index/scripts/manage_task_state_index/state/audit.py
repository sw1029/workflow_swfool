"""Task-state audit classification, reporting, and summaries."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, Callable

from .artifacts import discover_standard_artifacts
from .contracts import (
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    NON_ACTIVE_STATUSES,
    PREFIXES,
    TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES,
)
from .events import load_events_for_audit, merge_state
from .storage import (
    atomic_write_text,
    jsonl_path,
    markdown_path,
    now_iso,
    sha256_file,
    task_dir,
)

def add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    ids: list[str] | None = None,
    paths: list[str] | None = None,
) -> None:
    issues.append(
        {
            "severity": severity,
            "code": code,
            "message": message,
            "ids": ids or [],
            "paths": paths or [],
        }
    )

def _current_surface(
    root: Path,
    state: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str], set[str]]:
    active_tasks = [
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task" and item.get("status") == "active"
    ]
    current_task_digest = sha256_file(root / "task.md") if (root / "task.md").is_file() else None
    current_task_alias_ids = [
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task"
        and item.get("path") == "task.md"
        and item.get("content_sha256") == current_task_digest
        and (
            item.get("status") == "active"
            or (
                item.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
                and isinstance(item.get("fields"), dict)
                and item["fields"].get("record_class") == "mutable_alias"
                and item["fields"].get("canonical_id") == item_id
            )
        )
    ]
    current_surface_ids = set(current_task_alias_ids)
    while True:
        prior_size = len(current_surface_ids)
        for item_id, item in state.items():
            links = item.get("links") if isinstance(item.get("links"), list) else []
            if item_id in current_surface_ids:
                if isinstance(item.get("parent_id"), str) and item.get("parent_id"):
                    current_surface_ids.add(str(item["parent_id"]))
                current_surface_ids.update(
                    str(link.get("id"))
                    for link in links
                    if isinstance(link, dict) and isinstance(link.get("id"), str) and link.get("id")
                )
            if item.get("parent_id") in current_surface_ids or any(
                isinstance(link, dict) and link.get("id") in current_surface_ids for link in links
            ):
                current_surface_ids.add(item_id)
        if len(current_surface_ids) == prior_size:
            break

    return active_tasks, current_task_alias_ids, current_surface_ids


def _classify_malformed_rows(
    root: Path,
    read_results: list[dict[str, Any]],
    current_surface_ids: set[str],
    issues: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str], str]:
    malformed_results = [result for result in read_results if result.get("migration_status") == "malformed_quarantined"]
    legacy_results = [result for result in read_results if result.get("migration_status") == "normalized_legacy"]
    projection_not_evaluated_ids: set[str] = set()
    unknown_projection_impact = False
    for result in malformed_results:
        lineage_ids = {str(value) for value in result.pop("_lineage_ids", []) if str(value)}
        current_projection_hint = result.pop("_current_projection_hint", False) is True
        row_identity = str(result.get("row_identity") or "")
        if current_projection_hint:
            result["projection_impact"] = "affected"
            if row_identity:
                projection_not_evaluated_ids.add(row_identity)
            else:
                unknown_projection_impact = True
                projection_not_evaluated_ids.update(current_surface_ids)
        elif not row_identity:
            result["projection_impact"] = "unknown"
            unknown_projection_impact = True
            projection_not_evaluated_ids.update(current_surface_ids)
        elif row_identity in current_surface_ids or lineage_ids.intersection(current_surface_ids):
            result["projection_impact"] = "affected"
            projection_not_evaluated_ids.add(row_identity)
            projection_not_evaluated_ids.update(lineage_ids.intersection(current_surface_ids))
        else:
            result["projection_impact"] = "independent"
        add_issue(
            issues,
            "medium",
            "malformed_index_row",
            f"Index row {result.get('line_no')} was quarantined; projection impact is {result['projection_impact']}.",
            [row_identity] if row_identity else [],
        )

    current_projection_status = "evaluated"
    if projection_not_evaluated_ids or (unknown_projection_impact and ((root / "task.md").is_file() or current_surface_ids)):
        current_projection_status = "not_evaluated"
        add_issue(
            issues,
            "high",
            "current_projection_not_evaluated",
            "Malformed index history may affect the current projection; do not consume current traceability as pass.",
            sorted(projection_not_evaluated_ids),
            ["task.md"] if not projection_not_evaluated_ids and (root / "task.md").is_file() else [],
        )

    return malformed_results, legacy_results, projection_not_evaluated_ids, current_projection_status


def _collect_item_issues(
    root: Path,
    state: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
) -> None:
    for item_id, item in sorted(state.items()):
        item_type = str(item.get("type", ""))
        expected_prefix = PREFIXES.get(item_type)
        if expected_prefix and not item_id.startswith(f"{expected_prefix}-"):
            add_issue(
                issues,
                "medium",
                "prefix_mismatch",
                f"ID prefix does not match type {item_type}; expected {expected_prefix}-.",
                [item_id],
            )

        path_value = item.get("path")
        status = str(item.get("status", ""))
        if path_value and status not in {"deleted"}:
            path = root / str(path_value)
            if not path.exists() and status not in {"obsolete", "superseded"}:
                add_issue(issues, "high", "missing_path", "Indexed artifact path does not exist.", [item_id], [str(path_value)])
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            if fields.get("record_class") == "immutable_snapshot":
                snapshot_value = fields.get("snapshot_path")
                snapshot_path = root / str(snapshot_value) if snapshot_value else None
                if snapshot_path is None or not snapshot_path.is_file():
                    add_issue(issues, "medium", "immutable_snapshot_missing", "Historical record lacks its immutable snapshot body.", [item_id], [str(snapshot_value or path_value)])
                else:
                    snapshot_digest = sha256_file(snapshot_path)
                    if fields.get("snapshot_digest") and snapshot_digest != fields.get("snapshot_digest"):
                        add_issue(issues, "medium", "immutable_snapshot_digest_mismatch", "Historical snapshot body differs from its immutable digest.", [item_id], [str(snapshot_value)])
            elif path.is_file() and status not in NON_ACTIVE_STATUSES:
                digest = sha256_file(path)
                if item.get("content_sha256") and digest and digest != item.get("content_sha256"):
                    add_issue(
                        issues,
                        "medium",
                        "digest_mismatch",
                        "Indexed artifact content changed since its latest upsert event.",
                        [item_id],
                        [str(path_value)],
                    )

        parent_id = item.get("parent_id")
        if parent_id and parent_id not in state:
            add_issue(issues, "high", "missing_parent", "Artifact references a parent_id that is not indexed.", [item_id, str(parent_id)])

        for link in item.get("links", []):
            if not isinstance(link, dict):
                continue
            target_id = link.get("id")
            if not target_id:
                add_issue(issues, "medium", "empty_link_target", "Artifact contains a link without a target id.", [item_id])
                continue
            if target_id == item_id:
                add_issue(issues, "low", "self_link", "Artifact links to itself.", [item_id])
            elif target_id not in state:
                add_issue(issues, "high", "broken_link", "Artifact links to an unknown id.", [item_id, str(target_id)])



def _collect_relationship_issues(
    root: Path,
    state: dict[str, dict[str, Any]],
    active_tasks: list[str],
    current_task_alias_ids: list[str],
    issues: list[dict[str, Any]],
) -> list[str]:
    if len(active_tasks) > 1:
        add_issue(issues, "high", "multiple_active_tasks", "More than one task is marked active.", active_tasks)
    if (root / "task.md").is_file() and not current_task_alias_ids:
        add_issue(issues, "high", "current_canonical_id_missing", "Current task.md has no current canonical task ID.", paths=["task.md"])

    active_packs = [
        item_id
        for item_id, item in state.items()
        if item.get("type") == "task_pack" and item.get("status") == "active"
    ]
    if len(active_packs) > 1:
        add_issue(issues, "high", "multiple_active_task_packs", "More than one task pack is marked active.", active_packs)

    active_by_path: dict[tuple[str, str], list[str]] = {}
    for item_id, item in state.items():
        path_value = item.get("path")
        status = str(item.get("status", ""))
        if path_value and status not in NON_ACTIVE_STATUSES:
            active_by_path.setdefault((str(item.get("type", "")), str(path_value)), []).append(item_id)
    for (item_type, path_value), ids in sorted(active_by_path.items()):
        if len(ids) > 1:
            add_issue(
                issues,
                "medium",
                "duplicate_active_path",
                f"Multiple non-closed {item_type} IDs point to the same path.",
                ids,
                [path_value],
            )

    task_like_types = {"task_pack", "candidate_task", "task_miss", "execution", "audit", "validation", "environment", "issue", "issue_resolution"}
    for item_id, item in state.items():
        if item.get("type") not in task_like_types or item.get("status") in NON_ACTIVE_STATUSES:
            continue
        links = item.get("links", [])
        has_task_ref = item.get("parent_id") in current_task_alias_ids or any(
            link.get("id") in current_task_alias_ids or link.get("rel") in {"run_for", "audit_for", "miss_for", "validates", "issue_for", "tracks_task"}
            for link in links
            if isinstance(link, dict)
        )
        if current_task_alias_ids and not has_task_ref:
            add_issue(issues, "low", "unlinked_task_artifact", "Artifact is not linked to an active task.", [item_id])

    state_paths = {
        (str(item.get("type", "")), str(item.get("path", "")), item.get("content_sha256"))
        for item in state.values()
        if item.get("path")
    }
    for item_type, path_value, _status, _title in discover_standard_artifacts(root):
        digest = sha256_file(root / path_value)
        if (item_type, path_value, digest) not in state_paths:
            add_issue(issues, "medium", "unindexed_artifact", "Workspace artifact is not represented by a matching index event.", paths=[path_value])

    index_jsonl = jsonl_path(root)
    index_md = markdown_path(root)
    if not index_md.exists():
        add_issue(issues, "medium", "missing_markdown_index", ".task/index.md is missing.")
    elif index_jsonl.exists() and index_md.stat().st_mtime < index_jsonl.stat().st_mtime:
        add_issue(issues, "low", "stale_markdown_index", ".task/index.md is older than .task/index.jsonl.")

    return active_packs


def _partition_issues(
    root: Path,
    state: dict[str, dict[str, Any]],
    issues: list[dict[str, Any]],
    current_task_alias_ids: list[str],
    active_packs: list[str],
    current_projection_status: str,
) -> tuple[dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
    counts_by_type: dict[str, int] = {}
    for item in state.values():
        counts_by_type[str(item.get("type", "unknown"))] = counts_by_type.get(str(item.get("type", "unknown")), 0) + 1

    current_blocker_codes = {
        "current_canonical_id_missing",
        "multiple_active_tasks",
        "current_projection_not_evaluated",
    }
    active_ids = set(current_task_alias_ids)
    designated_surface_ids = active_ids | set(active_packs)
    designated_surface_paths = {
        (str(state[item_id].get("type", "")), str(state[item_id].get("path", "")))
        for item_id in designated_surface_ids
        if item_id in state and state[item_id].get("path")
    }
    if (root / "task.md").is_file():
        designated_surface_paths.add(("task", "task.md"))

    def duplicate_intersects_designated_surface(issue: dict[str, Any]) -> bool:
        if issue.get("code") != "duplicate_active_path" or current_projection_status != "evaluated":
            return False
        issue_ids = {str(item_id) for item_id in issue.get("ids") or []}
        if issue_ids.intersection(designated_surface_ids):
            return True
        return any(
            (
                str(state[item_id].get("type", "")),
                str(state[item_id].get("path", "")),
            )
            in designated_surface_paths
            for item_id in issue_ids
            if item_id in state
        )

    current_surface_blockers = [
        issue
        for issue in issues
        if issue.get("code") in current_blocker_codes
        or duplicate_intersects_designated_surface(issue)
        or (issue.get("code") == "broken_link" and active_ids.intersection(issue.get("ids") or []))
    ]
    historical_debt = [issue for issue in issues if issue not in current_surface_blockers]

    return counts_by_type, current_surface_blockers, historical_debt


def audit_index(
    root: Path,
    *,
    now_fn: Callable[[], str] = now_iso,
) -> dict[str, Any]:
    events, read_results = load_events_for_audit(root)
    state = merge_state(events)
    issues: list[dict[str, Any]] = []
    active_tasks, current_task_alias_ids, current_surface_ids = _current_surface(root, state)
    (
        malformed_results,
        legacy_results,
        projection_not_evaluated_ids,
        current_projection_status,
    ) = _classify_malformed_rows(root, read_results, current_surface_ids, issues)
    _collect_item_issues(root, state, issues)
    active_packs = _collect_relationship_issues(
        root, state, active_tasks, current_task_alias_ids, issues
    )
    counts_by_type, current_surface_blockers, historical_debt = _partition_issues(
        root,
        state,
        issues,
        current_task_alias_ids,
        active_packs,
        current_projection_status,
    )
    return {
        "format_version": INDEX_FORMAT_VERSION,
        "schema_version": INDEX_SCHEMA_VERSION,
        "workspace": str(root),
        "audited_at": now_fn(),
        "audit_evidence_status": (
            "not_evaluated_current_projection"
            if current_projection_status == "not_evaluated"
            else "evaluated"
            if events or discover_standard_artifacts(root)
            else "not_evaluated_no_artifacts"
        ),
        "current_projection_status": current_projection_status,
        "projection_completeness": "complete" if not malformed_results else "incomplete",
        "projection_not_evaluated_ids": sorted(projection_not_evaluated_ids),
        "legacy_normalized_count": len(legacy_results),
        "malformed_row_count": len(malformed_results),
        "raw_row_count": len(read_results),
        "index_read_results": [
            {key: value for key, value in result.items() if not key.startswith("_")}
            for result in read_results
            if result.get("migration_status") != "current"
        ][:100],
        "index_read_results_truncated_count": max(
            0,
            len([result for result in read_results if result.get("migration_status") != "current"]) - 100,
        ),
        "event_count": len(events),
        "artifact_count": len(state),
        "counts_by_type": counts_by_type,
        "issue_count": len(issues),
        "issues": issues,
        "current_surface_blockers": current_surface_blockers,
        "historical_debt": historical_debt,
    }
def write_audit_report(root: Path, audit: dict[str, Any]) -> Path:
    report_dir = task_dir(root) / "id_audit"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-id-consistency-audit.md"
    lines = [
        "# ID Consistency Audit",
        "",
        f"- Timestamp: {audit['audited_at']}",
        f"- Workspace: {audit['workspace']}",
        f"- Events: {audit['event_count']}",
        f"- Artifacts: {audit['artifact_count']}",
        f"- Issues: {audit['issue_count']}",
        "",
        "## Counts By Type",
        "",
    ]
    for item_type, count in sorted(audit["counts_by_type"].items()):
        lines.append(f"- {item_type}: {count}")
    lines.extend(["", "## Issues", ""])
    if audit["issues"]:
        for issue in audit["issues"]:
            ids = ", ".join(issue.get("ids", [])) or "N/A"
            paths = ", ".join(issue.get("paths", [])) or "N/A"
            lines.extend(
                [
                    f"- [{issue['severity']}] {issue['code']}: {issue['message']}",
                    f"  IDs: {ids}",
                    f"  Paths: {paths}",
                ]
            )
    else:
        lines.append("- None")
    atomic_write_text(report_path, "\n".join(lines).rstrip() + "\n")
    return report_path


def severity_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for issue in issues:
        severity = str(issue.get("severity") or "unknown")
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def issue_matches_focus(issue: dict[str, Any], focus_paths: list[str]) -> bool:
    if not focus_paths:
        return True
    paths = [str(path) for path in issue.get("paths", []) if path is not None]
    ids = [str(item_id) for item_id in issue.get("ids", []) if item_id is not None]
    haystack = paths + ids
    for focus in focus_paths:
        focus = focus.strip()
        if not focus:
            continue
        for value in haystack:
            if value == focus or value.startswith(focus.rstrip("/") + "/") or focus in value:
                return True
    return False


def summarize_audit(audit: dict[str, Any], focus_paths: list[str], limit: int = 20) -> dict[str, Any]:
    issues = [issue for issue in audit.get("issues", []) if isinstance(issue, dict)]
    focused = [issue for issue in issues if issue_matches_focus(issue, focus_paths)]
    return {
        "workspace": audit.get("workspace"),
        "audited_at": audit.get("audited_at"),
        "summary_only": True,
        "focus_paths": [path for path in focus_paths if path],
        "audit_evidence_status": audit.get("audit_evidence_status"),
        "current_projection_status": audit.get("current_projection_status"),
        "projection_completeness": audit.get("projection_completeness"),
        "projection_not_evaluated_ids": audit.get("projection_not_evaluated_ids", []),
        "legacy_normalized_count": audit.get("legacy_normalized_count", 0),
        "malformed_row_count": audit.get("malformed_row_count", 0),
        "raw_row_count": audit.get("raw_row_count", audit.get("event_count")),
        "event_count": audit.get("event_count"),
        "artifact_count": audit.get("artifact_count"),
        "counts_by_type": audit.get("counts_by_type", {}),
        "issue_count": audit.get("issue_count", len(issues)),
        "severity_counts": severity_counts(issues),
        "focused_issue_count": len(focused),
        "focused_severity_counts": severity_counts(focused),
        "focused_issues": focused[:limit],
        "omitted_issue_count": max(0, len(issues) - min(len(focused), limit)) if focus_paths else max(0, len(issues) - limit),
        "historical_debt_note": "summary_only preserves global counts while limiting emitted issues to focus paths; run audit without --summary-only for the full issue list.",
    }
