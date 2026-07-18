from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .common import bounded_opaque_id, boolish, first_present


FULL_SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_BINDING_FIELDS = {"revision_id", "content_digest"}
RECEIPT_MATERIAL_FIELDS = (
    "schema_version",
    "run_id",
    "input_revision_id",
    "input_digest",
    "output_digest",
)
RECEIPT_FIELDS = {*RECEIPT_MATERIAL_FIELDS, "receipt_sha256"}
APPLICABILITY_VALUES = {
    "applicable",
    "excluded_by_task",
    "not_applicable",
    "legacy_unspecified",
    "scope_unknown",
}


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def full_sha256(value: object) -> str | None:
    text = str(value or "").strip()
    return text if FULL_SHA256.fullmatch(text) else None


def execution_applicability(event: dict[str, Any]) -> tuple[str, str | None]:
    raw = first_present(
        event,
        (
            "execution_scope_applicability",
            "execution_scope.applicability",
            "profile_contract.execution_scope_applicability",
        ),
    )
    if raw is None:
        return "legacy_unspecified", None
    if not isinstance(raw, str):
        return "scope_unknown", None
    status = raw.strip().lower()
    if status not in {"applicable", "excluded_by_task", "not_applicable"}:
        return "scope_unknown", None
    reason = bounded_opaque_id(
        first_present(
            event,
            (
                "execution_scope_exclusion_reason_id",
                "execution_scope.exclusion_reason_id",
                "profile_contract.execution_scope_exclusion_reason_id",
            ),
        )
    )
    return status, reason


def required_input_binding(event: dict[str, Any]) -> tuple[dict[str, str] | None, str]:
    raw = first_present(
        event,
        (
            "required_input_binding",
            "execution.required_input_binding",
            "profile_contract.required_input_binding",
        ),
    )
    if raw is None:
        return None, "absent"
    if not isinstance(raw, dict) or set(raw) != REQUIRED_BINDING_FIELDS:
        return None, "invalid"
    revision_id = bounded_opaque_id(raw.get("revision_id"))
    content_digest = full_sha256(raw.get("content_digest"))
    if revision_id is None or content_digest is None:
        return None, "invalid"
    return {"revision_id": revision_id, "content_digest": content_digest}, "valid"


def producer_run_receipt(event: dict[str, Any]) -> dict[str, Any] | None:
    raw = first_present(
        event,
        (
            "producer_run_receipt",
            "execution.producer_run_receipt",
            "run.producer_run_receipt",
        ),
    )
    return normalize_producer_run_receipt(raw)


def normalize_producer_run_receipt(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or set(raw) != RECEIPT_FIELDS:
        return None
    run_id = bounded_opaque_id(raw.get("run_id"))
    input_revision_id = bounded_opaque_id(raw.get("input_revision_id"))
    input_digest = full_sha256(raw.get("input_digest"))
    output_digest = full_sha256(raw.get("output_digest"))
    receipt_sha256 = full_sha256(raw.get("receipt_sha256"))
    schema_version = raw.get("schema_version")
    material = {
        "schema_version": schema_version,
        "run_id": run_id,
        "input_revision_id": input_revision_id,
        "input_digest": input_digest,
        "output_digest": output_digest,
    }
    if (
        schema_version != 1
        or run_id is None
        or input_revision_id is None
        or input_digest is None
        or output_digest is None
        or receipt_sha256 != canonical_sha256(material)
    ):
        return None
    return {**material, "receipt_sha256": receipt_sha256}


def matching_fresh_run(
    event: dict[str, Any],
    required_binding: dict[str, str] | None,
    *,
    strict_binding: bool,
) -> tuple[str | None, dict[str, Any] | None]:
    if boolish(
        first_present(event, ("replayed", "run_replayed", "carried_forward_run"))
    ):
        return None, None
    receipt = producer_run_receipt(event)
    if required_binding is not None:
        if receipt is None:
            return None, None
        raw_run_id = first_present(
            event,
            ("run_id", "execution.run_id", "run.run_id", "fresh_run_id"),
        )
        declared_run_id = bounded_opaque_id(raw_run_id)
        if raw_run_id is not None and declared_run_id != receipt["run_id"]:
            return None, None
        if (
            receipt["input_revision_id"] != required_binding["revision_id"]
            or receipt["input_digest"] != required_binding["content_digest"]
        ):
            return None, None
        return str(receipt["run_id"]), receipt
    if strict_binding:
        return None, None
    legacy_run_id = bounded_opaque_id(
        first_present(
            event,
            ("run_id", "execution.run_id", "run.run_id", "fresh_run_id"),
        )
    )
    return legacy_run_id, None
