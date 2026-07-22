"""Pre-effect provenance revalidation for a prepared selected successor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding, read_bound_json
from .selection_publication_store import _sha256_file
from .selection_publication_state import load_state
from .selection_publication_v2 import _selected_source, normalize_prepare


def validate_selected_source_for_prepared_successor(
    root: Path,
    source_binding_value: Any,
    prepare_binding_value: Any,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Reopen the selected source while its exact prepare is active pre-effect."""

    root = root.expanduser().resolve(strict=True)
    source_binding = normalize_binding(
        source_binding_value, "selected-successor source decision"
    )
    prepare_binding = normalize_binding(
        prepare_binding_value, "selected-successor publication prepare"
    )
    _, raw_prepare = read_bound_json(
        root, prepare_binding, "selected-successor publication prepare"
    )
    prepare = normalize_prepare(root, raw_prepare)
    state = load_state(root)
    active = state.get("active_transaction") if isinstance(state, dict) else None
    if (
        not isinstance(active, dict)
        or active.get("prepare") != prepare_binding
        or active.get("receipt") is not None
        or prepare.get("schema_version") != 3
        or prepare.get("publication_mode")
        != "selected_successor_external_settlement"
        or prepare.get("source_decision") != source_binding
        or prepare.get("source_decision_sha256") != source_binding["sha256"]
    ):
        raise ValueError(
            "selected-successor active prepare does not bind the selected source"
        )
    binding, receipt = _selected_source(
        root,
        source_binding,
        expected_active_prepare=prepare_binding,
    )
    target = prepare["targets"][0]
    if (
        binding != source_binding
        or receipt.get("schema_version") != 2
        or prepare.get("source_decision_id") != receipt.get("receipt_id")
        or prepare.get("selection_id") != receipt.get("selected_task_id")
        or target.get("before_sha256") != _sha256_file(root / "task.md")
    ):
        raise ValueError(
            "selected-successor active prepare provenance differs from current owners"
        )
    return binding, receipt


__all__ = ("validate_selected_source_for_prepared_successor",)
