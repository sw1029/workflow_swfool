"""Preparation-bound producers for model-supplied stage semantics and receipts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..cycle_ledger import immutable_write_bytes
from ..ledger.support import read_initialization_metadata, rel_path
from ..ledger.workflow_contract import require_cycle_mutation_contract
from ..model_effort.routing import select_route
from .artifact_store import (
    MAX_SEMANTIC_BYTES,
    MAX_STAGE_INPUT_BYTES,
    MAX_USAGE_BYTES,
    _read_exact_json,
    cas_write_receipt,
    stage_input_path,
)
from .builder import ResultBuilder
from .contracts import (
    PREPARATION_SCHEMA_VERSION_V2,
    PREPARATION_SCHEMA_VERSION_V3,
    canonical_bytes,
)
from .executor_registry import EXECUTOR_REGISTRY, executor_spec
from .native_results import (
    native_owner_artifact_kind,
    normalize_native_owner_result,
)
from .preparation_store import load_published_preparation
from .specs import TARGET_COMPILE_SPECS


OWNER_RESULT_PRODUCER_TARGETS = frozenset(
    target
    for target, registered in EXECUTOR_REGISTRY.items()
    if registered.executor_kind != "deterministic"
)
SEMANTIC_PRODUCER_TARGETS = frozenset(
    target
    for target, registered in EXECUTOR_REGISTRY.items()
    if registered.executor_kind == "hybrid"
)
ROUTING_REQUEST_FIELDS = frozenset(
    {
        "signals",
        "signal_evidence",
        "final_direction_ownership",
        "requested_tier",
        "request_max",
        "max_escalation_reason",
        "prior_tier5_evidence",
        "agent_count",
        "model_bindings",
    }
)
USAGE_OBSERVATION_FIELDS = frozenset(
    {
        "provider_id",
        "runtime_id",
        "model_id",
        "request_id",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
    }
)

if len(OWNER_RESULT_PRODUCER_TARGETS) != 20:
    raise RuntimeError("owner-result producer registry must cover exactly 20 targets")
if len(SEMANTIC_PRODUCER_TARGETS) != 4:
    raise RuntimeError("semantic producer registry must cover exactly 4 hybrid targets")


def _preparation(
    root: str | Path, ref: str, sha256: str
) -> tuple[Path, dict[str, Any]]:
    workspace = Path(root).resolve(strict=True)
    preparation = load_published_preparation(workspace, ref, sha256)
    if preparation.get("schema_version") not in {
        PREPARATION_SCHEMA_VERSION_V2,
        PREPARATION_SCHEMA_VERSION_V3,
    }:
        raise ValueError("stage input producers require a v2/v3 preparation")
    state = require_cycle_mutation_contract(
        read_initialization_metadata(
            workspace, str(preparation["cycle_id"])
        ),
        "publish preparation-bound stage input",
    )
    if state != "enforced":
        raise ValueError(
            "stage input producers are available only for compiler-first cycles"
        )
    return workspace, preparation


def _wrapper(
    preparation: dict[str, Any],
    input_kind: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "artifact_kind": (
            "model_usage_observation"
            if input_kind == "usage"
            else "stage_routing_receipt"
            if input_kind == "routing"
            else f"stage_{input_kind}"
        ),
        "cycle_id": preparation["cycle_id"],
        "target": preparation["target"],
        "preparation_id": preparation["preparation_id"],
        "state_fingerprint": preparation["state_fingerprint"],
        **fields,
    }


def _payload(
    root: Path,
    preparation: dict[str, Any],
    input_kind: str,
    fields: dict[str, Any],
) -> tuple[dict[str, Any], bytes, str, Path]:
    wrapper = _wrapper(preparation, input_kind, fields)
    payload = canonical_bytes(wrapper) + b"\n"
    maximum = (
        MAX_SEMANTIC_BYTES
        if input_kind == "semantic"
        else MAX_USAGE_BYTES
        if input_kind in {"routing", "usage"}
        else MAX_STAGE_INPUT_BYTES
    )
    if len(payload) > maximum:
        raise ValueError(f"{input_kind} producer output exceeds its byte budget")
    digest = hashlib.sha256(payload).hexdigest()
    return (
        wrapper,
        payload,
        digest,
        stage_input_path(
            root, str(preparation["cycle_id"]), input_kind, digest
        ),
    )


def _publish(
    root: Path,
    preparation: dict[str, Any],
    input_kind: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    _value, payload, digest, path = _payload(
        root, preparation, input_kind, fields
    )
    mutation_performed = immutable_write_bytes(path, payload)
    binding = {
        "ref": rel_path(root, path),
        "sha256": digest,
        "size_bytes": len(payload),
    }
    return {
        "schema_version": 1,
        "artifact_kind": f"compiled_stage_{input_kind}_binding",
        "cycle_id": preparation["cycle_id"],
        "target": preparation["target"],
        "preparation_id": preparation["preparation_id"],
        f"{input_kind}_binding": binding,
        "publication_status": (
            "published" if mutation_performed else "reused"
        ),
        "write_receipt": cas_write_receipt(
            len(payload), mutation_performed
        ),
    }


def _owner_validation_body(
    root: Path,
    preparation: dict[str, Any],
    body: dict[str, Any],
    *,
    source_ref: str | None = None,
) -> dict[str, Any]:
    target = str(preparation["target"])
    _wrapper_value, _payload_bytes, digest, path = _payload(
        root, preparation, "owner_result", {"result": body}
    )
    normalized = normalize_native_owner_result(
        target,
        body,
        root=root,
        cycle_id=str(preparation["cycle_id"]),
        source_ref=source_ref or rel_path(root, path),
        publish_auxiliary=False,
    )
    normalized = dict(normalized)
    validation_body = dict(normalized)
    for field, expected in (preparation.get("derived_values") or {}).items():
        if field in validation_body and validation_body[field] != expected:
            raise ValueError(
                f"owner result conflicts with derived field: {field}"
            )
        validation_body.pop(field, None)
    specification = TARGET_COMPILE_SPECS[target]
    missing = set(specification.owner_receipt_fields) - set(validation_body)
    if missing:
        raise ValueError(
            "owner result is missing required owner fields: "
            + ", ".join(sorted(missing))
        )
    ResultBuilder().build(
        preparation, {"owner_result": validation_body}
    )
    if digest != hashlib.sha256(
        canonical_bytes(
            _wrapper(preparation, "owner_result", {"result": body})
        )
        + b"\n"
    ).hexdigest():
        raise RuntimeError("owner-result producer identity changed during validation")
    return normalized


def publish_owner_result(
    root: str | Path,
    preparation_ref: str,
    preparation_sha256: str,
    body: dict[str, Any] | None = None,
    *,
    source_ref: str | None = None,
    source_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate owner-origin fields, then publish only the canonical wrapper."""

    workspace, preparation = _preparation(
        root, preparation_ref, preparation_sha256
    )
    target = str(preparation["target"])
    if target not in OWNER_RESULT_PRODUCER_TARGETS:
        raise ValueError(
            "deterministic targets publish through their registered executor"
        )
    native_kind = native_owner_artifact_kind(target)
    if bool(source_ref) != bool(source_sha256):
        raise ValueError(
            "owner source ref and sha256 must be supplied together"
        )
    source_binding = None
    if native_kind is not None:
        if not source_ref or not source_sha256 or body is not None:
            raise ValueError(
                "native owner targets require one exact source binding"
            )
        source_value, source_payload, _source_path = _read_exact_json(
            workspace,
            source_ref,
            source_sha256,
            MAX_STAGE_INPUT_BYTES,
        )
        if source_payload != canonical_bytes(source_value) + b"\n":
            raise ValueError("native owner source must be canonical immutable JSON")
        source_binding = {
            "ref": source_ref,
            "sha256": source_sha256,
            "size_bytes": len(source_payload),
        }
        body = source_value
        if (
            source_value.get("artifact_kind") == "stage_owner_result"
            and source_value.get("schema_version") == 1
            and source_value.get("cycle_id") == preparation["cycle_id"]
            and source_value.get("target") == target
            and isinstance(source_value.get("result"), dict)
        ):
            body = source_value["result"]
    elif source_ref or source_sha256:
        raise ValueError(
            "non-native owner targets accept a semantic owner body, not a source binding"
        )
    if not isinstance(body, dict):
        raise ValueError("owner result body must be a JSON object")
    normalized = _owner_validation_body(
        workspace,
        preparation,
        body,
        source_ref=source_ref,
    )
    fields: dict[str, Any] = {"result": normalized}
    if source_binding is not None:
        fields["source_binding"] = source_binding
    return _publish(
        workspace, preparation, "owner_result", fields
    )


def publish_semantic(
    root: str | Path,
    preparation_ref: str,
    preparation_sha256: str,
    semantic: dict[str, Any],
    *,
    reasoned_not_applicable: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish a closed hybrid semantic body without a model-authored envelope."""

    workspace, preparation = _preparation(
        root, preparation_ref, preparation_sha256
    )
    target = str(preparation["target"])
    if target not in SEMANTIC_PRODUCER_TARGETS:
        raise ValueError("semantic producer requires a registered hybrid target")
    if not isinstance(semantic, dict):
        raise ValueError("semantic body must be a JSON object")
    reasoned = reasoned_not_applicable or {}
    if not isinstance(reasoned, dict):
        raise ValueError("reasoned_not_applicable must be a JSON object")
    specification = TARGET_COMPILE_SPECS[target]
    allowed = set(specification.semantic_fields) | set(
        specification.optional_semantic_fields
    )
    unknown = set(semantic) - allowed
    missing = set(specification.semantic_fields) - set(semantic)
    if unknown:
        raise ValueError(
            "semantic body has unsupported fields: "
            + ", ".join(sorted(unknown))
        )
    if missing:
        raise ValueError(
            "semantic body is missing required fields: "
            + ", ".join(sorted(missing))
        )
    ResultBuilder().build(
        preparation,
        {
            "semantic": semantic,
            "reasoned_not_applicable": reasoned,
        },
    )
    return _publish(
        workspace,
        preparation,
        "semantic",
        {
            "semantic": semantic,
            "reasoned_not_applicable": reasoned,
        },
    )


def compile_routing(
    root: str | Path,
    preparation_ref: str,
    preparation_sha256: str,
    profile_id: str,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive a compact preparation-bound receipt from routing semantics."""

    workspace, preparation = _preparation(
        root, preparation_ref, preparation_sha256
    )
    target = str(preparation["target"])
    registered = executor_spec(target)
    if not registered.routing_required:
        raise ValueError("stage target does not permit a routing receipt")
    if profile_id not in registered.allowed_routing_profiles:
        raise ValueError("routing profile is outside the registered target set")
    route_request = request or {}
    if not isinstance(route_request, dict):
        raise ValueError("routing request must be a JSON object")
    unknown = set(route_request) - ROUTING_REQUEST_FIELDS
    if unknown:
        raise ValueError(
            "routing request has unsupported fields: "
            + ", ".join(sorted(unknown))
        )
    if len(canonical_bytes(route_request)) > MAX_USAGE_BYTES:
        raise ValueError("routing request exceeds its byte budget")
    route = select_route(profile_id, route_request)
    if route.get("routing_violations"):
        codes = ", ".join(
            str(item.get("code") or "routing_violation")
            for item in route["routing_violations"]
            if isinstance(item, dict)
        )
        raise ValueError(f"routing request violates policy: {codes}")
    receipt_fields = {
        key: route[key]
        for key in (
            "policy_id",
            "profile_id",
            "routing_tier",
            "requested_model_ref",
            "requested_model",
            "model_configuration_status",
            "requested_reasoning_effort",
            "routing_reason_codes",
        )
    }
    return _publish(
        workspace, preparation, "routing", receipt_fields
    )


def publish_usage_observation(
    root: str | Path,
    preparation_ref: str,
    preparation_sha256: str,
    observation: dict[str, Any],
) -> dict[str, Any]:
    """Publish caller-asserted usage without elevating it to trusted telemetry."""

    workspace, preparation = _preparation(
        root, preparation_ref, preparation_sha256
    )
    if preparation.get("executor_kind") == "deterministic":
        raise ValueError("deterministic stages cannot publish model usage")
    if not isinstance(observation, dict) or set(observation) != set(
        USAGE_OBSERVATION_FIELDS
    ):
        raise ValueError("usage observation fields are incomplete or unsupported")
    for field in ("provider_id", "runtime_id", "model_id", "request_id"):
        value = observation.get(field)
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value.encode("utf-8")) > 256
        ):
            raise ValueError("usage provenance IDs must be bounded strings")
    counts: dict[str, int] = {}
    for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
        count = observation.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("usage token counts must be non-negative integers")
        counts[field] = count
    if counts["cached_input_tokens"] > counts["input_tokens"]:
        raise ValueError("cached input tokens cannot exceed input tokens")
    output = _publish(
        workspace, preparation, "usage", dict(observation)
    )
    output.update(
        {
            "usage_aggregate_eligible": False,
            "usage_provenance_status": "caller_asserted_unverified",
        }
    )
    return output


__all__ = [
    "OWNER_RESULT_PRODUCER_TARGETS",
    "ROUTING_REQUEST_FIELDS",
    "SEMANTIC_PRODUCER_TARGETS",
    "USAGE_OBSERVATION_FIELDS",
    "compile_routing",
    "publish_owner_result",
    "publish_semantic",
    "publish_usage_observation",
]
