from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


acceptance_identity = load_module(
    ROOT / "normalize-acceptance-and-demo" / "scripts" / "acceptance_identity.py",
    "acceptance_identity_tests",
)
result_contract = load_module(
    ROOT / "orchestrate-task-cycle" / "scripts" / "result_contract.py",
    "acceptance_identity_result_contract_tests",
)


def final_packet() -> dict[str, Any]:
    return {
        "acceptance_status": "normalized",
        "acceptance_criteria": ["The deterministic contract tests pass."],
        "blockers": [],
        "evidence_paths": ["acceptance-source.json"],
    }


def test_identity_binds_exact_task_revision_and_changes_after_edit(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n\nFirst revision.\n", encoding="utf-8")
    first = acceptance_identity.bind(tmp_path, "task-1", "task.md", final_packet(), True)
    task.write_text("# Task\n\nSecond revision.\n", encoding="utf-8")
    second = acceptance_identity.bind(tmp_path, "task-1", "task.md", final_packet(), True)

    assert first["acceptance_id"] != second["acceptance_id"]
    assert first["acceptance_provenance"]["source_task_fingerprint"] != second["acceptance_provenance"]["source_task_fingerprint"]
    assert second["acceptance_provenance"]["source_task_path"] == "task.md"


def test_identity_rejects_packet_for_another_task(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    packet = final_packet()
    packet["task_id"] = "task-other"

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match="does not match"):
        acceptance_identity.bind(tmp_path, "task-1", "task.md", packet, True)


def test_final_identity_requires_explicit_contract_fields(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match="acceptance_status"):
        acceptance_identity.bind(tmp_path, "task-1", "task.md", {}, True)


def test_identity_rejects_task_path_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-task.md"
    outside.write_text("# Outside\n", encoding="utf-8")

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match="escapes"):
        acceptance_identity.bind(tmp_path, "task-1", str(outside), final_packet(), True)


@pytest.mark.parametrize("criterion", [None, {}, [], "   "])
def test_final_identity_rejects_semantically_empty_criteria(tmp_path: Path, criterion: Any) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    packet = final_packet()
    packet["acceptance_criteria"] = [criterion]

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match="semantically empty"):
        acceptance_identity.bind(tmp_path, "task-1", "task.md", packet, True)


def test_acceptance_result_contract_rejects_semantically_empty_criterion() -> None:
    result = result_contract.validate(
        "acceptance",
        {
            "step": "acceptance",
            "acceptance_id": "acceptance-task-1",
            "task_id": "task-1",
            "acceptance_status": "normalized",
            "acceptance_provenance": {
                "source_task_id": "task-1",
                "source_task_path": "task.md",
                "source_task_fingerprint": "a" * 64,
            },
            "acceptance_criteria": [None],
            "blockers": [],
            "evidence_paths": ["task.md"],
        },
        "block",
    )

    assert result["status"] == "block"
    assert any(finding["code"] == "semantically_empty_acceptance_criteria" for finding in result["findings"])


def test_acceptance_result_contract_rejects_semantically_empty_blocker() -> None:
    result = result_contract.validate(
        "acceptance",
        {
            "step": "acceptance",
            "acceptance_id": "acceptance-task-1",
            "task_id": "task-1",
            "acceptance_status": "blocked",
            "acceptance_provenance": {
                "source_task_id": "task-1",
                "source_task_path": "task.md",
                "source_task_fingerprint": "a" * 64,
            },
            "acceptance_criteria": ["A concrete outcome is required."],
            "blockers": ["   "],
            "evidence_paths": ["task.md"],
        },
        "block",
    )

    assert result["status"] == "block"
    assert any(finding["code"] == "semantically_empty_acceptance_blocker" for finding in result["findings"])


@pytest.mark.parametrize(
    ("status", "blockers", "message"),
    [
        ("normalized", ["still unresolved"], "cannot retain blockers"),
        ("blocked", [], "requires a concrete blocker"),
        ("blocked", ["   "], "semantically empty blocker"),
        ("needs_review", [], "requires a concrete blocker"),
    ],
)
def test_final_identity_enforces_status_blocker_consistency(
    tmp_path: Path,
    status: str,
    blockers: list[str],
    message: str,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n", encoding="utf-8")
    packet = final_packet()
    packet["acceptance_status"] = status
    packet["blockers"] = blockers

    with pytest.raises(acceptance_identity.AcceptanceIdentityError, match=message):
        acceptance_identity.bind(tmp_path, "task-1", "task.md", packet, True)
