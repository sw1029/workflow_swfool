"""Validate current and historical authority settlement receipts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

from .common import (
    WorkflowError,
    read_json,
    require,
    workspace_file,
    workspace_regular_file,
)


SKILLS_ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_SCRIPTS = SKILLS_ROOT / "manage-agent-authority" / "scripts"
if str(AUTHORITY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTHORITY_SCRIPTS))

from manage_agent_authority.projection_io import (  # noqa: E402
    validate_reservation_state,
)
from manage_agent_authority.projection_receipts import (  # noqa: E402
    validate_release_receipt,
    validate_use_receipt,
)
from manage_agent_authority.projection_reconciliation import (  # noqa: E402
    validate_reconciliation_evidence,
    validate_reconciliation_receipt,
)
from manage_agent_authority.projection_reservations import (  # noqa: E402
    load_bound_reservation,
)


T = TypeVar("T")


def _call(code: str, label: str, action: Callable[[], T]) -> T:
    try:
        return action()
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        message = str(error) or error.__class__.__name__
        raise WorkflowError(code, f"{label} is invalid: {message}") from error


def _binding(value: Any, label: str) -> dict[str, str]:
    require(isinstance(value, dict) and set(value) == {"ref", "sha256"},
            "authority_settlement_mismatch",
            f"{label} must be an exact file binding")
    return {"ref": str(value["ref"]), "sha256": str(value["sha256"])}


def _reservation_id(root: Path, binding: dict[str, str]) -> str:
    reservation, _, _ = _call(
        "invalid_authority_settlement", "settlement reservation",
        lambda: load_bound_reservation(root, binding, "settlement reservation"),
    )
    return reservation["reservation_id"]


def _current_state(
    root: Path, reservation: dict[str, str], status: str,
    receipt: dict[str, Any],
) -> None:
    reservation_id = _reservation_id(root, reservation)
    state_ref = (
        ".task/authorization/state/reservations/"
        f"{reservation_id}.json"
    )
    path = workspace_regular_file(
        root, state_ref, "settled_reservation_state"
    )
    state = _call(
        "invalid_authority_settlement", "settled reservation state",
        lambda: validate_reservation_state(
            read_json(path, "invalid_authority_settlement"),
            reservation_id,
            "settled reservation state",
        ),
    )
    require(
        state["status"] == status
        and state["last_event_id"] == receipt["receipt_id"],
        "stale_authority_settlement",
        "authority receipt is not the current reservation settlement",
    )
    changes = receipt.get("state_changes")
    require(isinstance(changes, list), "invalid_authority_settlement",
            "authority receipt lacks exact state changes")
    matches = [
        row for row in changes
        if isinstance(row, dict) and row.get("ref") == state_ref
    ]
    require(len(matches) == 1 and matches[0].get("after") == state,
            "stale_authority_settlement",
            "current reservation state differs from receipt after-state")


def _registered_owner(
    root: Path, evidence: dict[str, str],
) -> dict[str, str] | None:
    path = workspace_file(
        root, evidence["ref"], evidence["sha256"],
        "authority owner validation",
    )
    body = read_json(path, "invalid_authority_settlement")
    if body.get("artifact_kind") != "owner_validation_receipt":
        return None
    require(
        body.get("outcome") == "confirmed_no_effect",
        "authority_settlement_mismatch",
        "registered release does not prove confirmed no-effect",
    )
    return _binding(body.get("owner_result"), "owner validation owner_result")


def validate_settlement_artifact(
    root: Path,
    receipt_binding: dict[str, str],
    reservation: dict[str, str],
    effect_status: str,
) -> dict[str, str]:
    """Validate one producer receipt and return its direct owner artifact."""

    path = workspace_file(
        root, receipt_binding["ref"], receipt_binding["sha256"],
        "authority settlement receipt",
    )
    receipt = read_json(path, "invalid_authority_settlement")
    kind = receipt.get("artifact_kind")
    if kind == "authority_use_receipt":
        _call("invalid_authority_settlement", "authority use receipt",
              lambda: validate_use_receipt(root, receipt, path))
        require(effect_status == "confirmed_effect",
                "authority_settlement_mismatch",
                "use receipt cannot prove a no-effect result")
        owner = _binding(
            receipt.get("owner_execution_result"),
            "use receipt owner_execution_result",
        )
        expected_state = "consumed"
    elif kind == "authority_release_receipt":
        _call("invalid_authority_settlement", "authority release receipt",
              lambda: validate_release_receipt(root, receipt, path))
        require(
            effect_status == "confirmed_no_effect"
            and receipt.get("effect_status") == "verified_no_effect"
            and receipt.get("release_applied") is True,
            "authority_settlement_mismatch",
            "release receipt does not prove confirmed no-effect",
        )
        evidence = _binding(
            receipt.get("no_effect_evidence"),
            "release receipt no_effect_evidence",
        )
        owner = _registered_owner(root, evidence) or evidence
        expected_state = "released"
    elif kind == "authority_reconciliation_receipt":
        _call(
            "invalid_authority_settlement",
            "authority reconciliation receipt",
            lambda: validate_reconciliation_receipt(root, receipt, path),
        )
        require(receipt.get("outcome") == effect_status,
                "authority_settlement_mismatch",
                "reconciliation outcome mismatch")
        bound, _, normalized = _call(
            "invalid_authority_settlement", "reconciliation reservation",
            lambda: load_bound_reservation(
                root, receipt["reservation"], "reconciliation reservation"
            ),
        )
        evidence = _call(
            "invalid_authority_settlement", "reconciliation evidence",
            lambda: validate_reconciliation_evidence(
                root, receipt["effect_evidence"], bound, normalized,
                receipt["outcome"], require_current_subject=False,
            ),
        )
        owner = _binding(
            evidence.get("owner_result"),
            "reconciliation owner_result",
        )
        expected_state = (
            "consumed" if effect_status == "confirmed_effect" else "released"
        )
    else:
        raise WorkflowError(
            "invalid_authority_settlement",
            "authority settlement must be a use, release, or reconciliation receipt",
        )
    require(receipt.get("reservation") == reservation,
            "authority_settlement_mismatch",
            "settlement binds a different reservation")
    _current_state(root, reservation, expected_state, receipt)
    return owner


def validate_not_started_receipt(
    root: Path,
    receipt_binding: dict[str, str],
    reservation: dict[str, str],
) -> None:
    path = workspace_file(
        root, receipt_binding["ref"], receipt_binding["sha256"],
        "authority not-started release receipt",
    )
    receipt = read_json(path, "invalid_authority_settlement")
    _call("invalid_authority_settlement", "authority release receipt",
          lambda: validate_release_receipt(root, receipt, path))
    require(
        receipt.get("effect_status") == "not_started"
        and receipt.get("release_applied") is True
        and receipt.get("reservation") == reservation,
        "authority_settlement_mismatch",
        "release receipt does not prove an exact not-started result",
    )
    _current_state(root, reservation, "released", receipt)


def validate_terminal_state(
    root: Path,
    reservation: dict[str, str],
    status: str,
    receipt: dict[str, Any],
) -> None:
    _current_state(root, reservation, status, receipt)


def validate_settlement_receipt(
    root: Path,
    receipt_binding: dict[str, str],
    reservation: dict[str, str],
    owner_effect: dict[str, str],
    owner_artifact: dict[str, str],
    effect_status: str,
) -> str:
    observed = validate_settlement_artifact(
        root, receipt_binding, reservation, effect_status
    )
    require(
        observed == owner_effect or observed == owner_artifact,
        "authority_settlement_mismatch",
        "settlement does not bind the exact task-doctor owner result",
    )
    return effect_status


__all__ = [
    "validate_not_started_receipt",
    "validate_settlement_artifact",
    "validate_settlement_receipt",
    "validate_terminal_state",
]
