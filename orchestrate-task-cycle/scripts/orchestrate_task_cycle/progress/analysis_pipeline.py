"""Explicit ordered Strategy pipeline for progress-loop analysis."""

from __future__ import annotations

from collections.abc import Sequence

from .analysis_aggregation import ProgressAggregationStage
from .analysis_context import AnalysisContext, AnalysisStage
from .analysis_evidence import EvidenceCollectionStage
from .analysis_findings import FindingBuilderStage
from .analysis_gates import GateEvaluationStage
from .analysis_result import ResultBuilderStage
from .analysis_roots import RootMetricStage


def default_stages() -> tuple[AnalysisStage, ...]:
    """Build the stable stage order used by the legacy analyzer flow."""

    return (
        EvidenceCollectionStage(),
        ProgressAggregationStage(),
        RootMetricStage(),
        GateEvaluationStage(),
        FindingBuilderStage(),
        ResultBuilderStage(),
    )


class AnalysisPipeline:
    """Run each analysis strategy exactly once in declared order."""

    def __init__(self, stages: Sequence[AnalysisStage] | None = None) -> None:
        self.stages = tuple(stages) if stages is not None else default_stages()

    def run(self, context: AnalysisContext) -> dict[str, object]:
        for stage in self.stages:
            stage.run(context)
        if context.result is None:  # pragma: no cover - static pipeline invariant
            raise RuntimeError("progress analysis pipeline produced no result")
        return context.result


__all__ = ["AnalysisPipeline", "default_stages"]
