"""Deterministic repository adapter architecture inspection contracts."""

from .adjudication import adjudicate_architecture
from .cache import architecture_cache_fingerprint, validate_cache_receipt
from .facts import compile_architecture_facts
from .native import build_adapter_validation_packet, build_code_structure_packet
from .semantic_receipt import validate_semantic_receipt

__all__ = (
    "adjudicate_architecture",
    "architecture_cache_fingerprint",
    "build_adapter_validation_packet",
    "build_code_structure_packet",
    "compile_architecture_facts",
    "validate_cache_receipt",
    "validate_semantic_receipt",
)
