from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
KIND = "task_doctor_workflow_journal"
PLAN_KIND = "task_doctor_workflow_plan"
MODES = {"execute_with_declared_authorization", "consolidated_review"}
GIT_STATES = {"requested", "deferred", "not_applicable"}
RESOLUTIONS = {
    "authority_not_applicable",
    "already_covered",
    "already_settled",
    "needs_user_approval",
    "ready_to_resume",
    "projection_repair",
    "effect_reconciliation",
    "plan_changed",
    "blocked_by_defect",
}
DISPATCHABLE = {"authority_not_applicable", "ready_to_resume", "projection_repair"}
FORBIDDEN_EFFECTS = {
    "implementation",
    "goal_truth_change",
    "risk_acceptance",
    "external_input",
    "design_selection",
    "remote_push",
    "destructive_change",
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SKILL_ID = re.compile(r"^\$?[a-z0-9][a-z0-9-]{0,127}$")


class WorkflowError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        user_action_required: bool = False,
        next_action: str = "inspect_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.user_action_required = user_action_required
        self.next_action = next_action
        self.details = details or {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, code: str, message: str, **kwargs: Any) -> None:
    if not condition:
        raise WorkflowError(code, message, **kwargs)


def expect_keys(
    value: dict[str, Any], required: set[str], optional: set[str], label: str,
    code: str = "invalid_plan",
) -> None:
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required - optional)
    require(not missing, code, f"{label} is missing keys: {missing}")
    require(not unknown, code, f"{label} has unknown keys: {unknown}")


def validate_hex(value: Any, label: str) -> str:
    require(isinstance(value, str) and HEX64.fullmatch(value) is not None,
            "invalid_evidence", f"{label} must be a lowercase sha256 digest")
    return value


def validate_nonempty(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()),
            "invalid_plan", f"{label} must be a non-empty string")
    return value.strip()


def read_json(path: Path, code: str = "invalid_json") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise WorkflowError("file_not_found", f"file not found: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowError(code, f"cannot read JSON from {path}: {error}") from error
    require(isinstance(value, dict), code, f"JSON root must be an object: {path}")
    return value


def workspace_regular_file(root: Path, ref: str, label: str) -> Path:
    validate_nonempty(ref, f"{label}.ref")
    candidate = Path(ref)
    require(not candidate.is_absolute(), "invalid_evidence",
            f"{label}.ref must be workspace-relative")
    require(candidate.as_posix() == ref, "invalid_evidence",
            f"{label}.ref must use one canonical POSIX workspace-relative spelling")
    require(all(part not in {"", ".", ".."} for part in candidate.parts),
            "invalid_evidence", f"{label}.ref must not contain dot segments")
    root = root.resolve()
    current = root
    for offset, part in enumerate(candidate.parts):
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError as error:
            raise WorkflowError("evidence_not_found",
                                f"{label} does not exist: {ref}") from error
        leaf = offset == len(candidate.parts) - 1
        require(not stat.S_ISLNK(mode), "invalid_evidence",
                f"{label} must not traverse a symlink component")
        require(stat.S_ISREG(mode) if leaf else stat.S_ISDIR(mode),
                "invalid_evidence",
                f"{label} must traverse directories to one regular file")
    return current


def workspace_file(root: Path, ref: str, digest: str, label: str) -> Path:
    validate_hex(digest, f"{label}.sha256")
    resolved = workspace_regular_file(root, ref, label)
    observed = sha256_file(resolved)
    require(observed == digest, "evidence_digest_mismatch",
            f"{label} digest differs from the workspace file",
            details={"expected": digest, "observed": observed, "ref": ref})
    return resolved
