"""Immutable authority decision artifact verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._authority_artifact_io import (
    artifact_finding as _finding,
    authority_binding as _binding,
    read_bound_bytes as _read_bytes,
    read_bound_json as _read_json,
)
from ._authority_artifact_projection import (
    approval_projection as _expected_approval,
    axes_match as _axes_match,
    scope_projection as _expected_scope,
)
from .authority_boundary import canonical_sha256


DECISION_KEYS = {
    "schema_version",
    "artifact_kind",
    "decision_id",
    "request",
    "request_sha256",
    "evaluation_context",
    "evaluation_context_sha256",
    "decision",
    "reason_codes",
    "approval_projection",
    "selected_grants",
    "lineage_grants",
    "operation_manifest",
    "effective_authority_fingerprint",
    "evaluated_at",
}


def _read_decision(
    root: Path,
    packet: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    binding = (
        packet.get("decision_binding")
        if isinstance(packet.get("decision_binding"), dict)
        else {}
    )
    expected_ref = f".task/authorization/decisions/{binding.get('decision_id')}.json"
    return _read_json(
        root,
        _binding(binding.get("artifact_ref"), binding.get("artifact_sha256")),
        "decision",
        findings,
        expected_ref=expected_ref,
    )


def _decision_schema_is_valid(
    decision: dict[str, Any],
    findings: list[dict[str, Any]],
) -> bool:
    if (
        set(decision) != DECISION_KEYS
        or decision.get("schema_version") != 2
        or decision.get("artifact_kind") != "authority_decision"
    ):
        findings.append(
            _finding(
                "authority_owner_decision_schema_invalid",
                "Reopened authority decision does not match the closed owner contract.",
                "decision",
            )
        )
        return False
    return True


def _verify_request_evidence(
    root: Path,
    request: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    request = request if isinstance(request, dict) else {}
    request_context = (
        request.get("context") if isinstance(request.get("context"), dict) else {}
    )
    evidence_bindings = [
        request_context.get(field)
        for field in (
            "external_input_evidence",
            "risk_acceptance_evidence",
            "design_selection_evidence",
        )
        if request_context.get(field) is not None
    ]
    if len({canonical_sha256(item) for item in evidence_bindings}) != len(
        evidence_bindings
    ):
        findings.append(
            _finding(
                "authority_axes_evidence_conflated",
                "Separate decision axes cannot reuse one source binding.",
                "decision.request.context",
            )
        )
    for field in (
        "external_input_evidence",
        "risk_acceptance_evidence",
        "design_selection_evidence",
    ):
        if request_context.get(field) is not None:
            _read_bytes(
                root,
                request_context[field],
                f"request:{field}",
                findings,
                authorization_only=False,
            )


def _verify_goal_autonomy_source(
    root: Path,
    decision: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    evaluation = (
        decision.get("evaluation_context")
        if isinstance(decision.get("evaluation_context"), dict)
        else {}
    )
    envelope = (
        evaluation.get("goal_autonomy_envelope")
        if isinstance(evaluation.get("goal_autonomy_envelope"), dict)
        else {}
    )
    if envelope.get("source_binding") is not None:
        _read_bytes(
            root,
            envelope["source_binding"],
            "goal_autonomy_source",
            findings,
            authorization_only=False,
        )


def _verify_subject(
    root: Path,
    request: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    subject = request.get("subject") if isinstance(request.get("subject"), dict) else {}
    subject_ref = subject.get("ref")
    if isinstance(subject_ref, str):
        subject_path = Path(subject_ref)
        if subject_path.is_absolute() or ".." in subject_path.parts:
            findings.append(
                _finding(
                    "authority_subject_path_unsafe",
                    "Authority subject cannot escape the workspace.",
                    "decision.request.subject",
                )
            )
        elif (root / subject_path).exists() or (root / subject_path).is_symlink():
            _read_bytes(
                root,
                _binding(subject_ref, subject.get("digest")),
                "subject",
                findings,
                authorization_only=False,
            )


def _decision_comparisons(
    decision: dict[str, Any],
    packet: dict[str, Any],
    binding: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, tuple[Any, Any]]:
    core = {key: value for key, value in decision.items() if key != "decision_id"}
    expected_id = "authd-" + canonical_sha256(core)[:24]
    comparisons = {
        "decision_id": (decision.get("decision_id"), binding.get("decision_id")),
        "derived_decision_id": (decision.get("decision_id"), expected_id),
        "request_id": (request.get("request_id"), binding.get("request_id")),
        "request_sha256": (
            decision.get("request_sha256"),
            binding.get("request_sha256"),
        ),
        "request_body_sha256": (
            decision.get("request_sha256"),
            canonical_sha256(request),
        ),
        "evaluation_context_sha256": (
            decision.get("evaluation_context_sha256"),
            canonical_sha256(decision.get("evaluation_context")),
        ),
        "decision": (decision.get("decision"), binding.get("decision")),
        "fingerprint": (
            decision.get("effective_authority_fingerprint"),
            binding.get("effective_authority_fingerprint"),
        ),
        "operation": (
            {
                key: request.get(key)
                for key in (
                    "skill_id",
                    "skill_version",
                    "operation_id",
                    "operation_version",
                )
            },
            {
                key: (packet.get("operation_binding") or {}).get(key)
                for key in (
                    "skill_id",
                    "skill_version",
                    "operation_id",
                    "operation_version",
                )
            },
        ),
        "mutation_class": (
            request.get("mutation_class"),
            (packet.get("operation_binding") or {}).get("mutation_class"),
        ),
        "subject": (request.get("subject"), packet.get("subject")),
        "scope": (_expected_scope(request), packet.get("scope")),
        "selected_grants": (
            decision.get("selected_grants"),
            packet.get("selected_grants"),
        ),
        "lineage_grants": (
            decision.get("lineage_grants"),
            packet.get("lineage_grants"),
        ),
        "approval_projection": (
            decision.get("approval_projection"),
            packet.get("approval_projection"),
        ),
        "approval_projection_derivation": (
            decision.get("approval_projection"),
            _expected_approval(decision),
        ),
        "composition_receipt": (
            request.get("composition_receipt"),
            packet.get("composition_receipt"),
        ),
    }
    operation = (
        packet.get("operation_binding")
        if isinstance(packet.get("operation_binding"), dict)
        else {}
    )
    manifest = decision.get("operation_manifest")
    packet_manifest = (
        None
        if operation.get("manifest_ref") is None
        and operation.get("manifest_sha256") is None
        else _binding(operation.get("manifest_ref"), operation.get("manifest_sha256"))
    )
    comparisons["operation_manifest"] = (manifest, packet_manifest)
    return comparisons


def _decision_mismatches(
    decision: dict[str, Any],
    packet: dict[str, Any],
    comparisons: dict[str, tuple[Any, Any]],
) -> list[str]:
    mismatches = sorted(
        name for name, pair in comparisons.items() if pair[0] != pair[1]
    )
    if not _axes_match(decision, packet.get("axes")):
        mismatches.append("axes")
    approval = decision.get("approval_projection")
    if isinstance(approval, dict):
        approval_core = {
            key: value for key, value in approval.items() if key != "projection_id"
        }
        if (
            approval.get("projection_id")
            != "authp-" + canonical_sha256(approval_core)[:24]
        ):
            mismatches.append("approval_projection_id")
    return mismatches


def _report_mismatches(
    mismatches: list[str],
    findings: list[dict[str, Any]],
) -> None:
    if mismatches:
        findings.append(
            {
                "code": "authority_owner_decision_mismatch",
                "message": "Authority packet does not exactly project the reopened owner decision.",
                "evidence": {"fields": mismatches},
            }
        )


def verify_decision(
    root: Path,
    packet: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    binding = (
        packet.get("decision_binding")
        if isinstance(packet.get("decision_binding"), dict)
        else {}
    )
    decision = _read_decision(root, packet, findings)
    if decision is None or not _decision_schema_is_valid(decision, findings):
        return None
    request = (
        decision.get("request") if isinstance(decision.get("request"), dict) else {}
    )
    _verify_request_evidence(root, request, findings)
    _verify_goal_autonomy_source(root, decision, findings)
    _verify_subject(root, request, findings)
    comparisons = _decision_comparisons(decision, packet, binding, request)
    _report_mismatches(
        _decision_mismatches(decision, packet, comparisons),
        findings,
    )
    composition = request.get("composition_receipt")
    if composition is not None:
        _read_json(root, composition, "composition_receipt", findings)
    return decision


__all__ = ("verify_decision",)
