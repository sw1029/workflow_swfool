"""Read-only live authority projection for task-doctor workflow UX."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .authority import validate_reservation_binding
from .authority_settlement_projection import validate_settlement_projection
from .authority_grant import verify_materialized_grant
from .common import WorkflowError, now, require
from .journal import dependencies_complete


SKILLS_ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_SCRIPTS = SKILLS_ROOT / "manage-agent-authority" / "scripts"
if str(AUTHORITY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTHORITY_SCRIPTS))

from manage_agent_authority.workflow_status import resolve_operation  # noqa: E402
from manage_agent_authority.projection_io import load_grant_artifact  # noqa: E402


def _source_binding_matches(item: dict[str, Any], result: dict[str, Any]) -> None:
    source = result.get("workflow_basis", {}).get("source_approval")
    require(isinstance(source, dict), "invalid_authority_overlay",
            "live source-authority progression lacks a verified source approval")
    spec = item["authority"]["materialization"]["grant_spec"]
    candidates = {
        *source.get("materializable_grant_ids", []),
        *source.get("usable_grant_ids", []),
    }
    require(spec["grant_id"] in candidates
            and spec["lineage_id"] in source.get("lineage_ids", []),
            "invalid_authority_overlay",
            "live source approval does not bind the planned grant and lineage")


def _decision_binding_matches(
    root: Path, item: dict[str, Any], result: dict[str, Any],
) -> None:
    decision = result.get("workflow_basis", {}).get("decision")
    require(isinstance(decision, dict), "invalid_authority_overlay",
            "live allowed progression lacks an exact decision")
    grant_id = item["authority"]["materialization"]["grant_spec"]["grant_id"]
    selected = decision.get("selected_grants", [])
    require(isinstance(selected, list)
            and grant_id in {entry.get("grant_id") for entry in selected
                             if isinstance(entry, dict)},
            "invalid_authority_overlay",
            "live allowed decision does not select the planned exact grant")
    try:
        grant, _binding = load_grant_artifact(root, grant_id)
    except (SystemExit, KeyError, TypeError, ValueError) as error:
        raise WorkflowError(
            "invalid_authority_overlay", "selected live grant is invalid"
        ) from error
    verify_materialized_grant(grant, item["authority"])


def _reservation_binding_matches(
    root: Path, item: dict[str, Any], result: dict[str, Any], *, phase: str,
) -> None:
    reservation = result.get("workflow_basis", {}).get("reservation")
    require(isinstance(reservation, dict), "invalid_authority_overlay",
            "live reservation progression lacks an exact reservation binding")
    observed = validate_reservation_binding(
        root, item, {"ref": reservation.get("ref", ""),
                     "sha256": reservation.get("sha256", "")}, phase=phase,
    )
    require(observed["request_sha256"] == item["authority"]["request_sha256"],
            "invalid_authority_overlay",
            "live reservation binds a different authority request")


def _validate_overlay(
    root: Path, item: dict[str, Any], result: dict[str, Any],
) -> None:
    require(result.get("status") == "resolved", "invalid_authority_overlay",
            "public authority resolver returned an invalid result")
    expected_request = item["authority"]["request_sha256"]
    basis = result.get("workflow_basis")
    require(isinstance(basis, dict)
            and basis.get("request_sha256") == expected_request,
            "invalid_authority_overlay",
            "live authority projection binds a different exact request")
    resolution = result.get("resolution")
    if resolution == "source_approval_ready_for_grant":
        _source_binding_matches(item, result)
    elif resolution == "ready_to_reserve":
        _decision_binding_matches(root, item, result)
    elif resolution in {"ready_to_resume", "reserved_authority_recovery"}:
        _reservation_binding_matches(root, item, result, phase="structural")
    elif resolution in {"already_consumed", "already_released", "recover_settlement",
                        "effect_reconciliation"}:
        _reservation_binding_matches(root, item, result, phase="structural")


def _settlement_projection(
    root: Path, journal: dict[str, Any], item: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    recovery_approval_wait = (
        result.get("resolution") == "needs_user_approval"
        and result.get("next_action", {}).get("code")
        == "approve_exact_recovery_projection"
    )
    if result.get("resolution") == "source_authority_exhausted" or (
        recovery_approval_wait
    ):
        return {
            **result, "resolution": "plan_changed",
            "workflow_state": "replanning_required", "should_prompt": False,
            "user_action": None,
            "next_action": {"actor": "system", "code": "prepare_new_plan"},
        }
    if result.get("resolution") in {"already_consumed", "already_released"}:
        basis = result.get("workflow_basis", {})
        reservation = basis.get("reservation")
        receipt = basis.get("settlement_receipt")
        require(isinstance(reservation, dict) and isinstance(receipt, dict),
                "invalid_authority_overlay",
                "terminal live authority state lacks exact settlement bindings")
        effect_status = validate_settlement_projection(
            root, journal, item,
            {key: reservation.get(key) for key in ("ref", "sha256")},
            {key: receipt.get(key) for key in ("ref", "sha256")},
        )
        if effect_status == "not_started":
            return {
                **result, "resolution": "plan_changed",
                "workflow_state": "replanning_required", "should_prompt": False,
                "user_action": None,
                "next_action": {
                    "actor": "system", "code": "prepare_new_plan"
                },
            }
        return {
            **result, "resolution": "recover_settlement",
            "workflow_state": "recover_settlement", "should_prompt": False,
            "user_action": None,
            "next_action": {"actor": "system", "code": "recover_owner_completion"},
        }
    if result.get("resolution") != "idle":
        return result
    request_sha = item["authority"]["request_sha256"]
    released = [
        row for row in result.get("existing_reservations", [])
        if row.get("reservation", {}).get("request_sha256") == request_sha
        and row.get("state", {}).get("status") == "released"
    ]
    if not released:
        return result
    receipt = released[0].get("settlement_receipt")
    require(isinstance(receipt, dict), "invalid_authority_overlay",
            "released authority state lacks its exact settlement receipt")
    basis = {
        "kind": "released", "request_sha256": request_sha,
        "reservation": released[0]["reservation"],
        "reservation_state": released[0]["state_binding"],
        "decision": None, "source_approval": None,
        "settlement_receipt": receipt, "blocker_codes": [],
    }
    return _settlement_projection(
        root, journal, item, {**result, "resolution": "already_released",
                             "workflow_basis": basis}
    )


def live_authority_overlay(
    root: Path, journal: dict[str, Any], *, evaluated_at: str | None = None,
    owner_lifecycle: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve authority only for dependency-ready, publicly ready owner rows."""

    resolved: dict[str, dict[str, Any]] = {}
    current_time = evaluated_at or now()
    owner_lifecycle = owner_lifecycle or {}
    for item in journal["plan"]["operations"]:
        state = journal["operation_state"][item["operation_id"]]
        semantic_review_pending = state["resolution"] == "needs_user_approval"
        if (item["authority"]["applicability"] != "required"
                or state["status"] != "pending"
                or (
                    not semantic_review_pending
                    and (
                        not dependencies_complete(journal, item)
                        or owner_lifecycle.get(item["operation_id"], {}).get("status")
                        != "ready"
                    )
                )):
            continue
        try:
            result = resolve_operation(
                root, item["authority"]["request"],
                item["authority"]["materialization"]["evaluation_context"],
                evaluated_at=current_time, skills_root=SKILLS_ROOT,
            )
        except (SystemExit, KeyError, TypeError, ValueError) as error:
            message = str(error) or error.__class__.__name__
            raise WorkflowError(
                "invalid_authority_overlay",
                f"public live authority resolution failed: {message}",
            ) from error
        result = _settlement_projection(root, journal, item, result)
        _validate_overlay(root, item, result)
        if (journal["plan"]["execution_mode"] == "execute_with_declared_authorization"
                and result["should_prompt"]):
            result = {
                **result, "resolution": "source_authority_defect",
                "workflow_state": "source_authority_defect", "should_prompt": False,
                "user_action": None,
                "next_action": {
                    "actor": "system", "code": "repair_declared_authority"
                },
            }
        resolved[item["operation_id"]] = result
    return resolved


__all__ = ["live_authority_overlay"]
