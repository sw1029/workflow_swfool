from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import resolve_workspace_path
from .canonical import sha256_file
from .contracts import DECISION_CLASSES
from .contracts import MUTATION_CLASSES
from .contracts import RISK_TIERS
from .contracts import risk_value


EVALUATION_CONTEXT_KEYS = {
    "schema_version",
    "context_kind",
    "session_ceiling",
    "goal_autonomy_envelope",
}
SESSION_KEYS = {"capabilities", "risk_ceiling", "mutation_classes", "evidence_id"}
ENVELOPE_KEYS = {
    "envelope_id",
    "capabilities",
    "risk_ceiling",
    "decision_classes",
    "subjects",
    "operations",
    "source_binding",
}


def _closed(value: dict[str, Any], expected: set[str], label: str) -> None:
    extra = sorted(set(value) - expected)
    missing = sorted(expected - set(value))
    if extra or missing:
        raise SystemExit(f"{label} has unknown={extra} missing={missing}.")


def _exact_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{label} must be a non-empty list.")
    normalized = sorted(set(str(item) for item in value))
    if len(normalized) != len(value) or any(
        not item or "*" in item for item in normalized
    ):
        raise SystemExit(f"{label} must contain unique exact values without wildcards.")
    return normalized


def validate_evaluation_context(root: Path, value: dict[str, Any]) -> dict[str, Any]:
    _closed(value, EVALUATION_CONTEXT_KEYS, "evaluation context")
    if value["schema_version"] != 2 or value["context_kind"] != "authority_evaluation":
        raise SystemExit(
            "Evaluation context requires schema_version=2 and context_kind=authority_evaluation."
        )
    session = value["session_ceiling"]
    envelope = value["goal_autonomy_envelope"]
    if not isinstance(session, dict) or not isinstance(envelope, dict):
        raise SystemExit("Evaluation context axes must be objects.")
    _closed(session, SESSION_KEYS, "session_ceiling")
    _closed(envelope, ENVELOPE_KEYS, "goal_autonomy_envelope")
    mutation_classes = _exact_strings(
        session["mutation_classes"], "session_ceiling.mutation_classes"
    )
    if any(item not in MUTATION_CLASSES for item in mutation_classes):
        raise SystemExit("session_ceiling.mutation_classes contains an unknown enum.")
    decision_classes = _exact_strings(
        envelope["decision_classes"], "goal_autonomy_envelope.decision_classes"
    )
    if any(item not in DECISION_CLASSES for item in decision_classes):
        raise SystemExit(
            "goal_autonomy_envelope.decision_classes contains an unknown enum."
        )
    subjects = envelope["subjects"]
    operations = envelope["operations"]
    if (
        not isinstance(subjects, list)
        or not subjects
        or not all(isinstance(item, str) for item in subjects)
    ):
        raise SystemExit(
            "goal_autonomy_envelope.subjects must contain exact subject digests."
        )
    if (
        not isinstance(operations, list)
        or not operations
        or not all(isinstance(item, str) for item in operations)
    ):
        raise SystemExit(
            "goal_autonomy_envelope.operations must contain exact operation identities."
        )
    subjects = sorted(set(subjects))
    operations = sorted(set(operations))
    if len(subjects) != len(envelope["subjects"]) or len(operations) != len(
        envelope["operations"]
    ):
        raise SystemExit("Goal autonomy envelope scopes must be unique.")
    binding = envelope["source_binding"]
    if not isinstance(binding, dict) or set(binding) != {"ref", "sha256"}:
        raise SystemExit(
            "goal_autonomy_envelope.source_binding must contain ref and sha256."
        )
    source = resolve_workspace_path(root, binding["ref"], "goal autonomy source")
    if sha256_file(source) != binding["sha256"]:
        raise SystemExit("Goal autonomy source digest mismatch.")
    session_risk = str(session["risk_ceiling"])
    envelope_risk = str(envelope["risk_ceiling"])
    if session_risk not in RISK_TIERS or envelope_risk not in RISK_TIERS:
        raise SystemExit("Evaluation context risk ceilings are invalid.")
    evidence_id = str(session["evidence_id"] or "").strip()
    envelope_id = str(envelope["envelope_id"] or "").strip()
    if not evidence_id or not envelope_id:
        raise SystemExit("Evaluation context requires opaque session and envelope IDs.")
    return {
        "schema_version": 2,
        "context_kind": "authority_evaluation",
        "session_ceiling": {
            "capabilities": _exact_strings(
                session["capabilities"], "session_ceiling.capabilities"
            ),
            "risk_ceiling": session_risk,
            "mutation_classes": mutation_classes,
            "evidence_id": evidence_id,
        },
        "goal_autonomy_envelope": {
            "envelope_id": envelope_id,
            "capabilities": _exact_strings(
                envelope["capabilities"], "goal_autonomy_envelope.capabilities"
            ),
            "risk_ceiling": envelope_risk,
            "decision_classes": decision_classes,
            "subjects": subjects,
            "operations": operations,
            "source_binding": {
                "ref": str(binding["ref"]),
                "sha256": str(binding["sha256"]),
            },
        },
    }


def verify_request_evidence(root: Path, request: dict[str, Any]) -> None:
    for field in (
        "external_input_evidence",
        "risk_acceptance_evidence",
        "design_selection_evidence",
    ):
        binding = request["context"][field]
        if binding is None:
            continue
        path = resolve_workspace_path(root, binding["ref"], f"request.context.{field}")
        if sha256_file(path) != binding["sha256"]:
            raise SystemExit(f"request.context.{field} SHA-256 does not match.")


def context_decision(
    request: dict[str, Any], context: dict[str, Any]
) -> tuple[str | None, list[str]]:
    request_context = request["context"]
    external = request_context["external_input_status"]
    if external == "missing_supplyable":
        return "waiting_external_input", ["external_input_missing_supplyable"]
    if external == "missing_unsupplyable":
        return "waiting_external_input", [
            "external_input_unsupplyable_route_local_or_descope"
        ]
    if external == "unverified":
        return "classification_repair", ["external_input_availability_unverified"]
    if request_context["goal_truth_status"] == "blocked":
        return "blocked_by_goal_truth", ["goal_truth_blocks_subject_operation"]
    if request_context["goal_truth_status"] == "unverified":
        return "classification_repair", ["goal_truth_alignment_unverified"]
    intent = request["intent_type"]
    if intent == "supply_external_input":
        return "not_applicable", ["external_input_supply_is_not_authority_grant"]
    if intent == "ratify_goal_truth":
        return "approval_required", [
            "goal_truth_ratification_requires_goal_owner_decision"
        ]
    if intent == "accept_risk_or_cost":
        return "approval_required", ["risk_cost_acceptance_is_separate_from_authority"]
    if intent == "select_design_option":
        return "approval_required", ["design_selection_is_separate_from_authority"]
    if request_context["risk_acceptance_status"] == "unverified":
        return "classification_repair", ["risk_acceptance_status_unverified"]
    if (
        risk_value(request["risk_tier"]) >= risk_value("R2")
        and request_context["risk_acceptance_status"] == "unresolved"
    ):
        return "approval_required", ["risk_acceptance_unresolved"]
    if request_context["design_selection_status"] == "unverified":
        return "classification_repair", ["design_selection_status_unverified"]
    if (
        request["decision_class"] in {"D0", "D1"}
        and request_context["design_selection_status"] == "unresolved"
    ):
        return "approval_required", ["goal_or_design_decision_unresolved"]
    ceiling = context["session_ceiling"]
    envelope = context["goal_autonomy_envelope"]
    capabilities = set(request["required_capabilities"])
    if not capabilities.issubset(ceiling["capabilities"]):
        return "capability_unavailable", ["outside_session_capability_ceiling"]
    if not capabilities.issubset(envelope["capabilities"]):
        return "blocked_by_goal_truth", ["outside_goal_autonomy_capability_envelope"]
    if request["mutation_class"] not in ceiling["mutation_classes"]:
        return "capability_unavailable", ["outside_session_mutation_ceiling"]
    if risk_value(request["risk_tier"]) > risk_value(ceiling["risk_ceiling"]):
        return "capability_unavailable", ["outside_session_risk_ceiling"]
    if risk_value(request["risk_tier"]) > risk_value(envelope["risk_ceiling"]):
        return "blocked_by_goal_truth", ["outside_goal_autonomy_risk_ceiling"]
    operation_key = ":".join(
        (
            request["skill_id"],
            request["skill_version"],
            request["operation_id"],
            request["operation_version"],
        )
    )
    if (
        operation_key not in envelope["operations"]
        or request["subject"]["digest"] not in envelope["subjects"]
    ):
        return "blocked_by_goal_truth", ["outside_goal_autonomy_exact_scope"]
    if request["decision_class"] not in envelope["decision_classes"]:
        return "blocked_by_goal_truth", ["outside_goal_autonomy_decision_class"]
    return None, []
