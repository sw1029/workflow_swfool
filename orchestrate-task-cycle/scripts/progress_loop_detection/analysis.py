from __future__ import annotations

from pathlib import Path
from typing import Any

from .values import normalize_detector_policy
from .registry import load_symbol_registry_state
from .analysis_aggregation import ProgressAggregationMixin
from .analysis_evidence import EvidenceCollectionMixin, candidate_files
from .analysis_findings import FindingBuilderMixin
from .analysis_gates import GateEvaluationMixin
from .analysis_result import ResultBuilderMixin
from .analysis_roots import RootMetricMixin


class BaseProgressLoopAnalyzer:
    """Base class for analyzers that emit the loop-breaker packet."""

    def run(self) -> dict[str, Any]:
        raise NotImplementedError


class ProgressLoopAnalyzer(
    EvidenceCollectionMixin,
    ProgressAggregationMixin,
    RootMetricMixin,
    GateEvaluationMixin,
    FindingBuilderMixin,
    ResultBuilderMixin,
    BaseProgressLoopAnalyzer,
):
    """Orchestrates loop-breaker evidence collection, gates, findings, and packet rendering."""

    def __init__(
        self,
        root: Path,
        recent: int | None,
        strict: bool,
        goal_productive_threshold: int | None = None,
        root_axis_threshold: int | None = None,
        feature_symbol_threshold: int | None = None,
        terminal_quiescence_threshold: int | None = None,
        terminal_escalation_threshold: int | None = None,
        write_registry: bool = False,
        policy: dict[str, Any] | None = None,
        finalized_cycle_id: str | None = None,
    ) -> None:
        self.root = root
        self.strict = strict
        self.policy = normalize_detector_policy(policy)
        budgets = self.policy["budgets"]
        self.recent = recent if recent is not None else budgets.get("evidence_scope_limit")
        self.recurrence_threshold = budgets.get("recurrence")
        self.goal_productive_threshold = goal_productive_threshold or budgets.get("goal_productive_stale")
        self.root_axis_threshold = root_axis_threshold or budgets.get("root_axis_stall")
        self.feature_symbol_threshold = feature_symbol_threshold or budgets.get("feature_symbol_stall")
        self.terminal_quiescence_threshold = terminal_quiescence_threshold or budgets.get("terminal_quiescence")
        self.terminal_escalation_threshold = terminal_escalation_threshold or budgets.get("terminal_escalation")
        self.detection_only_streak_cap = budgets.get("detection_only_streak")
        self.consolidation_streak_cap = budgets.get("consolidation_streak")
        self.command_surface_threshold = budgets.get("command_surface_count")
        self.metadata_only_window = budgets.get("metadata_only_window")
        self.write_registry = write_registry
        self.finalized_cycle_id = finalized_cycle_id
        self.state: dict[str, Any] = {}

    def run(self) -> dict[str, Any]:
        registry_state = load_symbol_registry_state(self.root, self.finalized_cycle_id)
        self.state = {"policy": self.policy, "registry_state": registry_state}
        self.state["evidence"] = self._collect_evidence() if registry_state["status"] != "block" else []
        self._aggregate_progress()
        self._derive_progress_metrics()
        self._derive_root_metrics()
        self._evaluate_gates()
        self._build_findings()
        self._build_terminal_blocker_candidate()
        return self._build_result()


def analyze(
    root: Path,
    recent: int | None,
    strict: bool,
    goal_productive_threshold: int | None = None,
    root_axis_threshold: int | None = None,
    feature_symbol_threshold: int | None = None,
    terminal_quiescence_threshold: int | None = None,
    terminal_escalation_threshold: int | None = None,
    write_registry: bool = False,
    policy: dict[str, Any] | None = None,
    finalized_cycle_id: str | None = None,
) -> dict[str, Any]:
    return ProgressLoopAnalyzer(
        root,
        recent,
        strict,
        goal_productive_threshold,
        root_axis_threshold,
        feature_symbol_threshold,
        terminal_quiescence_threshold,
        terminal_escalation_threshold,
        write_registry,
        policy,
        finalized_cycle_id,
    ).run()
