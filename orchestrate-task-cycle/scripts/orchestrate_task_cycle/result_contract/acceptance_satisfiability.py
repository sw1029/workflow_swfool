"""Independently verify predicate/directive satisfiability claims.

The acceptance normalizer owns production of these rows.  Result-contract
consumers recompute them from the raw predicate and producer directives so a
caller cannot replace an unsatisfied contract with a self-attested ``pass``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STATUSES = frozenset({"pass", "fail", "not_evaluated"})


@dataclass(frozen=True, slots=True)
class SatisfiabilityAssessment:
    present: bool
    expected_rows: tuple[dict[str, Any], ...]
    supplied_rows_match: bool
    supplied_conflict_matches: bool
    supplied_unverifiable_matches: bool
    mutually_unsatisfiable: bool
    unverifiable: bool


def _normalized_strings(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        return None
    return sorted({item.strip() for item in value})


def _records(value: Any, plural_key: str) -> list[dict[str, Any]] | None:
    if isinstance(value, dict) and isinstance(value.get(plural_key), list):
        rows = value[plural_key]
    elif isinstance(value, list):
        rows = value
    elif isinstance(value, dict):
        rows = [value]
    else:
        return None
    if any(not isinstance(row, dict) for row in rows):
        return None
    return rows


def _base_row(evidence_refs: list[str]) -> dict[str, Any]:
    return {
        "criterion_id": "not_evaluated",
        "predicate_id": "not_evaluated",
        "producer_directive_id": "not_evaluated",
        "affected_output_classes": [],
        "evaluation_status": "not_evaluated",
        "conflict_class": "mapping_missing",
        "local_repair_possible": "not_evaluated",
        "evidence_refs": evidence_refs,
    }


def _expected_row(
    criterion: dict[str, Any],
    directive: dict[str, Any] | None,
    evidence_refs: list[str],
) -> dict[str, Any]:
    row = _base_row(evidence_refs)
    missing: list[str] = []
    for source, target in (
        ("criterion_id", "criterion_id"),
        ("predicate_id", "predicate_id"),
    ):
        value = criterion.get(source)
        if isinstance(value, str) and value.strip():
            row[target] = value.strip()
        else:
            missing.append(source)
    if directive is None:
        missing.append("producer_directive_binding")
        row["missing_mappings"] = missing
        return row

    directive_id = directive.get("producer_directive_id")
    if isinstance(directive_id, str) and directive_id.strip():
        row["producer_directive_id"] = directive_id.strip()
    else:
        missing.append("producer_directive_id")

    owners = {
        "required_output_classes": criterion,
        "required_non_empty_output_classes": criterion,
        "required_mutation_surfaces": criterion,
        "required_verifier_input_classes": criterion,
        "permitted_output_classes": directive,
        "guaranteed_non_empty_output_classes": directive,
        "allowed_task_mutation_surfaces": directive,
        "verifier_observable_output_classes": directive,
        "satisfying_execution_paths": directive,
    }
    values: dict[str, list[str]] = {}
    for field, owner in owners.items():
        normalized = _normalized_strings(owner.get(field))
        if normalized is None:
            missing.append(field)
            values[field] = []
        else:
            values[field] = normalized
    row["affected_output_classes"] = sorted(
        set(values["required_output_classes"])
        | set(values["required_non_empty_output_classes"])
    )

    freshness = criterion.get("required_freshness_class")
    if not isinstance(freshness, str) or not freshness.strip():
        missing.append("required_freshness_class")
        freshness = "not_evaluated"
    else:
        freshness = freshness.strip()
    execution_allowed = directive.get("producer_execution_allowed")
    if freshness == "fresh_producer_execution" and type(execution_allowed) is not bool:
        missing.append("producer_execution_allowed")
    body_movement = criterion.get("requires_body_movement")
    if type(body_movement) is not bool:
        missing.append("requires_body_movement")
    body_mutation_allowed = directive.get("body_mutation_allowed")
    if body_movement is True and type(body_mutation_allowed) is not bool:
        missing.append("body_mutation_allowed")

    conflicts: list[str] = []
    comparisons = (
        (
            "required_output_classes",
            "permitted_output_classes",
            "required_output_prohibited",
        ),
        (
            "required_non_empty_output_classes",
            "guaranteed_non_empty_output_classes",
            "non_empty_population_unproducible",
        ),
        (
            "required_mutation_surfaces",
            "allowed_task_mutation_surfaces",
            "required_mutation_surface_forbidden",
        ),
    )
    for required, supplied, conflict in comparisons:
        if set(values[required]) - set(values[supplied]):
            conflicts.append(conflict)
    if freshness == "fresh_producer_execution" and execution_allowed is False:
        conflicts.append("fresh_producer_execution_forbidden")
    if body_movement is True and body_mutation_allowed is False:
        conflicts.append("body_movement_forbidden")

    verifier_unobserved = set(values["required_verifier_input_classes"]) - set(
        values["verifier_observable_output_classes"]
    )
    if verifier_unobserved:
        missing.append("required_verifier_input_unobservable")
    if not values["satisfying_execution_paths"]:
        missing.append("satisfying_execution_path")

    if conflicts:
        row["evaluation_status"] = "fail"
        row["conflict_class"] = (
            conflicts[0] if len(conflicts) == 1 else "multiple_conflicts"
        )
        row["conflict_classes"] = conflicts
        routes = _normalized_strings(directive.get("local_repair_routes"))
        row["local_repair_possible"] = (
            bool(routes) if routes is not None else "not_evaluated"
        )
    elif missing:
        row["missing_mappings"] = sorted(set(missing))
        if verifier_unobserved:
            row["conflict_class"] = "required_verifier_unobservable"
        elif "satisfying_execution_path" in missing:
            row["conflict_class"] = "satisfying_execution_path_missing"
    else:
        row["evaluation_status"] = "pass"
        row["conflict_class"] = "none"
        row["local_repair_possible"] = False
    return row


def _expected_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    contract = result.get("validation_predicate_contract")
    criteria = _records(contract, "criteria")
    directives = _records(result.get("producer_directives"), "directives")
    evidence_refs = _normalized_strings(result.get("evidence_paths")) or []
    if criteria is None or directives is None or not criteria:
        row = _base_row(evidence_refs)
        row["missing_mappings"] = [
            "criteria" if criteria is None or not criteria else "producer_directives"
        ]
        return [row]
    expected: list[dict[str, Any]] = []
    for criterion in criteria:
        criterion_id = criterion.get("criterion_id")
        normalized_criterion_id = (
            criterion_id.strip()
            if isinstance(criterion_id, str) and criterion_id.strip()
            else None
        )
        matches = [
            directive
            for directive in directives
            if normalized_criterion_id is not None
            and normalized_criterion_id
            in (_normalized_strings(directive.get("criterion_ids")) or [])
        ]
        expected.append(
            _expected_row(
                criterion,
                matches[0] if len(matches) == 1 else None,
                evidence_refs,
            )
        )
    return expected


def assess_contract_satisfiability(
    result: dict[str, Any],
) -> SatisfiabilityAssessment:
    contract = result.get("validation_predicate_contract")
    present = (
        "validation_predicate_contract" in result or "producer_directives" in result
    )
    if not present:
        return SatisfiabilityAssessment(False, (), True, True, True, False, False)
    expected = _expected_rows(result)
    supplied = (
        contract.get("satisfiability_rows") if isinstance(contract, dict) else None
    )
    conflict = any(row["evaluation_status"] == "fail" for row in expected)
    unverifiable = any(row["evaluation_status"] == "not_evaluated" for row in expected)
    supplied_conflict = result.get("mutually_unsatisfiable_contract")
    supplied_unverifiable = result.get("unverifiable_acceptance_contract")
    return SatisfiabilityAssessment(
        present=True,
        expected_rows=tuple(expected),
        supplied_rows_match=supplied == expected,
        supplied_conflict_matches=(
            type(supplied_conflict) is bool and supplied_conflict == conflict
        ),
        supplied_unverifiable_matches=(
            type(supplied_unverifiable) is bool
            and supplied_unverifiable == unverifiable
        ),
        mutually_unsatisfiable=conflict,
        unverifiable=unverifiable,
    )


__all__ = ("SatisfiabilityAssessment", "assess_contract_satisfiability")
