from __future__ import annotations

import re
from pathlib import Path

from ..base import RuleContext, TargetContractRule
from ..common import add, non_empty, value_for


SHA256 = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


def criterion_is_semantically_non_empty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if not isinstance(value, dict) or not value:
        return False

    def has_content(item: object) -> bool:
        if isinstance(item, str):
            return bool(item.strip())
        if isinstance(item, dict):
            return bool(item) and any(has_content(nested) for nested in item.values())
        if isinstance(item, (list, tuple)):
            return any(has_content(nested) for nested in item)
        return item is not None

    return any(has_content(item) for item in value.values())


class AcceptanceRule(TargetContractRule):
    """Bind a normalized acceptance packet to exactly one active task revision."""

    targets = frozenset({"acceptance"})

    def check(self, context: RuleContext) -> None:
        result = context.result
        findings = context.findings
        task_id = str(value_for(result, "task_id") or "").strip()
        acceptance_id = str(value_for(result, "acceptance_id") or "").strip()
        acceptance_status = str(value_for(result, "acceptance_status") or "").strip().lower()
        criteria = value_for(result, "acceptance_criteria")
        blockers = value_for(result, "blockers")
        provenance = value_for(result, "acceptance_provenance")

        if acceptance_status not in {"normalized", "partial", "blocked", "needs_review"}:
            add(
                findings,
                "block",
                "invalid_acceptance_status",
                "Acceptance status must be normalized, partial, blocked, or needs_review.",
                {"acceptance_status": acceptance_status},
            )
        if not isinstance(criteria, list) or not criteria:
            add(findings, "block", "invalid_acceptance_criteria", "Acceptance criteria must be a non-empty JSON list.")
        elif any(not criterion_is_semantically_non_empty(criterion) for criterion in criteria):
            add(
                findings,
                "block",
                "semantically_empty_acceptance_criteria",
                "Every acceptance criterion must be a non-empty string or a structured object containing substantive values.",
            )
        if not isinstance(blockers, list):
            add(findings, "block", "acceptance_blockers_not_list", "Acceptance blockers must be an explicit JSON list.")
        elif any(not criterion_is_semantically_non_empty(blocker) for blocker in blockers):
            add(findings, "block", "semantically_empty_acceptance_blocker", "Acceptance blocker entries must contain substantive values.")
        elif acceptance_status == "normalized" and blockers:
            add(findings, "block", "normalized_acceptance_has_blockers", "Normalized acceptance cannot carry unresolved blockers.")
        elif acceptance_status in {"blocked", "needs_review"} and not blockers:
            add(findings, "block", "acceptance_status_without_blocker", "Blocked/needs_review acceptance requires at least one concrete blocker.")
        if not acceptance_id:
            add(findings, "block", "acceptance_id_missing", "Acceptance normalization must emit a stable `acceptance_id`.")
        if not isinstance(provenance, dict):
            add(
                findings,
                "block",
                "acceptance_provenance_missing",
                "Acceptance normalization must identify the exact task source revision it normalized.",
            )
            return

        required = ("source_task_id", "source_task_path", "source_task_fingerprint")
        missing = [field for field in required if not non_empty(provenance.get(field))]
        if missing:
            add(
                findings,
                "block",
                "acceptance_provenance_incomplete",
                "Acceptance provenance is missing task identity or revision evidence.",
                {"missing_fields": missing},
            )
        source_task_id = str(provenance.get("source_task_id") or "").strip()
        source_task_path = str(provenance.get("source_task_path") or "").strip()
        source_task_fingerprint = str(provenance.get("source_task_fingerprint") or "").strip()
        if task_id and source_task_id and source_task_id != task_id:
            add(
                findings,
                "block",
                "acceptance_task_identity_mismatch",
                "Acceptance provenance belongs to a different task; normalize the current task before governance.",
                {"task_id": task_id, "source_task_id": source_task_id},
            )
        if source_task_path and (Path(source_task_path).is_absolute() or ".." in Path(source_task_path).parts):
            add(findings, "block", "acceptance_source_task_path_invalid", "Acceptance source task path must be workspace-relative without parent traversal.")
        if source_task_fingerprint and not SHA256.fullmatch(source_task_fingerprint):
            add(findings, "block", "acceptance_source_task_fingerprint_invalid", "Acceptance source task fingerprint must be a full lowercase SHA-256 digest.")
