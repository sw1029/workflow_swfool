from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..base import RuleRegistry


@dataclass
class ValidationState:
    target: str
    result: dict[str, Any]
    mode: str
    rule_registry: RuleRegistry
    contract_context: dict[str, Any] | None
    findings: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    severity: str = "warn"
    require_context_field: Callable[[str, str, str], None] | None = None
    explicit_report_key_divergence: bool = False
    auto_report_key_divergences: list[dict[str, Any]] = field(default_factory=list)
    conformance_by_id: Any = None
    conformance_rows: Any = None
    consumer_id: Any = None
    consumer_mismatches: Any = None
    decision_identity: Any = None
    expected_attempt_identity: Any = None
    expected_body_fingerprint: Any = None
    expected_cohort_present: Any = None
    expected_cycle_id: Any = None
    expected_input_fingerprints: Any = None
    expected_input_state_fingerprint: Any = None
    expected_verification_input_ids: Any = None
    invalid_consumers: Any = None
    malformed_conformance_aliases: Any = None
    required_consumer_ids: Any = None
    row: Any = None
    verification_input_values: Any = None
