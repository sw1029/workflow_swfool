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



class ProgressAggregationMixin:
    def _aggregate_progress(self) -> None:
        evidence = self.state["evidence"]
        progress_items = [item for item in evidence if item.get("progress_verdict")]
        counters = {
            "blocker": Counter(),
            "signature": Counter(),
            "semantic": Counter(),
            "root_axis": Counter(),
            "root_key": Counter(),
            "root_family": Counter(),
            "feature_symbol": Counter(),
            "feature_symbol_no_delta": Counter(),
            "feature_symbol_output_class": Counter(),
            "input_kind": Counter(),
        }
        supplied_input_paths: set[str] = set()
        provider_reattempt_records: list[dict[str, Any]] = []
        for item in progress_items:
            self._count_progress_item(item, counters, supplied_input_paths, provider_reattempt_records)
        self.state.update(
            {
                "progress_items": progress_items,
                "last_two": progress_items[:2],
                "counters": counters,
                "supplied_input_paths": supplied_input_paths,
                "provider_reattempt_records": provider_reattempt_records,
            }
        )
        self._derive_repetition_lists()

    def _count_progress_item(
        self,
        item: dict[str, Any],
        counters: dict[str, Counter[str]],
        supplied_input_paths: set[str],
        provider_reattempt_records: list[dict[str, Any]],
    ) -> None:
        counters["blocker"].update(item.get("blockers") or [])
        for field, counter_name in (
            ("blocker_signature", "signature"),
            ("semantic_signature", "semantic"),
            ("root_axis", "root_axis"),
            ("root_key", "root_key"),
            ("blocker_root_family", "root_family"),
        ):
            if item.get(field):
                counters[counter_name].update([str(item[field])])
        feature = item.get("feature_symbol")
        observed = item.get("observed_output")
        if isinstance(feature, dict) and feature.get("symbol"):
            symbol = str(feature["symbol"])
            counters["feature_symbol"].update([symbol])
            observed_class = str((observed or {}).get("observed_output_class") or "unknown")
            counters["feature_symbol_output_class"].update([observed_class])
            if observed_class in {"metadata_only", "terminal_record"}:
                counters["feature_symbol_no_delta"].update([symbol])
        counters["input_kind"].update(item.get("new_input_kinds") or [])
        supplied_input_paths.update(str(path) for path in item.get("supplied_input_artifact_paths") or [])
        self._append_provider_reattempt_record(item, provider_reattempt_records)

    def _append_provider_reattempt_record(self, item: dict[str, Any], records: list[dict[str, Any]]) -> None:
        provider_gate = item.get("provider_reattempt_gate")
        if not isinstance(provider_gate, dict):
            return
        if not (provider_gate.get("provider_reattempt_required") or provider_gate.get("provider_mitigation_required")):
            return
        records.append(
            {
                "path": item.get("path"),
                "provider_request_count": provider_gate.get("provider_request_count"),
                "failure_class": provider_gate.get("failure_class"),
                "authority_allows_retry": provider_gate.get("authority_allows_retry"),
                "provider_mitigation_required": provider_gate.get("provider_mitigation_required"),
                "missing_mitigations": provider_gate.get("missing_mitigations"),
                "mitigations_attempted": provider_gate.get("mitigations_attempted"),
                "mitigations_unavailable": provider_gate.get("mitigations_unavailable"),
                "provider_terminal_seal_allowed": provider_gate.get("provider_terminal_seal_allowed"),
            }
        )

    def _derive_repetition_lists(self) -> None:
        counters = self.state["counters"]
        repeated = {
            "repeated_blockers": [{"blocker": key, "count": count} for key, count in counters["blocker"].most_common() if count >= 2],
            "repeated_signatures": [{"blocker_signature": key, "count": count} for key, count in counters["signature"].most_common() if count >= 2],
            "repeated_semantic_signatures": [{"semantic_signature": key, "count": count} for key, count in counters["semantic"].most_common() if count >= 2],
            "repeated_feature_symbols": [{"feature_symbol": key, "count": count} for key, count in counters["feature_symbol"].most_common() if count >= 2],
            "recurring_no_delta_feature_symbols": [
                {"feature_symbol": key, "count": count}
                for key, count in counters["feature_symbol_no_delta"].most_common()
                if count >= 2
            ],
            "over_threshold_feature_symbols": [
                {"feature_symbol": key, "count": count}
                for key, count in counters["feature_symbol_no_delta"].most_common()
                if count >= self.feature_symbol_threshold
            ],
        }
        repeated["feature_terminal_history"] = self._feature_terminal_history(repeated["recurring_no_delta_feature_symbols"])
        self.state.update(repeated)

    def _feature_terminal_history(self, recurring: list[dict[str, Any]]) -> list[dict[str, Any]]:
        progress_items = self.state["progress_items"]
        matches: list[dict[str, Any]] = []
        for repeated in recurring[:3]:
            symbol = repeated["feature_symbol"]
            source_item = next(
                (item for item in progress_items if isinstance(item.get("feature_symbol"), dict) and item["feature_symbol"].get("symbol") == symbol),
                None,
            )
            if source_item and isinstance(source_item.get("feature_symbol"), dict):
                for match in terminal_history_matches(self.root, source_item["feature_symbol"]):
                    matches.append({"feature_symbol": symbol, **match})
        return matches

    def _derive_progress_metrics(self) -> None:
        evidence = self.state["evidence"]
        progress_items = self.state["progress_items"]
        counters = self.state["counters"]
        supplied_input_paths = self.state["supplied_input_paths"]
        coverage_delta_items = [item.get("coverage_quality_delta_gate") for item in progress_items if isinstance(item.get("coverage_quality_delta_gate"), dict)]
        dispatch_items = [item.get("provider_scale_dispatch_gate") for item in progress_items if isinstance(item.get("provider_scale_dispatch_gate"), dict)]
        has_positive_output_delta = any(
            boolish((item.get("output_delta_gate") or {}).get("produced_domain_delta")) and item.get("confidence") in {"high", "medium"}
            for item in progress_items
        )
        self.state.update(
            {
                "safety_count": sum(1 for item in progress_items if item.get("progress_verdict") == "safety_only"),
                "governance_only_count": sum(1 for item in progress_items if item.get("progress_kind") == "governance_only"),
                "metadata_only_count": sum(1 for item in progress_items if item.get("metadata_only")),
                "no_live_count": sum(1 for item in evidence if item.get("has_no_live_language")),
                "source_backed_count": sum(1 for item in evidence if item.get("has_source_backed_language")),
                "positive_delta_required_count": sum(1 for item in evidence if item.get("positive_input_delta_required")),
                "has_positive_input_delta": bool(counters["input_kind"]),
                "has_positive_output_delta": has_positive_output_delta,
                "has_supplied_input_delta": has_positive_output_delta or bool(supplied_input_paths),
                "goal_productive_this_cycle": bool(progress_items and progress_items[0].get("progress_kind") == "goal_productive"),
                "cycles_since_goal_productive_output": self._cycles_since_goal_productive(progress_items),
                "coverage_quality_delta_gate_result": self._coverage_gate_result(coverage_delta_items),
                "provider_scale_dispatch_gate_result": self._dispatch_gate_result(dispatch_items),
                "sealed_families": collect_sealed_families(self.root),
            }
        )

    def _cycles_since_goal_productive(self, progress_items: list[dict[str, Any]]) -> int:
        cycles = 0
        for item in progress_items:
            if item.get("progress_kind") == "goal_productive":
                break
            cycles += 1
        return cycles

    def _coverage_gate_result(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        improved = sorted({str(field) for item in items for field in (item.get("improved_fields") or []) if field})
        passed = any(boolish(item.get("quality_delta_pass")) for item in items)
        return {"gate": "G-COV", "quality_delta_pass": passed, "improved_fields": improved, "status": "pass" if passed else "block"}

    def _dispatch_gate_result(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        required = any(boolish(item.get("dispatch_required")) for item in items)
        return {
            "gate": "G-DISPATCH",
            "dispatch_required": required,
            "hard_stop_required": any(boolish(item.get("hard_stop_required")) for item in items),
            "constrains_disposition": any(boolish(item.get("constrains_disposition")) for item in items),
            "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
            "records": items[:10],
            "status": "block" if required else "ok",
        }
