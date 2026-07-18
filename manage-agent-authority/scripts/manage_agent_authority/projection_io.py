from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .canonical import resolve_workspace_path
from .contracts import validate_grant
from .projection_contracts import AUTHORIZATION_ROOT
from .projection_contracts import BINDING_KEYS
from .projection_contracts import CHANGE_KEYS
from .projection_contracts import GRANT_STATUSES
from .projection_contracts import GRANT_STATE_KEYS
from .projection_contracts import GRANT_USE_KEYS
from .projection_contracts import MAX_INTENT_BYTES
from .projection_contracts import RESERVATION_STATE_KEYS
from .projection_contracts import RESERVATION_STATUSES
from .projection_contracts import STATE_ROOT
from .projection_contracts import closed
from .projection_contracts import identifier
from .projection_contracts import nonnegative_int
from .projection_contracts import positive_int
from .projection_contracts import sha
from .stable_store import read_regular


def _stable_file_bytes(root: Path, path: Path, label: str, *, max_bytes: int) -> bytes:
    root = root.resolve()
    try:
        ref = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise SystemExit(f"{label} escapes the workspace.") from exc
    resolved = resolve_workspace_path(root, ref, label)
    data = read_regular(resolved, label=label)
    assert data is not None
    if len(data) > max_bytes:
        raise SystemExit(f"{label} exceeds the {max_bytes}-byte safety limit.")
    return data


def _stable_file_digest(root: Path, path: Path, label: str) -> str:
    root = root.resolve()
    try:
        ref = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise SystemExit(f"{label} escapes the workspace.") from exc
    resolved = resolve_workspace_path(root, ref, label)
    data = read_regular(resolved, label=label)
    assert data is not None
    return hashlib.sha256(data).hexdigest()


def safe_json(
    root: Path, path: Path, label: str, *, max_bytes: int = MAX_INTENT_BYTES
) -> tuple[dict[str, Any], str]:
    data = _stable_file_bytes(root, path, label, max_bytes=max_bytes)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} is not readable UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object.")
    return value, hashlib.sha256(data).hexdigest()


def safe_owned_directory(root: Path, relative: Path, label: str) -> Path | None:
    """Resolve an optional owned directory without following any symlink component."""
    if relative.is_absolute() or ".." in relative.parts:
        raise SystemExit(f"{label} path is not workspace-relative.")
    current = root.resolve()
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise SystemExit(f"{label} must not traverse a symlink directory.")
        if not current.exists():
            return None
        if not current.is_dir():
            raise SystemExit(f"{label} must be a regular directory.")
    return current


def binding(value: Any, label: str) -> dict[str, str]:
    raw = closed(value, BINDING_KEYS, label)
    ref = str(raw["ref"] or "").strip()
    if not ref or Path(ref).is_absolute() or ".." in Path(ref).parts or "*" in ref:
        raise SystemExit(f"{label}.ref must be an exact workspace-relative path.")
    return {"ref": ref, "sha256": sha(raw["sha256"], f"{label}.sha256")}


def verify_file_binding(
    root: Path, value: Any, label: str
) -> tuple[dict[str, str], Path]:
    normalized = binding(value, label)
    path = resolve_workspace_path(root, normalized["ref"], f"{label}.ref")
    if _stable_file_digest(root, path, f"{label}.ref") != normalized["sha256"]:
        raise SystemExit(f"{label} digest does not match its bound artifact.")
    return normalized, path


def expected_path(root: Path, path: Path, relative: Path, label: str) -> None:
    expected = (root.resolve() / relative).resolve(strict=False)
    if path.resolve(strict=False) != expected:
        raise SystemExit(f"{label} is not stored at its deterministic path.")


def load_bound_json(
    root: Path,
    value: Any,
    label: str,
    *,
    expected_relative: Path | None = None,
) -> tuple[dict[str, Any], Path, dict[str, str]]:
    normalized = binding(value, label)
    path = resolve_workspace_path(root, normalized["ref"], f"{label}.ref")
    if expected_relative is not None:
        expected_path(root, path, expected_relative, label)
    artifact, digest = safe_json(root, path, label)
    if digest != normalized["sha256"]:
        raise SystemExit(f"{label} digest does not match its bound artifact.")
    return artifact, path, normalized


def load_grant_artifact(root: Path, grant_id: str) -> tuple[dict[str, Any], str]:
    grant_id = identifier(grant_id, "grant_id")
    relative = AUTHORIZATION_ROOT / "grants" / f"{grant_id}.json"
    path = resolve_workspace_path(root, relative.as_posix(), "authority grant")
    raw, digest = safe_json(root, path, "authority grant")
    grant = validate_grant(raw)
    if grant["grant_id"] != grant_id:
        raise SystemExit("Authority grant identity does not match its path.")
    return grant, digest


def validate_grant_state(
    value: Any, grant: dict[str, Any], digest: str, label: str
) -> dict[str, Any]:
    state = closed(value, GRANT_STATE_KEYS, label)
    if (
        state["schema_version"] != 2
        or state["artifact_kind"] != "authority_grant_state"
        or state["grant_id"] != grant["grant_id"]
        or state["grant_sha256"] != digest
        or state["status"] not in GRANT_STATUSES
    ):
        raise SystemExit(f"{label} identity or contract is invalid.")
    remaining = state["remaining_uses"]
    if remaining is not None:
        remaining = nonnegative_int(remaining, f"{label}.remaining_uses")
    reserved = nonnegative_int(state["reserved_uses"], f"{label}.reserved_uses")
    consumed = nonnegative_int(state["consumed_uses"], f"{label}.consumed_uses")
    nonnegative_int(state["version"], f"{label}.version")
    if state["last_event_id"] is not None:
        identifier(state["last_event_id"], f"{label}.last_event_id")
    max_uses = grant["max_uses"]
    if max_uses is None:
        if remaining is not None:
            raise SystemExit(f"{label} must keep an unbounded remaining-use marker.")
    elif remaining is None or remaining + consumed != max_uses or reserved > remaining:
        raise SystemExit(f"{label} use accounting is invalid.")
    if state["status"] == "exhausted" and remaining != 0:
        raise SystemExit(f"{label} exhausted status does not match its budget.")
    if state["status"] in {"active", "suspended"} and remaining == 0:
        raise SystemExit(f"{label} live status has no remaining budget.")
    return state


def validate_reservation_state(
    value: Any, reservation_id: str, label: str
) -> dict[str, Any]:
    state = closed(value, RESERVATION_STATE_KEYS, label)
    if (
        state["schema_version"] != 2
        or state["artifact_kind"] != "authority_reservation_state"
        or state["reservation_id"] != reservation_id
        or state["status"] not in RESERVATION_STATUSES
    ):
        raise SystemExit(f"{label} identity or contract is invalid.")
    nonnegative_int(state["version"], f"{label}.version")
    identifier(state["last_event_id"], f"{label}.last_event_id")
    return state


def intent_changes(
    root: Path, artifact: dict[str, Any], path: Path
) -> list[dict[str, Any]]:
    changes = artifact.get("state_changes")
    if not isinstance(changes, list) or not changes:
        raise SystemExit(f"Authority intent has no recoverable state_changes: {path}")
    refs: set[str] = set()
    normalized: list[dict[str, Any]] = []
    boundary = (root.resolve() / STATE_ROOT).resolve()
    for index, raw in enumerate(changes):
        change = closed(raw, CHANGE_KEYS, f"authority intent {path} change {index}")
        ref = str(change["ref"] or "").strip()
        target = resolve_workspace_path(
            root,
            ref,
            f"authority intent {path} change {index}.ref",
            must_exist=False,
        )
        try:
            target.relative_to(boundary)
        except ValueError as exc:
            raise SystemExit("Projection recovery escapes the state boundary.") from exc
        if ref != target.relative_to(root.resolve()).as_posix():
            raise SystemExit("Projection recovery reference is not normalized.")
        if ref in refs:
            raise SystemExit(f"Authority intent contains a duplicate state ref: {ref}")
        refs.add(ref)
        if change["before"] is not None and not isinstance(change["before"], dict):
            raise SystemExit(
                f"Authority intent {path} change {index} before is invalid."
            )
        if not isinstance(change["after"], dict):
            raise SystemExit(
                f"Authority intent {path} change {index} after is invalid."
            )
        normalized.append(
            {"ref": ref, "before": change["before"], "after": change["after"]}
        )
    return normalized


def changes_by_ref(changes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {change["ref"]: change for change in changes}


def grant_use(value: Any, label: str) -> dict[str, Any]:
    use = closed(value, GRANT_USE_KEYS, label)
    grant_id = identifier(use["grant_id"], f"{label}.grant_id")
    digest = sha(use["grant_sha256"], f"{label}.grant_sha256")
    units = positive_int(use["units"], f"{label}.units")
    before = nonnegative_int(
        use["state_version_before"], f"{label}.state_version_before"
    )
    after = nonnegative_int(use["state_version_after"], f"{label}.state_version_after")
    if after != before + 1:
        raise SystemExit(f"{label} state versions are not contiguous.")
    return {
        "grant_id": grant_id,
        "grant_sha256": digest,
        "units": units,
        "state_version_before": before,
        "state_version_after": after,
    }
