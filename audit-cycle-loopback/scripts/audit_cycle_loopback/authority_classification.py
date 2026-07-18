from __future__ import annotations

from typing import Any


AUTHORITY_STATUSES = {"already_granted", "new_authority_required", "unverified"}
LOCAL_STATUSES = {"available", "unavailable", "unverified"}
EXTERNAL_DEPENDENCIES = {
    "none",
    "waiting_state",
    "missing_external_input",
    "unverified",
}
RISK_STATUSES = {"required", "not_required", "unverified"}


def _opaque(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if (
        not text
        or len(text) > 255
        or any(ord(char) < 33 or char in "/\\" for char in text)
    ):
        return None
    return text


def _ids(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items = [_opaque(item) for item in value]
    if any(item is None for item in items) or len(items) != len(set(items)):
        return None
    return [item for item in items if item is not None]


def _raw_rows(values: tuple[Any, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        raw = value.get("authority_classification")
        candidates = (
            raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
        )
        if "authority_status" in value:
            candidates.append(value)
        rows.extend(
            candidate for candidate in candidates if isinstance(candidate, dict)
        )
    return rows


def classify_authority_axes(
    values: tuple[Any, ...], terminal_requested: bool
) -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    invalid_count = 0
    for row in _raw_rows(values):
        item_id = _opaque(row.get("item_id"))
        resolution_kind_id = _opaque(row.get("resolution_kind_id"))
        authority_status = str(row.get("authority_status") or "").strip().lower()
        local_status = str(row.get("local_resolution_status") or "").strip().lower()
        external = str(row.get("external_dependency") or "").strip().lower()
        risk = str(row.get("risk_or_cost_confirmation") or "").strip().lower()
        authority_evidence = _ids(row.get("authority_evidence_ids"))
        local_evidence = _ids(row.get("local_capability_evidence_ids"))
        valid = bool(
            item_id
            and resolution_kind_id
            and authority_status in AUTHORITY_STATUSES
            and local_status in LOCAL_STATUSES
            and external in EXTERNAL_DEPENDENCIES
            and risk in RISK_STATUSES
            and authority_evidence is not None
            and local_evidence is not None
            and (
                {
                    authority_status,
                    external,
                    risk,
                }
                == {"unverified"}
                or authority_evidence
            )
            and (local_status == "unverified" or local_evidence)
        )
        if not valid:
            invalid_count += 1
        normalized.append(
            {
                "item_id": item_id,
                "authority_status": authority_status
                if authority_status in AUTHORITY_STATUSES
                else "unverified",
                "local_resolution_status": local_status
                if local_status in LOCAL_STATUSES
                else "unverified",
                "external_dependency": external
                if external in EXTERNAL_DEPENDENCIES
                else "unverified",
                "risk_or_cost_confirmation": risk
                if risk in RISK_STATUSES
                else "unverified",
                "resolution_kind_id": resolution_kind_id,
                "authority_evidence_ids": authority_evidence or [],
                "local_capability_evidence_ids": local_evidence or [],
                "classification_valid": valid,
            }
        )
    required_missing = terminal_requested and not normalized
    unverified = [
        row
        for row in normalized
        if not row["classification_valid"]
        or "unverified"
        in {
            row["authority_status"],
            row["local_resolution_status"],
            row["external_dependency"],
            row["risk_or_cost_confirmation"],
        }
    ]
    waiting = [
        row for row in normalized if row["external_dependency"] == "waiting_state"
    ]
    local = [row for row in normalized if row["local_resolution_status"] == "available"]
    authority = [
        row for row in normalized if row["authority_status"] == "new_authority_required"
    ]
    risk = [row for row in normalized if row["risk_or_cost_confirmation"] == "required"]
    external = [
        row
        for row in normalized
        if row["external_dependency"] == "missing_external_input"
    ]
    terminal_prohibited = bool(
        required_missing or unverified or waiting or local or authority or risk
    )
    if required_missing or unverified:
        route = "classification_repair"
    elif waiting:
        route = "monitor_or_harvest"
    elif local:
        route = "local_resolution"
    elif authority or risk:
        route = "user_confirmation"
    elif external:
        route = "external_input"
    else:
        route = "terminal_eligible"
    return {
        "authority_classification": normalized,
        "authority_axis_status": "not_evaluated"
        if required_missing or unverified
        else "pass",
        "authority_axis_unverified": bool(required_missing or unverified),
        "invalid_authority_classification_count": invalid_count,
        "waiting_state_count": len(waiting),
        "local_resolution_available_count": len(local),
        "new_authority_required_count": len(authority),
        "risk_or_cost_confirmation_required_count": len(risk),
        "missing_external_input_count": len(external),
        "authority_goal_terminal_prohibited": terminal_prohibited,
        "recommended_resolution_route": route,
    }
