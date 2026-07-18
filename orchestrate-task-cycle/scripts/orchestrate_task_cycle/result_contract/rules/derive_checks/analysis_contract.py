from __future__ import annotations

import hashlib
import json
from typing import Any

from .analysis_manifest import validate_shared_manifest
from .shared import (
    CANONICAL_PACK_DISPOSITIONS,
    DERIVE_AGENT_ROLES,
    DERIVE_SELECTION_OUTCOMES,
    add,
)
from .state import DeriveFacts
from ...derive_advice import validate_derive_advice_analysis

ACTIONABILITY_VALUES = {
    "actionable",
    "blocked_external",
    "blocked_authority",
    "unverified",
}
CANDIDATE_KEY_FIELDS = (
    "exact_subject_fingerprint",
    "first_failing_invariant",
    "canonical_owner",
    "task_kind",
    "expected_blocker_transition",
    "actionability",
    "pack_disposition",
    "issue_derived",
)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _full_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


def _nonempty_strings(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _finding(
    facts: DeriveFacts, code: str, message: str, evidence: dict[str, Any] | None = None
) -> None:
    add(facts.findings, "block", code, message, evidence)


def _validate_candidate(facts: DeriveFacts, candidate: object, role_id: str) -> str:
    if not isinstance(candidate, dict):
        _finding(
            facts,
            "derive_lens_candidate_invalid",
            "Lens candidates must be structured objects.",
            {"role_id": role_id},
        )
        return ""
    required = (
        "candidate_id",
        "exact_subject_fingerprint",
        "first_failing_invariant",
        "canonical_owner",
        "task_kind",
        "expected_blocker_transition",
        "actionability",
        "pack_disposition",
    )
    missing = [
        field
        for field in required
        if not isinstance(candidate.get(field), str)
        or not candidate.get(field, "").strip()
    ]
    if (
        missing
        or not _nonempty_strings(candidate.get("evidence_ids"))
        or not _nonempty_strings(candidate.get("validation_ids"))
    ):
        _finding(
            facts,
            "derive_lens_candidate_incomplete",
            "Lens candidate is missing owner, invariant, evidence, or validation contract.",
            {"role_id": role_id, "fields": missing},
        )
    if str(candidate.get("actionability") or "") not in ACTIONABILITY_VALUES:
        _finding(
            facts,
            "derive_candidate_actionability_invalid",
            "Candidate actionability is not canonical.",
            {"role_id": role_id},
        )
    if str(candidate.get("pack_disposition") or "") not in CANONICAL_PACK_DISPOSITIONS:
        _finding(
            facts,
            "derive_candidate_pack_disposition_invalid",
            "Candidate pack disposition is outside the canonical enum.",
            {"role_id": role_id},
        )
    if not isinstance(candidate.get("issue_derived"), bool):
        _finding(
            facts,
            "derive_candidate_issue_derivation_missing",
            "Each candidate must declare whether it is issue-derived.",
            {"role_id": role_id},
        )
    return str(candidate.get("candidate_id") or "")


def _validate_rejections(
    facts: DeriveFacts, output: dict[str, Any], role_id: str, candidate_count: int
) -> None:
    rows = output.get("rejection_inventory")
    if not isinstance(rows, list) or (candidate_count == 0 and not rows):
        _finding(
            facts,
            "derive_zero_candidate_rejection_inventory_missing",
            "A zero-candidate lens requires a non-empty rejection inventory.",
            {"role_id": role_id},
        )
        return
    seen: set[str] = set()
    for row in rows:
        valid = (
            isinstance(row, dict)
            and all(
                isinstance(row.get(field), str) and row.get(field, "").strip()
                for field in ("option_id", "reason_code")
            )
            and _nonempty_strings(row.get("evidence_ids"))
        )
        option_id = str(row.get("option_id") or "") if isinstance(row, dict) else ""
        if not valid or option_id in seen:
            _finding(
                facts,
                "derive_lens_rejection_inventory_invalid",
                "Lens rejection rows require unique option ID, reason code, and evidence IDs.",
                {"role_id": role_id},
            )
        seen.add(option_id)


def _validate_lenses(
    facts: DeriveFacts, analysis: dict[str, Any], shared_sha: str
) -> tuple[list[dict[str, Any]], set[str]]:
    rows = analysis.get("lens_results")
    if not isinstance(rows, list) or len(rows) != 3:
        _finding(
            facts,
            "derive_exact_three_lenses_required",
            "Derivation requires exactly three independent lens receipts.",
        )
        return [], set()
    roles = [str(row.get("role_id") or "") for row in rows if isinstance(row, dict)]
    agent_ids = [
        str(row.get("agent_id") or "") for row in rows if isinstance(row, dict)
    ]
    receipts = [
        str(row.get("agent_receipt_id") or "") for row in rows if isinstance(row, dict)
    ]
    if set(roles) != set(DERIVE_AGENT_ROLES) or len(set(roles)) != 3:
        _finding(
            facts,
            "derive_lens_roles_invalid",
            "Lens roles must match the three canonical independent roles.",
            {"roles": roles},
        )
    if (
        len(receipts) != 3
        or any(not item for item in receipts)
        or len(set(receipts)) != 3
    ):
        _finding(
            facts,
            "derive_agent_receipts_not_unique",
            "All three lens receipts must have distinct opaque agent receipt IDs.",
        )
    if (
        len(agent_ids) != 3
        or any(not item for item in agent_ids)
        or len(set(agent_ids)) != 3
    ):
        _finding(
            facts,
            "derive_agent_ids_not_unique",
            "The three lens receipts must come from three distinct opaque agent IDs.",
        )
    candidate_ids: set[str] = set()
    candidate_signatures: dict[str, str] = {}
    signature_ids: dict[str, str] = {}
    valid_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            _finding(
                facts,
                "derive_lens_result_invalid",
                "Every lens result must be a structured object.",
            )
            continue
        role_id = str(row.get("role_id") or "")
        if (
            row.get("read_only") is not True
            or str(row.get("status") or "") != "complete"
        ):
            _finding(
                facts,
                "derive_lens_execution_receipt_incomplete",
                "Each lens must attest read-only completed execution.",
                {"role_id": role_id},
            )
        if row.get("input_evidence_manifest_sha256") != shared_sha:
            _finding(
                facts,
                "derive_lens_input_digest_mismatch",
                "All lens agents must consume the identical frozen evidence digest.",
                {"role_id": role_id},
            )
        output = row.get("output")
        if not isinstance(output, dict):
            _finding(
                facts,
                "derive_lens_output_missing",
                "Lens execution receipt is missing structured output.",
                {"role_id": role_id},
            )
            continue
        if (
            row.get("output_sha256") != _canonical_sha256(output)
            or not str(row.get("output_ref") or "").strip()
        ):
            _finding(
                facts,
                "derive_lens_output_receipt_invalid",
                "Lens output ref/digest does not bind the structured output.",
                {"role_id": role_id},
            )
        candidates = output.get("candidates")
        if not isinstance(candidates, list) or len(candidates) > 5:
            _finding(
                facts,
                "derive_lens_candidate_count_invalid",
                "Each lens must return zero through five candidates.",
                {"role_id": role_id},
            )
            candidates = []
        for candidate in candidates:
            candidate_id = _validate_candidate(facts, candidate, role_id)
            signature = _canonical_sha256(
                {field: candidate.get(field) for field in CANDIDATE_KEY_FIELDS}
                if isinstance(candidate, dict)
                else {}
            )
            if (
                candidate_id in candidate_signatures
                and candidate_signatures[candidate_id] != signature
            ):
                _finding(
                    facts,
                    "derive_candidate_id_conflict",
                    "A candidate ID cannot represent different canonical subject/owner/transition keys.",
                    {"candidate_id": candidate_id},
                )
            if signature in signature_ids and signature_ids[signature] != candidate_id:
                _finding(
                    facts,
                    "derive_candidate_union_not_normalized",
                    "Equivalent subject/invariant/owner/task/transition candidates must share one normalized candidate ID.",
                    {"candidate_ids": sorted({signature_ids[signature], candidate_id})},
                )
            candidate_signatures[candidate_id] = signature
            signature_ids[signature] = candidate_id
            candidate_ids.add(candidate_id)
        _validate_rejections(facts, output, role_id, len(candidates))
        valid_rows.append(row)
    return valid_rows, candidate_ids


def _candidate_rows(lenses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(candidate.get("candidate_id")): candidate
        for lens in lenses
        for candidate in lens.get("output", {}).get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("candidate_id")
    }


def _synthesis_receipt(
    facts: DeriveFacts,
    analysis: dict[str, Any],
    lenses: list[dict[str, Any]],
    shared_sha: str,
) -> dict[str, Any] | None:
    synthesis = analysis.get("synthesis")
    if not isinstance(synthesis, dict):
        _finding(
            facts,
            "derive_synthesis_contract_missing",
            "A single structured synthesis receipt is required.",
        )
        return None
    receipt_ids = {str(row.get("agent_receipt_id") or "") for row in lenses}
    lens_agent_ids = {str(row.get("agent_id") or "") for row in lenses}
    synthesis_receipt_id = str(synthesis.get("synthesis_receipt_id") or "")
    if not synthesis_receipt_id or synthesis_receipt_id in receipt_ids:
        _finding(
            facts,
            "derive_synthesis_receipt_id_invalid",
            "Synthesis requires its own non-empty receipt ID distinct from lens receipts.",
        )
    synthesis_agent_id = str(synthesis.get("synthesis_agent_id") or "")
    if not synthesis_agent_id or synthesis_agent_id in lens_agent_ids:
        _finding(
            facts,
            "derive_synthesis_agent_id_invalid",
            "Synthesis requires one opaque agent ID distinct from all three lens agents.",
        )
    consumed = synthesis.get("consumed_agent_receipt_ids")
    if (
        not isinstance(consumed, list)
        or len(consumed) != 3
        or set(map(str, consumed)) != receipt_ids
    ):
        _finding(
            facts,
            "derive_synthesis_lens_consumption_incomplete",
            "Synthesis must consume all and only the three lens receipts.",
        )
    if synthesis.get("input_evidence_manifest_sha256") != shared_sha:
        _finding(
            facts,
            "derive_synthesis_input_digest_mismatch",
            "Synthesis must consume the frozen shared evidence digest.",
        )
    return synthesis


def _validate_synthesis(
    facts: DeriveFacts,
    analysis: dict[str, Any],
    lenses: list[dict[str, Any]],
    candidate_ids: set[str],
    shared_sha: str,
    issue_fit_status: str,
) -> None:
    synthesis = _synthesis_receipt(facts, analysis, lenses, shared_sha)
    if synthesis is None:
        return
    union = synthesis.get("candidate_union_ids")
    if (
        not isinstance(union, list)
        or len(union) != len(set(map(str, union)))
        or set(map(str, union)) != candidate_ids
    ):
        _finding(
            facts,
            "derive_synthesis_candidate_union_mismatch",
            "Synthesis candidate union must exactly equal the validated lens candidate union.",
        )
    if synthesis.get("candidate_union_sha256") != _canonical_sha256(
        sorted(candidate_ids)
    ):
        _finding(
            facts,
            "derive_synthesis_candidate_union_digest_invalid",
            "Synthesis candidate-union digest is invalid.",
        )
    outcome = str(synthesis.get("selection_outcome") or "")
    if outcome not in DERIVE_SELECTION_OUTCOMES:
        _finding(
            facts,
            "derive_selection_outcome_invalid",
            "Synthesis selection outcome is not canonical.",
            {"selection_outcome": outcome},
        )
    disposition = str(synthesis.get("pack_disposition") or "")
    if disposition not in CANONICAL_PACK_DISPOSITIONS:
        _finding(
            facts,
            "derive_synthesis_pack_disposition_invalid",
            "Synthesis pack disposition is outside the canonical enum.",
        )
    selected_id = str(synthesis.get("selected_candidate_id") or "")
    candidates = _candidate_rows(lenses)
    if outcome == "selected" and selected_id not in candidate_ids:
        _finding(
            facts,
            "derive_synthesis_selected_outside_union",
            "Selected candidate must be a member of the three-lens union.",
            {"selected_candidate_id": selected_id},
        )
    if outcome != "selected" and selected_id:
        _finding(
            facts,
            "derive_synthesis_nonselected_candidate_present",
            "Terminal, wait, and escalation synthesis cannot select a candidate ID.",
        )
    selected = candidates.get(selected_id, {})
    if selected and str(selected.get("actionability")) != "actionable":
        _finding(
            facts,
            "derive_synthesis_selected_candidate_not_actionable",
            "Synthesis cannot select a blocked or unverified candidate.",
        )
    if (
        selected
        and issue_fit_status == "unavailable"
        and selected.get("issue_derived") is True
    ):
        _finding(
            facts,
            "derive_issue_candidate_selected_without_fit",
            "Unavailable issue-fit degrades only issue-derived candidates and forbids selecting one.",
        )
    if selected and str(selected.get("pack_disposition") or "") != disposition:
        _finding(
            facts,
            "derive_synthesis_candidate_disposition_mismatch",
            "Synthesis must preserve the selected candidate's canonical pack disposition.",
        )
    actionable = [
        row
        for row in candidates.values()
        if row.get("actionability") == "actionable"
        and not (issue_fit_status == "unavailable" and row.get("issue_derived") is True)
    ]
    if outcome != "selected" and actionable:
        _finding(
            facts,
            "derive_nonselected_outcome_with_actionable_candidate",
            "Terminal or escalation outcome is invalid while an actionable candidate remains.",
        )
    for field, expected in (
        ("selection_outcome", outcome),
        ("pack_disposition", disposition),
        ("selected_candidate_id", selected_id),
    ):
        observed = str(facts.result.get(field) or "")
        if observed != expected:
            _finding(
                facts,
                "derive_synthesis_top_level_mismatch",
                "Top-level derive decision must exactly echo synthesis.",
                {"field": field},
            )


def check_analysis_contract(facts: DeriveFacts) -> None:
    result = facts.result
    if result.get("derive_contract_version") != 2:
        _finding(
            facts,
            "derive_analysis_contract_version_missing",
            "Derive publication requires derive_contract_version=2.",
        )
    analysis = result.get("improvement_analysis_manifest")
    if not isinstance(analysis, dict):
        _finding(
            facts,
            "derive_improvement_analysis_manifest_missing",
            "Derive publication requires the frozen three-agent analysis manifest.",
        )
        return
    if analysis.get("schema_version") != 1:
        _finding(
            facts,
            "derive_improvement_analysis_schema_invalid",
            "Improvement analysis manifest requires schema_version=1.",
        )
    for code in validate_derive_advice_analysis(analysis):
        _finding(
            facts,
            code,
            "Active advice must be frozen into the shared manifest, assessed by all three lenses, and reconciled by the actual synthesis receipt.",
        )
    shared_sha, issue_fit_status = validate_shared_manifest(facts, analysis)
    lenses, candidate_ids = _validate_lenses(facts, analysis, shared_sha)
    _validate_synthesis(
        facts, analysis, lenses, candidate_ids, shared_sha, issue_fit_status
    )
