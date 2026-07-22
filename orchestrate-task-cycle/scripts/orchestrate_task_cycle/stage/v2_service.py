"""Compact v2 stage preparation and exact-input submission services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..result_contract.api import validate as validate_result
from .artifact_store import load_routing_receipt, load_stage_input, load_usage_observation
from .builder import ResultBuilder
from .contracts import (
    canonical_bytes,
    canonical_sha256,
    leaf_count,
)
from .gates import validate_submission_transition
from .publication import (
    existing_publication,
    publish_result,
    published_preparation,
    replay_mismatch,
)
from .specs import TARGET_COMPILE_SPECS
from .executor_registry import executor_spec
from .freshness import (
    evaluate_preparation_freshness,
    load_bound_material,
    validate_owner_post_effect_claims,
)
from .preparation_v3 import prepare_v2


OUTPUT_SCALARS = (
    "status",
    "validation_verdict",
    "progress_verdict",
    "review_status",
    "quality_verdict",
    "selection_outcome",
    "index_status",
    "commit_status",
    "completion_status",
)


def _pair(ref: str | None, digest: str | None, label: str) -> tuple[str, str] | None:
    if bool(ref) != bool(digest):
        raise ValueError(f"--{label}-ref and --{label}-sha256 must be supplied together")
    return (str(ref), str(digest)) if ref and digest else None


def require_v1_judgment(
    judgment: dict[str, Any] | None, *exact_bindings: str | None
) -> dict[str, Any]:
    if any(value is not None for value in exact_bindings):
        raise ValueError("exact stage input bindings require a v2 preparation")
    if judgment is None:
        raise ValueError("v1 stage submission requires inline judgment JSON")
    return judgment


def _exact_judgment(
    root: Path,
    preparation: dict[str, Any],
    *,
    owner_result_ref: str | None,
    owner_result_sha256: str | None,
    semantic_ref: str | None,
    semantic_sha256: str | None,
    routing_ref: str | None,
    routing_sha256: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    target, cycle_id = str(preparation["target"]), str(preparation["cycle_id"])
    spec = TARGET_COMPILE_SPECS[target]
    owner_pair = _pair(owner_result_ref, owner_result_sha256, "owner-result")
    semantic_pair = _pair(semantic_ref, semantic_sha256, "semantic")
    routing_pair = _pair(routing_ref, routing_sha256, "routing")
    registered = executor_spec(target)
    if bool(spec.owner_receipt_fields) != bool(owner_pair):
        raise ValueError("v2 stage requires one exact owner result binding")
    if bool(spec.semantic_fields) != bool(semantic_pair):
        raise ValueError("v2 semantic binding presence does not match field origin contract")
    if registered.routing_required != bool(routing_pair):
        raise ValueError("stage routing receipt presence does not match executor contract")
    judgment: dict[str, Any] = {}
    bindings: dict[str, Any] = {}
    routing: dict[str, Any] | None = None
    if owner_pair:
        loaded, binding = load_stage_input(
            root,
            *owner_pair,
            cycle_id=cycle_id,
            target=target,
            input_kind="owner_result",
        )
        owner = loaded["owner_result"]
        for field, expected in (preparation.get("derived_values") or {}).items():
            if field in owner and owner[field] != expected:
                raise ValueError(f"owner result conflicts with derived field: {field}")
            owner.pop(field, None)
        judgment.update(loaded)
        bindings["owner_result_binding"] = binding
    if semantic_pair:
        loaded, binding = load_stage_input(
            root,
            *semantic_pair,
            cycle_id=cycle_id,
            target=target,
            input_kind="semantic",
        )
        judgment.update(loaded)
        bindings["semantic_binding"] = binding
    if routing_pair:
        routing, binding = load_routing_receipt(
            root,
            *routing_pair,
            cycle_id=cycle_id,
            target=target,
            preparation_id=str(preparation["preparation_id"]),
            state_fingerprint=str(preparation["state_fingerprint"]),
        )
        if (
            routing.get("policy_id") != registered.routing_policy_id
            or routing.get("profile_id") not in registered.allowed_routing_profiles
        ):
            raise ValueError(
                "stage routing receipt is outside the registered policy/profile set"
            )
        owner = judgment.setdefault("owner_result", {})
        if not isinstance(owner, dict):
            raise ValueError("routing requires an owner result object")
        owner.update(
            {
                "agent_routing_applicability": "delegated",
                "policy_id": routing["policy_id"],
                "profile_id": routing["profile_id"],
                "routing_tier": routing["routing_tier"],
                "requested_model_ref": routing["requested_model_ref"],
                "requested_model": routing["requested_model"],
                "model_configuration_status": "reference_only",
                "requested_reasoning_effort": routing[
                    "requested_reasoning_effort"
                ],
                "routing_reason_codes": routing["routing_reason_codes"],
                "routing_signals": {},
                "routing_signal_evidence": {},
                "routing_violations": [],
                "routing_enforcement": "prompt_only",
                "routing_limitation": (
                    "preparation-bound request receipt does not prove runtime enforcement"
                ),
            }
        )
        bindings["routing_binding"] = binding
    return judgment, bindings, routing


def _usage(
    root: Path,
    preparation: dict[str, Any],
    ref: str | None,
    digest: str | None,
) -> tuple[dict[str, int], dict[str, Any] | None]:
    pair = _pair(ref, digest, "usage")
    if pair is None:
        return {}, None
    if preparation.get("executor_kind") == "deterministic":
        raise ValueError("deterministic stage executors must not supply model usage")
    return load_usage_observation(
        root,
        *pair,
        cycle_id=str(preparation["cycle_id"]),
        target=str(preparation["target"]),
    )


def _submission_prestate(
    root: Path,
    preparation: dict[str, Any],
    *,
    max_files: int,
    max_paths: int,
) -> dict[str, Any]:
    replay = published_preparation(
        root, str(preparation["cycle_id"]), preparation
    )
    if replay:
        _material, work_order = load_bound_material(root, preparation)
        return {
            "status": "ok",
            "replay": True,
            "preparation": preparation,
            "full_context": None,
            "work_order": work_order,
            "freshness": None,
        }
    freshness = evaluate_preparation_freshness(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
        allow_post_effect=True,
    )
    if freshness["status"] == "block":
        return freshness
    return {
        "status": "ok",
        "replay": False,
        "preparation": freshness["preparation"],
        "full_context": freshness["full_context"],
        "work_order": freshness["work_order"],
        "freshness": freshness,
    }


def _record_precondition_metrics(
    output: dict[str, Any],
    validation: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    changed = list(freshness["changed_precondition_selectors"])
    status = str(freshness["freshness_status"])
    if changed:
        status = (
            "owner_validated_post_effect"
            if validation["status"] != "block"
            else "post_effect_owner_validation_failed"
        )
    output["compiler_metrics"].update(
        {
            "precondition_validation_status": status,
            "post_effect_changed_selector_count": len(changed),
            "post_effect_changed_selectors_sha256": canonical_sha256(changed),
        }
    )


def submit_v2(
    root: Path,
    preparation: dict[str, Any],
    *,
    task_id: str | None,
    owner_result_ref: str | None,
    owner_result_sha256: str | None,
    semantic_ref: str | None,
    semantic_sha256: str | None,
    routing_ref: str | None,
    routing_sha256: str | None,
    usage_ref: str | None,
    usage_sha256: str | None,
    mode: str,
    apply: bool,
    max_files: int,
    max_paths: int,
) -> dict[str, Any]:
    cycle_id, target = str(preparation["cycle_id"]), str(preparation["target"])
    prestate = _submission_prestate(
        root, preparation, max_files=max_files, max_paths=max_paths
    )
    if prestate["status"] == "block":
        return prestate
    replay = bool(prestate["replay"])
    preparation = prestate["preparation"]
    full = prestate["full_context"]
    work_order = prestate["work_order"]
    freshness = prestate["freshness"]
    judgment, input_bindings, routing = _exact_judgment(
        root,
        preparation,
        owner_result_ref=owner_result_ref,
        owner_result_sha256=owner_result_sha256,
        semantic_ref=semantic_ref,
        semantic_sha256=semantic_sha256,
        routing_ref=routing_ref,
        routing_sha256=routing_sha256,
    )
    if freshness is not None:
        claim_block = validate_owner_post_effect_claims(
            preparation, freshness, judgment.get("owner_result")
        )
        if claim_block is not None:
            return claim_block
    usage, usage_binding = _usage(
        root, preparation, usage_ref, usage_sha256
    )
    if usage_binding is not None:
        input_bindings["usage_binding"] = usage_binding
    result = ResultBuilder().build(preparation, judgment)
    digest = canonical_sha256(result)
    existing = existing_publication(
        root,
        cycle_id,
        target,
        preparation,
        result,
        digest,
        input_bindings,
        repair_projection=apply,
    )
    if existing is not None:
        return _output(
            preparation,
            judgment,
            result,
            digest,
            input_bindings,
            usage=usage,
            existing=existing,
        )
    if replay:
        return replay_mismatch(preparation)
    if full is None:
        raise RuntimeError("current stage context was not collected")
    transition = validate_submission_transition(
        full, preparation, routing if routing is not None else work_order
    )
    if transition["status"] == "block":
        return {
            "status": "block",
            "stop_reason": "blocked_transition",
            "preparation_id": preparation["preparation_id"],
            "transition_validation": transition,
            "freshness_status": freshness["freshness_status"],
            "changed_precondition_selectors": freshness[
                "changed_precondition_selectors"
            ],
            "applied": False,
        }
    validation = validate_result(target, result, mode, full)
    output = _output(
        preparation,
        judgment,
        result,
        digest,
        input_bindings,
        usage=usage,
        validation=validation,
    )
    _record_precondition_metrics(output, validation, freshness)
    if not apply or validation["status"] == "block":
        return output
    publication = publish_result(
        root,
        cycle_id,
        preparation,
        result,
        digest,
        output["compiler_metrics"],
        input_bindings,
    )
    output.update(
        {
            "applied": True,
            "event": publication["event"],
            "event_duplicate": publication["event_duplicate"],
            "ledger_path": publication["ledger_path"],
        }
    )
    output["compiler_metrics"].update(publication["compiler_metrics"])
    output["compiler_metrics"]["ledger_event_bytes"] = publication[
        "ledger_event_bytes"
    ]
    return output


def _output(
    preparation: dict[str, Any],
    judgment: dict[str, Any],
    result: dict[str, Any],
    digest: str,
    input_bindings: dict[str, Any],
    *,
    usage: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validation or {
        "status": "ok",
        "target": preparation["target"],
        "mode": "replay",
        "findings": [],
        "missing_fields": [],
    }
    projection = {
        key: result.get(key)
        for key in OUTPUT_SCALARS
        if result.get(key) is None
        or isinstance(result.get(key), (bool, int, float))
        or (
            isinstance(result.get(key), str)
            and len(result.get(key).encode("utf-8")) <= 256
        )
    }
    preparation_metrics = preparation.get("compiler_metrics") or {}
    if not isinstance(preparation_metrics, dict):
        preparation_metrics = {}
    opened_inputs = len(
        [binding for binding in input_bindings.values() if isinstance(binding, dict)]
    ) + (1 if preparation.get("machine_input_binding") else 2)
    usage_binding = input_bindings.get("usage_binding") or {}
    root_fields = {
        "status": validation["status"],
        "stop_reason": "rejected_result" if validation["status"] == "block" else None,
        "preparation_id": preparation["preparation_id"],
        "result_projection": projection,
        "result_contract": validation,
        "result_artifact_sha256": digest,
        "applied": existing is not None,
        "input_bindings": input_bindings,
        "compiler_metrics": {
            **preparation_metrics,
            "semantic_leaf_count": leaf_count(judgment.get("semantic") or {}),
            "owner_result_leaf_count": leaf_count(judgment.get("owner_result") or {}),
            "compiled_result_leaf_count": leaf_count(result),
            "model_authored_mechanical_bytes": 0,
            "model_authored_mechanical_bytes_origin": "field_origin_registry",
            "inline_payload_bytes": 0,
            "owner_result_bytes": int(
                (input_bindings.get("owner_result_binding") or {}).get(
                    "size_bytes", 0
                )
            ),
            "semantic_bytes": int(
                (input_bindings.get("semantic_binding") or {}).get("size_bytes", 0)
            ),
            "raw_bytes_read": sum(
                int(binding.get("size_bytes") or 0)
                for binding in input_bindings.values()
                if isinstance(binding, dict)
            ),
            "files_opened_count": int(
                preparation_metrics.get("files_opened_count") or 0
            )
            + opened_inputs,
            "files_written_count": int(
                preparation_metrics.get("files_written_count") or 0
            ),
            "preparation_bytes": len(canonical_bytes(preparation)) + 1,
            "model_visible_bytes": (
                0
                if preparation.get("executor_kind") == "deterministic"
                else int(preparation_metrics.get("model_visible_bytes") or 0)
                + int(
                    (input_bindings.get("semantic_binding") or {}).get(
                        "size_bytes", 0
                    )
                )
            ),
            "model_call_count": (
                1
                if input_bindings.get("routing_binding")
                or input_bindings.get("semantic_binding")
                else 0
            ),
            "usage_receipt_ref": usage_binding.get("ref"),
            "usage_receipt_sha256": usage_binding.get("sha256"),
            "usage_receipt_schema_version": usage_binding.get("schema_version"),
            **(usage or {}),
        },
    }
    if existing:
        stored_metrics = existing["event"].get("compiler_metrics")
        if isinstance(stored_metrics, dict):
            root_fields["compiler_metrics"] = dict(stored_metrics)
        root_fields.update(
            {
                "result_artifact_ref": existing["result_artifact_ref"],
                "event": existing["event"],
                "event_duplicate": True,
                "ledger_path": existing["ledger_path"],
            }
        )
    else:
        root_fields["result_artifact_ref"] = (
            f".task/cycle/{preparation['cycle_id']}/packets/"
            f"result-{preparation['target']}-{digest}.json"
        )
    return root_fields


__all__ = ["prepare_v2", "require_v1_judgment", "submit_v2"]
