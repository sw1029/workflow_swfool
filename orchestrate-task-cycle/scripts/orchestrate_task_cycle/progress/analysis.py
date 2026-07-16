"""Composable progress-loop analyzer with a stable public entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .analysis_aggregation import ProgressAggregationMixin
from .analysis_context import AnalysisContext
from .analysis_evidence import EvidenceCollectionMixin, candidate_files as candidate_files
from .analysis_findings import FindingBuilderMixin
from .analysis_gates import GateEvaluationMixin
from .analysis_pipeline import AnalysisPipeline
from .analysis_result import ResultBuilderMixin
from .analysis_roots import RootMetricMixin
from .values import normalize_detector_policy


class BaseProgressLoopAnalyzer:
    """Base class for analyzers that emit the loop-breaker packet."""

    def run(self) -> dict[str, Any]:
        raise NotImplementedError


class ProgressLoopAnalyzer(BaseProgressLoopAnalyzer):
    """Coordinate the explicit ordered analysis-stage pipeline."""

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
        self.goal_productive_threshold = (
            goal_productive_threshold or budgets.get("goal_productive_stale")
        )
        self.root_axis_threshold = root_axis_threshold or budgets.get("root_axis_stall")
        self.feature_symbol_threshold = (
            feature_symbol_threshold or budgets.get("feature_symbol_stall")
        )
        self.terminal_quiescence_threshold = (
            terminal_quiescence_threshold or budgets.get("terminal_quiescence")
        )
        self.terminal_escalation_threshold = (
            terminal_escalation_threshold or budgets.get("terminal_escalation")
        )
        self.detection_only_streak_cap = budgets.get("detection_only_streak")
        self.consolidation_streak_cap = budgets.get("consolidation_streak")
        self.command_surface_threshold = budgets.get("command_surface_count")
        self.metadata_only_window = budgets.get("metadata_only_window")
        self.write_registry = write_registry
        self.finalized_cycle_id = finalized_cycle_id
        self.state: dict[str, Any] = {}
        self.pipeline = AnalysisPipeline()

    def _context(self) -> AnalysisContext:
        return AnalysisContext(
            root=self.root,
            recent=self.recent,
            strict=self.strict,
            policy=self.policy,
            recurrence_threshold=self.recurrence_threshold,
            goal_productive_threshold=self.goal_productive_threshold,
            root_axis_threshold=self.root_axis_threshold,
            feature_symbol_threshold=self.feature_symbol_threshold,
            terminal_quiescence_threshold=self.terminal_quiescence_threshold,
            terminal_escalation_threshold=self.terminal_escalation_threshold,
            detection_only_streak_cap=self.detection_only_streak_cap,
            consolidation_streak_cap=self.consolidation_streak_cap,
            command_surface_threshold=self.command_surface_threshold,
            metadata_only_window=self.metadata_only_window,
            write_registry=self.write_registry,
            finalized_cycle_id=self.finalized_cycle_id,
            state=self.state,
        )

    def run(self) -> dict[str, Any]:
        self.state = {}
        context = self._context()
        result = self.pipeline.run(context)
        self.state = context.state
        return result


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


__all__ = [
    "BaseProgressLoopAnalyzer",
    "EvidenceCollectionMixin",
    "FindingBuilderMixin",
    "GateEvaluationMixin",
    "ProgressAggregationMixin",
    "ProgressLoopAnalyzer",
    "ResultBuilderMixin",
    "RootMetricMixin",
    "analyze",
    "candidate_files",
]
