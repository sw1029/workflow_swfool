from __future__ import annotations

import json
from pathlib import Path

import pytest

import orchestrate_task_cycle.selection_tick as selection_tick
import orchestrate_task_cycle.selection_tick_baseline as selection_tick_baseline
from orchestrate_task_cycle.selection_tick import (
    MAX_EXACT_PREMISES,
    build_selection_tick,
)


def _repo(root: Path) -> Path:
    (root / ".agent_goal").mkdir(parents=True)
    (root / "task.md").write_text("# Task\n", encoding="utf-8")
    (root / ".agent_goal/final_goal.md").write_text("# Goal\n", encoding="utf-8")
    return root


def test_duplicate_exact_paths_or_ids_fail_before_missing_file_reads(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    with pytest.raises(ValueError, match="nonempty and unique"):
        build_selection_tick(
            root,
            premise_paths=["missing.json", "missing.json"],
            premise_ids=["premise-A", "premise-B"],
        )
    with pytest.raises(ValueError, match="nonempty and unique"):
        build_selection_tick(
            root,
            premise_paths=["missing-A.json", "missing-B.json"],
            premise_ids=["premise-A", "premise-A"],
        )


def test_exact_premise_count_is_bounded_before_missing_file_reads(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    count = MAX_EXACT_PREMISES + 1

    with pytest.raises(ValueError, match=f"exceeds {MAX_EXACT_PREMISES}"):
        build_selection_tick(
            root,
            premise_paths=[f"missing-{index}.json" for index in range(count)],
            premise_ids=[f"premise-{index}" for index in range(count)],
        )


def test_cli_rejects_duplicate_premises_before_loading_previous_packet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _repo(tmp_path)

    def unexpected_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("previous packet must not be read")

    monkeypatch.setattr(selection_tick, "_load_previous", unexpected_read)
    code = selection_tick.main(
        [
            "--root",
            str(root),
            "--previous-json",
            "missing.json",
            "--premise-path",
            "missing.json",
            "--premise-id",
            "premise-A",
            "--premise-path",
            "missing.json",
            "--premise-id",
            "premise-B",
        ]
    )

    assert code == 2
    assert "nonempty and unique" in capsys.readouterr().out


def test_cli_previous_json_is_root_local_regular_and_non_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-previous.json"
    outside.write_text("{}", encoding="utf-8")

    assert (
        selection_tick.main(["--root", str(root), "--previous-json", str(outside)]) == 2
    )
    serialized = capsys.readouterr().out
    assert "outside repository root" in serialized
    assert str(outside) not in serialized

    assert (
        selection_tick.main(
            ["--root", str(root), "--previous-json", f"../{outside.name}"]
        )
        == 2
    )
    assert "path is invalid" in capsys.readouterr().out

    link = root / "previous-link.json"
    link.symlink_to(outside)
    assert selection_tick.main(["--root", str(root), "--previous-json", link.name]) == 2
    serialized = capsys.readouterr().out
    assert "is unreadable" in serialized
    assert str(outside) not in serialized


def test_cli_authority_packet_is_root_local_regular_and_non_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-authority.json"
    outside.write_text("{}", encoding="utf-8")

    assert (
        selection_tick.main(["--root", str(root), "--authority-packet", str(outside)])
        == 2
    )
    serialized = capsys.readouterr().out
    assert "outside repository root" in serialized
    assert str(outside) not in serialized

    link = root / "authority-link.json"
    link.symlink_to(outside)
    assert (
        selection_tick.main(["--root", str(root), "--authority-packet", link.name]) == 2
    )
    serialized = capsys.readouterr().out
    assert "is unreadable" in serialized
    assert str(outside) not in serialized


@pytest.mark.parametrize("option", ["--previous-json", "--authority-packet"])
def test_cli_json_inputs_are_bounded_before_decode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    option: str,
) -> None:
    root = _repo(tmp_path)
    payload = root / "oversized.json"
    payload.write_text(json.dumps({"body": "x" * 32}), encoding="utf-8")
    monkeypatch.setattr(selection_tick_baseline, "MAX_SELECTION_JSON_BYTES", 18)

    assert selection_tick.main(["--root", str(root), option, payload.name]) == 2
    serialized = capsys.readouterr().out
    assert "exceeds 18 bytes" in serialized
    assert str(payload) not in serialized


def test_cli_defaults_to_verified_baseline_then_identical_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repo(tmp_path)
    assert selection_tick.main(["--root", str(root)]) == 0
    baseline = json.loads(capsys.readouterr().out)
    assert baseline["status"] == "baseline_recorded"
    assert baseline["premise_input_contract"] == (
        "validated_exact_subject_premise_receipt_v2"
    )
    previous = root / "previous-selection-tick.json"
    previous.write_text(json.dumps(baseline), encoding="utf-8")

    assert (
        selection_tick.main(["--root", str(root), "--previous-json", previous.name])
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    assert second["status"] == "no_op"
    assert second["premise_input_contract"] == baseline["premise_input_contract"]
