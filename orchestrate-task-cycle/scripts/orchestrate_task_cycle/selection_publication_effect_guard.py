"""Effect-lease guard construction for selected-successor publication."""

from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any

from .selection_publication_store import _receipt_path


def publication_effect_guard(
    root: Path,
    prepare: dict[str, Any],
    prepare_path: Path,
    prepare_sha: str,
    transaction_id: str,
    execution_lease: dict[str, str] | None,
    legacy_token: object | None,
) -> Any:
    """Return the exact external-owner guard for a new publication effect."""
    if _receipt_path(root, transaction_id).is_file():
        return nullcontext()
    if prepare.get("schema_version") != 3:
        raise ValueError(
            "Legacy schema-v1/v2 selection prepares are immutable recovery "
            "evidence; new publication effects are forbidden"
        )
    from manage_task_state_index.state.selected_successor_guard import (
        guard_selected_successor_effect,
    )

    return guard_selected_successor_effect(
        root,
        execution_lease,
        action="publish_selected_successor_topology",
        effect_inputs={
            "prepare": {
                "ref": prepare_path.relative_to(root).as_posix(),
                "sha256": prepare_sha,
            },
            "transaction_id": transaction_id,
        },
        legacy_token=legacy_token,
    )
