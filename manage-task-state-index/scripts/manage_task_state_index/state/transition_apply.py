"""CAS application service for immutable task-state transition plans."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .events import (
    _append_events_unlocked,
    _load_events_unlocked,
    load_events_read_only,
    merge_state,
)
from .render import (
    _markdown_projection_matches,
    _rebuild_markdown_unlocked as _default_rebuild_markdown,
)
from .selected_successor_guard import (
    guard_selected_successor_effect,
    plan_requires_selected_successor_lease,
)
from .storage import index_lock, markdown_path, rel_path, sha256_file
from .transition_external import (
    is_external_plan,
    pending_receipt_for_plan,
    publish_pending_receipt,
    settled_receipt_status,
    validate_external_prepare,
)
from .transition_intent import (
    assert_no_pending_transition_intents,
    publish_transition_intent,
)
from .transition_no_effect import load_no_effect_receipt
from .transition_plan_contract import (
    RESULT_SCHEMA_VERSION,
    canonical_bytes,
    load_transition_plan,
    owned_transition_file,
    publish_immutable,
    receipt_for_plan,
    receipt_status,
    workspace_path,
)
from .transition_recovery import (
    committed_boundary_valid,
    matching_events,
)
from .transition_semantics import validate_transition_plan_semantics
from .transition_verification import cas_status


@dataclass(frozen=True, slots=True)
class ApplyContext:
    root: Path
    plan: dict[str, Any]
    plan_ref: str
    plan_file_sha256: str
    external: bool
    external_prepare: dict[str, str] | None
    receipt_path: Path
    rebuild_markdown: Callable[..., dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ApplyOutcome:
    receipt: dict[str, Any]
    receipt_path: Path
    receipt_file_sha256: str
    replay: bool
    recovered: bool
    appended: bool
    intent_created: bool
    render_result: dict[str, Any]


def _settled_replay(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> dict[str, Any] | None:
    status, digest = settled_receipt_status(
        root, plan, plan_ref, plan_file_sha256
    )
    if status == "conflict":
        raise ValueError("Task-state transition external settlement receipt conflict")
    if status != "current":
        return None
    receipt_ref = f".task/transition_receipts/{plan['plan_id']}.json"
    return {
        "result_kind": "task_state_transition_apply_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "already_applied",
        "activation_status": "active",
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "receipt_ref": receipt_ref,
        "receipt_file_sha256": digest,
        "execution_result_binding": {"ref": receipt_ref, "sha256": digest},
        "events_appended": 0,
        "idempotent_replay": True,
        "publication_recovered": False,
        "mutation_performed": False,
        "render_result": {},
        "selection_consumption_allowed": True,
    }


def _preflight(
    root: Path,
    path_value: str | Path,
    external_prepare: dict[str, str] | None,
    rebuild_markdown: Callable[..., dict[str, Any]],
) -> tuple[ApplyContext, dict[str, Any] | None]:
    root = root.resolve()
    plan_path, plan, plan_file_sha256 = load_transition_plan(root, path_value)
    validate_transition_plan_semantics(root, plan)
    workspace_path(root, ".task/index.jsonl")
    workspace_path(root, ".task/index.md")
    plan_ref = rel_path(root, plan_path)
    external = is_external_plan(plan)
    if external:
        if external_prepare is None:
            raise ValueError(
                "Prospective task-state apply requires an external publication prepare binding"
            )
        external_prepare = validate_external_prepare(
            root, plan, plan_ref, plan_file_sha256, external_prepare
        )
        replay = _settled_replay(root, plan, plan_ref, plan_file_sha256)
    else:
        if external_prepare is not None:
            raise ValueError("Legacy task-state apply cannot bind external publication")
        replay = None
    no_effect, _receipt, _digest = load_no_effect_receipt(
        root, plan, plan_ref, plan_file_sha256
    )
    if no_effect == "current":
        raise ValueError("Task-state transition plan is settled with no effect")
    receipt_path = owned_transition_file(
        root,
        "transition_pending_receipts" if external else "transition_receipts",
        f"{plan['plan_id']}.json",
        create_parent=False,
    )
    return (
        ApplyContext(
            root=root,
            plan=plan,
            plan_ref=plan_ref,
            plan_file_sha256=plan_file_sha256,
            external=external,
            external_prepare=external_prepare,
            receipt_path=receipt_path,
            rebuild_markdown=rebuild_markdown,
        ),
        replay,
    )


def _publish_receipt(
    context: ApplyContext,
    receipt: dict[str, Any],
) -> tuple[Path, str]:
    if context.external:
        path, _created, digest = publish_pending_receipt(
            context.root, context.plan, receipt
        )
        return path, digest
    path = owned_transition_file(
        context.root,
        "transition_receipts",
        f"{context.plan['plan_id']}.json",
        create_parent=True,
    )
    publish_immutable(path, canonical_bytes(receipt) + b"\n")
    digest = sha256_file(path)
    assert digest is not None
    return path, digest


def _apply_locked(context: ApplyContext) -> ApplyOutcome:
    root, plan = context.root, context.plan
    with index_lock(root):
        assert_no_pending_transition_intents(
            root, allowed_plan_id=str(plan["plan_id"])
        )
        no_effect, _receipt, _digest = load_no_effect_receipt(
            root, plan, context.plan_ref, context.plan_file_sha256
        )
        if no_effect == "current":
            raise ValueError("Task-state transition plan is settled with no effect")
        existing, _ledger_digest = load_events_read_only(root)
        exact, conflict = matching_events(existing, plan)
        if conflict:
            raise ValueError(
                "Task-state transition plan is partially or conflictingly applied"
            )
        if exact and not committed_boundary_valid(root, plan, existing):
            raise ValueError("Task-state transition committed boundary is invalid")
        receipt = (
            pending_receipt_for_plan(
                plan,
                context.plan_ref,
                context.plan_file_sha256,
                context.external_prepare,
            )
            if context.external
            else receipt_for_plan(plan, context.plan_ref, context.plan_file_sha256)
        )
        status, receipt_digest = receipt_status(context.receipt_path, receipt)
        if status == "conflict":
            raise ValueError("Task-state transition apply receipt conflict")
        if not exact:
            current, defects = cas_status(root, plan, phase="apply")
            if not current:
                raise ValueError(
                    "Task-state transition plan CAS mismatch: " + ", ".join(defects)
                )
        intent_created = status == "missing" and publish_transition_intent(
            root, plan, context.plan_ref, context.plan_file_sha256
        )
        if not exact:
            _append_events_unlocked(
                root,
                plan["events"],
                allowed_transition_plan_id=str(plan["plan_id"]),
            )
        ledger_current = sha256_file(root / ".task/index.jsonl") == plan["ledger"][
            "after_sha256"
        ]
        current_events = _load_events_unlocked(root)
        projection_current = (
            not plan["markdown"]["render"]
            or _markdown_projection_matches(root, merge_state(current_events))
        )
        repair = plan["markdown"]["render"] and (
            not exact or status == "missing" or not projection_current
        )
        render_result = (
            context.rebuild_markdown(
                root, now_fn=lambda: str(plan["created_at"])
            )
            if repair
            else {}
        )
        if repair and not _markdown_projection_matches(
            root, merge_state(current_events)
        ):
            raise ValueError("Task-state transition current projection mismatch")
        if (
            repair
            and ledger_current
            and sha256_file(markdown_path(root)) != plan["markdown"]["after_sha256"]
        ):
            raise ValueError("Task-state transition rendered projection digest mismatch")
        if not ledger_current and not exact:
            raise ValueError("Task-state transition ledger digest mismatch after apply")
        receipt_path = context.receipt_path
        recovered = bool(exact and repair)
        if status == "missing":
            receipt_path, receipt_digest = _publish_receipt(context, receipt)
            recovered = exact
        assert receipt_digest is not None
        return ApplyOutcome(
            receipt=receipt,
            receipt_path=receipt_path,
            receipt_file_sha256=receipt_digest,
            replay=exact,
            recovered=recovered,
            appended=not exact,
            intent_created=bool(intent_created),
            render_result=render_result,
        )


def _result(context: ApplyContext, outcome: ApplyOutcome) -> dict[str, Any]:
    plan = context.plan
    receipt_ref = rel_path(context.root, outcome.receipt_path)
    return {
        "result_kind": "task_state_transition_apply_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": (
            "already_pending_external_settlement"
            if context.external and outcome.replay
            else "pending_external_settlement"
            if context.external
            else "already_applied"
            if outcome.replay
            else "applied"
        ),
        "activation_status": (
            "pending_external_settlement" if context.external else "active"
        ),
        "plan_id": plan["plan_id"],
        "plan_ref": context.plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": context.plan_file_sha256,
        "receipt_ref": receipt_ref,
        "receipt_content_sha256": outcome.receipt["receipt_content_sha256"],
        "receipt_file_sha256": outcome.receipt_file_sha256,
        "execution_result_binding": {
            "ref": receipt_ref,
            "sha256": outcome.receipt_file_sha256,
        },
        "events_appended": 0 if outcome.replay else len(plan["events"]),
        "idempotent_replay": outcome.replay,
        "publication_recovered": outcome.recovered,
        "mutation_performed": (
            outcome.appended or outcome.recovered or outcome.intent_created
        ),
        "render_result": outcome.render_result,
        "selection_consumption_allowed": not context.external,
    }


def apply_transition_plan(
    root: Path,
    path_value: str | Path,
    *,
    external_prepare: dict[str, str] | None = None,
    execution_lease: dict[str, str] | None = None,
    _selected_successor_execution_token: object | None = None,
    rebuild_markdown: Callable[..., dict[str, Any]] = _default_rebuild_markdown,
) -> dict[str, Any]:
    context, replay = _preflight(
        root, path_value, external_prepare, rebuild_markdown
    )
    if replay is not None:
        return replay
    if plan_requires_selected_successor_lease(context.plan):
        with guard_selected_successor_effect(
            context.root,
            execution_lease,
            action="apply_task_state_plan_pending",
            effect_inputs={
                "plan": {
                    "ref": context.plan_ref,
                    "sha256": context.plan_file_sha256,
                },
                "external_prepare": context.external_prepare,
            },
            legacy_token=_selected_successor_execution_token,
        ):
            return _result(context, _apply_locked(context))
    if execution_lease is not None or _selected_successor_execution_token is not None:
        raise ValueError(
            "Selected-successor execution authority cannot be attached to "
            "an unrelated task-state transition"
        )
    return _result(context, _apply_locked(context))


__all__ = ("apply_transition_plan",)
