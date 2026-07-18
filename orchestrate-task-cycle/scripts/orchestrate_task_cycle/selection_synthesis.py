"""Closed durable projection of the three-lens derive synthesis."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


SYNTHESIS_KEYS = {
    "schema_version",
    "artifact_kind",
    "derive_contract_version",
    "selection_synthesis_id",
    "cycle_id",
    "selection_outcome",
    "selected_task_id",
    "pack_disposition",
    "selected_candidate_id",
    "synthesis_receipt_id",
    "input_evidence_manifest_sha256",
    "improvement_analysis_manifest",
    "runtime_artifact_binding",
    "runtime_artifact_set_sha256",
    "not_goal_truth",
    "not_authority",
    "mutation_performed",
    "selection_synthesis_sha256",
}
OUTCOMES = frozenset(
    {"selected", "terminal_wait", "terminal_blocked", "user_escalation"}
)
OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _analysis_findings(value: dict[str, Any]) -> list[dict[str, Any]]:
    # Lazy imports avoid a module cycle through the terminal derive rule, which
    # consumes durable selection receipts.
    from .result_contract.base import RuleContext
    from .result_contract.rules.derive_checks.analysis_contract import (
        check_analysis_contract,
    )
    from .result_contract.rules.derive_checks.state import DeriveFacts

    findings: list[dict[str, Any]] = []
    context = RuleContext(
        target="derive",
        result=value,
        mode="block",
        findings=findings,
        missing=[],
        require_context_field=lambda _field, _code, _message: None,
    )
    check_analysis_contract(DeriveFacts(context))
    return findings


def _runtime_binding(
    root: Path, source_result: dict[str, Any], analysis: dict[str, Any]
) -> dict[str, Any]:
    from .result_contract.derive_advice_artifacts import (
        derive_runtime_artifact_binding,
    )

    binding = derive_runtime_artifact_binding(
        source_result,
        analysis,
        explicit_root=root,
    )
    if not isinstance(binding, dict):
        raise ValueError("selection synthesis runtime agent artifacts are invalid")
    return binding


def _projection_core(root: Path, source_result: dict[str, Any]) -> dict[str, Any]:
    analysis = source_result.get("improvement_analysis_manifest")
    synthesis = analysis.get("synthesis") if isinstance(analysis, dict) else None
    if not isinstance(analysis, dict) or not isinstance(synthesis, dict):
        raise ValueError("selection synthesis requires one analysis synthesis receipt")
    cycle_id = source_result.get("cycle_id")
    if not isinstance(cycle_id, str) or not OPAQUE_ID.fullmatch(cycle_id):
        raise ValueError("selection synthesis requires one explicit cycle ID")
    runtime_binding = _runtime_binding(root, source_result, analysis)
    if runtime_binding.get("cycle_id") != cycle_id:
        raise ValueError("selection synthesis cycle differs from runtime artifacts")
    outcome = source_result.get("selection_outcome")
    selected_task = source_result.get("next_task_id")
    if selected_task is None or selected_task == "":
        selected_task_id = None
    elif (
        isinstance(selected_task, str)
        and selected_task == selected_task.strip()
        and OPAQUE_ID.fullmatch(selected_task)
    ):
        selected_task_id = selected_task
    else:
        raise ValueError("selection synthesis next task ID is not canonical")
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise ValueError("selection synthesis outcome is invalid")
    if outcome == "selected":
        if selected_task_id is None:
            raise ValueError("selected synthesis requires one bounded next task ID")
    elif selected_task_id is not None:
        raise ValueError("non-selected synthesis cannot carry a next task ID")
    pack_disposition = source_result.get("pack_disposition")
    selected_candidate_id = source_result.get("selected_candidate_id")
    if (
        not isinstance(pack_disposition, str)
        or not OPAQUE_ID.fullmatch(pack_disposition)
        or not isinstance(selected_candidate_id, str)
        or selected_candidate_id != selected_candidate_id.strip()
        or (outcome == "selected" and not OPAQUE_ID.fullmatch(selected_candidate_id))
        or (outcome != "selected" and selected_candidate_id != "")
    ):
        raise ValueError("selection synthesis disposition projection is invalid")
    receipt_id = synthesis.get("synthesis_receipt_id")
    input_digest = synthesis.get("input_evidence_manifest_sha256")
    if (
        not isinstance(receipt_id, str)
        or not OPAQUE_ID.fullmatch(receipt_id)
        or not isinstance(input_digest, str)
        or not SHA256.fullmatch(input_digest)
    ):
        raise ValueError("selection synthesis receipt identity is invalid")
    return {
        "schema_version": 1,
        "artifact_kind": "derive_selection_synthesis",
        "derive_contract_version": 2,
        "cycle_id": cycle_id,
        "selection_outcome": outcome,
        "selected_task_id": selected_task_id,
        "pack_disposition": pack_disposition,
        "selected_candidate_id": selected_candidate_id,
        "synthesis_receipt_id": receipt_id,
        "input_evidence_manifest_sha256": input_digest,
        "improvement_analysis_manifest": analysis,
        "runtime_artifact_binding": runtime_binding,
        "runtime_artifact_set_sha256": runtime_binding["artifact_set_sha256"],
        "not_goal_truth": True,
        "not_authority": True,
        "mutation_performed": False,
    }


def render_selection_synthesis(
    root: Path, source_result: dict[str, Any]
) -> dict[str, Any]:
    """Project and seal one direct derive result's three-lens synthesis."""

    if not isinstance(source_result, dict) or set(source_result) == {"result"}:
        raise ValueError("selection synthesis requires a direct derive result object")
    findings = _analysis_findings(source_result)
    if findings:
        codes = ", ".join(sorted({str(row.get("code")) for row in findings}))
        raise ValueError(f"selection synthesis analysis contract failed: {codes}")
    core = _projection_core(root.expanduser().resolve(strict=True), source_result)
    synthesis_id = "selection-synthesis-" + canonical_sha256(core)[:24]
    body = {**core, "selection_synthesis_id": synthesis_id}
    return {**body, "selection_synthesis_sha256": canonical_sha256(body)}


def validate_selection_synthesis(root: Path, value: Any) -> dict[str, Any]:
    """Validate a closed synthesis projection and all three embedded lenses."""

    if not isinstance(value, dict) or set(value) != SYNTHESIS_KEYS:
        raise ValueError("selection synthesis requires its exact closed fields")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != "derive_selection_synthesis"
        or value.get("derive_contract_version") != 2
        or value.get("not_goal_truth") is not True
        or value.get("not_authority") is not True
        or value.get("mutation_performed") is not False
    ):
        raise ValueError("selection synthesis fixed fields are invalid")
    source = {
        "derive_contract_version": 2,
        "cycle_id": value.get("cycle_id"),
        "selection_outcome": value.get("selection_outcome"),
        "next_task_id": value.get("selected_task_id"),
        "pack_disposition": value.get("pack_disposition"),
        "selected_candidate_id": value.get("selected_candidate_id"),
        "improvement_analysis_manifest": value.get("improvement_analysis_manifest"),
    }
    findings = _analysis_findings(source)
    if findings:
        codes = ", ".join(sorted({str(row.get("code")) for row in findings}))
        raise ValueError(f"selection synthesis analysis contract failed: {codes}")
    core = _projection_core(root.expanduser().resolve(strict=True), source)
    expected_id = "selection-synthesis-" + canonical_sha256(core)[:24]
    body = {**core, "selection_synthesis_id": expected_id}
    sealed = {**body, "selection_synthesis_sha256": canonical_sha256(body)}
    if value != sealed:
        raise ValueError("selection synthesis integrity check failed")
    return sealed


__all__ = (
    "SYNTHESIS_KEYS",
    "canonical_bytes",
    "canonical_sha256",
    "render_selection_synthesis",
    "validate_selection_synthesis",
)
