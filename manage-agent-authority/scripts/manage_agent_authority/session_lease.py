"""Closed session-scoped authority lease and budget state transitions."""

from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Iterable

from .session_binding import (
    SessionBindingError,
    sha256_value,
    validate_session_binding,
)


SESSION_LEASE_KIND = "authority_session_lease"
SESSION_LEASE_SCHEMA_VERSION = 1
DEFAULT_BUDGETS = {
    "max_cycles": 3,
    # Twenty-four actions is the per-cycle planning envelope.  The lease spans
    # three cycles, so the session budget must cover all three without forcing
    # an artificial re-approval between cycles.
    "max_agent_actions": 72,
    "max_concurrent_long_runs": 1,
    "max_commits_per_cycle": 1,
}
_RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,255}$")
_FORBIDDEN_NARROWING_OPERATIONS = frozenset(
    {
        "activate_authority",
        "raise_authority_mode",
        "change_authority_policy",
        "change_goal_design",
        "push_git",
        "external_mutation",
        "destructive_mutation",
        "access_credentials",
    }
)


class SessionLeaseError(ValueError):
    """Raised when a lease would widen authority or violate its lifecycle."""


def _opaque(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    normalized = str(value or "").strip()
    if not _OPAQUE.fullmatch(normalized):
        raise SessionLeaseError(f"{label} must be a bounded opaque identifier")
    return normalized


def _time(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    normalized = str(value or "")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SessionLeaseError(f"{label} must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise SessionLeaseError(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _unique_strings(value: Iterable[str], label: str) -> list[str]:
    items = [str(item or "").strip() for item in value]
    if (
        not items
        or any(not _OPAQUE.fullmatch(item) for item in items)
        or len(items) != len(set(items))
    ):
        raise SessionLeaseError(f"{label} must contain unique opaque identifiers")
    return sorted(items)


def _budgets(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(DEFAULT_BUDGETS):
        raise SessionLeaseError("session budgets must use the closed budget fields")
    normalized: dict[str, int] = {}
    for field, default in DEFAULT_BUDGETS.items():
        item = value.get(field, default)
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            raise SessionLeaseError(f"{field} must be a positive integer")
        normalized[field] = item
    return normalized


def _usage(value: Any) -> dict[str, Any]:
    fields = {
        "cycles",
        "agent_actions",
        "active_long_runs",
        "commits_by_cycle",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise SessionLeaseError("session usage fields are not closed")
    cycles = value["cycles"]
    actions = value["agent_actions"]
    if (
        isinstance(cycles, bool)
        or not isinstance(cycles, int)
        or cycles < 0
        or isinstance(actions, bool)
        or not isinstance(actions, int)
        or actions < 0
    ):
        raise SessionLeaseError("session usage counters must be non-negative integers")
    runs = _unique_strings(value["active_long_runs"], "active_long_runs") if value["active_long_runs"] else []
    commits = value["commits_by_cycle"]
    if not isinstance(commits, dict):
        raise SessionLeaseError("commits_by_cycle must be an object")
    normalized_commits: dict[str, int] = {}
    for cycle_id, count in commits.items():
        key = _opaque(cycle_id, "commit cycle_id")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise SessionLeaseError("commit usage must be non-negative")
        normalized_commits[str(key)] = count
    return {
        "cycles": cycles,
        "agent_actions": actions,
        "active_long_runs": runs,
        "commits_by_cycle": dict(sorted(normalized_commits.items())),
    }


def _identity(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in (
            "schema_version",
            "artifact_kind",
            "session_binding",
            "goal_id",
            "task_family",
            "activation_mode",
            "risk_ceiling",
            "allowed_operation_groups",
            "goal_digest",
            "policy_digest",
            "manifest_digest",
            "issued_at",
            "expires_at",
            "budgets",
        )
    }


def _state_material(value: dict[str, Any]) -> dict[str, Any]:
    return {
        **_identity(value),
        "lifecycle": value["lifecycle"],
        "usage": value["usage"],
    }


def build_session_lease(
    *,
    session_binding: dict[str, Any],
    goal_id: str,
    task_family: str,
    activation_mode: str,
    activation_risk_ceiling: str,
    allowed_operation_groups: Iterable[str],
    goal_digest: str,
    policy_digest: str,
    manifest_digest: str,
    issued_at: str,
    expires_at: str | None,
    budgets: dict[str, int] | None = None,
) -> dict[str, Any]:
    binding = validate_session_binding(session_binding)
    if activation_mode not in {"workspace", "governed"}:
        raise SessionLeaseError("activation_mode must be workspace or governed")
    if activation_risk_ceiling not in _RISK_ORDER:
        raise SessionLeaseError("unknown activation risk ceiling")
    # A session receipt only amortizes repeated in-session approval.  It never
    # turns R3 or separately confirmed operations into ambient authority,
    # regardless of whether the receipt came from the host or the TTY fallback.
    risk = min((activation_risk_ceiling, "R2"), key=_RISK_ORDER.get)
    operations = _unique_strings(
        allowed_operation_groups, "allowed_operation_groups"
    )
    if _FORBIDDEN_NARROWING_OPERATIONS.intersection(operations):
        raise SessionLeaseError(
            "session approval cannot authorize mode, policy, R3, or external effects"
        )
    lease: dict[str, Any] = {
        "schema_version": SESSION_LEASE_SCHEMA_VERSION,
        "artifact_kind": SESSION_LEASE_KIND,
        "session_binding": binding,
        "goal_id": _opaque(goal_id, "goal_id"),
        "task_family": _opaque(task_family, "task_family"),
        "activation_mode": activation_mode,
        "risk_ceiling": risk,
        "allowed_operation_groups": operations,
        "goal_digest": _opaque(goal_digest, "goal_digest"),
        "policy_digest": _opaque(policy_digest, "policy_digest"),
        "manifest_digest": _opaque(manifest_digest, "manifest_digest"),
        "issued_at": _time(issued_at, "issued_at"),
        "expires_at": _time(expires_at, "expires_at", nullable=True),
        "budgets": _budgets(budgets or dict(DEFAULT_BUDGETS)),
        "lifecycle": {
            "status": "live",
            "host_receipt_live": True,
            "stopped_at": None,
            "last_seen_at": _time(issued_at, "issued_at"),
        },
        "usage": {
            "cycles": 0,
            "agent_actions": 0,
            "active_long_runs": [],
            "commits_by_cycle": {},
        },
    }
    lease["lease_id"] = f"lease-{sha256_value(_identity(lease))[:32]}"
    lease["state_sha256"] = sha256_value(_state_material(lease))
    return validate_session_lease(lease)


def validate_session_lease(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SessionLeaseError("session lease must be an object")
    fields = {
        "schema_version",
        "artifact_kind",
        "session_binding",
        "goal_id",
        "task_family",
        "activation_mode",
        "risk_ceiling",
        "allowed_operation_groups",
        "goal_digest",
        "policy_digest",
        "manifest_digest",
        "issued_at",
        "expires_at",
        "budgets",
        "lifecycle",
        "usage",
        "lease_id",
        "state_sha256",
    }
    if set(value) != fields:
        raise SessionLeaseError("session lease fields are not closed")
    if (
        value.get("schema_version") != SESSION_LEASE_SCHEMA_VERSION
        or value.get("artifact_kind") != SESSION_LEASE_KIND
    ):
        raise SessionLeaseError("unsupported session lease contract")
    binding = validate_session_binding(value.get("session_binding"))
    activation_mode = str(value.get("activation_mode") or "")
    if activation_mode not in {"workspace", "governed"}:
        raise SessionLeaseError("invalid activation_mode")
    risk = str(value.get("risk_ceiling") or "")
    if risk not in _RISK_ORDER:
        raise SessionLeaseError("invalid risk_ceiling")
    if _RISK_ORDER[risk] > _RISK_ORDER["R2"]:
        raise SessionLeaseError("session approval cannot carry R3 authority")
    operations = _unique_strings(
        value.get("allowed_operation_groups") or [],
        "allowed_operation_groups",
    )
    if _FORBIDDEN_NARROWING_OPERATIONS.intersection(operations):
        raise SessionLeaseError("session lease widens authority")
    lifecycle = value.get("lifecycle")
    lifecycle_fields = {
        "status",
        "host_receipt_live",
        "stopped_at",
        "last_seen_at",
    }
    if not isinstance(lifecycle, dict) or set(lifecycle) != lifecycle_fields:
        raise SessionLeaseError("session lifecycle fields are not closed")
    if lifecycle["status"] not in {"live", "stopped", "lost"}:
        raise SessionLeaseError("invalid session lifecycle status")
    if not isinstance(lifecycle["host_receipt_live"], bool):
        raise SessionLeaseError("host_receipt_live must be boolean")
    if lifecycle["status"] == "live" and not lifecycle["host_receipt_live"]:
        raise SessionLeaseError("live session requires a live host receipt")
    normalized_lifecycle = {
        "status": lifecycle["status"],
        "host_receipt_live": lifecycle["host_receipt_live"],
        "stopped_at": _time(
            lifecycle["stopped_at"], "stopped_at", nullable=True
        ),
        "last_seen_at": _time(lifecycle["last_seen_at"], "last_seen_at"),
    }
    normalized: dict[str, Any] = {
        "schema_version": SESSION_LEASE_SCHEMA_VERSION,
        "artifact_kind": SESSION_LEASE_KIND,
        "session_binding": binding,
        "goal_id": _opaque(value.get("goal_id"), "goal_id"),
        "task_family": _opaque(value.get("task_family"), "task_family"),
        "activation_mode": activation_mode,
        "risk_ceiling": risk,
        "allowed_operation_groups": operations,
        "goal_digest": _opaque(value.get("goal_digest"), "goal_digest"),
        "policy_digest": _opaque(value.get("policy_digest"), "policy_digest"),
        "manifest_digest": _opaque(
            value.get("manifest_digest"), "manifest_digest"
        ),
        "issued_at": _time(value.get("issued_at"), "issued_at"),
        "expires_at": _time(value.get("expires_at"), "expires_at", nullable=True),
        "budgets": _budgets(value.get("budgets")),
        "lifecycle": normalized_lifecycle,
        "usage": _usage(value.get("usage")),
    }
    expected_id = f"lease-{sha256_value(_identity(normalized))[:32]}"
    if value.get("lease_id") != expected_id:
        raise SessionLeaseError("lease_id does not match immutable lease identity")
    expected_state = sha256_value(_state_material(normalized))
    if value.get("state_sha256") != expected_state:
        raise SessionLeaseError("session lease state digest mismatch")
    return {
        **normalized,
        "lease_id": expected_id,
        "state_sha256": expected_state,
    }


def _refresh(value: dict[str, Any]) -> dict[str, Any]:
    lease = dict(value)
    lease["state_sha256"] = sha256_value(_state_material(lease))
    return validate_session_lease(lease)


def assert_dispatch_allowed(
    value: dict[str, Any],
    *,
    at: str,
    goal_digest: str,
    policy_digest: str,
    manifest_digest: str,
    operation_group: str,
    risk_tier: str,
) -> dict[str, Any]:
    lease = validate_session_lease(value)
    observed = _time(at, "at")
    if lease["lifecycle"]["status"] != "live":
        raise SessionLeaseError("session does not allow new dispatch")
    if (
        lease["expires_at"] is not None
        and datetime.fromisoformat(observed.replace("Z", "+00:00"))
        >= datetime.fromisoformat(
            lease["expires_at"].replace("Z", "+00:00")
        )
    ):
        raise SessionLeaseError("session lease has expired")
    if (
        lease["goal_digest"] != goal_digest
        or lease["policy_digest"] != policy_digest
        or lease["manifest_digest"] != manifest_digest
    ):
        raise SessionLeaseError("session authority inputs drifted")
    operation = _opaque(operation_group, "operation_group")
    if operation not in lease["allowed_operation_groups"]:
        raise SessionLeaseError("operation is outside the session envelope")
    if risk_tier not in _RISK_ORDER:
        raise SessionLeaseError("unknown requested risk tier")
    if _RISK_ORDER[risk_tier] > _RISK_ORDER[lease["risk_ceiling"]]:
        raise SessionLeaseError("requested risk exceeds the session ceiling")
    return lease


def consume_budget(
    value: dict[str, Any],
    *,
    kind: str,
    identifier: str | None = None,
) -> dict[str, Any]:
    lease = validate_session_lease(value)
    usage = {
        **lease["usage"],
        "active_long_runs": list(lease["usage"]["active_long_runs"]),
        "commits_by_cycle": dict(lease["usage"]["commits_by_cycle"]),
    }
    budgets = lease["budgets"]
    if kind == "cycle":
        if usage["cycles"] >= budgets["max_cycles"]:
            raise SessionLeaseError("session cycle budget exhausted")
        usage["cycles"] += 1
    elif kind == "agent_action":
        if usage["agent_actions"] >= budgets["max_agent_actions"]:
            raise SessionLeaseError("session agent-action budget exhausted")
        usage["agent_actions"] += 1
    elif kind == "long_run":
        run_id = _opaque(identifier, "run_id")
        if run_id in usage["active_long_runs"]:
            return lease
        if len(usage["active_long_runs"]) >= budgets["max_concurrent_long_runs"]:
            raise SessionLeaseError("concurrent long-run budget exhausted")
        usage["active_long_runs"] = sorted(
            [*usage["active_long_runs"], run_id]
        )
    elif kind == "commit":
        cycle_id = _opaque(identifier, "cycle_id")
        count = usage["commits_by_cycle"].get(cycle_id, 0)
        if count >= budgets["max_commits_per_cycle"]:
            raise SessionLeaseError("cycle commit budget exhausted")
        usage["commits_by_cycle"][cycle_id] = count + 1
        usage["commits_by_cycle"] = dict(sorted(usage["commits_by_cycle"].items()))
    else:
        raise SessionLeaseError("unknown session budget kind")
    updated = dict(lease)
    updated["usage"] = usage
    return _refresh(updated)


def settle_long_run(value: dict[str, Any], run_id: str) -> dict[str, Any]:
    lease = validate_session_lease(value)
    identifier = _opaque(run_id, "run_id")
    if identifier not in lease["usage"]["active_long_runs"]:
        return lease
    updated = dict(lease)
    updated["usage"] = {
        **lease["usage"],
        "active_long_runs": [
            item for item in lease["usage"]["active_long_runs"] if item != identifier
        ],
        "commits_by_cycle": dict(lease["usage"]["commits_by_cycle"]),
    }
    return _refresh(updated)


def update_liveness(
    value: dict[str, Any],
    *,
    at: str,
    host_receipt_live: bool,
    stop: bool = False,
) -> dict[str, Any]:
    lease = validate_session_lease(value)
    observed = _time(at, "at")
    status = "stopped" if stop else "live" if host_receipt_live else "lost"
    updated = dict(lease)
    updated["lifecycle"] = {
        "status": status,
        "host_receipt_live": bool(host_receipt_live) and not stop,
        "stopped_at": observed if stop else lease["lifecycle"]["stopped_at"],
        "last_seen_at": observed,
    }
    return _refresh(updated)


__all__ = (
    "DEFAULT_BUDGETS",
    "SESSION_LEASE_KIND",
    "SESSION_LEASE_SCHEMA_VERSION",
    "SessionBindingError",
    "SessionLeaseError",
    "assert_dispatch_allowed",
    "build_session_lease",
    "consume_budget",
    "settle_long_run",
    "update_liveness",
    "validate_session_lease",
)
