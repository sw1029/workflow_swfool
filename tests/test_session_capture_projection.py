from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "audit-session-governance" / "scripts"


def module_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(SCRIPTS)
    return env


def run_capture(
    root: Path,
    transcript: Path,
    *,
    tool: str,
    session_id: str = "session-1",
    extra_payload: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "transcript_path": str(transcript),
        "cwd": str(root),
        "hook_event_name": "Stop",
    }
    payload.update(extra_payload or {})
    return subprocess.run(
        [sys.executable, "-m", "audit_session_governance", "capture", "--root", str(root), "--tool", tool],
        env=module_env(),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )


def write_jsonl(path: Path, events: list[Any]) -> None:
    path.write_text(
        "".join(
            json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_codex_capture_rebuilds_minimal_projection_without_raw_fallback(
    tmp_path: Path,
) -> None:
    transcript = tmp_path / "codex-source.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-11T01:00:00Z",
                "type": "session_meta",
                "payload": {"instructions": "RAW-SYSTEM-SECRET"},
            },
            {
                "timestamp": "2026-07-11T01:00:01Z",
                "type": "event_msg",
                "payload": {
                    "type": "user_message",
                    "message": "  user question  ",
                    "images": ["IMAGE-PATH-SECRET"],
                    "local_images": [],
                    "text_elements": [],
                },
            },
            {
                "timestamp": "2026-07-11T01:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "TOOL-PAYLOAD-SECRET",
                },
            },
            {
                "timestamp": "2026-07-11T01:00:03Z",
                "type": "event_msg",
                "payload": {
                    "type": "agent_message",
                    "message": "assistant answer",
                    "phase": "final_answer",
                    "memory_citation": None,
                },
            },
            {
                "timestamp": "2026-07-11T01:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "DUPLICATE-SECRET"}],
                },
            },
        ],
    )

    result = run_capture(tmp_path, transcript, tool="codex")

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    destination = tmp_path / "logs" / "codex" / "session-1.jsonl"
    rendered = destination.read_text(encoding="utf-8")
    assert "RAW-SYSTEM-SECRET" not in rendered
    assert "IMAGE-PATH-SECRET" not in rendered
    assert "TOOL-PAYLOAD-SECRET" not in rendered
    assert "DUPLICATE-SECRET" not in rendered
    assert read_jsonl(destination) == [
        {
            "schema_version": 1,
            "timestamp": "2026-07-11T01:00:01.000000Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "user question"},
        },
        {
            "schema_version": 1,
            "timestamp": "2026-07-11T01:00:03.000000Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "assistant answer"},
        },
    ]
    audited = subprocess.run(
        [
            sys.executable,
            "-m",
            "audit_session_governance",
            "audit",
            "inspect",
            "--root",
            str(tmp_path),
            "--source",
            "logs/codex/session-1.jsonl",
            "--tool",
            "codex",
        ],
        env=module_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert audited.returncode == 0, audited.stderr


def test_claude_capture_keeps_only_text_blocks(tmp_path: Path) -> None:
    transcript = tmp_path / "claude-source.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-11T02:00:00Z",
                "type": "user",
                "cwd": "/PRIVATE-CWD",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "content": "TOOL-RESULT-SECRET"},
                        {"type": "text", "text": "question"},
                    ],
                },
            },
            {
                "timestamp": "2026-07-11T02:00:01Z",
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "model": "PRIVATE-MODEL",
                    "usage": {"input_tokens": 99},
                    "content": [
                        {"type": "thinking", "thinking": "REASONING-SECRET"},
                        {"type": "text", "text": "answer"},
                        {"type": "tool_use", "input": {"token": "TOOL-SECRET"}},
                    ],
                },
            },
            {
                "timestamp": "2026-07-11T02:00:02Z",
                "type": "user",
                "isMeta": True,
                "message": {"role": "user", "content": "META-SECRET"},
            },
        ],
    )

    result = run_capture(tmp_path, transcript, tool="claude-code")

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    destination = tmp_path / "logs" / "claude-code" / "session-1.jsonl"
    rendered = destination.read_text(encoding="utf-8")
    for secret in (
        "/PRIVATE-CWD",
        "TOOL-RESULT-SECRET",
        "PRIVATE-MODEL",
        "REASONING-SECRET",
        "TOOL-SECRET",
        "META-SECRET",
    ):
        assert secret not in rendered
    assert [event["type"] for event in read_jsonl(destination)] == ["user", "assistant"]


def test_malformed_transcript_never_overwrites_with_raw_input(tmp_path: Path) -> None:
    transcript = tmp_path / "broken.jsonl"
    transcript.write_text('{"type":"user"}\nnot-json\nRAW-SECRET', encoding="utf-8")
    destination = tmp_path / "logs" / "codex" / "session-1.jsonl"
    destination.parent.mkdir(parents=True)
    destination.write_text("previous-safe-projection\n", encoding="utf-8")

    result = run_capture(tmp_path, transcript, tool="codex")

    assert result.returncode == 0
    assert result.stdout == ""
    assert "malformed JSONL" in result.stderr
    assert destination.read_text(encoding="utf-8") == "previous-safe-projection\n"
    assert "RAW-SECRET" not in destination.read_text(encoding="utf-8")


def test_no_supported_events_leaves_no_raw_fallback(tmp_path: Path) -> None:
    transcript = tmp_path / "tools-only.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-07-11T03:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "shell",
                    "arguments": "RAW-TOOL-SECRET",
                },
            }
        ],
    )

    result = run_capture(tmp_path, transcript, tool="codex")

    assert result.returncode == 0
    assert result.stdout == ""
    assert "no supported conversation events" in result.stderr
    assert not (tmp_path / "logs" / "codex" / "session-1.jsonl").exists()


def test_symlinked_destination_component_is_rejected(tmp_path: Path) -> None:
    transcript = tmp_path / "source.jsonl"
    write_jsonl(
        transcript,
        [{"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}],
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "logs").symlink_to(outside, target_is_directory=True)

    result = run_capture(tmp_path, transcript, tool="codex")

    assert result.returncode == 0
    assert result.stdout == ""
    assert "output directory is unsafe" in result.stderr
    assert not (outside / "codex" / "session-1.jsonl").exists()


def test_symlinked_transcript_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    write_jsonl(
        source,
        [{"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}],
    )
    transcript = tmp_path / "linked.jsonl"
    transcript.symlink_to(source)

    result = run_capture(tmp_path, transcript, tool="codex")

    assert result.returncode == 0
    assert result.stdout == ""
    assert "symlink" in result.stderr
    assert not (tmp_path / "logs" / "codex" / "session-1.jsonl").exists()


def test_symlinked_destination_file_is_replaced_nowhere(tmp_path: Path) -> None:
    transcript = tmp_path / "source.jsonl"
    write_jsonl(
        transcript,
        [{"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}],
    )
    destination_dir = tmp_path / "logs" / "codex"
    destination_dir.mkdir(parents=True)
    outside = tmp_path / "outside.jsonl"
    outside.write_text("outside-safe\n", encoding="utf-8")
    (destination_dir / "session-1.jsonl").symlink_to(outside)

    result = run_capture(tmp_path, transcript, tool="codex")

    assert result.returncode == 0
    assert result.stdout == ""
    assert "destination is unsafe" in result.stderr
    assert outside.read_text(encoding="utf-8") == "outside-safe\n"


def test_unsafe_session_id_and_oversized_transcript_fail_quiet(tmp_path: Path) -> None:
    transcript = tmp_path / "source.jsonl"
    write_jsonl(
        transcript,
        [{"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}],
    )
    unsafe = run_capture(tmp_path, transcript, tool="codex", session_id="../../escape")
    assert unsafe.returncode == 0
    assert unsafe.stdout == ""
    assert "session_id is missing or unsafe" in unsafe.stderr
    assert not (tmp_path / "escape.jsonl").exists()

    transcript.write_bytes(b" " * (10 * 1024 * 1024 + 1))
    oversized = run_capture(tmp_path, transcript, tool="codex", session_id="bounded")
    assert oversized.returncode == 0
    assert oversized.stdout == ""
    assert "bounded capture size" in oversized.stderr
    assert not (tmp_path / "logs" / "codex" / "bounded.jsonl").exists()
