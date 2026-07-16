from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
AGENT_LOG_SCRIPTS = ROOT / "record-agent-work-log" / "scripts"
TASK_STATE_SCRIPTS = ROOT / "manage-task-state-index" / "scripts"
ADVICE_SCRIPTS = ROOT / "manage-external-advice" / "scripts"


@pytest.mark.parametrize(
    ("pythonpath", "module"),
    [
        (AGENT_LOG_SCRIPTS, "record_agent_work_log"),
        (TASK_STATE_SCRIPTS, "manage_task_state_index"),
        (ADVICE_SCRIPTS, "manage_external_advice"),
    ],
)
def test_package_root_help_is_successful(
    tmp_path: Path,
    pythonpath: Path,
    module: str,
) -> None:
    roots = [pythonpath]
    if module in {"manage_task_state_index", "manage_external_advice"}:
        roots.append(AGENT_LOG_SCRIPTS)
    completed = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(str(root) for root in roots),
        },
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout
    assert "commands:" in completed.stdout


@pytest.mark.parametrize(
    ("pythonpath", "module", "command"),
    [
        (AGENT_LOG_SCRIPTS, "record_agent_work_log", "write"),
        (AGENT_LOG_SCRIPTS, "record_agent_work_log", "migrate"),
        (AGENT_LOG_SCRIPTS, "record_agent_work_log", "verify-migration"),
        (TASK_STATE_SCRIPTS, "manage_task_state_index", "index"),
        (TASK_STATE_SCRIPTS, "manage_task_state_index", "migrate"),
        (TASK_STATE_SCRIPTS, "manage_task_state_index", "verify-migration"),
        (ADVICE_SCRIPTS, "manage_external_advice", "registry"),
    ],
)
def test_package_commands_start_from_an_arbitrary_working_directory(
    tmp_path: Path,
    pythonpath: Path,
    module: str,
    command: str,
) -> None:
    roots = [pythonpath]
    if module in {"manage_task_state_index", "manage_external_advice"}:
        roots.append(AGENT_LOG_SCRIPTS)
    completed = subprocess.run(
        [sys.executable, "-m", module, command, "--help"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": os.pathsep.join(str(root) for root in roots),
        },
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout


def test_static_command_registries_are_unique_and_complete() -> None:
    for package_root in (AGENT_LOG_SCRIPTS, TASK_STATE_SCRIPTS, ADVICE_SCRIPTS):
        if str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))

    from manage_external_advice.command_registry import COMMANDS as advice_commands
    from manage_task_state_index.command_registry import COMMANDS as task_commands
    from record_agent_work_log.command_registry import COMMANDS as log_commands

    assert tuple(command.name for command in log_commands) == (
        "write",
        "migrate",
        "verify-migration",
    )
    assert tuple(command.name for command in task_commands) == (
        "index",
        "migrate",
        "verify-migration",
    )
    assert tuple(command.name for command in advice_commands) == ("registry",)
    for commands in (log_commands, task_commands, advice_commands):
        assert len({command.name for command in commands}) == len(commands)
        assert all(isinstance(command.help, str) and command.help for command in commands)
        assert all(callable(command.handler) for command in commands)


def test_command_registries_use_explicit_lazy_handlers() -> None:
    for registry in (
        AGENT_LOG_SCRIPTS / "record_agent_work_log" / "command_registry.py",
        TASK_STATE_SCRIPTS / "manage_task_state_index" / "command_registry.py",
        ADVICE_SCRIPTS / "manage_external_advice" / "command_registry.py",
    ):
        source = registry.read_text(encoding="utf-8")
        assert "import_module" not in source
        assert "getattr(" not in source
        assert "handler: CommandHandler" in source


def test_external_advice_registry_subcommands_keep_their_shared_state_contract(
    tmp_path: Path,
) -> None:
    source = tmp_path / "advice.md"
    source.write_text(
        "# Preserve exact evidence\n\n"
        "Current evidence identifies a repeatable workflow gap.\n"
        "- Must preserve existing command interaction and output contracts.\n"
        "- output_fingerprint: original-output-1234\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            (str(ADVICE_SCRIPTS), str(AGENT_LOG_SCRIPTS))
        ),
    }

    def run_registry(*arguments: str) -> dict[str, object]:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "manage_external_advice",
                "registry",
                "--root",
                str(tmp_path),
                *arguments,
            ],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout)

    intake = run_registry("intake", "--source", str(source), "--priority", "high")
    assert intake["status"] == "ok"
    assert intake["event"]["status"] == "active"  # type: ignore[index]

    listing = run_registry("list", "--status", "active")
    assert len(listing["items"]) == 1  # type: ignore[arg-type]

    audit = run_registry(
        "audit", "--current-output-fingerprint", "current-output-5678"
    )
    assert audit["status"] == "ok"
    assert audit["advice_freshness_gate"]["advice_metrics_stale"] is True  # type: ignore[index]


def test_legacy_flat_entry_points_are_absent() -> None:
    for scripts_root in (AGENT_LOG_SCRIPTS, TASK_STATE_SCRIPTS, ADVICE_SCRIPTS):
        assert not list(scripts_root.glob("*.py"))
