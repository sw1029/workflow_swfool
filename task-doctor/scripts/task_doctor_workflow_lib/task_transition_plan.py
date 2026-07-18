"""Closed public contract for one prospective canonical task transition."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from .common import (
    HEX64,
    SAFE_ID,
    WorkflowError,
    expect_keys,
    require,
    sha256_file,
    sha256_json,
)


PLAN_KIND = "task_transition_plan"
PLAN_SCHEMA_VERSION = 1
TRANSITION_KINDS = {
    "initial_task",
    "replace_task",
    "retarget_task",
}
OPERATION_IDENTITY = {
    "skill_id": "task-doctor",
    "skill_version": "2.2.0",
    "operation_id": "mutate_task_scope",
    "operation_version": "1",
    "effect_class": "retarget_or_replace_task",
}
def _canonical_prospective_ref(value: Any, transition_id: str) -> str:
    require(isinstance(value, str) and bool(value), "invalid_owner_plan",
            "prospective_task.ref must be non-empty")
    candidate = PurePosixPath(value)
    parts = candidate.parts
    require(
        not candidate.is_absolute()
        and len(parts) == 4
        and parts[:3] == (".task", "task_doctor", "prospective")
        and parts[3] == f"{transition_id}.md"
        and candidate.as_posix() == value,
        "invalid_owner_plan",
        "prospective task must use .task/task_doctor/prospective/<transition-id>.md",
    )
    return value


def _digest(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    require(isinstance(value, str) and HEX64.fullmatch(value) is not None,
            "invalid_owner_plan", f"{label} must be a lowercase SHA-256 digest")
    return value


def validate_task_transition_plan(plan: Any) -> dict[str, Any]:
    """Validate the body-safe immutable task transition plan shape."""

    require(isinstance(plan, dict), "invalid_owner_plan",
            "task transition plan must be an object")
    expect_keys(
        plan,
        {
            "schema_version", "plan_kind", "transition_id", "transition_kind",
            "operation_identity", "before_task", "prospective_task", "after_task",
            "archive_task", "plan_sha256",
        },
        set(),
        "task transition plan",
        "invalid_owner_plan",
    )
    require(plan["schema_version"] == PLAN_SCHEMA_VERSION
            and plan["plan_kind"] == PLAN_KIND, "invalid_owner_plan",
            "unsupported task transition plan contract")
    transition_id = plan["transition_id"]
    require(isinstance(transition_id, str) and SAFE_ID.fullmatch(transition_id),
            "invalid_owner_plan", "task transition_id is invalid")
    require(plan["transition_kind"] in TRANSITION_KINDS, "invalid_owner_plan",
            "task transition_kind is invalid")
    operation = plan["operation_identity"]
    require(isinstance(operation, dict), "invalid_owner_plan",
            "task transition operation_identity must be an object")
    expect_keys(operation, set(OPERATION_IDENTITY), set(), "operation_identity",
                "invalid_owner_plan")
    require(operation == OPERATION_IDENTITY, "invalid_owner_plan",
            "task transition operation identity mismatch")

    before = plan["before_task"]
    prospective = plan["prospective_task"]
    after = plan["after_task"]
    archive = plan["archive_task"]
    for value, required, label in (
        (before, {"ref", "exists", "sha256"}, "before_task"),
        (prospective, {"ref", "sha256"}, "prospective_task"),
        (after, {"ref", "sha256"}, "after_task"),
    ):
        require(isinstance(value, dict), "invalid_owner_plan", f"{label} must be an object")
        expect_keys(value, required, set(), label, "invalid_owner_plan")
    require(before["ref"] == "task.md" and after["ref"] == "task.md",
            "invalid_owner_plan", "task transition canonical ref must be task.md")
    require(isinstance(before["exists"], bool), "invalid_owner_plan",
            "before_task.exists must be boolean")
    before_digest = _digest(before["sha256"], "before_task.sha256", nullable=True)
    require((before_digest is not None) == before["exists"], "invalid_owner_plan",
            "before task existence and digest are inconsistent")
    require((plan["transition_kind"] == "initial_task") is (not before["exists"]),
            "invalid_owner_plan",
            "initial_task requires an absent before task; all other transitions "
            "require an existing before task")
    _canonical_prospective_ref(prospective["ref"], transition_id)
    prospective_digest = _digest(prospective["sha256"], "prospective_task.sha256")
    after_digest = _digest(after["sha256"], "after_task.sha256")
    require(prospective_digest == after_digest, "invalid_owner_plan",
            "prospective and canonical after-task digests must match")
    require(isinstance(archive, dict), "invalid_owner_plan",
            "archive_task must be an object")
    expect_keys(archive, {"required", "ref", "sha256"}, set(), "archive_task",
                "invalid_owner_plan")
    require(archive["required"] is before["exists"], "invalid_owner_plan",
            "archive_task.required must match before-task existence")
    if archive["required"]:
        expected_ref = (
            f".task/task_doctor/transitions/archives/{transition_id}.md"
        )
        require(archive["ref"] == expected_ref, "invalid_owner_plan",
                "archive_task ref is not the deterministic transition archive")
        require(_digest(archive["sha256"], "archive_task.sha256") == before_digest,
                "invalid_owner_plan",
                "archive_task must preserve the exact predecessor task bytes")
    else:
        require(archive == {"required": False, "ref": None, "sha256": None},
                "invalid_owner_plan",
                "an initial task transition cannot declare an archive")
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    require(plan["plan_sha256"] == sha256_json(body), "invalid_owner_plan",
            "task transition plan digest mismatch")
    return plan


def _strict_regular(root: Path, ref: str, label: str) -> Path:
    current = root.resolve()
    for part in PurePosixPath(ref).parts:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError as error:
            raise WorkflowError(
                "stale_owner_plan", f"{label} is missing: {ref}"
            ) from error
        require(not stat.S_ISLNK(mode), "invalid_owner_plan",
                f"{label} must not traverse symlinks: {ref}")
    require(stat.S_ISREG(os.lstat(current).st_mode), "invalid_owner_plan",
            f"{label} must be a regular file: {ref}")
    return current


def verify_task_transition_plan(root: Path, plan: Any) -> dict[str, Any]:
    """Reopen exact before/prospective bytes at prepare and pre-dispatch time."""

    normalized = validate_task_transition_plan(plan)
    root = root.resolve()
    canonical = root / "task.md"
    before = normalized["before_task"]
    if before["exists"]:
        current = _strict_regular(root, "task.md", "before task")
        require(sha256_file(current) == before["sha256"], "stale_owner_plan",
                "canonical task bytes changed after task transition planning")
    else:
        require(not canonical.exists() and not canonical.is_symlink(), "stale_owner_plan",
                "canonical task appeared after task transition planning")
    prospective = _strict_regular(
        root, normalized["prospective_task"]["ref"], "prospective task"
    )
    require(sha256_file(prospective) == normalized["prospective_task"]["sha256"],
            "stale_owner_plan", "prospective task bytes changed after planning")
    return normalized


def build_task_transition_plan(
    root: Path, transition_id: str, transition_kind: str, prospective_ref: str,
) -> dict[str, Any]:
    """Build the closed plan from current canonical and staged prospective bytes."""

    root = root.resolve()
    _canonical_prospective_ref(prospective_ref, transition_id)
    prospective = _strict_regular(root, prospective_ref, "prospective task")
    canonical = root / "task.md"
    if canonical.exists() or canonical.is_symlink():
        current = _strict_regular(root, "task.md", "before task")
        before = {"ref": "task.md", "exists": True, "sha256": sha256_file(current)}
    else:
        before = {"ref": "task.md", "exists": False, "sha256": None}
    digest = sha256_file(prospective)
    body = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_kind": PLAN_KIND,
        "transition_id": transition_id,
        "transition_kind": transition_kind,
        "operation_identity": dict(OPERATION_IDENTITY),
        "before_task": before,
        "prospective_task": {"ref": prospective_ref, "sha256": digest},
        "after_task": {"ref": "task.md", "sha256": digest},
        "archive_task": (
            {
                "required": True,
                "ref": (
                    ".task/task_doctor/transitions/archives/"
                    f"{transition_id}.md"
                ),
                "sha256": before["sha256"],
            }
            if before["exists"]
            else {"required": False, "ref": None, "sha256": None}
        ),
    }
    plan = {**body, "plan_sha256": sha256_json(body)}
    return validate_task_transition_plan(plan)


__all__ = [
    "build_task_transition_plan",
    "validate_task_transition_plan",
    "verify_task_transition_plan",
]
