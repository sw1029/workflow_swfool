"""Preparation-bound stage input storage and exact-binding validation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..cycle_ledger import cycle_dir, immutable_write_bytes
from ..ledger.support import (
    initialization_path,
    read_initialization_metadata,
    rel_path,
)
from ..ledger.workflow_contract import (
    require_cycle_mutation_contract,
    workflow_contract_state,
)
from .contracts import canonical_bytes
from .native_results import (
    native_owner_artifact_kind,
    normalize_native_owner_result,
)
from .native_source import native_source_result
from .storage_common import (
    SHA256_PATTERN,
    cas_write_receipt,
    read_exact_json,
)


MAX_STAGE_INPUT_BYTES = 2 * 1024 * 1024
MAX_SEMANTIC_BYTES = 64 * 1024
MAX_USAGE_BYTES = 16 * 1024


def stage_input_path(
    root: Path, cycle_id: str, input_kind: str, digest: str
) -> Path:
    """Return the sole producer-owned CAS path for one exact stage input."""

    if input_kind not in {"owner_result", "semantic", "routing", "usage"}:
        raise ValueError("unsupported stage input kind")
    if not SHA256_PATTERN.fullmatch(digest):
        raise ValueError("stage input digest must be lowercase SHA-256")
    return (
        cycle_dir(root, cycle_id)
        / "compiler"
        / input_kind
        / "sha256"
        / f"{digest}.json"
    )


def _cycle_input_contract_state(root: Path, cycle_id: str) -> str | None:
    if not initialization_path(root, cycle_id).is_file():
        return None
    return workflow_contract_state(read_initialization_metadata(root, cycle_id))


def _require_producer_cas(
    root: Path,
    cycle_id: str,
    input_kind: str,
    ref: str,
    digest: str,
    path: Path,
) -> None:
    expected = stage_input_path(
        root, cycle_id, input_kind, digest
    ).resolve(strict=False)
    expected_ref = expected.relative_to(root).as_posix()
    if path != expected or ref != expected_ref:
        raise ValueError(
            f"{input_kind} binding must use its compiler producer CAS path"
        )


def load_stage_input(
    root: Path,
    ref: str,
    sha256: str,
    *,
    cycle_id: str,
    target: str,
    input_kind: str,
    preparation_id: str | None = None,
    state_fingerprint: str | None = None,
    publish_native_artifacts: bool = False,
    predict_native_artifacts: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if publish_native_artifacts and predict_native_artifacts:
        raise ValueError("native artifacts cannot be published and predicted together")
    maximum = (
        MAX_SEMANTIC_BYTES
        if input_kind == "semantic"
        else MAX_STAGE_INPUT_BYTES
    )
    value, payload, path = read_exact_json(root, ref, sha256, maximum)
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError(f"{input_kind} input must be canonical immutable JSON")
    enforced = _cycle_input_contract_state(root, cycle_id) == "enforced"
    native_direct_diagnostic = (
        enforced
        and input_kind == "owner_result"
        and native_owner_artifact_kind(target) is not None
        and preparation_id is None
        and state_fingerprint is None
    )
    if enforced and not native_direct_diagnostic:
        _require_producer_cas(
            root, cycle_id, input_kind, ref, sha256, path
        )
    expected_kind = f"stage_{input_kind}"
    if value.get("artifact_kind") == expected_kind:
        wrapper_fields = {
            "schema_version",
            "artifact_kind",
            "cycle_id",
            "target",
            "result" if input_kind == "owner_result" else "semantic",
        }
        if input_kind == "semantic":
            wrapper_fields.add("reasoned_not_applicable")
        if (
            enforced
            and input_kind == "owner_result"
            and native_owner_artifact_kind(target) is not None
        ):
            wrapper_fields.add("source_binding")
        required_fields = wrapper_fields - {"reasoned_not_applicable"}
        if enforced:
            wrapper_fields.update({"preparation_id", "state_fingerprint"})
            required_fields.update({"preparation_id", "state_fingerprint"})
            if input_kind == "semantic":
                required_fields.add("reasoned_not_applicable")
        if not required_fields <= set(value) <= wrapper_fields:
            raise ValueError(f"{input_kind} wrapper has unsupported fields")
        if value.get("schema_version") != (2 if enforced else 1):
            raise ValueError(f"unsupported {input_kind} schema_version")
        if value.get("cycle_id") != cycle_id or value.get("target") != target:
            raise ValueError(f"{input_kind} binding scope does not match preparation")
        if enforced:
            sealed_preparation = value.get("preparation_id")
            sealed_fingerprint = value.get("state_fingerprint")
            if (
                not isinstance(sealed_preparation, str)
                or not sealed_preparation
                or not SHA256_PATTERN.fullmatch(str(sealed_fingerprint))
            ):
                raise ValueError(
                    f"{input_kind} binding preparation provenance is invalid"
                )
            if (
                preparation_id is not None
                and sealed_preparation != preparation_id
            ) or (
                state_fingerprint is not None
                and sealed_fingerprint != state_fingerprint
            ):
                raise ValueError(
                    f"{input_kind} binding does not match the exact preparation"
                )
        key = "result" if input_kind == "owner_result" else "semantic"
        body = value.get(key)
        if not isinstance(body, dict):
            raise ValueError(f"{input_kind} artifact {key} must be an object")
    elif input_kind == "owner_result" and (
        not enforced or native_direct_diagnostic
    ):
        body = value
    else:
        raise ValueError("semantic input must use the stage_semantic wrapper")
    binding = {"ref": ref, "sha256": sha256, "size_bytes": len(payload)}
    if input_kind == "semantic":
        reasoned = value.get("reasoned_not_applicable") or {}
        if not isinstance(reasoned, dict):
            raise ValueError("semantic reasoned_not_applicable must be an object")
        return {"semantic": body, "reasoned_not_applicable": reasoned}, binding
    source_binding = value.get("source_binding") if enforced else None
    source_verified = False
    if source_binding is not None:
        body = native_source_result(
            root,
            source_binding,
            target=target,
            cycle_id=cycle_id,
            sealed_body=body,
            maximum_bytes=MAX_STAGE_INPUT_BYTES,
            publish_native_artifacts=publish_native_artifacts,
            predict_native_artifacts=predict_native_artifacts,
        )
        source_verified = True
    if not source_verified:
        body = normalize_native_owner_result(
            target,
            body,
            root=root,
            cycle_id=cycle_id,
            source_ref=ref,
            publish_auxiliary=publish_native_artifacts,
            include_auxiliary_binding=(
                publish_native_artifacts or predict_native_artifacts
            ),
        )
    return {"owner_result": body}, binding


def write_stage_input(
    root: Path,
    cycle_id: str,
    target: str,
    input_kind: str,
    body: dict[str, Any],
    *,
    preparation: dict[str, Any] | None = None,
    reasoned_not_applicable: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish one canonical exact stage input generated by an executor."""

    require_cycle_mutation_contract(
        read_initialization_metadata(root, cycle_id),
        f"publish {input_kind}",
    )
    wrapper, binding, payload = project_stage_input(
        root,
        cycle_id,
        target,
        input_kind,
        body,
        preparation=preparation,
        reasoned_not_applicable=reasoned_not_applicable,
    )
    del wrapper
    mutation_performed = immutable_write_bytes(
        root / str(binding["ref"]), payload
    )
    return {
        **binding,
        "duplicate": not mutation_performed,
        "write_receipt": cas_write_receipt(len(payload), mutation_performed),
    }


def project_stage_input(
    root: Path,
    cycle_id: str,
    target: str,
    input_kind: str,
    body: dict[str, Any],
    *,
    preparation: dict[str, Any] | None = None,
    reasoned_not_applicable: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    """Render one exact stage input and binding without mutating the workspace."""

    if input_kind not in {"owner_result", "semantic"}:
        raise ValueError("unsupported stage input kind")
    wrapper: dict[str, Any] = {
        "schema_version": 2 if preparation is not None else 1,
        "artifact_kind": f"stage_{input_kind}",
        "cycle_id": cycle_id,
        "target": target,
        "result" if input_kind == "owner_result" else "semantic": body,
    }
    if preparation is not None:
        if (
            preparation.get("cycle_id") != cycle_id
            or preparation.get("target") != target
        ):
            raise ValueError("stage input preparation scope is invalid")
        wrapper.update(
            {
                "preparation_id": preparation.get("preparation_id"),
                "state_fingerprint": preparation.get("state_fingerprint"),
            }
        )
    if input_kind == "semantic" and preparation is not None:
        wrapper["reasoned_not_applicable"] = dict(
            reasoned_not_applicable or {}
        )
    payload = canonical_bytes(wrapper) + b"\n"
    maximum = (
        MAX_SEMANTIC_BYTES
        if input_kind == "semantic"
        else MAX_STAGE_INPUT_BYTES
    )
    if len(payload) > maximum:
        raise ValueError("generated stage input exceeds its byte budget")
    digest = hashlib.sha256(payload).hexdigest()
    path = stage_input_path(root, cycle_id, input_kind, digest)
    return wrapper, {
        "ref": rel_path(root, path),
        "sha256": digest,
        "size_bytes": len(payload),
    }, payload


def load_usage_observation(
    root: Path,
    ref: str,
    sha256: str,
    *,
    cycle_id: str,
    target: str,
    preparation_id: str | None = None,
    state_fingerprint: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load caller-asserted token observations without upgrading trust."""

    value, payload, path = read_exact_json(
        root, ref, sha256, MAX_USAGE_BYTES
    )
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError("model usage observation must be canonical immutable JSON")
    v1_fields = {
        "schema_version", "artifact_kind", "cycle_id", "target",
        "input_tokens", "cached_input_tokens", "output_tokens",
    }
    legacy_v2_fields = v1_fields | {
        "provider_id", "runtime_id", "model_id", "request_id",
    }
    producer_v2_fields = legacy_v2_fields | {
        "preparation_id", "state_fingerprint",
    }
    enforced = _cycle_input_contract_state(root, cycle_id) == "enforced"
    version = value.get("schema_version")
    expected_fields = (
        producer_v2_fields
        if enforced
        else legacy_v2_fields
        if version == 2
        else v1_fields
    )
    if set(value) != expected_fields:
        raise ValueError("model usage observation has unsupported fields")
    if (
        version not in {1, 2}
        or value.get("artifact_kind") != "model_usage_observation"
        or value.get("cycle_id") != cycle_id
        or value.get("target") != target
    ):
        raise ValueError("model usage observation scope is invalid")
    if enforced:
        _require_producer_cas(root, cycle_id, "usage", ref, sha256, path)
        if (
            version != 2
            or value.get("preparation_id") != preparation_id
            or value.get("state_fingerprint") != state_fingerprint
        ):
            raise ValueError(
                "model usage observation does not match the exact preparation"
            )
    counts: dict[str, Any] = {}
    for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
        count = value.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(
                "model usage token counts must be non-negative integers"
            )
        counts[field] = count
    if counts["cached_input_tokens"] > counts["input_tokens"]:
        raise ValueError("cached input tokens cannot exceed input tokens")
    if version == 2:
        for field in ("provider_id", "runtime_id", "model_id", "request_id"):
            item = value.get(field)
            if (
                not isinstance(item, str)
                or not item.strip()
                or len(item.encode()) > 256
            ):
                raise ValueError(
                    "usage v2 provenance IDs must be bounded strings"
                )
            counts[field] = item
        counts["usage_aggregate_eligible"] = False
        counts["usage_provenance_status"] = "caller_asserted_unverified"
    else:
        counts["usage_aggregate_eligible"] = False
        counts["usage_provenance_status"] = "legacy_unverified"
    return counts, {
        "ref": ref,
        "sha256": sha256,
        "size_bytes": len(payload),
        "schema_version": version,
    }


def load_routing_receipt(
    root: Path,
    ref: str,
    sha256: str,
    *,
    cycle_id: str,
    target: str,
    preparation_id: str,
    state_fingerprint: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load one closed, current-target routing decision receipt."""

    value, payload, path = read_exact_json(
        root, ref, sha256, MAX_USAGE_BYTES
    )
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError("stage routing receipt must be canonical immutable JSON")
    fields = {
        "schema_version", "artifact_kind", "cycle_id", "target",
        "preparation_id", "state_fingerprint", "policy_id", "profile_id",
        "routing_tier", "requested_model_ref", "requested_model",
        "requested_reasoning_effort", "routing_reason_codes",
    }
    enforced = _cycle_input_contract_state(root, cycle_id) == "enforced"
    if enforced:
        fields.add("model_configuration_status")
        _require_producer_cas(root, cycle_id, "routing", ref, sha256, path)
    if set(value) != fields:
        raise ValueError("stage routing receipt has unsupported fields")
    if (
        value.get("schema_version") != (2 if enforced else 1)
        or value.get("artifact_kind") != "stage_routing_receipt"
        or value.get("cycle_id") != cycle_id
        or value.get("target") != target
        or value.get("preparation_id") != preparation_id
        or value.get("state_fingerprint") != state_fingerprint
    ):
        raise ValueError("stage routing receipt scope is stale or invalid")
    tier = value.get("routing_tier")
    if (
        isinstance(tier, bool)
        or not isinstance(tier, int)
        or tier not in range(1, 6)
    ):
        raise ValueError("stage routing receipt requires routing_tier 1..5")
    for field in (
        "policy_id", "profile_id", "requested_model_ref",
        "requested_model", "requested_reasoning_effort",
    ):
        item = value.get(field)
        if (
            not isinstance(item, str)
            or not item.strip()
            or len(item.encode()) > 256
        ):
            raise ValueError(
                "stage routing receipt requires bounded routing claims"
            )
    if enforced and value.get("model_configuration_status") not in {
        "reference_only", "resolved",
    }:
        raise ValueError(
            "stage routing receipt has an invalid model configuration status"
        )
    reasons = value.get("routing_reason_codes")
    if (
        not reasons
        or not isinstance(reasons, list)
        or any(
            not isinstance(item, str)
            or not item
            or len(item.encode()) > 128
            for item in reasons
        )
        or len(set(reasons)) != len(reasons)
    ):
        raise ValueError("stage routing receipt reason codes are invalid")
    return value, {"ref": ref, "sha256": sha256, "size_bytes": len(payload)}


__all__ = [
    "MAX_SEMANTIC_BYTES",
    "MAX_STAGE_INPUT_BYTES",
    "MAX_USAGE_BYTES",
    "load_routing_receipt",
    "load_stage_input",
    "load_usage_observation",
    "project_stage_input",
    "stage_input_path",
    "write_stage_input",
]
