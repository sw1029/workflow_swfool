from __future__ import annotations

from .runtime_dependencies import (
    argparse,
    reset_adapter_invocation_receipts,
)

from .evaluation_frame import _EvaluationFrame
from .evaluation_stages.setup_registry import _prepare_registry_state
from .evaluation_stages.setup_artifact import _prepare_artifact_state
from .evaluation_stages.setup_budgets import _prepare_budget_state
from .evaluation_stages.setup_adapter import _prepare_adapter_state
from .evaluation_stages.setup_quality import _prepare_quality_state
from .evaluation_stages.setup_external_gates import _prepare_external_gates
from .evaluation_stages.setup_identity import _prepare_initial_identity
from .evaluation_stages.setup_consumer import _prepare_consumer_probe


def _prepare_evaluation(args: argparse.Namespace) -> _EvaluationFrame:
    reset_adapter_invocation_receipts()
    frame = _EvaluationFrame({"args": args})
    _prepare_registry_state(frame)
    _prepare_artifact_state(frame)
    _prepare_budget_state(frame)
    _prepare_adapter_state(frame)
    _prepare_quality_state(frame)
    _prepare_external_gates(frame)
    _prepare_initial_identity(frame)
    _prepare_consumer_probe(frame)
    return frame
