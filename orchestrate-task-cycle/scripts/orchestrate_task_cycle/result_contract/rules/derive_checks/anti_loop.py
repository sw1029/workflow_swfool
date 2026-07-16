from __future__ import annotations

from .shared import (
    HANDOFF_APPLICABILITY,
    _local_packet,
    _packet_scalar,
    _workspace_root,
    add,
    boolish,
    first_present,
    list_values,
    non_empty,
    selected_task_kind_value,
    value_for,
)
from .state import DeriveFacts


def _check_required_handoff(
    facts: DeriveFacts,
    handoff: dict[str, object],
    pending_selected_source: str,
    pending_selected_kind: str,
) -> None:
    context = facts.context
    result = facts.result
    findings = facts.findings
    required_handoff_fields = (
        "handoff_contract_version",
        "packet_ref",
        "packet_sha256",
        "artifact_id",
        "artifact_sha256",
        "artifact_family",
        "blocker_signature",
        "progress_verdict",
        "allowed_next_action_classes",
    )
    missing_handoff = [field for field in required_handoff_fields if not non_empty(handoff.get(field))]
    if missing_handoff:
        add(
            findings,
            "block",
            "derive_anti_loop_handoff_incomplete",
            "Required anti-loop handoff identity/action fields are incomplete.",
            {"missing_fields": missing_handoff},
        )
    expected_sha = str(handoff.get("packet_sha256") or "").removeprefix("sha256:").lower()
    if len(expected_sha) != 64 or any(character not in "0123456789abcdef" for character in expected_sha):
        add(findings, "block", "derive_anti_loop_handoff_hash_invalid", "Anti-loop handoff packet_sha256 must be a full lowercase SHA-256 digest.")
    local_packet = _local_packet(_workspace_root(context), handoff.get("packet_ref"))
    observed_sha = local_packet[0] if local_packet is not None else None
    if observed_sha is not None and observed_sha != expected_sha:
        add(
            findings,
            "block",
            "derive_anti_loop_handoff_hash_mismatch",
            "Anti-loop handoff packet hash does not match the referenced packet.",
        )
    elif observed_sha is None:
        verification_receipt = handoff.get("packet_verification_receipt")
        receipt_packet = (
            _local_packet(_workspace_root(context), verification_receipt.get("evidence_ref"))
            if isinstance(verification_receipt, dict)
            else None
        )
        receipt_evidence_sha = str(
            verification_receipt.get("evidence_sha256") or ""
        ).removeprefix("sha256:").lower() if isinstance(verification_receipt, dict) else ""
        receipt_valid = bool(
            isinstance(verification_receipt, dict)
            and str(verification_receipt.get("status") or "").lower() == "pass"
            and str(verification_receipt.get("packet_sha256") or "").removeprefix("sha256:").lower() == expected_sha
            and non_empty(verification_receipt.get("evidence_ref"))
            and receipt_packet is not None
            and receipt_evidence_sha == receipt_packet[0]
            and _packet_scalar(receipt_packet[1], "packet_sha256") == expected_sha
            and _packet_scalar(receipt_packet[1], "packet_ref") == handoff.get("packet_ref")
        )
        if not receipt_valid:
            add(
                findings,
                "block",
                "derive_anti_loop_handoff_ref_unverifiable",
                "Anti-loop packet reference requires either a verified workspace file or a trusted hash-bound store receipt.",
            )
    if local_packet is not None:
        packet_body = local_packet[1]
        scalar_bindings = (
            ("artifact_id", ("artifact_id", "current_artifact_id", "decision_artifact_ref.artifact_id")),
            ("artifact_sha256", ("artifact_sha256", "decision_artifact_ref.artifact_sha256")),
            ("artifact_family", ("artifact_family",)),
            ("blocker_signature", ("blocker_signature",)),
            ("progress_verdict", ("progress_verdict",)),
            ("hard_stop", ("hard_stop", "hard_stop_required")),
            ("terminal_state", ("terminal_state", "terminal_disposition")),
        )
        mismatched_scalars: list[str] = []
        for handoff_field, packet_paths in scalar_bindings:
            handoff_value = handoff.get(handoff_field)
            packet_value = _packet_scalar(packet_body, *packet_paths)
            if handoff_field in {"artifact_id", "artifact_sha256", "artifact_family", "blocker_signature", "progress_verdict"} and packet_value in (None, "", [], {}):
                mismatched_scalars.append(handoff_field)
            elif handoff_value not in (None, "", [], {}) and packet_value != handoff_value:
                mismatched_scalars.append(handoff_field)
        packet_actions = _packet_scalar(packet_body, "allowed_next_action_classes", "effective_allowed_dispositions")
        if packet_actions in (None, "", [], {}) or {
            str(item) for item in list_values(packet_actions)
        } != {str(item) for item in list_values(handoff.get("allowed_next_action_classes"))}:
            mismatched_scalars.append("allowed_next_action_classes")
        if mismatched_scalars:
            add(
                findings,
                "block",
                "derive_anti_loop_handoff_body_mismatch",
                "Anti-loop handoff scalar identity does not match the referenced authoritative packet body.",
                {"fields": sorted(set(mismatched_scalars))},
            )
    echoed_value = first_present(result, ["consumed_anti_loop_packet_sha256", "anti_loop_handoff_consumption.packet_sha256"])
    echoed_sha = str(echoed_value or "").removeprefix("sha256:").lower()
    if not echoed_value or echoed_sha != expected_sha:
        add(findings, "block", "derive_anti_loop_handoff_echo_mismatch", "Derive did not echo the consumed anti-loop packet identity.")
    allowed_actions = {str(item).strip().lower() for item in list_values(handoff.get("allowed_next_action_classes"))}
    selected_actions = {
        item
        for item in (
            pending_selected_source,
            pending_selected_kind,
            str(value_for(result, "progress_kind") or "").strip().lower(),
            str(value_for(result, "loop_breaker_disposition") or "").strip().lower(),
        )
        if item
    }
    if allowed_actions and selected_actions and not (allowed_actions & selected_actions):
        add(
            findings,
            "block",
            "derive_action_outside_anti_loop_handoff",
            "Selected derive action is outside the authoritative anti-loop handoff action classes.",
            {"selected": sorted(selected_actions), "allowed": sorted(allowed_actions)},
        )
    if boolish(handoff.get("hard_stop")) and str(value_for(result, "progress_kind") or "").lower() == "goal_productive":
        add(
            findings,
            "block",
            "derive_overrides_anti_loop_hard_stop",
            "Derive cannot upgrade a hash-bound anti-loop hard stop to goal_productive.",
        )


def check_anti_loop(facts: DeriveFacts) -> None:
    context = facts.context
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    result = context.result
    mode = context.mode
    findings = context.findings
    explicit_report_key_divergence = context.get("explicit_report_key_divergence", False)
    auto_report_key_divergences = context.get("auto_report_key_divergences", [])
    pending_long_runs = context.get("pending_long_runs", [])
    pending_selected_kind = selected_task_kind_value(result)
    pending_selected_source = str(value_for(result, "selected_task_source") or "").strip().lower()
    pending_allowed_kinds = {
        "long_run_monitor",
        "long_run_harvest",
        "long_run_finalize",
        "terminal_blocked",
        "terminal_blocker",
        "user_escalation",
    }
    derive_mode = str(first_present(result, ["derive_mode", "mode", "derive.mode", "result.derive_mode"]) or "").strip().lower()
    ordinary_derive = derive_mode != "initial_init" and not (
        pending_selected_kind in pending_allowed_kinds or pending_selected_source == "terminal_blocked"
    )
    handoff = first_present(
        result,
        [
            "anti_loop_handoff",
            "anti_loop_progress_handoff",
            "anti_loop_progress_gate.handoff",
            "result.anti_loop_handoff",
            "result.anti_loop_progress_handoff",
        ],
    )
    gate_value = first_present(result, ["anti_loop_progress_gate", "result.anti_loop_progress_gate"])
    if not isinstance(handoff, dict) and isinstance(gate_value, dict) and gate_value.get("applicability"):
        handoff = gate_value
    handoff_version = (
        handoff.get("handoff_contract_version")
        if isinstance(handoff, dict)
        else gate_value.get("handoff_contract_version")
        if isinstance(gate_value, dict)
        else first_present(result, ["handoff_contract_version", "result.handoff_contract_version"])
    )
    handoff_version_text = str(handoff_version).strip()
    explicit_legacy_handoff = handoff_version_text == "0"
    if explicit_legacy_handoff:
        add(
            findings,
            "warn",
            "derive_anti_loop_handoff_explicit_legacy",
            "Explicit handoff contract version 0 uses legacy unbound consumption; emit a current hash-bound handoff on the next governed transition.",
        )
        handoff = None
    governed_handoff_required = boolish(
        first_present(
            result,
            [
                "governed_transition",
                "loopback_audit_completed",
                "anti_loop_handoff_required",
                "result.governed_transition",
            ],
        )
    ) or isinstance(handoff, dict) or isinstance(gate_value, dict)
    if explicit_legacy_handoff:
        governed_handoff_required = False
    if governed_handoff_required and not isinstance(handoff, dict):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_anti_loop_handoff_missing",
            "A governed post-loopback derive transition requires a bounded hash-bound anti-loop handoff.",
        )
    elif isinstance(handoff, dict):
        if handoff_version_text != "1":
            add(
                findings,
                "block",
                "derive_anti_loop_handoff_version_missing_or_invalid",
                "Current anti-loop handoffs require handoff_contract_version=1; legacy requires explicit version 0.",
            )
        applicability = str(handoff.get("applicability") or "").strip().lower()
        if applicability not in HANDOFF_APPLICABILITY:
            add(findings, "block", "derive_anti_loop_applicability_invalid", "Anti-loop handoff applicability is invalid.")
        elif applicability == "missing_required":
            add(findings, "block", "derive_anti_loop_handoff_missing_required", "A required anti-loop handoff is missing.")
        elif applicability == "not_applicable":
            reason = handoff.get("not_applicable_reason") or handoff.get("applicability_reason")
            legitimate_na = derive_mode == "initial_init" or pending_selected_source == "standalone"
            prior_packet = bool(
                handoff.get("prior_packet_exists")
                or first_present(result, ["prior_loopback_packet_ref", "loopback_packet_ref"])
            )
            if not legitimate_na or not non_empty(reason) or prior_packet:
                add(
                    findings,
                    "block",
                    "derive_anti_loop_not_applicable_invalid",
                    "Anti-loop handoff not_applicable requires a reasoned initial/standalone derive with no prior required packet.",
                )
        elif applicability == "required":
            _check_required_handoff(
                facts,
                handoff,
                pending_selected_source,
                pending_selected_kind,
            )
    if ordinary_derive and not context.get("long_run_state_checked", False):
        add(
            findings,
            "block",
            "long_run_state_not_checked",
            "Ordinary derivation requires explicit proof that current long-run state was checked.",
        )
    if pending_long_runs and ordinary_derive:
        add(
            findings,
            "block",
            "pending_long_run_ordinary_derive",
            "Pending long-running execution permits only monitor/harvest/finalize or terminal/user-escalation derivation.",
            {
                "pending_long_runs": pending_long_runs,
                "selected_task_kind": pending_selected_kind or None,
                "selected_task_source": pending_selected_source or None,
            },
        )
    
    facts.explicit_report_key_divergence = explicit_report_key_divergence
    facts.auto_report_key_divergences = auto_report_key_divergences

