#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from validation_set_contract import (
    ARTIFACT_FIELDS,
    FINALIZATION_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    ORACLE_RESULTS_SCHEMA_VERSION,
    SHA256_RE,
    build_finalization_record,
    canonical_sha256,
    deterministic_result_record,
    required_item_oracle_pairs,
    sha256_file,
)


ALLOWED_SOURCE_CLASSES = {
    "test_fixture",
    "synthetic_fixture",
    "sampled_real_metadata",
    "sampled_real_positive_evidence",
    "real_reviewed_work",
    "local_dataset_candidate",
    "external_metadata",
    "generated_candidate",
}
QUALITY_TIERS = {"candidate", "silver", "human_review_required", "gold"}
VALIDATION_SET_STATUSES = {"complete", "partial", "blocked", "not_applicable", "candidate_only"}
CONSUMABLE_STATUSES = {"complete"}
LABEL_TYPES = {"deterministic", "executable", "agent_consensus", "human_reviewed", "reference"}
LABEL_STATUSES = {"candidate", "accepted", "rejected", "needs_human_review", "blocked"}
ORACLE_TYPES = {"deterministic", "executable", "span_hash", "reference", "agent_consensus", "human_reviewed"}
ORACLE_TARGETS = {"item", "label", "set", "output", "root"}
SEALED_HOLDOUT_STATUSES = {"true_sealed", "quasi_sealed", "not_sealed", "not_applicable"}
FORBIDDEN_RAW_FIELDS = {"raw_body", "provider_body", "full_text", "source_text", "document_body"}
STRICT_BOOLEAN_FIELDS = {
    "not_gold",
    "fully_deterministic_authoritative_oracle",
    "premise_satisfied",
    "expectation_lineage_stale",
    "gating_axis_expected_pass",
    "report_key_divergence_expected",
    "acceptance_inversion_candidate",
    "sealed_holdout_labels_exposed",
    "authoritative",
}


def add(findings: list[dict[str, Any]], severity: str, code: str, message: str, evidence: Any = None) -> None:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if evidence is not None:
        item["evidence"] = evidence
    findings.append(item)


def nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def is_json_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def is_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalized_field_name(value: str) -> str:
    with_word_boundaries = re.sub(r"(?<!^)(?=[A-Z])", "_", value)
    return with_word_boundaries.casefold().replace("-", "_")


def walk_forbidden(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            child = f"{path}.{key_text}"
            if normalized_field_name(key_text) in FORBIDDEN_RAW_FIELDS:
                found.append(child)
            found.extend(walk_forbidden(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_forbidden(item, f"{path}[{index}]"))
    return found


def validate_boolean_fields(value: Any, findings: list[dict[str, Any]], path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if str(key) in STRICT_BOOLEAN_FIELDS and type(item) is not bool:
                add(
                    findings,
                    "block",
                    "invalid_boolean_type",
                    f"`{key}` must be a JSON boolean, not a truthy/falsy substitute.",
                    {"path": child, "value": item},
                )
            validate_boolean_fields(item, findings, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_boolean_fields(item, findings, f"{path}[{index}]")


def read_json(path: Path, findings: list[dict[str, Any]], artifact: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        add(findings, "block", "invalid_json_artifact", f"`{artifact}` is not valid UTF-8 JSON.", {"path": str(path), "error": str(exc)})
        return {}
    if not isinstance(value, dict):
        add(findings, "block", "invalid_json_artifact_type", f"`{artifact}` must contain a JSON object.", {"path": str(path)})
        return {}
    return value


def read_jsonl(path: Path, findings: list[dict[str, Any]], artifact: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    add(findings, "block", "invalid_jsonl_record", f"`{artifact}` contains invalid JSON.", {"path": str(path), "line": line_number, "error": str(exc)})
                    continue
                if not isinstance(value, dict):
                    add(findings, "block", "invalid_jsonl_record_type", f"`{artifact}` records must be JSON objects.", {"path": str(path), "line": line_number})
                    continue
                records.append(value)
    except (OSError, UnicodeError) as exc:
        add(findings, "block", "unreadable_jsonl_artifact", f"`{artifact}` could not be read as UTF-8 JSONL.", {"path": str(path), "error": str(exc)})
    return records


def within_root(root: Path, candidate: Path) -> Path | None:
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def resolve_manifest_path(
    root: Path,
    base: Path,
    value: Any,
    field: str,
    findings: list[dict[str, Any]],
) -> Path | None:
    if not is_string(value):
        return None
    raw = Path(value)
    candidates = [raw] if raw.is_absolute() else [root / raw, base / raw]
    selected: Path | None = None
    for candidate in candidates:
        bounded = within_root(root, candidate)
        if bounded is None:
            continue
        if bounded.is_file():
            selected = bounded
            break
        if selected is None:
            selected = bounded
    if selected is None:
        add(findings, "block", "manifest_path_escape", f"`{field}` escapes the declared root, including through a symlink.", {"path": value})
        return None
    return selected


def require_fields(record: dict[str, Any], fields: tuple[str, ...], findings: list[dict[str, Any]], code: str, subject: str) -> None:
    for field in fields:
        if field not in record or not nonempty(record.get(field)):
            add(findings, "block", code, f"{subject} is missing `{field}`.", {"field": field})


def validate_manifest(manifest: dict[str, Any], findings: list[dict[str, Any]]) -> bool:
    required = (
        "validation_set_id",
        "validation_set_status",
        "quality_tier",
        "not_gold",
        "created_at",
        "source_class_distribution",
        "item_count",
        "label_count",
        "oracle_count",
        "items_path",
        "labels_path",
        "oracle_manifest_path",
        "split_manifest_path",
        "leakage_report_path",
    )
    allow_empty = {"not_gold", "item_count", "label_count", "oracle_count", "source_class_distribution"}
    for field in required:
        if field not in manifest or (field not in allow_empty and not nonempty(manifest.get(field))):
            add(findings, "block", "missing_manifest_field", f"Manifest is missing `{field}`.", {"field": field})
    if "not_gold" in manifest and type(manifest.get("not_gold")) is not bool:
        add(findings, "block", "invalid_boolean_type", "`not_gold` must be a JSON boolean.", {"field": "not_gold", "value": manifest.get("not_gold")})
    for field in ("item_count", "label_count", "oracle_count"):
        if field in manifest and not is_json_int(manifest.get(field)):
            add(findings, "block", "invalid_manifest_count", f"`{field}` must be a non-negative JSON integer.", {"field": field, "value": manifest.get(field)})
    status = manifest.get("validation_set_status")
    if status not in VALIDATION_SET_STATUSES:
        add(findings, "block", "invalid_validation_set_status", "Validation-set status is not recognized.", {"validation_set_status": status})
    quality_tier = manifest.get("quality_tier")
    if quality_tier not in QUALITY_TIERS:
        add(findings, "block", "invalid_quality_tier", "Quality tier is not recognized.", {"quality_tier": quality_tier})
    if quality_tier == "gold" and manifest.get("not_gold") is not False:
        add(findings, "block", "gold_marked_not_gold", "A gold set must explicitly use `not_gold: false`.")
    distribution = manifest.get("source_class_distribution")
    if not isinstance(distribution, dict) or any(not is_string(key) or not is_json_int(value) for key, value in distribution.items()):
        add(findings, "block", "invalid_source_class_distribution", "`source_class_distribution` must map source-class strings to non-negative JSON integers.")
    if manifest.get("cycle_id") and not is_string(manifest.get("task_id")):
        add(findings, "block", "missing_task_id_for_linked_set", "A cycle-linked validation set must include a non-empty `task_id`.")
    schema_version = manifest.get("manifest_schema_version")
    if schema_version is None:
        add(
            findings,
            "warn",
            "legacy_manifest_migration_required",
            "Versionless validation-set manifests remain readable but cannot be consumable or frozen; rebuild/finalize with schema version 2.",
        )
        return False
    if type(schema_version) is not int or schema_version != MANIFEST_SCHEMA_VERSION:
        add(findings, "block", "invalid_manifest_schema_version", "Manifest must use supported integer schema version 2.", {"value": schema_version})
        return False
    if not is_string(manifest.get("oracle_results_path")):
        add(findings, "block", "missing_manifest_field", "Schema-v2 manifest is missing `oracle_results_path`.", {"field": "oracle_results_path"})
    return status in CONSUMABLE_STATUSES


def validate_items(items: list[dict[str, Any]], manifest: dict[str, Any], findings: list[dict[str, Any]]) -> set[str]:
    ids: list[str] = []
    extensions = manifest.get("source_class_extensions")
    allowed_extensions = {value for value in extensions if is_string(value)} if isinstance(extensions, list) else set()
    for index, item in enumerate(items, start=1):
        subject = f"Validation item {index}"
        require_fields(item, ("item_id", "source_class", "evidence_status"), findings, "missing_item_field", subject)
        if not nonempty(item.get("source_ref")) and not nonempty(item.get("source_hash")):
            add(findings, "block", "missing_item_source_trace", f"{subject} requires `source_ref` or `source_hash`.", {"item_id": item.get("item_id")})
        if not nonempty(item.get("task_family")) and not nonempty(item.get("failure_taxonomy")):
            add(findings, "block", "missing_item_task_classification", f"{subject} requires `task_family` or `failure_taxonomy`.", {"item_id": item.get("item_id")})
        item_id = item.get("item_id")
        if item_id is not None and not is_string(item_id):
            add(findings, "block", "invalid_item_id", "`item_id` must be a non-empty string.", {"index": index, "value": item_id})
        elif is_string(item_id):
            ids.append(item_id)
        source_class = item.get("source_class")
        if source_class not in ALLOWED_SOURCE_CLASSES and source_class not in allowed_extensions:
            add(findings, "block", "unknown_source_class", "Source class is not in the contract vocabulary or declared extensions.", {"item_id": item_id, "source_class": source_class})
        evidence_status = item.get("evidence_status")
        if not is_string(evidence_status):
            add(findings, "block", "invalid_evidence_status", "`evidence_status` must be a non-empty string.", {"item_id": item_id})
        if source_class in {"test_fixture", "synthetic_fixture", "sampled_real_metadata", "local_dataset_candidate"} and evidence_status in {"sampled_real_positive_evidence", "real_reviewed_work", "gold"}:
            add(findings, "block", "source_class_promotion_violation", "Item evidence status promotes a fixture/metadata class into sampled-real or gold evidence.", {"item_id": item_id, "source_class": source_class, "evidence_status": evidence_status})
        source_hash = item.get("source_hash")
        if source_hash is not None and not is_string(source_hash):
            add(findings, "block", "invalid_source_hash", "`source_hash` must be a non-empty hash string.", {"item_id": item_id})
        oracle_ids = item.get("oracle_ids")
        if oracle_ids is not None and (not isinstance(oracle_ids, list) or any(not is_string(value) for value in oracle_ids)):
            add(findings, "block", "invalid_item_oracle_ids", "`oracle_ids` must be a list of non-empty strings.", {"item_id": item_id})
        elif isinstance(oracle_ids, list) and len(oracle_ids) != len(set(oracle_ids)):
            add(findings, "block", "duplicate_item_oracle_id", "An item may reference each oracle at most once.", {"item_id": item_id})
    duplicates = [{"item_id": key, "count": count} for key, count in Counter(ids).items() if count > 1]
    if duplicates:
        add(findings, "block", "duplicate_item_id", "Item IDs must be unique.", duplicates[:20])
    return set(ids)


def validate_source_bindings(
    items: list[dict[str, Any]],
    *,
    root: Path,
    strict_v2: bool,
    consumable: bool,
    findings: list[dict[str, Any]],
) -> bool:
    if not strict_v2:
        return False
    all_bound = True
    for item in items:
        item_id = item.get("item_id")
        binding_type = item.get("source_binding_type")
        source_ref = item.get("source_ref")
        source_hash = item.get("source_hash")
        severity = "block" if consumable else "warn"
        if binding_type == "local_file":
            if not is_string(source_ref):
                add(findings, severity, "local_source_ref_missing", "A local-file binding requires a non-empty root-relative `source_ref`.", {"item_id": item_id})
                all_bound = False
                continue
            raw = Path(source_ref)
            if raw.is_absolute() or ".." in raw.parts:
                add(findings, "block", "local_source_path_escape", "Local source paths must be root-relative without parent traversal.", {"item_id": item_id, "source_ref": source_ref})
                all_bound = False
                continue
            source_path = within_root(root, root / raw)
            if source_path is None:
                add(findings, "block", "local_source_path_escape", "Local source path escapes the declared root, including through a symlink.", {"item_id": item_id, "source_ref": source_ref})
                all_bound = False
                continue
            if not source_path.is_file():
                add(findings, "block", "local_source_missing", "Local source binding does not resolve to a file.", {"item_id": item_id, "source_ref": source_ref})
                all_bound = False
                continue
            if not isinstance(source_hash, str) or not SHA256_RE.fullmatch(source_hash):
                add(findings, severity, "local_source_hash_missing", "A local-file binding requires a lowercase SHA-256 `source_hash`.", {"item_id": item_id})
                all_bound = False
                continue
            try:
                actual_hash = sha256_file(source_path)
            except (OSError, ValueError) as exc:
                add(findings, "block", "local_source_unhashable", "Local source bytes could not be hashed.", {"item_id": item_id, "error": str(exc)})
                all_bound = False
                continue
            if actual_hash != source_hash:
                add(findings, "block", "local_source_hash_mismatch", "Local source bytes no longer match the item source_hash.", {"item_id": item_id, "source_ref": source_ref, "declared": source_hash, "actual": actual_hash})
                all_bound = False
        elif binding_type == "authoritative_attestation":
            attestation = item.get("source_attestation")
            required = ("authority_ref", "attestation_ref", "attested_sha256")
            if (
                not is_string(source_ref)
                or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", source_ref) is None
                or not isinstance(attestation, dict)
                or attestation.get("authoritative") is not True
                or any(not is_string(attestation.get(field)) for field in required)
                or not isinstance(source_hash, str)
                or not SHA256_RE.fullmatch(source_hash)
                or attestation.get("attested_sha256") != source_hash
            ):
                add(findings, severity, "invalid_authoritative_source_attestation", "Authoritative source bindings require authoritative=true, authority/attestation refs, and an attested SHA-256 equal to item source_hash.", {"item_id": item_id})
                all_bound = False
        elif binding_type == "opaque_candidate":
            add(findings, severity, "opaque_source_binding_unverified", "Opaque/remote source locators may remain candidates but require an authoritative attestation before consumption.", {"item_id": item_id, "source_ref": source_ref})
            all_bound = False
        else:
            add(findings, severity, "invalid_source_binding_type", "Schema-v2 items require source_binding_type local_file, authoritative_attestation, or opaque_candidate.", {"item_id": item_id, "value": binding_type})
            all_bound = False
    return all_bound


def validate_labels(labels: list[dict[str, Any]], item_ids: set[str], findings: list[dict[str, Any]]) -> set[str]:
    label_ids: list[str] = []
    for index, label in enumerate(labels, start=1):
        subject = f"Label record {index}"
        require_fields(label, ("label_id", "item_id", "label_type", "label_status"), findings, "missing_label_field", subject)
        label_id = label.get("label_id")
        if not is_string(label_id):
            add(findings, "block", "invalid_label_id", "`label_id` must be a non-empty string.", {"index": index})
        else:
            label_ids.append(label_id)
        item_id = label.get("item_id")
        if is_string(item_id) and item_id not in item_ids:
            add(findings, "block", "label_references_missing_item", "Label references an item that does not exist.", {"label_id": label_id, "item_id": item_id})
        if label.get("label_type") not in LABEL_TYPES:
            add(findings, "block", "invalid_label_type", "`label_type` is not in the contract vocabulary.", {"label_id": label_id, "label_type": label.get("label_type")})
        if label.get("label_status") not in LABEL_STATUSES:
            add(findings, "block", "invalid_label_status", "`label_status` is not in the contract vocabulary.", {"label_id": label_id, "label_status": label.get("label_status")})
        if label.get("label_type") == "human_reviewed":
            if not is_string(label.get("human_reviewer_ref")) or not isinstance(label.get("evidence_refs"), list) or not all(is_string(value) for value in label.get("evidence_refs", [])) or not label.get("evidence_refs"):
                add(findings, "block", "human_reviewed_without_concrete_evidence", "Human-reviewed labels require a reviewer reference and at least one bounded evidence reference.", {"label_id": label_id})
        oracle_ids = label.get("oracle_ids")
        if oracle_ids is not None and (not isinstance(oracle_ids, list) or any(not is_string(value) for value in oracle_ids)):
            add(findings, "block", "invalid_label_oracle_ids", "`oracle_ids` must be a list of non-empty strings.", {"label_id": label_id})
        confidence = label.get("confidence")
        if confidence is not None and (type(confidence) not in {int, float} or not 0 <= confidence <= 1):
            add(findings, "block", "invalid_label_confidence", "`confidence` must be a JSON number between 0 and 1.", {"label_id": label_id, "value": confidence})
    duplicates = [{"label_id": key, "count": count} for key, count in Counter(label_ids).items() if count > 1]
    if duplicates:
        add(findings, "block", "duplicate_label_id", "Label IDs must be unique.", duplicates[:20])
    return set(label_ids)


def validate_oracles(
    oracle_manifest: dict[str, Any],
    manifest: dict[str, Any],
    items: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if oracle_manifest.get("validation_set_id") != manifest.get("validation_set_id"):
        add(findings, "block", "oracle_manifest_set_id_mismatch", "Oracle manifest must bind the same validation-set ID.")
    oracles = oracle_manifest.get("oracles")
    if not isinstance(oracles, list):
        add(findings, "block", "invalid_oracle_records", "Oracle manifest must contain an `oracles` list.")
        oracles = []
    oracle_count = oracle_manifest.get("oracle_count")
    if oracle_count is not None and (not is_json_int(oracle_count) or oracle_count != len(oracles)):
        add(findings, "block", "oracle_manifest_count_mismatch", "Oracle manifest count must be an exact non-negative integer matching `oracles`.", {"declared": oracle_count, "actual": len(oracles)})
    by_id: dict[str, dict[str, Any]] = {}
    for index, oracle in enumerate(oracles, start=1):
        if not isinstance(oracle, dict):
            add(findings, "block", "invalid_oracle_record", "Each oracle must be a JSON object.", {"index": index})
            continue
        require_fields(oracle, ("oracle_id", "oracle_type", "target", "description"), findings, "missing_oracle_field", f"Oracle {index}")
        oracle_id = oracle.get("oracle_id")
        if not is_string(oracle_id):
            add(findings, "block", "invalid_oracle_id", "`oracle_id` must be a non-empty string.", {"index": index})
        elif oracle_id in by_id:
            add(findings, "block", "duplicate_oracle_id", "Oracle IDs must be unique.", {"oracle_id": oracle_id})
        else:
            by_id[oracle_id] = oracle
        if oracle.get("oracle_type") not in ORACLE_TYPES:
            add(findings, "block", "invalid_oracle_type", "Oracle type is not recognized.", {"oracle_id": oracle_id})
        if oracle.get("target") not in ORACLE_TARGETS:
            add(findings, "block", "invalid_oracle_target", "Oracle target is not recognized.", {"oracle_id": oracle_id})
        for field in ("required_fields", "forbidden_fields"):
            value = oracle.get(field)
            if value is not None and (not isinstance(value, list) or any(not is_string(entry) for entry in value)):
                add(findings, "block", "invalid_oracle_field_list", f"`{field}` must be a list of non-empty strings.", {"oracle_id": oracle_id})
        allowed_values = oracle.get("allowed_values")
        if allowed_values is not None and (not isinstance(allowed_values, dict) or any(not isinstance(values, list) for values in allowed_values.values())):
            add(findings, "block", "invalid_oracle_allowed_values", "`allowed_values` must map fields to JSON lists.", {"oracle_id": oracle_id})
    referenced: list[tuple[str, str]] = []
    # Preserve record-local evidence paths while checking every oracle reference.
    for record_kind, records in (("item", items), ("label", labels)):
        for record in records:
            record_id = str(record.get("item_id") if record_kind == "item" else record.get("label_id"))
            for oracle_id in record.get("oracle_ids") or []:
                referenced.append((record_id, str(oracle_id)))
    for record_id, oracle_id in referenced:
        if oracle_id not in by_id:
            add(findings, "block", "unresolved_oracle_reference", "A record references an unknown oracle.", {"record_id": record_id, "oracle_id": oracle_id})
    return by_id


def authoritative_human_pairs(labels: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for label in labels:
        if (
            label.get("label_type") != "human_reviewed"
            or label.get("label_status") != "accepted"
            or label.get("authoritative") is not True
            or not is_string(label.get("human_reviewer_ref"))
            or not isinstance(label.get("evidence_refs"), list)
            or not label.get("evidence_refs")
            or any(not is_string(value) for value in label.get("evidence_refs", []))
            or not is_string(label.get("item_id"))
            or not isinstance(label.get("oracle_ids"), list)
        ):
            continue
        pairs.update((label["item_id"], oracle_id) for oracle_id in label["oracle_ids"] if is_string(oracle_id))
    return pairs


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


def validate(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    requested = Path(args.manifest) if args.manifest else Path(args.set_root) / "validation_set_manifest.json"
    requested = requested if requested.is_absolute() else root / requested
    manifest_path = within_root(root, requested)
    findings: list[dict[str, Any]] = []
    manifest_allowed = manifest_path is not None
    if manifest_path is None:
        add(findings, "block", "manifest_path_escape", "Manifest path escapes the declared root, including through a symlink.", {"path": str(requested)})
        manifest_path = requested.resolve(strict=False)
    if not manifest_allowed:
        manifest = {}
    elif not manifest_path.is_file():
        add(findings, "block", "manifest_file_missing", "Validation-set manifest does not exist.", {"path": str(manifest_path)})
        manifest = {}
    else:
        manifest = read_json(manifest_path, findings, "validation_set_manifest")
    base = manifest_path.parent
    strict_v2 = type(manifest.get("manifest_schema_version")) is int and manifest.get("manifest_schema_version") == MANIFEST_SCHEMA_VERSION
    legacy_manifest = manifest.get("manifest_schema_version") is None
    consumable = validate_manifest(manifest, findings)
    paths: dict[str, Path | None] = {}
    path_fields = ["items_path", "labels_path", "oracle_manifest_path", "split_manifest_path", "leakage_report_path"]
    if strict_v2 or "oracle_results_path" in manifest:
        path_fields.append("oracle_results_path")
    for field in path_fields:
        path = resolve_manifest_path(root, base, manifest.get(field), field, findings)
        paths[field] = path
        if path is None or not path.is_file():
            add(findings, "block", "manifest_path_missing", f"`{field}` does not resolve to a file.", {"path": str(path) if path else None})
    items = read_jsonl(paths["items_path"], findings, "validation_set_items") if paths["items_path"] and paths["items_path"].is_file() else []
    labels = read_jsonl(paths["labels_path"], findings, "validation_set_labels") if paths["labels_path"] and paths["labels_path"].is_file() else []
    oracle_manifest = read_json(paths["oracle_manifest_path"], findings, "oracle_manifest") if paths["oracle_manifest_path"] and paths["oracle_manifest_path"].is_file() else {}
    split_manifest = read_json(paths["split_manifest_path"], findings, "split_manifest") if paths["split_manifest_path"] and paths["split_manifest_path"].is_file() else {}
    leakage_report = read_json(paths["leakage_report_path"], findings, "leakage_report") if paths["leakage_report_path"] and paths["leakage_report_path"].is_file() else {}
    oracle_results_path = paths.get("oracle_results_path")
    oracle_results = read_json(oracle_results_path, findings, "oracle_results") if oracle_results_path and oracle_results_path.is_file() else {}
    durable = {"manifest": manifest, "items": items, "labels": labels, "oracles": oracle_manifest, "oracle_results": oracle_results, "splits": split_manifest, "leakage": leakage_report}
    forbidden_paths = walk_forbidden(durable)
    if forbidden_paths:
        add(findings, "block", "raw_body_field_persisted", "Durable validation artifacts contain forbidden raw-body field names, even if their current values are empty.", forbidden_paths[:20])
    validate_boolean_fields(durable, findings)
    item_ids = validate_items(items, manifest, findings)
    source_bindings_verified = validate_source_bindings(items, root=root, strict_v2=strict_v2, consumable=consumable, findings=findings)
    validate_labels(labels, item_ids, findings)
    oracles = validate_oracles(oracle_manifest, manifest, items, labels, findings)
    oracle_results_verified = validate_oracle_results(
        oracle_results,
        manifest=manifest,
        items=items,
        labels=labels,
        oracles=oracles,
        items_path=paths.get("items_path"),
        oracle_manifest_path=paths.get("oracle_manifest_path"),
        strict_v2=strict_v2,
        consumable=consumable,
        findings=findings,
    )
    validate_scenario_coverage(manifest, items, labels, oracles, oracle_results, root, consumable, findings)
    validate_split_manifest(split_manifest, manifest, item_ids, consumable, root, base, findings)
    validate_counts(manifest, items, labels, len(oracles), consumable, findings)
    leakage_status = leakage_report.get("status")
    leakage_execution = leakage_report.get("execution_status")
    if leakage_status == "block":
        add(findings, "block", "leakage_report_blocking", "Leakage report contains blocking findings.", leakage_report.get("findings"))
    if leakage_execution != "completed" or leakage_status not in {"ok", "warn", "block"}:
        add(findings, "block" if consumable else "warn", "leakage_not_evaluated", "Leakage checking must report `execution_status: completed` before the set is consumable.", {"status": leakage_status, "execution_status": leakage_execution})
    if leakage_execution == "completed":
        for field, actual in (("item_count", len(items)), ("label_count", len(labels))):
            if not is_json_int(leakage_report.get(field)) or leakage_report.get(field) != actual:
                add(findings, "block" if consumable else "warn", "leakage_count_mismatch", f"Leakage report `{field}` must match the bound records.", {"reported": leakage_report.get(field), "actual": actual})
    if consumable and leakage_status not in {"ok", "warn"}:
        add(findings, "block", "consumable_leakage_not_clear", "A consumable validation set requires a completed non-blocking leakage report.")
    if consumable and not source_bindings_verified:
        add(findings, "block", "consumable_source_bindings_unverified", "Every consumable item requires a verified local source binding or authoritative attestation.")
    if consumable and not oracle_results_verified:
        add(findings, "block", "consumable_oracle_results_unverified", "Consumable sets require current completed non-blocking oracle results.")
    if consumable:
        artifact_paths = {
            name: paths[field]
            for name, field in ARTIFACT_FIELDS.items()
            if paths.get(field) is not None and paths[field].is_file()
        }
        if len(artifact_paths) != len(ARTIFACT_FIELDS):
            add(findings, "block", "finalization_inputs_missing", "Complete schema-v2 sets require every finalization input artifact.")
        else:
            validate_finalization_record(manifest, artifact_paths, oracle_results, findings)
    validate_gold(manifest, labels, oracles, findings)
    status = "block" if any(item["severity"] == "block" for item in findings) else "warn" if findings else "ok"
    if consumable and status == "ok":
        readiness = "consumable"
    elif legacy_manifest and manifest.get("validation_set_status") == "complete" and status != "block":
        readiness = "migration_required"
    elif not consumable and status != "block":
        readiness = "candidate"
    else:
        readiness = "blocked"
    return {
        "status": status,
        "readiness": readiness,
        "manifest_path": str(manifest_path),
        "validation_set_id": manifest.get("validation_set_id"),
        "item_count": len(items),
        "label_count": len(labels),
        "oracle_count": len(oracles),
        "findings": findings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate validation-set manifest/files and no-overclaim guardrails.")
    parser.add_argument("--root", default=".")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--set-root")
    group.add_argument("--manifest")
    parser.add_argument("--warn-only", action="store_true")
    args = parser.parse_args(argv)
    result = validate(args)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.warn_only:
        return 0
    return 2 if result["status"] == "block" else 0


if __name__ == "__main__":
    raise SystemExit(main())
