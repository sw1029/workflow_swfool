from __future__ import annotations

from .runtime_dependencies import (
    Any,
    argparse,
)

from .evaluation_decision import _evaluate_decision_runtime
from .evaluation_failure import _evaluate_failure_runtime
from .evaluation_finalize import _finalize_evaluation
from .evaluation_progress import _evaluate_progress_runtime
from .evaluation_setup import _prepare_evaluation


def _evaluate_impl(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    frame = _prepare_evaluation(args)
    _evaluate_failure_runtime(frame)
    _evaluate_progress_runtime(frame)
    _evaluate_decision_runtime(frame)
    return _finalize_evaluation(frame)


class LoopbackEvaluator:
    def evaluate(self, args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        return _evaluate_impl(args)


def evaluate(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    return LoopbackEvaluator().evaluate(args)
