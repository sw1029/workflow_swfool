"""Reopen and validate immutable legacy-retirement artifact chains."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..authority_artifacts import validate_authority_use_receipt_settlement
from .legacy_retirement_contract import (
    LEGACY_ELIGIBILITY_CONTRACT_VERSION,
    normalize_plan,
    task_fields,
)
from .legacy_retirement_schema import (
    ACTIVATION_KEYS,
    COMPLETION_KEYS,
    ELIGIBILITY_KEYS,
    NON_CLAIMS,
    OVERLAY_KEYS,
    PREPARE_KEYS,
    SOURCE_OVERLAY_KEYS,
    binding,
    closed,
    transaction_id,
)
from .legacy_retirement_store import (
    artifact_ref,
    canonical_sha256,
    read_bound_bytes,
    read_bound_json,
    safe_regular_file,
)
from .state_machine import derived_operational_status
from .storage import canonical_pack_sha256
from .validation import validate_pack


def load_prepare(
    root: Path, artifact_binding: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    tx_id = Path(artifact_binding["ref"]).stem
    _, prepare = read_bound_json(
        root,
        artifact_binding,
        "legacy retirement prepare",
        expected_prefix=".task/task_pack_retirement/prepares",
        expected_ref=artifact_ref("prepares", tx_id),
    )
    closed(prepare, PREPARE_KEYS, "legacy retirement prepare")
    plan = normalize_plan(prepare.get("plan"))
    if (
        prepare.get("schema_version") != 1
        or prepare.get("artifact_kind") != "legacy_task_pack_retirement_prepare"
        or prepare.get("transaction_id") != tx_id
        or tx_id != transaction_id(plan)
    ):
        raise ValueError("legacy retirement prepare identity is invalid")
    binding(prepare.get("source_snapshot"), "prepare.source_snapshot")
    binding(prepare.get("overlay"), "prepare.overlay")
    return prepare, plan


def validate_overlay_source(
    root: Path, overlay: dict[str, Any]
) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    source = closed(
        overlay.get("source_pack"), SOURCE_OVERLAY_KEYS, "overlay.source_pack"
    )
    expected_path = root / str(source.get("ref") or "")
    safe_path = read_bound_bytes(
        root,
        {"ref": source.get("ref"), "sha256": source.get("file_sha256")},
        "retired source pack",
    )[0]
    if safe_path != expected_path or safe_path.parent != root / ".task" / "task_pack":
        raise ValueError("retired source pack is not a top-level canonical pack")
    try:
        pack = json.loads(safe_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("retired source pack is not valid JSON") from exc
    if not isinstance(pack, dict):
        raise ValueError("retired source pack must remain a JSON object")
    if (
        pack.get("pack_id") != source.get("pack_id")
        or pack.get("status") != source.get("declared_status")
        or canonical_pack_sha256(pack) != source.get("canonical_pack_sha256")
    ):
        raise ValueError("retired source pack identity or canonical state drifted")
    _, snapshot = read_bound_bytes(
        root,
        {"ref": source.get("snapshot_ref"), "sha256": source.get("snapshot_sha256")},
        "legacy source snapshot",
        expected_prefix=".task/task_pack_retirement/snapshots",
    )
    if snapshot != safe_path.read_bytes():
        raise ValueError("legacy source snapshot no longer equals the raw pack bytes")
    current_task = safe_regular_file(
        root, "task.md", "current task", expected_ref="task.md"
    )
    current_pack = task_fields(current_task.read_bytes())["task_pack"]
    bound_names = {
        str(source.get("ref") or ""),
        str(source.get("pack_id") or ""),
        Path(str(source.get("ref") or "")).name,
        Path(str(source.get("ref") or "")).stem,
    }
    if current_pack.lower() != "none" and current_pack in bound_names:
        raise ValueError("current task is bound to the retired legacy pack")
    blocking = [
        finding
        for finding in validate_pack(pack, safe_path)
        if finding.get("severity") == "block"
    ]
    eligibility = closed(
        overlay.get("eligibility"), ELIGIBILITY_KEYS, "overlay.eligibility"
    )
    codes = sorted({str(row.get("code") or "") for row in blocking})
    if (
        not blocking
        or eligibility.get("contract_version") != LEGACY_ELIGIBILITY_CONTRACT_VERSION
        or eligibility.get("blocking_finding_codes") != codes
        or eligibility.get("blocking_finding_fingerprint") != canonical_sha256(blocking)
        or eligibility.get("raw_contract_status") != "block"
        or eligibility.get("derived_operational_status")
        != derived_operational_status(pack)
        or eligibility.get("current_task_bound") is not False
    ):
        raise ValueError(
            "legacy retirement eligibility no longer matches raw diagnostics"
        )
    return safe_path, pack, blocking


def load_overlay(root: Path, artifact_binding: dict[str, str]) -> dict[str, Any]:
    retirement_id = Path(artifact_binding["ref"]).stem
    _, overlay = read_bound_json(
        root,
        artifact_binding,
        "legacy retirement overlay",
        expected_prefix=".task/task_pack_retirement/overlays",
        expected_ref=artifact_ref("overlays", retirement_id),
    )
    closed(overlay, OVERLAY_KEYS, "legacy retirement overlay")
    core = {key: value for key, value in overlay.items() if key != "retirement_id"}
    if (
        overlay.get("schema_version") != 1
        or overlay.get("artifact_kind") != "legacy_task_pack_retirement_overlay"
        or overlay.get("disposition") != "retired_legacy_closed"
        or overlay.get("retirement_id") != retirement_id
        or retirement_id != "lgr-" + canonical_sha256(core)[:32]
        or overlay.get("non_claims") != NON_CLAIMS
    ):
        raise ValueError("legacy retirement overlay identity or non-claims are invalid")
    validate_overlay_source(root, overlay)
    return overlay


def validate_completion_binding(
    root: Path, artifact_binding: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    tx_id = Path(artifact_binding["ref"]).stem
    _, completion = read_bound_json(
        root,
        artifact_binding,
        "legacy retirement completion",
        expected_prefix=".task/task_pack_retirement/completions",
        expected_ref=artifact_ref("completions", tx_id),
    )
    closed(completion, COMPLETION_KEYS, "legacy retirement completion")
    if (
        completion.get("schema_version") != 1
        or completion.get("artifact_kind") != "legacy_task_pack_retirement_completion"
        or completion.get("transaction_id") != tx_id
        or completion.get("status") != "committed"
    ):
        raise ValueError("legacy retirement completion identity is invalid")
    prepare_binding = binding(completion.get("prepare"), "completion.prepare")
    prepare, plan = load_prepare(root, prepare_binding)
    if tx_id != prepare.get("transaction_id"):
        raise ValueError("completion and prepare transaction identities differ")
    overlay_binding = binding(completion.get("overlay"), "completion.overlay")
    snapshot_binding = binding(
        completion.get("source_snapshot"), "completion.source_snapshot"
    )
    if (
        overlay_binding != prepare.get("overlay")
        or snapshot_binding != prepare.get("source_snapshot")
        or completion.get("source_pack")
        != {
            "ref": plan["source_pack"]["ref"],
            "sha256": plan["source_pack"]["file_sha256"],
        }
        or completion.get("completed_at") != plan.get("prepared_at")
    ):
        raise ValueError("completion does not exactly bind its prepared effect")
    overlay = load_overlay(root, overlay_binding)
    authority = overlay.get("authority") or {}
    source = overlay.get("source_pack") or {}
    if (
        overlay.get("transaction") != {"transaction_id": tx_id}
        or source.get("snapshot_ref") != snapshot_binding["ref"]
        or source.get("snapshot_sha256") != snapshot_binding["sha256"]
        or authority.get("packet") != plan["authority_packet"]
        or authority.get("pre_commit") != plan["pre_commit_verification"]
        or authority.get("consume_idempotency_key") != plan["consume_idempotency_key"]
    ):
        raise ValueError("overlay does not exactly bind its plan and completion")
    return completion, overlay, plan


def validate_activation_binding(
    root: Path,
    artifact_binding: dict[str, str],
    *,
    phase: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    activation_id = Path(artifact_binding["ref"]).stem
    _, activation = read_bound_json(
        root,
        artifact_binding,
        "legacy retirement activation",
        expected_prefix=".task/task_pack_retirement/activations",
        expected_ref=artifact_ref("activations", activation_id),
    )
    closed(activation, ACTIVATION_KEYS, "legacy retirement activation")
    core = {key: value for key, value in activation.items() if key != "activation_id"}
    if (
        activation.get("schema_version") != 1
        or activation.get("artifact_kind") != "legacy_task_pack_retirement_activation"
        or activation.get("activation_id") != activation_id
        or activation_id != "lgra-" + canonical_sha256(core)[:32]
    ):
        raise ValueError("legacy retirement activation identity is invalid")
    completion_binding = binding(activation.get("completion"), "activation.completion")
    completion, overlay, plan = validate_completion_binding(root, completion_binding)
    overlay_binding = binding(activation.get("retirement"), "activation.retirement")
    if overlay_binding != completion.get("overlay"):
        raise ValueError("activation retirement does not match the committed overlay")
    use_binding = binding(
        activation.get("authority_use_receipt"), "activation.authority_use_receipt"
    )
    _, packet = read_bound_json(
        root, plan["authority_packet"], "activation authority packet"
    )
    findings = validate_authority_use_receipt_settlement(
        packet,
        use_binding,
        root,
        execution_result=completion_binding,
        idempotency_key=plan["consume_idempotency_key"],
        phase=phase,
    )
    if findings:
        codes = ", ".join(str(row.get("code")) for row in findings)
        raise ValueError(f"authority settlement validation failed: {codes}")
    _, use_receipt = read_bound_json(
        root,
        use_binding,
        "authority use receipt",
        expected_prefix=".task/authorization/use_receipts",
    )
    if activation.get("activated_at") != use_receipt.get("consumed_at"):
        raise ValueError("activation time must equal the immutable consume time")
    return activation, overlay, plan


__all__ = (
    "load_overlay",
    "load_prepare",
    "validate_activation_binding",
    "validate_completion_binding",
    "validate_overlay_source",
)
