"""Body-free selected-successor preparation and authority execution contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_publication import (
    _load_prepare,
    prepare_publication_intent,
    receipt_for_prepare,
)
from .selection_publication_store import (
    _bounded_payload,
    _canonical_json,
    _display_json,
    _sha256_bytes,
    _successor_bundle_path,
    _write_once,
)
from .selection_decision_store import normalize_binding, read_bound_bytes
from .selected_successor_index import load_prepare_index, write_prepare_index


BUNDLE_SCHEMA_VERSION = 1
MAX_BUNDLE_BYTES = 256 * 1024


def _subject(
    kind: str, binding: dict[str, str], revision: str
) -> dict[str, str]:
    return {
        "kind": kind,
        "ref": binding["ref"],
        "digest": binding["sha256"],
        "revision": revision,
    }


def _operation(
    *,
    skill_id: str,
    operation_id: str,
    subject: dict[str, str],
    idempotency_key: str,
    inputs: dict[str, dict[str, str]],
    expected_result: dict[str, str],
) -> dict[str, Any]:
    return {
        "operation": {
            "skill_id": skill_id,
            "skill_version": "2.0.0",
            "operation_id": operation_id,
            "operation_version": "1",
        },
        "subject": subject,
        "idempotency_key": idempotency_key,
        "required_inputs": inputs,
        "expected_result": expected_result,
        "authority_bindings": {
            "reservation": {"required_keys": ["ref", "sha256"]},
            "pre_commit_verification": {"required_keys": ["ref", "sha256"]},
            "must_be_validated_before_first_effect": True,
        },
    }


def _execution_order(
    plan_binding: dict[str, str],
    prepare_binding: dict[str, str],
    transaction_id: str,
    plan_id: str,
    pending_binding: dict[str, str],
    publication_binding: dict[str, str],
    settled_binding: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "action": "apply_task_state_plan_pending",
            **_operation(
                skill_id="manage-task-state-index",
                operation_id="mutate_task_state_index",
                subject=_subject("task_index_transition_plan", plan_binding, plan_id),
                idempotency_key=f"selected-successor-index-{plan_id}",
                inputs={"plan": plan_binding, "external_prepare": prepare_binding},
                expected_result=pending_binding,
            ),
        },
        {
            "step": 2,
            "action": "publish_selected_successor_topology",
            **_operation(
                skill_id="orchestrate-task-cycle",
                operation_id="publish_selected_successor_topology",
                subject=_subject(
                    "selection_publication_binding",
                    prepare_binding,
                    transaction_id,
                ),
                idempotency_key=f"selected-successor-publish-{transaction_id[10:]}",
                inputs={"prepare": prepare_binding, "pending": pending_binding},
                expected_result=publication_binding,
            ),
        },
        {
            "step": 3,
            "action": "settle_selected_successor_task_state",
            **_operation(
                skill_id="orchestrate-task-cycle",
                operation_id="settle_selected_successor_task_state",
                subject=_subject("task_state_transition_plan", plan_binding, plan_id),
                idempotency_key=f"selected-successor-settle-{plan_id}",
                inputs={
                    "plan": plan_binding,
                    "pending": pending_binding,
                    "publication": publication_binding,
                },
                expected_result=settled_binding,
            ),
        },
    ]


def _expected_bundle_body(
    root: Path,
    plan_value: Any,
    prepare_value: Any,
    transaction_id: str,
) -> dict[str, Any]:
    from .selection_decision_store import normalize_binding
    from manage_task_state_index.state.transition_external import (
        external_receipt_binding,
        pending_receipt_for_plan,
        settled_receipt_for_plan,
    )
    from manage_task_state_index.state.transition_plan_contract import (
        load_transition_plan,
    )

    plan_binding = normalize_binding(
        plan_value, "selected-successor task-state plan"
    )
    prepare_binding = normalize_binding(
        prepare_value, "selected-successor publication prepare"
    )
    prepare, prepare_path, prepare_sha = _load_prepare(root, transaction_id)
    if prepare_binding != {
        "ref": prepare_path.relative_to(root).as_posix(),
        "sha256": prepare_sha,
    }:
        raise ValueError("selected-successor bundle prepare binding differs")
    plan_path, plan, plan_sha = load_transition_plan(root, plan_binding["ref"])
    if plan_binding != {
        "ref": plan_path.relative_to(root).as_posix(),
        "sha256": plan_sha,
    } or prepare.get("task_state_plan") != plan_binding:
        raise ValueError("selected-successor bundle plan binding differs")
    request = plan.get("request") if isinstance(plan, dict) else None
    sources = request.get("artifact_sources") if isinstance(request, dict) else None
    task_sources = [
        row.get("source")
        for row in sources or []
        if isinstance(row, dict) and row.get("target_ref") == "task.md"
    ]
    if len(task_sources) != 1:
        raise ValueError("selected-successor bundle plan lacks one task source")
    task_source = normalize_binding(task_sources[0], "selected-successor task source")
    source_decision = normalize_binding(
        prepare.get("source_decision"), "selected-successor decision receipt"
    )
    pending = pending_receipt_for_plan(
        plan, plan_binding["ref"], plan_binding["sha256"], prepare_binding
    )
    pending_binding = external_receipt_binding(plan, pending, pending=True)
    publication = receipt_for_prepare(
        root, prepare, prepare_path, prepare_sha, pending_binding=pending_binding
    )
    publication_binding = {
        "ref": f".task/selection_publication/receipts/{transaction_id}.json",
        "sha256": _sha256_bytes(_display_json(publication)),
    }
    settled = settled_receipt_for_plan(
        plan,
        plan_binding["ref"],
        plan_binding["sha256"],
        pending_binding,
        prepare_binding,
        publication_binding,
    )
    settled_binding = external_receipt_binding(plan, settled, pending=False)
    execution = _execution_order(
        plan_binding,
        prepare_binding,
        transaction_id,
        str(plan.get("plan_id") or ""),
        pending_binding,
        publication_binding,
        settled_binding,
    )
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "artifact_kind": "selected_successor_preparation_bundle",
        "created_at": plan.get("created_at"),
        "selected_task_id": prepare.get("selection_id"),
        "source_decision": source_decision,
        "task_source": task_source,
        "task_state_plan": plan_binding,
        "selection_prepare": prepare_binding,
        "transaction_id": transaction_id,
        "execution_order": execution,
        "recovery": {
            "state": "prepared",
            "completed_steps": [
                "prepare_task_state_transition_plan",
                "prepare_selection_publication",
            ],
            "next_step": "apply_task_state_plan_pending",
            "resume_by_exact_expected_result": True,
            "effect_execution_requires_all_three_authority_pre_commits": True,
        },
    }


def _preparation_result(
    bundle: dict[str, Any],
    bundle_binding: dict[str, str],
    *,
    storage_schema_version: int,
    mutation_performed: bool,
) -> dict[str, Any]:
    return {
        "result_kind": "selected_successor_preparation_result",
        "schema_version": 1,
        "status": "prepared",
        "selected_task_id": bundle["selected_task_id"],
        "bundle": bundle_binding,
        "task_state_plan": bundle["task_state_plan"],
        "selection_prepare": bundle["selection_prepare"],
        "transaction_id": bundle["transaction_id"],
        "storage_schema_version": storage_schema_version,
        "mutation_performed": mutation_performed,
    }


def _publish_bundle(
    root: Path, body: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], bool]:
    """Seal and size-check one bundle before resolving its store path."""

    content_sha = _sha256_bytes(_canonical_json(body))
    bundle = {**body, "bundle_content_sha256": content_sha}
    payload = _bounded_payload(
        _canonical_json(bundle),
        MAX_BUNDLE_BYTES,
        "selected-successor preparation bundle",
    )
    path = _successor_bundle_path(root, content_sha)
    created = not path.exists() and not path.is_symlink()
    digest = _write_once(path, payload, "selected-successor preparation bundle")
    return bundle, {
        "ref": path.relative_to(root).as_posix(),
        "sha256": digest,
    }, created


def prepare_selected_successor_bundle(
    root: Path,
    *,
    source_decision: dict[str, str],
    task_source: dict[str, str],
    at: str,
) -> dict[str, Any]:
    """Render all mechanical lifecycle JSON without applying an active effect."""

    from manage_task_state_index.state.selected_successor import (
        prepare_selected_successor,
    )
    from .selection_publication_state import STORAGE_SCHEMA_VERSION

    root = root.expanduser().resolve(strict=True)
    indexed = load_prepare_index(root, source_decision, task_source, at)
    if indexed is not None:
        bundle_binding = indexed["bundle"]
        bundle = load_selected_successor_bundle(root, bundle_binding)
        if (
            bundle.get("source_decision") != indexed["source_decision"]
            or bundle.get("task_source") != indexed["task_source"]
            or bundle.get("created_at") != indexed["created_at"]
        ):
            raise ValueError(
                "Selected-successor prepare-input index points to another bundle"
            )
        from .selected_successor_execution_support import (
            checkpoint_states,
            validate_pristine_source,
        )

        _rows, states = checkpoint_states(root, bundle)
        validate_pristine_source(root, bundle, states)
        return _preparation_result(
            bundle,
            bundle_binding,
            storage_schema_version=STORAGE_SCHEMA_VERSION,
            mutation_performed=False,
        )
    # Compile once without writing so the exact intent key is known. Only an
    # existing immutable prepare index may bypass reopening a now-historical
    # trigger chain; every new plan/prepare write first receives full owner
    # validation. A merely self-sealed receipt therefore has a zero-write path.
    prospective = prepare_selected_successor(
        root,
        source_decision=source_decision,
        task_source=task_source,
        at=at,
        publish=False,
    )
    plan_binding = prospective["plan_binding"]
    intent = {
        "schema_version": 2,
        "kind": "selection_publication_intent",
        "source_decision": prospective["source_decision"],
        "task_source": prospective["task_source"],
        "task_state_plan": plan_binding,
    }
    from .selection_publication_external import external_intent_identity
    from .selection_publication_intent_index import load_intent_index
    from .selection_publication_v2 import validate_selected_source

    _normalized_intent, intent_sha256 = external_intent_identity(intent)
    if load_intent_index(root, intent_sha256, committed=False) is None:
        validate_selected_source(root, source_decision)
    task_state = prepare_selected_successor(
        root,
        source_decision=source_decision,
        task_source=task_source,
        at=at,
        publish=True,
    )
    plan_binding = task_state["plan_binding"]
    prepared = prepare_publication_intent(root, intent)
    transaction_id = str(prepared["transaction_id"])
    _prepare, prepare_path, prepare_sha = _load_prepare(root, transaction_id)
    prepare_binding = {
        "ref": prepare_path.relative_to(root).as_posix(),
        "sha256": prepare_sha,
    }
    body = _expected_bundle_body(
        root, plan_binding, prepare_binding, transaction_id
    )
    bundle, bundle_binding, bundle_created = _publish_bundle(root, body)
    _index, index_created = write_prepare_index(
        root, source_decision, task_source, at, bundle_binding
    )
    return _preparation_result(
        bundle,
        bundle_binding,
        storage_schema_version=prepared["storage_schema_version"],
        mutation_performed=bool(
            task_state["mutation_performed"]
            or prepared["mutation_performed"]
            or bundle_created
            or index_created
        ),
    )


def load_selected_successor_bundle(
    root: Path, binding: dict[str, str]
) -> dict[str, Any]:
    """Read one bundle for the later authority-gated executor."""

    root = root.expanduser().resolve(strict=True)
    try:
        normalized = normalize_binding(binding, "selected-successor bundle")
        path, raw = read_bound_bytes(
            root,
            normalized,
            "selected-successor bundle",
            max_bytes=MAX_BUNDLE_BYTES,
        )
    except ValueError as exc:
        if "raw SHA-256" in str(exc):
            raise ValueError("selected-successor bundle binding has drifted") from exc
        raise
    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("selected-successor bundle is unreadable") from exc
    if raw != _canonical_json(bundle):
        raise ValueError("selected-successor bundle is not canonical JSON")
    if not isinstance(bundle, dict):
        raise ValueError("selected-successor bundle integrity failed")
    content_sha = bundle.get("bundle_content_sha256")
    body = {key: value for key, value in bundle.items() if key != "bundle_content_sha256"}
    if not isinstance(content_sha, str):
        raise ValueError("selected-successor bundle integrity failed")
    expected_path = _successor_bundle_path(root, content_sha)
    expected_ref = expected_path.relative_to(root).as_posix()
    if (
        content_sha != _sha256_bytes(_canonical_json(body))
        or path != expected_path
        or normalized["ref"] != expected_ref
    ):
        raise ValueError("selected-successor bundle integrity failed")
    validate_selected_successor_bundle(root, bundle)
    return bundle


def validate_selected_successor_bundle(
    root: Path, bundle: dict[str, Any]
) -> dict[str, Any]:
    """Re-render and compare the complete closed bundle contract."""

    root = root.expanduser().resolve(strict=True)
    transaction_id = str(bundle.get("transaction_id") or "")
    expected_body = _expected_bundle_body(
        root,
        bundle.get("task_state_plan"),
        bundle.get("selection_prepare"),
        transaction_id,
    )
    body = {
        key: value for key, value in bundle.items() if key != "bundle_content_sha256"
    }
    if body != expected_body or bundle.get("bundle_content_sha256") != _sha256_bytes(
        _canonical_json(expected_body)
    ):
        raise ValueError("selected-successor bundle closed contract differs")
    return bundle


__all__ = (
    "load_selected_successor_bundle",
    "prepare_selected_successor_bundle",
    "validate_selected_successor_bundle",
)
