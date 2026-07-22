"""Exact cache identities for deterministic facts plus semantic receipts."""

from __future__ import annotations

import ast
import platform
import sys
from typing import Any

from .contracts import (
    ADJUDICATOR_REVISION,
    ANALYZER_REVISION,
    CACHE_SCHEMA_REVISION,
    SEMANTIC_SCHEMA_REVISION,
    object_sha256,
    require_closed_fields,
    require_sha256,
)
from .semantic_receipt import validate_semantic_receipt


def _row_basis(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    closure = row.get("runtime_closure")
    return {
        "adapter_id": row.get("adapter_id"),
        "manifest_sha256": row.get("manifest_sha256"),
        "adapter_revision_sha256": row.get("adapter_revision_sha256"),
        "component_registry_sha256": row.get("component_registry_sha256"),
        "runtime_closure_sha256": closure.get("runtime_closure_sha256")
        if isinstance(closure, dict)
        else None,
        "code_convention_contract_sha256": row.get(
            "code_convention_contract_sha256"
        ),
        "hook_contract_sha256": row.get("hook_contract_sha256"),
    }


def architecture_cache_fingerprint(
    before_row: dict[str, Any] | None,
    after_row: dict[str, Any],
    *,
    policy_revision: str = "adapter-architecture-policy-v1",
) -> str:
    basis = {
        "cache_schema_revision": CACHE_SCHEMA_REVISION,
        "subject_manifest_before": _row_basis(before_row),
        "subject_manifest_after": _row_basis(after_row),
        "analyzer_revision": ANALYZER_REVISION,
        "adjudicator_revision": ADJUDICATOR_REVISION,
        "semantic_schema_revision": SEMANTIC_SCHEMA_REVISION,
        "policy_revision": policy_revision,
        "parser_versions": {
            "python": platform.python_version(),
            "implementation_cache_tag": sys.implementation.cache_tag,
            "ast_module": getattr(ast, "__version__", "stdlib"),
        },
    }
    return object_sha256(basis)


def validate_cache_receipt(
    receipt: dict[str, Any],
    *,
    expected_fingerprint: str,
    adapter_id: str,
    adapter_revision_sha256: str,
    convention_sha256: str,
    fact_packet_sha256: str,
    structural_pressures: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise ValueError("architecture cache receipt must be an object")
    require_closed_fields(
        receipt,
        required={
            "schema_version",
            "artifact_kind",
            "cache_schema_revision",
            "cache_fingerprint",
            "semantic_receipt",
            "cache_receipt_sha256",
        },
        label="architecture cache receipt",
    )
    if (
        receipt["schema_version"] != 1
        or receipt["artifact_kind"] != "adapter_architecture_cache_receipt"
        or receipt["cache_schema_revision"] != CACHE_SCHEMA_REVISION
    ):
        raise ValueError("architecture cache receipt schema is unsupported")
    if require_sha256(receipt["cache_fingerprint"], "cache_fingerprint") != expected_fingerprint:
        raise ValueError("architecture cache fingerprint mismatch")
    body = {key: value for key, value in receipt.items() if key != "cache_receipt_sha256"}
    if require_sha256(receipt["cache_receipt_sha256"], "cache_receipt_sha256") != object_sha256(body):
        raise ValueError("architecture cache receipt integrity mismatch")
    semantic = validate_semantic_receipt(
        receipt["semantic_receipt"],
        adapter_id=adapter_id,
        adapter_revision_sha256=adapter_revision_sha256,
        convention_sha256=convention_sha256,
        fact_packet_sha256=fact_packet_sha256,
        structural_pressures=structural_pressures,
    )
    return {**receipt, "semantic_receipt": semantic}


__all__ = ("architecture_cache_fingerprint", "validate_cache_receipt")
