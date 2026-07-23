"""Current and historical authority checks for selected-successor execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selected_successor_execution_support import ACTIONS


def authority_preflight(
    root: Path,
    rows: list[dict[str, Any]],
    proofs: dict[str, dict[str, Any]],
    *,
    require_current: bool,
    owner_results: tuple[dict[str, str], ...] | None = None,
    settled_at: str | None = None,
    skills_root: Path | None = None,
) -> list[dict[str, Any]]:
    from manage_agent_authority.execution_results import (
        validate_pre_commit_verification,
    )
    from manage_agent_authority.historical_proof_chain import (
        validate_historical_proof_chains,
    )

    checked: list[dict[str, Any]] = []
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
    for row, chain in zip(rows, chains):
        action = row["action"]
        proof = proofs[action]
        reservation_binding = proof["reservation"]
        reservation = chain["reservation"]
        state = chain["current_state"]
        if chain["reservation_binding"] != reservation_binding:
            raise ValueError(f"Selected-successor {action} reservation path differs")
        decision = chain["decision"]
        request = decision.get("request")
        operation = row.get("operation")
        if not isinstance(request, dict) or not isinstance(operation, dict):
            raise ValueError(f"Selected-successor {action} authority request is invalid")
        expected_operation = {
            key: operation.get(key)
            for key in (
                "skill_id",
                "skill_version",
                "operation_id",
                "operation_version",
            )
        }
        if (
            any(request.get(key) != value for key, value in expected_operation.items())
            or request.get("subject") != row.get("subject")
            or request.get("idempotency_key") != row.get("idempotency_key")
            or reservation.get("idempotency_key") != row.get("idempotency_key")
        ):
            raise ValueError(
                f"Selected-successor {action} reservation authorizes another operation"
            )
        expected_version = proof["expected_version"]
        replayed = False
        if require_current:
            if state.get("status") != "reserved" or state.get("version") != expected_version:
                raise ValueError(
                    f"Selected-successor {action} reservation is not current before effect"
                )
        elif state.get("status") == "reserved" and state.get("version") == expected_version:
            pass
        elif (
            state.get("status") == "consumed"
            and state.get("version") == expected_version + 1
        ):
            if owner_results is None or settled_at is None:
                raise ValueError("Consumed authority replay inputs are missing")
            from manage_agent_authority.settlement import settle_owner_result

            replay = settle_owner_result(
                root,
                reservation_binding["ref"],
                reservation_binding["sha256"],
                owner_results[len(checked)],
                proof["pre_commit_verification"],
                settled_at=settled_at,
                expected_version=expected_version,
                idempotency_key=row["idempotency_key"],
                skills_root=skills_root,
            )
            if (
                replay.get("status") != "consumed"
                or replay.get("outcome") != "confirmed_effect"
            ):
                raise ValueError(
                    f"Selected-successor {action} consumed replay is invalid"
                )
            replayed = True
        else:
            raise ValueError(
                f"Selected-successor {action} reservation is not replayable"
            )
        if chain["verification_binding"] != proof["pre_commit_verification"]:
            raise ValueError(
                f"Selected-successor {action} pre-commit verification path differs"
            )
        if state.get("status") == "reserved":
            validate_pre_commit_verification(
                root,
                reservation,
                reservation_binding,
                proof["pre_commit_verification"],
                expected_version=expected_version,
                require_current_state=True,
            )
        checked.append(
            {
                "action": action,
                "reservation": reservation_binding,
                "pre_commit_verification": proof["pre_commit_verification"],
                "expected_version": expected_version,
                "state_status": state.get("status"),
                "exact_v3_settlement_replayed": replayed,
            }
        )
    return checked


__all__ = ("authority_preflight",)
