"""Durable proof that a deterministic result came from the exact renderer."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..ledger.support import stable_file_token
from .artifact_store import (
    ARTIFACT_LIMITS,
    compiler_artifact_path,
    write_compiler_artifact,
)
from .contracts import (
    canonical_bytes,
    canonical_sha256,
    preparation_binding_sha256,
)
from .stage_input_store import (
    MAX_STAGE_INPUT_BYTES,
    project_stage_input,
    stage_input_path,
)
from .storage_common import read_exact_json, resolved_ref


RECEIPT_ARTIFACT_TYPE = "deterministic_commit_receipt"
RECEIPT_ARTIFACT_KIND = "deterministic_stage_commit_receipt"
RECEIPT_COMPILER_ID = "orchestrate-task-cycle/deterministic-executor-v1"
_BINDING_FIELDS = {"ref", "sha256", "size_bytes"}
_MACHINE_BINDING_FIELDS = {
    "artifact_type",
    "ref",
    "sha256",
    "size_bytes",
}
_RECEIPT_FIELDS = {
    "schema_version",
    "artifact_kind",
    "compiler_id",
    "cycle_id",
    "target",
    "preparation_id",
    "preparation_binding_sha256",
    "state_fingerprint",
    "precondition_fingerprints_sha256",
    "machine_input_binding",
    "executor_spec",
    "prediction_sha256",
    "raw_owner_result_sha256",
    "result_sha256",
    "owner_result_binding",
    "effect_plan",
    "effect_plan_sha256",
    "effect_applicability",
    "effect_observation",
}


def _binding(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in _BINDING_FIELDS}


def _machine_binding(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _MACHINE_BINDING_FIELDS:
        raise ValueError("deterministic machine input binding is invalid")
    return {key: value[key] for key in _MACHINE_BINDING_FIELDS}


def _effect_bytes(
    target: str, effect: dict[str, Any] | None
) -> bytes:
    if target != "dashboard":
        if effect is not None:
            raise ValueError(
                "only the dashboard deterministic renderer may plan an effect"
            )
        return b""
    if (
        not isinstance(effect, dict)
        or set(effect)
        != {"kind", "ref", "content", "content_sha256"}
        or effect.get("kind") != "write_text"
        or not isinstance(effect.get("ref"), str)
        or not isinstance(effect.get("content"), str)
    ):
        raise ValueError("dashboard deterministic effect plan is invalid")
    payload = effect["content"].encode("utf-8")
    if effect.get("content_sha256") != hashlib.sha256(payload).hexdigest():
        raise ValueError("dashboard deterministic effect digest is invalid")
    return payload


def _effect_receipt(
    target: str,
    effect: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    payload = _effect_bytes(target, effect)
    if target != "dashboard":
        return {"kind": "not_applicable"}, None
    assert effect is not None
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "kind": "write_text",
        "ref": effect["ref"],
        "encoding": "utf-8",
        "content_sha256": digest,
        "size_bytes": len(payload),
    }, {
        "ref": effect["ref"],
        "sha256": digest,
        "size_bytes": len(payload),
    }


def deterministic_prediction_sha256(
    preparation: dict[str, Any],
    prediction: dict[str, Any],
) -> str:
    """Bind renderer output to its exact preparation and executor projection."""

    return canonical_sha256(
        {
            "domain": "deterministic-stage-prediction-v1",
            "cycle_id": preparation.get("cycle_id"),
            "target": preparation.get("target"),
            "preparation_id": preparation.get("preparation_id"),
            "state_fingerprint": preparation.get("state_fingerprint"),
            "machine_input_binding": preparation.get(
                "machine_input_binding"
            ),
            "executor_spec": prediction.get("executor_spec"),
            "raw_owner_result": prediction.get("raw_owner_result"),
            "effect_plan": prediction.get("effect_plan"),
        }
    )


def _render_receipt(
    preparation: dict[str, Any],
    prediction: dict[str, Any],
    result_sha256: str,
    owner_result_binding: dict[str, Any],
) -> dict[str, Any]:
    cycle_id = str(preparation["cycle_id"])
    target = str(preparation["target"])
    raw_owner = prediction.get("raw_owner_result")
    if not isinstance(raw_owner, dict):
        raise ValueError("deterministic prediction lacks an owner result")
    owner = _binding(owner_result_binding)
    effect = prediction.get("effect_plan")
    effect_plan, effect_observation = _effect_receipt(target, effect)
    return {
        "schema_version": 1,
        "artifact_kind": RECEIPT_ARTIFACT_KIND,
        "compiler_id": RECEIPT_COMPILER_ID,
        "cycle_id": cycle_id,
        "target": target,
        "preparation_id": str(preparation["preparation_id"]),
        "preparation_binding_sha256": preparation_binding_sha256(
            preparation
        ),
        "state_fingerprint": str(preparation["state_fingerprint"]),
        "precondition_fingerprints_sha256": canonical_sha256(
            preparation.get("precondition_fingerprints") or {}
        ),
        "machine_input_binding": _machine_binding(
            preparation["machine_input_binding"]
        ),
        "executor_spec": prediction.get("executor_spec"),
        "prediction_sha256": deterministic_prediction_sha256(
            preparation,
            prediction,
        ),
        "raw_owner_result_sha256": canonical_sha256(raw_owner),
        "result_sha256": result_sha256,
        "owner_result_binding": owner,
        "effect_plan": effect_plan,
        "effect_plan_sha256": canonical_sha256(effect_plan),
        "effect_applicability": (
            "required" if target == "dashboard" else "not_applicable"
        ),
        "effect_observation": effect_observation,
    }


def _publish_deterministic_commit_receipt(
    root: Path,
    preparation: dict[str, Any],
    prediction: dict[str, Any],
    result_sha256: str,
    owner_result_binding: dict[str, Any],
) -> dict[str, Any]:
    receipt = _render_receipt(
        preparation,
        prediction,
        result_sha256,
        owner_result_binding,
    )
    published = write_compiler_artifact(
        root,
        str(preparation["cycle_id"]),
        RECEIPT_ARTIFACT_TYPE,
        receipt,
    )
    return _binding(published)


def _load_receipt(
    root: Path,
    cycle_id: str,
    binding: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if (
        not isinstance(binding, dict)
        or set(binding) not in (
            {"ref", "sha256"},
            _BINDING_FIELDS,
        )
    ):
        raise ValueError("deterministic commit binding fields are invalid")
    ref = str(binding.get("ref") or "")
    digest = str(binding.get("sha256") or "")
    value, payload, path = read_exact_json(
        root,
        ref,
        digest,
        ARTIFACT_LIMITS[RECEIPT_ARTIFACT_TYPE],
    )
    expected = compiler_artifact_path(
        root,
        cycle_id,
        RECEIPT_ARTIFACT_TYPE,
        digest,
    ).resolve(strict=True)
    if path != expected or ref != expected.relative_to(root).as_posix():
        raise ValueError(
            "deterministic commit binding must use its compiler CAS path"
        )
    if payload != canonical_bytes(value) + b"\n":
        raise ValueError(
            "deterministic commit receipt must be canonical immutable JSON"
        )
    if (
        "size_bytes" in binding
        and binding.get("size_bytes") != len(payload)
    ):
        raise ValueError("deterministic commit binding size is invalid")
    return value, {
        "ref": ref,
        "sha256": digest,
        "size_bytes": len(payload),
    }


def _raw_owner(
    root: Path,
    preparation: dict[str, Any],
    binding: dict[str, Any],
) -> dict[str, Any]:
    cycle_id = str(preparation["cycle_id"])
    ref = str(binding["ref"])
    digest = str(binding["sha256"])
    value, payload, path = read_exact_json(
        root,
        ref,
        digest,
        MAX_STAGE_INPUT_BYTES,
    )
    expected = stage_input_path(
        root, cycle_id, "owner_result", digest
    ).resolve(strict=True)
    if (
        path != expected
        or ref != expected.relative_to(root).as_posix()
        or payload != canonical_bytes(value) + b"\n"
        or binding.get("size_bytes") != len(payload)
    ):
        raise ValueError("deterministic owner binding is not exact")
    raw = value.get("result")
    if not isinstance(raw, dict):
        raise ValueError("deterministic owner wrapper lacks its raw result")
    return raw


def _verify_receipt_shape(
    receipt: dict[str, Any],
    preparation: dict[str, Any],
    result_sha256: str,
    owner_result_binding: dict[str, Any],
    raw_owner: dict[str, Any],
) -> None:
    if set(receipt) != _RECEIPT_FIELDS:
        raise ValueError("deterministic commit receipt fields are not closed")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind") != RECEIPT_ARTIFACT_KIND
        or receipt.get("compiler_id") != RECEIPT_COMPILER_ID
        or receipt.get("cycle_id") != preparation.get("cycle_id")
        or receipt.get("target") != preparation.get("target")
        or receipt.get("preparation_id") != preparation.get("preparation_id")
        or receipt.get("preparation_binding_sha256")
        != preparation_binding_sha256(preparation)
        or receipt.get("state_fingerprint")
        != preparation.get("state_fingerprint")
        or receipt.get("precondition_fingerprints_sha256")
        != canonical_sha256(
            preparation.get("precondition_fingerprints") or {}
        )
        or receipt.get("machine_input_binding")
        != _machine_binding(preparation["machine_input_binding"])
        or receipt.get("executor_spec")
        != preparation.get("executor_spec")
        or receipt.get("result_sha256") != result_sha256
        or receipt.get("owner_result_binding")
        != _binding(owner_result_binding)
    ):
        raise ValueError("deterministic commit receipt scope is invalid")
    effect = receipt.get("effect_plan")
    target = str(preparation["target"])
    if target == "dashboard":
        expected_ref = (
            f".task/cycle/{preparation['cycle_id']}/dashboard.md"
        )
        if (
            not isinstance(effect, dict)
            or set(effect)
            != {
                "kind",
                "ref",
                "encoding",
                "content_sha256",
                "size_bytes",
            }
            or effect.get("kind") != "write_text"
            or effect.get("ref") != expected_ref
            or effect.get("encoding") != "utf-8"
            or receipt.get("effect_observation")
            != {
                "ref": effect.get("ref"),
                "sha256": effect.get("content_sha256"),
                "size_bytes": effect.get("size_bytes"),
            }
        ):
            raise ValueError("dashboard commit effect receipt is invalid")
    elif (
        effect != {"kind": "not_applicable"}
        or receipt.get("effect_observation") is not None
    ):
        raise ValueError(
            "effectless deterministic receipt must be not_applicable"
        )
    if (
        not isinstance(receipt.get("prediction_sha256"), str)
        or receipt.get("raw_owner_result_sha256")
        != canonical_sha256(raw_owner)
        or receipt.get("effect_plan_sha256") != canonical_sha256(effect)
        or receipt.get("effect_applicability")
        != (
            "required"
            if preparation.get("target") == "dashboard"
            else "not_applicable"
        )
    ):
        raise ValueError("deterministic commit receipt integrity failed")


def _verify_effect_observation(
    root: Path,
    preparation: dict[str, Any],
    receipt: dict[str, Any],
) -> None:
    if preparation.get("target") != "dashboard":
        return
    observation = receipt["effect_observation"]
    effect_path = resolved_ref(root, str(observation["ref"]))
    token = stable_file_token(effect_path)
    if (
        token is None
        or token[2] != observation["size_bytes"]
        or token[5] != observation["sha256"]
    ):
        raise ValueError(
            "dashboard effect bytes differ from the committed receipt"
        )


def validate_deterministic_commit_receipt(
    root: Path,
    preparation: dict[str, Any],
    result_sha256: str,
    owner_result_binding: dict[str, Any],
    commit_binding: dict[str, Any],
    *,
    max_files: int,
    max_paths: int,
    verify_current: bool,
) -> dict[str, Any]:
    """Reopen a receipt and optionally prove it against the current renderer."""

    cycle_id = str(preparation["cycle_id"])
    receipt, exact_binding = _load_receipt(
        root,
        cycle_id,
        commit_binding,
    )
    raw_owner = _raw_owner(root, preparation, owner_result_binding)
    _verify_receipt_shape(
        receipt,
        preparation,
        result_sha256,
        owner_result_binding,
        raw_owner,
    )
    from .artifact_store import load_compiler_artifact

    load_compiler_artifact(
        root,
        cycle_id,
        preparation["machine_input_binding"],
        "machine_input",
    )
    _verify_effect_observation(root, preparation, receipt)
    if not verify_current:
        return exact_binding
    from .deterministic_dispatch import predict_deterministic

    prediction = predict_deterministic(
        root,
        preparation,
        max_files=max_files,
        max_paths=max_paths,
    )
    if prediction.get("status") == "block":
        raise ValueError("deterministic commit receipt preparation is stale")
    expected = _render_receipt(
        preparation,
        prediction,
        result_sha256,
        owner_result_binding,
    )
    if canonical_bytes(expected) != canonical_bytes(receipt):
        raise ValueError(
            "deterministic commit receipt differs from current renderer"
        )
    _wrapper, projected, _payload = project_stage_input(
        root,
        cycle_id,
        str(preparation["target"]),
        "owner_result",
        prediction["raw_owner_result"],
        preparation=preparation,
    )
    if projected != _binding(owner_result_binding):
        raise ValueError(
            "deterministic owner binding differs from current renderer"
        )
    return exact_binding


__all__ = [
    "deterministic_prediction_sha256",
    "validate_deterministic_commit_receipt",
]
