from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .decision_identity_dimensions import parse_decision_identity


LINEAGE_STATUSES = frozenset(
    {
        "all_current",
        "implementation_ahead_of_artifact",
        "artifact_ahead_of_review",
        "no_domain_artifact",
        "not_applicable",
    }
)
LINEAGE_PATHS = (
    "decision_freshness_lineage",
    "decision_freshness_gate.lineage",
    "artifact_revision_lineage",
    "artifact_lineage",
)


@dataclass(frozen=True, slots=True)
class FreshnessLineageAssessment:
    declared: bool
    applicability: str
    status: str
    issues: tuple[str, ...]
    measurement_valid: bool
    no_impact_valid: bool
    evidence_required: str

    @property
    def evidence_valid(self) -> bool:
        if self.evidence_required == "measurement":
            return self.measurement_valid
        if self.evidence_required == "measurement_or_no_impact":
            return self.measurement_valid or self.no_impact_valid
        return True


def canonical_receipt_sha256(receipt: dict[str, Any]) -> str:
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _full_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower().removeprefix("sha256:")
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _opaque(value: Any, *, maximum: int = 512) -> bool:
    return bool(
        isinstance(value, str)
        and 0 < len(value.strip()) <= maximum
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _deep_declared(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _lineage(data: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    for path in LINEAGE_PATHS:
        declared, value = _deep_declared(data, path)
        if declared:
            return True, value if isinstance(value, dict) else {"_malformed": value}
    direct_fields = {
        "latest_implementation_revision_id",
        "latest_compatible_deliverable_revision_id",
        "latest_semantically_reviewed_deliverable_revision_id",
        "lineage_status",
    }
    if direct_fields.intersection(data):
        return True, data
    return False, {}


def _decision_subject(data: dict[str, Any], lineage: dict[str, Any]) -> tuple[Any, Any]:
    identity: Any = data.get("decision_artifact_ref") or data.get("decision_identity")
    projection = parse_decision_identity(identity)
    if projection.explicit:
        return (
            projection.subject_values.get("decision_subject_id"),
            projection.subject_values.get("subject_digest"),
        )
    if isinstance(identity, dict):
        return identity.get("artifact_id"), identity.get("artifact_sha256")
    return lineage.get("decision_subject_id"), lineage.get("decision_subject_digest")


def _identity_evidence_requirement(
    data: dict[str, Any], lineage: dict[str, Any]
) -> str:
    identity: Any = data.get("decision_artifact_ref") or data.get("decision_identity")
    projection = parse_decision_identity(identity)
    if projection.explicit:
        if projection.dimension_statuses.get("producer_run") == "applicable":
            return "measurement"
        if any(
            projection.dimension_statuses.get(name) == "applicable"
            for name in ("body_fingerprint", "production_lane")
        ):
            return "measurement_or_no_impact"
        return "none"
    requested = str(lineage.get("fresh_evidence_requirement") or "").strip().lower()
    return (
        requested
        if requested in {"none", "measurement", "measurement_or_no_impact"}
        else "none"
    )


def _identity_measurement_echo(data: dict[str, Any]) -> tuple[Any, Any, bool]:
    identity: Any = data.get("decision_artifact_ref") or data.get("decision_identity")
    projection = parse_decision_identity(identity)
    if not projection.explicit:
        return None, None, False
    return (
        projection.dimension_values.get("producer_run"),
        projection.dimension_values.get("body_fingerprint"),
        any(
            projection.dimension_statuses.get(name) == "applicable"
            for name in ("body_fingerprint", "production_lane", "producer_run")
        ),
    )


def _receipt_valid(
    receipt: Any,
    *,
    kind: str,
    subject_id: Any,
    subject_digest: Any,
    implementation_revision_id: Any,
    expected_run_id: Any = None,
    expected_output_fingerprint: Any = None,
) -> bool:
    if not isinstance(receipt, dict):
        return False
    common_valid = all(
        (
            _opaque(receipt.get("decision_subject_id")),
            receipt.get("decision_subject_id") == subject_id,
            _full_sha256(receipt.get("decision_subject_digest")),
            str(receipt.get("decision_subject_digest")).removeprefix("sha256:").lower()
            == str(subject_digest or "").removeprefix("sha256:").lower(),
            receipt.get("input_revision_id") == implementation_revision_id,
            _full_sha256(receipt.get("receipt_sha256")),
            str(receipt.get("receipt_sha256")).removeprefix("sha256:").lower()
            == canonical_receipt_sha256(receipt),
        )
    )
    if not common_valid:
        return False
    if kind == "measurement":
        return bool(
            _opaque(receipt.get("run_id"))
            and _full_sha256(receipt.get("output_fingerprint"))
            and (expected_run_id is None or receipt.get("run_id") == expected_run_id)
            and (
                expected_output_fingerprint is None
                or str(receipt.get("output_fingerprint"))
                .removeprefix("sha256:")
                .lower()
                == str(expected_output_fingerprint).removeprefix("sha256:").lower()
            )
        )
    return bool(
        _opaque(receipt.get("predicate_id"))
        and str(receipt.get("evaluation_status") or "").strip().lower() == "pass"
        and _full_sha256(receipt.get("evidence_digest"))
    )


def _relation_receipt_valid(
    receipt: Any,
    *,
    relation_kind: str,
    subject_id: Any,
    subject_digest: Any,
) -> bool:
    if not isinstance(receipt, dict):
        return False
    required_keys = {
        "contract_version",
        "relation_kind",
        "decision_subject_id",
        "decision_subject_digest",
        "evidence_digest",
        "receipt_sha256",
    }
    relation_keys = {
        "compatible_deliverable_for_implementation": {
            "implementation_revision_id",
            "deliverable_revision_id",
        },
        "semantic_review_of_deliverable": {
            "deliverable_revision_id",
            "review_revision_id",
        },
    }
    expected_keys = required_keys | relation_keys[relation_kind]
    if set(receipt) != expected_keys:
        return False
    return bool(
        receipt.get("contract_version") == 1
        and receipt.get("relation_kind") == relation_kind
        and receipt.get("decision_subject_id") == subject_id
        and _opaque(subject_id)
        and _full_sha256(receipt.get("decision_subject_digest"))
        and str(receipt.get("decision_subject_digest")).removeprefix("sha256:").lower()
        == str(subject_digest or "").removeprefix("sha256:").lower()
        and all(_opaque(receipt.get(key)) for key in relation_keys[relation_kind])
        and _full_sha256(receipt.get("evidence_digest"))
        and _full_sha256(receipt.get("receipt_sha256"))
        and str(receipt.get("receipt_sha256")).removeprefix("sha256:").lower()
        == canonical_receipt_sha256(receipt)
    )


def _status_issues(
    lineage: dict[str, Any],
    applicability: str,
    status: str,
    *,
    subject_id: Any,
    subject_digest: Any,
) -> list[str]:
    implementation = lineage.get("latest_implementation_revision_id")
    deliverable = lineage.get("latest_compatible_deliverable_revision_id")
    reviewed = lineage.get("latest_semantically_reviewed_deliverable_revision_id")
    implementation_relation = lineage.get("implementation_deliverable_relation_receipt")
    review_relation = lineage.get("deliverable_review_relation_receipt")
    issues: list[str] = []
    if applicability == "not_applicable":
        if status != "not_applicable" or any(
            value is not None
            for value in (
                implementation,
                deliverable,
                reviewed,
                implementation_relation,
                review_relation,
            )
        ):
            issues.append("not_applicable_projection")
        return issues
    if applicability != "applicable":
        return ["applicability"]
    if status not in LINEAGE_STATUSES - {"not_applicable"}:
        issues.append("lineage_status")
        return issues
    if not _opaque(implementation):
        issues.append("latest_implementation_revision_id")
    implementation_relation_valid = _relation_receipt_valid(
        implementation_relation,
        relation_kind="compatible_deliverable_for_implementation",
        subject_id=subject_id,
        subject_digest=subject_digest,
    )
    review_relation_valid = _relation_receipt_valid(
        review_relation,
        relation_kind="semantic_review_of_deliverable",
        subject_id=subject_id,
        subject_digest=subject_digest,
    )
    if status == "all_current":
        if not (_opaque(deliverable) and _opaque(reviewed)):
            issues.append("current_revision_ids")
        if not implementation_relation_valid:
            issues.append("implementation_deliverable_relation_receipt")
        elif (
            implementation_relation.get("implementation_revision_id") != implementation
            or implementation_relation.get("deliverable_revision_id") != deliverable
        ):
            issues.append("implementation_deliverable_relation_binding")
        if not review_relation_valid:
            issues.append("deliverable_review_relation_receipt")
        elif (
            review_relation.get("deliverable_revision_id") != deliverable
            or reviewed != deliverable
        ):
            issues.append("deliverable_review_relation_binding")
    elif status == "implementation_ahead_of_artifact":
        if not (_opaque(deliverable) and _opaque(reviewed)):
            issues.append("stale_revision_ids")
        if not implementation_relation_valid:
            issues.append("implementation_deliverable_relation_receipt")
        elif (
            implementation_relation.get("implementation_revision_id") == implementation
            or implementation_relation.get("deliverable_revision_id") != deliverable
        ):
            issues.append("implementation_ahead_relation_binding")
        if not review_relation_valid:
            issues.append("deliverable_review_relation_receipt")
        elif (
            review_relation.get("deliverable_revision_id") != deliverable
            or reviewed != deliverable
        ):
            issues.append("deliverable_review_relation_binding")
    elif status == "artifact_ahead_of_review":
        if not (_opaque(deliverable) and _opaque(reviewed)):
            issues.append("stale_revision_ids")
        if not implementation_relation_valid:
            issues.append("implementation_deliverable_relation_receipt")
        elif (
            implementation_relation.get("implementation_revision_id") != implementation
            or implementation_relation.get("deliverable_revision_id") != deliverable
        ):
            issues.append("implementation_deliverable_relation_binding")
        if not review_relation_valid:
            issues.append("deliverable_review_relation_receipt")
        elif (
            review_relation.get("deliverable_revision_id") != reviewed
            or reviewed == deliverable
        ):
            issues.append("artifact_ahead_review_relation_binding")
    elif status == "no_domain_artifact" and any(
        value is not None
        for value in (deliverable, reviewed, implementation_relation, review_relation)
    ):
        issues.append("no_domain_artifact_relation")
    return issues


def assess_decision_freshness_lineage(
    data: dict[str, Any],
) -> FreshnessLineageAssessment:
    declared, lineage = _lineage(data)
    if not declared:
        return FreshnessLineageAssessment(False, "", "", (), False, False, "none")
    if "_malformed" in lineage:
        return FreshnessLineageAssessment(
            True, "", "", ("lineage",), False, False, "none"
        )
    applicability = str(lineage.get("applicability") or "").strip().lower()
    status = (
        str(lineage.get("lineage_status") or lineage.get("status") or "")
        .strip()
        .lower()
    )
    subject_id, subject_digest = _decision_subject(data, lineage)
    issues = _status_issues(
        lineage,
        applicability,
        status,
        subject_id=subject_id,
        subject_digest=subject_digest,
    )
    expected_run_id, expected_output_fingerprint, explicit_dimensions = (
        _identity_measurement_echo(data)
    )
    if applicability == "not_applicable" and explicit_dimensions:
        issues.append("not_applicable_with_applicable_decision_dimension")
    if applicability == "applicable":
        if lineage.get("decision_subject_id") != subject_id or not _opaque(subject_id):
            issues.append("decision_subject_id")
        lineage_digest = lineage.get("decision_subject_digest")
        if not _full_sha256(lineage_digest) or not _full_sha256(subject_digest):
            issues.append("decision_subject_digest")
        elif (
            str(lineage_digest).removeprefix("sha256:").lower()
            != str(subject_digest).removeprefix("sha256:").lower()
        ):
            issues.append("decision_subject_digest_binding")
    requirement = _identity_evidence_requirement(data, lineage)
    implementation = lineage.get("latest_implementation_revision_id")
    measurement_valid = _receipt_valid(
        lineage.get("fresh_measurement_receipt"),
        kind="measurement",
        subject_id=subject_id,
        subject_digest=subject_digest,
        implementation_revision_id=implementation,
        expected_run_id=expected_run_id,
        expected_output_fingerprint=expected_output_fingerprint,
    )
    no_impact_valid = _receipt_valid(
        lineage.get("no_impact_receipt"),
        kind="no_impact",
        subject_id=subject_id,
        subject_digest=subject_digest,
        implementation_revision_id=implementation,
    )
    return FreshnessLineageAssessment(
        True,
        applicability,
        status,
        tuple(sorted(set(issues))),
        measurement_valid,
        no_impact_valid,
        requirement,
    )


__all__ = (
    "FreshnessLineageAssessment",
    "LINEAGE_STATUSES",
    "assess_decision_freshness_lineage",
    "canonical_receipt_sha256",
)
