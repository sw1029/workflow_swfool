"""Root-aware completeness checks for cross-store task-doctor effects."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .common import WorkflowError, require, workspace_regular_file


SKILLS_ROOT = Path(__file__).resolve().parents[3]


def _live_index_state(root: Path) -> bool:
    ledger = root.resolve() / ".task/index.jsonl"
    markdown = root.resolve() / ".task/index.md"
    ledger_present = ledger.exists() or ledger.is_symlink()
    markdown_present = markdown.exists() or markdown.is_symlink()
    require(ledger_present == markdown_present, "invalid_task_index_store",
            "task-state index store is partial; repair it before task doctoring")
    if not ledger_present:
        return False
    workspace_regular_file(root, ".task/index.jsonl", "task_state_index.ledger")
    workspace_regular_file(root, ".task/index.md", "task_state_index.markdown")
    scripts = SKILLS_ROOT / "manage-task-state-index" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        from manage_task_state_index.state.events import load_events_read_only

        load_events_read_only(root)
        markdown.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise WorkflowError(
            "invalid_task_index_store",
            "task-state index store is malformed or unsafe",
        ) from error
    return True


def validate_root_effect_inventory(root: Path, plan: dict[str, Any]) -> None:
    """Require advice lifecycle effects to reconcile an existing task index."""

    advice = [
        item for item in plan["operations"]
        if item["workflow_role"] == "external_advice_intake"
    ]
    if not advice or not _live_index_state(root):
        return
    index = [
        item for item in plan["operations"]
        if item["workflow_role"] == "task_index_transition"
    ]
    require(len(index) == 1
            and plan["task_index_transition"]["status"] == "planned",
            "plan_incomplete",
            "advice lifecycle changes require one final transition when a live "
            "task-state index exists",
            next_action="prepare_final_task_index_transition")
    required = {item["operation_id"] for item in advice}
    require(required <= set(index[0]["dependencies"]), "plan_incomplete",
            "the final task-index transition must depend on every advice effect",
            next_action="consolidate_task_index_transition")


__all__ = ["validate_root_effect_inventory"]
