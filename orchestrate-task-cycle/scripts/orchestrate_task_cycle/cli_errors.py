"""Bounded machine-readable errors for expected CLI contract failures."""

from __future__ import annotations

import json
import sys
from typing import TextIO


MAX_CLI_ERROR_MESSAGE_CHARS = 512


def emit_contract_error(
    code: str,
    error: ValueError,
    *,
    stream: TextIO | None = None,
) -> int:
    """Emit one compact blocked result without changing library exception APIs."""

    message = " ".join(str(error).split()) or "contract rejected"
    if len(message) > MAX_CLI_ERROR_MESSAGE_CHARS:
        message = message[: MAX_CLI_ERROR_MESSAGE_CHARS - 3] + "..."
    json.dump(
        {
            "error": {"code": code, "message": message},
            "mutation_performed": False,
            "status": "block",
        },
        sys.stdout if stream is None else stream,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    (sys.stdout if stream is None else stream).write("\n")
    return 2
