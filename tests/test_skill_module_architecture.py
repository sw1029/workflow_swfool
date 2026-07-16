from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAX_MODULE_LINES = 500
MAX_DEFINITION_LINES = 140

SKILL_PACKAGES = {
    "audit-cycle-loopback": "audit_cycle_loopback",
    "audit-session-governance": "audit_session_governance",
    "build-validation-set-with-agents": "build_validation_set_with_agents",
    "find-local-python-envs": "find_local_python_envs",
    "manage-agent-authority": "manage_agent_authority",
    "manage-external-advice": "manage_external_advice",
    "manage-task-state-index": "manage_task_state_index",
    "normalize-acceptance-and-demo": "normalize_acceptance_and_demo",
    "orchestrate-task-cycle": "orchestrate_task_cycle",
    "plan-validation-scope": "plan_validation_scope",
    "record-agent-work-log": "record_agent_work_log",
    "run-task-code-and-log": "run_task_code_and_log",
    "validate-task-completion": "validate_task_completion",
}

INTENTIONAL_FILE_ADAPTER_LOADERS = {
    Path("run-task-code-and-log/scripts/run_task_code_and_log/failure_diagnostics.py"),
}


def production_modules() -> list[Path]:
    modules: list[Path] = []
    for skill in SKILL_PACKAGES:
        scripts = ROOT / skill / "scripts"
        modules.extend(
            path
            for path in scripts.rglob("*.py")
            if "tests" not in path.relative_to(scripts).parts
        )
    return sorted(modules)


def relative(path: Path) -> Path:
    return path.relative_to(ROOT)


def test_production_entrypoints_are_packages_only() -> None:
    flat_modules = [
        relative(path)
        for skill in SKILL_PACKAGES
        for path in (ROOT / skill / "scripts").glob("*.py")
    ]
    assert flat_modules == []

    missing_package_files: list[Path] = []
    for skill, package in SKILL_PACKAGES.items():
        package_root = ROOT / skill / "scripts" / package
        for name in ("__init__.py", "__main__.py"):
            candidate = package_root / name
            if not candidate.is_file():
                missing_package_files.append(relative(candidate))
        if not any(
            (package_root / name).is_file()
            for name in ("cli.py", "command_registry.py")
        ):
            missing_package_files.append(relative(package_root / "<cli-or-command-registry>"))
    assert missing_package_files == []


def test_production_modules_respect_size_boundaries() -> None:
    oversized_modules: list[tuple[Path, int]] = []
    oversized_definitions: list[tuple[Path, str, int, int]] = []

    for path in production_modules():
        source = path.read_text(encoding="utf-8")
        line_count = len(source.splitlines())
        if line_count > MAX_MODULE_LINES:
            oversized_modules.append((relative(path), line_count))

        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.end_lineno is None:
                continue
            definition_lines = node.end_lineno - node.lineno + 1
            if definition_lines > MAX_DEFINITION_LINES:
                oversized_definitions.append(
                    (relative(path), node.name, node.lineno, definition_lines)
                )

    assert oversized_modules == []
    assert oversized_definitions == []


def test_internal_module_wiring_is_static_and_explicit() -> None:
    wildcard_imports: list[tuple[Path, int]] = []
    path_mutations: list[tuple[Path, int]] = []
    reflective_imports: list[tuple[Path, int, str]] = []
    file_loaders: list[tuple[Path, int]] = []

    for path in production_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        path_relative = relative(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                wildcard_imports.append((path_relative, node.lineno))
            if not isinstance(node, ast.Call):
                continue
            call_name = ast.unparse(node.func)
            if call_name in {"sys.path.append", "sys.path.extend", "sys.path.insert"}:
                path_mutations.append((path_relative, node.lineno))
            if call_name in {"importlib.import_module", "__import__"}:
                reflective_imports.append((path_relative, node.lineno, call_name))
            if call_name.endswith("spec_from_file_location"):
                is_loopback_adapter = (
                    path_relative.parts[:3]
                    == ("audit-cycle-loopback", "scripts", "audit_cycle_loopback")
                    and "adapter" in path_relative.as_posix()
                )
                if path_relative not in INTENTIONAL_FILE_ADAPTER_LOADERS and not is_loopback_adapter:
                    file_loaders.append((path_relative, node.lineno))

    assert wildcard_imports == []
    assert path_mutations == []
    assert reflective_imports == []
    assert file_loaders == []


@pytest.mark.parametrize(("skill", "package"), SKILL_PACKAGES.items())
def test_package_help_runs_outside_the_skill_directory(skill: str, package: str) -> None:
    scripts = ROOT / skill / "scripts"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(scripts)
    completed = subprocess.run(
        [sys.executable, "-m", package, "--help"],
        cwd=Path("/tmp"),
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert "usage:" in completed.stdout.lower()
