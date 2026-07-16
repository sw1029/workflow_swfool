from __future__ import annotations

from .evaluation_frame import _EvaluationFrame
from .evaluation_stages.failure_baseline import _evaluate_failure_baseline
from .evaluation_stages.failure_family import _evaluate_failure_family
from .evaluation_stages.failure_surface import _evaluate_failure_surface
from .evaluation_stages.failure_diagnostics import _evaluate_failure_diagnostics
from .evaluation_stages.failure_metrics import _evaluate_failure_metrics
from .evaluation_stages.failure_provenance import _evaluate_failure_provenance
from .evaluation_stages.failure_consumer import _evaluate_failure_consumer


def _evaluate_failure_runtime(frame: _EvaluationFrame) -> None:
    _evaluate_failure_baseline(frame)
    _evaluate_failure_family(frame)
    _evaluate_failure_surface(frame)
    _evaluate_failure_diagnostics(frame)
    _evaluate_failure_metrics(frame)
    _evaluate_failure_provenance(frame)
    _evaluate_failure_consumer(frame)
