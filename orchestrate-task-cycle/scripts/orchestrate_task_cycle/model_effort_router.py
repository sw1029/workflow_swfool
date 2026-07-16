"""Public facade for governed model/effort routing."""

from .model_effort.cli import main
from .model_effort.policy import (
    EVIDENCE_ID_FIELDS,
    MODEL_REF_PREFIX,
    POLICY_PATH,
    evidence_present,
    load_json_arg,
    load_policy,
    normalized_signals,
    receipt_hash,
    resolve_model_binding,
    rule_matches,
    sanitized_evidence_reference,
    sanitized_prior_tier5_evidence,
    valid_evidence_reference,
    valid_prior_tier5_evidence,
    validate_policy,
)
from .model_effort.routing import select_route
from .model_effort.validation import validate_claim

__all__ = [
    "EVIDENCE_ID_FIELDS",
    "MODEL_REF_PREFIX",
    "POLICY_PATH",
    "evidence_present",
    "load_json_arg",
    "load_policy",
    "main",
    "normalized_signals",
    "receipt_hash",
    "resolve_model_binding",
    "rule_matches",
    "sanitized_evidence_reference",
    "sanitized_prior_tier5_evidence",
    "select_route",
    "valid_evidence_reference",
    "valid_prior_tier5_evidence",
    "validate_claim",
    "validate_policy",
]


if __name__ == "__main__":
    raise SystemExit(main())
