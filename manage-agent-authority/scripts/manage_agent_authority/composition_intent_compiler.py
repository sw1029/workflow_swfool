"""Compile exact grant compositions from producer-owned operation inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import load_grant, verify_binding
from .canonical import normalized_time, object_sha256, sha256_file
from .composition import _create_compiled_composition
from .operation_batch import load_operation_batch
from .source_approval import (
    load_source_approval,
    validate_source_decision_binding,
)
from .producer_capability import _AUTHORITY_PRODUCER_CAPABILITY


MAX_COMPOSED_GRANTS = 128


def validate_composition_source_binding(
    root: Path, binding: dict[str, str]
) -> dict[str, str]:
    path = verify_binding(root, binding, "composition source approval")
    normalized = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    if normalized != binding:
        raise SystemExit("Composition source binding is not canonical.")
    approval = load_source_approval(path)
    if approval["schema_version"] in {2, 4}:
        raise SystemExit(
            "Historical schema-v2/v4 source approvals cannot authorize a "
            "prospective composition."
        )
    decision_kind = validate_source_decision_binding(root, approval)
    if decision_kind == "authority_root_approval_decision":
        raise SystemExit(
            "Historical full-echo root decisions cannot authorize a "
            "prospective composition."
        )
    return normalized


def _compiled_request(
    root: Path,
    operation_batch: dict[str, str],
    request_sha256: str,
    *,
    skills_root: Path | None,
) -> tuple[dict[str, str], dict[str, Any]]:
    batch_binding, _batch, compilations = load_operation_batch(
        root, operation_batch, skills_root=skills_root
    )
    matching = [
        item
        for item in compilations
        if item["request_sha256"] == request_sha256
    ]
    if len(matching) != 1:
        raise SystemExit(
            "Composition request digest must select exactly one operation-batch row."
        )
    request = matching[0]["request"]
    if request["composition_receipt"] is not None:
        raise SystemExit(
            "Composition must bind the exact base request with "
            "composition_receipt=null."
        )
    return batch_binding, matching[0]


def compile_grant_composition(
    root: Path,
    operation_batch: dict[str, str],
    request_sha256: str,
    grant_ids: list[str],
    source_approval: dict[str, str],
    *,
    created_at: str,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Derive and publish a composition receipt from closed semantic inputs."""

    workspace = root.resolve()
    at = normalized_time(created_at, "composition created_at")
    batch_binding, compilation = _compiled_request(
        workspace,
        operation_batch,
        request_sha256,
        skills_root=skills_root,
    )
    normalized_ids = sorted(set(str(item) for item in grant_ids))
    if (
        len(normalized_ids) != len(grant_ids)
        or len(normalized_ids) < 2
        or len(normalized_ids) > MAX_COMPOSED_GRANTS
    ):
        raise SystemExit(
            "Composition grant IDs must be unique and contain between 2 and "
            f"{MAX_COMPOSED_GRANTS} entries."
        )
    grant_bindings = []
    for grant_id in normalized_ids:
        grant, digest, _state = load_grant(workspace, grant_id)
        grant_bindings.append(
            {
                "grant_id": grant["grant_id"],
                "sha256": digest,
            }
        )
    source_binding = validate_composition_source_binding(
        workspace, source_approval
    )
    identity = object_sha256(
        {
            "operation_batch": batch_binding,
            "request_sha256": compilation["request_sha256"],
            "grant_bindings": grant_bindings,
            "source_approval": source_binding,
            "created_at": at,
        }
    )
    created = _create_compiled_composition(
        workspace,
        {
            "schema_version": 2,
            "artifact_kind": "authority_grant_composition",
            "composition_id": f"authcomp-{identity[:24]}",
            "request_sha256": compilation["request_sha256"],
            "grant_ids": normalized_ids,
            "source_approval": source_binding,
            "created_at": at,
            "idempotency_key": f"authcompk-{identity[:24]}",
        },
        producer_capability=_AUTHORITY_PRODUCER_CAPABILITY,
    )
    return {
        "status": "created",
        "composition_id": created["composition"]["composition_id"],
        "composition_binding": {
            "ref": created["ref"],
            "sha256": created["sha256"],
        },
        "request_sha256": compilation["request_sha256"],
        "grant_count": len(normalized_ids),
        "composition_intent_fingerprint": identity,
        "model_call_count": 0,
        "model_visible_bytes": 0,
        "model_authored_mechanical_bytes": 0,
    }


__all__ = (
    "MAX_COMPOSED_GRANTS",
    "compile_grant_composition",
    "validate_composition_source_binding",
)
