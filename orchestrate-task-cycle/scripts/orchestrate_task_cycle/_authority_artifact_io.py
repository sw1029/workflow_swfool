"""Safe path resolution and byte reopening for authority artifacts."""

from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path, PurePosixPath
from typing import Any


MAX_ARTIFACT_BYTES = 4 * 1024 * 1024


def authority_binding(ref: object, digest: object) -> dict[str, object]:
    return {"ref": ref, "sha256": digest}


def artifact_finding(
    code: str,
    message: str,
    label: str,
    reason: str | None = None,
) -> dict[str, Any]:
    evidence = {"artifact": label}
    if reason:
        evidence["reason"] = reason
    return {"code": code, "message": message, "evidence": evidence}


def workspace_root_from_metadata(metadata: dict[str, Any] | None) -> Path | None:
    """Return an explicit existing workspace root; never default to cwd."""

    metadata = metadata if isinstance(metadata, dict) else {}
    contract = metadata.get("contract_context")
    contexts = (contract if isinstance(contract, dict) else {}, metadata)
    raw = next(
        (
            context.get(key)
            for context in contexts
            for key in ("workspace_root", "workspace", "root")
            if isinstance(context.get(key), (str, Path))
            and str(context.get(key)).strip()
        ),
        None,
    )
    if raw is None:
        return None
    path = Path(raw).expanduser()
    try:
        if path.is_symlink():
            return None
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


def safe_authority_path(
    root: Path,
    ref: object,
    expected_ref: str | None = None,
    *,
    authorization_only: bool = True,
) -> tuple[Path | None, str | None]:
    if not isinstance(ref, str) or ref != ref.strip() or "\\" in ref or "\x00" in ref:
        return None, "malformed_ref"
    pure = PurePosixPath(ref)
    if (
        pure.is_absolute()
        or pure.as_posix() != ref
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        return None, "unsafe_ref"
    if expected_ref is not None and ref != expected_ref:
        return None, "unexpected_ref"
    if authorization_only and pure.parts[:2] != (".task", "authorization"):
        return None, "outside_authorization_store"
    current = root
    try:
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                return None, "symlink"
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
        mode = current.lstat().st_mode
    except (OSError, ValueError):
        return None, "missing_or_escaped"
    if resolved != current or not stat.S_ISREG(mode):
        return None, "not_regular"
    try:
        if current.stat().st_size > MAX_ARTIFACT_BYTES:
            return None, "oversized"
    except OSError:
        return None, "unreadable"
    return current, None


def read_bound_bytes(
    root: Path,
    binding: object,
    label: str,
    findings: list[dict[str, Any]],
    *,
    expected_ref: str | None = None,
    authorization_only: bool = True,
) -> bytes | None:
    if not isinstance(binding, dict) or set(binding) != {"ref", "sha256"}:
        findings.append(
            artifact_finding(
                "authority_artifact_binding_invalid",
                "Authority artifact binding must contain exact ref and sha256.",
                label,
            )
        )
        return None
    path, reason = safe_authority_path(
        root,
        binding.get("ref"),
        expected_ref,
        authorization_only=authorization_only,
    )
    if path is None:
        findings.append(
            artifact_finding(
                "authority_artifact_path_unsafe",
                "Authority artifacts must be exact workspace-relative "
                "non-symlink regular files.",
                label,
                reason,
            )
        )
        return None
    try:
        observed = path.read_bytes()
    except OSError:
        findings.append(
            artifact_finding(
                "authority_artifact_unreadable",
                "Authority artifact could not be reopened.",
                label,
            )
        )
        return None
    digest = hashlib.sha256(observed).hexdigest()
    if digest != binding.get("sha256"):
        findings.append(
            artifact_finding(
                "authority_artifact_content_drift",
                "Authority artifact bytes do not match the bound SHA-256.",
                label,
            )
        )
        return None
    return observed


def read_bound_json(
    root: Path,
    binding: object,
    label: str,
    findings: list[dict[str, Any]],
    *,
    expected_ref: str | None = None,
    authorization_only: bool = True,
) -> dict[str, Any] | None:
    observed = read_bound_bytes(
        root,
        binding,
        label,
        findings,
        expected_ref=expected_ref,
        authorization_only=authorization_only,
    )
    if observed is None:
        return None
    try:
        value = json.loads(observed)
    except (UnicodeDecodeError, json.JSONDecodeError):
        findings.append(
            artifact_finding(
                "authority_artifact_json_invalid",
                "Authority owner artifact must contain a JSON object.",
                label,
            )
        )
        return None
    if not isinstance(value, dict):
        findings.append(
            artifact_finding(
                "authority_artifact_json_invalid",
                "Authority owner artifact must contain a JSON object.",
                label,
            )
        )
        return None
    return value


__all__ = (
    "MAX_ARTIFACT_BYTES",
    "artifact_finding",
    "authority_binding",
    "read_bound_bytes",
    "read_bound_json",
    "safe_authority_path",
    "workspace_root_from_metadata",
)
