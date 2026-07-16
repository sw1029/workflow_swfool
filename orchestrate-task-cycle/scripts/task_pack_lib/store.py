"""Task-pack store selection and integrity checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import task_pack_replacement

from .packet_io import load_json
from .receipts import pack_paths
from .storage import rel_path

def status_from_findings(findings: list[dict[str, Any]]) -> str:
    if any(item.get("severity") == "block" for item in findings):
        return "block"
    if findings:
        return "warn"
    return "ok"


def active_pack_candidates(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path, data)
        for path in pack_paths(root)
        for data in [load_json(path)]
        if data.get("status") == "active"
    ]


def task_pack_store_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    pending = task_pack_replacement.pending_transaction_ids(root)
    if pending:
        findings.append(
            {
                "severity": "block",
                "code": "replacement_transaction_pending",
                "message": "A prepared task-pack replacement requires forward recovery before other reads or mutations.",
                "evidence": {"transaction_ids": pending},
            }
        )
    active = active_pack_candidates(root)
    if len(active) > 1:
        findings.append(
            {
                "severity": "block",
                "code": "multiple_active_task_packs",
                "message": "Task-pack store must contain at most one active pack.",
                "evidence": {"active_pack_refs": [rel_path(root, path) for path, _data in active]},
            }
        )
    return findings


def active_pack(root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    findings = task_pack_store_findings(root)
    if findings:
        raise SystemExit(findings[0]["message"])
    active = active_pack_candidates(root)
    return active[0] if active else (None, None)

