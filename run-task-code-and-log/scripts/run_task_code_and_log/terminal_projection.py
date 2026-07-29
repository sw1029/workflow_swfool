"""Closed terminal projection for bounded and long-running executions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Any

from .terminal_evidence import verify_projection_evidence


CONTRACT_ID = "run_terminal_projection@v1"
_STATUSES = frozenset({"running", "succeeded", "failed_closed"})
_SHA = re.compile(r"^[0-9a-f]{64}$")
_OPAQUE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,255}$")
_CYCLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class RunTerminalProjectionError(ValueError):
    """Raised when execution evidence could cause an unsafe retry or promotion."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _opaque(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    normalized = str(value or "").strip()
    if not _OPAQUE.fullmatch(normalized):
        raise RunTerminalProjectionError(
            f"{label} must be a bounded opaque identifier"
        )
    return normalized


def _cycle_id(value: Any, label: str = "cycle_id") -> str:
    normalized = str(value or "").strip()
    if not _CYCLE.fullmatch(normalized):
        raise RunTerminalProjectionError(
            f"{label} must be a path-safe cycle identifier"
        )
    return normalized


def _binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"ref", "sha256"}:
        raise RunTerminalProjectionError(f"{label} must be a ref/sha256 binding")
    ref = str(value.get("ref") or "").strip()
    path = PurePosixPath(ref)
    sha = str(value.get("sha256") or "").lower()
    if not ref or path.is_absolute() or ".." in path.parts or "\\" in ref:
        raise RunTerminalProjectionError(f"{label}.ref is unsafe")
    if not _SHA.fullmatch(sha):
        raise RunTerminalProjectionError(f"{label}.sha256 is invalid")
    return {"ref": path.as_posix(), "sha256": sha}


def _read_regular_nofollow(path: Path, label: str) -> bytes:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RunTerminalProjectionError(f"{label} is unavailable") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise RunTerminalProjectionError(f"{label} must be a regular file")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        closed = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        current = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise RunTerminalProjectionError(f"{label} changed while opening") from exc
    opened_identity = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
    )
    closed_identity = (
        closed.st_dev,
        closed.st_ino,
        closed.st_size,
        closed.st_mtime_ns,
    )
    current_identity = (
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
    )
    if (
        not stat.S_ISREG(current.st_mode)
        or opened_identity != closed_identity
        or closed_identity != current_identity
    ):
        raise RunTerminalProjectionError(f"{label} changed while opening")
    return b"".join(chunks)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _artifact_rows(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RunTerminalProjectionError(f"{label} must be a list")
    rows: list[dict[str, Any]] = []
    identities: set[str] = set()
    for index, row in enumerate(value):
        if not isinstance(row, dict) or set(row) != {
            "artifact_id",
            "binding",
            "safety_status",
        }:
            raise RunTerminalProjectionError(f"{label}[{index}] is not closed")
        artifact_id = _opaque(row.get("artifact_id"), f"{label}.artifact_id")
        if artifact_id in identities:
            raise RunTerminalProjectionError(f"{label} contains duplicate artifacts")
        identities.add(str(artifact_id))
        safety = str(row.get("safety_status") or "")
        if safety not in {"safe", "unsafe", "unknown"}:
            raise RunTerminalProjectionError(f"{label} safety status is invalid")
        rows.append(
            {
                "artifact_id": artifact_id,
                "binding": _binding(row.get("binding"), f"{label}.binding"),
                "safety_status": safety,
            }
        )
    return sorted(rows, key=lambda item: str(item["artifact_id"]))


def _artifact_partition(
    value: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    surviving = _artifact_rows(
        value.get("safe_surviving_artifacts"), "safe_surviving_artifacts"
    )
    discarded = _artifact_rows(
        value.get("discarded_artifacts"), "discarded_artifacts"
    )
    surviving_ids = {item["artifact_id"] for item in surviving}
    discarded_ids = {item["artifact_id"] for item in discarded}
    if surviving_ids & discarded_ids:
        raise RunTerminalProjectionError(
            "surviving and discarded artifact identities overlap"
        )
    surviving_bindings = {
        (item["binding"]["ref"], item["binding"]["sha256"])
        for item in surviving
    }
    discarded_bindings = {
        (item["binding"]["ref"], item["binding"]["sha256"])
        for item in discarded
    }
    if surviving_bindings & discarded_bindings:
        raise RunTerminalProjectionError(
            "surviving and discarded artifact bindings overlap"
        )
    if any(item["safety_status"] != "safe" for item in surviving):
        raise RunTerminalProjectionError("only safe artifacts may survive")
    return surviving, discarded


def _normalize(value: dict[str, Any]) -> dict[str, Any]:
    status = str(value.get("status") or "")
    if status not in _STATUSES:
        raise RunTerminalProjectionError("run terminal status is invalid")
    monitor = value.get("monitor")
    harvest = value.get("harvest")
    failure = value.get("failure")
    if not isinstance(monitor, dict) or set(monitor) != {
        "status",
        "monitor_command_id",
        "stop_command_id",
    }:
        raise RunTerminalProjectionError("monitor contract is not closed")
    if not isinstance(harvest, dict) or set(harvest) != {
        "status",
        "evidence_binding",
    }:
        raise RunTerminalProjectionError("harvest contract is not closed")
    monitor_status = str(monitor.get("status") or "")
    harvest_status = str(harvest.get("status") or "")
    if monitor_status not in {"pending", "terminal"}:
        raise RunTerminalProjectionError("monitor status is invalid")
    if harvest_status not in {
        "pending",
        "required",
        "completed",
        "not_required",
        "unavailable",
    }:
        raise RunTerminalProjectionError("harvest status is invalid")
    retry = value.get("retry_policy")
    if not isinstance(retry, dict) or set(retry) != {"automatic_retry"}:
        raise RunTerminalProjectionError("retry_policy is not closed")
    if not isinstance(retry["automatic_retry"], bool):
        raise RunTerminalProjectionError("automatic_retry must be boolean")
    next_action = str(value.get("next_action") or "")
    if next_action not in {
        "monitor",
        "harvest",
        "review",
        "complete",
    }:
        raise RunTerminalProjectionError("next_action is invalid")
    surviving, discarded = _artifact_partition(value)
    if status == "running":
        if (
            monitor_status != "pending"
            or not monitor.get("monitor_command_id")
            or not monitor.get("stop_command_id")
            or harvest_status != "pending"
            or next_action != "monitor"
            or failure is not None
        ):
            raise RunTerminalProjectionError("running projection is incomplete")
    elif status == "succeeded":
        if (
            monitor_status != "terminal"
            or not monitor.get("monitor_command_id")
            or harvest_status != "completed"
            or harvest.get("evidence_binding") is None
            or next_action not in {"complete", "review"}
            or failure is not None
            or retry["automatic_retry"]
        ):
            raise RunTerminalProjectionError("succeeded projection is inconsistent")
    else:
        if (
            monitor_status != "terminal"
            or not monitor.get("monitor_command_id")
            or harvest_status not in {"required", "completed", "unavailable"}
            or (
                harvest_status == "completed"
                and harvest.get("evidence_binding") is None
            )
            or not isinstance(failure, dict)
            or set(failure) != {"reason", "evidence_binding"}
            or retry["automatic_retry"]
            or next_action != "review"
        ):
            raise RunTerminalProjectionError("failed_closed projection is unsafe")
    normalized_failure = (
        {
            "reason": _opaque(failure.get("reason"), "failure.reason"),
            "evidence_binding": _binding(
                failure.get("evidence_binding"), "failure.evidence_binding"
            ),
        }
        if isinstance(failure, dict)
        else None
    )
    return {
        "contract_id": CONTRACT_ID,
        "cycle_id": _cycle_id(value.get("cycle_id")),
        "run_id": _opaque(value.get("run_id"), "run_id"),
        "status": status,
        "terminal": status != "running",
        "monitor": {
            "status": monitor_status,
            "monitor_command_id": _opaque(
                monitor.get("monitor_command_id"),
                "monitor_command_id",
                nullable=status != "running",
            ),
            "stop_command_id": _opaque(
                monitor.get("stop_command_id"),
                "stop_command_id",
                nullable=status != "running",
            ),
        },
        "harvest": {
            "status": harvest_status,
            "evidence_binding": (
                _binding(harvest.get("evidence_binding"), "harvest.evidence_binding")
                if harvest.get("evidence_binding") is not None
                else None
            ),
        },
        "safe_surviving_artifacts": surviving,
        "discarded_artifacts": discarded,
        "failure": normalized_failure,
        "next_action": next_action,
        "retry_policy": {"automatic_retry": retry["automatic_retry"]},
    }


def build_run_terminal_projection(**fields: Any) -> dict[str, Any]:
    normalized = _normalize({"contract_id": CONTRACT_ID, **fields})
    normalized["projection_id"] = f"run-terminal-{_digest(normalized)[:32]}"
    return validate_run_terminal_projection(normalized)


def validate_run_terminal_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RunTerminalProjectionError("run terminal projection must be an object")
    fields = {
        "contract_id",
        "projection_id",
        "cycle_id",
        "run_id",
        "status",
        "terminal",
        "monitor",
        "harvest",
        "safe_surviving_artifacts",
        "discarded_artifacts",
        "failure",
        "next_action",
        "retry_policy",
    }
    if set(value) != fields or value.get("contract_id") != CONTRACT_ID:
        raise RunTerminalProjectionError("run terminal projection is not closed")
    normalized = _normalize(value)
    expected = f"run-terminal-{_digest(normalized)[:32]}"
    if value.get("projection_id") != expected:
        raise RunTerminalProjectionError("run terminal projection digest mismatch")
    if value.get("terminal") != normalized["terminal"]:
        raise RunTerminalProjectionError("run terminal flag is inconsistent")
    return {**normalized, "projection_id": expected}


def reopen_run_terminal_projection(
    root: str | Path,
    value: Any,
    binding: Any,
    *,
    expected_cycle_id: str | None = None,
) -> dict[str, Any]:
    """Reopen one projection from its fixed producer CAS without following links."""

    projection = validate_run_terminal_projection(value)
    if (
        expected_cycle_id is not None
        and projection["cycle_id"] != _cycle_id(
            expected_cycle_id, "expected_cycle_id"
        )
    ):
        raise RunTerminalProjectionError(
            "run terminal projection belongs to another cycle"
        )
    normalized_binding = _binding(binding, "run terminal projection binding")
    expected_ref = (
        ".agent_log/run-terminal-projections/"
        f"{projection['projection_id']}.json"
    )
    if normalized_binding["ref"] != expected_ref:
        raise RunTerminalProjectionError(
            "run terminal projection is outside its producer CAS"
        )
    workspace = Path(root).resolve(strict=True)
    log_root = workspace / ".agent_log"
    directory = log_root / "run-terminal-projections"
    path = workspace / expected_ref
    if log_root.is_symlink() or directory.is_symlink() or path.is_symlink():
        raise RunTerminalProjectionError(
            "run terminal projection CAS must not contain symlinks"
        )
    if not directory.is_dir() or not directory.resolve().is_relative_to(workspace):
        raise RunTerminalProjectionError(
            "run terminal projection CAS is unavailable"
        )
    payload = _read_regular_nofollow(path, "run terminal projection artifact")
    expected_payload = _canonical(projection) + b"\n"
    if (
        payload != expected_payload
        or hashlib.sha256(payload).hexdigest() != normalized_binding["sha256"]
    ):
        raise RunTerminalProjectionError(
            "run terminal projection binding does not match producer bytes"
        )
    verify_projection_evidence(workspace, projection)
    return {"projection": projection, "binding": normalized_binding}


def publish_run_terminal_projection(
    root: str | Path, value: Any
) -> dict[str, Any]:
    """Publish canonical projection bytes at one producer-owned CAS path."""

    projection = validate_run_terminal_projection(value)
    workspace = Path(root).resolve(strict=True)
    verify_projection_evidence(workspace, projection)
    log_root = workspace / ".agent_log"
    directory = log_root / "run-terminal-projections"
    if log_root.is_symlink() or directory.is_symlink():
        raise RunTerminalProjectionError(
            "terminal projection directory must not be a symlink"
        )
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.resolve().is_relative_to(workspace):
        raise RunTerminalProjectionError(
            "terminal projection directory escapes the workspace"
        )
    path = directory / f"{projection['projection_id']}.json"
    if path.is_symlink():
        raise RunTerminalProjectionError(
            "terminal projection target must not be a symlink"
        )
    payload = _canonical(projection) + b"\n"
    created = False
    if path.exists() or path.is_symlink():
        existing = _read_regular_nofollow(
            path, "terminal projection CAS target"
        )
        if existing != payload:
            raise RunTerminalProjectionError(
                "terminal projection CAS path contains different bytes"
            )
    else:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".run-terminal-", dir=directory
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path, follow_symlinks=False)
                created = True
            except FileExistsError:
                existing = _read_regular_nofollow(
                    path, "terminal projection CAS target"
                )
                if existing != payload:
                    raise RunTerminalProjectionError(
                        "terminal projection CAS target appeared with different bytes"
                    )
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        _fsync_directory(directory)
    return {
        "projection": projection,
        "binding": {
            "ref": path.relative_to(workspace).as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
        "created": created,
    }


__all__ = (
    "CONTRACT_ID",
    "RunTerminalProjectionError",
    "build_run_terminal_projection",
    "publish_run_terminal_projection",
    "reopen_run_terminal_projection",
    "validate_run_terminal_projection",
)
