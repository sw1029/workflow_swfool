from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .constants import REGISTRY_REL_PATH
from .io_utils import read_jsonl, read_text, rel_path
from .values import number_value
from ..ledger.operation_contract import (
    build_durable_operation,
    build_typed_operations_candidate,
)


def _legacy_symbol_registry(root: Path) -> dict[str, dict[str, Any]]:
    registry_path = root / REGISTRY_REL_PATH
    latest: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(registry_path):
        symbol = record.get("symbol")
        if isinstance(symbol, str) and symbol:
            latest[symbol] = record
    return latest


def load_symbol_registry_state(
    root: Path,
    finalized_cycle_id: str | None = None,
) -> dict[str, Any]:
    """Load either an explicitly verified projection or legacy flat state."""
    if finalized_cycle_id is None:
        return {
            "status": "legacy_compat",
            "receipt_verified": False,
            "finalized_cycle_id": None,
            "rows": _legacy_symbol_registry(root),
            "findings": [],
        }
    try:
        from ..cycle_ledger import load_current_finalized_state

        finalized = load_current_finalized_state(root, finalized_cycle_id)
    except Exception as exc:
        return {
            "status": "block",
            "receipt_verified": False,
            "finalized_cycle_id": finalized_cycle_id,
            "rows": {},
            "findings": [
                {
                    "severity": "block",
                    "code": "finalized_registry_receipt_load_failed",
                    "error_class": exc.__class__.__name__,
                }
            ],
        }
    if not finalized.get("valid"):
        return {
            "status": "block",
            "receipt_verified": False,
            "finalized_cycle_id": finalized_cycle_id,
            "rows": {},
            "findings": [
                {
                    "severity": "block",
                    "code": "finalized_registry_receipt_invalid",
                    "errors": finalized.get("errors") or [],
                }
            ],
        }
    durable = finalized.get("durable_state_candidate")
    if (
        not isinstance(durable, dict)
        or durable.get("contract_version") != 2
        or durable.get("mode") != "typed_operations"
        or durable.get("producer") != "progress_loop_detection"
    ):
        return {
            "status": "block",
            "receipt_verified": True,
            "finalized_cycle_id": finalized_cycle_id,
            "rows": {},
            "findings": [{"severity": "block", "code": "finalized_registry_contract_mismatch"}],
        }
    target_projection = finalized.get("post_write_projection")
    projection = (
        target_projection.get("dedup_symbol_registry")
        if isinstance(target_projection, dict)
        else None
    )
    if not isinstance(projection, dict):
        return {
            "status": "block",
            "receipt_verified": True,
            "finalized_cycle_id": finalized_cycle_id,
            "rows": {},
            "findings": [
                {
                    "severity": "block",
                    "code": "finalized_registry_projection_missing_or_ambiguous",
                    "projection_count": 0,
                }
            ],
        }
    payload = projection.get("payload")
    if projection.get("operation_kind") != "replace_projection":
        return {
            "status": "block",
            "receipt_verified": True,
            "finalized_cycle_id": finalized_cycle_id,
            "rows": {},
            "findings": [{"severity": "block", "code": "finalized_registry_operation_type_mismatch"}],
        }
    raw_rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(raw_rows, list):
        return {
            "status": "block",
            "receipt_verified": True,
            "finalized_cycle_id": finalized_cycle_id,
            "rows": {},
            "findings": [{"severity": "block", "code": "finalized_registry_rows_not_list"}],
        }
    rows: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(raw_rows):
        symbol = row.get("symbol") if isinstance(row, dict) else None
        if (
            not isinstance(symbol, str)
            or not symbol
            or symbol in rows
            or not set(row).issubset(_DURABLE_REGISTRY_FIELDS)
        ):
            return {
                "status": "block",
                "receipt_verified": True,
                "finalized_cycle_id": finalized_cycle_id,
                "rows": {},
                "findings": [
                    {
                        "severity": "block",
                        "code": "finalized_registry_row_invalid",
                        "index": index,
                    }
                ],
            }
        rows[symbol] = row
    return {
        "status": "verified_current",
        "receipt_verified": True,
        "finalized_cycle_id": finalized_cycle_id,
        "rows": rows,
        "findings": [],
    }


def load_symbol_registry(
    root: Path,
    finalized_cycle_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    state = load_symbol_registry_state(root, finalized_cycle_id)
    if state["status"] == "block":
        raise ValueError("finalized symbol registry is not consumable")
    return state["rows"]


_DURABLE_REGISTRY_FIELDS = {
    "symbol",
    "scope",
    "first_seen_evidence_id",
    "occurrence_count",
    "consumed_input_fp",
    "target_unit_fp",
    "target_unit_count",
    "observed_output_classes",
    "last_observed_output_class",
    "last_observed_material_delta",
    "artifact_fingerprint",
    "artifact_count_fingerprint",
    "last_evidence_id",
    "status",
}


def _durable_registry_row(value: dict[str, Any]) -> dict[str, Any]:
    """Project one registry row without source paths, locators, or quoted content."""
    return {key: value.get(key) for key in sorted(_DURABLE_REGISTRY_FIELDS) if key in value}


def _opaque_evidence_id(feature: dict[str, Any], observed: dict[str, Any]) -> str:
    material = {
        "symbol": feature.get("symbol"),
        "observed_output_class": observed.get("observed_output_class"),
        "artifact_fingerprint": observed.get("artifact_fingerprint"),
        "artifact_count_fingerprint": observed.get("artifact_count_fingerprint"),
    }
    canonical = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "evidence-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def terminal_history_matches(root: Path, feature: dict[str, Any]) -> list[dict[str, Any]]:
    axis = str(feature.get("blocker_root_axis") or "")
    if not axis or axis == "unknown":
        return []
    candidates: list[Path] = []
    for group in (
        root / ".task" / "cycle",
        root / ".task" / "task_miss",
    ):
        if group.is_dir():
            candidates.extend(
                path
                for path in group.rglob("*")
                if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".md"}
            )
    sealed = root / ".task" / "sealed_blocker_families.json"
    if sealed.is_file():
        candidates.append(sealed)
    matches: list[dict[str, Any]] = []
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        text = read_text(path).lower()
        if axis not in text:
            continue
        reason = None
        for token in ("no_material_miss", "no-material-miss", "fail_closed", "fail-closed", "terminal", "sealed"):
            if token in text:
                reason = token
                break
        if reason:
            matches.append({"path": rel_path(root, path), "reason_code": reason})
    return matches


def prepare_feature_symbol_registry_update(
    root: Path,
    current_item: dict[str, Any],
    recurrence_threshold: int | None = None,
    previous_registry: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a complete typed projection without mutating durable state."""
    feature = current_item.get("feature_symbol")
    observed = current_item.get("observed_output")
    attempt_identity = str(
        current_item.get("attempt_identity") or current_item.get("attempt_id") or ""
    ).strip()
    if not isinstance(feature, dict) or not isinstance(observed, dict) or not feature.get("symbol"):
        return {
            "write_enabled": False,
            "legacy_write_requested": True,
            "updated": False,
            "prepared": False,
            "reason": "missing_feature_symbol",
        }
    if not attempt_identity:
        return {
            "write_enabled": False,
            "legacy_write_requested": True,
            "updated": False,
            "prepared": False,
            "reason": "missing_attempt_identity",
        }
    registry = previous_registry if previous_registry is not None else load_symbol_registry(root)
    previous = registry.get(str(feature["symbol"])) or {}
    observed_class = str(observed.get("observed_output_class") or "unknown")
    prior_classes = [str(item) for item in previous.get("observed_output_classes", []) if item is not None]
    if observed_class == "material_delta":
        occurrence_count = 1
        status = "observed_delta"
    else:
        occurrence_count = int(number_value(previous.get("occurrence_count")) or 0) + 1
        if recurrence_threshold is None:
            status = "budget_unverified"
        else:
            status = "recurring_no_delta" if occurrence_count >= recurrence_threshold else "seen"
    evidence_id = _opaque_evidence_id(feature, observed)
    record = {
        "symbol": feature["symbol"],
        "scope": "workflow_loop",
        "first_seen_evidence_id": previous.get("first_seen_evidence_id") or evidence_id,
        "occurrence_count": occurrence_count,
        "consumed_input_fp": feature.get("consumed_input_fp"),
        "target_unit_fp": feature.get("target_unit_fp"),
        "target_unit_count": feature.get("target_unit_count"),
        "observed_output_classes": [*prior_classes, observed_class],
        "last_observed_output_class": observed_class,
        "last_observed_material_delta": int(observed.get("artifact_record_count") or 0),
        "artifact_fingerprint": observed.get("artifact_fingerprint") or previous.get("artifact_fingerprint"),
        "artifact_count_fingerprint": observed.get("artifact_count_fingerprint") or previous.get("artifact_count_fingerprint"),
        "last_evidence_id": evidence_id,
        "status": status,
    }
    projected = {
        symbol: _durable_registry_row(row)
        for symbol, row in registry.items()
        if isinstance(row, dict)
    }
    projected[str(feature["symbol"])] = _durable_registry_row(record)
    payload = {"rows": [projected[key] for key in sorted(projected)]}
    operation = build_durable_operation(
        target_ref="dedup_symbol_registry",
        operation_kind="replace_projection",
        attempt_identity=attempt_identity,
        payload_schema_id="dedup-symbol-registry-v1",
        payload=payload,
    )
    candidate = build_typed_operations_candidate(
        producer="progress_loop_detection",
        attempt_identity=attempt_identity,
        operations=[operation],
    )
    return {
        "write_enabled": False,
        "legacy_write_requested": True,
        "updated": False,
        "prepared": True,
        "finalization_required": True,
        "state_commit_status": "not_finalized",
        "symbol": feature["symbol"],
        "occurrence_count": occurrence_count,
        "status": status,
        "durable_mutation_candidate": candidate,
    }


def append_feature_symbol_registry(
    root: Path,
    current_item: dict[str, Any],
    recurrence_threshold: int | None = None,
    previous_registry: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compatibility alias retained as a prepare-only operation."""
    return prepare_feature_symbol_registry_update(
        root,
        current_item,
        recurrence_threshold,
        previous_registry,
    )
