"""Task-pack store selection and integrity checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from . import replacement_engine as task_pack_replacement
from . import mutation_journal

from .packet_io import load_json
from .legacy_retirement import (
    active_retirement_for_pack,
    retirement_store_projection,
)
from .receipts import pack_paths
from .state_machine import derived_operational_status
from .storage import rel_path
from .validation import validate_pack


LIVE_PACK_STATUSES = {"active", "blocked"}

def status_from_findings(findings: list[dict[str, Any]]) -> str:
    if any(item.get("severity") == "block" for item in findings):
        return "block"
    if findings:
        return "warn"
    return "ok"


def _pack_store_projection(
    root: Path,
    retirement: dict[str, Any] | None = None,
) -> tuple[list[tuple[Path, dict[str, Any]]], list[dict[str, Any]]]:
    retirement = retirement or retirement_store_projection(root)
    live: list[tuple[Path, dict[str, Any]]] = []
    findings: list[dict[str, Any]] = []
    for path in pack_paths(root):
        try:
            data = load_json(path)
        except SystemExit as exc:
            findings.append(
                {
                    "severity": "block",
                    "code": "task_pack_json_invalid",
                    "message": str(exc),
                    "evidence": {"pack_ref": rel_path(root, path)},
                }
            )
            continue
        blocking = [
            item for item in validate_pack(data, path) if item.get("severity") == "block"
        ]
        if blocking:
            settled = active_retirement_for_pack(root, path, retirement)
            if settled is not None:
                continue
            findings.append(
                {
                    "severity": "block",
                    "code": "task_pack_state_invalid",
                    "message": "Task-pack store contains a pack that requires lifecycle or contract repair.",
                    "evidence": {
                        "pack_ref": rel_path(root, path),
                        "declared_status": data.get("status"),
                        "operational_status": derived_operational_status(data),
                        "finding_codes": sorted(
                            {str(item.get("code") or "unknown_pack_finding") for item in blocking}
                        ),
                    },
                }
            )
            continue
        if derived_operational_status(data) in LIVE_PACK_STATUSES:
            live.append((path, data))
    return live, findings


def active_pack_candidates(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    return _pack_store_projection(root)[0]


def task_pack_store_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    retirement = retirement_store_projection(root)
    findings.extend(retirement["findings"])
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
    mutation_pending = mutation_journal.pending_transaction_ids(root)
    if mutation_pending:
        findings.append(
            {
                "severity": "block",
                "code": "mutation_transaction_pending",
                "message": "A prepared task-pack mutation requires forward recovery before other reads or mutations.",
                "evidence": {"transaction_ids": mutation_pending},
            }
        )
    active, pack_findings = _pack_store_projection(root, retirement)
    findings.extend(pack_findings)
    if len(active) > 1:
        findings.append(
            {
                "severity": "block",
                "code": "multiple_active_task_packs",
                "message": "Task-pack store must contain at most one live active-or-blocked pack.",
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
