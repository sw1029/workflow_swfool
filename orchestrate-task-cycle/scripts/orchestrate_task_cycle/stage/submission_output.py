"""Compact output and metrics projection for stage submission."""

from __future__ import annotations

from typing import Any

from .contracts import canonical_bytes, canonical_sha256, leaf_count


OUTPUT_SCALARS = (
    "status",
    "validation_verdict",
    "progress_verdict",
    "review_status",
    "quality_verdict",
    "selection_outcome",
    "index_status",
    "audit_observation_scope",
    "live_revalidation_required",
    "commit_status",
    "completion_status",
)


def record_precondition_metrics(
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


def record_publication(
    output: dict[str, Any],
    publication: dict[str, Any],
) -> dict[str, Any]:
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


def build_submission_output(
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
        [
            binding
            for binding in input_bindings.values()
            if isinstance(binding, dict)
        ]
    ) + (1 if preparation.get("machine_input_binding") else 2)
    usage_binding = input_bindings.get("usage_binding") or {}
    root_fields = {
        "status": validation["status"],
        "stop_reason": (
            "rejected_result" if validation["status"] == "block" else None
        ),
        "preparation_id": preparation["preparation_id"],
        "result_projection": projection,
        "result_contract": validation,
        "result_artifact_sha256": digest,
        "applied": existing is not None,
        "input_bindings": input_bindings,
        "compiler_metrics": {
            **preparation_metrics,
            "semantic_leaf_count": leaf_count(judgment.get("semantic") or {}),
            "owner_result_leaf_count": leaf_count(
                judgment.get("owner_result") or {}
            ),
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
                (input_bindings.get("semantic_binding") or {}).get(
                    "size_bytes", 0
                )
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
            "usage_receipt_schema_version": usage_binding.get(
                "schema_version"
            ),
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


__all__ = [
    "OUTPUT_SCALARS",
    "build_submission_output",
    "record_publication",
    "record_precondition_metrics",
]
