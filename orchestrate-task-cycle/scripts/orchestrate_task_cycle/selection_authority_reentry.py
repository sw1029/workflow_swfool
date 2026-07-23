"""Compile a user-escalation authority delta into an immutable selection chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .selection_authority_reentry_artifacts import _validate_artifact_binding
from .selection_authority_reentry_authority import (
    _normalized_reentry_at,
    _old_authority_scope,
    _validated_authority_decisions,
)
from .selection_authority_reentry_compiler import compile_components
from .selection_authority_reentry_contracts import (
    _operation as _operation,
    validate_authority_reentry_resolution_seal,
)
from .selection_authority_reentry_validation import validate_resolution
from .selection_decision_store import (
    normalize_binding,
    read_bound_json,
)
from .selection_publication_gc_write import write_once_relative
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)
from .selection_publication_reference_barrier import registered_producer_barrier
from .selection_trigger import (
    render_normal_cycle_trigger,
    validate_normal_cycle_trigger,
)


def _compile_components(
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
    at: str,
) -> dict[str, Any]:
    return compile_components(
        root,
        cycle_id=cycle_id,
        source_result=source_result,
        cycle_finalization=cycle_finalization,
        schema_pre_derive=schema_pre_derive,
        current_task=current_task,
        task_index=task_index,
        publication_head=publication_head,
        authority_decisions=authority_decisions,
        skills_root=skills_root,
        reentry_at=at,
        old_authority_scope=_old_authority_scope,
        validated_authority_decisions=_validated_authority_decisions,
        render_trigger=render_normal_cycle_trigger,
    )


def compile_authority_reentry(
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
    at: str,
) -> dict[str, Any]:
    """Compile the complete re-entry chain without writing any artifact."""

    workspace = root.expanduser().resolve(strict=True)
    resolved_skills = skills_root.expanduser().resolve(strict=True)
    reentry_at = _normalized_reentry_at(at)
    return _compile_components(
        workspace,
        cycle_id=cycle_id,
        source_result=source_result,
        cycle_finalization=cycle_finalization,
        schema_pre_derive=schema_pre_derive,
        current_task=current_task,
        task_index=task_index,
        publication_head=publication_head,
        authority_decisions=authority_decisions,
        skills_root=resolved_skills,
        at=reentry_at,
    )


def _recompile(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    inputs = plan.get("compiler_inputs") if isinstance(plan, dict) else None
    if not isinstance(inputs, dict):
        raise ValueError("authority reentry plan lacks compiler inputs")
    return compile_authority_reentry(
        root,
        cycle_id=inputs["cycle_id"],
        source_result=inputs["source_result"],
        cycle_finalization=inputs["cycle_finalization"],
        schema_pre_derive=inputs["schema_pre_derive"],
        current_task=inputs["current_task"],
        task_index=inputs["task_index"],
        publication_head=inputs["publication_head"],
        authority_decisions=inputs["authority_decisions"],
        skills_root=Path(inputs["skills_root"]),
        at=inputs["authority_reentry_at"],
    )


def publish_authority_reentry(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Recompile under the producer barrier and publish the immutable chain."""

    workspace = root.expanduser().resolve(strict=True)
    preflight = _recompile(workspace, plan)
    if preflight != plan:
        raise ValueError("authority reentry plan differs from exact recompilation")
    with registered_producer_barrier(
        workspace,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        refreshed = _recompile(workspace, plan)
        if refreshed != preflight:
            raise ValueError(
                "authority reentry inputs changed during barrier acquisition"
            )
        created: list[bool] = []
        for artifact in refreshed["artifacts"]:
            binding = artifact["binding"]
            category = str(artifact["category"])
            ref = _validate_artifact_binding(binding, category=category)
            digest, was_created = write_once_relative(
                workspace,
                ref,
                artifact["payload"],
                f"selection authority reentry {category}",
                producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
            )
            if digest != binding["sha256"]:
                raise ValueError("authority reentry CAS write binding drifted")
            created.append(was_created)
    _, receipt = read_bound_json(
        workspace, refreshed["receipt"], "authority reentry receipt"
    )
    from .selection_decision_receipt_v3 import (
        validate_selection_decision_receipt_v3,
    )

    validate_selection_decision_receipt_v3(workspace, receipt)
    return {
        "schema_version": 1,
        "artifact_kind": "authority_reentry_publication_result",
        "status": "completed",
        "selected_task_id": refreshed["selected_task_id"],
        "trigger": refreshed["trigger"],
        "synthesis": refreshed["synthesis"],
        "task_source": refreshed["task_source"],
        "resolution": refreshed["resolution"],
        "decision": refreshed["decision"],
        "receipt": refreshed["receipt"],
        "published_count": sum(created),
        "reused_count": len(created) - sum(created),
        "mutation_performed": any(created),
        "effect_boundary": "preparation_only",
        "not_authority": True,
    }


def validate_authority_reentry_resolution(
    root: Path,
    value: Any,
    *,
    skills_root: Path | None = None,
    expected_active_prepare: Any = None,
) -> dict[str, Any]:
    """Reopen and exactly reconstruct a persisted authority resolution."""

    return validate_resolution(
        root,
        value,
        skills_root=skills_root,
        expected_active_prepare=expected_active_prepare,
        old_authority_scope=_old_authority_scope,
        validated_authority_decisions=_validated_authority_decisions,
        validate_trigger=validate_normal_cycle_trigger,
    )


def load_authority_reentry_resolution(
    root: Path,
    binding: dict[str, str],
    *,
    skills_root: Path | None = None,
    expected_active_prepare: Any = None,
) -> dict[str, Any]:
    workspace = root.expanduser().resolve(strict=True)
    normalized = normalize_binding(binding, "authority reentry resolution")
    _, value = read_bound_json(workspace, normalized, "authority reentry resolution")
    expected_ref = (
        f".task/selection_reentry/resolutions/sha256/{normalized['sha256']}.json"
    )
    if normalized["ref"] != expected_ref:
        raise ValueError("authority reentry resolution is outside its CAS")
    return validate_authority_reentry_resolution(
        workspace,
        value,
        skills_root=skills_root,
        expected_active_prepare=expected_active_prepare,
    )


def compile_and_publish_authority_reentry(
    root: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience wrapper retaining the compile/recompile/publish boundary."""

    return publish_authority_reentry(root, compile_authority_reentry(root, **kwargs))


__all__ = (
    "compile_and_publish_authority_reentry",
    "compile_authority_reentry",
    "load_authority_reentry_resolution",
    "publish_authority_reentry",
    "validate_authority_reentry_resolution",
    "validate_authority_reentry_resolution_seal",
)
