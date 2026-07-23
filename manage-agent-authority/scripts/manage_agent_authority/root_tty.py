"""Fail-closed controlling-TTY confirmation for root authority actions."""

from __future__ import annotations

import errno
import json
import os
import stat
from typing import Any


TTY_PATH = "/dev/tty"
MAX_CONFIRMATION_BYTES = 512
MAX_SUMMARY_BYTES = 1024 * 1024

TTY_UNAVAILABLE = "root_tty_unavailable"
TTY_NOT_INTERACTIVE = "root_tty_not_interactive"
TTY_NOT_FOREGROUND = "root_tty_not_foreground"
TTY_IO_FAILED = "root_tty_io_failed"
SUMMARY_TOO_LARGE = "root_approval_summary_too_large"
CONFIRMATION_EOF = "root_confirmation_eof"
CONFIRMATION_TOO_LONG = "root_confirmation_too_long"
CONFIRMATION_INVALID_UTF8 = "root_confirmation_invalid_utf8"
CONFIRMATION_MISMATCH = "root_confirmation_mismatch"


class RootTTYError(RuntimeError):
    """A stable, body-free root TTY failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _close(descriptor: int | None) -> bool:
    if descriptor is None:
        return True
    try:
        os.close(descriptor)
    except OSError:
        return False
    return True


def _close_checked(
    read_descriptor: int,
    write_descriptor: int,
) -> None:
    write_closed = _close(write_descriptor)
    read_closed = _close(read_descriptor)
    if not write_closed or not read_closed:
        raise RootTTYError(TTY_IO_FAILED)


def _open_checked_tty() -> tuple[int, int]:
    base_flags = (
        getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOCTTY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    read_descriptor: int | None = None
    write_descriptor: int | None = None
    try:
        read_descriptor = os.open(TTY_PATH, os.O_RDONLY | base_flags)
        write_descriptor = os.open(TTY_PATH, os.O_WRONLY | base_flags)
    except OSError as exc:
        _close(write_descriptor)
        _close(read_descriptor)
        raise RootTTYError(TTY_UNAVAILABLE) from exc

    try:
        read_status = os.fstat(read_descriptor)
        write_status = os.fstat(write_descriptor)
        if (
            not stat.S_ISCHR(read_status.st_mode)
            or not stat.S_ISCHR(write_status.st_mode)
            or read_status.st_rdev != write_status.st_rdev
            or not os.isatty(read_descriptor)
            or not os.isatty(write_descriptor)
        ):
            raise RootTTYError(TTY_NOT_INTERACTIVE)
        try:
            foreground_process_group = os.tcgetpgrp(read_descriptor)
        except OSError as exc:
            raise RootTTYError(TTY_IO_FAILED) from exc
        if foreground_process_group != os.getpgrp():
            raise RootTTYError(TTY_NOT_FOREGROUND)
    except BaseException:
        _close(write_descriptor)
        _close(read_descriptor)
        raise
    return read_descriptor, write_descriptor


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    while written < len(view):
        try:
            count = os.write(descriptor, view[written:])
        except OSError as exc:
            if exc.errno == errno.EINTR:
                continue
            raise RootTTYError(TTY_IO_FAILED) from exc
        if count <= 0:
            raise RootTTYError(TTY_IO_FAILED)
        written += count


def _read_confirmation(descriptor: int) -> str:
    payload = bytearray()
    maximum_buffer = MAX_CONFIRMATION_BYTES + 2
    while True:
        if len(payload) >= maximum_buffer:
            raise RootTTYError(CONFIRMATION_TOO_LONG)
        try:
            chunk = os.read(
                descriptor,
                min(128, maximum_buffer - len(payload)),
            )
        except OSError as exc:
            if exc.errno == errno.EINTR:
                continue
            raise RootTTYError(TTY_IO_FAILED) from exc
        if not chunk:
            raise RootTTYError(CONFIRMATION_EOF)
        payload.extend(chunk)
        newline = payload.find(b"\n")
        if newline < 0:
            continue
        line = bytes(payload[:newline])
        if line.endswith(b"\r"):
            line = line[:-1]
        if len(line) > MAX_CONFIRMATION_BYTES:
            raise RootTTYError(CONFIRMATION_TOO_LONG)
        try:
            return line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RootTTYError(CONFIRMATION_INVALID_UTF8) from exc


def _render_prompt(summary: dict[str, Any] | None, expected: str) -> bytes:
    try:
        expected_payload = expected.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise RootTTYError(TTY_IO_FAILED) from exc
    if (
        not expected_payload
        or len(expected_payload) > MAX_CONFIRMATION_BYTES
        or "\r" in expected
        or "\n" in expected
    ):
        raise RootTTYError(CONFIRMATION_TOO_LONG)

    prompt = bytearray()
    if summary is not None:
        try:
            summary_payload = json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8", errors="strict")
        except (TypeError, ValueError, UnicodeEncodeError) as exc:
            raise RootTTYError(TTY_IO_FAILED) from exc
        if len(summary_payload) > MAX_SUMMARY_BYTES:
            raise RootTTYError(SUMMARY_TOO_LARGE)
        prompt.extend(summary_payload)
        prompt.extend(b"\n")
    prompt.extend(b"Type exactly: ")
    prompt.extend(expected_payload)
    prompt.extend(b"\n> ")
    return bytes(prompt)


def preflight() -> None:
    """Verify that this process has a usable foreground controlling TTY."""

    read_descriptor, write_descriptor = _open_checked_tty()
    _close_checked(read_descriptor, write_descriptor)


def confirm_exact(
    summary: dict[str, Any] | None,
    expected: str,
) -> None:
    """Display a bounded summary and require one exact TTY confirmation line."""

    prompt = _render_prompt(summary, expected)
    read_descriptor, write_descriptor = _open_checked_tty()
    failure: BaseException | None = None
    observed = ""
    try:
        _write_all(write_descriptor, prompt)
        observed = _read_confirmation(read_descriptor)
    except BaseException as exc:
        failure = exc
    try:
        _close_checked(read_descriptor, write_descriptor)
    except RootTTYError as exc:
        if failure is None:
            failure = exc
    if failure is not None:
        raise failure
    if observed != expected:
        raise RootTTYError(CONFIRMATION_MISMATCH)


__all__ = [
    "CONFIRMATION_EOF",
    "CONFIRMATION_INVALID_UTF8",
    "CONFIRMATION_MISMATCH",
    "CONFIRMATION_TOO_LONG",
    "MAX_CONFIRMATION_BYTES",
    "MAX_SUMMARY_BYTES",
    "RootTTYError",
    "SUMMARY_TOO_LARGE",
    "TTY_IO_FAILED",
    "TTY_NOT_FOREGROUND",
    "TTY_NOT_INTERACTIVE",
    "TTY_UNAVAILABLE",
    "confirm_exact",
    "preflight",
]
