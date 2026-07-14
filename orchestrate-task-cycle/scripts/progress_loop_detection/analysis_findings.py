from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from .constants import *
from .values import *
from .io_utils import *
from .registry import *
from .terminal import *
from .dispositions import *
from .gates import *
from .evidence import *



class FindingBuilderMixin:
    def _build_findings(self) -> None:
        findings: list[dict[str, Any]] = []
        findings.extend(self.policy.get("findings") or [])
        findings.extend(self.state["registry_state"].get("findings") or [])
        self._add_repetition_findings(findings)
        self._add_delta_findings(findings)
        self._add_gate_findings(findings)
        self._add_terminal_findings(findings)
        self._add_streak_and_fallback_findings(findings)
        self.state["findings"] = findings

    def _add_repetition_findings(self, findings: list[dict[str, Any]]) -> None:
        recurrence = self.recurrence_threshold
        recent_window = self.state["progress_items"][:recurrence] if recurrence is not None else []
        if recurrence is not None and len(recent_window) == recurrence and all(item.get("progress_verdict") == "safety_only" for item in recent_window):
            findings.append({"severity": "block" if self.strict and self.state["repeated_blockers"] else "warn", "code": "consecutive_safety_only", "message": "The configured recent progress window is entirely `safety_only`.", "evidence": recent_window})
        if self.state["repeated_blockers"]:
            findings.append({"severity": "warn", "code": "repeated_blocker", "message": "The same blocker appears in multiple recent artifacts.", "evidence": self.state["repeated_blockers"][:5]})
        for key, code, message in (
            ("repeated_signatures", "repeated_blocker_signature", "The same normalized blocker signature appears in multiple recent artifacts."),
            ("repeated_semantic_signatures", "repeated_semantic_signature", "The same semantic blocker family appears in multiple recent artifacts."),
        ):
            if self.state[key]:
                findings.append({"severity": "block" if self.strict and not self.state["has_supplied_input_delta"] else "warn", "code": code, "message": message, "evidence": self.state[key][:5]})
        if self.state["recurring_no_delta_feature_symbols"] or self.state["over_threshold_feature_symbols"]:
            threshold_hit = bool(self.state["over_threshold_feature_symbols"])
            terminal_hit = bool(self.state["feature_terminal_history"])
            findings.append(
                {
                    "severity": "block" if (threshold_hit or terminal_hit or self.strict) and not self.state["has_supplied_input_delta"] else "warn",
                    "code": "repeated_feature_symbol_no_delta",
                    "message": "The same observed-over-declared workflow feature symbol recurred without an observed material delta; labels and self-declared progress do not reset this counter.",
                    "evidence": {"recurring_no_delta_feature_symbols": self.state["recurring_no_delta_feature_symbols"][:5], "over_threshold_feature_symbols": self.state["over_threshold_feature_symbols"][:5], "terminal_history_matches": self.state["feature_terminal_history"][:10], "threshold": self.feature_symbol_threshold},
                }
            )
        if self.state["repeated_root_keys"]:
            findings.append({"severity": "block" if self.strict and not self.state["has_supplied_input_delta"] else "warn", "code": "repeated_root_key", "message": "The same suffix-normalized root key appears in multiple recent artifacts; version/date/sequence suffixes do not reset the loop counter.", "evidence": self.state["repeated_root_keys"][:5]})

    def _add_delta_findings(self, findings: list[dict[str, Any]]) -> None:
        recurrence = self.recurrence_threshold
        recent_window = self.state["progress_items"][:recurrence] if recurrence is not None else []
        if recurrence is not None and len(recent_window) == recurrence and all(item.get("progress_kind") == "governance_only" for item in recent_window):
            findings.append({"severity": "block" if self.strict else "warn", "code": "consecutive_governance_only", "message": "The configured recent progress window is governance-only, not goal-productive.", "evidence": recent_window})
        if recurrence is not None and len(recent_window) == recurrence and all(item.get("metadata_only") for item in recent_window):
            findings.append({"severity": "block" if self.strict else "warn", "code": "consecutive_metadata_only", "message": "The configured recent progress window is metadata-only after output-delta review.", "evidence": recent_window, "recommendation": "resume_primary_output"})
        if self.goal_productive_threshold is not None and self.state["cycles_since_goal_productive_output"] > self.goal_productive_threshold:
            findings.append({"severity": "block" if self.strict else "warn", "code": "goal_productive_output_stale", "message": "Recent cycles exceed the goal-productive output threshold.", "evidence": {"cycles_since_goal_productive_output": self.state["cycles_since_goal_productive_output"], "threshold": self.goal_productive_threshold}})
        if self.state["positive_delta_required_count"] and not self.state["has_supplied_input_delta"]:
            findings.append({"severity": "block" if self.strict else "warn", "code": "positive_input_delta_missing", "message": "Recent evidence requires a positive input delta, but no non-empty supplied artifact or positive output delta was detected.", "evidence": {"positive_delta_required_count": self.state["positive_delta_required_count"]}})
        if self.state["has_positive_input_delta"] and not self.state["has_supplied_input_delta"]:
            findings.append({"severity": "block" if self.strict else "warn", "code": "named_only_input_delta", "message": "`has_new_input_kind` is present, but no non-empty supplied input artifact or positive output delta proves a real input delta.", "evidence": {"new_input_kinds": sorted(self.state["counters"]["input_kind"]), "supplied_input_artifact_paths": sorted(self.state["supplied_input_paths"])}})

    def _add_gate_findings(self, findings: list[dict[str, Any]]) -> None:
        if self.state["autonomous_retarget_disabled"]:
            findings.append({"severity": "block", "code": "autonomous_retarget_disabled", "message": "The same root axis or suffix-normalized root key has exceeded the autonomous governance-only/provider-neutral retarget threshold without a high-confidence domain delta.", "evidence": self._root_gate_evidence()})
        if (self.state["sealed_matches"] or self.state["sealed_blocker_matches"]) and not self.state["has_supplied_input_delta"]:
            findings.append({"severity": "block" if self.strict else "warn", "code": "sealed_semantic_family_without_input_delta", "message": "A sealed blocker family recurred without a supplied input artifact or positive output delta.", "evidence": {"semantic_matches": self.state["sealed_matches"], "blocker_matches": self.state["sealed_blocker_matches"]}})
        if self.state["provider_reattempt_records"]:
            findings.append({"severity": "block" if self.strict else "warn", "code": "provider_reattempt_required", "message": "A transient provider failure cannot be treated as provider-terminal while required mitigations remain unexhausted.", "evidence": self.state["provider_reattempt_records"][:5]})
        if self.state["surface_budget"].get("consolidation_candidate_required"):
            findings.append({"severity": "warn", "code": "command_surface_budget_exceeded", "message": "Global contract/preflight command-surface debt is dashboard-only until an exact current-family scope proves it can constrain the decision.", "evidence": self.state["surface_budget"]})
        if self.state["provider_scale_dispatch_gate_result"]["dispatch_required"]:
            findings.append({"severity": "block", "code": "provider_scale_dispatch_required", "message": "No provider dispatch occurred and coverage/quality high-water evidence remains all-zero; derive must choose bounded dispatch/scale work if authority permits, or terminal/user-escalate with missing authority/input.", "evidence": self.state["provider_scale_dispatch_gate_result"]})
        if self.state["validator_gate_records"]:
            findings.append({"severity": "block", "code": "validator_integrity_or_coverage_failed", "message": "A validator reported a top-level pass despite embedded failures, or inspected fewer items than its declared population.", "evidence": self.state["validator_integrity_gate_result"]})
        if self.state["detection_balance_required"]:
            findings.append({"severity": "block", "code": "detection_only_streak_capped", "message": "Detection-only work repeated for the same root blocker family without primary-output delta; derive must select correction, terminal_blocked, or user_escalation.", "evidence": self.state["detection_balance_gate"]})

    def _root_gate_evidence(self) -> dict[str, Any]:
        return {
            "root_axis": self.state["primary_root_axis"],
            "root_key": self.state["primary_root_key"],
            "threshold": self.root_axis_threshold,
            "root_axis_disabled": self.state["root_axis_disabled"],
            "root_key_disabled": self.state["root_key_disabled"],
            "root_axis_governance_only_count": self.state["root_axis_governance_only_count"],
            "root_axis_provider_neutral_count": self.state["root_axis_provider_neutral_count"],
            "root_axis_produced_domain_delta": self.state["root_axis_produced_domain_delta"],
            "root_key_governance_only_count": self.state["root_key_governance_only_count"],
            "root_key_produced_domain_delta": self.state["root_key_produced_domain_delta"],
        }

    def _add_terminal_findings(self, findings: list[dict[str, Any]]) -> None:
        quiescence = self.state["terminal_quiescence_gate_result"]
        escalation = self.state["terminal_escalation_gate_result"]
        if quiescence.get("quiescence_required"):
            findings.append({"severity": "block", "code": "terminal_quiescence_required", "message": "The same terminal root recurred without supplied input delta; orchestrator must stop automatic domain-cycle restart and record only one user handoff note.", "evidence": quiescence})
        elif (quiescence.get("quiescence_untried_reconcile") or {}).get("overridden_by_untried_root_cause"):
            findings.append({"severity": "warn", "code": "terminal_quiescence_overridden_by_untried_root_cause", "message": "Terminal quiescence was reached but a verified, unexhausted untried root-cause repair may still be promoted.", "evidence": quiescence})
        if escalation.get("escalation_required"):
            findings.append({"severity": "block", "code": "terminal_blocked_recheck_escalated", "message": "terminal_blocked/recheck repeated for the same root family without supplied input delta; derive must seal the family and emit user_escalation with exactly one missing input.", "evidence": escalation})

    def _add_streak_and_fallback_findings(self, findings: list[dict[str, Any]]) -> None:
        if self.consolidation_streak_cap is not None and self.state["consolidation_streak_count"] >= self.consolidation_streak_cap:
            if "consolidation" in self.state["effective_allowed_dispositions"]:
                self.state["effective_allowed_dispositions"] = [item for item in self.state["effective_allowed_dispositions"] if item != "consolidation"]
            findings.append({"severity": "block", "code": "consolidation_streak_capped", "message": "Consecutive governance-only consolidation reached the configured cap; the next disposition must reduce goal distance or terminal/user-escalate.", "evidence": {"consolidation_streak": self.state["consolidation_streak_count"], "cap": self.consolidation_streak_cap}})
        if self.recurrence_threshold is not None and self.state["no_live_count"] >= self.recurrence_threshold and self.state["source_backed_count"] == 0:
            findings.append({"severity": "warn", "code": "no_live_micro_contract_loop", "message": "Recent artifacts repeatedly use no-live/fail-closed language without source-backed or bounded-preflight evidence language.", "evidence": {"no_live_count": self.state["no_live_count"], "source_backed_count": self.state["source_backed_count"]}})
        if any(item.get("confidence") == "low" for item in self.state["evidence"]):
            findings.append({"severity": "info", "code": "regex_low_confidence_fallback_used", "message": "Some progress evidence came from text regex fallback because structured ledger/index/validation evidence was insufficient."})
