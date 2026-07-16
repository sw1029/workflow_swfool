from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPTS = ROOT / "audit-session-governance" / "scripts"
ORCHESTRATION_SCRIPTS = ROOT / "orchestrate-task-cycle" / "scripts"
MODE_REGISTRY = ROOT / "orchestrate-task-cycle" / "references" / "mode-profiles.json"

sys.path[:0] = [str(AUDIT_SCRIPTS), str(ORCHESTRATION_SCRIPTS)]
from audit_session_governance import session_audit as audit  # noqa: E402
from orchestrate_task_cycle import mode_profile  # noqa: E402
from orchestrate_task_cycle.result_contract import session_audit as consumer  # noqa: E402


def module_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join((str(AUDIT_SCRIPTS), str(ORCHESTRATION_SCRIPTS)))
    return env


def write_jsonl(path: Path, events: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )


def codex_events(secret: str = "private body") -> list[dict[str, Any]]:
    return [
        {
            "timestamp": "2026-07-11T01:00:00Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": secret,
                "images": [],
                "local_images": [],
                "text_elements": [],
            },
        },
        {
            "timestamp": "2026-07-11T01:00:01+00:00",
            "type": "event_msg",
            "payload": {
                "type": "agent_message",
                "message": "completed claim must remain observational",
                "phase": "final_answer",
                "memory_citation": None,
            },
        },
    ]


def test_happy_codex_packet_is_body_free_and_consumer_compatible(
    tmp_path: Path,
) -> None:
    secret = "SECRET-MESSAGE-BODY-7319"
    source = tmp_path / "logs" / "codex" / "session.jsonl"
    write_jsonl(source, codex_events(secret))

    packet, output = audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle-1",
        task_id="task-1",
    )

    assert packet["capture_status"] == "complete"
    assert packet["capture_mode"] == "conversation_projection"
    assert packet["binding"] == {
        "status": "bound",
        "cycle_id": "cycle-1",
        "task_id": "task-1",
    }
    assert packet["consumable"] is True
    assert packet["not_goal_truth"] is True
    assert packet["not_validation_evidence"] is True
    assert packet["repair_class"] == "none"
    assert packet["auto_repair_allowed"] is False
    assert packet["parser_version"] == "session-audit/1"
    assert packet["event_counts"]["recognized_events"] == 2
    assert len(packet["evidence_paths"]) == 3
    assert all(
        value.startswith("sha256:")
        for value in packet["evidence_paths"][1:]
    )
    serialized = output.read_text(encoding="utf-8")
    assert secret not in serialized
    assert "completed claim must remain observational" not in serialized
    assert not audit.validate_packet(packet, tmp_path)
    assert not consumer.validate_session_audit_packet(packet)


def test_happy_claude_projection(tmp_path: Path) -> None:
    source = tmp_path / "logs" / "claude-code" / "session.jsonl"
    write_jsonl(
        source,
        [
            {
                "timestamp": "2026-07-11T01:00:00Z",
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "question"}],
                },
            },
            {
                "timestamp": "2026-07-11T01:00:02Z",
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "answer"}],
                },
            },
        ],
    )

    packet, _ = audit.inspect(
        tmp_path,
        source,
        tool="claude-code",
        cycle_id="cycle-2",
        task_id="task-2",
    )

    assert packet["capture_status"] == "complete"
    assert packet["event_counts"]["claude_code_events"] == 2
    assert packet["timestamp_bounds"] == {
        "first": "2026-07-11T01:00:00.000000Z",
        "last": "2026-07-11T01:00:02.000000Z",
    }
    assert not consumer.validate_session_audit_packet(packet)


def test_raw_tool_and_mixed_events_are_quarantined(tmp_path: Path) -> None:
    source = tmp_path / "logs" / "codex" / "raw.jsonl"
    events = codex_events() + [
        {
            "timestamp": "2026-07-11T01:00:03Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "arguments": "secret tool payload",
            },
        },
        {
            "timestamp": "2026-07-11T01:00:04Z",
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "mixed"}],
            },
        },
    ]
    write_jsonl(source, events)

    packet, output = audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle-1",
        task_id="task-1",
    )

    codes = {finding["code"] for finding in packet["findings"]}
    assert {"raw_or_tool_event", "mixed_tool_schemas"} <= codes
    assert packet["capture_status"] == "quarantined"
    assert packet["consumable"] is False
    assert packet["repair_class"] == "proposal_only"
    assert packet["auto_repair_allowed"] is False
    assert "secret tool payload" not in output.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("raw", "expected_code"),
    [
        ('{"type":', "malformed_jsonl"),
        (
            json.dumps(
                {
                    "schema_version": 2,
                    "timestamp": "2026-07-11T01:00:00Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "future"},
                }
            ),
            "unsupported_schema",
        ),
    ],
)
def test_malformed_and_future_schema_are_quarantined(
    tmp_path: Path, raw: str, expected_code: str
) -> None:
    source = tmp_path / "logs" / "codex" / f"{expected_code}.jsonl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(raw + "\n", encoding="utf-8")

    packet, _ = audit.inspect(tmp_path, source, tool="codex")

    assert packet["capture_status"] == "quarantined"
    assert packet["consumable"] is False
    assert expected_code in {item["code"] for item in packet["findings"]}
    assert not audit.validate_packet(packet, tmp_path)


def test_invalid_utf8_and_size_limit_fail_without_raw_fallback(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "logs" / "codex" / "invalid.jsonl"
    invalid.parent.mkdir(parents=True)
    invalid.write_bytes(b"\xffprivate")
    failed, invalid_output = audit.inspect(tmp_path, invalid, tool="codex")
    assert failed["capture_status"] == "failed"
    assert "private" not in invalid_output.read_text(encoding="utf-8")

    large = tmp_path / "logs" / "codex" / "large.jsonl"
    large.write_bytes(b"x" * (audit.MAX_BYTES + 1))
    limited, _ = audit.inspect(tmp_path, large, tool="codex")
    assert limited["capture_status"] == "failed"
    assert limited["evidence_paths"] == ["logs/codex/large.jsonl"]


def test_traversal_and_source_or_output_symlinks_are_rejected(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.jsonl"
    write_jsonl(outside, codex_events())
    with pytest.raises(audit.AuditError, match="inside repository|traversal"):
        audit.inspect(
            tmp_path,
            f"../{outside.name}",
            tool="codex",
            cycle_id="cycle",
            task_id="task",
        )

    source = tmp_path / "logs" / "codex" / "linked.jsonl"
    source.parent.mkdir(parents=True)
    source.symlink_to(outside)
    with pytest.raises(audit.AuditError, match="symlink"):
        audit.inspect(tmp_path, source, tool="codex")

    source.unlink()
    write_jsonl(source, codex_events())
    packet, output = audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle",
        task_id="task",
    )
    preserved = tmp_path / "preserved.json"
    preserved.write_text("preserve", encoding="utf-8")
    output.unlink()
    output.symlink_to(preserved)
    with pytest.raises(audit.AuditError, match="unsafe"):
        audit.inspect(
            tmp_path,
            source,
            tool="codex",
            cycle_id="cycle",
            task_id="task",
        )
    assert preserved.read_text(encoding="utf-8") == "preserve"
    assert packet["audit_id"] in output.name


def test_replay_is_byte_deterministic_and_tampering_is_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "stable.jsonl"
    write_jsonl(source, codex_events())
    first, output = audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle",
        task_id="task",
    )
    first_bytes = output.read_bytes()
    second, second_output = audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle",
        task_id="task",
    )
    assert first == second
    assert output == second_output
    assert second_output.read_bytes() == first_bytes

    tampered = dict(first)
    tampered["not_validation_evidence"] = False
    errors = audit.validate_packet(tampered, tmp_path)
    assert any("non-validation" in error for error in errors)
    assert any("audit-id" in error for error in errors)

    upgraded = dict(first)
    upgraded["validation_verdict"] = "pass"
    assert audit.validate_packet(upgraded, tmp_path) == [
        "packet top-level schema is not closed"
    ]
    assert consumer.validate_session_audit_packet(upgraded)


def test_system_like_sibling_fields_and_line_flood_are_bounded(
    tmp_path: Path,
) -> None:
    sibling = tmp_path / "logs" / "codex" / "sibling.jsonl"
    events = codex_events()
    events[0]["payload"]["tool_results"] = [{"secret": "must not persist"}]
    events.append({
        "timestamp": "2026-07-11T01:00:03Z",
        "type": "event_msg",
        "payload": {
            "type": "user_message",
            "message": "<permissions secret system injection",
        },
    })
    write_jsonl(sibling, events)
    packet, output = audit.inspect(tmp_path, sibling, tool="codex")
    assert packet["capture_status"] == "quarantined"
    assert [item["code"] for item in packet["findings"]].count(
        "raw_or_tool_event"
    ) == 1
    assert "must not persist" not in output.read_text(encoding="utf-8")

    flood = tmp_path / "logs" / "codex" / "flood.jsonl"
    flood.write_text("{}\n" * (audit.MAX_LINES + 1), encoding="utf-8")
    bounded, bounded_output = audit.inspect(tmp_path, flood, tool="codex")
    assert bounded["capture_status"] == "failed"
    assert bounded["evidence_paths"] == ["logs/codex/flood.jsonl"]
    assert bounded_output.stat().st_size < 10_000


def test_validator_reparses_projection_and_checks_scalar_types(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "reparse.jsonl"
    write_jsonl(source, codex_events())
    packet, _ = audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle",
        task_id="task",
    )
    changed = json.loads(json.dumps(packet))
    changed["event_counts"]["recognized_events"] = 99
    body = dict(changed)
    body.pop("audit_id")
    changed["audit_id"] = audit.derived_id("audit", body)
    assert any(
        "deterministic source projection" in error
        for error in audit.validate_packet(changed, tmp_path)
    )

    bool_size = json.loads(json.dumps(packet))
    bool_size["source"]["size_bytes"] = True
    assert any(
        "source schema" in error
        for error in audit.validate_packet(bool_size, tmp_path)
    )

    bad_bound = json.loads(json.dumps(packet))
    bad_bound["binding"]["cycle_id"] = "../escape"
    assert any(
        "bound identifiers" in error
        for error in audit.validate_packet(bad_bound, tmp_path)
    )


def test_content_addressed_packet_refuses_conflicting_regular_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "immutable.jsonl"
    write_jsonl(source, codex_events())
    _, output = audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle",
        task_id="task",
    )
    output.write_text("conflict\n", encoding="utf-8")
    with pytest.raises(audit.AuditError, match="conflicting bytes"):
        audit.inspect(
            tmp_path,
            source,
            tool="codex",
            cycle_id="cycle",
            task_id="task",
        )


def test_source_tampering_and_arbitrary_evidence_are_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "source.jsonl"
    write_jsonl(source, codex_events())
    packet, _ = audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle",
        task_id="task",
    )
    changed = dict(packet)
    changed["evidence_paths"] = [
        *packet["evidence_paths"],
        "../../secret",
    ]
    body = dict(changed)
    body.pop("audit_id")
    changed["audit_id"] = audit.derived_id("audit", body)
    assert any(
        "evidence" in error
        for error in audit.validate_packet(changed, tmp_path)
    )

    source.write_text("{}\n", encoding="utf-8")
    assert any(
        "source snapshot" in error
        for error in audit.validate_packet(packet, tmp_path)
    )


def test_index_rebuild_is_deterministic_and_only_derived_repair(
    tmp_path: Path,
) -> None:
    for name in ("one", "two"):
        source = tmp_path / "logs" / "codex" / f"{name}.jsonl"
        write_jsonl(source, codex_events(name))
        audit.inspect(
            tmp_path,
            source,
            tool="codex",
            cycle_id=f"cycle-{name}",
            task_id=f"task-{name}",
        )

    first, output = audit.rebuild_index(tmp_path)
    first_bytes = output.read_bytes()
    second, second_output = audit.rebuild_index(tmp_path)

    assert first == second
    assert output == second_output
    assert second_output.read_bytes() == first_bytes
    assert first["repair_class"] == "derived_metadata_only"
    assert first["auto_repair_allowed"] is True
    assert first["not_goal_truth"] is True
    assert first["not_validation_evidence"] is True
    assert [item["audit_id"] for item in first["entries"]] == sorted(
        item["audit_id"] for item in first["entries"]
    )

    third_source = tmp_path / "logs" / "codex" / "three.jsonl"
    write_jsonl(third_source, codex_events("three"))
    audit.inspect(
        tmp_path,
        third_source,
        tool="codex",
        cycle_id="cycle-three",
        task_id="task-three",
    )
    updated, _ = audit.rebuild_index(tmp_path)
    assert len(updated["entries"]) == 3
    assert updated["index_id"] != first["index_id"]


def test_ambiguous_or_unbound_observation_cannot_be_consumable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "binding.jsonl"
    write_jsonl(source, codex_events())
    ambiguous, _ = audit.inspect(
        tmp_path, source, tool="codex", cycle_id="cycle-only"
    )
    assert ambiguous["binding"] == {"status": "ambiguous"}
    assert ambiguous["consumable"] is False
    assert "ambiguous_binding" in {
        item["code"] for item in ambiguous["findings"]
    }

    unbound, _ = audit.inspect(tmp_path, source, tool="codex")
    assert unbound["binding"] == {"status": "unbound"}
    assert unbound["consumable"] is False


def test_unattended_index_repair_requires_validated_nondefault_mode_resolution(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "repair.jsonl"
    write_jsonl(source, codex_events("repair-source"))
    audit.inspect(
        tmp_path,
        source,
        tool="codex",
        cycle_id="cycle-repair",
        task_id="task-repair",
    )
    profile = mode_profile.load_profile(MODE_REGISTRY, "audit-index-repair")
    resolution = mode_profile.resolve_profile(
        profile,
        activation_source="caller_policy",
    )
    resolution_path = tmp_path / ".task" / "mode-resolution.json"
    resolution_path.write_text(json.dumps(resolution), encoding="utf-8")

    receipt, output = audit.auto_rebuild_index(tmp_path, resolution_path)

    assert output == tmp_path / ".task" / "session_audit" / "index.json"
    assert receipt["artifact_kind"] == "workflow_mode_repair_receipt"
    assert receipt["resolution_id"] == resolution["resolution_id"]
    assert receipt["operation"] == "rebuild_index"
    assert receipt["target"] == ".task/session_audit/index.json"
    assert receipt["before_sha256"] is None
    assert receipt["after_sha256"] == audit.digest(output.read_bytes())
    assert receipt["not_goal_truth"] is True
    assert receipt["not_validation_evidence"] is True

    forged = json.loads(json.dumps(resolution))
    forged["activation_source"] = "default"
    forged_path = tmp_path / ".task" / "forged-mode-resolution.json"
    forged_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(audit.AuditError, match="mode resolution is invalid"):
        audit.auto_rebuild_index(tmp_path, forged_path)


def test_cli_is_fail_quiet_for_quarantine_but_validation_detects_tamper(
    tmp_path: Path,
) -> None:
    source = tmp_path / "logs" / "codex" / "bad.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text("{bad\n", encoding="utf-8")
    inspected = subprocess.run(
        [
            sys.executable,
            "-m",
            "audit_session_governance",
            "audit",
            "inspect",
            "--root",
            str(tmp_path),
            "--source",
            str(source),
            "--tool",
            "codex",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=module_env(),
    )
    assert inspected.returncode == 0
    summary = json.loads(inspected.stdout)
    assert summary["capture_status"] == "quarantined"

    packet_path = Path(summary["output"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["not_goal_truth"] = False
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    validated = subprocess.run(
        [
            sys.executable,
            "-m",
            "audit_session_governance",
            "audit",
            "validate",
            "--root",
            str(tmp_path),
            "--packet",
            str(packet_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=module_env(),
    )
    assert validated.returncode == 2
    assert json.loads(validated.stdout)["valid"] is False
