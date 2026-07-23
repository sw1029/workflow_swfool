"""Persisted-chain validation for selection authority re-entry."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .selection_authority_reentry_artifacts import _binding_for_payload
from .selection_authority_reentry_authority import (
    _validate_authority_subject_identity,
)
from .selection_authority_reentry_contracts import (
    _resolution_body,
    _selected_task_id,
    _singleton_authority_candidate,
    _source_predecessor_task_id,
    _task_markdown,
    validate_authority_reentry_resolution_seal,
)
from .selection_decision_store import read_bound_bytes, read_bound_json
from .selection_synthesis import (
    render_selection_synthesis,
    validate_selection_synthesis,
)


def validate_resolution(
    root: Path,
    value: Any,
    *,
    skills_root: Path | None,
    expected_active_prepare: Any,
    old_authority_scope: Callable[..., Any],
    validated_authority_decisions: Callable[..., Any],
    validate_trigger: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Reopen and exactly reconstruct a persisted authority resolution."""

    workspace = root.expanduser().resolve(strict=True)
    resolution = validate_authority_reentry_resolution_seal(value)
    _, source = read_bound_json(
        workspace, resolution["source_derive"], "authority reentry source derive"
    )
    synthesis = render_selection_synthesis(workspace, source)
    _, persisted_synthesis = read_bound_json(
        workspace,
        resolution["source_selection_synthesis"],
        "authority reentry source synthesis",
    )
    if validate_selection_synthesis(workspace, persisted_synthesis) != synthesis:
        raise ValueError("authority reentry source synthesis differs")
    _, trigger = read_bound_json(
        workspace, resolution["selection_trigger"], "authority reentry trigger"
    )
    validated_trigger = validate_trigger(
        workspace,
        trigger,
        expected_active_prepare=expected_active_prepare,
    )
    if (
        validated_trigger.get("cycle_id") != resolution["source_cycle_id"]
        or validated_trigger.get("derive_result") != resolution["source_derive"]
        or validated_trigger.get("input_evidence_manifest_sha256")
        != synthesis["input_evidence_manifest_sha256"]
    ):
        raise ValueError("authority reentry trigger source differs")
    candidate = _singleton_authority_candidate(synthesis)
    (
        subject,
        required_operation,
        approval,
        scope,
        source_authority_request,
    ) = old_authority_scope(workspace, source)
    source_task_id = _source_predecessor_task_id(source)
    _validate_authority_subject_identity(
        workspace,
        subject=subject,
        candidate=candidate,
        source_cycle_id=resolution["source_cycle_id"],
        source_task_id=source_task_id,
        approval=approval,
        packet_scope=scope,
    )
    selected_skills_root = (
        skills_root.expanduser().resolve(strict=True)
        if skills_root is not None
        else Path(__file__).resolve().parents[3]
    )
    entries, operations, source_approval, materialization = (
        validated_authority_decisions(
            workspace,
            [row["decision"] for row in resolution["authority_decisions"]],
            skills_root=selected_skills_root,
            subject=subject,
            source_cycle_id=resolution["source_cycle_id"],
            source_task_id=source_task_id,
            required_operation=required_operation,
            required_request_semantic_sha256=source_authority_request[
                "request_semantic_sha256"
            ],
            at=resolution["authority_reentry_at"],
        )
    )
    task_path, task_payload = read_bound_bytes(
        workspace, resolution["task_source"], "authority reentry task source"
    )
    expected_task = _task_markdown(
        task_id=_selected_task_id(candidate),
        source_cycle_id=resolution["source_cycle_id"],
        source_derive=resolution["source_derive"],
        candidate=candidate,
        subject=subject,
        operations=operations,
        excluded_effects=approval["excluded_effects"],
    )
    expected_task_binding = _binding_for_payload(
        "task_sources", expected_task, suffix=".md"
    )
    if (
        task_payload != expected_task
        or resolution["task_source"] != expected_task_binding
        or task_path.relative_to(workspace).as_posix() != expected_task_binding["ref"]
    ):
        raise ValueError("authority reentry task source differs")
    expected = _resolution_body(
        trigger_binding=resolution["selection_trigger"],
        synthesis_binding=resolution["source_selection_synthesis"],
        source_cycle_id=resolution["source_cycle_id"],
        source_derive=resolution["source_derive"],
        authority_reentry_at=resolution["authority_reentry_at"],
        candidate=candidate,
        subject=subject,
        source_authority_request=source_authority_request,
        decision_entries=entries,
        source_approval=source_approval,
        root_materialization_ref=materialization,
        authorized_operations=operations,
        selected_task_id=_selected_task_id(candidate),
        task_source=expected_task_binding,
    )
    if resolution != expected:
        raise ValueError("authority reentry resolution exact reconstruction failed")
    return expected


__all__ = ()
