"""Tracked session-lease materialization from an eligible signed activation."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from . import authority_interaction as interaction
from .session_binding import (
    build_session_binding,
    canonical_bytes,
    sha256_value,
)
from .session_lease import (
    DEFAULT_BUDGETS,
    build_session_lease,
    update_liveness,
    validate_session_lease,
)
from .session_registry import (
    SessionRegistryError as SessionStoreError,
    locked_session_registry,
    matching_session_leases_locked,
    reusable_scope_lease,
    scope_rows,
)


def _workspace_id(root: Path) -> str:
    identity = interaction.workspace_identity(root)
    digest = hashlib.sha256(canonical_bytes(identity)).hexdigest()
    return f"workspace-{digest[:32]}"


def _eligible_activation(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    status = interaction.status(root)
    current_mode = str(status.get("authority_interaction_mode") or "")
    rows: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = []
    for row in status.get("activations") or []:
        if not isinstance(row, dict) or row.get("eligible") is not True:
            continue
        plan_binding = row.get("activation_plan")
        if not isinstance(plan_binding, dict):
            continue
        try:
            _binding, plan = interaction.load_activation_plan(root, plan_binding)
        except SystemExit:
            continue
        plan_mode = str(plan.get("authority_interaction_mode") or "")
        if plan_mode not in {"workspace", "governed"}:
            continue
        if current_mode == "governed" and plan_mode != "governed":
            continue
        rank = 0 if plan_mode == current_mode else 1
        rows.append((rank, str(plan.get("prepared_at") or ""), row, plan))
    if not rows:
        raise SessionStoreError(
            "no eligible signed workspace activation is available"
        )
    best_rank = min(item[0] for item in rows)
    _rank, _prepared, row, plan = max(
        (item for item in rows if item[0] == best_rank),
        key=lambda item: item[1],
    )
    return row, plan


def _lease_path(root: Path, lease: dict[str, Any]) -> Path:
    ref = Path(lease["session_binding"]["session_ref"])
    if ref.is_absolute() or ".." in ref.parts:
        raise SessionStoreError("session lease path is unsafe")
    path = root / ref
    current = root
    for part in ref.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise SessionStoreError("session lease path traverses a symlink")
    if path.is_symlink():
        raise SessionStoreError("session lease target must not be a symlink")
    return path


def write_session_lease(
    root: Path,
    lease: dict[str, Any],
    *,
    expected_state_sha256: str | None = None,
) -> Path:
    normalized = validate_session_lease(lease)
    path = _lease_path(root, normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    directory_descriptor = os.open(
        path.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        fcntl.flock(directory_descriptor, fcntl.LOCK_EX)
        if path.is_symlink():
            raise SessionStoreError(
                "session lease target must not be a symlink"
            )
        if path.exists():
            try:
                current = validate_session_lease(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (ValueError, json.JSONDecodeError) as exc:
                raise SessionStoreError(
                    "existing session lease is invalid"
                ) from exc
            if current == normalized:
                return path
            if expected_state_sha256 is None:
                raise SessionStoreError("session lease already exists")
            if current["state_sha256"] != expected_state_sha256:
                raise SessionStoreError(
                    "session lease compare-and-swap failed"
                )
        elif expected_state_sha256 is not None:
            raise SessionStoreError(
                "session lease disappeared before update"
            )
        descriptor, temporary = tempfile.mkstemp(
            prefix=".session-lease-", dir=path.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.fsync(directory_descriptor)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    finally:
        fcntl.flock(directory_descriptor, fcntl.LOCK_UN)
        os.close(directory_descriptor)
    return path


def _goal_identifiers(plan: dict[str, Any]) -> tuple[str, str]:
    snapshot = plan["goal_policy_snapshot"]
    goal_digest = str(snapshot["final_goal_sha256"])
    if goal_digest == "absent":
        goal_digest = str(snapshot["goal_contract_sha256"])
    identity = hashlib.sha256(goal_digest.encode("utf-8")).hexdigest()
    return f"goal-{identity[:24]}", f"goal-family-{identity[:24]}"


def reusable_session_lease(
    root: str | Path,
    *,
    thread_binding: str,
    provider: str,
    trust_class: str,
    approval_receipt: str | None = None,
) -> dict[str, Any] | None:
    """Return the one compatible live lease for the current activation."""

    workspace = Path(root).resolve(strict=True)
    with locked_session_registry(
        workspace, create=False, exclusive=True
    ) as registry:
        row, _plan = _eligible_activation(workspace)
        if registry is None:
            return None
        rows = matching_session_leases_locked(
            workspace, registry, thread_binding=thread_binding
        )
        scoped = scope_rows(
            rows,
            workspace_identity=_workspace_id(workspace),
            thread_binding=thread_binding,
            activation_evidence_id=str(row["activation_id"]),
        )
        return reusable_scope_lease(
            scoped,
            provider=provider,
            trust_class=trust_class,
            approval_receipt=approval_receipt,
        )


def build_session_lease_from_approval(
    root: str | Path,
    *,
    thread_binding: str,
    provider: str,
    approval_receipt: str,
    issued_at: str,
    trust_class: str,
) -> dict[str, Any]:
    """Narrow one eligible signed activation to the current host thread."""

    workspace = Path(root).resolve(strict=True)
    with locked_session_registry(
        workspace, create=True, exclusive=True
    ) as registry:
        assert registry is not None
        row, plan = _eligible_activation(workspace)
        workspace_identity = _workspace_id(workspace)
        rows = matching_session_leases_locked(
            workspace, registry, thread_binding=thread_binding
        )
        scoped = scope_rows(
            rows,
            workspace_identity=workspace_identity,
            thread_binding=thread_binding,
            activation_evidence_id=str(row["activation_id"]),
        )
        existing = reusable_scope_lease(
            scoped,
            provider=provider,
            trust_class=trust_class,
            approval_receipt=approval_receipt,
        )
        if existing is not None:
            return existing
        goal_id, task_family = _goal_identifiers(plan)
        snapshot = plan["goal_policy_snapshot"]
        manifest_digest = hashlib.sha256(
            canonical_bytes(plan["manifest_bindings"])
        ).hexdigest()
        binding = build_session_binding(
            workspace_identity=workspace_identity,
            provider=provider,
            thread_binding=thread_binding,
            activation_evidence_id=str(row["activation_id"]),
            trust_class=trust_class,
            approval_receipt=approval_receipt,
        )
        limits = plan["limits"]
        lease = build_session_lease(
            session_binding=binding,
            goal_id=goal_id,
            task_family=task_family,
            activation_mode=str(plan["authority_interaction_mode"]),
            activation_risk_ceiling=str(plan["profile"]["max_risk"]),
            allowed_operation_groups=plan["profile"]["operation_groups"],
            goal_digest=str(snapshot["final_goal_sha256"]),
            policy_digest=str(snapshot["authority_policy_sha256"]),
            manifest_digest=manifest_digest,
            issued_at=issued_at,
            expires_at=str(plan["expires_at"]),
            budgets={
                "max_cycles": 3,
                "max_agent_actions": min(
                    DEFAULT_BUDGETS["max_agent_actions"],
                    int(limits["max_total_uses"]),
                ),
                "max_concurrent_long_runs": int(
                    limits["max_concurrent_long_runs"]
                ),
                "max_commits_per_cycle": 1,
            },
        )
        write_session_lease(workspace, lease)
        return lease


def build_tty_session_lease(
    root: str | Path,
    *,
    thread_binding: str,
    provider: str,
    approval_receipt: str,
    issued_at: str,
) -> dict[str, Any]:
    """Use a foreground TTY confirmation as the bounded fallback receipt."""

    return build_session_lease_from_approval(
        root,
        thread_binding=thread_binding,
        provider=provider,
        approval_receipt=approval_receipt,
        issued_at=issued_at,
        trust_class="agent_mediated_tty_narrowing",
    )


def build_host_session_lease(
    root: str | Path,
    *,
    thread_binding: str,
    provider: str,
    approval_receipt: str,
    issued_at: str,
) -> dict[str, Any]:
    """Bind a host-issued session approval receipt without another prompt."""

    return build_session_lease_from_approval(
        root,
        thread_binding=thread_binding,
        provider=provider,
        approval_receipt=approval_receipt,
        issued_at=issued_at,
        trust_class="platform_host_receipt",
    )


def matching_session_leases(
    root: str | Path, *, thread_binding: str | None
) -> list[tuple[Path, dict[str, Any]]]:
    workspace = Path(root).resolve(strict=True)
    with locked_session_registry(
        workspace, create=False, exclusive=False
    ) as registry:
        if registry is None:
            return []
        return matching_session_leases_locked(
            workspace, registry, thread_binding=thread_binding
        )


def stop_matching_session(
    root: str | Path, *, thread_binding: str, stopped_at: str
) -> dict[str, Any]:
    rows = [
        row
        for row in matching_session_leases(root, thread_binding=thread_binding)
        if row[1]["lifecycle"]["status"] == "live"
    ]
    if len(rows) != 1:
        raise SessionStoreError("exactly one live matching session is required")
    _path, lease = rows[0]
    stopped = update_liveness(
        lease, at=stopped_at, host_receipt_live=False, stop=True
    )
    write_session_lease(
        Path(root).resolve(strict=True),
        stopped,
        expected_state_sha256=lease["state_sha256"],
    )
    return stopped


def session_child_grant_count(root: Path, session_id: str) -> int:
    from .contracts import validate_grant

    directory = root / ".task" / "authorization" / "grants"
    if directory.is_symlink() or not directory.is_dir():
        return 0
    grant_ids: set[str] = set()
    for path in directory.glob("*.json"):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            grant = validate_grant(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError, json.JSONDecodeError, SystemExit):
            continue
        if grant.get("session_id") == session_id:
            grant_ids.add(str(grant["grant_id"]))
    return len(grant_ids)


def session_status(
    root: str | Path, *, thread_binding: str | None
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    rows = matching_session_leases(
        workspace, thread_binding=thread_binding
    )

    def remaining(path: Path, lease: dict[str, Any]) -> dict[str, int]:
        budgets = lease["budgets"]
        usage = lease["usage"]
        session_child_actions = session_child_grant_count(
            workspace,
            lease["session_binding"]["session_id"],
        )
        workflow_path = path.with_name("workflow-session.json")
        if workflow_path.is_file() and not workflow_path.is_symlink():
            try:
                workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
                material = {
                    key: value
                    for key, value in workflow.items()
                    if key != "state_sha256"
                }
                if (
                    workflow.get("artifact_kind")
                    == "orchestrate_continuation_session"
                    and workflow.get("session_id")
                    == lease["session_binding"]["session_id"]
                    and workflow.get("budgets") == budgets
                    and workflow.get("state_sha256")
                    == sha256_value(material)
                    and isinstance(workflow.get("usage"), dict)
                    and set(workflow["usage"])
                    == {
                        "cycles",
                        "agent_actions",
                        "active_long_runs",
                        "commits_by_cycle",
                    }
                ):
                    usage = {
                        **workflow["usage"],
                        "agent_actions": max(
                            int(workflow["usage"]["agent_actions"]),
                            session_child_actions,
                        ),
                    }
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        usage = {
            **usage,
            "agent_actions": max(
                int(usage["agent_actions"]), session_child_actions
            ),
        }
        return {
            "cycles": max(0, budgets["max_cycles"] - int(usage["cycles"])),
            "agent_actions": max(
                0,
                budgets["max_agent_actions"] - int(usage["agent_actions"]),
            ),
            "long_run_slots": max(
                0,
                budgets["max_concurrent_long_runs"]
                - len(usage["active_long_runs"]),
            ),
        }

    return {
        "status": "ok",
        "sessions": [
            {
                "session_id": lease["session_binding"]["session_id"],
                "trust_class": lease["session_binding"]["trust_class"],
                "profile": lease["activation_mode"],
                "risk_ceiling": lease["risk_ceiling"],
                "lifecycle": lease["lifecycle"]["status"],
                "expires_at": lease["expires_at"],
                "remaining": remaining(path, lease),
            }
            for path, lease in rows
        ],
    }


__all__ = (
    "SessionStoreError",
    "build_host_session_lease",
    "build_session_lease_from_approval",
    "build_tty_session_lease",
    "matching_session_leases",
    "reusable_session_lease",
    "session_child_grant_count",
    "session_status",
    "stop_matching_session",
    "write_session_lease",
)
