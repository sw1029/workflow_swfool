"""Compact v2 stage preparation and exact-input submission services."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..ledger.support import (
    ledger_lock,
    read_initialization_metadata,
)
from ..ledger.workflow_contract import require_cycle_mutation_contract
from ..result_contract.api import validate as validate_result
from .artifact_store import (
    load_routing_receipt,
    load_stage_input,
    load_usage_observation,
)
from .contracts import canonical_sha256
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
from .native_submission import publish_validated_projection
from .deterministic_submission import (
    build_receipted_result,
    receipt_pair,
)
from .submission_output import (
    build_submission_output,
    record_precondition_metrics,
    record_publication,
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
    publish_native_artifacts: bool = False,
    predict_native_artifacts: bool = False,
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
            preparation_id=str(preparation["preparation_id"]),
            state_fingerprint=str(preparation["state_fingerprint"]),
            publish_native_artifacts=publish_native_artifacts,
            predict_native_artifacts=predict_native_artifacts,
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
            preparation_id=str(preparation["preparation_id"]),
            state_fingerprint=str(preparation["state_fingerprint"]),
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
                "model_configuration_status": routing.get(
                    "model_configuration_status", "reference_only"
                ),
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
        preparation_id=str(preparation["preparation_id"]),
        state_fingerprint=str(preparation["state_fingerprint"]),
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


def _validate_candidate(
    full: dict[str, Any],
    preparation: dict[str, Any],
    routing: dict[str, Any] | None,
    work_order: dict[str, Any] | None,
    result: dict[str, Any],
    digest: str,
    judgment: dict[str, Any],
    input_bindings: dict[str, Any],
    usage: dict[str, Any],
    freshness: dict[str, Any],
    mode: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
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
        }, None
    validation = validate_result(
        str(preparation["target"]), result, mode, full
    )
    output = build_submission_output(
        preparation,
        judgment,
        result,
        digest,
        input_bindings,
        usage=usage,
        validation=validation,
    )
    record_precondition_metrics(output, validation, freshness)
    return output, validation


def _preflight_deterministic_submission(
    root: Path,
    preparation: dict[str, Any],
    prediction: dict[str, Any],
    *,
    mode: str = "block",
    max_files: int,
    max_paths: int,
) -> dict[str, Any]:
    from .deterministic_preflight import _preflight

    return _preflight(
        root,
        preparation,
        prediction,
        mode=mode,
        max_files=max_files,
        max_paths=max_paths,
    )


def _submit_v2_locked(
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
    deterministic_commit_pair: tuple[str, str] | None,
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
        predict_native_artifacts=True,
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
    result, digest, commit_block = build_receipted_result(
        root,
        preparation,
        judgment,
        input_bindings,
        deterministic_commit_pair,
        replay=replay,
        max_files=max_files,
        max_paths=max_paths,
    )
    if commit_block is not None:
        return commit_block
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
        return build_submission_output(
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
    output, validation = _validate_candidate(
        full,
        preparation,
        routing,
        work_order,
        result,
        digest,
        judgment,
        input_bindings,
        usage,
        freshness,
        mode,
    )
    if validation is None or not apply or validation["status"] == "block":
        return output
    judgment, result = publish_validated_projection(
        root,
        preparation,
        judgment,
        routing,
        result,
        validation,
        full,
        mode,
        exact_loader=_exact_judgment,
        result_validator=validate_result,
        owner_result_ref=owner_result_ref,
        owner_result_sha256=owner_result_sha256,
        semantic_ref=semantic_ref,
        semantic_sha256=semantic_sha256,
        routing_ref=routing_ref,
        routing_sha256=routing_sha256,
    )
    digest = canonical_sha256(result)
    publication = publish_result(
        root,
        cycle_id,
        preparation,
        result,
        digest,
        output["compiler_metrics"],
        input_bindings,
        max_files=max_files,
        max_paths=max_paths,
    )
    return record_publication(output, publication)


def submit_v2(
    root: Path,
    preparation: dict[str, Any],
    **submission: Any,
) -> dict[str, Any]:
    """Run prediction, gates, auxiliary commit, and publication under one lock."""

    cycle_id = str(preparation["cycle_id"])
    apply = bool(submission.get("apply"))
    commit_pair, receipt_block = receipt_pair(
        preparation,
        submission.get("deterministic_commit_ref"),
        submission.get("deterministic_commit_sha256"),
    )
    if receipt_block is not None:
        return receipt_block
    locked_submission = dict(submission)
    locked_submission.pop("deterministic_commit_ref", None)
    locked_submission.pop("deterministic_commit_sha256", None)
    locked_submission["deterministic_commit_pair"] = commit_pair
    if apply:
        require_cycle_mutation_contract(
            read_initialization_metadata(root, cycle_id),
            "submit compiled stage",
        )
    preview_input = {**locked_submission, "apply": False}
    with ledger_lock(root, cycle_id, exclusive=False):
        preview = _submit_v2_locked(root, preparation, **preview_input)
    if (
        not apply
        or preview.get("status") == "block"
    ):
        return preview
    with ledger_lock(root, cycle_id, exclusive=True):
        require_cycle_mutation_contract(
            read_initialization_metadata(root, cycle_id),
            "submit compiled stage",
        )
        return _submit_v2_locked(
            root, preparation, **locked_submission
        )


__all__ = [
    "prepare_v2",
    "require_v1_judgment",
    "submit_v2",
]
