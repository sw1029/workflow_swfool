"""Deterministic stage preparation and result compilation facade."""

from .builder import ResultBuilder
from .service import advance_stage, prepare_stage, submit_stage
from .specs import TARGET_COMPILE_SPECS, TargetCompileSpec

__all__ = [
    "ResultBuilder",
    "TARGET_COMPILE_SPECS",
    "TargetCompileSpec",
    "advance_stage",
    "prepare_stage",
    "submit_stage",
]
