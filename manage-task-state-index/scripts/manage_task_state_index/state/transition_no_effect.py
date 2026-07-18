"""Immutable proof that a stale index plan produced no canonical effect."""
from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
from typing import Any

from .transition_plan_contract import (
    canonical_bytes,
    owned_transition_file,
    publish_immutable,
    regular_payload,
    sha256_bytes,
)


NO_EFFECT_KIND = "task_state_transition_no_effect_receipt"
NO_EFFECT_SCHEMA_VERSION = 1


def no_effect_receipt_path(
    root: Path, plan_id: str, *, create_parent: bool = False
) -> Path:
    return owned_transition_file(
        root,
        "transition_no_effect_receipts",
        f"{plan_id}.json",
        create_parent=create_parent,
    )


def build_no_effect_receipt(
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    observation: dict[str, Any],
    *,
    settled_at: str,
) -> dict[str, Any]:
    body = {
        "schema_version": NO_EFFECT_SCHEMA_VERSION,
        "receipt_kind": NO_EFFECT_KIND,
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "settled_at": settled_at,
        "reason": "prestate_changed_without_plan_effect",
        "observation": observation,
    }
    return {
        **body,
        "receipt_content_sha256": sha256_bytes(canonical_bytes(body)),
    }


def _valid_sha256(value: Any, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def validate_no_effect_receipt(
    receipt: dict[str, Any],
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> None:
    required = {
        "schema_version",
        "receipt_kind",
        "plan_id",
        "plan_ref",
        "plan_sha256",
        "plan_file_sha256",
        "settled_at",
        "reason",
        "observation",
        "receipt_content_sha256",
    }
    if set(receipt) != required:
        raise ValueError("Task-state no-effect receipt fields are malformed")
    if (
        receipt["schema_version"] != NO_EFFECT_SCHEMA_VERSION
        or receipt["receipt_kind"] != NO_EFFECT_KIND
        or receipt["plan_id"] != plan["plan_id"]
        or receipt["plan_ref"] != plan_ref
        or receipt["plan_sha256"] != plan["plan_sha256"]
        or receipt["plan_file_sha256"] != plan_file_sha256
        or receipt["reason"] != "prestate_changed_without_plan_effect"
        or not isinstance(receipt["settled_at"], str)
        or not receipt["settled_at"]
    ):
        raise ValueError("Task-state no-effect receipt plan binding mismatch")
    try:
        settled_at = dt.datetime.fromisoformat(
            receipt["settled_at"].replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("Task-state no-effect receipt timestamp is malformed") from exc
    if settled_at.tzinfo is None:
        raise ValueError("Task-state no-effect receipt timestamp needs a timezone")
    observation = receipt["observation"]
    if not isinstance(observation, dict) or set(observation) != {
        "ledger_sha256",
        "markdown_sha256",
        "artifact_sha256",
        "cas_defects",
        "plan_effect_observed",
        "plan_intent_observed",
    }:
        raise ValueError("Task-state no-effect observation is malformed")
    artifacts = observation["artifact_sha256"]
    if (
        not _valid_sha256(observation["ledger_sha256"])
        or not _valid_sha256(observation["markdown_sha256"], nullable=True)
        or not isinstance(artifacts, list)
        or any(
            not isinstance(item, dict)
            or set(item) != {"path", "sha256"}
            or not isinstance(item["path"], str)
            or not item["path"]
            or not _valid_sha256(item["sha256"], nullable=True)
            for item in artifacts
        )
        or not isinstance(observation["cas_defects"], list)
        or not observation["cas_defects"]
        or any(not isinstance(item, str) or not item for item in observation["cas_defects"])
        or observation["plan_effect_observed"] is not False
        or observation["plan_intent_observed"] is not False
    ):
        raise ValueError("Task-state no-effect observation values are malformed")
    expected_paths = [anchor["path"] for anchor in plan["artifact_anchors"]]
    if [item["path"] for item in artifacts] != expected_paths:
        raise ValueError("Task-state no-effect artifact observations do not bind the plan")
    expected_defects: list[str] = []
    if observation["ledger_sha256"] != plan["ledger"]["before_sha256"]:
        expected_defects.append("ledger_sha256_mismatch")
    if observation["markdown_sha256"] != plan["markdown"]["before_sha256"]:
        expected_defects.append("markdown_sha256_mismatch")
    for artifact, anchor in zip(artifacts, plan["artifact_anchors"], strict=True):
        if artifact["sha256"] != anchor["expected_sha256"]:
            expected_defects.append(f"artifact_sha256_mismatch:{anchor['path']}")
    if observation["cas_defects"] != expected_defects or not expected_defects:
        raise ValueError("Task-state no-effect CAS proof does not match the observation")
    body = {
        key: value for key, value in receipt.items() if key != "receipt_content_sha256"
    }
    if receipt["receipt_content_sha256"] != sha256_bytes(canonical_bytes(body)):
        raise ValueError("Task-state no-effect receipt digest mismatch")


def load_no_effect_receipt(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> tuple[str, dict[str, Any] | None, str | None]:
    path = no_effect_receipt_path(root, str(plan["plan_id"]))
    if not path.exists() and not path.is_symlink():
        return "missing", None, None
    payload = regular_payload(path)
    try:
        receipt = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid task-state no-effect receipt") from exc
    if not isinstance(receipt, dict):
        raise ValueError("Task-state no-effect receipt must be a JSON object")
    validate_no_effect_receipt(receipt, plan, plan_ref, plan_file_sha256)
    if payload != canonical_bytes(receipt) + b"\n":
        raise ValueError("Task-state no-effect receipt file bytes are not canonical")
    return "current", receipt, sha256_bytes(payload)


def publish_no_effect_receipt(root: Path, receipt: dict[str, Any]) -> tuple[Path, bool]:
    path = no_effect_receipt_path(
        root, str(receipt["plan_id"]), create_parent=True
    )
    created = publish_immutable(path, canonical_bytes(receipt) + b"\n")
    return path, created


__all__ = [
    "build_no_effect_receipt",
    "load_no_effect_receipt",
    "no_effect_receipt_path",
    "publish_no_effect_receipt",
    "validate_no_effect_receipt",
]
