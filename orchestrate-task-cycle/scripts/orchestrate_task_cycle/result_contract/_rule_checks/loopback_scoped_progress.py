from __future__ import annotations

from ..scoped_progress import validate_scoped_progress
from .loopback_state import LoopbackState


def validate_scoped_progress_contract(state: LoopbackState) -> None:
    validate_scoped_progress(state.result, "loopback_audit", state.emit)
