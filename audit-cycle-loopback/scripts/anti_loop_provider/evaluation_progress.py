from __future__ import annotations

from .evaluation_frame import _EvaluationFrame
from .evaluation_stages.progress_evidence import _evaluate_progress_evidence
from .evaluation_stages.progress_reachability import _evaluate_progress_reachability
from .evaluation_stages.progress_measurement import _evaluate_progress_measurement
from .evaluation_stages.progress_blocker import _evaluate_progress_blocker
from .evaluation_stages.progress_semantics import _evaluate_progress_semantics
from .evaluation_stages.progress_correction import _evaluate_progress_correction
from .evaluation_stages.progress_adapter_demand import _evaluate_progress_adapter_demand
from .evaluation_stages.progress_chain import _evaluate_progress_chain
from .evaluation_stages.progress_primary_metric import _evaluate_progress_primary_metric


def _evaluate_progress_runtime(frame: _EvaluationFrame) -> None:
    _evaluate_progress_evidence(frame)
    _evaluate_progress_reachability(frame)
    _evaluate_progress_measurement(frame)
    _evaluate_progress_blocker(frame)
    _evaluate_progress_semantics(frame)
    _evaluate_progress_correction(frame)
    _evaluate_progress_adapter_demand(frame)
    _evaluate_progress_chain(frame)
    _evaluate_progress_primary_metric(frame)
