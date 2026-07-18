"""Grant, approval, reservation, and axis-relation authority validation."""

from __future__ import annotations

from typing import Any

from ._authority_boundary_schema import (
    APPROVAL_KEYS,
    GRANT_KEYS,
    GRANT_USE_KEYS,
    RESERVATION_KEYS,
)
from ._authority_boundary_validation import (
    binding,
    canonical_digest,
    closed,
    finding,
    identifier,
    nonnegative_int,
    sha,
)


def _validate_grant_rows(
    packet: dict[str, Any],
    field: str,
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = packet.get(field)
    if not isinstance(rows, list):
        findings.append(
            finding("authority_grant_bindings_invalid", f"{field} must be a list.")
        )
        return []
    for index, value in enumerate(rows):
        row = closed(value, GRANT_KEYS, f"{field}[{index}]", findings)
        if (
            not identifier(row.get("grant_id"))
            or sha(row.get("grant_sha256")) is None
            or not nonnegative_int(row.get("state_version"))
        ):
            findings.append(
                finding(
                    "authority_grant_binding_invalid",
                    f"{field}[{index}] is invalid.",
                )
            )
        binding(
            row.get("policy_snapshot"), f"{field}[{index}].policy_snapshot", findings
        )
    grant_ids = [
        str(row.get("grant_id"))
        for row in rows
        if isinstance(row, dict) and row.get("grant_id")
    ]
    if len(grant_ids) != len(set(grant_ids)):
        findings.append(
            finding(
                "authority_duplicate_grant_binding",
                f"{field} cannot contain duplicate grant IDs.",
            )
        )
    return [row for row in rows if isinstance(row, dict)]


def validate_grants(
    packet: dict[str, Any],
    findings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected = _validate_grant_rows(packet, "selected_grants", findings)
    lineage = _validate_grant_rows(packet, "lineage_grants", findings)
    selected_ids = {str(row.get("grant_id")) for row in selected}
    lineage_ids = {str(row.get("grant_id")) for row in lineage}
    if selected_ids & lineage_ids:
        findings.append(
            finding(
                "authority_grant_lineage_overlap",
                "Selected and lineage grant IDs must be disjoint.",
            )
        )
    if lineage and not selected:
        findings.append(
            finding(
                "authority_orphan_lineage_grant",
                "Lineage grants require at least one selected covering grant.",
            )
        )
    if len(selected) > 1 and packet.get("composition_receipt") is None:
        findings.append(
            finding(
                "authority_implicit_grant_union",
                "Multiple grants require an explicit composition receipt.",
            )
        )
    if packet.get("composition_receipt") is not None:
        binding(packet.get("composition_receipt"), "composition_receipt", findings)
    return selected, lineage


def validate_approval(
    packet: dict[str, Any],
    decision: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    projection = packet.get("approval_projection")
    if decision.get("decision") != "approval_required":
        if projection is not None:
            findings.append(
                finding(
                    "authority_unexpected_approval_projection",
                    "Only approval_required may carry an approval projection.",
                )
            )
        return
    row = closed(projection, APPROVAL_KEYS, "approval_projection", findings)
    core = {key: value for key, value in row.items() if key != "projection_id"}
    if (
        row.get("schema_version") != 2
        or row.get("artifact_kind") != "authority_approval_projection"
        or row.get("request_id") != decision.get("request_id")
        or row.get("projection_id") != "authp-" + canonical_digest(core)[:24]
    ):
        findings.append(
            finding(
                "authority_approval_projection_invalid",
                "Approval projection must be a deterministic exact owner projection.",
            )
        )


def validate_reservation(
    packet: dict[str, Any],
    findings: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reservation = closed(
        packet.get("reservation_binding"),
        RESERVATION_KEYS,
        "reservation_binding",
        findings,
    )
    applicability = reservation.get("applicability")
    if applicability not in {"required", "not_applicable"}:
        findings.append(
            finding(
                "authority_reservation_applicability_invalid",
                "Reservation applicability is invalid.",
            )
        )
    uses = reservation.get("grant_uses")
    if not isinstance(uses, list):
        findings.append(
            finding(
                "authority_grant_uses_invalid",
                "reservation_binding.grant_uses must be a list.",
            )
        )
        uses = []
    for index, value in enumerate(uses):
        row = closed(
            value,
            GRANT_USE_KEYS,
            f"reservation_binding.grant_uses[{index}]",
            findings,
        )
        integers = (
            row.get("units"),
            row.get("state_version_before"),
            row.get("state_version_after"),
        )
        if (
            not identifier(row.get("grant_id"))
            or sha(row.get("grant_sha256")) is None
            or not all(nonnegative_int(item) for item in integers)
        ):
            findings.append(
                finding(
                    "authority_grant_use_invalid",
                    f"reservation grant use {index} is invalid.",
                )
            )
        elif (
            row["units"] < 1
            or row["state_version_after"] != row["state_version_before"] + 1
        ):
            findings.append(
                finding(
                    "authority_grant_use_transition_invalid",
                    f"reservation grant use {index} has an invalid unit/version transition.",
                )
            )
    use_ids = [
        str(row.get("grant_id"))
        for row in uses
        if isinstance(row, dict) and row.get("grant_id")
    ]
    if len(use_ids) != len(set(use_ids)):
        findings.append(
            finding(
                "authority_duplicate_grant_use",
                "Reservation grant uses cannot contain duplicate grant IDs.",
            )
        )
    if applicability == "required":
        required = (
            "reservation_id",
            "artifact_ref",
            "artifact_sha256",
            "state_ref",
            "state_sha256",
            "state_version",
            "status",
            "effective_authority_fingerprint",
        )
        if (
            any(reservation.get(field) in (None, "") for field in required)
            or reservation.get("status") != "reserved"
        ):
            findings.append(
                finding(
                    "authority_reservation_binding_invalid",
                    "Required reservation must bind an immutable artifact and reserved CAS state.",
                )
            )
        if (
            not identifier(reservation.get("reservation_id"))
            or not nonnegative_int(reservation.get("state_version"))
            or any(
                sha(reservation.get(field)) is None
                for field in (
                    "artifact_sha256",
                    "state_sha256",
                    "effective_authority_fingerprint",
                )
            )
        ):
            findings.append(
                finding(
                    "authority_reservation_binding_invalid",
                    "Required reservation IDs, digests, and CAS version must be exact.",
                )
            )
    elif any(
        reservation.get(field) not in (None, "", [])
        for field in set(RESERVATION_KEYS) - {"applicability", "grant_uses"}
    ):
        findings.append(
            finding(
                "authority_reservation_not_applicable_populated",
                "A not-applicable reservation cannot carry state.",
            )
        )
    return reservation, [row for row in uses if isinstance(row, dict)]


def validate_relations(
    packet: dict[str, Any],
    statuses: dict[str, str],
    grants: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    decision = (packet.get("decision_binding") or {}).get("decision")
    authority = statuses.get("authority")
    local = statuses.get("local_resolution")
    external = statuses.get("external_input")
    risk = statuses.get("risk_cost")
    goal = statuses.get("goal_truth")
    expected: set[str] = set()
    if authority == "denied":
        expected.add("denied")
    if authority == "approval_required" or risk == "confirmation_required":
        expected.add("approval_required")
    if external in {"waiting_state", "missing_supplyable", "missing_unsupplyable"}:
        expected.add("waiting_external_input")
    if local == "unavailable" and external in {
        "not_required",
        "available",
        "unavailable",
    }:
        expected.add("capability_unavailable")
    if goal == "blocked":
        expected.add("blocked_by_goal_truth")
    if "unverified" in statuses.values():
        expected.add("classification_repair")
    allowed_axes = (
        authority in {"granted", "not_applicable"}
        and local in {"available", "not_applicable"}
        and external in {"not_required", "available", "not_applicable"}
        and risk in {"not_required", "accepted", "not_applicable"}
        and goal in {"aligned", "not_applicable"}
    )
    if decision == "allowed" and not allowed_axes:
        findings.append(
            finding(
                "authority_allowed_axes_conflict",
                "allowed conflicts with an unresolved authority, risk, goal, or external axis.",
            )
        )
    terminal_decisions = {
        "approval_required",
        "denied",
        "waiting_external_input",
        "capability_unavailable",
        "blocked_by_goal_truth",
    }
    if decision in terminal_decisions and decision not in expected:
        findings.append(
            finding(
                "authority_decision_axis_mismatch",
                "Decision is unsupported by independent axes.",
                {"decision": decision, "supported": sorted(expected)},
            )
        )
    if local == "available" and decision == "capability_unavailable":
        findings.append(
            finding(
                "authority_self_resolvable_escalated",
                "Verified local resolution cannot be escalated as capability or external-input debt.",
            )
        )
    if (
        decision == "approval_required"
        and authority == "granted"
        and risk != "confirmation_required"
    ):
        findings.append(
            finding(
                "authority_permission_inferred_from_other_axis",
                "Approval cannot be inferred from external, local, or goal state.",
            )
        )
    if authority == "granted" and not grants:
        findings.append(
            finding(
                "authority_covering_grant_missing",
                "A granted axis requires exact selected grant bindings.",
            )
        )
    if authority != "granted" and grants:
        findings.append(
            finding(
                "authority_unselected_grant_binding",
                "Only a granted authority axis may carry selected covering grants.",
            )
        )


__all__ = (
    "validate_approval",
    "validate_grants",
    "validate_relations",
    "validate_reservation",
)
