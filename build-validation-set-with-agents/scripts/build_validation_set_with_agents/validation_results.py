"""Validation rules for executed results, splits, promotion, and quality."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .validation_common import (
    SEALED_HOLDOUT_STATUSES,
    add,
    is_json_int,
    is_string,
    read_jsonl,
    require_fields,
    within_root,
)
from .validation_records import authoritative_human_pairs
from .validation_set_contract import (
    FINALIZATION_SCHEMA_VERSION,
    ORACLE_RESULTS_SCHEMA_VERSION,
    SHA256_RE,
    build_finalization_record,
    canonical_sha256,
    deterministic_result_record,
    required_item_oracle_pairs,
    sha256_file,
)


def _validate_result_records(
    results: list[Any],
    expected_results: dict[tuple[str, str], dict[str, Any]],
    findings: list[dict[str, Any]],
) -> tuple[list[tuple[str, str]], int, int]:
    actual_pairs: list[tuple[str, str]] = []
    actual_failed = 0
    semantic_failed = 0
    for index, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            add(findings, "block", "invalid_oracle_result_record", "Each oracle result must be an object.", {"index": index})
            continue
        item_id = result.get("item_id")
        oracle_id = result.get("oracle_id")
        if not is_string(item_id) or not is_string(oracle_id):
            add(findings, "block", "invalid_oracle_result_identity", "Oracle result records require item_id and oracle_id.", {"index": index})
            continue
        pair = (item_id, oracle_id)
        actual_pairs.append(pair)
        expected_result = expected_results.get(pair)
        result_status = result.get("status")
        failures = result.get("failures")
        if result_status not in {"passed", "failed"} or not isinstance(failures, list):
            add(findings, "block", "invalid_oracle_result_status", "Oracle result status/failures are malformed.", {"item_id": item_id, "oracle_id": oracle_id})
        if result_status == "failed":
            actual_failed += 1
        if result_status == "passed" and failures:
            add(findings, "block", "passed_oracle_result_has_failures", "A passed oracle result cannot contain failures.", {"item_id": item_id, "oracle_id": oracle_id})
        if expected_result is None:
            continue
        if result.get("item_content_sha256") != expected_result["item_content_sha256"]:
            add(findings, "block", "oracle_result_item_hash_mismatch", "Oracle result is not bound to the current item content.", {"item_id": item_id, "oracle_id": oracle_id})
        if result.get("oracle_definition_sha256") != expected_result["oracle_definition_sha256"]:
            add(findings, "block", "oracle_result_definition_hash_mismatch", "Oracle result is not bound to the current predicate definition.", {"item_id": item_id, "oracle_id": oracle_id})
        if result_status != expected_result["status"] or failures != expected_result["failures"]:
            add(findings, "block", "oracle_result_semantic_mismatch", "Stored oracle status/failures do not match deterministic re-execution of the current predicate.", {"item_id": item_id, "oracle_id": oracle_id})
        if expected_result["status"] == "failed":
            semantic_failed += 1
    return actual_pairs, actual_failed, semantic_failed


def validate_oracle_results(
    oracle_results: dict[str, Any],
    *,
    manifest: dict[str, Any],
    items: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    oracles: dict[str, dict[str, Any]],
    items_path: Path | None,
    oracle_manifest_path: Path | None,
    strict_v2: bool,
    consumable: bool,
    findings: list[dict[str, Any]],
) -> bool:
    if not strict_v2:
        return False
    if oracle_results.get("oracle_results_schema_version") != ORACLE_RESULTS_SCHEMA_VERSION or type(oracle_results.get("oracle_results_schema_version")) is not int:
        add(findings, "block", "invalid_oracle_results_schema_version", "Oracle results must use integer schema version 1.")
    if oracle_results.get("validation_set_id") != manifest.get("validation_set_id"):
        add(findings, "block", "oracle_results_set_id_mismatch", "Oracle results must bind the same validation-set ID.")
    if oracle_results.get("runner") != "run_validation_oracles.py":
        add(findings, "block", "invalid_oracle_results_runner", "Oracle results must identify the deterministic runner.")
    for label, path, field in (
        ("items", items_path, "items_sha256"),
        ("oracle manifest", oracle_manifest_path, "oracle_manifest_sha256"),
    ):
        declared = oracle_results.get(field)
        if not isinstance(declared, str) or not SHA256_RE.fullmatch(declared):
            add(findings, "block", "invalid_oracle_results_input_hash", f"Oracle results require a lowercase SHA-256 for {label}.", {"field": field})
            continue
        if path is None or not path.is_file():
            continue
        try:
            actual = sha256_file(path)
        except (OSError, ValueError) as exc:
            add(findings, "block", "oracle_results_input_unhashable", f"Bound {label} could not be hashed.", {"error": str(exc)})
            continue
        if declared != actual:
            add(findings, "block", "oracle_results_input_hash_mismatch", f"Oracle results were produced from different {label} bytes.", {"field": field, "declared": declared, "actual": actual})

    results = oracle_results.get("results")
    if not isinstance(results, list):
        add(findings, "block", "invalid_oracle_results_records", "Oracle results must contain a `results` list.")
        results = []
    completed = oracle_results.get("execution_status") == "completed"
    required_pairs = required_item_oracle_pairs(items, list(oracles.values()))
    runnable_pairs = [
        (item, oracle)
        for item, oracle in required_pairs
        if oracle.get("oracle_type") == "deterministic" and oracle.get("target") == "item"
    ]
    expected_results = {
        (str(item.get("item_id")), str(oracle.get("oracle_id"))): deterministic_result_record(item, oracle)
        for item, oracle in runnable_pairs
    }
    expected_unsupported = [
        {
            "item_id": item.get("item_id") or item.get("id") or "unknown",
            "oracle_id": oracle.get("oracle_id"),
            "oracle_type": oracle.get("oracle_type"),
            "target": oracle.get("target"),
            "oracle_definition_sha256": canonical_sha256(oracle),
        }
        for item, oracle in required_pairs
        if not (oracle.get("oracle_type") == "deterministic" and oracle.get("target") == "item")
    ]
    runnable_oracle_count = len({str(oracle.get("oracle_id")) for _, oracle in runnable_pairs})
    for field, actual in (
        ("item_count", len(items)),
        ("oracle_count", len(oracles)),
        ("result_count", len(results)),
    ):
        if not is_json_int(oracle_results.get(field)) or oracle_results.get(field) != actual:
            add(findings, "block", "oracle_results_count_mismatch", f"Oracle results `{field}` must exactly match current artifacts.", {"reported": oracle_results.get(field), "actual": actual})
    completed_counts = {
        "runnable_oracle_count": runnable_oracle_count,
        "required_pair_count": len(required_pairs),
        "executed_pair_count": len(expected_results),
        "unsupported_pair_count": len(expected_unsupported),
    }
    for field, actual in completed_counts.items():
        reported = oracle_results.get(field)
        if not is_json_int(reported) or (completed and reported != actual):
            add(findings, "block" if completed else "warn", "oracle_results_count_mismatch", f"Completed oracle results `{field}` must match current required coverage.", {"reported": reported, "actual": actual})
    if completed and oracle_results.get("unsupported_pairs") != expected_unsupported:
        add(findings, "block", "oracle_results_unsupported_pair_mismatch", "Oracle results must enumerate every unsupported required pair with its current predicate hash.")

    actual_pairs, actual_failed, semantic_failed = _validate_result_records(
        results,
        expected_results,
        findings,
    )

    expected_pairs = set(expected_results)
    if completed and (len(actual_pairs) != len(set(actual_pairs)) or set(actual_pairs) != expected_pairs):
        add(findings, "block", "oracle_results_pair_mismatch", "Oracle results must cover every runnable item-oracle pair exactly once.", {"expected_count": len(expected_pairs), "actual_count": len(actual_pairs)})
    if not is_json_int(oracle_results.get("failed_count")) or oracle_results.get("failed_count") != actual_failed:
        add(findings, "block", "oracle_results_count_mismatch", "Oracle results `failed_count` must match failed records.", {"reported": oracle_results.get("failed_count"), "actual": actual_failed})
    expected_runner_status = "failed" if semantic_failed else "passed"
    if completed and (oracle_results.get("status") != expected_runner_status or oracle_results.get("failed_count") != semantic_failed):
        add(findings, "block", "oracle_result_semantic_mismatch", "Oracle summary status/counts do not match deterministic re-execution.", {"expected_status": expected_runner_status, "expected_failed_count": semantic_failed})

    unsupported_pairs = {(str(record["item_id"]), str(record["oracle_id"])) for record in expected_unsupported}
    uncovered_pairs = sorted(unsupported_pairs - authoritative_human_pairs(labels))
    if uncovered_pairs:
        add(
            findings,
            "block" if consumable else "warn",
            "oracle_pair_coverage_incomplete",
            "Every required non-executed item-oracle pair needs an accepted authoritative human-reviewed label with reviewer and evidence references.",
            [{"item_id": item_id, "oracle_id": oracle_id} for item_id, oracle_id in uncovered_pairs],
        )
    passed = (
        completed
        and oracle_results.get("status") == "passed"
        and actual_failed == 0
        and semantic_failed == 0
        and bool(expected_pairs)
        and not uncovered_pairs
    )
    if not passed:
        add(
            findings,
            "block" if consumable else "warn",
            "oracle_results_not_completed_nonblocking",
            "Consumption requires semantically revalidated passing results plus complete required-pair coverage.",
            {"execution_status": oracle_results.get("execution_status"), "status": oracle_results.get("status"), "failed_count": actual_failed},
        )
    return passed


def validate_scenario_coverage(
    manifest: dict[str, Any],
    items: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    oracles: dict[str, dict[str, Any]],
    oracle_results: dict[str, Any],
    root: Path,
    consumable: bool,
    findings: list[dict[str, Any]],
) -> None:
    scenario_items = [item for item in items if is_string(item.get("acceptance_scenario_id"))]
    coverage = manifest.get("scenario_coverage")
    if not scenario_items and coverage is None:
        return
    severity = "block" if consumable else "warn"
    if not isinstance(coverage, list):
        add(findings, severity, "invalid_scenario_coverage", "Scenario-bearing sets require a `scenario_coverage` list.")
        return
    passed_pairs = {
        (str(result.get("item_id")), str(result.get("oracle_id")))
        for result in oracle_results.get("results") or []
        if isinstance(result, dict) and result.get("status") == "passed"
    }
    covered_pairs = passed_pairs | authoritative_human_pairs(labels)
    coverage_ids: list[str] = []
    for index, record in enumerate(coverage, start=1):
        if not isinstance(record, dict):
            add(findings, "block", "invalid_scenario_coverage", "Scenario coverage records must be objects.", {"index": index})
            continue
        scenario_id = record.get("acceptance_scenario_id")
        if not is_string(scenario_id):
            add(findings, "block", "invalid_scenario_coverage", "Scenario coverage requires acceptance_scenario_id.", {"index": index})
            continue
        coverage_ids.append(scenario_id)
        if record.get("coverage_status") not in {None, "covered"}:
            add(findings, severity, "invalid_scenario_coverage", "Entries in scenario_coverage must represent covered scenarios; use scenario_uncovered otherwise.", {"acceptance_scenario_id": scenario_id})
        if record.get("premise_satisfied") is not True:
            add(findings, severity, "scenario_coverage_without_satisfied_premise", "A covered scenario must explicitly record premise_satisfied=true.", {"acceptance_scenario_id": scenario_id})
        expected = record.get("expected_terminal_state")
        observed = record.get("observed_terminal_state")
        oracle_id = record.get("oracle_id")
        evidence_path = record.get("evidence_path")
        evidence_sha256 = record.get("evidence_sha256")
        if not all(is_string(value) for value in (expected, observed, oracle_id, evidence_path)) or not isinstance(evidence_sha256, str) or not SHA256_RE.fullmatch(evidence_sha256):
            add(findings, severity, "invalid_scenario_coverage", "Covered scenarios require expected/observed terminal states, root-relative evidence_path/evidence_sha256, and oracle_id.", {"acceptance_scenario_id": scenario_id})
            continue
        raw_evidence = Path(evidence_path)
        resolved_evidence = None if raw_evidence.is_absolute() or ".." in raw_evidence.parts else within_root(root, root / raw_evidence)
        if resolved_evidence is None or not resolved_evidence.is_file():
            add(findings, severity, "scenario_evidence_unavailable", "Scenario evidence must resolve to a file inside the declared root.", {"acceptance_scenario_id": scenario_id, "evidence_path": evidence_path})
        else:
            try:
                actual_evidence_hash = sha256_file(resolved_evidence)
            except (OSError, ValueError) as exc:
                add(findings, severity, "scenario_evidence_unavailable", "Scenario evidence could not be hashed.", {"acceptance_scenario_id": scenario_id, "error": str(exc)})
            else:
                if actual_evidence_hash != evidence_sha256:
                    add(findings, severity, "scenario_evidence_hash_mismatch", "Scenario evidence bytes do not match evidence_sha256.", {"acceptance_scenario_id": scenario_id, "declared": evidence_sha256, "actual": actual_evidence_hash})
        oracle = oracles.get(oracle_id)
        observed_fields: set[str] = set()
        if isinstance(oracle, dict) and oracle.get("oracle_type") == "deterministic":
            observed_fields.update(str(value) for value in oracle.get("required_fields") or [])
            observed_fields.update(str(value) for value in oracle.get("forbidden_fields") or [])
            observed_fields.update(str(value) for value in (oracle.get("allowed_values") or {}))
        human_observation = any(
            item.get("acceptance_scenario_id") == scenario_id
            and label.get("item_id") == item.get("item_id")
            and oracle_id in (label.get("oracle_ids") or [])
            and label.get("label_type") == "human_reviewed"
            and label.get("label_status") == "accepted"
            and label.get("authoritative") is True
            and label.get("expected_terminal_state") == expected
            and label.get("observed_terminal_state") == observed
            for item in scenario_items
            for label in labels
        )
        if not {"expected_terminal_state", "observed_terminal_state"} <= observed_fields and not human_observation:
            add(findings, severity, "scenario_oracle_does_not_observe_terminal_state", "Scenario coverage oracle/adjudication must explicitly bind expected and observed terminal-state fields.", {"acceptance_scenario_id": scenario_id, "oracle_id": oracle_id})
        matching = [
            item
            for item in scenario_items
            if item.get("acceptance_scenario_id") == scenario_id
            and item.get("premise_satisfied") is True
            and item.get("expected_terminal_state") == expected
            and item.get("observed_terminal_state") == observed
            and expected == observed
            and (str(item.get("item_id")), oracle_id) in covered_pairs
        ]
        if not matching:
            add(findings, severity, "scenario_coverage_without_satisfied_premise", "Covered scenario has no premise-satisfying item with matching observed terminal state and covered oracle pair.", {"acceptance_scenario_id": scenario_id, "oracle_id": oracle_id})
    duplicates = sorted(scenario_id for scenario_id, count in Counter(coverage_ids).items() if count > 1)
    if duplicates:
        add(findings, "block", "duplicate_scenario_coverage", "Each acceptance scenario may be claimed covered at most once.", duplicates)
    satisfied_ids = {str(item["acceptance_scenario_id"]) for item in scenario_items if item.get("premise_satisfied") is True}
    missing = sorted(satisfied_ids - set(coverage_ids))
    if missing:
        add(findings, severity, "scenario_coverage_missing", "Premise-satisfying scenario items require explicit manifest coverage records.", missing)


def validate_split_manifest(
    split_manifest: dict[str, Any],
    manifest: dict[str, Any],
    item_ids: set[str],
    consumable: bool,
    root: Path,
    base: Path,
    findings: list[dict[str, Any]],
) -> None:
    require_fields(split_manifest, ("validation_set_id", "sealed_holdout_status", "label_visibility_policy"), findings, "missing_split_manifest_field", "Split manifest")
    if "splits" not in split_manifest:
        add(findings, "block", "missing_split_manifest_field", "Split manifest is missing `splits`.", {"field": "splits"})
    if split_manifest.get("validation_set_id") != manifest.get("validation_set_id"):
        add(findings, "block", "split_manifest_set_id_mismatch", "Split manifest must bind the same validation-set ID.")
    if split_manifest.get("sealed_holdout_status") not in SEALED_HOLDOUT_STATUSES:
        add(findings, "block", "invalid_sealed_holdout_status", "Split manifest has an invalid sealed-holdout status.")
    splits = split_manifest.get("splits")
    if not isinstance(splits, dict):
        add(findings, "block", "invalid_splits", "`splits` must be a mapping from split name to item IDs.")
        return
    membership: dict[str, list[str]] = {}
    for split_name, members in splits.items():
        if not is_string(split_name) or not isinstance(members, list) or any(not is_string(member) for member in members):
            add(findings, "block", "invalid_split_members", "Every split must be named and contain a list of item IDs.", {"split": split_name})
            continue
        for member in members:
            if member in item_ids:
                membership.setdefault(member, []).append(split_name)
                continue
            shard_candidates = [root / member, base / member]
            shard_path = next((bounded for candidate in shard_candidates if (bounded := within_root(root, candidate)) is not None and bounded.is_file()), None)
            if shard_path is None:
                membership.setdefault(member, []).append(split_name)
                continue
            shard_items = read_jsonl(shard_path, findings, f"split shard {member}")
            shard_ids = [record.get("item_id") for record in shard_items]
            if not shard_ids or any(not is_string(item_id) for item_id in shard_ids):
                add(findings, "block", "invalid_split_shard", "A split shard must contain item records with non-empty item IDs.", {"split": split_name, "path": member})
                continue
            for item_id in shard_ids:
                membership.setdefault(item_id, []).append(split_name)
    unknown = sorted(set(membership) - item_ids)
    if unknown:
        add(findings, "block", "split_references_unknown_item", "Split manifest references unknown item IDs.", unknown[:20])
    duplicate_membership = {item_id: names for item_id, names in membership.items() if len(names) > 1}
    if duplicate_membership:
        add(findings, "block", "item_in_multiple_splits", "An item may not appear in multiple splits without an explicit contract extension.", duplicate_membership)
    missing = sorted(item_ids - set(membership))
    if missing:
        add(findings, "block" if consumable else "warn", "items_missing_from_splits", "Every consumable item must belong to exactly one split.", missing[:20])
    if consumable and not splits:
        add(findings, "block", "empty_split_manifest", "A consumable validation set requires at least one populated split.")
    if split_manifest.get("sealed_holdout_labels_exposed") is True:
        add(findings, "block", "sealed_holdout_labels_exposed", "Sealed holdout labels were exposed.")


def validate_counts(
    manifest: dict[str, Any],
    items: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    oracle_count: int,
    consumable: bool,
    findings: list[dict[str, Any]],
) -> None:
    expected = {"item_count": len(items), "label_count": len(labels), "oracle_count": oracle_count}
    for field, actual in expected.items():
        if is_json_int(manifest.get(field)) and manifest.get(field) != actual:
            add(findings, "block" if consumable else "warn", "manifest_count_mismatch", f"`{field}` does not match loaded files.", {"manifest": manifest.get(field), "actual": actual})
    declared_distribution = manifest.get("source_class_distribution")
    actual_distribution = dict(sorted(Counter(str(item.get("source_class")) for item in items).items()))
    if isinstance(declared_distribution, dict) and declared_distribution != actual_distribution:
        add(findings, "block" if consumable else "warn", "source_class_distribution_mismatch", "Source-class distribution does not match loaded items.", {"manifest": declared_distribution, "actual": actual_distribution})
    if consumable and not items:
        add(findings, "block", "empty_consumable_validation_set", "A consumable validation set must contain at least one item.")
    elif not consumable and not items:
        add(findings, "warn", "empty_candidate_validation_set", "The candidate set has no items and remains not evaluated.")
    if consumable and oracle_count == 0:
        add(findings, "block", "empty_consumable_oracle_set", "A consumable validation set must contain at least one oracle.")
    elif not consumable and oracle_count == 0:
        add(findings, "warn", "empty_candidate_oracle_set", "The candidate set has no oracles and remains not evaluated.")


def validate_finalization_record(
    manifest: dict[str, Any],
    artifact_paths: dict[str, Path],
    oracle_results: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    record = manifest.get("finalization_record")
    if not isinstance(record, dict):
        add(findings, "block", "missing_finalization_record", "A schema-v2 complete set must be promoted by finalize_validation_set.py.")
        return
    if record.get("finalization_schema_version") != FINALIZATION_SCHEMA_VERSION or type(record.get("finalization_schema_version")) is not int:
        add(findings, "block", "invalid_finalization_schema_version", "Finalization record must use integer schema version 1.")
    try:
        expected = build_finalization_record(manifest, artifact_paths, oracle_results)
    except (OSError, ValueError) as exc:
        add(findings, "block", "finalization_inputs_unhashable", "Finalization inputs could not be rebound.", {"error": str(exc)})
        return
    if record != expected:
        add(
            findings,
            "block",
            "finalization_record_mismatch",
            "Finalization record does not match current artifact bytes and manifest state; rerun finalize_validation_set.py.",
            {
                "declared_finalization_sha256": record.get("finalization_sha256"),
                "expected_finalization_sha256": expected.get("finalization_sha256"),
            },
        )


def validate_gold(
    manifest: dict[str, Any],
    labels: list[dict[str, Any]],
    oracles: dict[str, dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    if manifest.get("quality_tier") != "gold":
        return
    concrete_human = any(
        label.get("label_type") == "human_reviewed"
        and label.get("label_status") == "accepted"
        and is_string(label.get("human_reviewer_ref"))
        and isinstance(label.get("evidence_refs"), list)
        and bool(label.get("evidence_refs"))
        and all(is_string(value) for value in label.get("evidence_refs", []))
        for label in labels
    )
    authoritative_ids = manifest.get("authoritative_oracle_ids")
    concrete_oracle = False
    if manifest.get("fully_deterministic_authoritative_oracle") is True and isinstance(authoritative_ids, list) and authoritative_ids:
        concrete_oracle = all(
            is_string(oracle_id)
            and oracle_id in oracles
            and oracles[oracle_id].get("oracle_type") in {"deterministic", "executable"}
            and oracles[oracle_id].get("authoritative") is True
            and isinstance(oracles[oracle_id].get("evidence_paths"), list)
            and bool(oracles[oracle_id].get("evidence_paths"))
            and all(is_string(value) for value in oracles[oracle_id].get("evidence_paths", []))
            for oracle_id in authoritative_ids
        )
    if not concrete_human and not concrete_oracle:
        add(findings, "block", "gold_without_concrete_authoritative_evidence", "Gold requires an accepted human-reviewed label with bounded evidence or explicitly identified authoritative deterministic/executable oracles with evidence paths.")
