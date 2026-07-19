from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "manage-task-state-index" / "scripts",
    ROOT / "manage-external-advice" / "scripts",
    ROOT / "record-agent-work-log" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from manage_external_advice.disposition_compiler import (  # noqa: E402
    compile_dispositions,
    render_disposition_template,
)
from manage_external_advice.intake import cmd_intake  # noqa: E402
from manage_external_advice.lifecycle import cmd_mark_applied  # noqa: E402
from manage_external_advice.registry import main as advice_main  # noqa: E402
from manage_external_advice.storage import load_events, merge_state  # noqa: E402
from manage_task_state_index import index as task_index  # noqa: E402
from manage_task_state_index.state.transition_compiler import (  # noqa: E402
    compile_transition_intent,
)


AT = "2026-07-19T12:34:56+09:00"


def _task_intent() -> dict[str, object]:
    return {
        "schema_version": 1,
        "expected_index_revision": "current",
        "actions": [
            {
                "action": "set_lifecycle",
                "artifact_ref": "task.md",
                "artifact_type": "task",
                "identity": "current",
                "status": "superseded",
                "relationships": [
                    {
                        "rel": "superseded_by",
                        "target_ref": "task.md",
                        "target_type": "task",
                        "target_identity": "new",
                    }
                ],
            },
            {
                "action": "set_lifecycle",
                "artifact_ref": "task.md",
                "artifact_type": "task",
                "identity": "new",
                "status": "active",
                "relationships": [
                    {
                        "rel": "supersedes",
                        "target_ref": "task.md",
                        "target_type": "task",
                        "target_identity": "current",
                    }
                ],
            },
        ],
    }


def test_task_index_compiler_is_deterministic_and_plan_compatible(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    original = task_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    task.write_text("# Successor task\n", encoding="utf-8")

    first = compile_transition_intent(tmp_path, _task_intent(), at=AT)
    second = compile_transition_intent(tmp_path, _task_intent(), at=AT)
    plan = task_index.build_transition_plan(tmp_path, first["request"])

    assert first == second
    assert first["request_sha256"] == hashlib.sha256(
        json.dumps(
            first["request"], ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    assert first["request"]["events"][0] == {
        "event": "upsert",
        "id": original["id"],
        "status": "superseded",
        "links": [
            {
                "rel": "superseded_by",
                "id": "task-20260719-123456-successor-task",
            }
        ],
    }
    assert first["request"]["events"][1]["id"] == (
        "task-20260719-123456-successor-task"
    )
    assert first["request"]["events"][1]["content_sha256"] == task_index.sha256_file(
        task
    )
    assert plan["request"] == first["request"]
    assert not (tmp_path / ".task" / "transition_plans").exists()


def test_task_index_plan_transition_accepts_intent_and_rejects_stale_revision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task = tmp_path / "task.md"
    task.write_text("# Original task\n", encoding="utf-8")
    task_index.upsert_item(
        tmp_path,
        "task",
        "task.md",
        "active",
        item_id="task-original",
        replace_existing=False,
    )
    task.write_text("# Successor task\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="--at is required"):
        task_index.main(
            [
                "--root",
                str(tmp_path),
                "plan-transition",
                "--intent",
                json.dumps(_task_intent()),
                "--dry-run",
            ]
        )
    exit_code = task_index.main(
        [
            "--root",
            str(tmp_path),
            "plan-transition",
            "--intent",
            json.dumps(_task_intent()),
            "--at",
            AT,
            "--dry-run",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "dry_run"
    assert output["mutation_performed"] is False

    stale = _task_intent()
    stale["expected_index_revision"] = "0" * 64
    with pytest.raises(SystemExit, match="recompile_required"):
        task_index.main(
            [
                "--root",
                str(tmp_path),
                "compile-transition",
                "--intent",
                json.dumps(stale),
                "--at",
                AT,
            ]
        )


def test_task_index_compiler_rejects_symlinked_index_root(tmp_path: Path) -> None:
    (tmp_path / "task.md").write_text("# New task\n", encoding="utf-8")
    outside = tmp_path / "outside-task-state"
    outside.mkdir()
    (tmp_path / ".task").symlink_to(outside, target_is_directory=True)
    intent = {
        "schema_version": 1,
        "expected_index_revision": "current",
        "actions": [
            {
                "action": "set_lifecycle",
                "artifact_ref": "task.md",
                "artifact_type": "task",
                "identity": "new",
                "status": "active",
            }
        ],
    }

    with pytest.raises(ValueError, match="must not be a symlink"):
        compile_transition_intent(tmp_path, intent, at=AT)


def _active_advice(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> dict[str, object]:
    source = root / "advice.md"
    source.write_text(
        "# Advice\n\nSA-101: Must retain exact evidence.\n\n"
        "SA-102: Must preserve residual state.\n",
        encoding="utf-8",
    )
    cmd_intake(
        argparse.Namespace(
            root=str(root),
            source=str(source),
            title="workflow advice",
            priority="normal",
        )
    )
    capsys.readouterr()
    return next(iter(merge_state(load_events(root)).values()))


def test_advice_template_compiles_and_mark_applied_consumes_decision_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    item = _active_advice(tmp_path, capsys)
    evidence = tmp_path / "validation.json"
    evidence.write_text('{"status":"pass"}\n', encoding="utf-8")
    template = render_disposition_template(item)
    for index, directive_id in enumerate(template["actionable_directive_ids"]):
        template["decisions"][directive_id] = {
            "disposition": "incorporated" if index == 0 else "residual",
            "evidence_ref": "validation.json",
        }

    compilation = compile_dispositions(
        tmp_path, item, json.dumps(template, ensure_ascii=False)
    )
    expected_digest = hashlib.sha256(evidence.read_bytes()).hexdigest()

    assert [row["directive_id"] for row in compilation["rows"]] == template[
        "actionable_directive_ids"
    ]
    assert {row["evidence_sha256"] for row in compilation["rows"]} == {
        expected_digest
    }
    cmd_mark_applied(
        argparse.Namespace(
            root=str(tmp_path),
            advice_id=item["advice_id"],
            evidence="validation run",
            decision_map=json.dumps(template, ensure_ascii=False),
            directive_dispositions_json=None,
            note="residual remains open",
        )
    )
    capsys.readouterr()
    updated = merge_state(load_events(tmp_path))[item["advice_id"]]
    assert updated["status"] == "applied"
    assert updated["fields"]["directive_states"] == {
        template["actionable_directive_ids"][0]: "incorporated",
        template["actionable_directive_ids"][1]: "residual",
    }


def test_advice_decision_map_fails_closed_on_missing_or_unsafe_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    item = _active_advice(tmp_path, capsys)
    template = render_disposition_template(item)
    first = template["actionable_directive_ids"][0]
    incomplete = {
        first: {"disposition": "incorporated", "evidence_ref": "missing.json"}
    }
    with pytest.raises(SystemExit, match="cover every actionable"):
        compile_dispositions(tmp_path, item, json.dumps(incomplete))

    unsafe = {
        directive_id: {
            "disposition": "incorporated",
            "evidence_ref": "../outside.json",
        }
        for directive_id in template["actionable_directive_ids"]
    }
    with pytest.raises(SystemExit, match="canonical workspace-relative"):
        compile_dispositions(tmp_path, item, json.dumps(unsafe))

    real = tmp_path / "real.json"
    real.write_text("{}\n", encoding="utf-8")
    (tmp_path / "linked.json").symlink_to(real)
    linked = {
        directive_id: {
            "disposition": "incorporated",
            "evidence_ref": "linked.json",
        }
        for directive_id in template["actionable_directive_ids"]
    }
    with pytest.raises(SystemExit, match="contains a symlink"):
        compile_dispositions(tmp_path, item, json.dumps(linked))

    decisions = {
        directive_id: {
            "disposition": "incorporated",
            "evidence_ref": "real.json",
        }
        for directive_id in template["actionable_directive_ids"]
    }
    source = tmp_path / str(item["path"])
    source.write_text(source.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="source binding is stale"):
        compile_dispositions(tmp_path, item, json.dumps(decisions))


def test_advice_registry_exposes_template_and_compiler_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    item = _active_advice(tmp_path, capsys)
    evidence = tmp_path / "validation.json"
    evidence.write_text('{"status":"pass"}\n', encoding="utf-8")
    assert advice_main(
        [
            "--root",
            str(tmp_path),
            "render-disposition-template",
            "--advice-id",
            str(item["advice_id"]),
        ]
    ) == 0
    template = json.loads(capsys.readouterr().out)
    for directive_id in template["actionable_directive_ids"]:
        template["decisions"][directive_id] = {
            "disposition": "incorporated",
            "evidence_ref": "validation.json",
        }

    assert advice_main(
        [
            "--root",
            str(tmp_path),
            "compile-dispositions",
            "--advice-id",
            str(item["advice_id"]),
            "--decision-map",
            json.dumps(template, ensure_ascii=False),
        ]
    ) == 0
    compilation = json.loads(capsys.readouterr().out)
    assert compilation["result_kind"] == "external_advice_disposition_compilation"
    assert advice_main(
        [
            "--root",
            str(tmp_path),
            "mark-applied",
            "--advice-id",
            str(item["advice_id"]),
            "--evidence",
            "validation run",
            "--decision-map",
            json.dumps(template, ensure_ascii=False),
        ]
    ) == 0
    capsys.readouterr()
    assert merge_state(load_events(tmp_path))[item["advice_id"]]["status"] == "applied"
