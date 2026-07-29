"""Fail-closed proof that one sealed owner action is a local long run."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..authority_artifacts import (
    read_bound_authority_json,
    validate_authority_artifacts,
)
from ..authority_boundary import project_authority_packet
from ..authority_packet import validate_authority_packet_cycle
from ..cycle_ledger import read_events
from ..stage.artifact_store import load_compiler_artifact
from ..stage.contracts import (
    PREPARATION_SCHEMA_VERSION_V3,
    validate_preparation,
)
from ..stage.executor_registry import executor_spec
from ..stage.v2_context import (
    selected_state_fingerprint,
    selector_fingerprints,
)
from .state import validate_state


_OPERATION = {
    "skill_id": "run-task-code-and-log",
    "skill_version": "2.0.0",
    "operation_id": "run_long",
    "operation_version": "1",
}
_AUTHORITY_PROJECTION_FIELDS = (
    "event_id",
    "status",
    "decision_binding",
    "operation_binding",
    "subject",
    "scope",
    "axes",
    "reservation_binding",
    "dispatch_preflight",
    "effective_authority_fingerprint",
)
_PACKET_FIELDS = {
    "step",
    "schema_version",
    "artifact_kind",
    "packet_id",
    "decision_binding",
    "operation_binding",
    "subject",
    "scope",
    "axes",
    "selected_grants",
    "lineage_grants",
    "approval_projection",
    "composition_receipt",
    "reservation_binding",
    "dispatch_preflight",
    "effective_authority_fingerprint",
    "evidence_ids",
    "packet_sha256",
}
_RISK = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}


def _scalar_tree(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_scalar_tree(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _scalar_tree(item)
            for key, item in sorted(value.items())
        }
    return str(type(value).__name__)


def _authority_projection(event: dict[str, Any]) -> dict[str, Any]:
    return {
        field: _scalar_tree(event[field])
        for field in _AUTHORITY_PROJECTION_FIELDS
        if field in event
    }


def _sealed_authority_projection(
    root: Path, preparation: dict[str, Any]
) -> dict[str, Any]:
    prepared = validate_preparation(preparation)
    registered = executor_spec("run").projection()
    if (
        prepared["schema_version"] != PREPARATION_SCHEMA_VERSION_V3
        or prepared["target"] != "run"
        or prepared["executor_kind"] != "owner"
        or prepared["executor_spec"] != registered
        or registered["owner_id"] != "run-task-code-and-log"
        or registered["side_effect_class"]
        != "external_or_long_running_effect"
    ):
        raise ValueError("run preparation is not the sealed local-run shape")
    cycle_id = str(prepared["cycle_id"])
    context = load_compiler_artifact(
        root, cycle_id, prepared["context_binding"], "context"
    )
    work_order = load_compiler_artifact(
        root, cycle_id, prepared["work_order_binding"], "work_order"
    )
    model = context.get("model_context")
    if (
        not isinstance(model, dict)
        or context.get("cycle_id") != cycle_id
        or context.get("target") != "run"
        or context.get("state_fingerprint")
        != prepared["state_fingerprint"]
        or context.get("precondition_fingerprints")
        != prepared["precondition_fingerprints"]
        or work_order.get("cycle_id") != cycle_id
        or work_order.get("target") != "run"
        or work_order.get("executor_spec") != registered
        or work_order.get("context_binding")
        != prepared["context_binding"]
        or work_order.get("state_fingerprint")
        != prepared["state_fingerprint"]
        or work_order.get("precondition_fingerprints")
        != prepared["precondition_fingerprints"]
        or selected_state_fingerprint(
            model, prepared["fingerprint_roles"]
        )
        != prepared["state_fingerprint"]
    ):
        raise ValueError("run preparation inputs are not mutually bound")
    authority = model.get("authority")
    if not isinstance(authority, dict) or not authority:
        raise ValueError("run preparation lacks sealed authority evidence")
    expected = selector_fingerprints(
        {}, {"authority": authority}, ("authority",)
    )["authority"]
    if prepared["precondition_fingerprints"].get("authority") != expected:
        raise ValueError("run authority precondition fingerprint differs")
    return authority


def _authority_packet(
    root: Path,
    cycle_id: str,
    sealed_projection: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    matches = [
        event
        for event in read_events(root, cycle_id)
        if event.get("step") == "authority"
    ]
    if len(matches) != 1:
        raise ValueError("run requires one authoritative cycle decision")
    event = matches[0]
    if (
        event.get("status") not in {"complete", "completed"}
        or _authority_projection(event) != sealed_projection
    ):
        raise ValueError("run preparation authority evidence changed")
    if not _PACKET_FIELDS <= set(event):
        raise ValueError("authority event lacks its closed packet")
    packet = {field: event[field] for field in _PACKET_FIELDS}
    projection = project_authority_packet(packet)
    findings = list(projection.findings)
    findings.extend(validate_authority_artifacts(packet, root))
    if findings:
        raise ValueError("run authority packet no longer verifies")
    validate_authority_packet_cycle(root, cycle_id, packet)
    decision_binding = packet["decision_binding"]
    decision = read_bound_authority_json(
        root,
        {
            "ref": decision_binding["artifact_ref"],
            "sha256": decision_binding["artifact_sha256"],
        },
        "local long-run decision",
    )
    return packet, decision


def _session_lease(
    root: Path, state: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    from manage_agent_authority.session_binding import session_ref
    from manage_agent_authority.session_lease import validate_session_lease
    from manage_agent_authority.stable_store import read_regular

    binding = state["session_lease_binding"]
    expected_ref = session_ref(state["session_id"])
    if binding["ref"] != expected_ref:
        raise ValueError("continuation session lease ref changed")
    raw = read_regular(
        root / expected_ref,
        label="continuation local-run session lease",
        max_bytes=256 * 1024,
    )
    assert raw is not None
    if hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ValueError("continuation session lease bytes changed")
    try:
        lease = validate_session_lease(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("continuation session lease is unreadable") from exc
    if (
        lease["session_binding"]["session_id"] != state["session_id"]
        or lease["goal_id"] != state["goal_id"]
        or lease["task_family"] != state["task_family"]
        or lease["lifecycle"]["status"] != "live"
        or lease["lifecycle"]["host_receipt_live"] is not True
        or lease["risk_ceiling"] not in _RISK
        or _RISK[lease["risk_ceiling"]] < _RISK["R2"]
        or "local_long_run" not in lease["allowed_operation_groups"]
    ):
        raise ValueError("session lease does not cover a local long run")
    return lease, raw


def _active_plan(root: Path, lease: dict[str, Any]) -> dict[str, Any]:
    from manage_agent_authority import authority_interaction as interaction

    activation_id = lease["session_binding"]["activation_evidence_id"]
    rows = [
        row
        for row in interaction.status(root).get("activations") or []
        if isinstance(row, dict)
        and row.get("eligible") is True
        and row.get("activation_id") == activation_id
        and isinstance(row.get("activation_plan"), dict)
    ]
    if len(rows) != 1:
        raise ValueError("session activation is no longer uniquely eligible")
    _binding, plan = interaction.load_activation_plan(
        root, rows[0]["activation_plan"]
    )
    return plan


def _request_matches_session(
    root: Path,
    state: dict[str, Any],
    lease: dict[str, Any],
    packet: dict[str, Any],
    decision: dict[str, Any],
    *,
    at: str,
) -> bool:
    # ``authority_interaction`` owns the public compatibility import cycle;
    # initialize it before opening the broker's exact session-scope helper.
    from manage_agent_authority import authority_interaction as _interaction
    from manage_agent_authority.authority_interaction_broker import (
        _session_scope,
    )
    from manage_agent_authority.projection_io import load_grant_artifact

    _ = _interaction
    request = decision.get("request")
    context = decision.get("evaluation_context")
    if not isinstance(request, dict) or not isinstance(context, dict):
        return False
    operation = {
        field: request.get(field) for field in _OPERATION
    }
    packet_operation = packet.get("operation_binding") or {}
    axes = packet.get("axes") or {}
    scope = packet.get("scope") or {}
    external = axes.get("external_input") or {}
    authority = axes.get("authority") or {}
    local = axes.get("local_resolution") or {}
    reservation = packet.get("reservation_binding") or {}
    preflight = packet.get("dispatch_preflight") or {}
    if (
        operation != _OPERATION
        or any(packet_operation.get(key) != value for key, value in _OPERATION.items())
        or packet_operation.get("mutation_class") != "local_mutation"
        or packet["decision_binding"].get("decision") != "allowed"
        or authority.get("status") != "granted"
        or local.get("status") != "available"
        or external.get("status") != "not_required"
        or reservation.get("applicability") != "required"
        or reservation.get("status") != "reserved"
        or preflight.get("status") != "verified"
        or preflight.get("stage") != "pre_dispatch"
        or request.get("effect_class") != "run_long"
        or request.get("mutation_class") != "local_mutation"
        or request.get("data_class") != "runtime_state"
        or request.get("risk_tier") != "R2"
        or request.get("cycle_id") != state["active_cycle_id"]
        or request.get("task_id") != state["active_task_id"]
        or scope.get("cycle_id") != state["active_cycle_id"]
        or scope.get("task_id") != state["active_task_id"]
    ):
        return False
    ceiling = context.get("session_ceiling") or {}
    envelope = context.get("goal_autonomy_envelope") or {}
    source = envelope.get("source_binding") or {}
    if (
        ceiling.get("evidence_id") != state["session_id"]
        or source.get("sha256") != lease["goal_digest"]
    ):
        return False
    selected = packet.get("selected_grants")
    if not isinstance(selected, list) or len(selected) != 1:
        return False
    row = selected[0]
    if not isinstance(row, dict):
        return False
    grant, grant_sha = load_grant_artifact(root, str(row.get("grant_id") or ""))
    if (
        row.get("grant_sha256") != grant_sha
        or grant.get("session_id") != state["session_id"]
        or grant.get("task_id") != state["active_task_id"]
        or grant.get("risk_ceiling") not in _RISK
        or _RISK[grant["risk_ceiling"]] < _RISK["R2"]
        or grant.get("operations") != [_OPERATION]
        or (grant.get("policy_snapshot") or {}).get("sha256")
        != lease["policy_digest"]
    ):
        return False
    plan = _active_plan(root, lease)
    session_id, _expiry = _session_scope(
        root,
        activation_id=lease["session_binding"]["activation_evidence_id"],
        at=at,
        request=request,
        plan=plan,
    )
    return session_id == state["session_id"]


def local_long_run_authorized(
    root: str | Path,
    state: dict[str, Any],
    preparation: dict[str, Any],
    *,
    at: str,
) -> bool:
    """Return true only for a fully sealed, live-session local long run."""

    try:
        workspace = Path(root).resolve(strict=True)
        current = validate_state(state)
        if not current["host_session_live"]:
            return False
        observed = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        if observed.tzinfo is None or not os.environ.get("CODEX_THREAD_ID"):
            return False
        sealed = _sealed_authority_projection(workspace, preparation)
        packet, decision = _authority_packet(
            workspace, current["active_cycle_id"], sealed
        )
        lease, _raw = _session_lease(workspace, current)
        return _request_matches_session(
            workspace,
            current,
            lease,
            packet,
            decision,
            at=at,
        )
    except (OSError, UnicodeError, ValueError, SystemExit):
        return False


__all__ = ("local_long_run_authorized",)
