from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "orchestrate-task-cycle" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from orchestrate_task_cycle import workflow_launcher  # noqa: E402


TRUSTED_MODULES = (
    "orchestrate_task_cycle",
    "manage_agent_authority",
    "manage_task_state_index",
    "manage_external_advice",
    "record_agent_work_log",
    "audit_session_governance",
    "task_doctor_workflow_lib",
)
TRUSTED_SKILL_DOCS = (
    "orchestrate-task-cycle",
    "manage-agent-authority",
    "manage-task-state-index",
    "manage-external-advice",
    "record-agent-work-log",
    "audit-session-governance",
    "task-doctor",
)


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


def test_workflow_launcher_child_retains_python_safe_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(workflow_launcher.subprocess, "run", run)

    assert workflow_launcher.main(["cycle", "--help"]) == 0
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert argv[:4] == [sys.executable, "-P", "-m", "orchestrate_task_cycle"]
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["PYTHONSAFEPATH"] == "1"


def test_trusted_skill_module_examples_require_python_safe_path() -> None:
    unsafe = re.compile(
        r"python3 -m (?:" + "|".join(TRUSTED_MODULES) + r")\b"
    )
    defects = [
        path.relative_to(ROOT).as_posix()
        for skill in TRUSTED_SKILL_DOCS
        for path in (ROOT / skill).rglob("*.md")
        if unsafe.search(path.read_text(encoding="utf-8"))
    ]
    assert defects == []


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
            "-P",
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


def test_public_workflow_bootstrap_ignores_workspace_shadow_package(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    package = workspace / "orchestrate_task_cycle"
    package.mkdir(parents=True)
    marker = workspace / "workspace-shadow-ran"
    payload = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('shadowed', encoding='utf-8')\n"
        "raise SystemExit(97)\n"
    )
    (package / "__init__.py").write_text(payload, encoding="utf-8")
    (package / "__main__.py").write_text(payload, encoding="utf-8")
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
        cwd=workspace,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "usage:" in completed.stdout.lower()
    assert not marker.exists()


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
