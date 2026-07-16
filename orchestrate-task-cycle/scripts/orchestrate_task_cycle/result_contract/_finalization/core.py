from __future__ import annotations

import hashlib
import json
from typing import Any

from ..common import boolish, first_present


VERDICT_AXES = (
    "task_acceptance_verdict",
    "artifact_truth_verdict",
    "artifact_semantic_verdict",
    "pack_transition_verdict",
    "historical_index_verdict",
    "goal_readiness_verdict",
)
RECEIPT_KIND = "cycle_finalization_receipt"
SNAPSHOT_KIND = "cycle_finalization_snapshot"
CANDIDATE_KIND = "cycle_final_candidate"
SHA256_FIELDS = (
    "finalization_token",
    "snapshot_sha256",
    "final_candidate_digest",
    "validation_axes_digest",
    "authoritative_projection_digest",
    "receipt_hash",
)


def canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def projection_conclusions(projection: dict[str, Any]) -> tuple[str, str]:
    """Project typed axes without collapsing task acceptance into goal progress."""

    def status(axis: str) -> str:
        value = projection.get(axis)
        return (
            str(value.get("status") or value.get("verdict") or "").strip().lower()
            if isinstance(value, dict)
            else ""
        )

    acceptance = status("task_acceptance_verdict")
    validation = {
        "pass": "passed",
        "fail": "failed",
        "partial": "partial",
        "blocked": "blocked",
        "conflicted": "blocked",
        "not_evaluated": "not_run",
        "not_applicable": "not_applicable",
    }.get(acceptance, "not_run")
    semantic = status("artifact_semantic_verdict")
    goal = status("goal_readiness_verdict")
    all_statuses = {status(axis) for axis in VERDICT_AXES}
    if "conflicted" in all_statuses:
        progress = "blocked"
    elif semantic == "pass" and goal == "pass":
        progress = "advanced"
    elif "blocked" in {semantic, goal}:
        progress = "blocked"
    elif "not_evaluated" in {semantic, goal} or not semantic or not goal:
        progress = "not_run"
    else:
        progress = "no_progress"
    return validation, progress


def full_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def opaque_id(value: Any, *, max_length: int = 256) -> bool:
    return bool(
        isinstance(value, str)
        and 0 < len(value.strip()) <= max_length
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def finalization_receipt_aliases(result: dict[str, Any]) -> list[dict[str, Any]]:
    aliases: list[dict[str, Any]] = []
    declared_paths = (
        ("finalization_receipt",),
        ("validation_finalization_receipt",),
        ("finalization", "receipt"),
        ("result", "finalization_receipt"),
    )
    for path in declared_paths:
        current: Any = result
        declared = True
        for part in path:
            if not isinstance(current, dict) or part not in current:
                declared = False
                break
            current = current[part]
        if declared:
            if current is None:
                continue
            aliases.append(
                current
                if isinstance(current, dict)
                else {"malformed_receipt_value": True}
            )
    compatibility = result.get("receipt")
    if isinstance(compatibility, dict) and compatibility.get("kind") == RECEIPT_KIND:
        aliases.append(compatibility)
    return aliases


def conflicting_finalization_receipt_aliases(result: dict[str, Any]) -> bool:
    aliases = finalization_receipt_aliases(result)
    return len({canonical_digest(value) for value in aliases}) > 1


def extract_finalization_receipt(result: dict[str, Any]) -> dict[str, Any] | None:
    aliases = finalization_receipt_aliases(result)
    if not aliases:
        return None
    if len({canonical_digest(value) for value in aliases}) > 1:
        return {"malformed_receipt_value": True, "conflicting_receipt_aliases": True}
    return aliases[0]


def extract_finalization_consumption(result: dict[str, Any]) -> dict[str, Any] | None:
    value = first_present(
        result,
        [
            "finalization_consumption",
            "consumed_finalization",
            "result.finalization_consumption",
        ],
    )
    return value if isinstance(value, dict) else None


def _value_at_path(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = data
    for part in path:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def projection_aliases(result: dict[str, Any]) -> list[dict[str, Any]]:
    aliases: list[dict[str, Any]] = []
    for path in (
        ("authoritative_projection",),
        ("finalization", "authoritative_projection"),
        ("result", "authoritative_projection"),
    ):
        value = _value_at_path(result, path)
        if isinstance(value, dict):
            aliases.append(value)
    if all(
        result.get(field) is not None
        for field in ("verdict_contract_version", *VERDICT_AXES)
    ):
        authoritative_final = result.get("authoritative_final")
        if authoritative_final is not None:
            aliases.append(
                {
                    "verdict_contract_version": result["verdict_contract_version"],
                    **{field: result[field] for field in VERDICT_AXES},
                    "authoritative_final": authoritative_final,
                }
            )
    return aliases


def projection_from_result(result: dict[str, Any]) -> dict[str, Any] | None:
    aliases = projection_aliases(result)
    if not aliases or len({canonical_digest(value) for value in aliases}) != 1:
        return None
    return aliases[0]


def finalization_required(target: str, result: dict[str, Any]) -> bool:
    explicit = boolish(
        first_present(
            result,
            [
                "finalization_required",
                "prior_final_attempt_exists",
                "consumes_predecessor_final_attempt",
                "result.finalization_required",
            ],
        )
    )
    if explicit:
        return True
    if target == "validate":
        applicability = (
            str(
                first_present(
                    result,
                    ["finalization_applicability", "result.finalization_applicability"],
                )
                or ""
            )
            .strip()
            .lower()
        )
        return bool(
            first_present(
                result,
                [
                    "finalization_contract_version",
                    "result.finalization_contract_version",
                ],
            )
            == 1
            or applicability == "required"
            or boolish(
                first_present(
                    result, ["governed_transition", "result.governed_transition"]
                )
            )
        )
    if target == "derive":
        derive_mode = (
            str(
                first_present(result, ["derive_mode", "mode", "result.derive_mode"])
                or ""
            )
            .strip()
            .lower()
        )
        if derive_mode in {"initial_init", "bootstrap"}:
            return False
        applicability = (
            str(
                first_present(
                    result,
                    ["finalization_applicability", "result.finalization_applicability"],
                )
                or ""
            )
            .strip()
            .lower()
        )
        reason = first_present(
            result,
            [
                "finalization_not_applicable_reason",
                "result.finalization_not_applicable_reason",
            ],
        )
        prior_exists = first_present(
            result, ["prior_final_attempt_exists", "result.prior_final_attempt_exists"]
        )
        transition_kind = (
            str(
                first_present(result, ["transition_kind", "result.transition_kind"])
                or ""
            )
            .strip()
            .lower()
        )
        reasoned_exemption = bool(
            applicability == "not_applicable"
            and opaque_id(reason)
            and prior_exists is False
            and transition_kind
            in {"standalone_repair", "unrelated_state_repair", "no_predecessor_attempt"}
        )
        return not reasoned_exemption
    if target == "report":
        return (
            str(
                first_present(result, ["completion_status", "result.completion_status"])
                or ""
            )
            .strip()
            .lower()
            == "complete_verified"
        )
    return False
