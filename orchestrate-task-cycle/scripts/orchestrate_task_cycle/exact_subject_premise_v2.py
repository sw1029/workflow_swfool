"""Seal artifact-verified exact-subject premise receipts without paths or bodies."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any


CONTRACT_VERSION = 2
ATTESTATION_VERSION = 1
ARTIFACT_VALIDATOR_POLICY_ID = "exact-subject-artifact-verifier"
ARTIFACT_VALIDATOR_POLICY_VERSION = "1"
MAX_CANONICAL_BYTES = 128 * 1024

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ATTESTATION_KEYS = {
    "schema_version",
    "artifact_kind",
    "validator_policy",
    "workspace_file_validation",
    "current_binding_artifact",
    "current_subject",
    "freshness_baseline_subject",
    "source_subject",
    "invariant_evidence",
    "evidence_receipts",
    "source_body_persisted",
    "source_path_persisted",
}
_POLICY_KEYS = {"policy_id", "policy_version"}
_WORKSPACE_KEYS = {"status", "workspace_local", "regular_non_symlink"}
_BINDING_ARTIFACT_KEYS = {
    "artifact_kind",
    "artifact_id",
    "digest_mode",
    "binding_sha256",
    "raw_sha256",
}
_SUBJECT_KEYS = {"subject_id", "revision_id", "raw_sha256"}
_SOURCE_SUBJECT_KEYS = {"source_identity", "revision_id", "raw_sha256"}
_INVARIANT_KEYS = {"evidence_id", "raw_sha256"}
_EVIDENCE_RECEIPT_KEYS = {"role", "receipt_id", "raw_sha256"}
_RECEIPT_KEYS = {
    "schema_version",
    "artifact_kind",
    "status",
    "legacy_receipt",
    "legacy_receipt_sha256",
    "artifact_verification",
    "artifact_verification_sha256",
    "source_body_persisted",
    "source_path_persisted",
    "receipt_id",
    "receipt_sha256",
}


def _canonical_bytes(value: object) -> bytes:
    try:
        body = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "artifact-verified premise values must be canonical JSON"
        ) from exc
    if len(body) > MAX_CANONICAL_BYTES:
        raise ValueError(
            f"artifact-verified premise exceeds {MAX_CANONICAL_BYTES} canonical bytes"
        )
    return body


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _closed(value: object, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{label} requires exact fields {sorted(keys)}")
    return {str(key): child for key, child in value.items()}


def _opaque(value: object, label: str) -> str:
    if not isinstance(value, str) or _OPAQUE_ID.fullmatch(value) is None:
        raise ValueError(f"{label} must be a bounded opaque ID")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _validated_legacy_receipt(value: object) -> dict[str, Any]:
    # Lazy import keeps the v2 artifact layer independent of v1 import order.
    from .exact_subject_premise import validate_exact_subject_premise_receipt

    receipt = validate_exact_subject_premise_receipt(value)
    if receipt.get("status") != "consumed":
        raise ValueError("artifact verification requires a consumed v1 premise receipt")
    return copy.deepcopy(receipt)


def _subject(value: object, label: str) -> dict[str, str]:
    row = _closed(value, _SUBJECT_KEYS, label)
    return {
        "subject_id": _opaque(row["subject_id"], f"{label}.subject_id"),
        "revision_id": _opaque(row["revision_id"], f"{label}.revision_id"),
        "raw_sha256": _digest(row["raw_sha256"], f"{label}.raw_sha256"),
    }


def _source_subject(value: object) -> dict[str, str]:
    row = _closed(value, _SOURCE_SUBJECT_KEYS, "source_subject")
    return {
        "source_identity": _opaque(
            row["source_identity"], "source_subject.source_identity"
        ),
        "revision_id": _opaque(row["revision_id"], "source_subject.revision_id"),
        "raw_sha256": _digest(row["raw_sha256"], "source_subject.raw_sha256"),
    }


def _binding_artifact(value: object) -> dict[str, str]:
    row = _closed(value, _BINDING_ARTIFACT_KEYS, "current_binding_artifact")
    kind = str(row["artifact_kind"])
    if kind not in {"terminal_task", "selection_baseline"}:
        raise ValueError("current binding artifact kind is unsupported")
    digest_mode = str(row["digest_mode"])
    if digest_mode not in {"raw_sha256", "canonical_json_sha256"}:
        raise ValueError("current binding digest mode is unsupported")
    return {
        "artifact_kind": kind,
        "artifact_id": _opaque(
            row["artifact_id"], "current_binding_artifact.artifact_id"
        ),
        "digest_mode": digest_mode,
        "binding_sha256": _digest(
            row["binding_sha256"], "current_binding_artifact.binding_sha256"
        ),
        "raw_sha256": _digest(row["raw_sha256"], "current_binding_artifact.raw_sha256"),
    }


def _invariant(value: object) -> dict[str, str]:
    row = _closed(value, _INVARIANT_KEYS, "invariant_evidence")
    return {
        "evidence_id": _opaque(row["evidence_id"], "invariant_evidence.evidence_id"),
        "raw_sha256": _digest(row["raw_sha256"], "invariant_evidence.raw_sha256"),
    }


def _evidence_receipts(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("evidence_receipts must be a list")
    result: list[dict[str, str]] = []
    for index, item in enumerate(value):
        row = _closed(item, _EVIDENCE_RECEIPT_KEYS, f"evidence_receipts[{index}]")
        result.append(
            {
                "role": _opaque(row["role"], f"evidence_receipts[{index}].role"),
                "receipt_id": _opaque(
                    row["receipt_id"], f"evidence_receipts[{index}].receipt_id"
                ),
                "raw_sha256": _digest(
                    row["raw_sha256"], f"evidence_receipts[{index}].raw_sha256"
                ),
            }
        )
    return result


def _expected_binding(accepted: Mapping[str, Any]) -> dict[str, str]:
    binding = accepted["binding"]
    kind = str(binding["binding_kind"])
    if kind == "terminal_task":
        digest = str(binding["terminal_task_sha256"])
        return {
            "artifact_kind": kind,
            "artifact_id": "terminal-task",
            "digest_mode": "raw_sha256",
            "binding_sha256": digest,
            "raw_sha256": digest,
        }
    return {
        "artifact_kind": kind,
        "artifact_id": str(binding["selection_baseline_id"]),
        "digest_mode": "canonical_json_sha256",
        "binding_sha256": str(binding["selection_baseline_sha256"]),
    }


def _expected_subject(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "subject_id": str(value["subject_id"]),
        "revision_id": str(value["revision_id"]),
        "raw_sha256": str(value["content_sha256"]),
    }


def _expected_evidence(
    evidence: Mapping[str, Any],
) -> tuple[list[dict[str, str]], dict[str, str] | None]:
    if evidence["mode"] == "producer_verifier_replay":
        return (
            [
                {
                    "role": "producer",
                    "receipt_id": str(evidence["producer_receipt_id"]),
                    "raw_sha256": str(evidence["producer_receipt_sha256"]),
                },
                {
                    "role": "verifier",
                    "receipt_id": str(evidence["verifier_receipt_id"]),
                    "raw_sha256": str(evidence["verifier_receipt_sha256"]),
                },
                {
                    "role": "replay",
                    "receipt_id": str(evidence["replay_receipt_id"]),
                    "raw_sha256": str(evidence["replay_receipt_sha256"]),
                },
            ],
            None,
        )
    required = ("source_receipt_sha256", "current_body_receipt_sha256")
    if any(key not in evidence for key in required):
        raise ValueError(
            "artifact-verified source separation requires source/current receipt SHA-256"
        )
    return (
        [
            {
                "role": "source",
                "receipt_id": str(evidence["source_receipt_id"]),
                "raw_sha256": str(evidence["source_receipt_sha256"]),
            },
            {
                "role": "current_body",
                "receipt_id": str(evidence["current_body_receipt_id"]),
                "raw_sha256": str(evidence["current_body_receipt_sha256"]),
            },
            {
                "role": "comparison",
                "receipt_id": str(evidence["comparison_receipt_id"]),
                "raw_sha256": str(evidence["comparison_receipt_sha256"]),
            },
        ],
        {
            "source_identity": str(evidence["source_channel_id"]),
            "revision_id": str(evidence["source_revision_id"]),
            "raw_sha256": str(evidence["source_content_sha256"]),
        },
    )


def _normalized_attestation(
    value: object, legacy_receipt: Mapping[str, Any]
) -> dict[str, Any]:
    row = _closed(value, _ATTESTATION_KEYS, "artifact_verification")
    if (
        row["schema_version"] != ATTESTATION_VERSION
        or row["artifact_kind"] != "exact_subject_premise_artifact_verification"
    ):
        raise ValueError("artifact verification schema or kind is invalid")
    policy = _closed(row["validator_policy"], _POLICY_KEYS, "validator_policy")
    if policy != {
        "policy_id": ARTIFACT_VALIDATOR_POLICY_ID,
        "policy_version": ARTIFACT_VALIDATOR_POLICY_VERSION,
    }:
        raise ValueError("artifact validator policy binding is unsupported")
    workspace = _closed(
        row["workspace_file_validation"],
        _WORKSPACE_KEYS,
        "workspace_file_validation",
    )
    if workspace != {
        "status": "verified",
        "workspace_local": True,
        "regular_non_symlink": True,
    }:
        raise ValueError("workspace-local regular-file validation is not verified")
    if (
        row["source_body_persisted"] is not False
        or row["source_path_persisted"] is not False
    ):
        raise ValueError("artifact verification retained a source path or body")

    accepted = legacy_receipt["accepted_premise"]
    binding_artifact = _binding_artifact(row["current_binding_artifact"])
    expected_binding = _expected_binding(accepted)
    if any(
        binding_artifact[key] != expected for key, expected in expected_binding.items()
    ):
        raise ValueError("current binding artifact differs from the v1 premise receipt")

    current_subject = _subject(row["current_subject"], "current_subject")
    if current_subject != _expected_subject(accepted["subject"]):
        raise ValueError("current subject artifact differs from the v1 premise receipt")

    baseline = accepted["freshness"]["baseline_subject"]
    baseline_subject = (
        None
        if row["freshness_baseline_subject"] is None
        else _subject(row["freshness_baseline_subject"], "freshness_baseline_subject")
    )
    expected_baseline = None if baseline is None else _expected_subject(baseline)
    if baseline_subject != expected_baseline:
        raise ValueError(
            "freshness baseline artifact differs from the v1 premise receipt"
        )

    invariant = _invariant(row["invariant_evidence"])
    expected_invariant = {
        "evidence_id": str(accepted["first_failing_invariant"]["evidence_id"]),
        "raw_sha256": str(accepted["first_failing_invariant"]["evidence_sha256"]),
    }
    if invariant != expected_invariant:
        raise ValueError("invariant artifact differs from the v1 premise receipt")

    receipts = _evidence_receipts(row["evidence_receipts"])
    expected_receipts, expected_source = _expected_evidence(accepted["evidence"])
    if receipts != expected_receipts:
        raise ValueError(
            "evidence receipt artifacts differ from the v1 premise receipt"
        )
    source = (
        None
        if row["source_subject"] is None
        else _source_subject(row["source_subject"])
    )
    if source != expected_source:
        raise ValueError("source subject artifact differs from the v1 premise receipt")

    return {
        "schema_version": ATTESTATION_VERSION,
        "artifact_kind": "exact_subject_premise_artifact_verification",
        "validator_policy": dict(policy),
        "workspace_file_validation": dict(workspace),
        "current_binding_artifact": binding_artifact,
        "current_subject": current_subject,
        "freshness_baseline_subject": baseline_subject,
        "source_subject": source,
        "invariant_evidence": invariant,
        "evidence_receipts": receipts,
        "source_body_persisted": False,
        "source_path_persisted": False,
    }


def seal_artifact_verified_receipt(
    legacy_receipt: object, artifact_verification: object
) -> dict[str, Any]:
    """Seal a consumed v1 receipt and its closed path-free artifact attestation."""

    legacy = _validated_legacy_receipt(legacy_receipt)
    attestation = _normalized_attestation(artifact_verification, legacy)
    body: dict[str, Any] = {
        "schema_version": CONTRACT_VERSION,
        "artifact_kind": "artifact_verified_exact_subject_premise_receipt",
        "status": "consumed",
        "legacy_receipt": legacy,
        "legacy_receipt_sha256": str(legacy["receipt_sha256"]),
        "artifact_verification": attestation,
        "artifact_verification_sha256": _sha256(attestation),
        "source_body_persisted": False,
        "source_path_persisted": False,
    }
    body["receipt_id"] = "exact-premise-v2-" + _sha256(body)[:32]
    body["receipt_sha256"] = _sha256(body)
    return body


def validate_artifact_verified_exact_subject_premise_receipt(
    value: object,
) -> dict[str, Any]:
    """Validate a sealed v2 receipt and revalidate its embedded v1 receipt."""

    row = _closed(value, _RECEIPT_KEYS, "artifact-verified premise receipt")
    if (
        row["schema_version"] != CONTRACT_VERSION
        or row["artifact_kind"] != "artifact_verified_exact_subject_premise_receipt"
        or row["status"] != "consumed"
    ):
        raise ValueError("artifact-verified premise receipt schema is invalid")
    if (
        row["source_body_persisted"] is not False
        or row["source_path_persisted"] is not False
    ):
        raise ValueError("artifact-verified premise receipt retained source material")
    legacy = _validated_legacy_receipt(row["legacy_receipt"])
    if row["legacy_receipt_sha256"] != legacy["receipt_sha256"]:
        raise ValueError("artifact-verified premise legacy binding is invalid")
    attestation = _normalized_attestation(row["artifact_verification"], legacy)
    if row["artifact_verification_sha256"] != _sha256(attestation):
        raise ValueError("artifact verification digest is invalid")
    without_hash = {key: child for key, child in row.items() if key != "receipt_sha256"}
    without_identity = {
        key: child for key, child in without_hash.items() if key != "receipt_id"
    }
    expected_id = "exact-premise-v2-" + _sha256(without_identity)[:32]
    if row["receipt_id"] != expected_id or row["receipt_sha256"] != _sha256(
        without_hash
    ):
        raise ValueError("artifact-verified premise receipt integrity check failed")
    return copy.deepcopy(row)


__all__ = (
    "ARTIFACT_VALIDATOR_POLICY_ID",
    "ARTIFACT_VALIDATOR_POLICY_VERSION",
    "ATTESTATION_VERSION",
    "CONTRACT_VERSION",
    "seal_artifact_verified_receipt",
    "validate_artifact_verified_exact_subject_premise_receipt",
)
