"""Derive conservative optional-stage facts from one sealed stage context."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


_CODE_SUFFIXES = frozenset(
    {
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".go",
        ".java",
        ".js",
        ".jsx",
        ".kt",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scala",
        ".swift",
        ".ts",
        ".tsx",
    }
)
_POSITIVE = frozenset(
    {
        "apply",
        "build",
        "changed",
        "needed",
        "plan",
        "required",
        "true",
        "yes",
    }
)
_NEGATIVE = frozenset(
    {
        "false",
        "no",
        "none",
        "not_applicable",
        "not_needed",
        "not_required",
        "skipped",
        "unchanged",
    }
)


def _steps(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cycle = model.get("cycle")
    rows = cycle.get("steps") if isinstance(cycle, dict) else None
    return {
        str(key): value
        for key, value in (rows or {}).items()
        if isinstance(value, dict)
    }


def _scalar(
    steps: dict[str, dict[str, Any]], step: str, field: str
) -> Any:
    row = steps.get(step) or {}
    values = row.get("decision_scalars")
    return values.get(field) if isinstance(values, dict) else None


def _closed_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    normalized = str(value or "").strip().lower().replace("-", "_")
    if normalized in _POSITIVE:
        return True
    if normalized in _NEGATIVE:
        return False
    return None


def _git_paths(model: dict[str, Any]) -> tuple[list[str], bool]:
    git = model.get("git")
    if not isinstance(git, dict):
        return [], False
    identity = git.get("worktree_identity")
    changed = git.get("changed_paths")
    if (
        not isinstance(identity, dict)
        or identity.get("binding_status") != "exact"
        or not isinstance(changed, dict)
        or changed.get("truncated") is True
        or changed.get("included_count") != changed.get("total_count")
        or not isinstance(changed.get("items"), list)
    ):
        return [], False
    paths = [str(item) for item in changed["items"] if isinstance(item, str)]
    return paths, len(paths) == int(changed.get("total_count") or 0)


def _path_has(path: str, tokens: tuple[str, ...]) -> bool:
    lowered = path.lower()
    return any(token in lowered for token in tokens)


def _adapter_path(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return (
        name in {"agents.md", "skill.md", "authority.operations.json"}
        or _path_has(path, ("/.codex/", "/adapters/", "repo_skill_adapter"))
    )


def _code_path(path: str) -> bool:
    lowered = path.lower()
    if lowered.startswith((".task/", "docs/", "tests/")):
        return False
    return PurePosixPath(lowered).suffix in _CODE_SUFFIXES


def _schema_path(path: str) -> bool:
    lowered = path.lower()
    return (
        lowered.startswith((".schema/", ".contract/", "migrations/"))
        or _path_has(lowered, ("/schema/", "/schemas/", "/migrations/"))
        or PurePosixPath(lowered).suffix in {".sql", ".proto"}
    )


def _validation_set_fact(steps: dict[str, dict[str, Any]]) -> bool | None:
    return _closed_bool(
        _scalar(steps, "validation_set_plan", "validation_set_need")
    )


def _user_visible_fact(
    steps: dict[str, dict[str, Any]]
) -> bool | None:
    values = (
        _scalar(steps, "qualitative_review", "produced_domain_delta"),
        _scalar(steps, "qualitative_review", "changed_vs_previous"),
        _scalar(steps, "qualitative_review", "output_delta_status"),
    )
    normalized = [_closed_bool(value) for value in values if value is not None]
    if any(value is True for value in normalized):
        return True
    if normalized and all(value is False for value in normalized):
        return False
    return None


def _friction_fact(steps: dict[str, dict[str, Any]]) -> bool | None:
    loopback = steps.get("loopback_audit")
    if not loopback:
        return None
    count = _scalar(
        steps, "loopback_audit", "same_family_micro_hardening_count"
    )
    if isinstance(count, int) and not isinstance(count, bool) and count >= 2:
        return True
    if _closed_bool(_scalar(steps, "loopback_audit", "hard_stop_required")):
        return True
    disposition = str(
        _scalar(steps, "loopback_audit", "recommended_disposition") or ""
    ).lower()
    if disposition in {"escalate", "hard_stop", "retarget", "stop"}:
        return True
    if loopback.get("status") in {"complete", "completed", "passed", "success"}:
        return False
    return None


def _issue_fact(steps: dict[str, dict[str, Any]]) -> bool | None:
    validation = steps.get("validate")
    if not validation:
        return None
    blockers = validation.get("blockers")
    if isinstance(blockers, list) and blockers:
        return True
    verdict = str(
        _scalar(steps, "validate", "validation_verdict") or ""
    ).lower()
    if verdict in {"blocked", "fail", "failed", "rejected"}:
        return True
    if verdict in {"pass", "passed", "success", "valid"}:
        return False
    return None


def derive_applicability_facts(model: dict[str, Any]) -> dict[str, bool | None]:
    """Resolve absence only when its source projection is exact and complete."""

    steps = _steps(model)
    paths, git_exact = _git_paths(model)
    return {
        "needs_validation_set": _validation_set_fact(steps),
        "adapter_changed": (
            any(_adapter_path(path) for path in paths) if git_exact else None
        ),
        "code_surface_changed": (
            any(_code_path(path) for path in paths) if git_exact else None
        ),
        "user_visible_delta": _user_visible_fact(steps),
        "repeated_friction": _friction_fact(steps),
        "issue_context": _issue_fact(steps),
        "schema_impact": (
            any(_schema_path(path) for path in paths) if git_exact else None
        ),
        "tracked_delta": bool(paths) if git_exact else None,
    }


__all__ = ("derive_applicability_facts",)
