"""Validated adapters from native deterministic packets to stage result fields."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..ledger.support import read_initialization_metadata
from ..ledger.workflow_contract import workflow_contract_state
from .contracts import canonical_bytes
from .task_index_prevalidation import normalize_task_index_prevalidation


_REPO_SCAN_FIELDS = {
    "schema_version",
    "artifact_kind",
    "step",
    "cycle_id",
    "adapter_scan_status",
    "adapter_count",
    "repo_skill_adapter_packet",
    "blockers",
    "evidence_paths",
    "scan_packet_sha256",
}
_REPO_SCAN_RESULT_FIELDS = (
    "adapter_scan_status",
    "adapter_count",
    "repo_skill_adapter_packet",
    "blockers",
    "evidence_paths",
)
_ADAPTER_VALIDATION_FIELDS = {
    "schema_version",
    "artifact_kind",
    "step",
    "cycle_id",
    "task_id",
    "adapter_validation_status",
    "adapter_consumability_status",
    "adapter_architecture_status",
    "adapter_change_count",
    "adapter_validation_count",
    "adapter_revision_before_sha256",
    "adapter_revision_after_sha256",
    "adapter_architecture",
    "field_origins",
    "blockers",
    "evidence_paths",
    "validation_packet_sha256",
}
_CODE_STRUCTURE_FIELDS = {
    "schema_version",
    "artifact_kind",
    "step",
    "cycle_id",
    "result",
    "field_origins",
    "audit_packet_sha256",
}
_COMPILED_ACCEPTANCE_FIELDS = {
    "schema_version",
    "artifact_kind",
    "compiler_id",
    "source_draft_binding",
    "result",
    "result_sha256",
}
_ACCEPTANCE_REQUIRED_RESULT_FIELDS = {
    "format_version",
    "schema_version",
    "artifact_kind",
    "step",
    "acceptance_id",
    "task_id",
    "acceptance_status",
    "acceptance_provenance",
    "acceptance_criteria",
    "blockers",
    "evidence_paths",
}
_ACCEPTANCE_OPTIONAL_RESULT_FIELDS = {
    "acceptance_contract",
    "acceptance_scenarios",
    "validation_predicate_contract",
    "producer_directives",
    "mutually_unsatisfiable_contract",
    "unverifiable_acceptance_contract",
}
_COMPILER_FIRST_NATIVE_OWNER_KINDS = {
    "acceptance": "compiled_acceptance_owner_result",
    "authority": "orchestrator_authority_packet",
    "index": "task_state_index_scan_result",
    "index_pre_validate": "task_state_index_prevalidation_result",
}


def native_owner_artifact_kind(target: str) -> str | None:
    """Return the registered source artifact kind for native owner targets."""

    return _COMPILER_FIRST_NATIVE_OWNER_KINDS.get(target)


def _repo_scan_result(
    value: dict[str, Any], *, cycle_id: str, source_ref: str
) -> dict[str, Any]:
    if set(value) != _REPO_SCAN_FIELDS:
        raise ValueError("native repo adapter scan packet fields are invalid")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "repo_skill_adapter_scan_packet"
        or value.get("step") != "repo_skill_adapter_scan"
        or value.get("cycle_id") != cycle_id
    ):
        raise ValueError("native repo adapter scan packet scope is invalid")
    body = {
        key: item for key, item in value.items() if key != "scan_packet_sha256"
    }
    expected = hashlib.sha256(canonical_bytes(body) + b"\n").hexdigest()
    if value.get("scan_packet_sha256") != expected:
        raise ValueError("native repo adapter scan packet integrity failed")
    result = {key: value[key] for key in _REPO_SCAN_RESULT_FIELDS}
    evidence_paths = result.get("evidence_paths")
    if not isinstance(evidence_paths, list):
        raise ValueError("native repo adapter scan evidence_paths must be a list")
    if not evidence_paths:
        result["evidence_paths"] = [source_ref]
    return result


def _integrity(value: dict[str, Any], digest_field: str, label: str) -> None:
    body = {key: item for key, item in value.items() if key != digest_field}
    expected = hashlib.sha256(canonical_bytes(body) + b"\n").hexdigest()
    if value.get(digest_field) != expected:
        raise ValueError(f"native {label} packet integrity failed")


def _adapter_validation_result(
    value: dict[str, Any], *, cycle_id: str, source_ref: str
) -> dict[str, Any]:
    if set(value) != _ADAPTER_VALIDATION_FIELDS:
        raise ValueError("native adapter validation packet fields are invalid")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "repo_skill_adapter_validation_packet"
        or value.get("step") != "repo_skill_adapter_validate"
        or value.get("cycle_id") != cycle_id
    ):
        raise ValueError("native adapter validation packet scope is invalid")
    _integrity(value, "validation_packet_sha256", "adapter validation")
    result = {
        key: item
        for key, item in value.items()
        if key
        not in {
            "schema_version",
            "artifact_kind",
            "cycle_id",
            "validation_packet_sha256",
        }
    }
    if not isinstance(result.get("evidence_paths"), list):
        raise ValueError("native adapter validation evidence_paths must be a list")
    if not result["evidence_paths"]:
        result["evidence_paths"] = [source_ref]
    return result


def _code_structure_result(
    value: dict[str, Any], *, cycle_id: str, source_ref: str
) -> dict[str, Any]:
    if set(value) != _CODE_STRUCTURE_FIELDS:
        raise ValueError("native code structure packet fields are invalid")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "code_structure_audit_packet"
        or value.get("step") != "code_structure_audit"
        or value.get("cycle_id") != cycle_id
    ):
        raise ValueError("native code structure packet scope is invalid")
    _integrity(value, "audit_packet_sha256", "code structure")
    result = value.get("result")
    if not isinstance(result, dict):
        raise ValueError("native code structure result must be an object")
    result = dict(result)
    result["field_origins"] = value["field_origins"]
    evidence = result.get("evidence_paths")
    if not isinstance(evidence, list):
        raise ValueError("native code structure evidence_paths must be a list")
    if not evidence:
        result["evidence_paths"] = [source_ref]
    return result


def _compiled_acceptance_result(
    root: Path,
    value: dict[str, Any],
    *,
    cycle_id: str,
    source_ref: str,
) -> dict[str, Any]:
    try:
        from normalize_acceptance_and_demo.acceptance_compiler import (
            validate_compiled_acceptance,
        )
        from normalize_acceptance_and_demo.acceptance_identity import (
            AcceptanceIdentityError,
        )
    except ImportError as exc:
        raise ValueError(
            "registered acceptance compiler verifier is unavailable; "
            "launch the cycle through the workflow dependency registry"
        ) from exc
    initialization = read_initialization_metadata(root, cycle_id)
    expected_task_id = initialization.get("task_id")
    if not isinstance(expected_task_id, str) or not expected_task_id:
        raise ValueError(
            "compiled acceptance requires a task-bound cycle initialization"
        )
    try:
        verified = validate_compiled_acceptance(
            root,
            value,
            source_ref=source_ref,
            expected_task_id=expected_task_id,
        )
    except (AcceptanceIdentityError, OSError, UnicodeError) as exc:
        raise ValueError(f"native compiled acceptance verification failed: {exc}") from exc
    result = verified["result"]
    result_fields = set(result)
    if (
        not _ACCEPTANCE_REQUIRED_RESULT_FIELDS <= result_fields
        or result_fields
        - _ACCEPTANCE_REQUIRED_RESULT_FIELDS
        - _ACCEPTANCE_OPTIONAL_RESULT_FIELDS
        or result.get("format_version") != 2
        or result.get("schema_version") != 1
        or result.get("artifact_kind") != "acceptance_packet"
        or result.get("step") != "acceptance"
        or value.get("result_sha256") != hashlib.sha256(canonical_bytes(result)).hexdigest()
    ):
        raise ValueError("native compiled acceptance result integrity failed")
    return {
        key: item
        for key, item in result.items()
        if key
        not in {
            "format_version",
            "schema_version",
            "artifact_kind",
            "step",
            "task_id",
        }
    }


def _authority_packet_result(
    root: Path,
    value: dict[str, Any],
    *,
    cycle_id: str,
) -> dict[str, Any]:
    # Import lazily because authority_packet publishes through artifact_store.
    from ..authority_artifacts import validate_authority_artifacts
    from ..authority_boundary import project_authority_packet
    from ..authority_packet import validate_authority_packet_cycle

    projection = project_authority_packet(value)
    findings = list(projection.findings)
    findings.extend(validate_authority_artifacts(value, root))
    if findings:
        codes = ", ".join(str(row.get("code") or "") for row in findings)
        raise ValueError(
            f"native authority packet artifact verification failed: {codes}"
        )
    validate_authority_packet_cycle(root, cycle_id, value)
    return value


def _task_index_result(
    root: Path,
    value: dict[str, Any],
    *,
    cycle_id: str,
    source_ref: str,
    publish_auxiliary: bool,
    include_auxiliary_binding: bool,
) -> dict[str, Any]:
    try:
        from manage_task_state_index.state.compiler_contract_lint import (
            lint_owner_result,
        )
        from manage_task_state_index.state.prevalidation_compiler import (
            audit_projection,
        )
    except ImportError as exc:
        raise ValueError(
            "registered task-index compiler verifier is unavailable; "
            "launch the cycle through the workflow dependency registry"
        ) from exc
    payload = canonical_bytes(value) + b"\n"
    binding = {
        "ref": source_ref,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    lint = lint_owner_result(
        root,
        owner_result=binding,
        cycle_id=cycle_id,
    )
    if (
        lint.get("lint_status") != "pass"
        or lint.get("compatibility_class") != "canonical_schema_v2"
    ):
        findings = ", ".join(str(item) for item in lint.get("findings") or [])
        raise ValueError(
            "native task-index compiler result verification failed"
            + (f": {findings}" if findings else "")
        )
    audited = audit_projection(
        root,
        at=str(value.get("completed_at") or ""),
        publish=publish_auxiliary,
    )
    audit_result = audited.get("result")
    if not isinstance(audit_result, dict):
        raise ValueError("native task-index post-audit result is unavailable")
    blockers = audit_result.get("blockers")
    if not isinstance(blockers, list):
        raise ValueError("native task-index post-audit blockers are invalid")
    index_status = audit_result.get("index_status")
    if index_status not in {"pass", "blocked", "not_evaluated"}:
        raise ValueError("native task-index post-audit status is invalid")
    audit_verdict = (
        "pass"
        if index_status == "pass"
        else "block"
        if index_status == "blocked"
        else "not_evaluated"
    )
    high_blockers = [
        blocker
        for blocker in blockers
        if isinstance(blocker, dict) and blocker.get("severity") == "high"
    ]
    evidence_paths = [source_ref]
    for key in ("compilation", "plan", "transition_receipt"):
        candidate = value.get(key)
        if isinstance(candidate, dict) and isinstance(candidate.get("ref"), str):
            evidence_paths.append(candidate["ref"])
    audit_evidence = audit_result.get("evidence_paths")
    if isinstance(audit_evidence, list):
        evidence_paths.extend(
            path
            for path in audit_evidence
            if isinstance(path, str)
            and not path.startswith(
                ".task/index_prevalidation/input-manifest-"
            )
        )
    return {
        "index_status": (
            "snapshot_current" if index_status == "pass" else index_status
        ),
        "audit_verdict": audit_verdict,
        "high_severity_id_blockers": high_blockers,
        "audit_blockers": blockers,
        "index_snapshot_id": audit_result.get("index_snapshot_id"),
        "audit_input_manifest": (
            audited.get("index_snapshot") or {}
        ).get("audit_input_manifest"),
        "post_audit_owner_result_binding": (
            audited.get("owner_result_binding")
            if include_auxiliary_binding
            else None
        ),
        "audit_observation_scope": audit_result.get(
            "audit_observation_scope"
        ),
        "live_revalidation_required": audit_result.get(
            "live_revalidation_required"
        ),
        "evidence_paths": list(dict.fromkeys(evidence_paths)),
    }


def normalize_native_owner_result(
    target: str,
    value: dict[str, Any],
    *,
    root: Path | None = None,
    cycle_id: str,
    source_ref: str,
    publish_auxiliary: bool = False,
    include_auxiliary_binding: bool = False,
) -> dict[str, Any]:
    """Remove only a registered, integrity-checked native packet envelope."""

    artifact_kind = value.get("artifact_kind")
    if target == "repo_skill_adapter_scan" and artifact_kind == (
        "repo_skill_adapter_scan_packet"
    ):
        return _repo_scan_result(value, cycle_id=cycle_id, source_ref=source_ref)
    if target == "repo_skill_adapter_validate" and artifact_kind == (
        "repo_skill_adapter_validation_packet"
    ):
        return _adapter_validation_result(
            value, cycle_id=cycle_id, source_ref=source_ref
        )
    if target == "code_structure_audit" and artifact_kind == (
        "code_structure_audit_packet"
    ):
        return _code_structure_result(value, cycle_id=cycle_id, source_ref=source_ref)
    if target == "acceptance" and artifact_kind == (
        "compiled_acceptance_owner_result"
    ):
        if root is None:
            raise ValueError(
                "native compiled acceptance verification requires a workspace root"
            )
        return _compiled_acceptance_result(
            root,
            value,
            cycle_id=cycle_id,
            source_ref=source_ref,
        )
    if target == "authority" and artifact_kind == (
        "orchestrator_authority_packet"
    ):
        if root is None:
            raise ValueError(
                "native authority packet verification requires a workspace root"
            )
        return _authority_packet_result(root, value, cycle_id=cycle_id)
    if target == "index" and artifact_kind == "task_state_index_scan_result":
        if root is None:
            raise ValueError(
                "native task-index verification requires a workspace root"
            )
        return _task_index_result(
            root,
            value,
            cycle_id=cycle_id,
            source_ref=source_ref,
            publish_auxiliary=publish_auxiliary,
            include_auxiliary_binding=include_auxiliary_binding,
        )
    if (
        target == "index_pre_validate"
        and artifact_kind == "task_state_index_prevalidation_result"
    ):
        if root is None:
            raise ValueError(
                "native task-index prevalidation requires a workspace root"
            )
        return normalize_task_index_prevalidation(
            root,
            value,
            source_ref=source_ref,
        )
    if root is not None and target in _COMPILER_FIRST_NATIVE_OWNER_KINDS:
        initialization = read_initialization_metadata(root, cycle_id)
        if workflow_contract_state(initialization) == "enforced":
            expected = _COMPILER_FIRST_NATIVE_OWNER_KINDS[target]
            raise ValueError(
                f"compiler-first `{target}` owner result requires registered "
                f"artifact_kind `{expected}`"
            )
    return value


__all__ = ("native_owner_artifact_kind", "normalize_native_owner_result")
