"""Body-free immutable artifacts for selected-successor authority preparation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding, read_bound_bytes
from .selection_publication_store import (
    _bounded_payload,
    _canonical_json,
    _sha256_bytes,
    _successor_authority_index_path,
    _successor_authority_locator_path,
    _successor_authority_packet_path,
    _successor_authority_projection_path,
    _write_once,
)


PACKET_KEYS = {
    "schema_version",
    "artifact_kind",
    "status",
    "prepared_at",
    "bundle",
    "request_context",
    "evaluation_context",
    "grants",
    "operation_manifests",
    "operations",
    "authority_proofs",
    "authority_effects",
    "packet_content_sha256",
}
PROJECTION_KEYS = {
    "schema_version",
    "artifact_kind",
    "status",
    "prepared_at",
    "bundle",
    "request_context",
    "evaluation_context",
    "grants",
    "operation_manifests",
    "operations",
    "authority_effects",
    "projection_content_sha256",
}
INDEX_KEYS = {
    "schema_version",
    "artifact_kind",
    "input_sha256",
    "prepared_at",
    "bundle",
    "request_context",
    "evaluation_context",
    "grants",
    "operation_manifests",
    "outcome_kind",
    "outcome",
    "index_content_sha256",
}
MAX_INDEX_BYTES = 64 * 1024
MAX_OUTCOME_BYTES = 256 * 1024
LOCATOR_KEYS = {
    "schema_version",
    "artifact_kind",
    "input_sha256",
    "packet",
    "operation_manifests",
    "locator_content_sha256",
}


def _content(value: dict[str, Any], field: str) -> str:
    body = {key: item for key, item in value.items() if key != field}
    return _sha256_bytes(_canonical_json(body))


def authority_input_identity(
    *,
    bundle: Any,
    request_context: Any,
    evaluation_context: Any,
    grants: dict[str, dict[str, Any]],
    operation_manifests: dict[str, dict[str, str]],
    prepared_at: str,
) -> tuple[dict[str, Any], str]:
    identity = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_input",
        "prepared_at": prepared_at,
        "bundle": normalize_binding(bundle, "authority input bundle"),
        "request_context": normalize_binding(
            request_context, "authority input request context"
        ),
        "evaluation_context": normalize_binding(
            evaluation_context, "authority input evaluation context"
        ),
        "grants": grants,
        "operation_manifests": operation_manifests,
    }
    return identity, _sha256_bytes(_canonical_json(identity))


def _publish_content_addressed(
    root: Path,
    body: dict[str, Any],
    *,
    field: str,
    path_factory: Any,
    label: str,
    max_bytes: int,
) -> tuple[dict[str, Any], dict[str, str], bool]:
    digest = _sha256_bytes(_canonical_json(body))
    value = {**body, field: digest}
    payload = _bounded_payload(_canonical_json(value), max_bytes, label)
    path = path_factory(root, digest)
    created = not path.exists() and not path.is_symlink()
    raw_sha = _write_once(path, payload, label)
    return value, {"ref": path.relative_to(root).as_posix(), "sha256": raw_sha}, created


def publish_projection(
    root: Path, body: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], bool]:
    return _publish_content_addressed(
        root,
        body,
        field="projection_content_sha256",
        path_factory=_successor_authority_projection_path,
        label="selected-successor authority approval projection",
        max_bytes=MAX_OUTCOME_BYTES,
    )


def publish_packet(
    root: Path, body: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str], bool]:
    return _publish_content_addressed(
        root,
        body,
        field="packet_content_sha256",
        path_factory=_successor_authority_packet_path,
        label="selected-successor authority packet",
        max_bytes=MAX_OUTCOME_BYTES,
    )


def packet_candidate(
    root: Path, body: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    digest = _sha256_bytes(_canonical_json(body))
    value = {**body, "packet_content_sha256": digest}
    payload = _bounded_payload(
        _canonical_json(value),
        MAX_OUTCOME_BYTES,
        "selected-successor authority packet",
    )
    path = _successor_authority_packet_path(root, digest)
    return value, {
        "ref": path.relative_to(root).as_posix(),
        "sha256": _sha256_bytes(payload),
    }


def _load_content_addressed(
    root: Path,
    binding_value: Any,
    *,
    keys: set[str],
    kind: str,
    field: str,
    path_factory: Any,
    label: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    binding = normalize_binding(binding_value, label)
    path, raw = read_bound_bytes(
        root, binding, label, max_bytes=MAX_OUTCOME_BYTES
    )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if (
        not isinstance(value, dict)
        or set(value) != keys
        or raw != _canonical_json(value)
        or value.get("schema_version") != 1
        or value.get("artifact_kind") != kind
        or value.get(field) != _content(value, field)
        or path != path_factory(root, value.get(field))
    ):
        raise ValueError(f"{label} integrity failed")
    return binding, value


def load_locator(root: Path, input_sha256: str) -> dict[str, Any] | None:
    path = _successor_authority_locator_path(root, input_sha256)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INDEX_BYTES:
        raise ValueError("Authority packet locator must be a regular file at most 64 KiB")
    with path.open("rb") as handle:
        raw = handle.read(MAX_INDEX_BYTES + 1)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Authority packet locator is unreadable") from exc
    if (
        len(raw) > MAX_INDEX_BYTES
        or not isinstance(value, dict)
        or set(value) != LOCATOR_KEYS
        or raw != _canonical_json(value)
        or value.get("schema_version") != 1
        or value.get("artifact_kind") != "selected_successor_authority_locator"
        or value.get("input_sha256") != input_sha256
        or value.get("locator_content_sha256")
        != _content(value, "locator_content_sha256")
    ):
        raise ValueError("Authority packet locator integrity failed")
    normalize_binding(value.get("packet"), "authority located packet")
    return value


def publish_locator(
    root: Path,
    input_sha256: str,
    packet: dict[str, str],
    operation_manifests: dict[str, dict[str, str]],
) -> bool:
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_locator",
        "input_sha256": input_sha256,
        "packet": normalize_binding(packet, "authority located packet"),
        "operation_manifests": operation_manifests,
    }
    value = {**body, "locator_content_sha256": _content(body, "locator_content_sha256")}
    payload = _bounded_payload(
        _canonical_json(value),
        MAX_INDEX_BYTES,
        "selected-successor authority locator",
    )
    path = _successor_authority_locator_path(root, input_sha256)
    created = not path.exists() and not path.is_symlink()
    _write_once(path, payload, "selected-successor authority locator")
    return created


def load_packet(
    root: Path, binding_value: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    return _load_content_addressed(
        root,
        binding_value,
        keys=PACKET_KEYS,
        kind="selected_successor_authority_packet",
        field="packet_content_sha256",
        path_factory=_successor_authority_packet_path,
        label="selected-successor authority packet",
    )


def load_projection(
    root: Path, binding_value: Any
) -> tuple[dict[str, str], dict[str, Any]]:
    return _load_content_addressed(
        root,
        binding_value,
        keys=PROJECTION_KEYS,
        kind="selected_successor_authority_approval_projection",
        field="projection_content_sha256",
        path_factory=_successor_authority_projection_path,
        label="selected-successor authority projection",
    )


def load_index(
    root: Path, identity: dict[str, Any], input_sha256: str
) -> dict[str, Any] | None:
    path = _successor_authority_index_path(root, input_sha256)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INDEX_BYTES:
        raise ValueError("Authority input index must be a regular file of at most 64 KiB")
    with path.open("rb") as handle:
        raw = handle.read(MAX_INDEX_BYTES + 1)
    if len(raw) > MAX_INDEX_BYTES:
        raise ValueError("Authority input index exceeds 64 KiB")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Authority input index is unreadable") from exc
    expected_identity = {
        key: identity[key]
        for key in (
            "prepared_at",
            "bundle",
            "request_context",
            "evaluation_context",
            "grants",
            "operation_manifests",
        )
    }
    if (
        not isinstance(value, dict)
        or set(value) != INDEX_KEYS
        or raw != _canonical_json(value)
        or value.get("schema_version") != 1
        or value.get("artifact_kind") != "selected_successor_authority_index"
        or value.get("input_sha256") != input_sha256
        or path != _successor_authority_index_path(root, value.get("input_sha256"))
        or any(value.get(key) != item for key, item in expected_identity.items())
        or value.get("outcome_kind") not in {"packet", "approval_projection"}
        or value.get("index_content_sha256")
        != _content(value, "index_content_sha256")
    ):
        raise ValueError("Authority input index integrity failed")
    normalize_binding(value.get("outcome"), "authority indexed outcome")
    return value


def publish_index(
    root: Path,
    identity: dict[str, Any],
    input_sha256: str,
    *,
    outcome_kind: str,
    outcome: dict[str, str],
) -> bool:
    if outcome_kind not in {"packet", "approval_projection"}:
        raise ValueError("Authority indexed outcome kind is invalid")
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_index",
        "input_sha256": input_sha256,
        "prepared_at": identity["prepared_at"],
        "bundle": identity["bundle"],
        "request_context": identity["request_context"],
        "evaluation_context": identity["evaluation_context"],
        "grants": identity["grants"],
        "operation_manifests": identity["operation_manifests"],
        "outcome_kind": outcome_kind,
        "outcome": normalize_binding(outcome, "authority indexed outcome"),
    }
    value = {**body, "index_content_sha256": _content(body, "index_content_sha256")}
    payload = _bounded_payload(
        _canonical_json(value),
        MAX_INDEX_BYTES,
        "selected-successor authority index",
    )
    path = _successor_authority_index_path(root, input_sha256)
    created = not path.exists() and not path.is_symlink()
    _write_once(path, payload, "selected-successor authority index")
    return created


__all__ = (
    "authority_input_identity",
    "load_index",
    "load_locator",
    "load_packet",
    "load_projection",
    "packet_candidate",
    "publish_index",
    "publish_locator",
    "publish_packet",
    "publish_projection",
)
