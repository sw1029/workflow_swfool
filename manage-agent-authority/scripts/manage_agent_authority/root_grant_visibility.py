"""Expose root authority only through its exact signed publication chain."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from .canonical import resolve_workspace_path
from .root_grant_transaction import validate_root_grant_receipt_chain


_ACTIVE_RECEIPT_CACHE: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar(
    "authority_root_grant_receipt_cache",
    default=None,
)


@contextmanager
def root_grant_receipt_cache() -> Iterator[None]:
    """Reuse receipt validation only within one explicit grant-list read."""

    token = _ACTIVE_RECEIPT_CACHE.set({})
    try:
        yield
    finally:
        _ACTIVE_RECEIPT_CACHE.reset(token)


def effective_root_grant_state(
    root: Path,
    grant: dict[str, Any],
    grant_sha256: str,
    state: dict[str, Any],
    *,
    receipt_cache: dict[str, dict[str, Any]] | None = None,
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
    active_cache = (
        receipt_cache if receipt_cache is not None else _ACTIVE_RECEIPT_CACHE.get()
    )
    assets = active_cache.get(ref) if active_cache is not None else None
    if assets is None:
        assets = validate_root_grant_receipt_chain(root, ref)
        if active_cache is not None:
            active_cache[ref] = assets
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


__all__ = ("effective_root_grant_state", "root_grant_receipt_cache")
