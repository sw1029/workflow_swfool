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



class ResultBuilderMixin:
    def _build_terminal_blocker_candidate(self) -> None:
        escalation = self.state["terminal_escalation_gate_result"]
        if escalation.get("escalation_required"):
            self.state["terminal_blocker_candidate"] = {
                "root_key": escalation.get("root_family"),
                "semantic_signature": None,
                "blocker_signature": None,
                "feature_symbol": None,
                "reason": "Repeated terminal_blocked/recheck for the same root family without a detected supplied input delta.",
                "required_handoff": (escalation.get("missing_input") or {}).get("description"),
                "required_missing_input": escalation.get("missing_input"),
                "required_missing_input_count": 1,
                "forced_disposition": "user_escalation",
                "recent_evidence_paths": escalation.get("evidence_paths") or [],
                "seal_family_path": escalation.get("seal_family_path"),
            }
            return
        repeated_family = self.state["repeated_root_keys"] or self.state["repeated_semantic_signatures"] or self.state["repeated_signatures"] or self.state["recurring_no_delta_feature_symbols"] or self.state["sealed_matches"] or self.state["sealed_blocker_matches"]
        if repeated_family and not self.state["has_supplied_input_delta"] and not self.state["provider_reattempt_records"]:
            self.state["terminal_blocker_candidate"] = self._repeated_family_terminal_candidate()
            return
        self.state["terminal_blocker_candidate"] = None

    def _repeated_family_terminal_candidate(self) -> dict[str, Any]:
        return {
            "root_key": self.state["repeated_root_keys"][0]["root_key"] if self.state["repeated_root_keys"] else None,
            "semantic_signature": self.state["repeated_semantic_signatures"][0]["semantic_signature"] if self.state["repeated_semantic_signatures"] else (self.state["sealed_matches"][0] if self.state["sealed_matches"] else None),
            "blocker_signature": self.state["repeated_signatures"][0]["blocker_signature"] if self.state["repeated_signatures"] else (self.state["sealed_blocker_matches"][0] if self.state["sealed_blocker_matches"] else None),
            "feature_symbol": self.state["recurring_no_delta_feature_symbols"][0]["feature_symbol"] if self.state["recurring_no_delta_feature_symbols"] else None,
            "reason": "Repeated suffix-normalized root key, semantic blocker family, or blocker signature without a detected positive input delta.",
            "required_handoff": "Provide a new input kind, authority change, external-state change, or a safe provider-neutral task-pack item.",
            "recent_evidence_paths": [item.get("path") for item in self.state["evidence"][: self.recent] if item.get("path")],
            "seal_family_path": ".task/sealed_blocker_families.json",
        }

    def _build_result(self) -> dict[str, Any]:
        findings = self.state["findings"]
        status = "block" if any(item["severity"] == "block" for item in findings) else ("warn" if findings else "ok")
        progress_items = self.state["progress_items"]
        registry_update = (
            prepare_feature_symbol_registry_update(
                self.root,
                progress_items[0],
                self.recurrence_threshold,
                self.state["registry_state"]["rows"],
            )
            if self.write_registry and progress_items
            else {
                "write_enabled": False,
                "legacy_write_requested": self.write_registry,
                "updated": False,
                "prepared": False,
            }
        )
        return {
            "status": status,
            "checked_at": now_iso(),
            "workspace": str(self.root),
            "recent_limit": self.recent,
            "evidence_scope": {
                "status": "explicit_limit" if self.recent is not None else "not_evaluated",
                "limit": self.recent,
            },
            "detector_policy_gate": self.state["detector_policy_gate"],
            "registry_input_gate": self.state["registry_input_gate"],
            "recurrence_budget": {
                "threshold": self.recurrence_threshold,
                "evaluation_status": "evaluated" if self.recurrence_threshold is not None else "budget_unverified",
            },
            "safety_only_count": self.state["safety_count"],
            "governance_only_count": self.state["governance_only_count"],
            "metadata_only_count": self.state["metadata_only_count"],
            "repeated_blocker_signatures": self.state["repeated_signatures"][:5],
            "repeated_semantic_signatures": self.state["repeated_semantic_signatures"][:5],
            "repeated_root_keys": self.state["repeated_root_keys"][:5],
            "root_family_counts": dict(self.state["counters"]["root_family"]),
            "repeated_feature_symbols": self.state["repeated_feature_symbols"][:5],
            "feature_symbol_gate": self.state["feature_symbol_gate"],
            "feature_symbol_registry_update": registry_update,
            "coverage_quality_delta_gate": self.state["coverage_quality_delta_gate_result"],
            "provider_scale_dispatch_gate": self.state["provider_scale_dispatch_gate_result"],
            "validator_integrity_gate": self.state["validator_integrity_gate_result"],
            "detection_balance_gate": self.state["detection_balance_gate"],
            "terminal_quiescence_gate": self.state["terminal_quiescence_gate_result"],
            "terminal_escalation_gate": self.state["terminal_escalation_gate_result"],
            "terminal_recheck_streak": self.state["terminal_escalation_gate_result"].get("terminal_recheck_streak", 0),
            "quiescence_untried_reconcile": self.state["terminal_quiescence_gate_result"].get("quiescence_untried_reconcile"),
            "root_axis_gate": self.state["root_axis_gate"],
            "autonomous_retarget_disabled": self.state["autonomous_retarget_disabled"],
            "hard_stop_required": self._hard_stop_required(),
            "requires_goal_productive_or_user_escalation": self._requires_goal_productive_or_user_escalation(),
            "recommended_disposition": "user_escalation" if self.state["terminal_escalation_gate_result"].get("escalation_required") else None,
            "semantic_signature_gate": {"preferred_for_loop_comparison": True, "sealed_matches": self.state["sealed_matches"], "sealed_blocker_matches": self.state["sealed_blocker_matches"], "sealed_family_records": self.state["sealed_families"][:10]},
            "goal_distance_gate": self.state["goal_distance_gate"],
            "effective_allowed_dispositions": self.state["effective_allowed_dispositions"],
            "disposition_intersection_basis": self.state["disposition_intersection_basis"],
            "consolidation_streak": self.state["consolidation_streak_count"],
            "consolidation_reduces_goal_distance": False,
            "consolidation_streak_cap": self.consolidation_streak_cap,
            "consolidation_streak_evaluation_status": "evaluated" if self.consolidation_streak_cap is not None else "budget_unverified",
            "positive_input_delta_gate": self._positive_input_delta_gate(),
            "provider_reattempt_gate": self._provider_reattempt_summary(),
            "command_surface_budget": self.state["surface_budget"],
            "terminal_blocker_candidate": self.state["terminal_blocker_candidate"],
            "findings": findings,
            "evidence": self.state["evidence"],
        }

    def _hard_stop_required(self) -> bool:
        return bool(
            self.state["detector_policy_gate"]["hard_stop_required"]
            or self.state["registry_input_gate"]["hard_stop_required"]
            or self.state["feature_symbol_gate"]["hard_stop_required"]
            or self.state["autonomous_retarget_disabled"]
            or self.state["provider_scale_dispatch_gate_result"]["dispatch_required"]
            or self.state["validator_integrity_gate_result"]["hard_stop_required"]
            or self.state["detection_balance_gate"]["hard_stop_required"]
            or self.state["terminal_quiescence_gate_result"].get("quiescence_required")
            or self.state["terminal_escalation_gate_result"].get("hard_stop_required")
        )

    def _requires_goal_productive_or_user_escalation(self) -> bool:
        return bool(
            self.state["autonomous_retarget_disabled"]
            or self.state["provider_scale_dispatch_gate_result"]["dispatch_required"]
            or self.state["detection_balance_gate"]["hard_stop_required"]
            or self.state["terminal_escalation_gate_result"].get("hard_stop_required")
        )

    def _positive_input_delta_gate(self) -> dict[str, Any]:
        return {
            "required_count": self.state["positive_delta_required_count"],
            "has_new_input_kind": self.state["has_positive_input_delta"],
            "new_input_kinds": sorted(self.state["counters"]["input_kind"]),
            "has_positive_output_delta": self.state["has_positive_output_delta"],
            "has_supplied_input_delta": self.state["has_supplied_input_delta"],
            "supplied_input_artifact_paths": sorted(self.state["supplied_input_paths"]),
        }

    def _provider_reattempt_summary(self) -> dict[str, Any]:
        records = self.state["provider_reattempt_records"]
        policy_supplied = bool((self.policy.get("provider_retry_policy") or {}).get("supplied"))
        return {
            "provider_reattempt_required": any(bool(item.get("authority_allows_retry")) for item in records),
            "provider_mitigation_required": bool(records),
            "provider_terminal_seal_allowed": policy_supplied and not bool(records),
            "records": records[:10],
            "evaluation_status": "evaluated" if policy_supplied else "not_evaluated",
        }
