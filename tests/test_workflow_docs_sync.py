from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrate_task_cycle import workflow_docs
from orchestrate_task_cycle.cli import COMMANDS


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "orchestrate-task-cycle" / "scripts"


def test_root_readme_generated_workflow_sections_are_current() -> None:
    current = workflow_docs.README_PATH.read_text(encoding="utf-8")

    assert workflow_docs.render_readme(current) == current
    assert f"{len(COMMANDS)}개:" in workflow_docs.command_row()
    assert workflow_docs.main(["--check"]) == 0


def test_write_repairs_only_generated_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = workflow_docs.README_PATH.read_text(encoding="utf-8")
    stale = current.replace(f"{len(COMMANDS)}개:", "0개:", 1)
    readme = tmp_path / "README.md"
    readme.write_text(stale, encoding="utf-8")
    monkeypatch.setattr(workflow_docs, "README_PATH", readme)

    assert workflow_docs.main(["--check"]) == 1
    assert workflow_docs.main(["--write"]) == 0
    assert readme.read_text(encoding="utf-8") == current


def test_docs_check_runs_from_an_unrelated_clean_environment(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SCRIPTS)

    completed = subprocess.run(
        [
            sys.executable,
            "-P",
            "-m",
            "orchestrate_task_cycle.workflow_docs",
            "--check",
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "generated workflow docs are current" in completed.stdout


def test_public_workflow_launcher_runs_from_an_unrelated_clean_environment(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SCRIPTS)

    completed = subprocess.run(
        [
            sys.executable,
            "-P",
            "-m",
            "orchestrate_task_cycle",
            "workflow",
            "cycle",
            "--help",
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
