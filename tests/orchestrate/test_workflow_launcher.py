from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "orchestrate-task-cycle" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from orchestrate_task_cycle import workflow_launcher  # noqa: E402


@pytest.mark.parametrize(
    ("owner", "arguments"),
    (
        ("authority", ["authority", "--help"]),
        ("task-doctor", ["--help"]),
        ("external-advice", ["registry", "--help"]),
        ("task-index", ["index", "--help"]),
        ("cycle", ["--help"]),
        ("cycle", ["context", "--help"]),
        ("cycle", ["result-contract", "--help"]),
    ),
)
def test_workflow_owner_help_runs_from_unrelated_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    owner: str,
    arguments: list[str],
) -> None:
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    monkeypatch.chdir(unrelated)

    result = workflow_launcher.main([owner, *arguments])
    captured = capfd.readouterr()

    assert result == 0, captured.err or captured.out
    assert "usage:" in captured.out.lower()


def test_workflow_environment_replaces_unrelated_pythonpath(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", "/untrusted/inherited/path")
    spec = workflow_launcher.OWNER_SPECS["task-index"]

    environment = workflow_launcher._environment(spec)
    paths = environment["PYTHONPATH"].split(os.pathsep)

    assert "/untrusted/inherited/path" not in paths
    assert paths == [
        str(ROOT / "manage-task-state-index" / "scripts"),
        str(ROOT / "record-agent-work-log" / "scripts"),
    ]
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONSAFEPATH"] == "1"


@pytest.mark.parametrize(
    ("owner_arguments", "expected"),
    (
        (["task-index", "index", "--help"], "compile-transition"),
        (["cycle", "context", "--help"], "--root"),
        (["cycle", "result-contract", "--help"], "validate"),
    ),
)
def test_public_workflow_subcommand_dispatches_from_unrelated_cwd(
    tmp_path: Path, owner_arguments: list[str], expected: str,
) -> None:
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SCRIPTS)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrate_task_cycle",
            "workflow",
            *owner_arguments,
        ],
        cwd=unrelated,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert expected in completed.stdout


def test_workflow_launcher_rejects_symlinked_skill_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside" / "manage-task-state-index"
    module = outside / "scripts" / "manage_task_state_index"
    module.mkdir(parents=True)
    (module / "__main__.py").write_text("", encoding="utf-8")
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "manage-task-state-index").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(workflow_launcher, "_skills_root", lambda: skills)

    with pytest.raises(ValueError, match="unsafe"):
        workflow_launcher._environment(
            workflow_launcher.OWNER_SPECS["task-index"]
        )
