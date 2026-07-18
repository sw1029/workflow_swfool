#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ACCEPTANCE_STATUSES = {"normalized", "partial", "blocked", "needs_review"}
SATISFIABILITY_STATUSES = {"pass", "fail", "not_evaluated"}


class AcceptanceIdentityError(ValueError):
    pass


def criterion_is_semantically_non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if not isinstance(value, dict) or not value:
        return False

    def has_content(item: Any) -> bool:
        if isinstance(item, str):
            return bool(item.strip())
        if isinstance(item, dict):
            return bool(item) and any(has_content(nested) for nested in item.values())
        if isinstance(item, (list, tuple)):
            return any(has_content(nested) for nested in item)
        return item is not None

    return any(has_content(item) for item in value.values())


def normalized_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return sorted(set(item.strip() for item in value))


def contract_records(value: Any, plural_key: str) -> list[dict[str, Any]] | None:
    if isinstance(value, dict) and isinstance(value.get(plural_key), list):
        records = value[plural_key]
    elif isinstance(value, list):
        records = value
    elif isinstance(value, dict):
        records = [value]
    else:
        return None
    if any(not isinstance(record, dict) for record in records):
        return None
    return records


def build_satisfiability_row(
    criterion: dict[str, Any],
    directive: dict[str, Any] | None,
    evidence_refs: list[str],
) -> dict[str, Any]:
    criterion_id = criterion.get("criterion_id")
    predicate_id = criterion.get("predicate_id")
    row: dict[str, Any] = {
        "criterion_id": criterion_id.strip() if isinstance(criterion_id, str) and criterion_id.strip() else "not_evaluated",
        "predicate_id": predicate_id.strip() if isinstance(predicate_id, str) and predicate_id.strip() else "not_evaluated",
        "producer_directive_id": "not_evaluated",
        "affected_output_classes": [],
        "evaluation_status": "not_evaluated",
        "conflict_class": "mapping_missing",
        "local_repair_possible": "not_evaluated",
        "evidence_refs": evidence_refs,
    }
    missing: list[str] = []
    if row["criterion_id"] == "not_evaluated":
        missing.append("criterion_id")
    if row["predicate_id"] == "not_evaluated":
        missing.append("predicate_id")
    if directive is None:
        missing.append("producer_directive_binding")
        row["missing_mappings"] = missing
        return row

    directive_id = directive.get("producer_directive_id")
    if isinstance(directive_id, str) and directive_id.strip():
        row["producer_directive_id"] = directive_id.strip()
    else:
        missing.append("producer_directive_id")

    list_fields = {
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
    for field, owner in list_fields.items():
        normalized = normalized_string_list(owner.get(field))
        if normalized is None:
            missing.append(field)
            values[field] = []
        else:
            values[field] = normalized

    row["affected_output_classes"] = sorted(
        set(values["required_output_classes"]) | set(values["required_non_empty_output_classes"])
    )
    required_freshness = criterion.get("required_freshness_class")
    if not isinstance(required_freshness, str) or not required_freshness.strip():
        missing.append("required_freshness_class")
        required_freshness = "not_evaluated"
    else:
        required_freshness = required_freshness.strip()
    producer_execution_allowed = directive.get("producer_execution_allowed")
    if required_freshness == "fresh_producer_execution" and type(producer_execution_allowed) is not bool:
        missing.append("producer_execution_allowed")
    requires_body_movement = criterion.get("requires_body_movement")
    if type(requires_body_movement) is not bool:
        missing.append("requires_body_movement")
    body_mutation_allowed = directive.get("body_mutation_allowed")
    if requires_body_movement is True and type(body_mutation_allowed) is not bool:
        missing.append("body_mutation_allowed")

    conflicts: list[str] = []
    if set(values["required_output_classes"]) - set(values["permitted_output_classes"]):
        conflicts.append("required_output_prohibited")
    if set(values["required_non_empty_output_classes"]) - set(values["guaranteed_non_empty_output_classes"]):
        conflicts.append("non_empty_population_unproducible")
    if set(values["required_mutation_surfaces"]) - set(values["allowed_task_mutation_surfaces"]):
        conflicts.append("required_mutation_surface_forbidden")
    if required_freshness == "fresh_producer_execution" and producer_execution_allowed is False:
        conflicts.append("fresh_producer_execution_forbidden")
    if requires_body_movement is True and body_mutation_allowed is False:
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
        row["conflict_class"] = conflicts[0] if len(conflicts) == 1 else "multiple_conflicts"
        row["conflict_classes"] = conflicts
        routes = normalized_string_list(directive.get("local_repair_routes"))
        row["local_repair_possible"] = bool(routes) if routes is not None else "not_evaluated"
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


def recompute_contract_satisfiability(packet: dict[str, Any]) -> None:
    if "validation_predicate_contract" not in packet and "producer_directives" not in packet:
        return
    contract = packet.get("validation_predicate_contract")
    criteria = contract_records(contract, "criteria")
    directives = contract_records(packet.get("producer_directives"), "directives")
    evidence_refs = normalized_string_list(packet.get("evidence_paths")) or []
    rows: list[dict[str, Any]] = []
    if criteria is None or directives is None or not criteria:
        rows.append(
            {
                "criterion_id": "not_evaluated",
                "predicate_id": "not_evaluated",
                "producer_directive_id": "not_evaluated",
                "affected_output_classes": [],
                "evaluation_status": "not_evaluated",
                "conflict_class": "mapping_missing",
                "local_repair_possible": "not_evaluated",
                "missing_mappings": ["criteria" if criteria is None or not criteria else "producer_directives"],
                "evidence_refs": evidence_refs,
            }
        )
    else:
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
                in (normalized_string_list(directive.get("criterion_ids")) or [])
            ]
            rows.append(build_satisfiability_row(criterion, matches[0] if len(matches) == 1 else None, evidence_refs))

    if isinstance(contract, dict):
        contract["satisfiability_rows"] = rows
    else:
        packet["validation_predicate_contract"] = {"criteria": criteria or [], "satisfiability_rows": rows}

    supplied_conflict = packet.get("mutually_unsatisfiable_contract")
    if supplied_conflict is not None and type(supplied_conflict) is not bool:
        raise AcceptanceIdentityError("mutually_unsatisfiable_contract must be a JSON boolean")
    derived_conflict = any(row["evaluation_status"] == "fail" for row in rows)
    if supplied_conflict is not None and supplied_conflict != derived_conflict:
        raise AcceptanceIdentityError("caller-provided mutually_unsatisfiable_contract contradicts recomputed satisfiability")
    packet["mutually_unsatisfiable_contract"] = derived_conflict
    supplied_unverifiable = packet.get("unverifiable_acceptance_contract")
    if supplied_unverifiable is not None and type(supplied_unverifiable) is not bool:
        raise AcceptanceIdentityError("unverifiable_acceptance_contract must be a JSON boolean")
    derived_unverifiable = any(row["evaluation_status"] == "not_evaluated" for row in rows)
    if supplied_unverifiable is not None and supplied_unverifiable != derived_unverifiable:
        raise AcceptanceIdentityError("caller-provided unverifiable_acceptance_contract contradicts recomputed satisfiability")
    packet["unverifiable_acceptance_contract"] = derived_unverifiable


def bounded_file(root: Path, value: str) -> Path:
    raw = Path(value)
    path = (raw if raw.is_absolute() else root / raw).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AcceptanceIdentityError(f"task path escapes the workspace root, including through a symlink: {value}") from exc
    if not path.is_file():
        raise AcceptanceIdentityError(f"task path does not identify a file: {value}")
    return path


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def load_packet(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value == "-":
        raw = sys.stdin.read()
    else:
        stripped = value.strip()
        if stripped.startswith("{"):
            raw = stripped
        else:
            path = Path(value)
            try:
                raw = path.read_text(encoding="utf-8") if path.is_file() else value
            except OSError as exc:
                raise AcceptanceIdentityError(f"cannot read packet JSON: {exc}") from exc
    try:
        packet = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AcceptanceIdentityError(f"packet is not valid JSON: {exc}") from exc
    if not isinstance(packet, dict):
        raise AcceptanceIdentityError("packet JSON must contain an object")
    return packet


def validate_final_packet(packet: dict[str, Any]) -> None:
    status = packet.get("acceptance_status")
    if status not in ACCEPTANCE_STATUSES:
        raise AcceptanceIdentityError(
            "final acceptance packet requires acceptance_status: normalized|partial|blocked|needs_review"
        )
    criteria = packet.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        raise AcceptanceIdentityError("final acceptance packet requires non-empty acceptance_criteria")
    invalid_criteria = [index for index, criterion in enumerate(criteria) if not criterion_is_semantically_non_empty(criterion)]
    if invalid_criteria:
        raise AcceptanceIdentityError(
            f"final acceptance packet contains semantically empty acceptance_criteria at indexes: {invalid_criteria}"
        )
    blockers = packet.get("blockers")
    if not isinstance(blockers, list):
        raise AcceptanceIdentityError("final acceptance packet requires explicit blockers list")
    if any(not criterion_is_semantically_non_empty(blocker) for blocker in blockers):
        raise AcceptanceIdentityError("final acceptance packet contains a semantically empty blocker")
    if status == "normalized" and blockers:
        raise AcceptanceIdentityError("normalized acceptance cannot retain blockers")
    if status in {"blocked", "needs_review"} and not blockers:
        raise AcceptanceIdentityError("blocked/needs_review acceptance requires a concrete blocker")
    if not isinstance(packet.get("evidence_paths"), list):
        raise AcceptanceIdentityError("final acceptance packet requires explicit evidence_paths list")
    contract = packet.get("validation_predicate_contract")
    if isinstance(contract, dict) and "satisfiability_rows" in contract:
        rows = contract.get("satisfiability_rows")
        if not isinstance(rows, list) or not rows:
            raise AcceptanceIdentityError("validation_predicate_contract requires non-empty satisfiability_rows")
        invalid = [row for row in rows if not isinstance(row, dict) or row.get("evaluation_status") not in SATISFIABILITY_STATUSES]
        if invalid:
            raise AcceptanceIdentityError("satisfiability_rows require evaluation_status: pass|fail|not_evaluated")
        unresolved = [row for row in rows if row.get("evaluation_status") != "pass"]
        if unresolved and status == "normalized":
            raise AcceptanceIdentityError("normalized acceptance cannot contain failed or not-evaluated satisfiability rows")
        if unresolved and not blockers:
            raise AcceptanceIdentityError("unresolved satisfiability requires a concrete blocker or residual scope")
        directives = contract_records(packet.get("producer_directives"), "directives") or []
        failed_without_repair_route = []
        for row in rows:
            if row.get("evaluation_status") != "fail":
                continue
            bound_directives = [
                directive
                for directive in directives
                if isinstance(directive.get("producer_directive_id"), str)
                and directive.get("producer_directive_id").strip() == row.get("producer_directive_id")
                and isinstance(directive.get("criterion_ids"), list)
                and row.get("criterion_id") in directive.get("criterion_ids")
            ]
            if len(bound_directives) != 1 or not normalized_string_list(
                bound_directives[0].get("local_repair_routes")
            ):
                failed_without_repair_route.append(row)
        if failed_without_repair_route:
            raise AcceptanceIdentityError(
                "failed satisfiability rows require a uniquely bound producer directive with non-empty local_repair_routes"
            )


def bind(root: Path, task_id: str, task_path_value: str, packet: dict[str, Any], final: bool) -> dict[str, Any]:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise AcceptanceIdentityError("task_id must be a non-empty path-safe token of at most 128 characters")
    task_path = bounded_file(root, task_path_value)
    task_body = task_path.read_bytes()
    if not task_body.strip():
        raise AcceptanceIdentityError("cannot normalize acceptance from an empty task file")
    supplied_task_id = packet.get("task_id")
    if supplied_task_id is not None and str(supplied_task_id) != task_id:
        raise AcceptanceIdentityError("packet task_id does not match the active task_id")

    fingerprint = hashlib.sha256(task_body).hexdigest()
    result = copy.deepcopy(packet)
    result.update(
        {
            "format_version": 1,
            "step": "acceptance",
            "acceptance_id": f"acceptance-{task_id}-{fingerprint[:16]}",
            "task_id": task_id,
            "acceptance_provenance": {
                "source_task_id": task_id,
                "source_task_path": relative_path(root, task_path),
                "source_task_fingerprint": fingerprint,
            },
        }
    )
    if final:
        task_evidence = relative_path(root, task_path)
        if isinstance(result.get("evidence_paths"), list) and task_evidence not in result["evidence_paths"]:
            result["evidence_paths"].append(task_evidence)
        recompute_contract_satisfiability(result)
        validate_final_packet(result)
    else:
        result.setdefault("acceptance_status", "needs_review")
        result.setdefault("blockers", ["acceptance_packet_not_finalized"])
        result.setdefault("evidence_paths", [relative_path(root, task_path)])
    return result


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bind acceptance to one task revision and verify predicate/directive satisfiability.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-path", default="task.md")
    parser.add_argument("--packet-json")
    parser.add_argument("--final", action="store_true", help="Require the complete acceptance result contract.")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        result = bind(root, args.task_id, args.task_path, load_packet(args.packet_json), args.final)
        if args.output:
            output = Path(args.output)
            output = (output if output.is_absolute() else root / output).resolve(strict=False)
            try:
                output.relative_to(root)
            except ValueError as exc:
                raise AcceptanceIdentityError("output path must stay inside the workspace root") from exc
            atomic_write(output, result)
    except (AcceptanceIdentityError, OSError, UnicodeError) as exc:
        json.dump({"format_version": 1, "status": "block", "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
