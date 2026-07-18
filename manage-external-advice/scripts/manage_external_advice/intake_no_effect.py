"""Closed durable no-effect settlement for immutable advice intake plans."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .intake_plan_contract import (
    RESULT_SCHEMA_VERSION,
    canonical_bytes,
    canonical_destination_path,
    canonical_intake_artifact_path,
    sha256_bytes,
    workspace_path,
)
from .storage import publish_immutable
from .stable_store import read_regular


NO_EFFECT_KIND = "external_advice_intake_no_effect_receipt"
NO_EFFECT_REASONS = {
    "duplicate_exact_raw_source",
    "markdown_cas_stale",
    "normalized_destination_conflict",
    "raw_destination_conflict",
    "registry_cas_stale",
    "source_changed",
    "source_missing",
}
_TOP_LEVEL_KEYS = {
    "advice_id",
    "destination_observations",
    "duplicate_proof",
    "markdown_observation",
    "plan_event_observed",
    "plan_owned_publication_observed",
    "plan_file_sha256",
    "plan_id",
    "plan_intent_observed",
    "plan_ref",
    "plan_sha256",
    "reason_codes",
    "receipt_content_sha256",
    "receipt_kind",
    "registry_observation",
    "schema_version",
    "settlement_kind",
    "source_observation",
}


def _file_observation(
    root: Path, path: Path, expected: str, *, absent: str
) -> dict[str, Any]:
    payload = read_regular(root, path, missing=None, label="Advice intake artifact")
    if payload is None:
        return {"state": absent, "sha256": None}
    digest = sha256_bytes(payload)
    return {"state": "exact" if digest == expected else "conflict", "sha256": digest}


def observe_prestate(
    root: Path,
    plan: dict[str, Any],
    registry: bytes,
    markdown: bytes,
) -> dict[str, Any]:
    """Capture bounded, body-free pre-canonical observations."""

    try:
        source = workspace_path(root, plan["raw"]["source_ref"])
        source_observation = _file_observation(
            root, source, plan["raw"]["sha256"], absent="missing"
        )
        if source_observation["state"] == "conflict":
            source_observation["state"] = "changed"
    except SystemExit:
        source_observation = {"state": "unsafe", "sha256": None}
    destinations: dict[str, dict[str, Any]] = {}
    for key in ("raw", "normalized"):
        try:
            destination = canonical_destination_path(
                root, plan[key]["path"], kind=key
            )
            destinations[key] = {
                "path": plan[key]["path"],
                **_file_observation(
                    root, destination, plan[key]["sha256"], absent="absent"
                ),
            }
        except SystemExit:
            destinations[key] = {
                "path": plan[key]["path"],
                "state": "unsafe",
                "sha256": None,
            }
    plan_owned_publication = any(
        destinations[key]["state"] == "exact" for key in ("raw", "normalized")
    )
    return {
        "registry_observation": {
            "path": plan["registry"]["path"],
            "sha256": sha256_bytes(registry),
            "size": len(registry),
        },
        "markdown_observation": {
            "path": plan["markdown"]["path"],
            "sha256": sha256_bytes(markdown) if markdown else None,
        },
        "source_observation": {
            "ref": plan["raw"]["source_ref"],
            **source_observation,
        },
        "destination_observations": destinations,
        "plan_owned_publication_observed": plan_owned_publication,
    }


def stale_reason_codes(plan: dict[str, Any], observation: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if observation["registry_observation"]["sha256"] != plan["registry"]["before_sha256"]:
        reasons.append("registry_cas_stale")
    if observation["markdown_observation"]["sha256"] != plan["markdown"]["before_sha256"]:
        reasons.append("markdown_cas_stale")
    source_state = observation["source_observation"]["state"]
    if source_state in {"missing", "changed"}:
        reasons.append(f"source_{source_state}")
    for key in ("raw", "normalized"):
        if observation["destination_observations"][key]["state"] == "conflict":
            reasons.append(f"{key}_destination_conflict")
    return sorted(reasons)


def _receipt_body(
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    observation: dict[str, Any],
    reasons: list[str],
    proof: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "receipt_kind": NO_EFFECT_KIND,
        "settlement_kind": (
            "exact_duplicate" if proof is not None else "precanonical_stale"
        ),
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "advice_id": plan["advice_id"],
        "reason_codes": reasons,
        "plan_event_observed": False,
        "plan_intent_observed": False,
        "duplicate_proof": proof,
        **observation,
    }


def no_effect_receipt(
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    observation: dict[str, Any],
    reasons: list[str],
    proof: dict[str, Any] | None,
) -> dict[str, Any]:
    body = _receipt_body(
        plan, plan_ref, plan_file_sha256, observation, reasons, proof
    )
    return {**body, "receipt_content_sha256": sha256_bytes(canonical_bytes(body))}


def _valid_digest(value: Any, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_observation(receipt: dict[str, Any], plan: dict[str, Any]) -> bool:
    registry = receipt.get("registry_observation")
    markdown = receipt.get("markdown_observation")
    source = receipt.get("source_observation")
    destinations = receipt.get("destination_observations")
    if (
        not isinstance(registry, dict)
        or set(registry) != {"path", "sha256", "size"}
        or registry["path"] != plan["registry"]["path"]
        or not _valid_digest(registry["sha256"])
        or not isinstance(registry["size"], int)
        or isinstance(registry["size"], bool)
        or registry["size"] < 0
    ):
        return False
    if (
        not isinstance(markdown, dict)
        or set(markdown) != {"path", "sha256"}
        or markdown["path"] != plan["markdown"]["path"]
        or not _valid_digest(markdown["sha256"], nullable=True)
    ):
        return False
    if (
        not isinstance(source, dict)
        or set(source) != {"ref", "sha256", "state"}
        or source["ref"] != plan["raw"]["source_ref"]
        or source["state"] not in {"exact", "missing", "changed"}
        or not _valid_digest(source["sha256"], nullable=True)
        or (source["state"] == "exact" and source["sha256"] != plan["raw"]["sha256"])
        or (source["state"] == "missing" and source["sha256"] is not None)
        or (
            source["state"] == "changed"
            and (source["sha256"] is None or source["sha256"] == plan["raw"]["sha256"])
        )
    ):
        return False
    if not isinstance(destinations, dict) or set(destinations) != {"raw", "normalized"}:
        return False
    for key, value in destinations.items():
        if (
            not isinstance(value, dict)
            or set(value) != {"path", "sha256", "state"}
            or value["path"] != plan[key]["path"]
            or not _valid_digest(value["sha256"], nullable=True)
        ):
            return False
        if value["state"] not in {"absent", "exact", "conflict"}:
            return False
        if value["state"] == "absent" and value["sha256"] is not None:
            return False
        if value["state"] == "exact" and value["sha256"] != plan[key]["sha256"]:
            return False
        if value["state"] == "conflict" and (
            value["sha256"] is None or value["sha256"] == plan[key]["sha256"]
        ):
            return False
    if receipt.get("plan_owned_publication_observed") is not any(
        destinations[key]["state"] == "exact" for key in ("raw", "normalized")
    ):
        return False
    return True


def _valid_duplicate_proof(proof: Any, plan: dict[str, Any]) -> bool:
    expected_keys = {
        "advice_id", "event_index", "event_sha256", "match_basis",
        "raw_sha256", "raw_source_path",
    }
    if not isinstance(proof, dict) or set(proof) != expected_keys:
        return False
    if (
        proof["raw_sha256"] != plan["raw"]["sha256"]
        or proof["raw_source_path"] == plan["raw"]["path"]
        or not isinstance(proof["raw_source_path"], str)
    ):
        return False
    if proof["match_basis"] == "raw_file_sha256":
        return (
            proof["advice_id"] is None
            and proof["event_index"] is None
            and proof["event_sha256"] is None
        )
    return (
        proof["match_basis"] == "registry_raw_sha256"
        and isinstance(proof["advice_id"], str)
        and bool(proof["advice_id"])
        and isinstance(proof["event_index"], int)
        and not isinstance(proof["event_index"], bool)
        and proof["event_index"] >= 0
        and _valid_digest(proof["event_sha256"])
    )


def validate_no_effect_receipt(
    receipt: dict[str, Any],
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> None:
    if set(receipt) != _TOP_LEVEL_KEYS or not _valid_observation(receipt, plan):
        raise SystemExit("Invalid external-advice no-effect receipt schema")
    supplied = receipt["receipt_content_sha256"]
    body = {key: value for key, value in receipt.items() if key != "receipt_content_sha256"}
    expected_binding = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "receipt_kind": NO_EFFECT_KIND,
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "advice_id": plan["advice_id"],
        "plan_event_observed": False,
        "plan_intent_observed": False,
        "plan_owned_publication_observed": False,
    }
    if any(receipt.get(key) != value for key, value in expected_binding.items()):
        raise SystemExit("External-advice no-effect receipt plan binding mismatch")
    reasons = receipt.get("reason_codes")
    proof = receipt.get("duplicate_proof")
    settlement = receipt.get("settlement_kind")
    if (
        supplied != sha256_bytes(canonical_bytes(body))
        or not isinstance(reasons, list)
        or not reasons
        or reasons != sorted(set(reasons))
        or not set(reasons) <= NO_EFFECT_REASONS
        or (settlement == "exact_duplicate") != (proof is not None)
        or settlement not in {"exact_duplicate", "precanonical_stale"}
    ):
        raise SystemExit("External-advice no-effect receipt integrity mismatch")
    if settlement == "exact_duplicate" and reasons != ["duplicate_exact_raw_source"]:
        raise SystemExit("External-advice duplicate settlement reason mismatch")
    if settlement == "exact_duplicate" and not _valid_duplicate_proof(proof, plan):
        raise SystemExit("External-advice duplicate settlement proof mismatch")
    if settlement == "precanonical_stale" and reasons != stale_reason_codes(plan, receipt):
        raise SystemExit("External-advice stale settlement proof mismatch")


def load_no_effect_receipt(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
) -> tuple[str, dict[str, Any] | None, str | None]:
    path = canonical_intake_artifact_path(root, plan["plan_id"], "receipt")
    payload = read_regular(
        root, path, missing=None, label="External-advice no-effect receipt"
    )
    if payload is None:
        return "missing", None, None
    digest = sha256_bytes(payload)
    try:
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict) or value.get("receipt_kind") != NO_EFFECT_KIND:
            return "other", None, digest
        validate_no_effect_receipt(value, plan, plan_ref, plan_file_sha256)
        if payload != canonical_bytes(value) + b"\n":
            raise SystemExit("External-advice no-effect receipt bytes are not canonical")
    except (UnicodeDecodeError, json.JSONDecodeError, SystemExit):
        return "conflict", None, digest
    return "current", value, digest


def publish_no_effect_receipt(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    receipt: dict[str, Any],
) -> tuple[str, str]:
    validate_no_effect_receipt(receipt, plan, plan_ref, plan_file_sha256)
    path = canonical_intake_artifact_path(
        root, plan["plan_id"], "receipt", ensure_parent=True
    )
    payload = canonical_bytes(receipt) + b"\n"
    publish_immutable(root, path, payload)
    return path.relative_to(root).as_posix(), sha256_bytes(payload)


def no_effect_result(
    plan: dict[str, Any],
    plan_ref: str,
    receipt: dict[str, Any],
    receipt_ref: str,
    receipt_file_sha256: str,
    *,
    replay: bool,
) -> dict[str, Any]:
    return {
        "result_kind": "external_advice_intake_apply_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "settled_no_effect",
        "apply_status": "settled_no_effect",
        "receipt_kind": receipt["receipt_kind"],
        "settlement_kind": receipt["settlement_kind"],
        "reason_codes": receipt["reason_codes"],
        "advice_id": plan["advice_id"],
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": receipt["plan_file_sha256"],
        "receipt_ref": receipt_ref,
        "receipt_content_sha256": receipt["receipt_content_sha256"],
        "receipt_file_sha256": receipt_file_sha256,
        "execution_result_binding": {
            "ref": receipt_ref,
            "sha256": receipt_file_sha256,
        },
        "plan_effect_observed": False,
        "plan_intent_observed": False,
        "plan_owned_publication_observed": False,
        "no_effect_verified": True,
        "idempotent_replay": replay,
        "mutation_performed": not replay,
    }
