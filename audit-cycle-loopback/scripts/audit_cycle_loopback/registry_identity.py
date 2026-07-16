from __future__ import annotations

import hashlib
import json
from typing import Any

from . import values as _values
from . import vectors as _vectors

def default_high_water() -> dict[str, Any]:
    return {"ever_provider_dispatch": False}

def decision_input_state_fingerprint(values: list[Any], artifact_ref: dict[str, Any]) -> str:
    excluded_receipt_fields = {
        "attempt_identity",
        "decision_input_fingerprint",
        "input_state_fingerprint",
        "probe_evidence_id",
        "probe_evidence_sha256",
    }
    receipt_container_fields = {
        "consumer_context_conformance",
        "adapter_consumer_conformance",
    }

    def decision_input_projection(value: Any) -> Any:
        if isinstance(value, dict):
            projected: dict[str, Any] = {}
            for key, child in sorted(value.items(), key=lambda item: str(item[0])):
                key_text = str(key)
                if key_text in excluded_receipt_fields:
                    continue
                if key_text in receipt_container_fields:
                    required = (
                        sorted(str(item) for item in _vectors.string_list(child.get("required_consumer_ids")))
                        if isinstance(child, dict)
                        else []
                    )
                    projected[key_text] = {"required_consumer_ids": required}
                    continue
                projected[key_text] = decision_input_projection(child)
            return projected
        if isinstance(value, (list, tuple)):
            return [decision_input_projection(child) for child in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    supplied = next(
        (
            value.get("decision_input_fingerprint")
            or value.get("input_state_fingerprint")
            for value in values
            if isinstance(value, dict)
            and (
                value.get("decision_input_fingerprint")
                or value.get("input_state_fingerprint")
            )
        ),
        None,
    )
    input_fingerprints = next(
        (
            value.get("input_fingerprints")
            for value in values
            if isinstance(value, dict)
            and isinstance(value.get("input_fingerprints"), dict)
        ),
        None,
    )
    decision_inputs_raw = json.dumps(
        decision_input_projection(values),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    basis = {
        "artifact_id": artifact_ref.get("artifact_id"),
        "artifact_sha256": artifact_ref.get("artifact_sha256"),
        "production_lane_identity": artifact_ref.get("production_lane_identity"),
        "body_projection_fingerprint": artifact_ref.get("body_projection_fingerprint"),
        "verification_input_ids": sorted(
            str(item) for item in _vectors.string_list(artifact_ref.get("verification_input_ids"))
        ),
        "supplied_input_state_fingerprint": str(supplied) if supplied else None,
        "input_fingerprints": input_fingerprints if isinstance(input_fingerprints, dict) else {},
        "decision_inputs_sha256": hashlib.sha256(
            decision_inputs_raw.encode("utf-8")
        ).hexdigest(),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def content_bound_attempt_identity(
    cycle_id: str,
    canonical_artifact_family: str,
    blocker_signature: str,
    input_state_fingerprint: str,
) -> str:
    # Keep the legacy label parameters in the callable contract, but exclude
    # them from the logical identity.  Family and blocker labels are trace
    # metadata and may be corrected without creating another attempt.
    basis = {
        "cycle_id": str(cycle_id),
        "input_state_fingerprint": str(input_state_fingerprint),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "attempt-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def legacy_content_bound_attempt_identity(
    cycle_id: str,
    canonical_artifact_family: str,
    blocker_signature: str,
    input_state_fingerprint: str,
) -> str:
    """Return the pre-v2 label-bound identity for compatibility tracing."""
    basis = {
        "cycle_id": str(cycle_id),
        "canonical_artifact_family": str(canonical_artifact_family),
        "blocker_signature": str(blocker_signature),
        "input_state_fingerprint": str(input_state_fingerprint),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "attempt-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

def logical_attempt_key(row: dict[str, Any]) -> str:
    cycle_id = str(row.get("cycle_id") or "")
    input_fingerprint = str(row.get("input_state_fingerprint") or "")
    if cycle_id and input_fingerprint:
        return f"logical:{cycle_id}:{input_fingerprint}"
    identity = str(row.get("attempt_identity") or "")
    return f"identity:{identity}" if identity else ""

def attempt_revision_value(row: dict[str, Any] | None) -> int:
    if not isinstance(row, dict):
        return 0
    for field in ("attempt_revision", "attempt_revision_candidate"):
        value = int(_values.float_value(row.get(field)) or 0)
        if value > 0:
            return value
    return 1 if row.get("attempt_identity") else 0

def canonical_json_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
