"""Report-integrity public facade."""

# Compatibility facade intentionally re-exports imported symbols.
# ruff: noqa: F401

from ._integrity.body import actual_report_body_divergences
from ._integrity.core import (
    ACTUAL_CONTEXT_KEYS,
    IDENTITY_SCALAR_MAX_LENGTH,
    PROJECTION_FINGERPRINT_KEYS,
    REPORT_CONTEXT_KEYS,
    REPORT_DUPLICATE_KEY_EXCLUSIONS,
    _first_text,
    _report_root_name,
    bounded_scalar_text,
    canonical_encoded,
    collect_actual_roots,
    collect_report_roots,
    collect_terminal_key_values,
    identity_divergence_evidence,
    is_report_context_key,
    opaque_binding_evidence,
    opaque_fingerprint,
    projected_field_contract_supplied,
    projected_field_ids,
    projection_artifact_id,
    projection_fingerprint,
    report_integrity_required,
    scoped_report_roots,
)
from ._integrity.report import (
    cross_report_projection_values,
    report_key_divergences,
    report_key_duplicate_matches,
    scalar_leaves,
)


__all__ = [
    "ACTUAL_CONTEXT_KEYS",
    "IDENTITY_SCALAR_MAX_LENGTH",
    "PROJECTION_FINGERPRINT_KEYS",
    "REPORT_CONTEXT_KEYS",
    "REPORT_DUPLICATE_KEY_EXCLUSIONS",
    "actual_report_body_divergences",
    "bounded_scalar_text",
    "canonical_encoded",
    "collect_actual_roots",
    "collect_report_roots",
    "collect_terminal_key_values",
    "cross_report_projection_values",
    "identity_divergence_evidence",
    "is_report_context_key",
    "opaque_binding_evidence",
    "opaque_fingerprint",
    "projected_field_contract_supplied",
    "projected_field_ids",
    "projection_artifact_id",
    "projection_fingerprint",
    "report_integrity_required",
    "report_key_divergences",
    "report_key_duplicate_matches",
    "scalar_leaves",
    "scoped_report_roots",
]
