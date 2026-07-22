"""Discover and hand off repository-owned workflow adapters without loading them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from .repo_skill_adapter_handoff import registered_adapter_handoff
from .repo_skill_adapter_manifest import (
    COMPONENT_PATH_FIELDS as COMPONENT_PATH_FIELDS,
    _adapter_row,
    _object_sha256,
    _safe_regular_file,
)


def scan_repo_skill_adapters(
    root: str | Path, *, cycle_id: str = "unknown"
) -> dict[str, Any]:
    repo_root = Path(root).expanduser().resolve(strict=True)
    skill_root = repo_root / ".codex" / "skills"
    manifests: list[Path] = []
    if skill_root.is_dir() and not skill_root.is_symlink():
        manifests = sorted(
            path
            for path in skill_root.glob("*/adapter.manifest.json")
            if path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        )
    rows = [_adapter_row(repo_root, path) for path in manifests]
    blockers = [
        {
            "code": "repo_skill_adapter_static_validation_failed",
            "adapter_id": row.get("adapter_id"),
            "errors": row["static_validation"]["errors"],
        }
        for row in rows
        if row["static_validation"]["status"] != "pass"
    ]
    packet = {
        "schema_version": 2,
        "artifact_kind": "repo_skill_adapter_scan_packet",
        "step": "repo_skill_adapter_scan",
        "cycle_id": cycle_id,
        "adapter_scan_status": "pass" if not blockers else "block",
        "adapter_count": len(rows),
        "repo_skill_adapter_packet": {
            "schema_version": 2,
            "adapters": rows,
            "not_goal_truth": True,
            "not_validation_evidence": True,
        },
        "blockers": blockers,
        "evidence_paths": [row["manifest_path"] for row in rows],
    }
    packet["scan_packet_sha256"] = _object_sha256(packet)
    return packet


def _load_scan(root: Path, raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        path, _ = _safe_regular_file(root, raw)
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("adapter scan packet is not an object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    from .repo_skill_adapter_cli import main as cli_main

    return cli_main(argv)


__all__ = (
    "main",
    "registered_adapter_handoff",
    "scan_repo_skill_adapters",
)
