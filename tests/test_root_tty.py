from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import errno
import io
from pathlib import Path

import pytest

from manage_agent_authority import root_authorization_signer as signer
from manage_agent_authority import root_tty
from root_tty_test_support import run_with_tty, run_without_tty


def _assert_root_tty_error(result: object, code: str) -> None:
    assert result.status == "exception"
    assert result.exception_type == "RootTTYError"
    assert result.message == code


def test_exact_confirmation_uses_real_controlling_tty() -> None:
    expected = "APPROVE ROOT PLAN " + ("a" * 64)
    summary = {
        "workspace": "/tmp/example-workspace",
        "approval_plan": {
            "ref": ".task/authorization/root-plan.json",
            "sha256": "a" * 64,
        },
        "grant_count": 1,
    }

    result = run_with_tty(
        lambda: root_tty.confirm_exact(summary, expected),
        input_bytes=(expected + "\n").encode("utf-8"),
    )

    assert result.status == "ok"
    assert result.value is None
    assert b'"grant_count": 1' in result.output
    assert f"Type exactly: {expected}".encode() in result.output


def test_exact_confirmation_accepts_crlf_line_ending() -> None:
    expected = "APPROVE ROOT PLAN " + ("c" * 64)

    result = run_with_tty(
        lambda: root_tty.confirm_exact(None, expected),
        input_bytes=(expected + "\r\n").encode("utf-8"),
    )

    assert result.status == "ok"
    assert result.value is None


@pytest.mark.parametrize(
    ("supplied", "code"),
    [
        ("APPROVE ROOT PLAN " + ("b" * 64) + ".\n", "root_confirmation_mismatch"),
        (" APPROVE ROOT PLAN " + ("b" * 64) + "\n", "root_confirmation_mismatch"),
        ("approve root plan " + ("b" * 64) + "\n", "root_confirmation_mismatch"),
    ],
)
def test_exact_confirmation_does_not_normalize_user_input(
    supplied: str,
    code: str,
) -> None:
    expected = "APPROVE ROOT PLAN " + ("b" * 64)

    result = run_with_tty(
        lambda: root_tty.confirm_exact(None, expected),
        input_bytes=supplied.encode("utf-8"),
    )

    _assert_root_tty_error(result, code)
    assert supplied.rstrip("\n") not in result.message


@pytest.mark.parametrize(
    ("supplied", "code"),
    [
        (b"\x04", "root_confirmation_eof"),
        (b"x" * 513 + b"\n", "root_confirmation_too_long"),
        (b"\xff\n", "root_confirmation_invalid_utf8"),
    ],
)
def test_exact_confirmation_rejects_unbounded_or_malformed_input(
    supplied: bytes,
    code: str,
) -> None:
    result = run_with_tty(
        lambda: root_tty.confirm_exact(None, "APPROVE"),
        input_bytes=supplied,
    )

    _assert_root_tty_error(result, code)


def test_confirmation_rejects_oversized_summary_before_reading() -> None:
    result = run_with_tty(
        lambda: root_tty.confirm_exact(
            {"untrusted_summary": "x" * (1024 * 1024)},
            "APPROVE",
        ),
        input_bytes=b"APPROVE\n",
    )

    _assert_root_tty_error(result, "root_approval_summary_too_large")
    assert len(result.output) < 4096


def test_preflight_rejects_process_without_controlling_tty() -> None:
    result = run_without_tty(root_tty.preflight)

    _assert_root_tty_error(result, "root_tty_unavailable")


def test_confirmation_never_falls_back_to_stdin_without_controlling_tty() -> None:
    expected = "APPROVE ROOT PLAN " + ("d" * 64)

    result = run_without_tty(
        lambda: root_tty.confirm_exact(None, expected),
        input_bytes=(expected + "\n").encode("utf-8"),
    )

    _assert_root_tty_error(result, "root_tty_unavailable")


def test_preflight_rejects_background_process_group() -> None:
    result = run_with_tty(root_tty.preflight, background=True)

    _assert_root_tty_error(result, "root_tty_not_foreground")


def _preflight_main() -> dict[str, object]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = signer.main(["preflight-tty"])
    return {
        "status": status,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }


def test_public_preflight_is_body_free_and_has_no_authority_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    absent_store = tmp_path / "root-authorization"
    absent_registry = tmp_path / "root-authorization.trust.json"
    monkeypatch.setattr(signer, "ROOT_AUTHORIZATION_HOME", absent_store)
    monkeypatch.setattr(signer, "TRUST_ANCHOR_REGISTRY", absent_registry)
    before = list(tmp_path.rglob("*"))

    result = run_with_tty(_preflight_main)

    assert result.status == "ok"
    assert result.value == {
        "status": 0,
        "stdout": (
            '{"authority_effects":false,"schema_version":1,'
            '"status":"ready","transport":"controlling_tty"}\n'
        ),
        "stderr": "",
    }
    assert list(tmp_path.rglob("*")) == before
    assert not absent_store.exists()
    assert not absent_registry.exists()


def test_public_preflight_reports_stable_failure_code_without_tty() -> None:
    result = run_without_tty(_preflight_main)

    assert result.status == "ok"
    assert result.value == {
        "status": 2,
        "stdout": "",
        "stderr": "root_tty_unavailable\n",
    }


def test_preflight_parser_accepts_no_arguments_or_approval_bypasses() -> None:
    parser = signer.build_parser()
    parsed = parser.parse_args(["preflight-tty"])
    assert parsed.command == "preflight-tty"

    for forbidden in (
        "--yes",
        "--stdin",
        "--confirmation",
        "--approval-text",
        "--tty-path",
        "--private-key",
        "--passphrase",
    ):
        with pytest.raises(SystemExit):
            parser.parse_args(["preflight-tty", forbidden])


def test_tty_open_closes_first_descriptor_when_second_open_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened = 71
    calls = 0
    closed: list[int] = []

    def fail_second_open(_path: str, _flags: int) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return opened
        raise OSError(errno.ENXIO, "injected second-open failure")

    monkeypatch.setattr(root_tty.os, "open", fail_second_open)
    monkeypatch.setattr(root_tty.os, "close", closed.append)

    with pytest.raises(root_tty.RootTTYError) as captured:
        root_tty._open_checked_tty()  # noqa: SLF001

    assert captured.value.code == "root_tty_unavailable"
    assert closed == [opened]


def test_tty_prompt_write_retries_eintr_and_partial_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = bytearray()
    calls = 0

    def partial_write(_descriptor: int, payload: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.EINTR, "injected interruption")
        chunk = bytes(payload[:2])
        observed.extend(chunk)
        return len(chunk)

    monkeypatch.setattr(root_tty.os, "write", partial_write)

    root_tty._write_all(73, b"abcdef")  # noqa: SLF001

    assert calls == 4
    assert observed == b"abcdef"
