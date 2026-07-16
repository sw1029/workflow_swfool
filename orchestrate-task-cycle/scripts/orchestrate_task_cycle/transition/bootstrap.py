from __future__ import annotations

from typing import Any

from .access import add, status_for_step, step_event, text_blob
from .constants import (
    BOOTSTRAP_ORDER,
    PLACEHOLDER_IDS,
    SUBSTANTIVE_BOOTSTRAP_STATUSES,
)


def real_identifier(value: Any) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate.lower() not in PLACEHOLDER_IDS else ""


def explicit_task_absent(context: dict[str, Any]) -> bool:
    task_md = context.get("task_md")
    if isinstance(task_md, dict) and task_md.get("exists") is False:
        return True
    task_state = context.get("task_state")
    if isinstance(task_state, dict):
        nested = task_state.get("task_md")
        if isinstance(nested, dict) and nested.get("exists") is False:
            return True
    return context.get("task_md_exists") is False


def bootstrap_binding_findings(stage: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for step in BOOTSTRAP_ORDER:
        status = status_for_step(stage, step)
        if status not in SUBSTANTIVE_BOOTSTRAP_STATUSES:
            add(
                findings,
                "block",
                "bootstrap_substantive_step_missing",
                f"Bootstrap completion requires substantive `{step}` completion; N/A, skipped, partial, and missing rows cannot close initialization.",
                {"step": step, "status": status},
            )
    _validate_authority_binding(stage, findings)
    next_task_id = _validate_derive_binding(stage, findings)
    _validate_schema_binding(stage, next_task_id, findings)
    _validate_index_binding(stage, next_task_id, findings)
    return findings


def _validate_authority_binding(
    stage: dict[str, Any], findings: list[dict[str, Any]]
) -> None:
    event = step_event(stage, "authority")
    if not real_identifier(
        event.get("authority_policy")
        or event.get("effective_authority_policy")
        or event.get("authority_policy_source")
    ):
        add(
            findings,
            "block",
            "bootstrap_authority_evidence_missing",
            "Bootstrap authority must record a concrete policy or policy source.",
        )


def _validate_derive_binding(
    stage: dict[str, Any], findings: list[dict[str, Any]]
) -> str:
    event = step_event(stage, "derive")
    derive_mode = (
        str(event.get("derive_mode") or event.get("mode") or "").strip().lower()
    )
    if derive_mode != "initial_init":
        add(
            findings,
            "block",
            "bootstrap_derive_mode_invalid",
            "Bootstrap derive must set `derive_mode: initial_init`.",
            {"derive_mode": derive_mode or None},
        )
    next_task_id = real_identifier(event.get("next_task_id"))
    if not next_task_id:
        add(
            findings,
            "block",
            "bootstrap_next_task_id_missing",
            "Bootstrap derive must create one real next_task_id.",
        )
    if "task.md" not in text_blob(event):
        add(
            findings,
            "block",
            "bootstrap_task_md_binding_missing",
            "Bootstrap derive must bind the new task ID to a concrete task.md path/artifact.",
        )
    return next_task_id


def _validate_schema_binding(
    stage: dict[str, Any],
    next_task_id: str,
    findings: list[dict[str, Any]],
) -> None:
    schema_task_id = real_identifier(
        step_event(stage, "schema_post_derive").get("next_task_id")
    )
    if next_task_id and schema_task_id and schema_task_id != next_task_id:
        add(
            findings,
            "block",
            "bootstrap_schema_task_id_mismatch",
            "Post-derive schema reconciliation must bind to the task created by initial_init.",
            {
                "derive_next_task_id": next_task_id,
                "schema_next_task_id": schema_task_id,
            },
        )


def _validate_index_binding(
    stage: dict[str, Any],
    next_task_id: str,
    findings: list[dict[str, Any]],
) -> None:
    event = step_event(stage, "index")
    indexed_task_id = real_identifier(
        event.get("task_id")
        or event.get("next_task_id")
        or event.get("indexed_task_id")
    )
    if not indexed_task_id:
        add(
            findings,
            "block",
            "bootstrap_index_task_id_missing",
            "Bootstrap index must record the created task ID.",
        )
    elif next_task_id and indexed_task_id != next_task_id:
        add(
            findings,
            "block",
            "bootstrap_index_task_id_mismatch",
            "Bootstrap index task ID must match initial_init next_task_id.",
            {"derive_next_task_id": next_task_id, "indexed_task_id": indexed_task_id},
        )
    if not any(
        marker in text_blob(event)
        for marker in (".task/index", "index.jsonl", "index.md")
    ):
        add(
            findings,
            "block",
            "bootstrap_index_binding_missing",
            "Bootstrap index must cite a concrete .task/index artifact or path.",
        )
