from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable

from .constants import CANONICAL_STEPS


RETENTION_OUTPUT_LIMIT = 50
# ponytail: closeout stays bounded; raise these only after measured real-workspace need.
RETENTION_SCAN_ENTRY_LIMIT = 100_000
RETENTION_HASH_FILE_LIMIT = 200
RETENTION_HASH_BYTE_LIMIT = 64 * 1024 * 1024
_PACKET_DIGEST = re.compile(
    r"^(?:result|preparation)-.+-([0-9a-f]{64})\.json$"
)
_BUDGET_FIELDS = ("max_cycle_files", "max_cycle_bytes", "max_age_days")


def values(value: Any) -> list[str]:
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                candidate = item.get("path") or item.get("id") or item.get("issue_id")
                if candidate is not None:
                    result.append(str(candidate))
                else:
                    result.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            elif item is not None and str(item).strip():
                result.append(str(item))
        return result
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)] if value else []
    if value is not None and str(value).strip():
        return [str(value)]
    return []


def unique(items: Iterable[Any]) -> list[str]:
    return sorted(
        {str(item) for item in items if item is not None and str(item).strip()}
    )


def collect_fields(events: list[dict[str, Any]], fields: Iterable[str]) -> list[str]:
    collected: list[str] = []
    for event in events:
        for field in fields:
            collected.extend(values(event.get(field)))
    return unique(collected)


def evidence_paths(events: list[dict[str, Any]]) -> list[str]:
    collected = collect_fields(
        events, ("evidence_paths", "artifacts", "artifact_paths", "logs")
    )
    for event in events:
        for ref in event.get("artifact_refs") or []:
            if isinstance(ref, dict) and ref.get("path"):
                collected.append(str(ref["path"]))
        for field in ("report_path", "log_path", "dashboard_path"):
            if event.get(field):
                collected.append(str(event[field]))
    return unique(collected)


def long_run_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for event in events:
        event_kind = str(event.get("event_kind") or "").lower()
        role = str(event.get("long_run_role") or "").lower()
        if (
            event.get("long_run_branch")
            or event_kind.startswith("long_run_")
            or role in {"launch", "monitor", "harvest", "finalize"}
        ):
            result.append(event)
    return result


def latest_value(
    events: list[dict[str, Any]], *fields: str, default: Any = None
) -> Any:
    for event in reversed(events):
        for field in fields:
            value = event.get(field)
            if value is not None and value != "":
                return value
    return default


def event_malformed_reasons(event: dict[str, Any], cycle_id: str) -> list[str]:
    reasons: list[str] = []
    version = event.get("format_version", 0)
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version not in {0, 1, 2}
    ):
        reasons.append("unsupported_format_version")
    step = event.get("step")
    if not isinstance(step, str) or not step.strip():
        reasons.append("missing_step")
    elif step not in CANONICAL_STEPS:
        reasons.append("noncanonical_step")
    if not isinstance(event.get("status"), str) or not str(event.get("status")).strip():
        reasons.append("missing_status")
    event_cycle_id = event.get("cycle_id")
    if event_cycle_id is not None and str(event_cycle_id) != cycle_id:
        reasons.append("cycle_id_mismatch")
    if version in {1, 2} and event_cycle_id is None:
        reasons.append("missing_cycle_id")
    if version in {1, 2} and not str(event.get("event_id") or "").strip():
        reasons.append("missing_event_id")
    if version == 2 and event.get("event_kind") != "compiled_stage_result_ref":
        reasons.append("unsupported_compact_event_kind")
    return reasons


def _retention_policy(events: list[dict[str, Any]]) -> tuple[str, dict[str, int | None]]:
    policy: Any = None
    supplied = False
    for event in reversed(events):
        if "record_retention_policy" in event:
            policy = event["record_retention_policy"]
            supplied = True
            break
    empty = {field: None for field in _BUDGET_FIELDS}
    if not supplied:
        return "absent", empty
    if not isinstance(policy, dict) or not isinstance(policy.get("budgets"), dict):
        return "malformed", empty
    budgets = policy["budgets"]
    configured = {field: budgets.get(field) for field in _BUDGET_FIELDS}
    if not set(_BUDGET_FIELDS) <= set(budgets) or any(
        isinstance(configured[field], bool)
        or not isinstance(configured[field], int)
        or configured[field] < 1
        for field in _BUDGET_FIELDS
    ):
        return "malformed", empty
    return "configured", configured


def _age_anchor(events: list[dict[str, Any]]) -> tuple[str | None, float | None]:
    if not events:
        return None, None
    raw = str(events[-1].get("created_at") or "").strip()
    if not raw:
        return None, None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw, None
    if parsed.tzinfo is None:
        return raw, None
    return raw, parsed.timestamp()


def _protected_category(relative: Path) -> str:
    lowered = tuple(part.lower() for part in relative.parts)
    name = relative.name.lower()
    if name == "stage.jsonl" or "ledger" in lowered:
        return "ledger"
    if "packets" in lowered or name.startswith(("result-", "preparation-")):
        return "compact_result_cas"
    if any("finalization" in part for part in lowered):
        return "finalization"
    if any("authority" in part for part in lowered):
        return "authority"
    if any("settlement" in part for part in lowered):
        return "settlement"
    return "other_cycle_evidence"


def _hash_regular_file(path: Path, max_bytes: int) -> tuple[str, int] | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
            return None
        digest = hashlib.sha256()
        consumed = 0
        while chunk := os.read(descriptor, min(1024 * 1024, max_bytes + 1 - consumed)):
            consumed += len(chunk)
            if consumed > max_bytes:
                return None
            digest.update(chunk)
        return digest.hexdigest(), consumed
    finally:
        os.close(descriptor)


def _duplicate_packet_summary(
    candidates: list[tuple[str, Path, str, int]],
    limit: int,
) -> dict[str, Any]:
    by_binding: dict[str, list[tuple[Path, str, int]]] = {}
    for binding, path, display_path, size_bytes in candidates:
        by_binding.setdefault(binding, []).append((path, display_path, size_bytes))
    groups: list[dict[str, Any]] = []
    hashed_files = hashed_bytes = hash_truncated_count = 0
    exhausted = False
    for binding, paths in sorted(by_binding.items()):
        if len(paths) < 2:
            continue
        verified: dict[tuple[str, int], list[str]] = {}
        for index, (path, display_path, size_bytes) in enumerate(paths):
            if (
                hashed_files >= RETENTION_HASH_FILE_LIMIT
                or hashed_bytes + size_bytes > RETENTION_HASH_BYTE_LIMIT
            ):
                hash_truncated_count += len(paths) - index
                exhausted = True
                break
            observed = _hash_regular_file(
                path, RETENTION_HASH_BYTE_LIMIT - hashed_bytes
            )
            if observed is not None:
                hashed_files += 1
                hashed_bytes += observed[1]
                verified.setdefault(observed, []).append(display_path)
            else:
                hash_truncated_count += 1
        for (content_sha256, size_bytes), copies in verified.items():
            if len(copies) < 2:
                continue
            groups.append(
                {
                    "binding_sha256": binding,
                    "content_sha256": content_sha256,
                    "copy_count": len(copies),
                    "bytes_per_copy": size_bytes,
                    "potential_reclaim_bytes": (len(copies) - 1) * size_bytes,
                    "sample_paths": sorted(copies)[:3],
                    "protected": True,
                }
            )
        if exhausted:
            hash_truncated_count += sum(
                len(other)
                for other_binding, other in by_binding.items()
                if other_binding > binding and len(other) > 1
            )
            break
    groups.sort(
        key=lambda item: (
            -int(item["potential_reclaim_bytes"]),
            str(item["content_sha256"]),
        )
    )
    return {
        "status": "partial" if hash_truncated_count else "complete",
        "group_count": len(groups),
        "potential_reclaim_bytes": sum(
            int(item["potential_reclaim_bytes"]) for item in groups
        ),
        "groups": groups[:limit],
        "truncated_count": max(0, len(groups) - limit) + hash_truncated_count,
        "hash_truncated_count": hash_truncated_count,
        "hashed_file_count": hashed_files,
        "hashed_bytes": hashed_bytes,
    }


def _empty_retention_summary(
    policy_status: str,
    budget: dict[str, int | None],
    anchor_text: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "dry_run",
        "scope": ".task/cycle",
        "inventory_status": "not_evaluated",
        "policy_status": policy_status,
        "budget_status": "not_configured" if policy_status == "absent" else "malformed",
        "retention_fail_quiet": True,
        "age_anchor": anchor_text,
        "budget": budget,
        "overage": {
            "files": None,
            "bytes": None,
            "age_expired_files": None,
            "age_expired_bytes": None,
        },
        "inventory": {
            "file_count": None,
            "bytes": None,
            "packet_count": None,
            "packet_bytes": None,
            "skipped_symlink_count": 0,
            "scan_error_count": 0,
            "truncated_count": 0,
        },
        "duplicate_packets": {
            "status": "complete",
            "group_count": 0,
            "potential_reclaim_bytes": 0,
            "groups": [],
            "truncated_count": 0,
            "hash_truncated_count": 0,
            "hashed_file_count": 0,
            "hashed_bytes": 0,
        },
        "regenerable_intermediates": {
            "file_count": 0,
            "bytes": 0,
            "items": [],
            "truncated_count": 0,
        },
        "protected": {"file_count": 0, "bytes": 0, "categories": {}},
        "actions": {"archive": "not_implemented", "delete": "not_implemented", "apply": "not_implemented"},
        "archive_apply_status": "not_attempted",
        "deletion_authority": "not_requested",
    }


def _apply_retention_budget(
    result: dict[str, Any],
    budget: dict[str, int | None],
    inventory_complete: bool,
    totals: tuple[int, int, int, int],
    cutoff: float | None,
) -> None:
    if result["policy_status"] != "configured" or not inventory_complete:
        return
    total_files, total_bytes, expired_files, expired_bytes = totals
    max_files = budget["max_cycle_files"]
    max_bytes = budget["max_cycle_bytes"]
    result["overage"] = {
        "files": max(0, total_files - max_files) if max_files is not None else None,
        "bytes": max(0, total_bytes - max_bytes) if max_bytes is not None else None,
        "age_expired_files": expired_files if cutoff is not None else None,
        "age_expired_bytes": expired_bytes if cutoff is not None else None,
    }
    result["budget_status"] = "evaluated"
    result["retention_fail_quiet"] = False


def _is_dashboard_self_effect(cycle_root: Path, directory: Path, name: str, cycle_id: str | None) -> bool:
    return name == "dashboard.md" or bool(
        cycle_id
        and directory == cycle_root / cycle_id / "packets"
        and name.startswith("result-dashboard-")
    )


def retention_inventory(
    workspace_root: Path | None, events: list[dict[str, Any]],
    *, cycle_id: str | None = None, max_items: int = RETENTION_OUTPUT_LIMIT,
) -> dict[str, Any]:
    """Return a bounded, read-only closeout inventory for `.task/cycle`."""
    limit = max(0, min(max_items, RETENTION_OUTPUT_LIMIT))
    policy_status, budget = _retention_policy(events)
    anchor_text, anchor_timestamp = _age_anchor(events)
    result = _empty_retention_summary(policy_status, budget, anchor_text)
    if workspace_root is None:
        return result
    try:
        root = workspace_root.resolve(strict=True)
    except OSError:
        return result
    task_root = root / ".task"
    cycle_root = task_root / "cycle"
    if task_root.is_symlink() or cycle_root.is_symlink():
        result["inventory_status"] = "blocked_symlink_scope"
        result["inventory"]["skipped_symlink_count"] = 1
        return result
    total_files = total_bytes = packet_count = packet_bytes = 0
    expired_files = expired_bytes = skipped_symlinks = 0
    scan_errors: list[OSError] = []
    packet_candidates: list[tuple[str, Path, str, int]] = []
    regenerable: list[dict[str, Any]] = []
    protected: dict[str, dict[str, int]] = {}
    scanned_entries = scan_truncated_count = 0
    max_age_days = budget["max_age_days"]
    cutoff = anchor_timestamp - max_age_days * 86400 if (
        anchor_timestamp is not None and max_age_days is not None
    ) else None
    if cycle_root.exists():
        directories = [cycle_root]
        while directories and not scan_truncated_count:
            directory_path = directories.pop()
            try:
                entries = os.scandir(directory_path)
            except OSError as exc:
                scan_errors.append(exc)
                continue
            with entries:
                for entry in entries:
                    if scanned_entries >= RETENTION_SCAN_ENTRY_LIMIT:
                        scan_truncated_count = 1
                        break
                    scanned_entries += 1
                    path = Path(entry.path)
                    if entry.is_symlink():
                        skipped_symlinks += 1
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if cycle_id and directory_path == cycle_root / cycle_id and (
                                entry.name == "compiler"
                            ):
                                continue
                            directories.append(path)
                            continue
                    except OSError as exc:
                        scan_errors.append(exc)
                        continue
                    name = entry.name
                    if _is_dashboard_self_effect(cycle_root, directory_path, name, cycle_id):
                        continue
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                    except OSError as exc:
                        scan_errors.append(exc)
                        continue
                    if not stat.S_ISREG(metadata.st_mode):
                        continue
                    relative_cycle = path.relative_to(cycle_root)
                    display_path = path.relative_to(root).as_posix()
                    total_files += 1
                    total_bytes += metadata.st_size
                    if cutoff is not None and metadata.st_mtime < cutoff:
                        expired_files += 1
                        expired_bytes += metadata.st_size
                    if "packets" in relative_cycle.parts:
                        packet_count += 1
                        packet_bytes += metadata.st_size
                        match = _PACKET_DIGEST.fullmatch(name)
                        if match:
                            packet_candidates.append(
                                (
                                    match.group(1),
                                    path,
                                    display_path,
                                    metadata.st_size,
                                )
                            )
                    if name == "current_stage.json":
                        regenerable.append(
                            {
                                "kind": "current_stage_projection",
                                "path": display_path,
                                "size_bytes": metadata.st_size,
                            }
                        )
                        continue
                    category = _protected_category(relative_cycle)
                    counts = protected.setdefault(
                        category, {"file_count": 0, "bytes": 0}
                    )
                    counts["file_count"] += 1
                    counts["bytes"] += metadata.st_size
    duplicate_summary = _duplicate_packet_summary(packet_candidates, limit)
    inventory_complete = not (scan_errors or scan_truncated_count)
    result["inventory_status"] = "complete" if inventory_complete else "partial"
    result["inventory"] = {
        "file_count": total_files,
        "bytes": total_bytes,
        "packet_count": packet_count,
        "packet_bytes": packet_bytes,
        "skipped_symlink_count": skipped_symlinks,
        "scan_error_count": len(scan_errors),
        "truncated_count": scan_truncated_count,
    }
    result["duplicate_packets"] = duplicate_summary
    regenerable.sort(key=lambda item: str(item["path"]))
    result["regenerable_intermediates"] = {
        "file_count": len(regenerable),
        "bytes": sum(int(item["size_bytes"]) for item in regenerable),
        "items": regenerable[:limit],
        "truncated_count": max(0, len(regenerable) - limit),
    }
    result["protected"] = {
        "file_count": sum(item["file_count"] for item in protected.values()),
        "bytes": sum(item["bytes"] for item in protected.values()),
        "categories": dict(sorted(protected.items())),
    }
    _apply_retention_budget(
        result,
        budget,
        inventory_complete,
        (total_files, total_bytes, expired_files, expired_bytes),
        cutoff,
    )
    return result
