"""Recover a requested task-pack render after its JSON mutation committed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .packet_io import load_json
from .rendering import render_markdown, write_render
from .storage import canonical_pack_sha256, rel_path, resolve_pack_path


def recover_requested_render(
    root: Path,
    receipt: dict[str, Any],
    *,
    requested: bool,
    language: str,
) -> str | None:
    """Rebuild the exact current-pack projection requested by a replay."""

    if not requested:
        return None
    path = resolve_pack_path(root, str(receipt.get("target_ref") or ""))
    data = load_json(path)
    expected_pack_sha256 = str(receipt.get("after_pack_sha256") or "")
    if canonical_pack_sha256(data) != expected_pack_sha256:
        raise SystemExit(
            "Requested task-pack render recovery no longer matches the committed pack."
        )
    expected = render_markdown(root, path, data, language).encode("utf-8")
    output = write_render(root, path, data, language)
    if not output.is_file() or output.read_bytes() != expected:
        raise SystemExit("Requested task-pack render failed post-write verification.")
    return rel_path(root, output)


__all__ = ["recover_requested_render"]
