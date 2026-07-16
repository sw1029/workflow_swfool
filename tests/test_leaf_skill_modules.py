from __future__ import annotations

import ast
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    ("build-validation-set-with-agents", "build_validation_set_with_agents"),
    ("plan-validation-scope", "plan_validation_scope"),
    ("audit-session-governance", "audit_session_governance"),
    ("manage-agent-authority", "manage_agent_authority"),
    ("normalize-acceptance-and-demo", "normalize_acceptance_and_demo"),
    ("find-local-python-envs", "find_local_python_envs"),
    ("run-task-code-and-log", "run_task_code_and_log"),
    ("validate-task-completion", "validate_task_completion"),
)


@pytest.mark.parametrize(("skill", "package"), PACKAGES)
def test_public_module_help_runs_from_arbitrary_working_directory(
    tmp_path: Path,
    skill: str,
    package: str,
) -> None:
    scripts = ROOT / skill / "scripts"
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(scripts)

    result = subprocess.run(
        [sys.executable, "-m", package, "--help"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


@pytest.mark.parametrize(("skill", "package"), PACKAGES)
def test_production_code_is_package_owned_and_bounded(skill: str, package: str) -> None:
    scripts = ROOT / skill / "scripts"
    package_root = scripts / package

    assert not list(scripts.glob("*.py"))
    assert (package_root / "__main__.py").is_file()
    for path in package_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) <= 500, path
        assert "sys.path.insert" not in source, path
        assert "globals()" not in source, path
        assert "__dict__.update" not in source, path
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 <= 140, (path, node.name)
