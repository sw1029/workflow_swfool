"""Actual three-lens derive consumption contract for active advice clauses."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .derive_advice_artifacts import (
    advice_lens_receipt_projection,
    advice_synthesis_output_projection,
    advice_synthesis_output_sha256 as _artifact_advice_synthesis_output_sha256,
    derive_runtime_artifact_binding,
)


LENS_ROLES = {"goal_value", "architecture_contract", "miss_validation"}
CLAUSE_DISPOSITIONS = {"incorporated", "deferred", "tested", "rejected"}
CLAUSE_SET_KEYS = {
    "contract_version",
    "applicability",
    "advice_packet_digest",
    "actionable_clause_ids",
    "clause_source_digests",
    "clause_set_sha256",
}
NOT_APPLICABLE_KEYS = CLAUSE_SET_KEYS | {
    "not_applicable_reason_id",
    "evidence_ids",
}
ASSESSMENT_KEYS = {
    "contract_version",
    "clause_id",
    "lens_agent_id",
    "lens_receipt_id",
    "disposition",
    "evidence_ids",
    "candidate_ids",
    "assessment_sha256",
}
RECONCILIATION_KEYS = {
    "contract_version",
    "clause_id",
    "final_disposition",
    "consumed_lens_assessment_sha256s",
    "evidence_ids",
    "selected_candidate_ids",
    "reconciliation_sha256",
}


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _full_sha256(value: object) -> bool:
    text = str(value or "").strip().lower().removeprefix("sha256:")
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


def _opaque(value: object) -> bool:
    return isinstance(value, str) and value == value.strip() and 0 < len(value) <= 256


def _opaque_list(value: object, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(_opaque(item) for item in value)
        and len(value) == len(set(value))
    )


def _body_sha256(row: dict[str, Any], digest_key: str) -> str:
    return canonical_sha256(
        {key: value for key, value in row.items() if key != digest_key}
    )


def advice_clause_set_sha256(contract: dict[str, Any]) -> str:
    return _body_sha256(contract, "clause_set_sha256")


def advice_assessment_sha256(assessment: dict[str, Any]) -> str:
    return _body_sha256(assessment, "assessment_sha256")


def advice_reconciliation_row_sha256(reconciliation: dict[str, Any]) -> str:
    return _body_sha256(reconciliation, "reconciliation_sha256")


def advice_reconciliation_set_sha256(rows: list[dict[str, Any]]) -> str:
    return canonical_sha256(
        sorted(rows, key=lambda row: str(row.get("clause_id") or ""))
    )


def advice_synthesis_output_sha256(synthesis: dict[str, Any]) -> str:
    return _artifact_advice_synthesis_output_sha256(synthesis)


def _clause_set_errors(contract: object) -> list[str]:
    if not isinstance(contract, dict):
        return ["derive_advice_clause_set_missing"]
    applicability = str(contract.get("applicability") or "")
    expected_keys = (
        NOT_APPLICABLE_KEYS if applicability == "not_applicable" else CLAUSE_SET_KEYS
    )
    errors: list[str] = []
    if set(contract) != expected_keys or contract.get("contract_version") != 1:
        errors.append("derive_advice_clause_set_schema_invalid")
    clause_ids = contract.get("actionable_clause_ids")
    source_digests = contract.get("clause_source_digests")
    if not _opaque_list(clause_ids, allow_empty=True) or clause_ids != sorted(
        clause_ids
    ):
        errors.append("derive_advice_clause_set_ids_invalid")
        clause_ids = []
    if not isinstance(source_digests, dict) or set(source_digests) != set(clause_ids):
        errors.append("derive_advice_clause_sources_invalid")
    elif not all(
        _opaque(key) and _full_sha256(value) for key, value in source_digests.items()
    ):
        errors.append("derive_advice_clause_sources_invalid")
    if applicability == "applicable":
        if not _full_sha256(contract.get("advice_packet_digest")):
            errors.append("derive_advice_packet_digest_invalid")
    elif applicability == "not_applicable":
        if (
            clause_ids
            or source_digests
            or contract.get("advice_packet_digest") is not None
        ):
            errors.append("derive_advice_not_applicable_has_active_clause")
        if not _opaque(contract.get("not_applicable_reason_id")) or not _opaque_list(
            contract.get("evidence_ids")
        ):
            errors.append("derive_advice_not_applicable_unproven")
    else:
        errors.append("derive_advice_applicability_invalid")
    if not _full_sha256(contract.get("clause_set_sha256")) or contract.get(
        "clause_set_sha256"
    ) != advice_clause_set_sha256(contract):
        errors.append("derive_advice_clause_set_digest_invalid")
    return errors


def _assessment_errors(
    row: object,
    clause_id: str,
    candidate_ids: set[str],
    lens_agent_id: str,
    lens_receipt_id: str,
) -> list[str]:
    if not isinstance(row, dict) or set(row) != ASSESSMENT_KEYS:
        return ["derive_advice_lens_assessment_invalid"]
    errors: list[str] = []
    if (
        row.get("contract_version") != 1
        or row.get("clause_id") != clause_id
        or row.get("lens_agent_id") != lens_agent_id
        or row.get("lens_receipt_id") != lens_receipt_id
        or row.get("disposition") not in CLAUSE_DISPOSITIONS
        or not _opaque_list(row.get("evidence_ids"))
        or not _opaque_list(row.get("candidate_ids"), allow_empty=True)
        or not set(row.get("candidate_ids") or []).issubset(candidate_ids)
    ):
        errors.append("derive_advice_lens_assessment_invalid")
    if not _full_sha256(row.get("assessment_sha256")) or row.get(
        "assessment_sha256"
    ) != advice_assessment_sha256(row):
        errors.append("derive_advice_lens_assessment_digest_invalid")
    return errors


def _lens_errors(
    analysis: dict[str, Any], clause_ids: list[str], clause_set_sha: str
) -> tuple[list[str], dict[str, list[str]]]:
    lenses = analysis.get("lens_results")
    if not isinstance(lenses, list) or len(lenses) != 3:
        return ["derive_advice_exact_three_lenses_required"], {}
    errors: list[str] = []
    roles = [str(row.get("role_id") or "") for row in lenses if isinstance(row, dict)]
    agent_ids = [
        str(row.get("agent_id") or "") for row in lenses if isinstance(row, dict)
    ]
    receipt_ids = [
        str(row.get("agent_receipt_id") or "")
        for row in lenses
        if isinstance(row, dict)
    ]
    if set(roles) != LENS_ROLES or len(set(roles)) != 3:
        errors.append("derive_advice_lens_roles_invalid")
    if (
        len(agent_ids) != 3
        or len(set(agent_ids)) != 3
        or len(receipt_ids) != 3
        or len(set(receipt_ids)) != 3
    ):
        errors.append("derive_advice_lens_identity_invalid")
    expected_manifest_sha = analysis.get("shared_evidence_manifest_sha256")
    assessment_hashes: dict[str, list[str]] = {
        clause_id: [] for clause_id in clause_ids
    }
    for lens in lenses:
        if not isinstance(lens, dict):
            errors.append("derive_advice_lens_receipt_invalid")
            continue
        output = lens.get("output")
        if (
            lens.get("read_only") is not True
            or lens.get("status") != "complete"
            or lens.get("input_evidence_manifest_sha256") != expected_manifest_sha
            or not _opaque(lens.get("agent_id"))
            or not _opaque(lens.get("agent_receipt_id"))
            or not _opaque(lens.get("output_ref"))
            or not isinstance(output, dict)
            or lens.get("output_sha256") != canonical_sha256(output)
        ):
            errors.append("derive_advice_lens_receipt_invalid")
            continue
        candidates = output.get("candidates")
        candidate_ids = (
            {
                str(candidate.get("candidate_id"))
                for candidate in candidates
                if isinstance(candidate, dict)
                and _opaque(candidate.get("candidate_id"))
            }
            if isinstance(candidates, list)
            else set()
        )
        assessments = output.get("advice_clause_assessments")
        if (
            output.get("advice_clause_set_sha256") != clause_set_sha
            or not isinstance(assessments, list)
            or [
                str(row.get("clause_id") or "")
                for row in assessments
                if isinstance(row, dict)
            ]
            != clause_ids
        ):
            errors.append("derive_advice_lens_clause_coverage_mismatch")
            continue
        for clause_id, assessment in zip(clause_ids, assessments, strict=True):
            errors.extend(
                _assessment_errors(
                    assessment,
                    clause_id,
                    candidate_ids,
                    str(lens.get("agent_id") or ""),
                    str(lens.get("agent_receipt_id") or ""),
                )
            )
            if isinstance(assessment, dict):
                assessment_hashes[clause_id].append(
                    str(assessment.get("assessment_sha256") or "")
                )
    if any(
        len(values) != 3 or len(set(values)) != 3
        for values in assessment_hashes.values()
    ):
        errors.append("derive_advice_lens_assessment_consumption_basis_invalid")
    return errors, assessment_hashes


def _reconciliation_errors(
    synthesis: dict[str, Any],
    clause_ids: list[str],
    clause_set_sha: str,
    assessment_hashes: dict[str, list[str]],
) -> list[str]:
    rows = synthesis.get("advice_clause_reconciliation")
    if (
        not isinstance(rows, list)
        or [str(row.get("clause_id") or "") for row in rows if isinstance(row, dict)]
        != clause_ids
    ):
        return ["derive_advice_synthesis_clause_coverage_mismatch"]
    errors: list[str] = []
    union = synthesis.get("candidate_union_ids")
    candidate_union = set(map(str, union)) if isinstance(union, list) else set()
    for clause_id, row in zip(clause_ids, rows, strict=True):
        expected_hashes = sorted(assessment_hashes.get(clause_id, []))
        valid = (
            isinstance(row, dict)
            and set(row) == RECONCILIATION_KEYS
            and row.get("contract_version") == 1
            and row.get("clause_id") == clause_id
            and row.get("final_disposition") in CLAUSE_DISPOSITIONS
            and row.get("consumed_lens_assessment_sha256s") == expected_hashes
            and _opaque_list(row.get("evidence_ids"))
            and _opaque_list(row.get("selected_candidate_ids"), allow_empty=True)
            and set(row.get("selected_candidate_ids") or []).issubset(candidate_union)
        )
        if not valid:
            errors.append("derive_advice_synthesis_reconciliation_invalid")
            continue
        if not _full_sha256(row.get("reconciliation_sha256")) or row.get(
            "reconciliation_sha256"
        ) != advice_reconciliation_row_sha256(row):
            errors.append("derive_advice_synthesis_reconciliation_digest_invalid")
    if synthesis.get("advice_clause_set_sha256") != clause_set_sha:
        errors.append("derive_advice_synthesis_clause_set_mismatch")
    if synthesis.get(
        "advice_reconciliation_sha256"
    ) != advice_reconciliation_set_sha256(rows):
        errors.append("derive_advice_synthesis_reconciliation_set_digest_invalid")
    if (
        not _opaque(synthesis.get("synthesis_output_ref"))
        or not _full_sha256(synthesis.get("synthesis_output_sha256"))
        or synthesis.get("synthesis_output_sha256")
        != advice_synthesis_output_sha256(synthesis)
    ):
        errors.append("derive_advice_synthesis_output_receipt_invalid")
    return errors


def validate_derive_advice_analysis(analysis: object) -> list[str]:
    if not isinstance(analysis, dict):
        return ["derive_advice_analysis_missing"]
    manifest = analysis.get("shared_evidence_manifest")
    if not isinstance(manifest, dict):
        return ["derive_advice_clause_set_missing"]
    if analysis.get("shared_evidence_manifest_sha256") != canonical_sha256(manifest):
        return ["derive_advice_shared_manifest_digest_invalid"]
    contract = manifest.get("active_advice_clause_set")
    errors = _clause_set_errors(contract)
    if not isinstance(contract, dict):
        return errors
    clause_ids = contract.get("actionable_clause_ids")
    if not isinstance(clause_ids, list):
        return errors
    lens_errors, assessment_hashes = _lens_errors(
        analysis, clause_ids, str(contract.get("clause_set_sha256") or "")
    )
    errors.extend(lens_errors)
    synthesis = analysis.get("synthesis")
    if not isinstance(synthesis, dict):
        errors.append("derive_advice_synthesis_missing")
    else:
        errors.extend(
            _reconciliation_errors(
                synthesis,
                clause_ids,
                str(contract.get("clause_set_sha256") or ""),
                assessment_hashes,
            )
        )
    return sorted(set(errors))


def derive_advice_consumer_binding(
    result: dict[str, Any],
    clause_id: str,
    *,
    context: dict[str, Any] | None = None,
    workspace_root: str | Path | None = None,
) -> dict[str, Any] | None:
    if result.get("step") != "derive":
        return None
    analysis = result.get("improvement_analysis_manifest")
    if validate_derive_advice_analysis(analysis):
        return None
    assert isinstance(analysis, dict)
    manifest = analysis["shared_evidence_manifest"]
    contract = manifest["active_advice_clause_set"]
    if clause_id not in contract["actionable_clause_ids"]:
        return None
    synthesis = analysis["synthesis"]
    runtime_artifacts = derive_runtime_artifact_binding(
        result,
        analysis,
        context=context,
        explicit_root=workspace_root,
    )
    if runtime_artifacts is None:
        return None
    reconciliation = next(
        row
        for row in synthesis["advice_clause_reconciliation"]
        if row["clause_id"] == clause_id
    )
    return {
        "contract_version": 1,
        "consumer_kind": "derive_three_lens_synthesis",
        "shared_evidence_manifest_sha256": analysis["shared_evidence_manifest_sha256"],
        "advice_clause_set_sha256": contract["clause_set_sha256"],
        "synthesis_agent_id": synthesis["synthesis_agent_id"],
        "synthesis_receipt_id": synthesis["synthesis_receipt_id"],
        "synthesis_output_ref": synthesis["synthesis_output_ref"],
        "synthesis_output_sha256": synthesis["synthesis_output_sha256"],
        "advice_reconciliation_sha256": synthesis["advice_reconciliation_sha256"],
        "clause_reconciliation_sha256": reconciliation["reconciliation_sha256"],
        "runtime_artifact_binding": runtime_artifacts,
    }


__all__ = (
    "advice_lens_receipt_projection",
    "advice_assessment_sha256",
    "advice_clause_set_sha256",
    "advice_reconciliation_row_sha256",
    "advice_reconciliation_set_sha256",
    "advice_synthesis_output_projection",
    "advice_synthesis_output_sha256",
    "canonical_sha256",
    "derive_advice_consumer_binding",
    "validate_derive_advice_analysis",
)
