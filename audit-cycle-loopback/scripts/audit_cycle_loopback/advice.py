from __future__ import annotations

from typing import Any
from pathlib import Path
import hashlib
from .common import (
    ROOT_STEERING_DOC_NAMES,
)
from . import blockers as _blockers
from . import io_utils as _io_utils
from . import values as _values


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None

def active_advice_hashes(root: Path) -> set[str]:
    hashes: set[str] = set()
    active_dir = root / ".agent_advice" / "active"
    for path in sorted(active_dir.glob("*.md")) if active_dir.is_dir() else []:
        digest = _blockers.sha256_file(path)
        if digest:
            hashes.add(digest)
    index_path = root / ".agent_advice" / "index.jsonl"
    for event in _io_utils.read_jsonl(index_path):
        if str(event.get("status") or "").lower() != "active":
            continue
        for key in ("path", "raw_source_path"):
            raw_path = event.get(key)
            if not raw_path:
                continue
            path = Path(str(raw_path))
            if not path.is_absolute():
                path = root / path
            digest = _blockers.sha256_file(path)
            if digest:
                hashes.add(digest)
    return hashes

def advice_coherence_finding(root: Path) -> dict[str, Any] | None:
    root_docs = [root / name for name in sorted(ROOT_STEERING_DOC_NAMES) if (root / name).is_file()]
    if not root_docs:
        return None
    known_hashes = active_advice_hashes(root)
    orphans: list[str] = []
    for path in root_docs:
        digest = _blockers.sha256_file(path)
        if digest and digest in known_hashes:
            continue
        orphans.append(_io_utils.rel_path(root, path))
    if not orphans:
        return None
    return {
        "severity": "warn",
        "code": "orphan_advice_not_intaken",
        "message": "root steering advice exists but is not represented in .agent_advice/active; intake it before relying on derive to consume it.",
        "evidence": {"orphans": orphans, "active_advice_dir": ".agent_advice/active"},
        "action": "$manage-external-advice intake",
    }

def semantic_progress_value(value: Any) -> bool | None:
    if not isinstance(value, dict):
        return None
    for key in ("semantic_progress", "checks.semantic_progress", "output_delta.semantic_progress"):
        current: Any = value
        for part in key.split("."):
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(part)
        if current is not None:
            return _values.bool_value(current)
    return None

def validator_disagreement_finding(runner_validation: Any, output_delta: Any) -> dict[str, Any] | None:
    runner_sp = semantic_progress_value(runner_validation)
    delta_sp = semantic_progress_value(output_delta)
    if runner_sp is True and delta_sp is False:
        return {
            "severity": "block",
            "code": "validator_disagreement",
            "message": (
                "strict runner validator and output_delta disagree on semantic_progress; "
                "use the conservative output_delta verdict and do not treat runner pass as goal-productive evidence."
            ),
            "evidence": {"runner_semantic_progress": runner_sp, "output_delta_semantic_progress": delta_sp},
        }
    return None
