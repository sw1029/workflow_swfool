from __future__ import annotations

from typing import Any

from ...decision_identity_dimensions import (
    expected_dimension_echo,
    expected_subject_echo,
    parse_decision_identity,
)
from ...derive_advice import canonical_sha256
from ...receipts import _full_sha256
from .shared import add
from .state import DeriveFacts


DECISION_IDENTITY_FIELDS = (
    "cycle_id",
    "task_id",
    "attempt_id",
    "artifact_id",
    "artifact_sha256",
    "body_projection_fingerprint",
    "production_lane_identity",
    "input_state_fingerprint",
)
ISSUE_FIT_VALUES = {"available", "not_applicable", "unavailable"}


def _nonempty_strings(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _finding(
    facts: DeriveFacts,
    code: str,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> None:
    add(facts.findings, "block", code, message, evidence)


def _validate_issue_fit(facts: DeriveFacts, evidence_manifest: dict[str, Any]) -> str:
    issue_fit = evidence_manifest.get("issue_fit")
    if not isinstance(issue_fit, dict):
        _finding(
            facts,
            "derive_issue_fit_contract_missing",
            "The shared evidence manifest must include typed issue-fit status.",
        )
        return ""
    status = str(issue_fit.get("status") or "").strip().lower()
    if status not in ISSUE_FIT_VALUES:
        _finding(
            facts,
            "derive_issue_fit_status_invalid",
            "Issue-fit status is not canonical.",
            {"status": status},
        )
    if status == "unavailable" and (
        not str(issue_fit.get("unavailable_reason") or "").strip()
        or not _nonempty_strings(issue_fit.get("evidence_ids"))
    ):
        _finding(
            facts,
            "derive_issue_fit_unavailable_unbound",
            "Unavailable issue-fit may degrade issue-derived candidates only when reason and evidence IDs are bound.",
        )
    return status


def _validate_adapter_context(facts: DeriveFacts, manifest: dict[str, Any]) -> None:
    applicability = str(manifest.get("adapter_applicability") or "").strip().lower()
    if applicability == "not_applicable":
        if (
            str(manifest.get("adapter_registry_status") or "").strip().lower()
            != "no_registered_adapter"
            or not str(manifest.get("adapter_not_applicable_reason") or "").strip()
            or not _nonempty_strings(manifest.get("adapter_registry_evidence_ids"))
        ):
            _finding(
                facts,
                "derive_adapter_not_applicable_unproven",
                "Adapter decision input may be not-applicable only for an evidenced empty adapter registry.",
            )
        return
    if applicability != "required":
        _finding(
            facts,
            "derive_adapter_applicability_invalid",
            "Adapter applicability must be required or not_applicable.",
        )
        return
    context = manifest.get("adapter_decision_context")
    seal = manifest.get("adapter_post_use_seal")
    if not isinstance(context, dict):
        _finding(
            facts,
            "derive_adapter_decision_context_missing",
            "Required adapter decision context is missing.",
        )
        return
    if not isinstance(seal, dict):
        _finding(
            facts,
            "derive_adapter_post_use_seal_missing",
            "Required adapter post-use seal is missing.",
        )
        return
    packet = context.get("packet")
    if (
        not isinstance(packet, dict)
        or not str(context.get("packet_ref") or "").strip()
        or not _full_sha256(context.get("packet_sha256"))
        or context.get("packet_sha256") != canonical_sha256(packet)
    ):
        _finding(
            facts,
            "derive_adapter_decision_context_receipt_invalid",
            "Adapter decision context must bind a referenced packet and canonical digest.",
        )
        return
    static_validation = (
        packet.get("static_validation")
        if isinstance(packet.get("static_validation"), dict)
        else {}
    )
    load_preflight = (
        packet.get("load_preflight")
        if isinstance(packet.get("load_preflight"), dict)
        else {}
    )
    candidate_projection = (
        packet.get("candidate_projection")
        if isinstance(packet.get("candidate_projection"), dict)
        else {}
    )
    readiness = (
        static_validation.get("status") == "pass"
        and load_preflight.get("status") == "pass"
        and candidate_projection.get("status") == "eligible"
        and candidate_projection.get("eligible") is True
    )
    if not readiness:
        _finding(
            facts,
            "derive_adapter_decision_context_not_pass",
            "Adapter static, load, and candidate-projection states must pass before agent fanout.",
        )
    consumers = packet.get("required_consumer_ids")
    if (
        packet.get("phase") != "derive"
        or not isinstance(consumers, list)
        or "derive-improvement-task" not in consumers
    ):
        _finding(
            facts,
            "derive_adapter_consumer_phase_mismatch",
            "Adapter decision context must target the derive-improvement-task consumer in derive phase.",
        )
    if (
        str(seal.get("consumer_id") or "") != "derive-improvement-task"
        or seal.get("value_consumed_by_decision") is not True
    ):
        _finding(
            facts,
            "derive_adapter_post_use_seal_invalid",
            "Adapter seal must bind derive-improvement-task and consumed decision value.",
        )
    identity = packet.get("decision_identity")
    if not isinstance(identity, dict):
        _finding(
            facts,
            "derive_adapter_decision_identity_missing",
            "Adapter decision context must carry exact decision identity.",
        )
        return
    decision_ref = manifest.get("decision_artifact_ref")
    explicit_projection = parse_decision_identity(decision_ref)
    if explicit_projection.explicit:
        expected_echo = {
            **expected_subject_echo(decision_ref),
            "dimension_values": expected_dimension_echo(decision_ref),
        }
        mismatches = []
        if identity != decision_ref:
            mismatches.append("decision_identity")
        if seal.get("decision_identity_echo") != expected_echo:
            mismatches.append("decision_identity_echo")
        if mismatches:
            _finding(
                facts,
                "derive_adapter_post_use_binding_mismatch",
                "Adapter context and post-use seal must bind the exact subject and only applicable decision dimensions.",
                {"fields": mismatches},
            )
        _validate_adapter_packet_hashes(facts, packet, seal)
        return
    mismatches = [
        field
        for field in DECISION_IDENTITY_FIELDS
        if identity.get(field) != manifest.get(field)
        or seal.get(field) != manifest.get(field)
    ]
    _validate_adapter_packet_hashes(facts, packet, seal, mismatches)


def _validate_adapter_packet_hashes(
    facts: DeriveFacts,
    packet: dict[str, Any],
    seal: dict[str, Any],
    mismatches: list[str] | None = None,
) -> None:
    mismatches = list(mismatches or [])
    revision = (
        packet.get("adapter_revision")
        if isinstance(packet.get("adapter_revision"), dict)
        else {}
    )
    packet_hashes = {
        "adapter_revision_sha256": revision.get("adapter_revision_sha256"),
        "hook_results_sha256": packet.get("hook_results_sha256"),
    }
    mismatches.extend(
        field
        for field, value in packet_hashes.items()
        if value != seal.get(field) or not _full_sha256(value)
    )
    post_use = packet.get("post_use_decision_receipt")
    if (
        not isinstance(post_use, dict)
        or post_use.get("status") != "pass"
        or post_use.get("receipt_sha256") != seal.get("receipt_sha256")
    ):
        mismatches.append("post_use_decision_receipt")
    if mismatches:
        _finding(
            facts,
            "derive_adapter_post_use_binding_mismatch",
            "Adapter context, post-use seal, and shared evidence identity do not match.",
            {"fields": sorted(set(mismatches))},
        )
    receipt_sha = seal.get("receipt_sha256")
    if not _full_sha256(receipt_sha) or receipt_sha != canonical_sha256(
        {key: value for key, value in seal.items() if key != "receipt_sha256"}
    ):
        _finding(
            facts,
            "derive_adapter_post_use_receipt_invalid",
            "Adapter post-use seal digest is missing or invalid.",
        )


def validate_shared_manifest(
    facts: DeriveFacts, analysis: dict[str, Any]
) -> tuple[str, str]:
    manifest = analysis.get("shared_evidence_manifest")
    supplied_sha = str(analysis.get("shared_evidence_manifest_sha256") or "")
    if not isinstance(manifest, dict):
        _finding(
            facts,
            "derive_shared_evidence_manifest_missing",
            "Freeze one shared evidence manifest before agent fanout.",
        )
        return "", ""
    if supplied_sha != canonical_sha256(manifest):
        _finding(
            facts,
            "derive_shared_evidence_manifest_hash_mismatch",
            "Shared evidence manifest digest does not match its body.",
        )
    explicit_projection = parse_decision_identity(manifest.get("decision_artifact_ref"))
    if explicit_projection.explicit:
        if explicit_projection.issues:
            _finding(
                facts,
                "derive_shared_evidence_identity_incomplete",
                "Shared evidence manifest has an invalid explicit subject or applicability binding.",
                {"fields": list(explicit_projection.issues)},
            )
        if explicit_projection.subject_values.get("freshness_status") != "current":
            _finding(
                facts,
                "derive_shared_evidence_identity_not_current",
                "Derive fanout cannot select from a stale, conflicted, or unverified decision subject.",
                {
                    "freshness_status": explicit_projection.subject_values.get(
                        "freshness_status"
                    )
                },
            )
        for field in ("cycle_id", "task_id", "attempt_id", "input_state_fingerprint"):
            value = manifest.get(field)
            if not isinstance(value, str) or not value.strip():
                _finding(
                    facts,
                    "derive_shared_evidence_identity_incomplete",
                    "Shared evidence manifest lacks cycle/attempt identity around the exact decision subject.",
                    {"fields": [field]},
                )
        if not _full_sha256(manifest.get("input_state_fingerprint")):
            _finding(
                facts,
                "derive_shared_evidence_identity_incomplete",
                "Shared evidence input-state fingerprint must be a full SHA-256.",
                {"fields": ["input_state_fingerprint"]},
            )
    else:
        missing = [
            field
            for field in DECISION_IDENTITY_FIELDS
            if not isinstance(manifest.get(field), str)
            or not manifest.get(field, "").strip()
        ]
        for field in (
            "artifact_sha256",
            "body_projection_fingerprint",
            "input_state_fingerprint",
        ):
            if field not in missing and not _full_sha256(manifest.get(field)):
                missing.append(field)
        if missing:
            _finding(
                facts,
                "derive_shared_evidence_identity_incomplete",
                "Shared evidence manifest lacks exact decision identity.",
                {"fields": sorted(set(missing))},
            )
    issue_fit_status = _validate_issue_fit(facts, manifest)
    _validate_adapter_context(facts, manifest)
    return supplied_sha, issue_fit_status


__all__ = ("validate_shared_manifest",)
