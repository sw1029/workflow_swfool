"""Run one workflow owner with an exact, repository-relative import surface."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Sequence


@dataclass(frozen=True, slots=True)
class OwnerSpec:
    module: str
    skill_dependencies: tuple[str, ...]


OWNER_SPECS = {
    "authority": OwnerSpec(
        "manage_agent_authority",
        ("manage-agent-authority",),
    ),
    "task-doctor": OwnerSpec(
        "task_doctor_workflow_lib",
        (
            "task-doctor",
            "manage-agent-authority",
            "manage-external-advice",
            "manage-task-state-index",
            "record-agent-work-log",
        ),
    ),
    "external-advice": OwnerSpec(
        "manage_external_advice",
        ("manage-external-advice", "record-agent-work-log"),
    ),
    "task-index": OwnerSpec(
        "manage_task_state_index",
        ("manage-task-state-index", "record-agent-work-log"),
    ),
    "cycle": OwnerSpec(
        "orchestrate_task_cycle",
        (
            "orchestrate-task-cycle",
            "manage-agent-authority",
            "manage-external-advice",
            "manage-task-state-index",
            "record-agent-work-log",
            "audit-session-governance",
        ),
    ),
}


def _skills_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _scripts_path(root: Path, skill: str, module: str) -> Path:
    skill_path = root / skill
    scripts = skill_path / "scripts"
    module_root = scripts / module
    entrypoint = module_root / "__main__.py"
    for path, kind in (
        (skill_path, "directory"),
        (scripts, "directory"),
        (module_root, "directory"),
        (entrypoint, "file"),
    ):
        if not path.exists() and not path.is_symlink():
            raise ValueError(f"Workflow dependency is missing: {skill}")
        mode = path.lstat().st_mode
        expected = stat.S_ISDIR(mode) if kind == "directory" else stat.S_ISREG(mode)
        if stat.S_ISLNK(mode) or not expected:
            raise ValueError(f"Workflow dependency is unsafe: {skill}")
    return scripts


def _environment(spec: OwnerSpec) -> dict[str, str]:
    root = _skills_root()
    paths: list[str] = []
    for skill in spec.skill_dependencies:
        module = spec.module if skill == spec.skill_dependencies[0] else _module_for(skill)
        paths.append(str(_scripts_path(root, skill, module)))
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment["PYTHONPATH"] = os.pathsep.join(paths)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONSAFEPATH"] = "1"
    return environment


def _module_for(skill: str) -> str:
    modules = {
        "manage-agent-authority": "manage_agent_authority",
        "manage-external-advice": "manage_external_advice",
        "manage-task-state-index": "manage_task_state_index",
        "orchestrate-task-cycle": "orchestrate_task_cycle",
        "record-agent-work-log": "record_agent_work_log",
        "audit-session-governance": "audit_session_governance",
        "task-doctor": "task_doctor_workflow_lib",
    }
    try:
        return modules[skill]
    except KeyError as exc:  # pragma: no cover - static registry invariant.
        raise RuntimeError(f"Unregistered workflow dependency: {skill}") from exc


def _usage() -> str:
    owners = "|".join(OWNER_SPECS)
    return (
        f"usage: python3 -m orchestrate_task_cycle workflow {{{owners}}} ...\n"
        "\n"
        "Forward one owner command with its sibling skill dependencies wired.\n"
        "Run `workflow <owner> --help` for that owner's exact subcommands; for "
        "example, `workflow task-index index --help`."
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        print(_usage())
        return 0
    owner, *owner_arguments = arguments
    spec = OWNER_SPECS.get(owner)
    if spec is None:
        print(f"unknown workflow owner: {owner}", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    try:
        environment = _environment(spec)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    completed = subprocess.run(
        [sys.executable, "-P", "-m", spec.module, *owner_arguments],
        env=environment,
        check=False,
    )
    return completed.returncode


__all__ = ["OWNER_SPECS", "OwnerSpec", "main"]
