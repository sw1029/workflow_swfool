#!/usr/bin/env python3
# Compatibility facade: imported names intentionally preserve the legacy
# module surface while implementations live in focused modules.
# ruff: noqa: F401
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from result_contract_lib.advice import (  # noqa: E402
    _forward_test_rows,
    validate_advice_consumption_and_forward_tests,
)
from result_contract_lib.base import RuleContext, RuleRegistry  # noqa: E402
from result_contract_lib.common import (  # noqa: E402
    ADVICE_REQUIRED_TARGETS,
    AGENT_ROUTING_TARGETS,
    CANONICAL_LEDGER_STEPS,
    COMMON_FIELDS,
    MODEL_EFFORT_POLICY,
    MODEL_EFFORT_ROUTER,
    ROUTING_ENFORCEMENT_VALUES,
    SUPPORTED_AGENT_EFFORTS,
    SUPPORTED_AGENT_MODELS,
    TARGETS,
    active_advice_present,
    actual_report_body_divergences,
    add,
    advice_handling_rationale_present,
    boolish,
    first_present,
    has_value,
    list_values,
    load_json,
    non_empty,
    report_key_divergences,
    report_key_duplicate_matches,
    value_for,
)
from result_contract_lib.decision import (  # noqa: E402
    COUPLING_STATUSES,
    DECISION_TARGETS,
    EVIDENCE_PROVENANCE_STATUSES,
    validate_decision_identity_and_compatibility,
    validate_verification_axes,
)
from result_contract_lib.engine import SESSION_AUDIT_RULE, _validate  # noqa: E402
from result_contract_lib.finalization import validate_finalization_contract  # noqa: E402
from result_contract_lib.expectations import (  # noqa: E402
    validate_state_projection,
    validate_task_pack_expectation_comparison,
)
from result_contract_lib.metric_consumption import validate_metric_applicability_consumption  # noqa: E402
from result_contract_lib.lifecycle import validate_lifecycle_extensions  # noqa: E402
from result_contract_lib.policy import (  # noqa: E402
    PENDING_LONG_RUN_STATUSES,
    has_explicit_empty,
    long_run_state_checked,
    pending_long_run_context,
    reasoned_na_allows_explicit_empty,
)
from result_contract_lib.receipts import (  # noqa: E402
    _consumer_receipt_binding_sha256,
    _consumer_receipt_pass,
    _declared_values,
    _finite_numeric,
    _full_sha256,
    _metric_gate_signature,
    _normalized_verdict_status,
    _opaque_scalar,
    _opaque_string_items,
    _positive_decision_claim,
)
from result_contract_lib.registry import default_rule_registry  # noqa: E402
from result_contract_lib.rules.session_audit import SessionAuditRule  # noqa: E402
from result_contract_lib.verdicts import (  # noqa: E402
    VERDICT_AXES,
    VERDICT_AXIS_STATUSES,
    validate_verdict_axes,
)


class ResultContractValidator:
    """Reusable validator with an injectable target-rule registry."""

    def __init__(self, rule_registry: RuleRegistry | None = None) -> None:
        self.rule_registry = rule_registry or default_rule_registry()

    def validate(
        self,
        target: str,
        result: dict[str, Any],
        mode: str = "warn",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if target not in TARGETS:
            raise ValueError(f"unsupported result-contract target: {target}")
        if mode not in {"warn", "block"}:
            raise ValueError(f"unsupported result-contract mode: {mode}")
        return _validate(target, result, mode, self.rule_registry, context)


DEFAULT_VALIDATOR = ResultContractValidator()


def validate(
    target: str,
    result: dict[str, Any],
    mode: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Backward-compatible functional facade."""

    return DEFAULT_VALIDATOR.validate(target, result, mode, context)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a subskill result contract for orchestrate-task-cycle.")
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--result", default="-", help="Result JSON path, JSON string, or '-' for stdin.")
    parser.add_argument("--context", help="Optional cycle/long-run context JSON path or JSON string.")
    parser.add_argument("--mode", choices=("warn", "block"), default="warn")
    args = parser.parse_args(argv)

    contract_context = load_json(args.context) if args.context else None
    output = validate(args.target, load_json(args.result), args.mode, contract_context)
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "block" else 2


if __name__ == "__main__":
    raise SystemExit(main())
