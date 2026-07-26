"""TTY preflight and parser declarations for the root authorization signer."""

from __future__ import annotations

import argparse
from typing import Any

from .root_tty import preflight


def preflight_tty() -> dict[str, Any]:
    preflight()
    return {"authority_effects": False, "schema_version": 1, "status": "ready", "transport": "controlling_tty"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="root_authorization_signer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight-tty")
    approve = subparsers.add_parser("approve-root-plan")
    approve.add_argument("--workspace", required=True)
    approve.add_argument("--approval-plan-ref", required=True)
    approve.add_argument("--approval-plan-sha256", required=True)
    approve.add_argument("--key-id", required=True)
    activate = subparsers.add_parser("activate-authority-mode")
    activate.add_argument("--workspace", required=True)
    activate.add_argument("--activation-plan-ref", required=True)
    activate.add_argument("--activation-plan-sha256", required=True)
    activate.add_argument("--key-id", required=True)
    return parser
