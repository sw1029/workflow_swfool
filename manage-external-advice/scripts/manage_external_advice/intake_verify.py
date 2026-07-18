"""Read-only owner-effect verification for immutable advice intake plans."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import rel_path
from .intake_apply import (
    _committed_boundary_valid,
    _materialize_plan,
    _no_effect_proof_current,
    _observation_is_safe,
    _preflight_destinations,
    _prestate_current,
    _tagged_events,
)
from .intake_intent import assert_no_pending_intake_intents, intake_intent_status
from .intake_no_effect import load_no_effect_receipt, observe_prestate, stale_reason_codes
from .intake_plan import _registry_snapshot_read_only
from .intake_plan_contract import (
    RESULT_SCHEMA_VERSION,
    canonical_bytes,
    canonical_destination_path,
    canonical_intake_artifact_path,
    load_intake_plan,
    receipt_for_plan,
    receipt_status,
    regular_payload,
    sha256_bytes,
)
from .storage import index_md, merge_state, render_index_payload


def _projection_is_current(
    root: Path, events: list[dict[str, Any]], defects: list[str]
) -> bool:
    payload = regular_payload(root, index_md(root), missing=b"")
    if not payload:
        defects.append("markdown_projection_missing")
        return False
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        defects.append("markdown_projection_invalid_utf8")
        return False
    generated = [
        line.removeprefix("- Generated: ")
        for line in lines
        if line.startswith("- Generated: ")
    ]
    if len(generated) != 1:
        defects.append("markdown_projection_timestamp_invalid")
        return False
    if payload != render_index_payload(merge_state(events), generated[0]):
        defects.append("markdown_projection_stale")
        return False
    return True


def _published_artifacts_are_current(
    root: Path,
    plan: dict[str, Any],
    current_state: dict[str, dict[str, Any]],
    defects: list[str],
) -> bool:
    raw_path = canonical_destination_path(root, plan["raw"]["path"], kind="raw")
    try:
        raw_payload = regular_payload(root, raw_path)
    except SystemExit:
        defects.append("raw_artifact_missing_or_unsafe")
        return False
    if sha256_bytes(raw_payload) != plan["raw"]["sha256"]:
        defects.append("raw_artifact_digest_mismatch")
        return False
    state = current_state.get(str(plan["advice_id"]), {})
    if state.get("path") == plan["normalized"]["path"]:
        normalized_path = canonical_destination_path(
            root, plan["normalized"]["path"], kind="normalized"
        )
        try:
            normalized_payload = regular_payload(root, normalized_path)
        except SystemExit:
            defects.append("normalized_artifact_missing_or_unsafe")
            return False
        if sha256_bytes(normalized_payload) != plan["normalized"]["sha256"]:
            defects.append("normalized_artifact_digest_mismatch")
            return False
    elif state.get("content_sha256") != plan["normalized"]["sha256"]:
        defects.append("normalized_lifecycle_binding_mismatch")
        return False
    return True


def _classify_tagged(
    root: Path,
    plan: dict[str, Any],
    registry: bytes,
    events: list[dict[str, Any]],
    tagged: list[dict[str, Any]],
    receipt_state: str,
    no_effect_state: str,
    defects: list[str],
) -> str:
    projection_current = _projection_is_current(root, events, defects)
    event = tagged[0]
    event_exact = sha256_bytes(canonical_bytes(event)) == plan["event_sha256"]
    boundary_valid = event_exact and _committed_boundary_valid(
        registry, events, plan, event
    )
    artifacts_current = _published_artifacts_are_current(
        root, plan, merge_state(events), defects
    )
    if not event_exact:
        defects.append("committed_event_digest_mismatch")
    if event_exact and not boundary_valid:
        defects.append("committed_boundary_invalid")
    if receipt_state == "conflict":
        defects.append("receipt_conflict")
    if no_effect_state == "current":
        defects.append("no_effect_receipt_with_committed_event")
    elif no_effect_state == "conflict":
        defects.append("no_effect_receipt_conflict")
    fatal = (
        not event_exact
        or not boundary_valid
        or not artifacts_current
        or receipt_state == "conflict"
        or no_effect_state in {"current", "conflict"}
    )
    if fatal:
        return "conflict"
    if receipt_state == "current" and projection_current:
        return "already_applied"
    if receipt_state == "missing":
        defects.append("receipt_missing")
    return "recovery_required"


def _classify_uncommitted(
    root: Path,
    plan: dict[str, Any],
    observation: dict[str, Any],
    intent_state: str,
    receipt_state: str,
    no_effect_state: str,
    defects: list[str],
) -> str:
    destinations_ready = True
    try:
        content = _materialize_plan(root, plan)
        _preflight_destinations(root, plan, content, require_present=False)
        assert_no_pending_intake_intents(root, allowed_plan_id=str(plan["plan_id"]))
    except SystemExit:
        destinations_ready = False
        defects.append("source_destination_or_intent_preflight_failed")
    if no_effect_state == "conflict":
        defects.append("no_effect_receipt_conflict")
        return "conflict"
    if receipt_state != "missing":
        defects.append("receipt_without_committed_event")
        return "conflict"
    if intent_state == "conflict":
        defects.append("plan_intent_conflict")
        return "conflict"
    if intent_state == "current":
        defects.append("plan_intent_pending")
        return (
            "recovery_required"
            if _prestate_current(plan, observation) and destinations_ready
            else "conflict"
        )
    if observation["plan_owned_publication_observed"]:
        defects.append("plan_owned_destination_without_intent_or_event")
        return "recovery_required"
    if _prestate_current(plan, observation) and destinations_ready:
        return "ready"
    reasons = stale_reason_codes(plan, observation)
    if reasons and _observation_is_safe(observation):
        defects.extend(reasons)
        return "stale"
    return "conflict"


def verify_intake_plan(root: Path, path_value: str | Path) -> dict[str, Any]:
    """Classify one immutable intake plan without mutating workspace state."""

    root = root.resolve()
    plan_path, plan, plan_file_sha256 = load_intake_plan(root, path_value)
    plan_ref = rel_path(root, plan_path)
    for key in ("raw", "normalized"):
        canonical_destination_path(root, plan[key]["path"], kind=key)
    registry, events = _registry_snapshot_read_only(root)
    tagged = _tagged_events(events, plan)
    receipt_path = canonical_intake_artifact_path(root, plan["plan_id"], "receipt")
    apply_receipt = receipt_for_plan(plan, plan_ref, plan_file_sha256)
    receipt_state, receipt_digest = receipt_status(
        root, receipt_path, apply_receipt
    )
    no_effect_state, no_effect, no_effect_digest = load_no_effect_receipt(
        root, plan, plan_ref, plan_file_sha256
    )
    intent_state, _intent_digest = intake_intent_status(
        root, plan, plan_ref, plan_file_sha256
    )
    observation = observe_prestate(
        root, plan, registry, regular_payload(root, index_md(root), missing=b"")
    )
    defects: list[str] = []
    no_effect_verified = False
    if tagged:
        status = _classify_tagged(
            root, plan, registry, events, tagged, receipt_state, no_effect_state, defects
        )
    elif no_effect_state == "current" and no_effect is not None:
        no_effect_verified = _no_effect_proof_current(
            root, plan, registry, events, no_effect, intent_state
        )
        status = "settled_no_effect" if no_effect_verified else "conflict"
        if no_effect_verified:
            receipt_state, receipt_digest = "current", no_effect_digest
        else:
            defects.append("no_effect_proof_invalid")
    else:
        status = _classify_uncommitted(
            root,
            plan,
            observation,
            intent_state,
            receipt_state,
            no_effect_state,
            defects,
        )
    destination_effect = any(
        observation["destination_observations"][key]["state"] == "exact"
        for key in ("raw", "normalized")
    )
    effect_observed = bool(tagged) or destination_effect
    return {
        "result_kind": "external_advice_intake_verify_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": status,
        "plan_id": plan["plan_id"],
        "advice_id": plan["advice_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "receipt_ref": rel_path(root, receipt_path),
        "receipt_kind": (
            no_effect["receipt_kind"]
            if status == "settled_no_effect" and no_effect is not None
            else apply_receipt["receipt_kind"] if receipt_state == "current" else None
        ),
        "receipt_status": receipt_state,
        "receipt_file_sha256": receipt_digest,
        "plan_effect_observed": effect_observed,
        "plan_intent_observed": intent_state != "missing",
        "plan_owned_publication_observed": destination_effect,
        "prestate_current": _prestate_current(plan, observation),
        "no_effect_verified": no_effect_verified,
        "integrity_valid": status != "conflict",
        "apply_eligible": status in {"ready", "already_applied", "recovery_required"},
        "idempotent_replay": status in {"already_applied", "settled_no_effect"},
        "defects": defects,
        "mutation_performed": False,
    }
