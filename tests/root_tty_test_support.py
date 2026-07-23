from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import errno
import fcntl
import json
import os
import pty
import select
import selectors
import signal
import termios
import time
from typing import Any


@dataclass(frozen=True)
class PtyResult:
    status: str
    value: Any
    message: str
    exception_type: str
    output: bytes


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        try:
            written = os.write(descriptor, view)
        except InterruptedError:
            continue
        if written <= 0:
            raise RuntimeError("test result pipe stopped accepting bytes")
        view = view[written:]


def _invoke(action: Callable[[], Any], result_descriptor: int) -> None:
    try:
        value = action()
    except SystemExit as exc:
        record = {
            "status": "system_exit",
            "value": None,
            "message": str(exc),
            "exception_type": type(exc).__name__,
        }
    except BaseException as exc:  # pragma: no cover - diagnostic safety net
        record = {
            "status": "exception",
            "value": None,
            "message": str(exc),
            "exception_type": type(exc).__name__,
        }
    else:
        record = {
            "status": "ok",
            "value": value,
            "message": "",
            "exception_type": "",
        }
    _write_all(
        result_descriptor,
        json.dumps(record, sort_keys=True, default=str).encode("utf-8"),
    )


def _controlling_tty_child(
    slave: int,
    result_descriptor: int,
    action: Callable[[], Any],
    *,
    background: bool,
) -> None:
    os.setsid()
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    os.tcsetpgrp(slave, os.getpgrp())
    if not background:
        _invoke(action, result_descriptor)
        return

    worker = os.fork()
    if worker == 0:
        try:
            os.setpgid(0, 0)
            _invoke(action, result_descriptor)
        finally:
            os.close(result_descriptor)
        os._exit(0)

    os.close(result_descriptor)
    _pid, status = os.waitpid(worker, os.WUNTRACED)
    if os.WIFSTOPPED(status):
        os.kill(worker, signal.SIGKILL)
        os.waitpid(worker, 0)


def run_with_tty(
    action: Callable[[], Any],
    *,
    input_bytes: bytes | None = None,
    background: bool = False,
    timeout: float = 10.0,
) -> PtyResult:
    """Run ``action`` in a child with a real controlling pseudo-terminal."""

    master, slave = pty.openpty()
    result_reader, result_writer = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(master)
        os.close(result_reader)
        try:
            _controlling_tty_child(
                slave,
                result_writer,
                action,
                background=background,
            )
        finally:
            os.close(slave)
            if not background:
                os.close(result_writer)
        os._exit(0)

    os.close(slave)
    os.close(result_writer)
    if input_bytes is not None:
        _write_all(master, input_bytes)

    selector = selectors.DefaultSelector()
    selector.register(master, selectors.EVENT_READ, "tty")
    selector.register(result_reader, selectors.EVENT_READ, "result")
    output = bytearray()
    result_payload = bytearray()
    deadline = time.monotonic() + timeout
    live_descriptors = {master, result_reader}
    try:
        while live_descriptors:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("controlling TTY child did not finish")
            for key, _mask in selector.select(remaining):
                descriptor = key.fd
                try:
                    chunk = os.read(descriptor, 64 * 1024)
                except OSError as exc:
                    if key.data == "tty" and exc.errno == errno.EIO:
                        chunk = b""
                    else:
                        raise
                if chunk:
                    if key.data == "tty":
                        output.extend(chunk)
                    else:
                        result_payload.extend(chunk)
                    continue
                selector.unregister(descriptor)
                os.close(descriptor)
                live_descriptors.remove(descriptor)
    except BaseException:
        os.kill(child, signal.SIGKILL)
        os.waitpid(child, 0)
        raise
    finally:
        selector.close()
        for descriptor in tuple(live_descriptors):
            os.close(descriptor)

    _pid, status = os.waitpid(child, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AssertionError(f"controlling TTY child status was {status}")
    if not result_payload:
        raise AssertionError(
            f"controlling TTY child produced no result; tty={bytes(output)!r}"
        )
    record = json.loads(result_payload.decode("utf-8"))
    return PtyResult(
        status=record["status"],
        value=record["value"],
        message=record["message"],
        exception_type=record["exception_type"],
        output=bytes(output),
    )


def run_without_tty(
    action: Callable[[], Any],
    *,
    input_bytes: bytes | None = None,
    timeout: float = 10.0,
) -> PtyResult:
    """Run ``action`` in a fresh session with no controlling terminal."""

    result_reader, result_writer = os.pipe()
    stdin_reader: int | None = None
    if input_bytes is not None:
        stdin_reader, stdin_writer = os.pipe()
        try:
            _write_all(stdin_writer, input_bytes)
        finally:
            os.close(stdin_writer)
    child = os.fork()
    if child == 0:
        os.close(result_reader)
        try:
            if stdin_reader is not None:
                os.dup2(stdin_reader, 0)
                if stdin_reader != 0:
                    os.close(stdin_reader)
            os.setsid()
            _invoke(action, result_writer)
        finally:
            os.close(result_writer)
        os._exit(0)

    os.close(result_writer)
    if stdin_reader is not None:
        os.close(stdin_reader)
    deadline = time.monotonic() + timeout
    payload = bytearray()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("no-TTY child did not finish")
            ready, _write, _error = select.select(
                [result_reader],
                [],
                [],
                remaining,
            )
            if not ready:
                continue
            chunk = os.read(result_reader, 64 * 1024)
            if not chunk:
                break
            payload.extend(chunk)
    except BaseException:
        os.kill(child, signal.SIGKILL)
        os.waitpid(child, 0)
        raise
    finally:
        os.close(result_reader)

    _pid, status = os.waitpid(child, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AssertionError(f"no-TTY child status was {status}")
    record = json.loads(payload.decode("utf-8"))
    return PtyResult(
        status=record["status"],
        value=record["value"],
        message=record["message"],
        exception_type=record["exception_type"],
        output=b"",
    )


__all__ = ("PtyResult", "run_with_tty", "run_without_tty")
