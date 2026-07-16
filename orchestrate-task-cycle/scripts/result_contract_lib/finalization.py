from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .common import boolish, first_present


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
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def projection_conclusions(projection: dict[str, Any]) -> tuple[str, str]:
    """Project typed axes without collapsing task acceptance into goal progress."""

    def status(axis: str) -> str:
        value = projection.get(axis)
        return str(value.get("status") or value.get("verdict") or "").strip().lower() if isinstance(value, dict) else ""

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
            aliases.append(current if isinstance(current, dict) else {"malformed_receipt_value": True})
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
    if all(result.get(field) is not None for field in ("verdict_contract_version", *VERDICT_AXES)):
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
        applicability = str(first_present(result, ["finalization_applicability", "result.finalization_applicability"]) or "").strip().lower()
        return bool(
            first_present(result, ["finalization_contract_version", "result.finalization_contract_version"]) == 1
            or applicability == "required"
            or boolish(first_present(result, ["governed_transition", "result.governed_transition"]))
        )
    if target == "derive":
        derive_mode = str(first_present(result, ["derive_mode", "mode", "result.derive_mode"]) or "").strip().lower()
        if derive_mode in {"initial_init", "bootstrap"}:
            return False
        applicability = str(first_present(result, ["finalization_applicability", "result.finalization_applicability"]) or "").strip().lower()
        reason = first_present(result, ["finalization_not_applicable_reason", "result.finalization_not_applicable_reason"])
        prior_exists = first_present(result, ["prior_final_attempt_exists", "result.prior_final_attempt_exists"])
        transition_kind = str(first_present(result, ["transition_kind", "result.transition_kind"]) or "").strip().lower()
        reasoned_exemption = bool(
            applicability == "not_applicable"
            and opaque_id(reason)
            and prior_exists is False
            and transition_kind in {"standalone_repair", "unrelated_state_repair", "no_predecessor_attempt"}
        )
        return not reasoned_exemption
    if target == "report":
        return str(first_present(result, ["completion_status", "result.completion_status"]) or "").strip().lower() == "complete_verified"
    return False


def candidate_errors(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    def error(code: str, message: str, evidence: Any = None) -> None:
        row: dict[str, Any] = {"code": code, "message": message}
        if evidence is not None:
            row["evidence"] = evidence
        errors.append(row)

    if candidate.get("schema_version") != 1 or candidate.get("kind") != CANDIDATE_KIND:
        error("final_candidate_schema_invalid", "Final candidate requires schema_version=1 and kind=cycle_final_candidate.")
    if candidate.get("final_candidate") is not True:
        error("final_candidate_marker_invalid", "Completion validation must mark the immutable candidate with final_candidate=true.")
    for field in ("cycle_id", "attempt_id"):
        if not opaque_id(candidate.get(field)):
            error("final_candidate_identity_invalid", "Final candidate identity fields must be bounded opaque strings.", {"field": field})
    expected_fields = (
        "expected_previous_revision",
        "expected_previous_attempt_id",
        "expected_previous_finalization_token",
    )
    missing_expected = [field for field in expected_fields if field not in candidate]
    if missing_expected:
        error("final_candidate_previous_binding_missing", "Final candidate must explicitly bind the previous pointer, including null first-publication values.", {"fields": missing_expected})
    for field in ("expected_previous_revision",):
        value = candidate.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            error("final_candidate_revision_invalid", "Expected previous revision must be null or a positive integer.", {"field": field})
    previous_attempt = candidate.get("expected_previous_attempt_id")
    if previous_attempt is not None and not opaque_id(previous_attempt):
        error("final_candidate_identity_invalid", "Expected previous attempt ID must be null or a bounded opaque string.", {"field": "expected_previous_attempt_id"})
    previous_token = candidate.get("expected_previous_finalization_token")
    if previous_token is not None and not full_sha256(previous_token):
        error("final_candidate_previous_token_invalid", "Expected previous finalization token must be null or a full lowercase SHA-256 digest.")
    previous_fields = (
        candidate.get("expected_previous_revision"),
        candidate.get("expected_previous_attempt_id"),
        candidate.get("expected_previous_finalization_token"),
    )
    if any(value is None for value in previous_fields) and not all(value is None for value in previous_fields):
        error("final_candidate_previous_binding_partial", "Previous revision, attempt, and token must be all null for the first revision or all populated.")
    if candidate.get("verdict_contract_version") != 1:
        error("final_candidate_verdict_version_invalid", "Final candidate must preserve verdict_contract_version=1.")
    producer_projection_fields = sorted(
        {
            "authoritative_projection",
            "authoritative_projection_digest",
            "authoritative_projection_id",
            "validation_axes_digest",
        }.intersection(candidate)
    )
    nested_projection = (
        isinstance(candidate.get("finalization"), dict)
        and isinstance(candidate["finalization"].get("authoritative_projection"), dict)
    ) or (
        isinstance(candidate.get("result"), dict)
        and isinstance(candidate["result"].get("authoritative_projection"), dict)
    )
    if producer_projection_fields or nested_projection:
        error(
            "final_candidate_projection_preassigned",
            "Only the existing finalization owner may construct the authoritative projection and its digests.",
            {"fields": producer_projection_fields, "nested_projection": bool(nested_projection)},
        )
    missing_axes = [axis for axis in VERDICT_AXES if not isinstance(candidate.get(axis), dict)]
    if missing_axes:
        error("final_candidate_verdict_axis_missing", "Final candidate must preserve all six typed verdict axes.", {"axes": missing_axes})
    alias_containers = [
        candidate.get("verdict_axes"),
        candidate.get("result"),
        candidate.get("result", {}).get("verdict_axes")
        if isinstance(candidate.get("result"), dict)
        else None,
    ]
    alias_conflicts: list[str] = []
    for axis in VERDICT_AXES:
        canonical = candidate.get(axis)
        canonical_status = str(
            canonical.get("status") or canonical.get("verdict") or ""
        ).strip().lower() if isinstance(canonical, dict) else ""
        for container in alias_containers:
            if not isinstance(container, dict) or axis not in container:
                continue
            alias = container[axis]
            alias_status = str(
                alias.get("status") or alias.get("verdict") or ""
            ).strip().lower() if isinstance(alias, dict) else str(alias or "").strip().lower()
            if alias_status != canonical_status:
                alias_conflicts.append(axis)
                break
    if alias_conflicts:
        error(
            "final_candidate_verdict_alias_conflict",
            "Final candidate verdict aliases disagree with the canonical top-level axes.",
            {"axes": sorted(set(alias_conflicts))},
        )
    if "attempt_revision" in candidate or "supersedes_revision" in candidate or "supersedes_finalization_token" in candidate:
        error("final_candidate_revision_preassigned", "Only the finalization owner may assign attempt revision and supersession lineage.")
    durable_state = candidate.get("durable_state_candidate")
    if not isinstance(durable_state, dict) or durable_state.get("mode") not in {"complete_projection", "typed_operations"}:
        error("final_candidate_durable_state_invalid", "Final candidate requires a typed complete_projection or typed_operations durable state candidate.")
    return errors


def receipt_shape_errors(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    def error(code: str, message: str, evidence: Any = None) -> None:
        row: dict[str, Any] = {"code": code, "message": message}
        if evidence is not None:
            row["evidence"] = evidence
        errors.append(row)

    if receipt.get("schema_version") != 1 or receipt.get("kind") != RECEIPT_KIND:
        error("finalization_receipt_schema_invalid", "Finalization receipt requires schema_version=1 and kind=cycle_finalization_receipt.")
    for field in ("cycle_id", "attempt_id", "authoritative_final", "authoritative_projection_id"):
        if not opaque_id(receipt.get(field)):
            error("finalization_receipt_identity_invalid", "Finalization receipt identity fields must be bounded opaque strings.", {"field": field})
    if receipt.get("authoritative_final") not in {"success", "failure", "blocked", "partial", "not_evaluated"}:
        error("finalization_receipt_authoritative_final_invalid", "Authoritative final verdict is outside the producer's closed enum.")
    for field in ("attempt_revision",):
        value = receipt.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            error("finalization_receipt_revision_invalid", "Finalization receipt attempt_revision must be a positive integer.", {"field": field})
    for field in ("supersedes_revision", "expected_previous_revision"):
        value = receipt.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            error("finalization_receipt_revision_invalid", "Supersession revisions must be null or positive integers.", {"field": field})
    for field in ("supersedes_finalization_token", "expected_previous_finalization_token"):
        value = receipt.get(field)
        if value is not None and not full_sha256(value):
            error("finalization_receipt_supersession_invalid", "Supersession tokens must be null or full lowercase SHA-256 digests.", {"field": field})
    previous_attempt = receipt.get("expected_previous_attempt_id")
    if previous_attempt is not None and not opaque_id(previous_attempt):
        error("finalization_receipt_supersession_invalid", "Expected previous attempt ID must be null or a bounded opaque string.")
    if receipt.get("state_commit_status") != "committed":
        error("finalization_receipt_not_committed", "Only a committed finalization receipt may be consumed.")
    for field in SHA256_FIELDS:
        if not full_sha256(receipt.get(field)):
            error("finalization_receipt_hash_invalid", "Receipt hash fields require full lowercase SHA-256 digests.", {"field": field})
    if receipt.get("finalization_token") and receipt.get("snapshot_sha256") and receipt.get("finalization_token") != receipt.get("snapshot_sha256"):
        error("finalization_receipt_snapshot_token_mismatch", "Finalization token and immutable snapshot digest must match.")
    if receipt.get("authoritative_projection_id") != f"sha256:{receipt.get('authoritative_projection_digest')}":
        error("finalization_receipt_projection_id_mismatch", "Authoritative projection ID must be derived from its full digest.")
    snapshot_ref = receipt.get("snapshot_ref")
    if not opaque_id(snapshot_ref, max_length=512) or Path(str(snapshot_ref)).is_absolute() or ".." in Path(str(snapshot_ref)).parts:
        error("finalization_receipt_snapshot_ref_invalid", "Snapshot reference must be a bounded workspace-relative path.")
    if full_sha256(receipt.get("receipt_hash")):
        unhashed = {key: value for key, value in receipt.items() if key != "receipt_hash"}
        if canonical_digest(unhashed) != receipt.get("receipt_hash"):
            error("finalization_receipt_self_hash_mismatch", "Receipt hash does not bind the supplied receipt body.")
    expected_lineage = (
        receipt.get("expected_previous_revision"),
        receipt.get("expected_previous_attempt_id"),
        receipt.get("expected_previous_finalization_token"),
    )
    expected_empty = all(value is None for value in expected_lineage)
    expected_complete = all(value is not None for value in expected_lineage)
    if not expected_empty and not expected_complete:
        error("finalization_receipt_previous_binding_partial", "CAS predecessor revision, attempt, and token must be all null or all populated.")
    same_attempt_correction = bool(
        expected_complete and receipt.get("expected_previous_attempt_id") == receipt.get("attempt_id")
    )
    supersession = (
        receipt.get("supersedes_revision"),
        receipt.get("supersedes_finalization_token"),
    )
    if same_attempt_correction:
        if receipt.get("attempt_revision") != receipt.get("expected_previous_revision", 0) + 1:
            error("finalization_receipt_revision_sequence_invalid", "Same-attempt correction revision must increment the expected previous revision by one.")
        if any(value is None for value in supersession):
            error("finalization_receipt_supersession_incomplete", "Same-attempt corrections must preserve complete supersession lineage.")
        if receipt.get("supersedes_revision") != receipt.get("expected_previous_revision"):
            error("finalization_receipt_supersession_mismatch", "Superseded and expected previous revisions must match.")
        if receipt.get("supersedes_finalization_token") != receipt.get("expected_previous_finalization_token"):
            error("finalization_receipt_supersession_mismatch", "Superseded and expected previous finalization tokens must match.")
    else:
        if receipt.get("attempt_revision") != 1:
            error("finalization_receipt_new_attempt_revision_invalid", "A first or cross-attempt finalization must start at revision 1.")
        if any(value is not None for value in supersession):
            error("finalization_receipt_cross_attempt_supersession_invalid", "Cross-attempt CAS binding must not claim same-attempt supersession.")
    return errors


def consumption_errors(
    receipt: dict[str, Any],
    consumption: dict[str, Any] | None,
    projection: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    def error(code: str, message: str, evidence: Any = None) -> None:
        row: dict[str, Any] = {"code": code, "message": message}
        if evidence is not None:
            row["evidence"] = evidence
        errors.append(row)

    if not isinstance(consumption, dict):
        error("finalization_consumption_missing", "Consumer must echo the exact finalization token, revision, projection, and receipt hash.")
    else:
        bindings = {
            "finalization_token": receipt.get("finalization_token"),
            "attempt_id": receipt.get("attempt_id"),
            "attempt_revision": receipt.get("attempt_revision"),
            "authoritative_projection_id": receipt.get("authoritative_projection_id"),
            "authoritative_projection_digest": receipt.get("authoritative_projection_digest"),
            "receipt_hash": receipt.get("receipt_hash"),
        }
        mismatched = [field for field, expected in bindings.items() if consumption.get(field) != expected]
        if mismatched:
            error("finalization_consumption_binding_mismatch", "Consumer echo does not match the verified finalization receipt.", {"fields": mismatched})
    if not isinstance(projection, dict):
        error("authoritative_projection_missing", "Consumer must expose the finalized authoritative projection it consumed.")
    else:
        expected_keys = {"verdict_contract_version", *VERDICT_AXES, "authoritative_final"}
        if set(projection) != expected_keys:
            error(
                "authoritative_projection_schema_mismatch",
                "Authoritative projection must contain exactly the version, six verdict axes, and authoritative final.",
                {"missing": sorted(expected_keys - set(projection)), "extra": sorted(set(projection) - expected_keys)},
            )
        if canonical_digest(projection) != receipt.get("authoritative_projection_digest"):
            error("authoritative_projection_digest_mismatch", "Consumer projection does not match the receipt-bound authoritative projection digest.")
        if projection.get("authoritative_final") != receipt.get("authoritative_final"):
            error("authoritative_projection_verdict_mismatch", "Consumer projection and receipt expose different authoritative final verdicts.")
    return errors


def workspace_root(result: dict[str, Any], contract_context: dict[str, Any] | None) -> Path:
    values: Iterable[Any] = (
        (contract_context or {}).get("workspace_root"),
        (contract_context or {}).get("workspace"),
        (contract_context or {}).get("root"),
        result.get("workspace_root"),
        result.get("workspace"),
        result.get("root"),
    )
    value = next((item for item in values if isinstance(item, str) and item.strip()), ".")
    return Path(value).resolve()


def verify_current_receipt(
    root: Path,
    receipt: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        import cycle_ledger

        verified = cycle_ledger.verify_finalization_receipt(root, str(receipt.get("cycle_id") or ""), receipt)
    except (ImportError, AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, [
            {
                "code": "finalization_receipt_current_verification_failed",
                "message": "Finalization receipt did not verify against the immutable snapshot and current pointer.",
                "evidence": {"reason": type(exc).__name__},
            }
        ]
    if not isinstance(verified, dict) or verified.get("valid") is not True or not isinstance(verified.get("snapshot"), dict):
        return None, [
            {
                "code": "finalization_receipt_current_verification_failed",
                "message": "Finalization verifier did not return a valid current snapshot.",
            }
        ]
    return verified, []


def load_current_projection(
    root: Path,
    cycle_id: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        import cycle_ledger

        state = cycle_ledger.load_current_finalized_state(root, cycle_id)
    except (ImportError, AttributeError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return None, None, [
            {
                "code": "current_finalization_projection_unavailable",
                "message": "Current finalization pointer could not be verified and projected.",
                "evidence": {"reason": type(exc).__name__},
            }
        ]
    projection = state.get("authoritative_projection") if isinstance(state, dict) else None
    receipt = state.get("receipt") if isinstance(state, dict) else None
    errors: list[dict[str, Any]] = []
    if not isinstance(projection, dict) or not isinstance(receipt, dict):
        errors.append(
            {
                "code": "current_finalization_projection_invalid",
                "message": "Verified current finalization state omitted its projection or receipt.",
            }
        )
        return None, None, errors
    errors.extend(receipt_shape_errors(receipt))
    if canonical_digest(projection) != receipt.get("authoritative_projection_digest"):
        errors.append(
            {
                "code": "current_finalization_projection_digest_mismatch",
                "message": "Current pointer projection does not match its receipt-bound digest.",
            }
        )
    return (projection if not errors else None), receipt, errors


def validate_finalization_contract(
    target: str,
    result: dict[str, Any],
    contract_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    required = finalization_required(target, result)
    if target == "validate":
        candidate_present = result.get("final_candidate") is not None or result.get("kind") == CANDIDATE_KIND
        if required and not candidate_present:
            errors.append(
                {
                    "code": "final_candidate_missing",
                    "message": "Governed completion validation must emit an immutable final candidate before durable finalization.",
                }
            )
        if candidate_present:
            errors.extend(candidate_errors(result))
        return errors

    receipt = extract_finalization_receipt(result)
    receipt_present = receipt is not None
    if required and not receipt_present:
        errors.append(
            {
                "code": "finalization_receipt_missing",
                "message": "A predecessor final attempt cannot be consumed before its content-bound finalization receipt is verified.",
            }
        )
        return errors
    if not receipt_present:
        return errors
    if conflicting_finalization_receipt_aliases(result):
        errors.append(
            {
                "code": "finalization_receipt_alias_conflict",
                "message": "Finalization receipt aliases disagree; do not select a favorable or current-looking receipt.",
            }
        )
    errors.extend(receipt_shape_errors(receipt))
    aliases = projection_aliases(result)
    if len({canonical_digest(value) for value in aliases}) > 1:
        errors.append(
            {
                "code": "authoritative_projection_alias_conflict",
                "message": "Current authoritative projection aliases disagree; do not select the favorable projection.",
            }
        )
    projection = projection_from_result(result)
    consumption = extract_finalization_consumption(result)
    errors.extend(consumption_errors(receipt, consumption, projection))
    if errors:
        return errors
    verified, verification_errors = verify_current_receipt(workspace_root(result, contract_context), receipt)
    errors.extend(verification_errors)
    if verified is not None:
        snapshot = verified["snapshot"]
        snapshot_projection = snapshot.get("authoritative_projection")
        if snapshot.get("kind") != SNAPSHOT_KIND:
            errors.append({"code": "finalization_snapshot_schema_mismatch", "message": "Verified finalization snapshot kind is invalid."})
        if snapshot_projection != projection:
            errors.append(
                {
                    "code": "authoritative_projection_snapshot_mismatch",
                    "message": "Consumer projection differs from the current immutable finalization snapshot.",
                }
            )
    return errors


def verified_projection(
    result: dict[str, Any],
    contract_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    receipt = extract_finalization_receipt(result)
    if receipt is None:
        return None, None, []
    errors: list[dict[str, Any]] = []
    if conflicting_finalization_receipt_aliases(result):
        errors.append(
            {
                "code": "finalization_receipt_alias_conflict",
                "message": "Finalization receipt aliases disagree; current projection consumption is not evaluated.",
            }
        )
    errors.extend(receipt_shape_errors(receipt))
    if errors:
        return None, receipt, errors
    verified, verification_errors = verify_current_receipt(workspace_root(result, contract_context), receipt)
    errors.extend(verification_errors)
    if verified is None:
        return None, receipt, errors
    projection = verified["snapshot"].get("authoritative_projection")
    if not isinstance(projection, dict) or canonical_digest(projection) != receipt.get("authoritative_projection_digest"):
        errors.append(
            {
                "code": "authoritative_projection_snapshot_mismatch",
                "message": "Verified snapshot does not contain the receipt-bound authoritative projection.",
            }
        )
        return None, receipt, errors
    return projection, receipt, errors
