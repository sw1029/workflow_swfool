from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestrate_task_cycle import selection_decision_receipt_cli as receipt_cli
from orchestrate_task_cycle.selection_decision_receipt import (
    acknowledgement_binding,
    read_selection_decision_receipt,
    render_preliminary_selection_decision,
    render_selection_decision_receipt,
    validate_selection_decision_receipt,
)
from orchestrate_task_cycle.selection_tick import build_selection_tick
from orchestrate_task_cycle.selection_synthesis import render_selection_synthesis
from selection_synthesis_support import persisted_selection_synthesis


def _write(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _cli(
    capsys: pytest.CaptureFixture[str], argv: list[str]
) -> tuple[int, dict[str, object]]:
    code = receipt_cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _selected_tick(root: Path, suffix: str = "A") -> dict[str, object]:
    _write(root / "task.md", "# Task\n")
    goal = _write(root / ".agent_goal/final_goal.md", "# Goal\n")
    baseline = build_selection_tick(root)
    _write(goal, f"# Goal {suffix}\n")
    return build_selection_tick(root, previous=baseline)


def _receipt(root: Path) -> tuple[dict[str, object], dict[str, str], dict[str, object]]:
    trigger = _selected_tick(root)
    trigger_path = _write(root / ".task/cycle/cycle-A/selection-trigger.json", trigger)
    _, synthesis_binding, _ = persisted_selection_synthesis(root)
    decision = render_preliminary_selection_decision(
        root,
        trigger,
        synthesis_binding,
    )
    derive = _write(
        root / ".task/cycle/cycle-A/derive.json",
        decision,
    )
    receipt = render_selection_decision_receipt(
        root,
        trigger,
        _binding(root, trigger_path),
        _binding(root, derive),
    )
    path = _write(root / ".task/cycle/cycle-A/selection-decision.json", receipt)
    return trigger, _binding(root, path), receipt


def test_rendered_receipt_reopens_persisted_derive_and_trigger(
    tmp_path: Path,
) -> None:
    trigger, binding, receipt = _receipt(tmp_path)

    reopened = read_selection_decision_receipt(
        tmp_path, binding, expected_trigger_tick=trigger
    )
    acknowledgement = acknowledgement_binding(binding, reopened)

    assert reopened == receipt
    assert acknowledgement["selection_receipt_ref"] == binding["ref"]
    assert acknowledgement["selection_receipt_sha256"] == binding["sha256"]
    assert acknowledgement["selection_receipt_id"] == receipt["receipt_id"]
    assert acknowledgement["selection_outcome"] == "selected"
    assert acknowledgement["selected_task_id"] == "task-next"
    assert "result" not in acknowledgement
    assert receipt["not_goal_truth"] is True
    assert receipt["not_authority"] is True
    assert receipt["not_validation_evidence"] is True
    assert receipt["not_completion_evidence"] is True
    assert receipt["mutation_performed"] is False


def test_receipt_tamper_and_wrong_trigger_fail_closed(tmp_path: Path) -> None:
    trigger, binding, receipt = _receipt(tmp_path)
    tampered = {**receipt, "selected_task_id": "task-forged"}
    with pytest.raises(ValueError, match="integrity"):
        validate_selection_decision_receipt(
            tmp_path, tampered, expected_trigger_tick=trigger
        )

    other = _selected_tick(tmp_path, "B")
    with pytest.raises(ValueError, match="another trigger"):
        read_selection_decision_receipt(tmp_path, binding, expected_trigger_tick=other)


def test_raw_receipt_and_decision_file_tamper_fail_closed(tmp_path: Path) -> None:
    trigger, binding, receipt = _receipt(tmp_path)
    receipt_path = tmp_path / binding["ref"]
    _write(receipt_path, {**receipt, "outcome": "terminal_wait"})
    with pytest.raises(ValueError, match="raw SHA-256"):
        read_selection_decision_receipt(
            tmp_path, binding, expected_trigger_tick=trigger
        )

    _write(receipt_path, receipt)
    binding = _binding(tmp_path, receipt_path)
    decision_path = tmp_path / receipt["selection_decision"]["ref"]
    _write(decision_path, {"selection_outcome": "terminal_wait", "next_task_id": None})
    with pytest.raises(ValueError, match="raw SHA-256"):
        read_selection_decision_receipt(
            tmp_path, binding, expected_trigger_tick=trigger
        )


def test_trigger_and_runtime_artifact_tamper_fail_closed(tmp_path: Path) -> None:
    trigger, binding, receipt = _receipt(tmp_path)
    trigger_path = tmp_path / receipt["trigger_selection_tick"]["ref"]
    _write(trigger_path, {**trigger, "changed": []})
    with pytest.raises(ValueError, match="raw SHA-256"):
        read_selection_decision_receipt(
            tmp_path, binding, expected_trigger_tick=trigger
        )

    _write(trigger_path, trigger)
    receipt_path = tmp_path / binding["ref"]
    binding = _binding(tmp_path, receipt_path)
    decision_path = tmp_path / receipt["selection_decision"]["ref"]
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    synthesis_path = tmp_path / decision["selection_synthesis"]["ref"]
    synthesis = json.loads(synthesis_path.read_text(encoding="utf-8"))
    runtime_ref = synthesis["runtime_artifact_binding"]["artifacts"][0]["artifact_ref"]
    runtime_path = tmp_path / runtime_ref
    runtime_path.write_bytes(runtime_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="runtime agent artifacts"):
        read_selection_decision_receipt(
            tmp_path, binding, expected_trigger_tick=trigger
        )


@pytest.mark.parametrize(
    "binding",
    [
        {"ref": 7, "sha256": "0" * 64},
        {"ref": "receipt.json", "sha256": True},
        {"ref": "receipt.json", "sha256": "A" * 64},
        {"ref": "../receipt.json", "sha256": "0" * 64},
    ],
)
def test_receipt_reader_rejects_coerced_or_unsafe_binding(
    tmp_path: Path, binding: object
) -> None:
    trigger = _selected_tick(tmp_path)
    with pytest.raises(ValueError, match="safe ref|unsafe"):
        read_selection_decision_receipt(
            tmp_path,
            binding,
            expected_trigger_tick=trigger,  # type: ignore[arg-type]
        )


def test_nonselected_receipt_forbids_selected_task_id(tmp_path: Path) -> None:
    trigger = _selected_tick(tmp_path)
    trigger_path = _write(
        tmp_path / ".task/cycle/cycle-A/selection-trigger.json", trigger
    )
    _, synthesis_binding, _ = persisted_selection_synthesis(
        tmp_path, outcome="terminal_wait"
    )
    decision = render_preliminary_selection_decision(
        tmp_path,
        trigger,
        synthesis_binding,
    )
    derive = _write(
        tmp_path / ".task/cycle/cycle-A/derive.json",
        decision,
    )
    receipt = render_selection_decision_receipt(
        tmp_path,
        trigger,
        _binding(tmp_path, trigger_path),
        _binding(tmp_path, derive),
    )

    assert receipt["outcome"] == "terminal_wait"
    assert receipt["selected_task_id"] is None
    forged = {**receipt, "selected_task_id": "task-forged"}
    with pytest.raises(ValueError, match="integrity"):
        validate_selection_decision_receipt(
            tmp_path, forged, expected_trigger_tick=trigger
        )


def test_minimal_projection_cannot_be_used_as_preliminary_selection_decision(
    tmp_path: Path,
) -> None:
    trigger = _selected_tick(tmp_path)
    fake = _write(
        tmp_path / ".task/cycle/cycle-A/fake-derive.json",
        {"selection_outcome": "selected", "next_task_id": "task-next"},
    )

    with pytest.raises(ValueError, match="exact fields"):
        trigger_path = _write(
            tmp_path / ".task/cycle/cycle-A/selection-trigger.json", trigger
        )
        render_selection_decision_receipt(
            tmp_path,
            trigger,
            _binding(tmp_path, trigger_path),
            _binding(tmp_path, fake),
        )


def test_selection_synthesis_rejects_noncanonical_next_task_id(
    tmp_path: Path,
) -> None:
    source, _, _ = persisted_selection_synthesis(tmp_path, suffix="STRICT")
    source["next_task_id"] = " task-next "

    with pytest.raises(ValueError, match="not canonical"):
        render_selection_synthesis(tmp_path, source)


def test_cli_persists_and_reopens_the_complete_selection_chain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, _, expected_synthesis = persisted_selection_synthesis(
        tmp_path, suffix="CLI"
    )
    source_path = _write(
        tmp_path / ".task/cycle/cycle-A/direct-selection-source.json", source
    )
    source_binding = _binding(tmp_path, source_path)

    code, synthesis = _cli(
        capsys,
        [
            "--root",
            str(tmp_path),
            "render-synthesis",
            "--source-result-ref",
            source_binding["ref"],
            "--source-result-sha256",
            source_binding["sha256"],
        ],
    )
    assert code == 0
    assert synthesis == expected_synthesis
    synthesis_path = _write(
        tmp_path / ".task/cycle/cycle-A/cli-selection-synthesis.json", synthesis
    )
    synthesis_binding = _binding(tmp_path, synthesis_path)

    trigger = _selected_tick(tmp_path, "CLI")
    trigger_path = _write(
        tmp_path / ".task/cycle/cycle-A/cli-selection-trigger.json", trigger
    )
    trigger_binding = _binding(tmp_path, trigger_path)
    code, decision = _cli(
        capsys,
        [
            "--root",
            str(tmp_path),
            "render-decision",
            "--trigger-tick-ref",
            trigger_binding["ref"],
            "--trigger-tick-sha256",
            trigger_binding["sha256"],
            "--selection-synthesis-ref",
            synthesis_binding["ref"],
            "--selection-synthesis-sha256",
            synthesis_binding["sha256"],
        ],
    )
    assert code == 0
    decision_path = _write(
        tmp_path / ".task/cycle/cycle-A/cli-preliminary-decision.json", decision
    )
    decision_binding = _binding(tmp_path, decision_path)

    code, receipt = _cli(
        capsys,
        [
            "--root",
            str(tmp_path),
            "render",
            "--trigger-tick-ref",
            trigger_binding["ref"],
            "--trigger-tick-sha256",
            trigger_binding["sha256"],
            "--selection-decision-ref",
            decision_binding["ref"],
            "--selection-decision-sha256",
            decision_binding["sha256"],
        ],
    )
    assert code == 0
    receipt_path = _write(
        tmp_path / ".task/cycle/cycle-A/cli-selection-receipt.json", receipt
    )
    receipt_binding = _binding(tmp_path, receipt_path)

    code, reopened = _cli(
        capsys,
        [
            "--root",
            str(tmp_path),
            "validate",
            "--receipt-ref",
            receipt_binding["ref"],
            "--receipt-sha256",
            receipt_binding["sha256"],
            "--trigger-tick-ref",
            trigger_binding["ref"],
            "--trigger-tick-sha256",
            trigger_binding["sha256"],
        ],
    )
    assert code == 0
    assert reopened == receipt
    assert reopened["outcome"] == "selected"
    assert reopened["selected_task_id"] == "task-next"
