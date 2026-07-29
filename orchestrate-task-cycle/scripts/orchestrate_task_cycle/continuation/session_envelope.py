"""Exact session-lease reopening shared by every continuation entry point."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any

from .contracts import ContinuationContractError
from .safe_files import scan_session_files


_RISK = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}


def live_session_lease_candidates(
    root: Path,
) -> list[tuple[Path, dict[str, Any], str]]:
    """Return live leases bound to the exact current host interaction."""

    from manage_agent_authority.session_lease import validate_session_lease

    candidates: list[tuple[Path, dict[str, Any], str]] = []
    thread = os.environ.get("CODEX_THREAD_ID")
    if not thread:
        return candidates
    thread_sha = hashlib.sha256(thread.encode("utf-8")).hexdigest()
    host_receipt = os.environ.get("CODEX_SESSION_APPROVAL_RECEIPT")
    host_receipt_sha = (
        hashlib.sha256(host_receipt.encode("utf-8")).hexdigest()
        if host_receipt
        else None
    )
    eligible_activation_ids: set[str] | None = None
    observed_at = datetime.now(timezone.utc)
    for path, payload in scan_session_files(root, "session-lease.json"):
        try:
            lease = validate_session_lease(json.loads(payload))
        except (ValueError, json.JSONDecodeError):
            continue
        binding = lease["session_binding"]
        if binding["thread_binding_sha256"] != thread_sha:
            continue
        if (
            binding["trust_class"] == "platform_host_receipt"
            and binding["approval_receipt_sha256"] != host_receipt_sha
        ):
            continue
        if lease["lifecycle"]["status"] != "live":
            continue
        expires_at = lease.get("expires_at")
        if (
            expires_at is not None
            and observed_at >= _time(expires_at, "session expiry")
        ):
            continue
        if eligible_activation_ids is None:
            from manage_agent_authority.authority_interaction_broker import (
                status as authority_mode_status,
            )

            eligible_activation_ids = {
                str(row["activation_id"])
                for row in authority_mode_status(root).get("activations") or []
                if isinstance(row, dict) and row.get("eligible") is True
            }
        if binding["activation_evidence_id"] not in eligible_activation_ids:
            continue
        candidates.append((path, lease, hashlib.sha256(payload).hexdigest()))
    return candidates


def current_session_lease(root: Path) -> tuple[Path, dict[str, Any], str]:
    candidates = live_session_lease_candidates(root)
    if not candidates:
        raise ContinuationContractError(
            "session approval required: no live lease matches this host session"
        )
    if len(candidates) > 1:
        raise ContinuationContractError(
            "multiple live session leases match; stop the stale session first"
        )
    return candidates[0]


def _time(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContinuationContractError(f"{label} is not RFC3339") from exc
    if parsed.tzinfo is None:
        raise ContinuationContractError(f"{label} lacks a timezone")
    return parsed.astimezone(timezone.utc)


def _session_path(root: Path, ref: str) -> Path:
    candidate = PurePosixPath(ref)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ContinuationContractError("session lease ref is unsafe")
    current = root
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise ContinuationContractError(
                "session lease path traverses a symlink"
            )
    return current


def _host_binding_current(lease: dict[str, Any]) -> bool:
    binding = lease["session_binding"]
    thread = os.environ.get("CODEX_THREAD_ID")
    if (
        not thread
        or hashlib.sha256(thread.encode("utf-8")).hexdigest()
        != binding["thread_binding_sha256"]
    ):
        return False
    if binding["trust_class"] != "platform_host_receipt":
        return True
    receipt = os.environ.get("CODEX_SESSION_APPROVAL_RECEIPT")
    return bool(
        receipt
        and hashlib.sha256(receipt.encode("utf-8")).hexdigest()
        == binding["approval_receipt_sha256"]
    )


def _activation_plan(
    root: Path,
    lease: dict[str, Any],
    *,
    at: str,
) -> dict[str, Any]:
    from manage_agent_authority import authority_interaction as interaction

    activation_id = lease["session_binding"]["activation_evidence_id"]
    rows = [
        row
        for row in interaction.status(root, at=at).get("activations") or []
        if isinstance(row, dict)
        and row.get("eligible") is True
        and row.get("activation_id") == activation_id
        and isinstance(row.get("activation_plan"), dict)
    ]
    if len(rows) != 1:
        raise ContinuationContractError(
            "session activation is no longer uniquely eligible"
        )
    _binding, plan = interaction.load_activation_plan(
        root, rows[0]["activation_plan"]
    )
    return plan


def reopen_session_envelope(
    root: str | Path,
    state: dict[str, Any],
    *,
    at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reopen exact lease bytes and the still-current signed activation."""

    from manage_agent_authority.session_binding import (
        canonical_bytes,
        session_ref,
    )
    from manage_agent_authority.session_lease import validate_session_lease
    from manage_agent_authority.stable_store import read_regular

    workspace = Path(root).resolve(strict=True)
    binding = state["session_lease_binding"]
    expected_ref = session_ref(str(state["session_id"]))
    if binding["ref"] != expected_ref:
        raise ContinuationContractError("continuation session lease ref changed")
    raw = read_regular(
        _session_path(workspace, expected_ref),
        label="continuation session lease",
        max_bytes=256 * 1024,
    )
    if raw is None or hashlib.sha256(raw).hexdigest() != binding["sha256"]:
        raise ContinuationContractError("continuation session lease bytes changed")
    try:
        lease = validate_session_lease(json.loads(raw))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ContinuationContractError(
            "continuation session lease is invalid"
        ) from exc
    observed = _time(at, "session observation time")
    expiry = lease.get("expires_at")
    if (
        lease["session_binding"]["session_id"] != state["session_id"]
        or lease["goal_id"] != state["goal_id"]
        or lease["task_family"] != state["task_family"]
        or lease["budgets"] != state["budgets"]
        or lease["lifecycle"]["status"] != "live"
        or lease["lifecycle"]["host_receipt_live"] is not True
        or (expiry is not None and observed >= _time(expiry, "session expiry"))
        or not _host_binding_current(lease)
    ):
        raise ContinuationContractError(
            "continuation state is outside its live session lease"
        )
    usage = state["usage"]
    budgets = state["budgets"]
    if (
        usage["cycles"] > budgets["max_cycles"]
        or usage["agent_actions"] > budgets["max_agent_actions"]
        or len(usage["active_long_runs"])
        > budgets["max_concurrent_long_runs"]
        or any(
            count > budgets["max_commits_per_cycle"]
            for count in usage["commits_by_cycle"].values()
        )
    ):
        raise ContinuationContractError("continuation usage exceeds its lease")
    plan = _activation_plan(workspace, lease, at=at)
    snapshot = plan["goal_policy_snapshot"]
    manifest_digest = hashlib.sha256(
        canonical_bytes(plan["manifest_bindings"])
    ).hexdigest()
    profile = plan["profile"]
    if (
        lease["goal_digest"] != snapshot["final_goal_sha256"]
        or lease["policy_digest"] != snapshot["authority_policy_sha256"]
        or lease["manifest_digest"] != manifest_digest
        or lease["activation_mode"] != plan["authority_interaction_mode"]
        or lease["risk_ceiling"] not in _RISK
        or profile["max_risk"] not in _RISK
        or _RISK[lease["risk_ceiling"]] > _RISK[profile["max_risk"]]
        or not set(lease["allowed_operation_groups"])
        <= set(profile["operation_groups"])
    ):
        raise ContinuationContractError(
            "session lease differs from its signed activation envelope"
        )
    return lease, plan


def verify_live_state_lease(
    root: Path,
    state: dict[str, Any],
    candidates: list[tuple[Path, dict[str, Any], str]],
    *,
    at: str,
) -> bool:
    """Verify exact state-to-lease bytes before continuing a session."""

    matches = [
        row
        for row in candidates
        if row[1]["session_binding"]["session_id"] == state["session_id"]
    ]
    if not matches:
        return False
    if len(matches) != 1:
        raise ContinuationContractError(
            "multiple live leases match the continuation session"
        )
    path, _lease, payload_sha = matches[0]
    observed = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": payload_sha,
    }
    if observed != state["session_lease_binding"]:
        raise ContinuationContractError(
            "continuation session lease binding changed"
        )
    reopen_session_envelope(root, state, at=at)
    return True


__all__ = (
    "current_session_lease",
    "live_session_lease_candidates",
    "reopen_session_envelope",
    "verify_live_state_lease",
)
