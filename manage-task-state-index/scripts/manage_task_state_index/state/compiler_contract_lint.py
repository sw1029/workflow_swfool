"""Bounded structural lint for task-state owner-result compiler contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .scan_result_integrity import (
    SCAN_RESULT_FIELDS,
    validate_scan_result_evidence,
)
from .scan_transition import load_scan_compilation
from .transition_plan_contract import canonical_bytes


MAX_OWNER_RESULT_BYTES = 128 * 1024
MAX_OWNER_RESULT_LEAVES = 1024
FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "artifact_bodies",
        "context",
        "events",
        "full_packet",
        "packet",
        "source_body",
        "task_body",
    }
)
CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
COMPILER_FIRST_PROFILE = "compiler_first_enforced_v1"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _workspace_file(root: Path, ref: str) -> Path:
    raw = Path(ref)
    if raw.is_absolute() or not raw.parts or ".." in raw.parts:
        raise ValueError("Owner-result ref must be a workspace-relative path")
    candidate = root
    for part in raw.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("Owner-result ref must not traverse a symlink")
    try:
        path = candidate.resolve(strict=True)
        path.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError("Owner-result ref does not resolve inside the workspace") from exc
    if not path.is_file():
        raise ValueError("Owner-result ref must identify one regular file")
    return path


def _shape_metrics(value: Any) -> tuple[int, set[str]]:
    leaves = 0
    found: set[str] = set()
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            found.update(set(item) & FORBIDDEN_PAYLOAD_KEYS)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        else:
            leaves += 1
    return leaves, found


def _canonical_v2_findings(
    root: Path,
    binding: dict[str, str],
    payload: bytes,
    value: dict[str, Any],
) -> list[str]:
    findings: list[str] = []
    if set(value) != SCAN_RESULT_FIELDS:
        findings.append("schema_v2_fields_not_closed")
    if (
        value.get("artifact_kind") != "task_state_index_scan_result"
        or value.get("operation") != "scan"
    ):
        findings.append("schema_v2_owner_kind_invalid")
    body = {key: item for key, item in value.items() if key != "result_sha256"}
    if value.get("result_sha256") != _digest(canonical_bytes(body)):
        findings.append("schema_v2_result_digest_invalid")
    if payload != canonical_bytes(value) + b"\n":
        findings.append("schema_v2_not_canonical_json")
    try:
        compilation_binding, compilation = load_scan_compilation(
            root, value.get("compilation")
        )
        validate_scan_result_evidence(
            root,
            binding,
            payload,
            value,
            compilation_binding,
            compilation,
        )
    except (OSError, UnicodeError, ValueError):
        findings.append("schema_v2_evidence_rederivation_failed")
    return findings


def _cycle_profile(root: Path, cycle_id: str) -> str | None:
    if not CYCLE_ID_PATTERN.fullmatch(cycle_id):
        raise ValueError("Cycle id is not a bounded path-safe identifier")
    path = _workspace_file(
        root, f".task/cycle/{cycle_id}/initialization.json"
    )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Cycle initialization is not valid UTF-8 JSON") from exc
    if (
        not isinstance(value, dict)
        or value.get("cycle_id") != cycle_id
    ):
        raise ValueError("Cycle initialization does not match the selected cycle")
    profile = value.get("workflow_contract_profile")
    return str(profile) if profile is not None else None


def lint_owner_result(
    root: Path,
    *,
    owner_result: dict[str, str],
    cycle_id: str | None = None,
) -> dict[str, Any]:
    """Inspect one exact result without opening referenced artifact bodies."""

    if set(owner_result) != {"ref", "sha256"}:
        raise ValueError("Owner-result binding must contain exact ref and sha256")
    ref, expected = owner_result["ref"], owner_result["sha256"]
    if (
        not isinstance(ref, str)
        or not ref
        or not isinstance(expected, str)
        or len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        raise ValueError("Owner-result binding values are invalid")
    root = root.resolve()
    cycle_profile = _cycle_profile(root, cycle_id) if cycle_id else None
    path = _workspace_file(root, ref)
    size = path.stat().st_size
    if size > MAX_OWNER_RESULT_BYTES:
        raise ValueError(
            f"Owner result exceeds the {MAX_OWNER_RESULT_BYTES}-byte lint limit"
        )
    payload = path.read_bytes()
    if len(payload) > MAX_OWNER_RESULT_BYTES:
        raise ValueError(
            f"Owner result exceeds the {MAX_OWNER_RESULT_BYTES}-byte lint limit"
        )
    if _digest(payload) != expected:
        raise ValueError("Owner-result sha256 does not match exact bytes")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Owner result is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Owner result must be a JSON object")
    leaves, forbidden_keys = _shape_metrics(value)
    forbidden = sorted(forbidden_keys)
    findings: list[str] = []
    schema_version = value.get("schema_version")
    artifact_kind = value.get("artifact_kind")
    if (
        schema_version == 2
        and artifact_kind == "task_state_index_scan_result"
    ):
        compatibility_class = "canonical_schema_v2"
        findings.extend(
            _canonical_v2_findings(
                root,
                {"ref": ref, "sha256": expected},
                payload,
                value,
            )
        )
        lint_status = "pass" if not findings else "block"
    elif schema_version is None or schema_version == 1:
        compatibility_class = "historical_schema_v1"
        findings.append("schema_v1_owner_result_historical_only")
        if cycle_profile == COMPILER_FIRST_PROFILE:
            findings.append("schema_v1_forbidden_in_compiler_first_cycle")
            lint_status = "block"
        else:
            lint_status = "warn"
    else:
        compatibility_class = "unsupported"
        findings.append("unsupported_owner_result_schema")
        lint_status = "block"
    if leaves > MAX_OWNER_RESULT_LEAVES:
        findings.append("owner_result_leaf_budget_exceeded")
        lint_status = "block"
    if forbidden:
        findings.append("embedded_payload_keys_forbidden")
        lint_status = "block"
    return {
        "schema_version": 1,
        "artifact_kind": "task_state_index_compiler_contract_lint",
        "lint_status": lint_status,
        "compatibility_class": compatibility_class,
        "cycle_id": cycle_id,
        "workflow_contract_profile": cycle_profile,
        "owner_result_binding": {
            "ref": ref,
            "sha256": expected,
        },
        "size_bytes": len(payload),
        "size_limit_bytes": MAX_OWNER_RESULT_BYTES,
        "leaf_count": leaves,
        "leaf_limit": MAX_OWNER_RESULT_LEAVES,
        "forbidden_payload_keys": forbidden,
        "findings": sorted(set(findings)),
        "model_authored_mechanical_bytes_policy": "must_be_zero",
    }


__all__ = (
    "MAX_OWNER_RESULT_BYTES",
    "MAX_OWNER_RESULT_LEAVES",
    "lint_owner_result",
)
