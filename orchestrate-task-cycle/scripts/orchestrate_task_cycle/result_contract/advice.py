from __future__ import annotations

from typing import Any

from .advice_completeness import validate_expected_advice_completeness
from .advice_receipts import (
    advice_consumer_receipt_valid,
    advice_forward_path_receipt_valid,
    expected_advice_decision_identity_echo,
)
from .advice_regression import validate_unconsumed_regression
from .common import add, first_present
from .receipts import _opaque_scalar


def _forward_test_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = first_present(
        result,
        [
            "skill_forward_test",
            "skill_forward_tests",
            "validation.skill_forward_test",
            "result.skill_forward_test",
        ],
    )
    if isinstance(raw, dict):
        rows = raw.get("rows") if isinstance(raw.get("rows"), list) else [raw]
    else:
        rows = raw if isinstance(raw, list) else []
    return [row for row in rows if isinstance(row, dict)]


def _consumption_rows(result: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
    raw = first_present(
        result,
        [
            "advice_consumption_states",
            "advice_consumption_state",
            "consumption_state",
            "result.advice_consumption_states",
        ],
    )
    malformed: list[Any] = []
    if isinstance(raw, dict):
        if "rows" in raw:
            candidates = raw["rows"] if isinstance(raw.get("rows"), list) else []
            if not isinstance(raw.get("rows"), list):
                malformed.append(raw.get("rows"))
        else:
            candidates = [raw]
    elif isinstance(raw, list):
        candidates = raw
    elif raw is None:
        candidates = []
    else:
        candidates = []
        malformed.append(raw)
    malformed.extend(row for row in candidates if not isinstance(row, dict))
    return [row for row in candidates if isinstance(row, dict)], malformed


def _validate_consumption_rows(
    result: dict[str, Any],
    severity: str,
    findings: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, str], set[str]]:
    rows, malformed = _consumption_rows(result)
    if malformed:
        positive = any(
            isinstance(row, str) and row.strip().lower() in {"wired", "verified"}
            for row in malformed
        )
        add(
            findings,
            severity if positive else "warn",
            "advice_consumption_state_unverified",
            "Malformed advice-consumption state cannot establish clause wiring or verification.",
        )
    expected_identity = expected_advice_decision_identity_echo(result)
    state_by_clause: dict[str, str] = {}
    claimed_state_by_clause: dict[str, str] = {}
    verified: set[str] = set()
    for row in rows:
        raw_clause = row.get("clause_id") or row.get("advice_clause_id")
        clause_id = raw_clause.strip() if _opaque_scalar(raw_clause) else ""
        state = str(row.get("state") or "").strip().lower()
        if not clause_id or state not in {"pending", "wired", "verified"}:
            positive = state.startswith(("wire", "verif", "complete"))
            add(
                findings,
                severity if positive else "warn",
                "advice_consumption_state_invalid",
                "Advice clause consumption requires an opaque clause ID and pending, wired, or verified state.",
                {"clause_id": clause_id or None},
            )
            continue
        prior = claimed_state_by_clause.get(clause_id)
        if prior and prior != state:
            add(
                findings,
                severity,
                "advice_consumption_state_conflict",
                "One decision packet cannot claim conflicting states for the same advice clause.",
                {"clause_id": clause_id},
            )
        claimed_state_by_clause[clause_id] = state
        receipt_valid = state == "pending" or advice_consumer_receipt_valid(
            row, expected_identity, result, context
        )
        state_by_clause[clause_id] = state if receipt_valid else "pending"
        if state in {"wired", "verified"} and not receipt_valid:
            add(
                findings,
                severity,
                "advice_clause_wired_without_consumer_receipt",
                "Wired advice consumption requires identity-echoed decision use plus reopened, exact cycle-local lens and synthesis artifacts.",
                {"clause_id": clause_id},
            )
        if state == "verified":
            verified.add(clause_id)
    return state_by_clause, verified


def _forward_receipts_separated(happy: Any, negative: Any) -> bool:
    if not isinstance(happy, dict) or not isinstance(negative, dict):
        return False
    happy_artifact = happy.get("producer_artifact")
    negative_artifact = negative.get("producer_artifact")
    happy_verifier = happy.get("independent_verification_receipt")
    negative_verifier = negative.get("independent_verification_receipt")
    role_ids = [
        container.get(field)
        for container, field in (
            (happy_artifact, "producer_agent_id"),
            (negative_artifact, "producer_agent_id"),
            (happy_verifier, "verifier_agent_id"),
            (negative_verifier, "verifier_agent_id"),
            (happy_verifier, "invariant_owner_id"),
            (negative_verifier, "invariant_owner_id"),
        )
        if isinstance(container, dict) and container.get(field)
    ]
    receipt_ids = [
        container.get(field)
        for container, field in (
            (happy_artifact, "producer_receipt_id"),
            (negative_artifact, "producer_receipt_id"),
            (happy_verifier, "verifier_receipt_id"),
            (negative_verifier, "verifier_receipt_id"),
        )
        if isinstance(container, dict) and container.get(field)
    ]
    return bool(
        happy.get("receipt_ref") != negative.get("receipt_ref")
        and happy.get("receipt_sha256") != negative.get("receipt_sha256")
        and len(role_ids) == 6
        and len(set(role_ids)) == 6
        and len(receipt_ids) == 4
        and len(set(receipt_ids)) == 4
    )


def _forward_row_shape(
    row: dict[str, Any], verified: set[str]
) -> tuple[str, bool, dict[str, str], bool]:
    clause_id = str(row.get("clause_id") or "").strip()
    positive = clause_id in verified or str(
        row.get("verification_claim") or ""
    ).lower() in {"verified", "complete"}
    layers = {
        key: str(row.get(key) or "").strip().lower()
        for key in (
            "contract_test_status",
            "consumer_test_status",
            "forward_scenario_status",
            "regression_status",
        )
    }
    allowed = {"pass", "passed", "fail", "failed", "not_evaluated", "deferred"}
    preconditions = row.get("precondition_ids")
    malformed = (
        not _opaque_scalar(clause_id)
        or not _opaque_scalar(str(row.get("scenario_id") or "").strip())
        or not isinstance(preconditions, list)
        or not preconditions
        or not all(_opaque_scalar(item) for item in preconditions)
        or any(
            not _opaque_scalar(row.get(field))
            for field in (
                "injected_fault_class",
                "expected_decision_state",
                "observed_decision_state",
                "happy_expected_decision_state",
                "happy_observed_decision_state",
            )
        )
        or any(value not in allowed for value in layers.values())
    )
    return clause_id, positive, layers, malformed


def _validate_forward_row(
    result: dict[str, Any],
    row: dict[str, Any],
    verified: set[str],
    severity: str,
    findings: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> None:
    clause_id, positive, layers, malformed = _forward_row_shape(row, verified)
    if malformed:
        add(
            findings,
            severity if positive else "warn",
            "skill_forward_test_malformed",
            "Forward tests require clause/scenario IDs, opaque preconditions and fault class, and four bounded layer statuses.",
            {"clause_id": clause_id or None},
        )
        return
    expected_identity = expected_advice_decision_identity_echo(result)
    happy = row.get("happy_path_receipt")
    negative = row.get("negative_path_receipt")
    validity = {
        path_kind: advice_forward_path_receipt_valid(
            row,
            receipt,
            path_kind=path_kind,
            expected_identity_echo=expected_identity,
            result=result,
            context=context,
        )
        for path_kind, receipt in (("happy", happy), ("negative", negative))
    }
    separated = _forward_receipts_separated(happy, negative)
    boundary_distinct = bool(
        row.get("expected_decision_state") != row.get("happy_expected_decision_state")
        and row.get("observed_decision_state")
        != row.get("happy_observed_decision_state")
    )
    runtime_deferred = (
        str(
            row.get("runtime_forward_verification")
            or result.get("runtime_forward_verification")
            or ""
        ).strip()
        == "deferred_by_explicit_single_skill_constraint"
    )
    all_pass = all(value in {"pass", "passed"} for value in layers.values())
    if positive and (
        not all_pass
        or not all(validity.values())
        or not separated
        or not boundary_distinct
        or runtime_deferred
    ):
        add(
            findings,
            severity,
            "skill_forward_test_verified_without_full_receipt",
            "Verified advice requires reopened happy and negative runtime artifacts, exact decision-identity echoes, and a non-vacuous decision boundary.",
            {
                "clause_id": clause_id,
                "happy_receipt_valid": validity["happy"],
                "negative_receipt_valid": validity["negative"],
                "receipts_separated": separated,
                "decision_boundary_distinct": boundary_distinct,
                "runtime_forward_verification_deferred": runtime_deferred,
            },
        )


def _validate_forward_rows(
    result: dict[str, Any],
    verified: set[str],
    severity: str,
    findings: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> None:
    rows = _forward_test_rows(result)
    clauses_with_rows = {
        str(row.get("clause_id") or "").strip()
        for row in rows
        if _opaque_scalar(row.get("clause_id"))
    }
    for clause_id in sorted(verified - clauses_with_rows):
        add(
            findings,
            severity,
            "advice_clause_verified_without_forward_test",
            "Verified advice consumption requires a clause-bound forward-test receipt.",
            {"clause_id": clause_id},
        )
    for row in rows:
        _validate_forward_row(result, row, verified, severity, findings, context)


def validate_advice_consumption_and_forward_tests(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> None:
    severity = (
        "block" if mode == "block" or target in {"validate", "report"} else "warn"
    )
    rows, _ = _consumption_rows(result)
    validate_expected_advice_completeness(
        target, result, context, rows, severity, findings
    )
    state_by_clause, verified = _validate_consumption_rows(
        result, severity, findings, context
    )
    _validate_forward_rows(result, verified, severity, findings, context)
    validate_unconsumed_regression(result, state_by_clause, findings)
