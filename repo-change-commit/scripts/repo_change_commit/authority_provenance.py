"""Reopen and validate producer-owned authority evidence for one Git commit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .git_embedded_settlement import GitEmbeddedSettlementError


def validate_authority_provenance(
    root: Path,
    intent: dict[str, Any],
    *,
    require_current_state: bool = True,
) -> dict[str, Any]:
    """Validate request, reservation, pre-commit proof, and session lineage."""

    try:
        from manage_agent_authority.canonical import object_sha256
        from manage_agent_authority.contracts import validate_request
        from manage_agent_authority.execution_results import (
            validate_pre_commit_verification,
        )
        from manage_agent_authority.lifecycle import load_reservation
        from manage_agent_authority.projection_io import load_bound_json
        from manage_agent_authority.projection_io import (
            load_grant_artifact,
        )
        from manage_agent_authority.session_lease import (
            validate_session_lease,
        )
    except ImportError as exc:
        raise GitEmbeddedSettlementError(
            "manage-agent-authority is required to validate commit provenance"
        ) from exc

    workspace = root.resolve(strict=True)
    try:
        request, _request_path, request_binding = load_bound_json(
            workspace,
            intent["authority_request"],
            "commit authority request",
        )
        request = validate_request(request)
        reservation, _reservation_path, state = load_reservation(
            workspace,
            intent["authority_reservation"]["ref"],
            intent["authority_reservation"]["sha256"],
        )
        expected_version = int(state["version"])
        if not require_current_state:
            verification_artifact, _path, _binding = load_bound_json(
                workspace,
                intent["precommit_evidence"],
                "commit pre-commit verification",
            )
            reservation_state = verification_artifact.get(
                "reservation_state"
            )
            if not isinstance(reservation_state, dict):
                raise GitEmbeddedSettlementError(
                    "pre-commit verification lacks reservation state"
                )
            expected_version = int(reservation_state["version"])
        validate_pre_commit_verification(
            workspace,
            reservation,
            intent["authority_reservation"],
            intent["precommit_evidence"],
            expected_version=expected_version,
            require_current_state=require_current_state,
        )
        if (
            reservation["request_id"] != request["request_id"]
            or reservation["request_sha256"] != object_sha256(request)
        ):
            raise GitEmbeddedSettlementError(
                "commit authority reservation binds another request"
            )
        if (
            request["skill_id"] != "repo-change-commit"
            or request["operation_id"] != "finalize_git_state"
            or request["operation_version"] != "1"
        ):
            raise GitEmbeddedSettlementError(
                "commit authority request is not finalize_git_state@1"
            )
        for field in ("cycle_id", "task_id"):
            if request[field] != intent[field]:
                raise GitEmbeddedSettlementError(
                    f"commit authority request binds another {field}"
                )
        session_ids: set[str | None] = set()
        for use in reservation["grant_uses"]:
            grant, _digest = load_grant_artifact(
                workspace, str(use["grant_id"])
            )
            session_ids.add(grant.get("session_id"))
        if session_ids != {intent["session_id"]}:
            raise GitEmbeddedSettlementError(
                "commit authority grant session does not match the settlement"
            )

        session_binding = None
        if intent["session_id"] is not None:
            session_path = (
                workspace
                / ".task"
                / "authorization"
                / "sessions"
                / str(intent["session_id"])
                / "session-lease.json"
            )
            if session_path.is_symlink() or not session_path.is_file():
                raise GitEmbeddedSettlementError(
                    "settlement session lease is missing or unsafe"
                )
            lease = validate_session_lease(
                json.loads(session_path.read_text(encoding="utf-8"))
            )
            if (
                lease["session_binding"]["session_id"]
                != intent["session_id"]
                or lease["goal_id"] != intent["goal_id"]
                or (
                    require_current_state
                    and lease["lifecycle"]["status"] != "live"
                )
            ):
                raise GitEmbeddedSettlementError(
                    "settlement session lease does not match live goal authority"
                )
            session_binding = {
                "ref": session_path.relative_to(workspace).as_posix(),
                "sha256": hashlib.sha256(session_path.read_bytes()).hexdigest(),
            }
    except GitEmbeddedSettlementError:
        raise
    except (OSError, ValueError, KeyError, TypeError, SystemExit) as exc:
        raise GitEmbeddedSettlementError(
            f"commit authority provenance is invalid: {exc}"
        ) from exc

    return {
        "authority_request": request_binding,
        "authority_reservation": intent["authority_reservation"],
        "precommit_evidence": intent["precommit_evidence"],
        "session_lease": session_binding,
    }


__all__ = ("validate_authority_provenance",)
