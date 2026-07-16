"""Task-state workspace discovery and dry-run/apply scan orchestration."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .artifacts import (
    discover_standard_artifacts,
    extract_advice_fields,
    extract_issue_fields,
    extract_schema_fields,
    extract_task_pack_fields,
    select_external_advice_scan_id,
)
from .contracts import (
    INDEX_FORMAT_VERSION,
    INDEX_SCHEMA_VERSION,
    TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES,
)
from .events import (
    load_events,
    load_events_read_only,
    merge_state,
    stable_path_id,
)
from .render import _markdown_projection_matches, rebuild_markdown
from .storage import (
    ensure_index,
    jsonl_path,
    markdown_path,
    now_iso,
    rel_path,
    sha256_file,
)
from .write_service import upsert_item


Artifact = tuple[str, str, str, str]


@dataclass
class _ScanState:
    root: Path
    dry_run: bool
    now_fn: Callable[[], str]
    artifacts: list[Artifact]
    had_jsonl: bool
    had_markdown: bool
    source_index_sha256: str | None
    state: dict[str, dict[str, Any]]
    projected_state: dict[str, dict[str, Any]]
    projected_timestamp: str
    projected_pack_id_paths: dict[str, str]
    added: list[dict[str, Any]] = field(default_factory=list)
    pending: list[dict[str, Any]] = field(default_factory=list)
    markdown_changed: bool = False
    projected_markdown_forced: bool = False


@dataclass(frozen=True)
class _ArtifactUpdate:
    item_type: str
    path_value: str
    status: str
    title: str
    digest: str | None
    item_id: str | None
    fields: dict[str, Any] | None
    retire_alias_ids: list[str]


def _artifact_anchor(root: Path, artifacts: list[Artifact]) -> list[tuple[str, str, str, str, str | None]]:
    return [
        (item_type, path_value, status, title, sha256_file(root / path_value))
        for item_type, path_value, status, title in artifacts
    ]


def _validated_artifacts(
    root: Path,
    artifacts: list[Artifact],
    *,
    dry_run: bool,
    now_fn: Callable[[], str],
) -> list[Artifact]:
    for canonical_path in (jsonl_path(root), markdown_path(root)):
        if canonical_path.exists() and not canonical_path.is_file():
            raise ValueError(f"Task-state canonical path is not a regular file: {canonical_path}")
    if dry_run:
        return artifacts
    anchor = _artifact_anchor(root, artifacts)
    preflight = scan_artifacts(root, dry_run=True, _now_fn=now_fn)
    current = discover_standard_artifacts(root)
    if _artifact_anchor(root, current) != anchor:
        raise ValueError("Workspace artifacts changed during task-state scan preflight")
    if preflight.get("source_index_sha256") != sha256_file(jsonl_path(root)):
        raise ValueError("Task-state index changed after scan preflight")
    return current


def _pack_paths(state: dict[str, dict[str, Any]]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for item in state.values():
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        pack_id = str(fields.get("pack_id") or "")
        path_value = str(item.get("path") or "")
        if item.get("type") != "task_pack" or not pack_id or not path_value:
            continue
        previous = paths.setdefault(pack_id, path_value)
        if previous != path_value:
            raise ValueError(f"Task pack id {pack_id!r} is already bound to another artifact path")
    return paths


def _prepare_scan(
    root: Path,
    artifacts: list[Artifact],
    *,
    dry_run: bool,
    now_fn: Callable[[], str],
) -> _ScanState:
    artifacts = _validated_artifacts(root, artifacts, dry_run=dry_run, now_fn=now_fn)
    had_jsonl = jsonl_path(root).is_file()
    had_markdown = markdown_path(root).is_file()
    source_sha: str | None = None
    if dry_run:
        events, source_sha = load_events_read_only(root)
    else:
        ensure_index(root)
        events = load_events(root)
    state = merge_state(events)
    projected = copy.deepcopy(state)
    return _ScanState(
        root=root,
        dry_run=dry_run,
        now_fn=now_fn,
        artifacts=artifacts,
        had_jsonl=had_jsonl,
        had_markdown=had_markdown,
        source_index_sha256=source_sha,
        state=state,
        projected_state=projected,
        projected_timestamp=now_fn(),
        projected_pack_id_paths=_pack_paths(projected),
    )


def _metadata_for(
    scan: _ScanState,
    item_type: str,
    path_value: str,
    status: str,
) -> tuple[str | None, dict[str, Any] | None, list[str]]:
    identity_state = scan.projected_state if scan.dry_run else scan.state
    item_id = stable_path_id(identity_state, item_type, path_value)
    fields: dict[str, Any] | None = None
    retire_alias_ids: list[str] = []
    path = scan.root / path_value
    if item_type in {"schema_contract", "schema_map"}:
        fields = extract_schema_fields(path)
    elif item_type == "task_pack":
        fields = extract_task_pack_fields(path)
        if fields.get("render_path"):
            fields["render_path"] = rel_path(scan.root, Path(fields["render_path"]))
        pack_id = fields.get("pack_id")
        if pack_id:
            previous = scan.projected_pack_id_paths.setdefault(str(pack_id), path_value)
            if previous != path_value:
                raise ValueError(f"Task pack id {pack_id!r} is already bound to another artifact path")
            for existing_id, existing in identity_state.items():
                existing_fields = existing.get("fields") if isinstance(existing.get("fields"), dict) else {}
                if existing.get("type") == "task_pack" and existing_fields.get("pack_id") == pack_id:
                    item_id = existing_id
                    break
    elif item_type in {"issue", "issue_resolution", "issue_map"}:
        fields = extract_issue_fields(path)
    elif item_type == "external_advice":
        fields = extract_advice_fields(path)
        if fields is not None:
            fields["status"] = status
        advice_id = fields.get("advice_id") if fields else None
        if advice_id:
            item_id, retire_alias_ids = select_external_advice_scan_id(
                scan.root, identity_state, path_value, str(advice_id)
            )
    return item_id, fields, retire_alias_ids


def _artifact_update(scan: _ScanState, artifact: Artifact) -> _ArtifactUpdate | None:
    item_type, path_value, status, title = artifact
    identity_state = scan.projected_state if scan.dry_run else scan.state
    digest = sha256_file(scan.root / path_value)
    item_id, fields, retire_alias_ids = _metadata_for(scan, item_type, path_value, status)
    existing = identity_state.get(item_id) if item_id else None
    existing_fields = (
        existing.get("fields")
        if isinstance(existing, dict) and isinstance(existing.get("fields"), dict)
        else {}
    )
    completed_alias = bool(
        item_type == "task"
        and path_value == "task.md"
        and existing
        and existing.get("status") in TASK_SCAN_PRESERVED_NONEXECUTABLE_STATUSES
        and existing_fields.get("record_class") == "mutable_alias"
        and existing_fields.get("canonical_id") == item_id
    )
    if completed_alias:
        if existing.get("content_sha256") != digest:
            raise ValueError(
                "A non-executable current task alias changed body without an explicit lifecycle switch"
            )
        status = str(existing.get("status"))
    unchanged = bool(
        existing
        and existing.get("path") == path_value
        and existing.get("content_sha256") == digest
        and existing.get("status") == status
        and existing.get("title") == title
        and all(existing_fields.get(key) == value for key, value in (fields or {}).items())
    )
    if unchanged:
        return None
    return _ArtifactUpdate(
        item_type, path_value, status, title, digest, item_id, fields, retire_alias_ids
    )


def _project_update(scan: _ScanState, update: _ArtifactUpdate) -> None:
    scan.pending.append({
        "type": update.item_type,
        "path": update.path_value,
        "status": update.status,
        "title": update.title,
        "stable_id": update.item_id,
        "identity_status": "existing" if update.item_id else "would_allocate_on_apply",
        "content_sha256": update.digest,
    })
    if update.item_id:
        projected = copy.deepcopy(scan.projected_state.get(update.item_id) or {})
        projected.update({
            "type": update.item_type,
            "status": update.status,
            "path": update.path_value,
            "title": update.title,
            "updated_at": scan.projected_timestamp,
            "content_sha256": update.digest,
        })
        if update.fields:
            projected.setdefault("fields", {}).update(update.fields)
        scan.projected_state[update.item_id] = projected
        for alias_id in update.retire_alias_ids:
            if alias_id in scan.projected_state:
                scan.projected_state[alias_id]["status"] = "superseded"
                scan.projected_state[alias_id]["updated_at"] = scan.projected_timestamp
                scan.projected_markdown_forced = True
    else:
        scan.projected_markdown_forced = True


def _apply_update(scan: _ScanState, update: _ArtifactUpdate) -> None:
    result = upsert_item(
        scan.root,
        update.item_type,
        update.path_value,
        update.status,
        title=update.title,
        item_id=update.item_id,
        fields=update.fields,
        replace_existing=False,
        retire_alias_ids=update.retire_alias_ids,
        _now_fn=scan.now_fn,
    )
    scan.added.append(result["event"])
    scan.markdown_changed = scan.markdown_changed or bool(result.get("index_md_changed"))
    scan.state = merge_state(load_events(scan.root))


def _dry_run_result(scan: _ScanState) -> dict[str, Any]:
    markdown_matches = _markdown_projection_matches(scan.root, scan.projected_state)
    has_context = (
        bool(scan.artifacts)
        or scan.source_index_sha256 is not None
        or markdown_path(scan.root).is_file()
    )
    jsonl_change = bool(scan.pending) or (scan.source_index_sha256 is None and has_context)
    markdown_change = has_context and (
        scan.projected_markdown_forced or not markdown_matches
    )
    if sha256_file(jsonl_path(scan.root)) != scan.source_index_sha256:
        raise ValueError("Task-state index changed during read-only scan planning")
    return {
        "mode": "dry_run",
        "mutation_performed": False,
        "indexed_events": 0,
        "events": [],
        "planned_artifact_updates": len(scan.pending),
        "pending_artifacts": scan.pending,
        "would_change": bool(scan.pending) or jsonl_change or markdown_change,
        "index_jsonl_would_change": jsonl_change,
        "index_md_would_change": markdown_change,
        "source_index_sha256": scan.source_index_sha256,
        "source_index_md_sha256": sha256_file(markdown_path(scan.root)),
        "scan_evidence_status": "evaluated" if scan.artifacts else "not_evaluated_no_artifacts",
    }


def _apply_result(scan: _ScanState) -> dict[str, Any]:
    rebuild = rebuild_markdown(scan.root, now_fn=scan.now_fn)
    rebuild["index_md_changed"] = scan.markdown_changed or bool(rebuild.get("index_md_changed"))
    index_created = not scan.had_jsonl and jsonl_path(scan.root).is_file()
    return {
        "mode": "apply",
        "mutation_performed": index_created or bool(scan.added) or bool(rebuild.get("index_md_changed")),
        "index_jsonl_changed": index_created or bool(scan.added),
        "indexed_events": len(scan.added),
        "events": scan.added,
        "scan_evidence_status": "evaluated" if scan.artifacts else "not_evaluated_no_artifacts",
        **rebuild,
    }


def scan_artifacts(
    root: Path,
    *,
    dry_run: bool = False,
    _now_fn: Callable[[], str] = now_iso,
) -> dict[str, Any]:
    root = root.resolve()
    artifacts = discover_standard_artifacts(root)
    for canonical_path in (jsonl_path(root), markdown_path(root)):
        if canonical_path.exists() and not canonical_path.is_file():
            raise ValueError(
                f"Task-state canonical path is not a regular file: {canonical_path}"
            )
    had_jsonl = jsonl_path(root).is_file()
    had_markdown = markdown_path(root).is_file()
    if not dry_run and not artifacts and not had_jsonl and not had_markdown:
        return {
            "mode": "apply",
            "mutation_performed": False,
            "indexed_events": 0,
            "events": [],
            "index_md": None,
            "index_md_changed": False,
            "artifact_count": 0,
            "format_version": INDEX_FORMAT_VERSION,
            "schema_version": INDEX_SCHEMA_VERSION,
            "scan_evidence_status": "not_evaluated_no_artifacts",
        }
    scan = _prepare_scan(root, artifacts, dry_run=dry_run, now_fn=_now_fn)
    for artifact in scan.artifacts:
        update = _artifact_update(scan, artifact)
        if update is None:
            continue
        if scan.dry_run:
            _project_update(scan, update)
        else:
            _apply_update(scan, update)
    return _dry_run_result(scan) if scan.dry_run else _apply_result(scan)
