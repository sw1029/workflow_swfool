from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from .common import boolish, deep_get


FULL_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
INVOCATION_KINDS = frozenset({"cli", "api", "ui", "notebook", "remote", "other"})
PREMISE_STATUSES = frozenset({"pass", "fail", "not_evaluated", "not_applicable"})
NON_OBSERVED_STATES = frozenset({"not_evaluated", "not_applicable"})
INVOCATION_COMPONENT_RE = re.compile(
    r"^(?:cmd|subcommand|flag|action|param|ref|mode):[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
)

CONTRACT_PATHS = (
    "acceptance_scenarios",
    "acceptance.acceptance_scenarios",
    "acceptance_scenario_contract.acceptance_scenarios",
    "acceptance_scenario_gate.acceptance_scenarios",
    "result.acceptance_scenarios",
)
RECEIPT_PATHS = (
    "premise_receipts",
    "acceptance_scenario_gate.premise_receipts",
    "run.premise_receipts",
    "run.acceptance_scenario_gate.premise_receipts",
    "result.premise_receipts",
    "result.acceptance_scenario_gate.premise_receipts",
    "scenario_coverage",
    "acceptance_scenario_gate.scenario_coverage",
    "run.scenario_coverage",
    "run.acceptance_scenario_gate.scenario_coverage",
    "validation_set.scenario_coverage",
    "result.scenario_coverage",
    "result.acceptance_scenario_gate.scenario_coverage",
)
REQUIRED_PATHS = (
    "acceptance_scenario_required",
    "scenario_coverage_required",
    "acceptance_scenario_gate.required",
    "result.acceptance_scenario_gate.required",
)


@dataclass(frozen=True, slots=True)
class ScenarioIssue:
    code: str
    row_index: int | None
    scenario_id: str | None
    fields: tuple[str, ...]

    def evidence(self) -> dict[str, Any]:
        evidence: dict[str, Any] = {
            "issue_code": self.code,
            "invalid_fields": list(self.fields),
        }
        if self.row_index is not None:
            evidence["row_index"] = self.row_index
        if self.scenario_id:
            evidence["scenario_id"] = self.scenario_id
        return evidence


@dataclass(frozen=True, slots=True)
class ScenarioContract:
    scenario_id: str
    premise_predicate_id: str
    expected_terminal_state: str


@dataclass(frozen=True, slots=True)
class ReceiptEvaluation:
    scenario_id: str
    premise_passed: bool
    observed_terminal_state: str
    valid: bool


@dataclass(frozen=True, slots=True)
class ParsedReceipt:
    scenario_id: str
    predicate_id: str
    premise_status: str
    count: Any
    invocation_kind: str
    descriptor: Any
    invocation_digest: Any
    component_value: Any
    argv: Any
    input_revisions: tuple[str, ...] | None
    result_digest: Any
    expected_state: str
    observed_state: str
    run_ref: Any
    evidence_ref: Any


@dataclass(frozen=True, slots=True)
class ScenarioReceiptAssessment:
    applicable: bool
    contract_issues: tuple[ScenarioIssue, ...]
    receipt_issues: tuple[ScenarioIssue, ...]
    uncovered_scenario_ids: tuple[str, ...]
    inversion_scenario_ids: tuple[str, ...]


def _first_declared(data: dict[str, Any], paths: tuple[str, ...]) -> tuple[bool, Any]:
    empty_list_declared = False
    for path in paths:
        current: Any = data
        declared = True
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                declared = False
                break
            current = current[part]
        if declared:
            if isinstance(current, list) and not current:
                empty_list_declared = True
                continue
            return True, current
    return (True, []) if empty_list_declared else (False, None)


def _required(data: dict[str, Any]) -> bool:
    return any(boolish(deep_get(data, path)) for path in REQUIRED_PATHS)


def _opaque(value: Any, *, max_length: int = 512) -> bool:
    return bool(
        isinstance(value, str)
        and 0 < len(value.strip()) <= max_length
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _token(value: Any) -> str:
    return value.strip().lower() if _opaque(value, max_length=128) else ""


def _value(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return None


def _opaque_items(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(_opaque(item, max_length=256) for item in value):
        return None
    normalized = tuple(item.strip() for item in value)
    return normalized if len(set(normalized)) == len(normalized) else None


def _invocation_components(
    value: Any, *, invocation_kind: str
) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    if not all(
        isinstance(component, str) and INVOCATION_COMPONENT_RE.fullmatch(component)
        for component in value
    ):
        return None
    components = tuple(value)
    if invocation_kind == "cli":
        if not components[0].startswith("cmd:"):
            return None
        if not all(
            component.startswith(("subcommand:", "flag:", "ref:", "mode:"))
            for component in components[1:]
        ):
            return None
    return components


def canonical_invocation_sha256(
    *,
    scenario_id: str,
    premise_predicate_id: str,
    invocation_kind: str,
    invocation_descriptor_id: str,
    invocation_component_ids: list[str] | tuple[str, ...],
    input_revision_ids: list[str] | tuple[str, ...],
) -> str:
    payload = {
        "contract_version": 1,
        "scenario_id": scenario_id,
        "premise_predicate_id": premise_predicate_id,
        "invocation_kind": invocation_kind,
        "invocation_descriptor_id": invocation_descriptor_id,
        "invocation_component_ids": list(invocation_component_ids),
        "input_revision_ids": list(input_revision_ids),
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _nonnegative_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _scenario_contracts(
    data: dict[str, Any],
) -> tuple[list[ScenarioContract], list[ScenarioIssue]]:
    declared, raw_rows = _first_declared(data, CONTRACT_PATHS)
    issues: list[ScenarioIssue] = []
    contracts: list[ScenarioContract] = []
    if not declared:
        if _required(data):
            issues.append(
                ScenarioIssue(
                    "scenario_contract_missing", None, None, ("acceptance_scenarios",)
                )
            )
        return contracts, issues
    if not isinstance(raw_rows, list):
        return contracts, [
            ScenarioIssue(
                "scenario_contract_malformed", None, None, ("acceptance_scenarios",)
            )
        ]

    seen: set[str] = set()
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            issues.append(
                ScenarioIssue("scenario_contract_malformed", index, None, ("scenario",))
            )
            continue
        applicability = _token(raw_row.get("applicability"))
        if applicability == "not_applicable":
            continue
        invalid: list[str] = []
        if applicability and applicability != "applicable":
            invalid.append("applicability")
        scenario_value = raw_row.get("scenario_id")
        scenario_id = (
            scenario_value.strip() if _opaque(scenario_value, max_length=256) else ""
        )
        predicate_value = _value(raw_row, ("premise_predicate_id", "premise_predicate"))
        predicate_id = (
            predicate_value.strip() if _opaque(predicate_value, max_length=512) else ""
        )
        expected_value = _value(
            raw_row, ("expected_terminal_state", "expected_decision")
        )
        expected_state = _token(expected_value)
        if not scenario_id:
            invalid.append("scenario_id")
        elif scenario_id in seen:
            invalid.append("scenario_id_duplicate")
        if not predicate_id:
            invalid.append("premise_predicate_id")
        if not expected_state:
            invalid.append("expected_terminal_state")
        if invalid:
            issues.append(
                ScenarioIssue(
                    "scenario_contract_malformed",
                    index,
                    scenario_id or None,
                    tuple(sorted(set(invalid))),
                )
            )
            continue
        seen.add(scenario_id)
        contracts.append(ScenarioContract(scenario_id, predicate_id, expected_state))
    return contracts, issues


def _receipt_rows(data: dict[str, Any]) -> tuple[list[Any], list[ScenarioIssue]]:
    declared, raw_rows = _first_declared(data, RECEIPT_PATHS)
    if not declared:
        return [], []
    if not isinstance(raw_rows, list):
        return [], [
            ScenarioIssue(
                "scenario_receipts_malformed", None, None, ("premise_receipts",)
            )
        ]
    return raw_rows, []


def _parse_receipt(raw_row: dict[str, Any]) -> ParsedReceipt:
    scenario_value = raw_row.get("scenario_id")
    predicate_value = _value(raw_row, ("premise_predicate_id", "premise_predicate"))
    return ParsedReceipt(
        scenario_id=(
            scenario_value.strip() if _opaque(scenario_value, max_length=256) else ""
        ),
        predicate_id=(
            predicate_value.strip() if _opaque(predicate_value, max_length=512) else ""
        ),
        premise_status=_token(
            _value(raw_row, ("premise_evaluation_status", "premise_status"))
        ),
        count=raw_row.get("premise_satisfying_item_count"),
        invocation_kind=_token(raw_row.get("invocation_kind")),
        descriptor=_value(raw_row, ("invocation_descriptor_id", "invocation_id")),
        invocation_digest=raw_row.get("canonical_invocation_digest"),
        component_value=_value(
            raw_row,
            ("invocation_component_ids", "canonical_invocation_components"),
        ),
        argv=_value(raw_row, ("command_argv", "body_free_argv", "cli_argv")),
        input_revisions=_opaque_items(raw_row.get("input_revision_ids")),
        result_digest=raw_row.get("result_digest"),
        expected_state=_token(
            _value(raw_row, ("expected_terminal_state", "expected_decision"))
        ),
        observed_state=_token(
            _value(raw_row, ("observed_terminal_state", "observed_decision"))
        ),
        run_ref=_value(raw_row, ("run_id", "run_ref", "execution_run_id")),
        evidence_ref=_value(
            raw_row,
            (
                "evidence_ref",
                "evidence_path",
                "run_evidence_ref",
                "run_argv_evidence_ref",
                "result_evidence_ref",
            ),
        ),
    )


def _evaluate_receipt(
    raw_row: Any,
    row_index: int,
    contract_by_id: dict[str, ScenarioContract],
) -> tuple[ReceiptEvaluation | None, ScenarioIssue | None]:
    if not isinstance(raw_row, dict):
        return None, ScenarioIssue(
            "scenario_receipt_malformed", row_index, None, ("premise_receipt",)
        )

    row = _parse_receipt(raw_row)
    invalid: list[str] = []

    if not row.scenario_id:
        invalid.append("scenario_id")
    if not row.predicate_id:
        invalid.append("premise_predicate_id")
    if row.premise_status not in PREMISE_STATUSES:
        invalid.append("premise_evaluation_status")
    if not _nonnegative_integer(row.count):
        invalid.append("premise_satisfying_item_count")
    elif (row.premise_status == "pass") != (row.count > 0):
        invalid.extend(("premise_evaluation_status", "premise_satisfying_item_count"))
    if "premise_satisfied" in raw_row:
        if not isinstance(raw_row["premise_satisfied"], bool):
            invalid.append("premise_satisfied")
        elif raw_row["premise_satisfied"] != (
            row.premise_status == "pass"
            and _nonnegative_integer(row.count)
            and row.count > 0
        ):
            invalid.append("premise_satisfied")
    if row.invocation_kind not in INVOCATION_KINDS:
        invalid.append("invocation_kind")
    if not _opaque(row.descriptor, max_length=256):
        invalid.append("invocation_descriptor_id")

    components = _invocation_components(
        row.component_value, invocation_kind=row.invocation_kind
    )
    if components is None:
        invalid.append("invocation_component_ids")
    digest_valid = bool(FULL_SHA256.fullmatch(str(row.invocation_digest or "").strip()))
    argv_declared = row.argv is not None
    argv_valid = bool(
        not argv_declared
        or (
            row.invocation_kind == "cli"
            and components is not None
            and isinstance(row.argv, list)
            and row.argv == list(components)
        )
    )
    if not argv_valid:
        invalid.append("command_argv")
    if row.input_revisions is None:
        invalid.append("input_revision_ids")
    if digest_valid and components is not None and row.input_revisions is not None:
        expected_invocation_digest = canonical_invocation_sha256(
            scenario_id=row.scenario_id,
            premise_predicate_id=row.predicate_id,
            invocation_kind=row.invocation_kind,
            invocation_descriptor_id=str(row.descriptor or ""),
            invocation_component_ids=components,
            input_revision_ids=row.input_revisions,
        )
        digest_valid = (
            str(row.invocation_digest).strip().lower().removeprefix("sha256:")
            == expected_invocation_digest
        )
    if not digest_valid:
        invalid.append("canonical_invocation_digest")
    if not FULL_SHA256.fullmatch(str(row.result_digest or "").strip()):
        invalid.append("result_digest")
    if not row.expected_state:
        invalid.append("expected_terminal_state")
    if not row.observed_state:
        invalid.append("observed_terminal_state")
    if not _opaque(row.run_ref, max_length=512):
        invalid.append("run_id")
    if not _opaque(row.evidence_ref, max_length=512):
        invalid.append("evidence_ref")

    contract = contract_by_id.get(row.scenario_id)
    if contract_by_id and contract is None:
        invalid.append("scenario_id_binding")
    elif contract is not None:
        if row.predicate_id != contract.premise_predicate_id:
            invalid.append("premise_predicate_id_binding")
        if row.expected_state != contract.expected_terminal_state:
            invalid.append("expected_terminal_state_binding")

    issue = None
    if invalid:
        issue = ScenarioIssue(
            "scenario_receipt_malformed",
            row_index,
            row.scenario_id or None,
            tuple(sorted(set(invalid))),
        )
    evaluation = ReceiptEvaluation(
        scenario_id=row.scenario_id,
        premise_passed=row.premise_status == "pass"
        and _nonnegative_integer(row.count)
        and row.count > 0,
        observed_terminal_state=row.observed_state,
        valid=not invalid,
    )
    return evaluation, issue


def assess_scenario_receipts(data: dict[str, Any]) -> ScenarioReceiptAssessment:
    contracts, contract_issues = _scenario_contracts(data)
    raw_receipts, receipt_issues = _receipt_rows(data)
    contract_by_id = {contract.scenario_id: contract for contract in contracts}
    evaluations: list[ReceiptEvaluation] = []
    for index, raw_receipt in enumerate(raw_receipts):
        evaluation, issue = _evaluate_receipt(raw_receipt, index, contract_by_id)
        if evaluation is not None:
            evaluations.append(evaluation)
        if issue is not None:
            receipt_issues.append(issue)

    uncovered: set[str] = set()
    inversions: set[str] = set()
    for contract in contracts:
        matching = [
            row
            for row in evaluations
            if row.valid
            and row.premise_passed
            and row.scenario_id == contract.scenario_id
        ]
        if not any(
            row.observed_terminal_state == contract.expected_terminal_state
            for row in matching
        ):
            uncovered.add(contract.scenario_id)
        if any(
            row.observed_terminal_state not in NON_OBSERVED_STATES
            and row.observed_terminal_state != contract.expected_terminal_state
            for row in matching
        ):
            inversions.add(contract.scenario_id)

    applicable = bool(contracts or contract_issues or _required(data))
    return ScenarioReceiptAssessment(
        applicable=applicable,
        contract_issues=tuple(contract_issues),
        receipt_issues=tuple(receipt_issues),
        uncovered_scenario_ids=tuple(sorted(uncovered)),
        inversion_scenario_ids=tuple(sorted(inversions)),
    )
