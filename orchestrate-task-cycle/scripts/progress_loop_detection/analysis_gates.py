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



class GateEvaluationMixin:
    def _evaluate_gates(self) -> None:
        sealed_semantic = {str(item.get("semantic_signature")) for item in self.state["sealed_families"] if item.get("semantic_signature")}
        sealed_blocker = {str(item.get("blocker_signature")) for item in self.state["sealed_families"] if item.get("blocker_signature")}
        self.state["sealed_matches"] = sorted(set(self.state["counters"]["semantic"]) & sealed_semantic)
        self.state["sealed_blocker_matches"] = sorted(set(self.state["counters"]["signature"]) & sealed_blocker)
        self.state["surface_budget"] = self._surface_budget_gate()
        self.state["detector_policy_gate"] = self._detector_policy_gate()
        self.state["registry_input_gate"] = self._registry_input_gate()
        self.state["feature_symbol_gate"] = self._feature_symbol_gate()
        self.state["root_axis_gate"] = self._root_axis_gate()
        self.state["goal_distance_gate"] = self._goal_distance_gate()
        self.state["validator_integrity_gate_result"] = self._validator_integrity_gate_result()
        self.state["detection_balance_gate"] = self._detection_balance_gate()
        self.state["terminal_quiescence_gate_result"] = terminal_quiescence_gate(
            self.state["progress_items"], self.state["has_supplied_input_delta"], self.terminal_quiescence_threshold
        )
        self.state["terminal_escalation_gate_result"] = terminal_escalation_gate(
            self.state["progress_items"], self.state["has_supplied_input_delta"], self.terminal_escalation_threshold
        )
        effective_allowed, disposition_basis = effective_allowed_dispositions(self._disposition_gate_inputs())
        self.state["effective_allowed_dispositions"] = effective_allowed
        self.state["disposition_intersection_basis"] = disposition_basis
        self.state["consolidation_streak_count"] = consolidation_streak(self.state["progress_items"])

    def _surface_budget_gate(self) -> dict[str, Any]:
        surface = command_surface_budget(
            self.root,
            threshold=self.command_surface_threshold,
            metadata_only_count=self.state["metadata_only_count"],
            metadata_window=self.metadata_only_window,
            pattern=self.policy.get("command_surface_pattern"),
        )
        surface["hard_gate"] = bool(surface.get("hard_gate")) and bool(surface.get("constrains_current_family"))
        surface["strict_output_delta_present"] = self.state["has_positive_output_delta"]
        surface["allowed_dispositions"] = ["consolidation", "goal_productive", "terminal_blocked"] if self.state["has_positive_output_delta"] else ["consolidation", "terminal_blocked"]
        surface["constrains_disposition"] = bool(surface.get("hard_gate")) and bool(surface.get("constrains_current_family"))
        return surface

    def _detector_policy_gate(self) -> dict[str, Any]:
        invalid = self.policy.get("evaluation_status") == "invalid_contract"
        return {
            "gate": "DETECTOR-POLICY",
            "status": "block" if invalid else self.policy.get("evaluation_status", "not_evaluated"),
            "hard_stop_required": invalid,
            "constrains_disposition": invalid,
            "allowed_dispositions": ["terminal_blocked", "user_escalation"] if invalid else sorted(DISPOSITION_UNIVERSE),
            "findings": self.policy.get("findings") or [],
        }

    def _registry_input_gate(self) -> dict[str, Any]:
        registry = self.state["registry_state"]
        invalid = registry["status"] == "block"
        return {
            "gate": "REGISTRY-INPUT",
            "status": "block" if invalid else registry["status"],
            "receipt_verified": registry["receipt_verified"],
            "finalized_cycle_id": registry["finalized_cycle_id"],
            "legacy_compat": registry["status"] == "legacy_compat",
            "hard_stop_required": invalid,
            "constrains_disposition": invalid,
            "allowed_dispositions": ["terminal_blocked", "user_escalation"] if invalid else sorted(DISPOSITION_UNIVERSE),
            "findings": registry["findings"],
        }

    def _feature_symbol_gate(self) -> dict[str, Any]:
        budget_supplied = self.feature_symbol_threshold is not None
        hard_stop = bool(budget_supplied and (self.state["over_threshold_feature_symbols"] or self.state["feature_terminal_history"]))
        return {
            "registry_path": REGISTRY_REL_PATH,
            "registry_write_enabled": False,
            "registry_prepare_requested": self.write_registry,
            "finalization_required": self.write_registry,
            "threshold": self.feature_symbol_threshold,
            "evaluation_status": "evaluated" if budget_supplied else "budget_unverified",
            "feature_symbol_counts": dict(self.state["counters"]["feature_symbol"]),
            "feature_symbol_no_delta_counts": dict(self.state["counters"]["feature_symbol_no_delta"]),
            "observed_output_class_counts": dict(self.state["counters"]["feature_symbol_output_class"]),
            "recurring_no_delta_feature_symbols": self.state["recurring_no_delta_feature_symbols"][:10],
            "over_threshold_feature_symbols": self.state["over_threshold_feature_symbols"][:10],
            "terminal_history_matches": self.state["feature_terminal_history"][:10],
            "hard_stop_required": hard_stop,
            "constrains_disposition": hard_stop,
            "allowed_dispositions": ["goal_productive", "consolidation", "terminal_blocked", "user_escalation"],
        }

    def _root_axis_gate(self) -> dict[str, Any]:
        budget_supplied = self.root_axis_threshold is not None
        return {
            "root_axis": self.state["primary_root_axis"],
            "root_key": self.state["primary_root_key"],
            "threshold": self.root_axis_threshold,
            "evaluation_status": "evaluated" if budget_supplied else "budget_unverified",
            "root_axis_counts": dict(self.state["counters"]["root_axis"]),
            "root_key_counts": dict(self.state["counters"]["root_key"]),
            "root_axis_governance_only_count": self.state["root_axis_governance_only_count"],
            "root_axis_provider_neutral_count": self.state["root_axis_provider_neutral_count"],
            "root_axis_produced_domain_delta": self.state["root_axis_produced_domain_delta"],
            "root_key_governance_only_count": self.state["root_key_governance_only_count"],
            "root_key_produced_domain_delta": self.state["root_key_produced_domain_delta"],
            "root_axis_disabled": self.state["root_axis_disabled"],
            "root_key_disabled": self.state["root_key_disabled"],
            "autonomous_retarget_disabled": self.state["autonomous_retarget_disabled"],
            "hard_stop_required": self.state["autonomous_retarget_disabled"],
            "constrains_disposition": self.state["autonomous_retarget_disabled"],
            "requires_goal_productive_or_user_escalation": self.state["autonomous_retarget_disabled"],
            "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        }

    def _goal_distance_gate(self) -> dict[str, Any]:
        budget_supplied = self.goal_productive_threshold is not None
        requires = bool(
            budget_supplied
            and self.state["cycles_since_goal_productive_output"] > self.goal_productive_threshold
        )
        return {
            "threshold": self.goal_productive_threshold,
            "evaluation_status": "evaluated" if budget_supplied else "budget_unverified",
            "cycles_since_goal_productive_output": self.state["cycles_since_goal_productive_output"],
            "goal_productive_this_cycle": self.state["goal_productive_this_cycle"],
            "requires_goal_productive_next": requires,
            "constrains_disposition": requires,
            "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        }

    def _validator_integrity_gate_result(self) -> dict[str, Any]:
        records = [
            item.get("validator_integrity_gate")
            for item in self.state["progress_items"]
            if isinstance(item.get("validator_integrity_gate"), dict) and boolish((item.get("validator_integrity_gate") or {}).get("hard_stop_required"))
        ]
        self.state["validator_gate_records"] = records
        return {
            "gate": "G-INTEGRITY",
            "hard_stop_required": bool(records),
            "constrains_disposition": bool(records),
            "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
            "records": records[:10],
            "status": "block" if records else "ok",
        }

    def _detection_balance_gate(self) -> dict[str, Any]:
        required = self.state["detection_balance_required"]
        return {
            "gate": "G-BALANCE",
            "root_family": self.state["primary_root_family"],
            "detection_only_streak": self.state["detection_only_streak_count"],
            "detection_only_streak_cap": self.detection_only_streak_cap,
            "evaluation_status": "evaluated" if self.detection_only_streak_cap is not None else "budget_unverified",
            "root_family_produced_domain_delta": self.state["root_family_produced_domain_delta"],
            "requires_correction_or_terminal": required,
            "allowed_task_classes": ["correction", "terminal_blocked", "user_escalation"],
            "hard_stop_required": required,
            "constrains_disposition": required,
            "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
            "status": "block" if required else "ok",
        }

    def _disposition_gate_inputs(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            ("detector_policy_gate", self.state["detector_policy_gate"]),
            ("registry_input_gate", self.state["registry_input_gate"]),
            ("command_surface_budget", self.state["surface_budget"]),
            ("feature_symbol_gate", self.state["feature_symbol_gate"]),
            ("root_axis_gate", self.state["root_axis_gate"]),
            ("goal_distance_gate", self.state["goal_distance_gate"]),
            ("provider_scale_dispatch_gate", self.state["provider_scale_dispatch_gate_result"]),
            ("validator_integrity_gate", self.state["validator_integrity_gate_result"]),
            ("detection_balance_gate", self.state["detection_balance_gate"]),
            ("terminal_quiescence_gate", self.state["terminal_quiescence_gate_result"]),
            ("terminal_escalation_gate", self.state["terminal_escalation_gate_result"]),
        ]
