"""Mutation commands for prepare/commit and settlement activation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..authority_artifacts import validate_authority_use_receipt_settlement
from .legacy_retirement_build import activation_body, predict_artifacts
from .legacy_retirement_contract import (
    normalize_plan,
    validate_authority_phase,
    validate_target,
)
from .legacy_retirement_store import (
    artifact_ref,
    display_bytes,
    read_bound_json,
    scan_category,
    sha256_bytes,
    write_once,
)
from .legacy_retirement_validation import (
    validate_activation_binding,
    validate_completion_binding,
)
from .packet_io import load_plan
from .storage import pack_mutation_lock


def _blocked(code: str, error: Exception) -> dict[str, Any]:
    return {
        "status": "block",
        "mutation_performed": False,
        "findings": [
            {
                "severity": "block",
                "code": code,
                "message": str(error),
            }
        ],
    }


def _emit(output: dict[str, Any]) -> int:
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 2 if output["status"] == "block" else 0


def _assert_no_conflicting_transaction(
    root: Path, plan: dict[str, Any], transaction_id: str
) -> None:
    source_ref = plan["source_pack"]["ref"]
    for path in scan_category(root, "prepares"):
        value = json.loads(path.read_text(encoding="utf-8"))
        existing = value.get("plan") if isinstance(value, dict) else None
        source = existing.get("source_pack") if isinstance(existing, dict) else None
        if (
            isinstance(source, dict)
            and source.get("ref") == source_ref
            and path.stem != transaction_id
        ):
            raise ValueError(
                "source pack already has a different retirement transaction"
            )


def _write_effect_artifacts(root: Path, predicted: dict[str, Any], target: Any) -> None:
    steps = (
        (
            "snapshots",
            predicted["snapshot_id"],
            target.pack_bytes,
            predicted["snapshot_binding"],
        ),
        (
            "overlays",
            predicted["overlay"]["retirement_id"],
            display_bytes(predicted["overlay"]),
            predicted["overlay_binding"],
        ),
    )
    for category, artifact_id, body, expected in steps:
        if write_once(root, category, artifact_id, body) != expected:
            raise ValueError(f"{category} binding drifted")


def command_retire_legacy(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve(strict=True)
    try:
        plan = normalize_plan(load_plan(args.plan))
        with pack_mutation_lock(root, create=not bool(args.dry_run)):
            target = validate_target(root, plan)
            packet, verification = validate_authority_phase(root, plan)
            predicted = predict_artifacts(plan, target, packet, verification)
            if args.dry_run:
                output = {
                    "status": "dry_run",
                    "mutation_performed": False,
                    "transaction_id": predicted["transaction_id"],
                    "retirement_id": predicted["overlay"]["retirement_id"],
                    "overlay": predicted["overlay_binding"],
                    "execution_result": predicted["completion_binding"],
                    "raw_finding_codes": list(target.finding_codes),
                }
                return _emit(output)
            _assert_no_conflicting_transaction(root, plan, predicted["transaction_id"])
            # PREPARE is durable before the first effect-bearing snapshot/overlay.
            if (
                write_once(
                    root,
                    "prepares",
                    predicted["transaction_id"],
                    display_bytes(predicted["prepare"]),
                )
                != predicted["prepare_binding"]
            ):
                raise ValueError("prepared retirement binding drifted")
            validate_target(root, plan)
            validate_authority_phase(root, plan)
            _write_effect_artifacts(root, predicted, target)
            validate_target(root, plan)
            if (
                write_once(
                    root,
                    "completions",
                    predicted["transaction_id"],
                    display_bytes(predicted["completion"]),
                )
                != predicted["completion_binding"]
            ):
                raise ValueError("completion binding drifted")
            output = {
                "status": "pending_settlement",
                "mutation_performed": True,
                "transaction_id": predicted["transaction_id"],
                "retirement_id": predicted["overlay"]["retirement_id"],
                "overlay": predicted["overlay_binding"],
                "execution_result": predicted["completion_binding"],
                "authority_consume": {
                    "reservation_id": (packet.get("reservation_binding") or {}).get(
                        "reservation_id"
                    ),
                    "idempotency_key": plan["consume_idempotency_key"],
                    "execution_result": predicted["completion_binding"],
                },
                "next_action": "consume_reserved_authority_then_activate",
                "raw_finding_codes": list(target.finding_codes),
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        output = _blocked("legacy_retirement_prepare_invalid", exc)
    return _emit(output)


def command_activate_legacy_retirement(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve(strict=True)
    completion_binding = {
        "ref": str(args.completion_ref),
        "sha256": str(args.completion_sha256),
    }
    use_binding = {
        "ref": str(args.use_receipt_ref),
        "sha256": str(args.use_receipt_sha256),
    }
    try:
        with pack_mutation_lock(root):
            completion, overlay, plan = validate_completion_binding(
                root, completion_binding
            )
            validate_target(root, plan)
            _, use_receipt = read_bound_json(
                root,
                use_binding,
                "authority use receipt",
                expected_prefix=".task/authorization/use_receipts",
            )
            body = activation_body(
                completion["overlay"],
                completion_binding,
                use_binding,
                str(use_receipt.get("consumed_at") or ""),
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
                phase="activation",
            )
            if findings:
                codes = ", ".join(str(row.get("code")) for row in findings)
                raise ValueError(f"authority settlement validation failed: {codes}")
            activation_binding = write_once(
                root,
                "activations",
                body["activation_id"],
                display_bytes(body),
            )
            expected = {
                "ref": artifact_ref("activations", body["activation_id"]),
                "sha256": sha256_bytes(display_bytes(body)),
            }
            if activation_binding != expected:
                raise ValueError("activation binding drifted")
            validate_activation_binding(root, activation_binding, phase="historical")
            output = {
                "status": "active",
                "mutation_performed": True,
                "activation": activation_binding,
                "retirement": completion["overlay"],
                "execution_result": completion_binding,
                "source_pack_ref": (overlay.get("source_pack") or {}).get("ref"),
                "raw_findings_preserved": True,
            }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        output = _blocked("legacy_retirement_activation_invalid", exc)
    return _emit(output)


__all__ = ("command_activate_legacy_retirement", "command_retire_legacy")
