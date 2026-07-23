"""Expose root authority only through its exact signed publication chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import resolve_workspace_path
from .root_grant_transaction import validate_root_grant_receipt_chain


def effective_root_grant_state(
    root: Path,
    grant: dict[str, Any],
    grant_sha256: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    """Project an unpublished grant as draft and verify every published byte."""

    if grant["schema_version"] != 3:
        return state
    root = root.resolve()
    ref = grant["root_materialization_ref"]
    path = resolve_workspace_path(
        root,
        ref,
        "root grant materialization receipt",
        must_exist=False,
    )
    if not path.exists():
        return {**state, "status": "draft"}
    assets = validate_root_grant_receipt_chain(root, ref)
    matching = [
        item
        for item in assets["grant_assets"]
        if item["grant"]["grant_id"] == grant["grant_id"]
    ]
    if (
        len(matching) != 1
        or matching[0]["grant"] != grant
        or matching[0]["grant_sha256"] != grant_sha256
    ):
        raise SystemExit(
            "Root grant materialization receipt does not bind this exact grant."
        )
    return state


__all__ = ("effective_root_grant_state",)
