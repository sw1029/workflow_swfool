from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "normalize-acceptance-and-demo" / "scripts",
    ROOT / "orchestrate-task-cycle" / "scripts",
    ROOT / "record-agent-work-log" / "scripts",
    ROOT / "manage-agent-authority" / "scripts",
    ROOT / "manage-task-state-index" / "scripts",
    ROOT / "manage-external-advice" / "scripts",
    ROOT / "manage-evidence-cache" / "scripts",
    ROOT / "manage-implementation-issues" / "scripts",
    ROOT / "manage-schema-contracts" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from normalize_acceptance_and_demo import acceptance_compiler as acceptance_compiler_module  # noqa: E402
from normalize_acceptance_and_demo.acceptance_compiler import (  # noqa: E402
    compile_acceptance,
)
from normalize_acceptance_and_demo.acceptance_identity import (  # noqa: E402
    AcceptanceIdentityError,
)
from normalize_acceptance_and_demo.cli import main as acceptance_main  # noqa: E402
from orchestrate_task_cycle.cycle_ledger import init_cycle  # noqa: E402
from orchestrate_task_cycle.stage.artifact_store import load_stage_input  # noqa: E402


def _write_json(path: Path, value: object) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "ref": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _draft() -> dict[str, Any]:
    return {
        "acceptance_status": "normalized",
        "acceptance_criteria": ["The deterministic contract tests pass."],
        "blockers": [],
        "evidence_paths": ["acceptance-source.json"],
    }


def _satisfiable_fields() -> dict[str, Any]:
    return {
        "validation_predicate_contract": {
            "criteria": [
                {
                    "criterion_id": "criterion_A",
                    "predicate_id": "predicate_A",
                    "required_output_classes": ["body"],
                    "required_non_empty_output_classes": ["body"],
                    "required_mutation_surfaces": ["producer"],
                    "required_verifier_input_classes": ["body"],
                    "required_freshness_class": "fresh_producer_execution",
                    "requires_body_movement": True,
                }
            ]
        },
        "producer_directives": {
            "directives": [
                {
                    "producer_directive_id": "directive_A",
                    "criterion_ids": ["criterion_A"],
                    "permitted_output_classes": ["body"],
                    "guaranteed_non_empty_output_classes": ["body"],
                    "allowed_task_mutation_surfaces": ["producer"],
                    "verifier_observable_output_classes": ["body"],
                    "satisfying_execution_paths": ["bounded_execution"],
                    "producer_execution_allowed": True,
                    "body_mutation_allowed": True,
                    "local_repair_routes": ["same_task_contract_repair"],
                }
            ]
        },
    }


def test_compiler_publishes_compact_cas_binding_and_replays(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n\nBound acceptance.\n")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())

    first = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
    )
    second = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
    )

    assert "result" not in first
    assert first["model_authored_mechanical_bytes"] == 0
    assert first["mutation_performed"] is True
    assert second["duplicate"] is True
    assert second["owner_result_binding"] == first["owner_result_binding"]
    path = tmp_path / first["owner_result_binding"]["ref"]
    envelope = json.loads(path.read_text())
    result = envelope["result"]
    assert result["artifact_kind"] == "acceptance_packet"
    assert result["acceptance_id"].startswith("acceptance-task-1-")
    assert result["acceptance_provenance"]["source_semantic_draft_sha256"] == (
        draft_binding["sha256"]
    )
    assert first["owner_result_binding"]["sha256"] == hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def test_compiler_derives_satisfiability_and_stage_adapter_consumes_owner_fields(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    init_cycle(tmp_path, "cycle-1", "task-1", "acceptance adapter test")
    draft_binding = _write_json(
        tmp_path / "draft.json", {**_draft(), **_satisfiable_fields()}
    )
    compiled = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
    )
    binding = compiled["owner_result_binding"]

    loaded, exact = load_stage_input(
        tmp_path,
        binding["ref"],
        binding["sha256"],
        cycle_id="cycle-1",
        target="acceptance",
        input_kind="owner_result",
    )

    owner = loaded["owner_result"]
    assert "task_id" not in owner
    assert "step" not in owner
    assert owner["validation_predicate_contract"]["satisfiability_rows"][0][
        "evaluation_status"
    ] == "pass"
    assert owner["mutually_unsatisfiable_contract"] is False
    assert owner["unverifiable_acceptance_contract"] is False
    assert exact["size_bytes"] == binding["size_bytes"]


def test_compiler_preserves_rich_acceptance_contract_without_flat_packet_authoring(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    init_cycle(tmp_path, "cycle-1", "task-1", "rich acceptance contract")
    contract = {
        "non_goals": ["Do not widen the task."],
        "required_validation_commands": ["pytest -q"],
        "quantifiers": [{"minimum": 3, "unit": "runs"}],
        "evidence_kind": "live_run",
        "required_freshness_class": "fresh_producer_execution",
        "designated_baseline": {"id": "baseline-A"},
        "production_lane_identity": "lane-A",
        "parity_axes": [{"axis": "input", "status": "controlled"}],
        "required_evidence_resolution": "item_ids",
        "required_scale": 100,
        "observed_cycle_throughput": 10,
        "cycle_execution_cap": 2,
        "slack": {"kind": "adapter_owned", "value": 0.1},
        "harvest_contract_preflight": {"status": "pass"},
    }
    draft_binding = _write_json(
        tmp_path / "draft.json",
        {**_draft(), "acceptance_contract": contract},
    )
    compiled = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
    )
    binding = compiled["owner_result_binding"]

    loaded, _exact = load_stage_input(
        tmp_path,
        binding["ref"],
        binding["sha256"],
        cycle_id="cycle-1",
        target="acceptance",
        input_kind="owner_result",
    )

    assert loaded["owner_result"]["acceptance_contract"] == contract


def test_compiler_rejects_unknown_rich_acceptance_field(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    draft_binding = _write_json(
        tmp_path / "draft.json",
        {
            **_draft(),
            "acceptance_contract": {"invented_requirement": True},
        },
    )

    with pytest.raises(AcceptanceIdentityError, match="unsupported fields"):
        compile_acceptance(
            tmp_path,
            task_id="task-1",
            task_path="task.md",
            draft_binding=draft_binding,
        )


@pytest.mark.parametrize(
    "copy_ref",
    (
        ".task/copied-acceptance.json",
        ".task/acceptance/sha256/"
        + "a" * 64
        + ".json",
    ),
)
def test_stage_adapter_rejects_byte_identical_acceptance_outside_canonical_cas(
    tmp_path: Path, copy_ref: str
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    init_cycle(tmp_path, "cycle-1", "task-1", "acceptance CAS path test")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())
    compiled = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
    )
    source = tmp_path / compiled["owner_result_binding"]["ref"]
    copied = tmp_path / copy_ref
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_bytes(source.read_bytes())
    digest = hashlib.sha256(copied.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="producer CAS"):
        load_stage_input(
            tmp_path,
            copy_ref,
            digest,
            cycle_id="cycle-1",
            target="acceptance",
            input_kind="owner_result",
        )


@pytest.mark.parametrize(
    "derived",
    (
        {"acceptance_id": "caller-authored"},
        {"task_id": "task-1"},
        {"mutually_unsatisfiable_contract": False},
        {
            "validation_predicate_contract": {
                "criteria": [],
                "satisfiability_rows": [],
            }
        },
    ),
)
def test_compiler_rejects_model_authored_mechanical_fields(
    tmp_path: Path, derived: dict[str, Any]
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    draft_binding = _write_json(
        tmp_path / "draft.json", {**_draft(), **derived}
    )

    with pytest.raises(
        AcceptanceIdentityError,
        match="compiler-derived|must not author",
    ):
        compile_acceptance(
            tmp_path,
            task_id="task-1",
            task_path="task.md",
            draft_binding=draft_binding,
        )

    assert not (tmp_path / ".task").exists()


def test_compile_dry_run_is_zero_write_and_cli_emits_only_binding_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())

    exit_code = acceptance_main(
        [
            "compile",
            "--root",
            str(tmp_path),
            "--task-id",
            "task-1",
            "--draft-ref",
            draft_binding["ref"],
            "--draft-sha256",
            draft_binding["sha256"],
            "--dry-run",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "dry_run"
    assert "result" not in output
    assert not (tmp_path / ".task").exists()


def test_compiler_binds_task_revision(tmp_path: Path) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n\nFirst.\n")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())
    first = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
        publish=False,
    )
    task.write_text("# Task\n\nSecond.\n")
    second = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
        publish=False,
    )

    assert first["acceptance_id"] != second["acceptance_id"]
    assert first["owner_result_binding"] != second["owner_result_binding"]


def test_compiler_canonicalizes_draft_ref_aliases(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())
    alias_binding = {**draft_binding, "ref": "./draft.json"}

    direct = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
        publish=False,
    )
    alias = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=alias_binding,
        publish=False,
    )

    assert alias["source_draft_binding"]["ref"] == "draft.json"
    assert alias["owner_result_binding"] == direct["owner_result_binding"]


def test_compiler_rejects_symlinked_producer_directory(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / ".task").symlink_to(outside, target_is_directory=True)

    with pytest.raises(AcceptanceIdentityError, match="must not traverse a symlink"):
        compile_acceptance(
            tmp_path,
            task_id="task-1",
            task_path="task.md",
            draft_binding=draft_binding,
        )

    assert not (outside / "acceptance").exists()


def test_compiler_rejects_existing_symlink_in_nested_cas_ancestor(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())
    outside = tmp_path / "outside-nested-cas"
    outside.mkdir()
    (tmp_path / ".task").mkdir()
    (tmp_path / ".task/acceptance").symlink_to(
        outside, target_is_directory=True
    )

    with pytest.raises(AcceptanceIdentityError, match="must not traverse a symlink"):
        compile_acceptance(
            tmp_path,
            task_id="task-1",
            task_path="task.md",
            draft_binding=draft_binding,
        )

    assert list(outside.iterdir()) == []


def test_compiler_rejects_parent_swap_immediately_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())
    outside = tmp_path / "outside-acceptance-cas"
    outside.mkdir()
    detached = tmp_path / ".task/acceptance/sha256-detached"
    swapped = False

    def swap_parent(stage: str, path: Path) -> None:
        nonlocal swapped
        if stage == "before_link" and not swapped:
            swapped = True
            path.parent.rename(detached)
            os.symlink(outside, path.parent, target_is_directory=True)

    monkeypatch.setattr(
        acceptance_compiler_module, "_publication_race_hook", swap_parent
    )

    with pytest.raises(AcceptanceIdentityError, match="changed or became a symlink"):
        compile_acceptance(
            tmp_path,
            task_id="task-1",
            task_path="task.md",
            draft_binding=draft_binding,
        )

    assert swapped is True
    assert list(outside.iterdir()) == []
    assert list(detached.iterdir()) == []


def test_stage_adapter_rederives_task_and_draft_instead_of_trusting_self_hash(
    tmp_path: Path,
) -> None:
    (tmp_path / "task.md").write_text("# Task\n")
    init_cycle(tmp_path, "cycle-1", "task-1", "acceptance verification")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())
    compiled = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
    )
    source = tmp_path / compiled["owner_result_binding"]["ref"]
    forged = json.loads(source.read_text())
    forged["result"]["task_id"] = "wrong-task"
    forged["result"]["acceptance_provenance"]["source_task_id"] = "wrong-task"
    forged["result_sha256"] = hashlib.sha256(
        json.dumps(
            forged["result"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    payload = (
        json.dumps(
            forged,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    digest = hashlib.sha256(payload).hexdigest()
    ref = f".task/acceptance/sha256/{digest}.json"
    path = tmp_path / ref
    path.write_bytes(payload)

    with pytest.raises(ValueError, match="task does not match"):
        load_stage_input(
            tmp_path,
            ref,
            digest,
            cycle_id="cycle-1",
            target="acceptance",
            input_kind="owner_result",
        )


def test_stage_adapter_rejects_acceptance_after_task_revision_changes(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Task\n\nFirst.\n")
    init_cycle(tmp_path, "cycle-1", "task-1", "acceptance freshness")
    draft_binding = _write_json(tmp_path / "draft.json", _draft())
    compiled = compile_acceptance(
        tmp_path,
        task_id="task-1",
        task_path="task.md",
        draft_binding=draft_binding,
    )
    task.write_text("# Task\n\nSecond.\n")
    binding = compiled["owner_result_binding"]

    with pytest.raises(ValueError, match="deterministic recompilation"):
        load_stage_input(
            tmp_path,
            binding["ref"],
            binding["sha256"],
            cycle_id="cycle-1",
            target="acceptance",
            input_kind="owner_result",
        )
