from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from orchestrate_task_cycle.retained_change_evidence import (
    capture_baseline,
    compare_baseline,
)
from orchestrate_task_cycle.result_contract.retained_change import (
    classify_retained_change,
)


def _git(root: Path, *arguments: str) -> None:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "workflow@example.invalid")
    _git(root, "config", "user.name", "Workflow Test")
    source = root / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("value = 'initial'\n", encoding="utf-8")
    _git(root, "add", "src/app.py")
    _git(root, "commit", "-q", "-m", "baseline")
    return root


def test_clean_git_baseline_classifies_actual_new_bytes(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    baseline = capture_baseline(root)
    assert baseline["entries"] == []

    (root / "src" / "app.py").write_text("value = 'changed'\n", encoding="utf-8")
    (root / "src" / "new.py").write_text("added = True\n", encoding="utf-8")
    comparison = compare_baseline(root, baseline)
    evidence = comparison["retained_change_evidence"]

    assert [row["path"] for row in evidence["file_changes"]] == [
        "src/app.py",
        "src/new.py",
    ]
    assert [row["change_kind"] for row in evidence["file_changes"]] == [
        "modified",
        "added",
    ]
    assessment = classify_retained_change({"retained_change_evidence": evidence})
    assert assessment.evaluated is True
    assert assessment.producer_source_changed is True
    assert assessment.progress_cap == "root_reduction"
    assert assessment.invalid_evidence_fields == ()


def test_dirty_start_is_not_attributed_until_bytes_change(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    source = root / "src" / "app.py"
    source.write_text("value = 'preexisting-user-change'\n", encoding="utf-8")
    baseline = capture_baseline(root)

    unchanged = compare_baseline(root, baseline)
    assert unchanged["retained_change_evidence"]["file_changes"] == []
    assessment = classify_retained_change(unchanged)
    assert assessment.evaluated is True
    assert assessment.changed_files == ()
    assert assessment.progress_cap == "none"
    assert assessment.invalid_evidence_fields == ()

    before_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_text("value = 'task-change'\n", encoding="utf-8")
    changed = compare_baseline(root, baseline)["retained_change_evidence"]
    assert len(changed["file_changes"]) == 1
    assert changed["file_changes"][0]["before_sha256"] == before_digest
    assert (
        changed["file_changes"][0]["after_sha256"]
        == hashlib.sha256(source.read_bytes()).hexdigest()
    )


def test_tampered_baseline_fails_closed(tmp_path: Path) -> None:
    root = _repository(tmp_path)
    baseline = capture_baseline(root, ["src/app.py"])
    baseline["entries"][0]["content_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="baseline digest"):
        compare_baseline(root, baseline)
