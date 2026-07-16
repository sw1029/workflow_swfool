from __future__ import annotations

from .evaluation_frame import _EvaluationFrame
from .evaluation_stages.decision_primary_metric import _evaluate_decision_primary_metric
from .evaluation_stages.decision_retarget import _evaluate_decision_retarget
from .evaluation_stages.decision_disposition import _evaluate_decision_disposition
from .evaluation_stages.decision_verifier import _evaluate_decision_verifier
from .evaluation_stages.decision_task_options import _evaluate_decision_task_options


def _evaluate_decision_runtime(frame: _EvaluationFrame) -> None:
    _evaluate_decision_primary_metric(frame)
    _evaluate_decision_retarget(frame)
    _evaluate_decision_disposition(frame)
    _evaluate_decision_verifier(frame)
    _evaluate_decision_task_options(frame)
