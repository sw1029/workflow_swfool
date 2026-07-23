"""Pure compiler for the selection authority re-entry artifact chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Sequence

from .selection_authority_reentry_artifacts import (
    _artifact,
    _current_publication_head,
)
from .selection_authority_reentry_authority import (
    _validate_authority_subject_identity,
)
from .selection_authority_reentry_contracts import (
    CYCLE_ID,
    _resolution_body,
    _selected_task_id,
    _singleton_authority_candidate,
    _source_predecessor_task_id,
    _task_markdown,
    validate_authority_reentry_resolution_seal,
)
from .selection_decision_receipt_v3 import (
    render_preliminary_selection_decision_v3_from_values,
    render_selection_decision_receipt_v3_from_values,
)
from .selection_decision_store import normalize_binding, read_bound_json
from .selection_synthesis import render_selection_synthesis


def _source_context(
    root: Path,
    *,
    cycle_id: str,
    source_result: dict[str, str],
    authority_decisions: Sequence[dict[str, str]],
    skills_root: Path,
    reentry_at: str,
    old_authority_scope: Callable[..., Any],
    validated_authority_decisions: Callable[..., Any],
) -> dict[str, Any]:
    if not CYCLE_ID.fullmatch(cycle_id):
        raise ValueError("authority reentry cycle ID is invalid")
    source_binding = normalize_binding(source_result, "authority reentry source derive")
    _, source = read_bound_json(root, source_binding, "authority reentry source derive")
    if (
        source.get("step") != "derive"
        or source.get("cycle_id") != cycle_id
        or source.get("selection_outcome") != "user_escalation"
        or source.get("next_task_id") not in {None, ""}
        or source.get("selected_candidate_id") != ""
        or source.get("pack_disposition") != "user_escalation"
    ):
        raise ValueError("authority reentry source derive is not user_escalation")
    synthesis = render_selection_synthesis(root, source)
    candidate = _singleton_authority_candidate(synthesis)
    (
        subject,
        required_operation,
        approval,
        scope,
        source_authority_request,
    ) = old_authority_scope(root, source)
    source_task_id = _source_predecessor_task_id(source)
    _validate_authority_subject_identity(
        root,
        subject=subject,
        candidate=candidate,
        source_cycle_id=cycle_id,
        source_task_id=source_task_id,
        approval=approval,
        packet_scope=scope,
    )
    entries, operations, source_approval, materialization = (
        validated_authority_decisions(
            root,
            authority_decisions,
            skills_root=skills_root,
            subject=subject,
            source_cycle_id=cycle_id,
            source_task_id=source_task_id,
            required_operation=required_operation,
            required_request_semantic_sha256=source_authority_request[
                "request_semantic_sha256"
            ],
            at=reentry_at,
        )
    )
    return {
        "source_binding": source_binding,
        "synthesis": synthesis,
        "candidate": candidate,
        "subject": subject,
        "approval": approval,
        "source_authority_request": source_authority_request,
        "decision_entries": entries,
        "operations": operations,
        "source_approval": source_approval,
        "root_materialization_ref": materialization,
        "authority_reentry_at": reentry_at,
    }


def _trigger_artifact(
    root: Path,
    *,
    cycle_id: str,
    source_binding: dict[str, str],
    synthesis: dict[str, Any],
    cycle_finalization: dict[str, str],
    schema_pre_derive: dict[str, str],
    current_task: dict[str, str],
    task_index: dict[str, str],
    publication_head: dict[str, str] | None,
    render_trigger: Callable[..., dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    head = (
        normalize_binding(publication_head, "authority reentry publication head")
        if publication_head is not None
        else _current_publication_head(root)
    )
    trigger = render_trigger(
        root,
        cycle_id=cycle_id,
        cycle_finalization=normalize_binding(
            cycle_finalization, "authority reentry cycle finalization"
        ),
        schema_pre_derive=normalize_binding(
            schema_pre_derive, "authority reentry schema pre derive"
        ),
        derive_result=source_binding,
        current_task=normalize_binding(current_task, "authority reentry current task"),
        task_index=normalize_binding(task_index, "authority reentry task index"),
        publication_head=head,
        input_evidence_manifest_sha256=synthesis["input_evidence_manifest_sha256"],
    )
    return _artifact("triggers", trigger), head, trigger


def _selection_artifacts(
    root: Path,
    *,
    cycle_id: str,
    context: dict[str, Any],
    trigger_artifact: dict[str, Any],
    trigger: dict[str, Any],
) -> dict[str, Any]:
    synthesis_artifact = _artifact("syntheses", context["synthesis"])
    synthesis_binding = synthesis_artifact["binding"]
    trigger_binding = trigger_artifact["binding"]
    selected_task_id = _selected_task_id(context["candidate"])
    excluded = context["approval"].get("excluded_effects")
    if (
        not isinstance(excluded, list)
        or excluded != sorted(set(excluded))
        or not all(isinstance(item, str) and item for item in excluded)
    ):
        raise ValueError("source approval excluded effects are invalid")
    task_payload = _task_markdown(
        task_id=selected_task_id,
        source_cycle_id=cycle_id,
        source_derive=context["source_binding"],
        candidate=context["candidate"],
        subject=context["subject"],
        operations=context["operations"],
        excluded_effects=excluded,
    )
    task_artifact = _artifact("task_sources", task_payload, suffix=".md")
    resolution = _resolution_body(
        trigger_binding=trigger_binding,
        synthesis_binding=synthesis_binding,
        source_cycle_id=cycle_id,
        source_derive=context["source_binding"],
        authority_reentry_at=context["authority_reentry_at"],
        candidate=context["candidate"],
        subject=context["subject"],
        source_authority_request=context["source_authority_request"],
        decision_entries=context["decision_entries"],
        source_approval=context["source_approval"],
        root_materialization_ref=context["root_materialization_ref"],
        authorized_operations=context["operations"],
        selected_task_id=selected_task_id,
        task_source=task_artifact["binding"],
    )
    validate_authority_reentry_resolution_seal(resolution)
    resolution_artifact = _artifact("resolutions", resolution)
    decision = render_preliminary_selection_decision_v3_from_values(
        root,
        trigger_binding,
        trigger,
        synthesis_binding,
        context["synthesis"],
        resolution_artifact["binding"],
        resolution,
        task_artifact["binding"],
    )
    decision_artifact = _artifact("decisions", decision)
    receipt = render_selection_decision_receipt_v3_from_values(
        root,
        trigger_binding,
        trigger,
        synthesis_binding,
        context["synthesis"],
        resolution_artifact["binding"],
        resolution,
        decision_artifact["binding"],
        decision,
        task_artifact["binding"],
    )
    receipt_artifact = _artifact("receipts", receipt)
    return {
        "selected_task_id": selected_task_id,
        "artifacts": [
            synthesis_artifact,
            trigger_artifact,
            task_artifact,
            resolution_artifact,
            decision_artifact,
            receipt_artifact,
        ],
        "trigger": trigger_binding,
        "synthesis": synthesis_binding,
        "task_source": task_artifact["binding"],
        "resolution": resolution_artifact["binding"],
        "decision": decision_artifact["binding"],
        "receipt": receipt_artifact["binding"],
    }


def compile_components(
    root: Path,
    *,
    cycle_id: str,
    source_result: dict[str, str],
    cycle_finalization: dict[str, str],
    schema_pre_derive: dict[str, str],
    current_task: dict[str, str],
    task_index: dict[str, str],
    publication_head: dict[str, str] | None,
    authority_decisions: Sequence[dict[str, str]],
    skills_root: Path,
    reentry_at: str,
    old_authority_scope: Callable[..., Any],
    validated_authority_decisions: Callable[..., Any],
    render_trigger: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    context = _source_context(
        root,
        cycle_id=cycle_id,
        source_result=source_result,
        authority_decisions=authority_decisions,
        skills_root=skills_root,
        reentry_at=reentry_at,
        old_authority_scope=old_authority_scope,
        validated_authority_decisions=validated_authority_decisions,
    )
    trigger_artifact, head, trigger = _trigger_artifact(
        root,
        cycle_id=cycle_id,
        source_binding=context["source_binding"],
        synthesis=context["synthesis"],
        cycle_finalization=cycle_finalization,
        schema_pre_derive=schema_pre_derive,
        current_task=current_task,
        task_index=task_index,
        publication_head=publication_head,
        render_trigger=render_trigger,
    )
    outputs = _selection_artifacts(
        root,
        cycle_id=cycle_id,
        context=context,
        trigger_artifact=trigger_artifact,
        trigger=trigger,
    )
    compiler_inputs = {
        "cycle_id": cycle_id,
        "authority_reentry_at": reentry_at,
        "source_result": context["source_binding"],
        "cycle_finalization": normalize_binding(
            cycle_finalization, "authority reentry cycle finalization"
        ),
        "schema_pre_derive": normalize_binding(
            schema_pre_derive, "authority reentry schema pre derive"
        ),
        "current_task": normalize_binding(
            current_task, "authority reentry current task"
        ),
        "task_index": normalize_binding(task_index, "authority reentry task index"),
        "publication_head": head,
        "authority_decisions": [
            normalize_binding(row, "authority reentry decision")
            for row in authority_decisions
        ],
        "skills_root": str(skills_root),
    }
    return {
        "schema_version": 1,
        "artifact_kind": "authority_reentry_publication_plan",
        "compiler_inputs": compiler_inputs,
        **outputs,
    }


__all__ = ()
