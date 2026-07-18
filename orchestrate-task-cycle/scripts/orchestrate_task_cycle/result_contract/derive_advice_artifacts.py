"""Durable runtime-artifact bindings for derive advice synthesis."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .advice_runtime_artifacts import (
    RUNTIME_ARTIFACT_STORE_KIND,
    canonical_json_bytes,
    decision_cycle_id,
    verify_cycle_artifact,
    workspace_root,
)


SYNTHESIS_OUTPUT_FIELDS = (
    "synthesis_agent_id",
    "synthesis_receipt_id",
    "input_evidence_manifest_sha256",
    "consumed_agent_receipt_ids",
    "candidate_union_sha256",
    "selected_candidate_id",
    "selection_outcome",
    "pack_disposition",
    "advice_clause_set_sha256",
    "advice_reconciliation_sha256",
)
LENS_RECEIPT_FIELDS = (
    "role_id",
    "agent_id",
    "agent_receipt_id",
    "read_only",
    "status",
    "input_evidence_manifest_sha256",
    "output_ref",
    "output_sha256",
    "output",
)


def advice_lens_receipt_projection(lens: dict[str, Any]) -> dict[str, Any]:
    return {field: lens.get(field) for field in LENS_RECEIPT_FIELDS}


def advice_synthesis_output_projection(
    synthesis: dict[str, Any],
) -> dict[str, Any]:
    return {field: synthesis.get(field) for field in SYNTHESIS_OUTPUT_FIELDS}


def advice_synthesis_output_sha256(synthesis: dict[str, Any]) -> str:
    return hashlib.sha256(
        canonical_json_bytes(advice_synthesis_output_projection(synthesis))
    ).hexdigest()


def derive_runtime_artifact_binding(
    result: dict[str, Any],
    analysis: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    explicit_root: str | Path | None = None,
) -> dict[str, Any] | None:
    cycle_id = decision_cycle_id(result)
    lenses = analysis.get("lens_results")
    synthesis = analysis.get("synthesis")
    if (
        cycle_id is None
        or not isinstance(lenses, list)
        or len(lenses) != 3
        or not isinstance(synthesis, dict)
    ):
        return None
    root = workspace_root(result, context, explicit_root)
    artifacts: list[dict[str, Any]] = []
    for lens in lenses:
        binding = _lens_artifact_binding(root, cycle_id, lens)
        if binding is None:
            return None
        artifacts.append(binding)
    synthesis_binding = verify_cycle_artifact(
        root,
        cycle_id,
        synthesis.get("synthesis_output_ref"),
        advice_synthesis_output_projection(synthesis),
    )
    if synthesis_binding is None or synthesis_binding[
        "artifact_sha256"
    ] != synthesis.get("synthesis_output_sha256"):
        return None
    artifacts.append(
        {
            "artifact_kind": "synthesis_output",
            "agent_id": synthesis.get("synthesis_agent_id"),
            "agent_receipt_id": synthesis.get("synthesis_receipt_id"),
            **synthesis_binding,
        }
    )
    refs = [row["artifact_ref"] for row in artifacts]
    if len(set(refs)) != 4:
        return None
    return {
        "runtime_artifact_store_kind": RUNTIME_ARTIFACT_STORE_KIND,
        "cycle_id": cycle_id,
        "artifacts": artifacts,
        "artifact_set_sha256": hashlib.sha256(
            canonical_json_bytes(artifacts)
        ).hexdigest(),
    }


def _lens_artifact_binding(
    root: Path, cycle_id: str, lens: object
) -> dict[str, Any] | None:
    if not isinstance(lens, dict) or not isinstance(lens.get("output"), dict):
        return None
    binding = verify_cycle_artifact(
        root,
        cycle_id,
        lens.get("output_ref"),
        advice_lens_receipt_projection(lens),
    )
    if binding is None:
        return None
    return {
        "artifact_kind": "lens_output",
        "role_id": lens.get("role_id"),
        "agent_id": lens.get("agent_id"),
        "agent_receipt_id": lens.get("agent_receipt_id"),
        "output_sha256": lens.get("output_sha256"),
        **binding,
    }


__all__ = (
    "advice_lens_receipt_projection",
    "advice_synthesis_output_projection",
    "advice_synthesis_output_sha256",
    "derive_runtime_artifact_binding",
)
