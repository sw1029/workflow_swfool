"""Bounded subprocess capture for the fixed owner-validator registry."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
import selectors
import stat
import subprocess
import sys
import time
from typing import Sequence


MAX_OWNER_VALIDATOR_STDOUT_BYTES = 256 * 1024
MAX_OWNER_VALIDATOR_STDERR_BYTES = 64 * 1024
ISOLATED_MODULE_BOOTSTRAP = (
    "import runpy,sys;"
    "count=int(sys.argv[1]);"
    "roots=sys.argv[2:2+count];"
    "module=sys.argv[2+count];"
    "arguments=sys.argv[3+count:];"
    "sys.path[:0]=roots;"
    "sys.argv=[module,*arguments];"
    "runpy.run_module(module,run_name='__main__',alter_sys=True)"
)


def isolated_owner_validator_argv(
    module: str,
    arguments: Sequence[str],
    import_roots: Sequence[Path],
) -> list[str]:
    """Build a CPython 3.10+ owner-validator command without cwd imports."""

    if (
        not module
        or "\x00" in module
        or any(not isinstance(argument, str) or "\x00" in argument for argument in arguments)
    ):
        raise ValueError("Owner validator execution requires a module and import roots.")
    roots: list[str] = []
    for root in import_roots:
        if not root.is_absolute():
            raise ValueError(
                "Owner validator import roots must be canonical real directories."
            )
        try:
            resolved = root.resolve(strict=True)
            mode = root.lstat().st_mode
        except OSError as exc:
            raise ValueError("Owner validator import roots must exist.") from exc
        if (
            root != resolved
            or stat.S_ISLNK(mode)
            or not stat.S_ISDIR(mode)
        ):
            raise ValueError(
                "Owner validator import roots must be canonical real directories."
            )
        roots.append(str(root))
    if not roots:
        raise ValueError("Owner validator execution requires import roots.")
    return [
        sys.executable,
        "-B",
        "-I",
        "-c",
        ISOLATED_MODULE_BOOTSTRAP,
        str(len(roots)),
        *roots,
        module,
        *arguments,
    ]


def _decode(value: bytearray) -> str:
    return bytes(value).decode("utf-8", errors="replace")


def run_bounded_owner_validator(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    """Capture both pipes incrementally and kill on timeout or byte overflow."""

    process = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None and process.stderr is not None
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {
        "stdout": MAX_OWNER_VALIDATOR_STDOUT_BYTES,
        "stderr": MAX_OWNER_VALIDATOR_STDERR_BYTES,
    }
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + timeout
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)
            events = selector.select(remaining)
            if not events:
                raise subprocess.TimeoutExpired(argv, timeout)
            for key, _ in events:
                name = key.data
                buffer = buffers[name]
                chunk = os.read(key.fd, min(64 * 1024, limits[name] + 1 - len(buffer)))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffer.extend(chunk)
                if len(buffer) > limits[name]:
                    raise SystemExit(
                        f"Registered owner validator {name} exceeds the "
                        f"{limits[name]}-byte safety limit."
                    )
        returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except BaseException:
        if process.poll() is None:
            process.kill()
        with contextlib.suppress(subprocess.SubprocessError):
            process.wait(timeout=1)
        raise
    finally:
        selector.close()
        process.stdout.close()
        process.stderr.close()
    return subprocess.CompletedProcess(
        argv,
        returncode,
        stdout=_decode(buffers["stdout"]),
        stderr=_decode(buffers["stderr"]),
    )


__all__ = (
    "ISOLATED_MODULE_BOOTSTRAP",
    "MAX_OWNER_VALIDATOR_STDERR_BYTES",
    "MAX_OWNER_VALIDATOR_STDOUT_BYTES",
    "isolated_owner_validator_argv",
    "run_bounded_owner_validator",
)
