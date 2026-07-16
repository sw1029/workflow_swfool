from __future__ import annotations

from typing import Any

from .common import add, boolish, first_present
from .receipts import _full_sha256, _opaque_scalar

def _forward_test_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = first_present(result, ["skill_forward_test", "skill_forward_tests", "validation.skill_forward_test", "result.skill_forward_test"])
    if isinstance(raw, dict):
        rows = raw.get("rows") if isinstance(raw.get("rows"), list) else [raw]
    else:
        rows = raw if isinstance(raw, list) else []
    return [row for row in rows if isinstance(row, dict)]


def validate_advice_consumption_and_forward_tests(
    target: str,
    result: dict[str, Any],
    mode: str,
    findings: list[dict[str, Any]],
) -> None:
    severity = "block" if mode == "block" or target in {"validate", "report"} else "warn"
    raw_states = first_present(result, ["advice_consumption_states", "advice_consumption_state", "consumption_state", "result.advice_consumption_states"])
    malformed_state_rows: list[Any] = []
    if isinstance(raw_states, dict):
        if "rows" in raw_states:
            if isinstance(raw_states.get("rows"), list):
                candidate_rows = raw_states["rows"]
            else:
                candidate_rows = []
                malformed_state_rows.append(raw_states.get("rows"))
        else:
            candidate_rows = [raw_states]
    elif isinstance(raw_states, list):
        candidate_rows = raw_states
    elif raw_states is None:
        candidate_rows = []
    else:
        candidate_rows = []
        malformed_state_rows.append(raw_states)
    state_rows = [row for row in candidate_rows if isinstance(row, dict)]
    malformed_state_rows.extend(row for row in candidate_rows if not isinstance(row, dict))
    if malformed_state_rows:
        positive_malformed = any(
            isinstance(row, str) and row.strip().lower() in {"wired", "verified"}
            for row in malformed_state_rows
        )
        add(
            findings,
            severity if positive_malformed else "warn",
            "advice_consumption_state_unverified",
            "Malformed advice-consumption state cannot establish clause wiring or verification.",
        )
    forward_rows = _forward_test_rows(result)
    forward_by_clause = {
        row["clause_id"].strip(): row
        for row in forward_rows
        if _opaque_scalar(row.get("clause_id"))
    }
    verified_clause_ids: set[str] = set()
    positive_clause_ids: set[str] = set()
    for row in state_rows:
        clause_value = row.get("clause_id") if row.get("clause_id") is not None else row.get("advice_clause_id")
        clause_id = clause_value.strip() if _opaque_scalar(clause_value) else ""
        state = str(row.get("state") or "").strip().lower()
        if state not in {"pending", "wired", "verified"}:
            positive_like_state = isinstance(row.get("state"), str) and row["state"].strip().lower().startswith(("wire", "verif", "complete"))
            add(
                findings,
                severity if positive_like_state else "warn",
                "advice_consumption_state_invalid",
                "Advice clause consumption state is invalid.",
                {"clause_id": clause_id or None},
            )
            continue
        if state in {"wired", "verified"}:
            if clause_id:
                positive_clause_ids.add(clause_id)
            wired = bool(
                clause_id
                and _opaque_scalar(row.get("consumer_context_id") or row.get("consumer_id"))
                and boolish(row.get("invocation_completed"))
                and boolish(row.get("return_contract_valid"))
                and boolish(
                    row.get("consumer_identity_echo_valid")
                    or row.get("identity_echo_valid")
                    or row.get("artifact_identity_echo_valid")
                )
                and boolish(row.get("decision_path_consumed"))
                and _opaque_scalar(row.get("consumer_receipt_ref"))
                and _full_sha256(row.get("consumer_receipt_sha256"))
                and not boolish(row.get("documentation_only"))
                and not boolish(row.get("hook_declared_only"))
            )
            if not wired:
                add(
                    findings,
                    severity,
                    "advice_clause_wired_without_consumer_receipt",
                    "Copied text, task creation, hook declaration, or self-attestation cannot establish wired advice consumption.",
                    {"clause_id": clause_id or None},
                )
        if state == "verified":
            verified_clause_ids.add(clause_id)
            if clause_id not in forward_by_clause:
                add(findings, severity, "advice_clause_verified_without_forward_test", "Verified advice consumption requires a clause-bound forward-test receipt.", {"clause_id": clause_id or None})

    allowed_layer_statuses = {"pass", "passed", "fail", "failed", "not_evaluated", "deferred"}
    for row in forward_rows:
        clause_value = row.get("clause_id")
        scenario_value = row.get("scenario_id")
        clause_id = clause_value.strip() if _opaque_scalar(clause_value) else ""
        scenario_id = scenario_value.strip() if _opaque_scalar(scenario_value) else ""
        positive_claim = clause_id in positive_clause_ids or str(row.get("verification_claim") or "").lower() in {"wired", "verified", "complete"}
        precondition_ids = row.get("precondition_ids")
        preconditions_valid = isinstance(precondition_ids, list) and bool(precondition_ids) and all(
            _opaque_scalar(item) for item in precondition_ids
        )
        injected_fault_valid = _opaque_scalar(row.get("injected_fault_class"))
        expected = row.get("expected_decision_state")
        observed = row.get("observed_decision_state")
        decisions_present = _opaque_scalar(expected) and _opaque_scalar(observed)
        layer_values = {
            key: str(row.get(key) or "").strip().lower()
            for key in ("contract_test_status", "consumer_test_status", "forward_scenario_status", "regression_status")
        }
        invalid_layers = [key for key, value in layer_values.items() if value not in allowed_layer_statuses]
        if not clause_id or not scenario_id or invalid_layers or not preconditions_valid or not injected_fault_valid or not decisions_present:
            add(
                findings,
                severity if positive_claim else "warn",
                "skill_forward_test_malformed",
                "Forward-test rows require clause/scenario IDs, opaque preconditions, an injected fault class, expected/observed decisions, and all four bounded layer statuses.",
                {
                    "clause_id": clause_id or None,
                    "invalid_layers": invalid_layers,
                    "preconditions_valid": preconditions_valid,
                    "injected_fault_valid": injected_fault_valid,
                    "decisions_present": decisions_present,
                },
            )
            continue
        all_pass = all(value in {"pass", "passed"} for value in layer_values.values())
        receipt_valid = _opaque_scalar(row.get("consumer_receipt_ref")) and _full_sha256(row.get("consumer_receipt_sha256"))
        runtime_deferred = str(row.get("runtime_forward_verification") or result.get("runtime_forward_verification") or "").strip() == "deferred_by_explicit_single_skill_constraint"
        positive_claim = clause_id in verified_clause_ids or str(row.get("verification_claim") or "").lower() in {"verified", "complete"}
        if positive_claim and (not all_pass or expected != observed or not receipt_valid or runtime_deferred):
            add(
                findings,
                severity,
                "skill_forward_test_verified_without_full_receipt",
                "A verified claim requires contract, external consumer, negative forward-decision, and happy-path regression evidence bound to the same clause/scenario.",
                {"clause_id": clause_id, "runtime_forward_verification_deferred": runtime_deferred},
            )

