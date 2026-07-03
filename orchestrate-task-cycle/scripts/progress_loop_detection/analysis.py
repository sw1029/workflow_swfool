from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import TERMINAL_ESCALATION_STREAK_DEFAULT, TERMINAL_QUIESCENCE_STREAK_DEFAULT
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
        recent: int,
        strict: bool,
        goal_productive_threshold: int,
        root_axis_threshold: int = 6,
        feature_symbol_threshold: int = 6,
        terminal_quiescence_threshold: int = TERMINAL_QUIESCENCE_STREAK_DEFAULT,
        terminal_escalation_threshold: int = TERMINAL_ESCALATION_STREAK_DEFAULT,
        write_registry: bool = False,
    ) -> None:
        self.root = root
        self.recent = recent
        self.strict = strict
        self.goal_productive_threshold = goal_productive_threshold
        self.root_axis_threshold = root_axis_threshold
        self.feature_symbol_threshold = feature_symbol_threshold
        self.terminal_quiescence_threshold = terminal_quiescence_threshold
        self.terminal_escalation_threshold = terminal_escalation_threshold
        self.write_registry = write_registry
        self.state: dict[str, Any] = {}

    def run(self) -> dict[str, Any]:
        self.state = {"evidence": self._collect_evidence()}
        self._aggregate_progress()
        self._derive_progress_metrics()
        self._derive_root_metrics()
        self._evaluate_gates()
        self._build_findings()
        self._build_terminal_blocker_candidate()
        return self._build_result()


def analyze(
    root: Path,
    recent: int,
    strict: bool,
    goal_productive_threshold: int,
    root_axis_threshold: int = 6,
    feature_symbol_threshold: int = 6,
    terminal_quiescence_threshold: int = TERMINAL_QUIESCENCE_STREAK_DEFAULT,
    terminal_escalation_threshold: int = TERMINAL_ESCALATION_STREAK_DEFAULT,
    write_registry: bool = False,
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
    ).run()
