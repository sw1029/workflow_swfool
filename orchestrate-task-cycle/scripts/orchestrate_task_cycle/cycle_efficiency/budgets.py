from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .common import read_text


COMMAND_SURFACE_RE = re.compile(
    r"\b(?:build|validate|run|preflight)-[A-Za-z0-9_.:-]*[-_]v\d+[A-Za-z0-9_.:-]*(?:contract|handoff|packet|gate|preflight|check|locator|resolution|recovery)?[A-Za-z0-9_.:-]*",
    re.IGNORECASE,
)
RUN_DIR_THRESHOLD = 100
PROCESSED_CANDIDATE_THRESHOLD = 200
VERSIONED_FAMILY_THRESHOLD = 12


def command_surface_budget(
    root: Path, metadata_only_count: int, threshold: int = 12, metadata_window: int = 2
) -> dict[str, Any]:
    surfaces: list[dict[str, Any]] = []
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.rglob("*.py")):
            commands = [
                match.group(0).lower()
                for match in COMMAND_SURFACE_RE.finditer(read_text(path))
            ]
            if not commands:
                continue
            counts = Counter(
                re.sub(r"[-_]v\d+", "-vNNN", command)
                for command in commands
                if any(
                    token in command
                    for token in (
                        "contract",
                        "handoff",
                        "packet",
                        "gate",
                        "preflight",
                        "check",
                        "locator",
                        "resolution",
                        "recovery",
                    )
                )
            )
            total = sum(counts.values())
            if total >= threshold:
                surfaces.append(
                    {
                        "path": path.as_posix(),
                        "contract_like_command_count": total,
                        "top_command_families": [
                            {"family": family, "count": count}
                            for family, count in counts.most_common(8)
                        ],
                    }
                )
    exceeded = bool(surfaces) and metadata_only_count >= metadata_window
    return {
        "threshold": threshold,
        "surface_count": len(surfaces),
        "metadata_only_window": metadata_window,
        "metadata_only_count": metadata_only_count,
        "budget_exceeded": exceeded,
        "consolidation_candidate_required": exceeded,
        "hard_gate": False,
        "constrains_current_family": False,
        "decision_scope": "global_dashboard",
        "allowed_dispositions": [
            "consolidation",
            "goal_productive",
            "terminal_blocked",
        ],
        "surfaces": surfaces[:8],
    }


def artifact_sprawl_budget(root: Path) -> dict[str, Any]:
    run_root, processed_root = root / ".task" / "run", root / "processed"
    run_dir_count = (
        sum(1 for path in run_root.iterdir() if path.is_dir())
        if run_root.is_dir()
        else 0
    )
    processed_count = (
        sum(
            1
            for path in processed_root.rglob("*")
            if path.is_dir() and "candidate" in path.name.lower()
        )
        if processed_root.is_dir()
        else 0
    )
    families: Counter[str] = Counter()
    scripts_dir = root / "scripts"
    if scripts_dir.is_dir():
        for path in sorted(scripts_dir.rglob("*.py")):
            for match in COMMAND_SURFACE_RE.finditer(read_text(path)):
                families[re.sub(r"[-_]v\d+", "-vNNN", match.group(0).lower())] += 1
    over_budget = (
        run_dir_count >= RUN_DIR_THRESHOLD
        or processed_count >= PROCESSED_CANDIDATE_THRESHOLD
        or any(count >= VERSIONED_FAMILY_THRESHOLD for count in families.values())
    )
    return {
        "run_dir_threshold": RUN_DIR_THRESHOLD,
        "run_dir_count": run_dir_count,
        "processed_candidate_threshold": PROCESSED_CANDIDATE_THRESHOLD,
        "processed_candidate_count": processed_count,
        "versioned_family_threshold": VERSIONED_FAMILY_THRESHOLD,
        "top_versioned_command_families": [
            {"family": family, "count": count}
            for family, count in families.most_common(8)
        ],
        "consolidation_candidate_required": over_budget,
        "hard_gate": False,
        "constrains_current_family": False,
        "decision_scope": "global_dashboard",
        "allowed_dispositions": [
            "consolidation",
            "goal_productive",
            "terminal_blocked",
            "user_escalation",
        ],
    }
