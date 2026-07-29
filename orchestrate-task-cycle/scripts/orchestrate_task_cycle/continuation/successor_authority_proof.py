"""Read-only session and settlement proof for cross-cycle continuation."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from ..selected_successor_execution_support import ACTIONS, checkpoint_states


_RISK = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("successor proof timestamps must include a timezone")
    return parsed


def _default_skills_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[4]
    return candidate if (candidate / "manage-agent-authority").is_dir() else None


def _session_envelope(
    root: Path,
    session_id: str,
    goal_id: str | None,
    task_family: str | None,
) -> tuple[dict[str, Any], str]:
    from manage_agent_authority.session_binding import session_ref
    from manage_agent_authority.session_lease import validate_session_lease
    from manage_agent_authority.stable_store import read_regular

    ref = session_ref(session_id)
    current = root
    for part in Path(ref).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("session lease path traverses a symlink")
    raw = read_regular(current, label="successor session lease")
    if raw is None:
        raise ValueError("successor session lease is absent")
    try:
        lease = validate_session_lease(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise ValueError("successor session lease is unreadable") from exc
    if (
        lease["session_binding"]["session_id"] != session_id
        or lease["lifecycle"]["status"] != "live"
        or lease["lifecycle"]["host_receipt_live"] is not True
        or (goal_id is not None and lease["goal_id"] != goal_id)
        or (task_family is not None and lease["task_family"] != task_family)
    ):
        raise ValueError("successor session envelope differs")
    return lease, hashlib.sha256(raw).hexdigest()


def _operation_is_allowed(
    lease: dict[str, Any], operation: dict[str, Any]
) -> bool:
    from manage_agent_authority.authority_interaction import OPERATION_REGISTRY

    key = (
        operation["skill_id"],
        operation["operation_id"],
        operation["operation_version"],
    )
    return any(
        group in lease["allowed_operation_groups"]
        and key in OPERATION_REGISTRY[group]
        for group in OPERATION_REGISTRY
    )


def _settlements(
    root: Path,
    bundle: dict[str, Any],
    proofs: dict[str, dict[str, Any]],
    lease: dict[str, Any],
    *,
    session_id: str,
    skills_root: Path | None,
) -> tuple[datetime, tuple[dict[str, str], ...]]:
    from manage_agent_authority.canonical import object_sha256, read_object, sha256_file
    from manage_agent_authority.historical_proof_chain import (
        validate_historical_proof_chains,
    )
    from manage_agent_authority.projection_io import load_grant_artifact
    from manage_agent_authority.projection_receipts import validate_use_receipt

    rows, _states = checkpoint_states(root, bundle)
    chains = validate_historical_proof_chains(
        root,
        [
            (
                proofs[action]["reservation"],
                proofs[action]["pre_commit_verification"],
                proofs[action]["expected_version"],
            )
            for action in ACTIONS
        ],
        skills_root=skills_root,
    )
    consumed: list[datetime] = []
    bindings: list[dict[str, str]] = []
    issued = _time(lease["issued_at"])
    expiry = _time(lease["expires_at"]) if lease["expires_at"] else None
    for row, chain in zip(rows, chains):
        action = row["action"]
        proof = proofs[action]
        decision = chain["decision"]
        request = decision["request"]
        context = decision["evaluation_context"]
        envelope = context.get("goal_autonomy_envelope", {})
        selected = decision["selected_grants"]
        if (
            chain["reservation_binding"] != proof["reservation"]
            or chain["verification_binding"] != proof["pre_commit_verification"]
            or chain["current_state"].get("status") != "consumed"
            or chain["current_state"].get("version")
            != proof["expected_version"] + 1
            or request.get("task_id") != bundle["selected_task_id"]
            or request.get("subject") != row["subject"]
            or request.get("idempotency_key") != row["idempotency_key"]
            or context.get("session_ceiling", {}).get("evidence_id") != session_id
            or envelope.get("source_binding", {}).get("sha256")
            != lease["goal_digest"]
            or request.get("risk_tier") not in _RISK
            or _RISK[request["risk_tier"]] > _RISK[lease["risk_ceiling"]]
            or not _operation_is_allowed(lease, row["operation"])
            or not isinstance(selected, list)
            or len(selected) != 1
        ):
            raise ValueError("selected-successor authority is outside the session")
        grant, grant_sha = load_grant_artifact(root, selected[0]["grant_id"])
        if (
            selected[0].get("grant_sha256") != grant_sha
            or grant.get("session_id") != session_id
            or grant.get("task_id") != bundle["selected_task_id"]
            or grant.get("policy_snapshot", {}).get("sha256")
            != lease["policy_digest"]
        ):
            raise ValueError("selected-successor grant is not session-bound")
        identity = object_sha256(
            {
                "reservation": proof["reservation"]["sha256"],
                "key": row["idempotency_key"],
            }
        )[:24]
        path = (
            root
            / ".task"
            / "authorization"
            / "use_receipts"
            / f"authu-{identity}.json"
        )
        receipt = read_object(path, "selected-successor use receipt")
        validate_use_receipt(root, receipt, path, skills_root=skills_root)
        expected_owner = (
            rows[2]["expected_result"]
            if action != ACTIONS[1]
            else rows[1]["expected_result"]
        )
        if (
            receipt.get("reservation") != proof["reservation"]
            or receipt.get("pre_commit_verification")
            != proof["pre_commit_verification"]
            or receipt.get("owner_execution_result") != expected_owner
            or receipt.get("idempotency_key") != row["idempotency_key"]
        ):
            raise ValueError("selected-successor settlement is cross-bound")
        moment = _time(receipt["consumed_at"])
        evaluated = _time(decision["evaluated_at"])
        if min(evaluated, moment) < issued or (
            expiry is not None and max(evaluated, moment) >= expiry
        ):
            raise ValueError("selected-successor authority is outside session time")
        consumed.append(moment)
        bindings.append(
            {
                "ref": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return max(consumed), tuple(bindings)


def _session_unchanged(root: Path, session_id: str, expected_sha256: str) -> bool:
    from manage_agent_authority.session_binding import session_ref
    from manage_agent_authority.stable_store import read_regular

    raw = read_regular(
        root / session_ref(session_id), label="successor session lease replay"
    )
    return raw is not None and hashlib.sha256(raw).hexdigest() == expected_sha256


__all__ = (
    "_default_skills_root",
    "_session_envelope",
    "_session_unchanged",
    "_settlements",
    "_time",
)
