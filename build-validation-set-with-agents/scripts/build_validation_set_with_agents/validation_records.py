"""Validation rules for manifests, items, labels, and oracle declarations."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .validation_common import (
    ALLOWED_SOURCE_CLASSES,
    CONSUMABLE_STATUSES,
    LABEL_STATUSES,
    LABEL_TYPES,
    ORACLE_TARGETS,
    ORACLE_TYPES,
    QUALITY_TIERS,
    VALIDATION_SET_STATUSES,
    add,
    is_json_int,
    is_string,
    nonempty,
    require_fields,
    within_root,
)
from .validation_set_contract import MANIFEST_SCHEMA_VERSION, SHA256_RE, sha256_file

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
