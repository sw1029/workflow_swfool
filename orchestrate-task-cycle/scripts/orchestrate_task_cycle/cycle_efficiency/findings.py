from __future__ import annotations

import json
from typing import Any

from .state import CostProjection, ObservationState, ScopeState


def base_findings(
    scope: ScopeState, obs: ObservationState, index_records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if scope.execution_starvation_status == "scope_unknown":
        findings.append(
            {
                "severity": "warn",
                "code": "execution_scope_unknown",
                "message": "Execution starvation cannot be decided until the minimum producer-run scope is supplied.",
                "evidence": {
                    "missing_scope_fields": scope.execution_scope_evidence_required
                },
                "recommendation": "supply_evidence_path",
            }
        )
    elif scope.execution_starvation_status == "present":
        findings.append(
            {
                "severity": "warn",
                "code": "execution_starvation",
                "message": "No fresh run id was observed in the scoped recent-cycle window.",
                "evidence": {
                    "window": scope.execution_starvation_window,
                    "recent_cycle_run_id_count": 0,
                },
                "recommendation": "resume_primary_output",
            }
        )
    simple_findings = (
        (
            obs.repeated_blockers,
            "repeated_blocker",
            "A blocker appears multiple times.",
        ),
        (
            obs.repeated_signatures,
            "repeated_blocker_signature",
            "A normalized blocker signature appears multiple times.",
        ),
        (
            obs.duplicate_artifacts,
            "duplicate_artifact_paths",
            "Artifact paths repeat across events.",
        ),
        (
            obs.missing_unchanged_payload_refs,
            "unchanged_ref_missing_for_duplicate_artifacts",
            "Repeated artifact payloads should use unchanged_ref(path+hash) instead of reserializing identical packet content.",
        ),
    )
    for evidence, code, message in simple_findings:
        if evidence:
            findings.append(
                {
                    "severity": "warn",
                    "code": code,
                    "message": message,
                    "evidence": evidence[:5],
                }
            )
    if obs.full_chain_without_reason:
        findings.append(
            {
                "severity": "warn",
                "code": "full_chain_without_escalation_reason",
                "message": "Full-chain validation was recorded without escalation reason.",
                "count": len(obs.full_chain_without_reason),
            }
        )
    if obs.vacuous_untried_streak:
        findings.append(
            {
                "severity": "warn",
                "code": "vacuous_untried_streak",
                "message": "Untried root-cause repairs repeated without terminal_outcome_changed.",
                "evidence": {"vacuous_untried_streak": obs.vacuous_untried_streak},
            }
        )
    if obs.hypothesis_exhausted:
        findings.append(
            {
                "severity": "warn",
                "code": "hypothesis_exhausted",
                "message": "Root-cause hypothesis budget is exhausted; next work should stop, user-escalate, or require a supplied input delta.",
            }
        )
    if obs.forward_mutation_vacuous_count:
        findings.append(
            {
                "severity": "warn",
                "code": "forward_mutation_vacuous_streak",
                "message": "Capability-ladder movement occurred without observed terminal outcome change.",
                "evidence": {
                    "forward_mutation_vacuous_count": obs.forward_mutation_vacuous_count
                },
            }
        )
    if obs.validation_set_blockers and not obs.validation_set_events:
        findings.append(
            {
                "severity": "warn",
                "code": "validation_set_gap_without_build_phase",
                "message": "Validation-set, oracle, leakage, source-class, or quality blockers exist but no validation_set_build stage was recorded.",
                "evidence": obs.validation_set_blockers[:5],
            }
        )
    if len(obs.validation_set_artifacts) != len(set(obs.validation_set_artifacts)):
        findings.append(
            {
                "severity": "warn",
                "code": "duplicate_validation_set_artifacts",
                "message": "Validation-set artifact paths repeat across events.",
            }
        )
    if any(
        "base_commit" in json.dumps(record, sort_keys=True) for record in index_records
    ):
        findings.append(
            {
                "severity": "info",
                "code": "base_commit_present",
                "message": "Pre-commit hashes should stay classified as base/pre_commit evidence until $repo-change-commit returns a final commit.",
            }
        )
    return findings


def append_budget_findings(
    findings: list[dict[str, Any]], cost: CostProjection
) -> None:
    if cost.surface_budget["consolidation_candidate_required"]:
        findings.append(
            {
                "severity": "warn",
                "code": "command_surface_budget_exceeded",
                "message": "A target script has accumulated contract/preflight command surface while recent progress is metadata-only.",
                "evidence": cost.surface_budget,
            }
        )
    if cost.sprawl_budget["consolidation_candidate_required"]:
        findings.append(
            {
                "severity": "warn",
                "code": "artifact_sprawl_budget_exceeded",
                "message": "Run directories, processed candidates, or versioned command families exceed consolidation thresholds.",
                "evidence": cost.sprawl_budget,
            }
        )


def recommendations(findings: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    codes = {item["code"] for item in findings}
    if "execution_scope_unknown" in codes:
        values.append("supply_evidence_path")
    if "execution_starvation" in codes:
        values.append("resume_primary_output")
    if "repeated_blocker_signature" in codes:
        values.append("consume_or_reorder_task_pack_or_terminal_block")
    if "validation_set_gap_without_build_phase" in codes:
        values.append("route_validation_set_plan_or_build")
    if "vacuous_untried_streak" in codes or "forward_mutation_vacuous_streak" in codes:
        values.append("root_cause_repair_or_stop_with_blocker")
    if "hypothesis_exhausted" in codes:
        values.append("stop_with_blocker")
    return values
