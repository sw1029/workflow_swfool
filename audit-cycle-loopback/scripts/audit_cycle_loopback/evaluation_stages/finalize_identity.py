from __future__ import annotations

from ..runtime_dependencies import (
    bool_value,
    call_adapter,
    content_bound_attempt_identity,
    decision_input_state_fingerprint,
    legacy_content_bound_attempt_identity,
    load_json_value,
    normalize_root_family_key,
    rel_path,
)

from ..evaluation_frame import _EvaluationFrame


def _finalize_attempt_identity(frame: _EvaluationFrame) -> None:
    (
        adapter_revision_sha256, args, budget_evaluations, current_blocker_signature, current_root_family_key,
        current_root_key, current_rung, decision_artifact_ref, domain_adapter,
        evidence_provenance_error, evidence_provenance_value, family_key,
        identity_gate_inputs, output_delta, paths, primary_metric_error,
        primary_metric_source_separation_gate, primary_metric_value, quality, root,
        runner_validation, source_separation_gate,
    ) = frame.require(
        "adapter_revision_sha256", "args", "budget_evaluations", "current_blocker_signature",
        "current_root_family_key", "current_root_key", "current_rung",
        "decision_artifact_ref", "domain_adapter", "evidence_provenance_error",
        "evidence_provenance_value", "family_key", "identity_gate_inputs",
        "output_delta", "paths", "primary_metric_error",
        "primary_metric_source_separation_gate", "primary_metric_value", "quality",
        "root", "runner_validation", "source_separation_gate",
    )
    root_cause_hypotheses_value = load_json_value(
        root,
        getattr(args, "root_cause_hypotheses_json", None),
    )
    root_cause_hypotheses_error: str | None = None
    if root_cause_hypotheses_value is None:
        root_cause_hypotheses_value, root_cause_hypotheses_error = call_adapter(
            domain_adapter,
            "root_cause_hypotheses",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
            root_family_key=current_root_family_key,
            blocker_signature=current_blocker_signature,
            blocker_ladder_rung=current_rung,
        )
    input_state_fingerprint = decision_input_state_fingerprint(
        [
            runner_validation,
            output_delta,
            quality,
            *identity_gate_inputs,
            {
                "evidence_provenance_input": {
                    "value": evidence_provenance_value,
                    "error": evidence_provenance_error,
                    "source_separation": source_separation_gate,
                }
            },
            {
                "primary_metric_input": {
                    "value": primary_metric_value,
                    "error": primary_metric_error,
                    "source_separation": primary_metric_source_separation_gate,
                }
            },
            {
                "decision_budget_inputs": budget_evaluations,
                "numeric_epsilon": args.epsilon,
            },
            {
                "root_cause_hypotheses_input": {
                    "value": root_cause_hypotheses_value,
                    "error": root_cause_hypotheses_error,
                    "declared_hypothesis": getattr(args, "hypothesized_root_cause", None),
                    "repair_attempted": bool_value(
                        getattr(args, "root_cause_repair_attempted", False)
                    ),
                    "repair_task_id": getattr(args, "root_cause_repair_task_id", None),
                    "actionable": bool_value(
                        getattr(args, "root_cause_actionable", False)
                    ),
                }
            },
            {"adapter_revision_sha256": adapter_revision_sha256},
        ],
        decision_artifact_ref,
    )
    attempt_identity = content_bound_attempt_identity(
        args.cycle_id,
        normalize_root_family_key(args.artifact_family),
        "pending",
        input_state_fingerprint,
    )
    legacy_attempt_identity = legacy_content_bound_attempt_identity(
        args.cycle_id,
        normalize_root_family_key(args.artifact_family),
        str(current_blocker_signature).strip().lower(),
        input_state_fingerprint,
    )
    frame.update({
        "attempt_identity": attempt_identity,
        "input_state_fingerprint": input_state_fingerprint,
        "legacy_attempt_identity": legacy_attempt_identity,
        "root_cause_hypotheses_error": root_cause_hypotheses_error,
        "root_cause_hypotheses_value": root_cause_hypotheses_value,
    })
