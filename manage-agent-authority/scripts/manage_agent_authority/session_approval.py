"""Foreground-TTY approval for narrowing an existing signed activation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .authority_interaction import _utc_now
from .root_tty import RootTTYError, confirm_exact
from .session_lease import DEFAULT_BUDGETS
from .session_store import (
    build_host_session_lease,
    build_tty_session_lease,
    reusable_session_lease,
)


def start_tty_session(
    root: str | Path,
    *,
    thread_binding: str,
    provider: str = "codex",
) -> dict[str, Any]:
    """Prompt once and materialize a session-only narrowing lease."""

    workspace = Path(root).resolve(strict=True)
    existing = reusable_session_lease(
        workspace,
        thread_binding=thread_binding,
        provider=provider,
        trust_class="agent_mediated_tty_narrowing",
    )
    if existing is not None:
        return existing
    issued_at = _utc_now()
    identity = hashlib.sha256(
        f"{workspace}\0{provider}\0{thread_binding}\0{issued_at}".encode("utf-8")
    ).hexdigest()
    expected = f"APPROVE-SESSION-{identity[:8].upper()}"
    summary = {
        "action": "start governed workflow session",
        "workspace": str(workspace),
        "scope": "existing signed activation only",
        "budgets": {
            "cycles": 3,
            "agent_actions": (
                f"up to {DEFAULT_BUDGETS['max_agent_actions']}, "
                "also capped by the signed activation"
            ),
            "concurrent_long_runs": 1,
            "commits_per_cycle": 1,
        },
        "always_separate": [
            "R3",
            "push",
            "external or destructive effects",
            "credentials",
            "authority or goal-design changes",
        ],
    }
    try:
        confirm_exact(summary, expected)
    except RootTTYError:
        raise
    receipt = f"tty-narrowing-{identity}"
    return build_tty_session_lease(
        workspace,
        thread_binding=thread_binding,
        provider=provider,
        approval_receipt=receipt,
        issued_at=issued_at,
    )


def start_host_session(
    root: str | Path,
    *,
    thread_binding: str,
    approval_receipt: str,
    provider: str = "codex",
) -> dict[str, Any]:
    """Use a host-supplied receipt as the primary no-extra-prompt path."""

    return build_host_session_lease(
        Path(root).resolve(strict=True),
        thread_binding=thread_binding,
        provider=provider,
        approval_receipt=approval_receipt,
        issued_at=_utc_now(),
    )


def start_session_from_host_or_tty(
    root: str | Path,
    *,
    thread_binding: str,
    host_approval_receipt: str | None,
    provider: str = "codex",
) -> dict[str, Any]:
    """Prefer a trusted host receipt and fall back to one exact TTY prompt."""

    if host_approval_receipt:
        return start_host_session(
            root,
            thread_binding=thread_binding,
            approval_receipt=host_approval_receipt,
            provider=provider,
        )
    return start_tty_session(
        root,
        thread_binding=thread_binding,
        provider=provider,
    )


def public_session_card(lease: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "active",
        "session_id": lease["session_binding"]["session_id"],
        "trust_class": lease["session_binding"]["trust_class"],
        "profile": lease["activation_mode"],
        "risk_ceiling": lease["risk_ceiling"],
        "expires_at": lease["expires_at"],
        "budgets": lease["budgets"],
        "excluded": [
            "R3",
            "push",
            "external or destructive effects",
            "credentials",
            "authority or goal-design changes",
        ],
    }


__all__ = (
    "public_session_card",
    "start_host_session",
    "start_session_from_host_or_tty",
    "start_tty_session",
)
