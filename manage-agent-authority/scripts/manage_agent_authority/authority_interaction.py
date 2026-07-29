"""Signed, host-local authority-interaction activations and exact child grants.

The module deliberately treats the convenience mode as a narrowing input.  It
never replaces an operation manifest, evaluation context, sandbox, or the
ordinary reservation/settlement lifecycle.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
from typing import Any

from .artifact_store import verify_binding
from .authority_interaction_broker import (
    _operation_allowed,  # noqa: F401
    activation_child_eligible,
    activation_evidence_unsigned,
    materialize_activation,
    materialize_mode_child,
    publish_activation_evidence,
    status,
    validate_activation_evidence,
    validate_mode_child_source,
)
from .canonical import parse_time
from .root_authority_registry import canonical_json
from .stable_store import publish_immutable, read_regular


SKILL_ROOT = Path(__file__).resolve().parents[2]
CODEX_HOME = SKILL_ROOT.parent.parent
INTERACTION_HOME = CODEX_HOME / "authority-interaction"
CONFIG_PATH = INTERACTION_HOME / "config.toml"
STATE_PATH = INTERACTION_HOME / "state.json"
LAST_ATTEMPT_PATH = INTERACTION_HOME / "last_attempt.json"
TRUST_ANCHOR_REGISTRY = SKILL_ROOT / "root-authorization.trust.json"
ACTIVATION_ROOT = Path(".task/authorization/authority_interaction_activations")
PLAN_ROOT = ACTIVATION_ROOT / "plans" / "sha256"
EVIDENCE_ROOT = ACTIVATION_ROOT / "evidence" / "sha256"
MATERIALIZATION_ROOT = ACTIVATION_ROOT / "materializations"
STATE_ROOT = ACTIVATION_ROOT / "state"
MAX_CONFIG_BYTES = 64 * 1024
MODES = ("manual", "observe", "workspace", "governed")
RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
DECISION_ORDER = {"D0": 0, "D1": 1, "D2": 2, "D3": 3}


DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": 1,
    "enabled": False,
    "default_mode": "governed",
    "activation_scope": "workspace_goal",
    "activation_ttl_days": 30,
    "runtime_mode_policy": "narrow_only",
    "limits": {
        "max_child_grants": 256,
        "max_total_uses": 512,
        "max_bounded_reusable_uses": 8,
        "max_task_lease_uses": 32,
        "max_improvement_lease_uses": 64,
        "max_concurrent_long_runs": 1,
    },
    "profiles": {
        "governed": {
            "max_operation_source_floor": "S2",
            "max_risk": "R2",
            "decision_classes": ["D2", "D3"],
            "mutation_classes": ["local_mutation"],
            "cardinalities": [
                "single_use", "bounded_reusable", "task_lease", "improvement_lease",
            ],
            "operation_groups": [
                "local_edit", "local_worker", "monitor_state", "task_lifecycle",
                "task_topology", "validation_assets", "local_long_run", "local_git_commit",
            ],
        },
        "workspace": {
            "max_operation_source_floor": "S1",
            "max_risk": "R1",
            "decision_classes": ["D3"],
            "mutation_classes": ["local_mutation"],
            "cardinalities": ["single_use", "bounded_reusable", "task_lease"],
            "operation_groups": ["local_edit", "local_worker", "monitor_state", "task_lifecycle", "validation_assets"],
        },
    },
    "always_ask": {
        "ssh_push": True,
        "external_mutation": True,
        "destructive": True,
        "credentials": True,
        "authority_or_policy_change": True,
        "goal_or_design_change": True,
        "dependency_or_model_acquisition": True,
        "selection_retention_maintenance": True,
    },
}

# This is intentionally closed.  Config can select a group or omit it but
# cannot name arbitrary operation IDs.
OPERATION_REGISTRY: dict[str, set[tuple[str, str, str]]] = {
    "local_edit": {
        ("run-task-code-and-log", "edit_local", "1"),
        ("task-md-agent-governance", "implement_local_change", "1"),
    },
    "local_worker": {("orchestrate-task-cycle", "dispatch_local_worker", "1")},
    "monitor_state": {
        ("monitor-running-execution", "record_execution_monitor_event", "1"),
    },
    "task_lifecycle": {
        ("derive-improvement-task", "publish_task", "1"),
        ("maintain-cycle-ledger", "append_cycle_evidence", "1"),
        ("maintain-cycle-ledger", "finalize_cycle_attempt", "1"),
        ("manage-external-advice", "mutate_advice_lifecycle", "1"),
        ("manage-implementation-issues", "mutate_local_issue_lifecycle", "1"),
        ("orchestrate-task-cycle", "retire_terminal_wait_baseline_successor", "1"),
        ("orchestrate-task-cycle", "publish_terminal_wait_baseline_binding", "1"),
        ("orchestrate-task-cycle", "activate_terminal_wait_baseline_settlement", "1"),
        ("task-md-agent-governance", "advance_task_state", "1"),
    },
    "task_topology": {
        ("manage-task-state-index", "mutate_task_state_index", "1"),
        ("orchestrate-task-cycle", "mutate_task_topology", "1"),
        ("orchestrate-task-cycle", "publish_selected_successor_topology", "1"),
        ("orchestrate-task-cycle", "settle_selected_successor_task_state", "1"),
        ("orchestrate-task-cycle", "activate_task_topology_settlement", "1"),
    },
    "validation_assets": {
        ("build-validation-set-with-agents", "mutate_validation_set_assets", "1"),
        ("manage-schema-contracts", "publish_contract", "1"),
        ("normalize-acceptance-and-demo", "publish_acceptance_packet", "1"),
        ("plan-validation-scope", "publish_validation_scope", "1"),
    },
    "local_long_run": {("run-task-code-and-log", "run_long", "1")},
    "local_git_commit": {("repo-change-commit", "finalize_git_state", "1")},
}
ALWAYS_DENY_OPERATION_IDS = {
    "dispatch_external_operation",
    "apply_selection_publication_retention",
    "restore_selection_publication_retention",
    "update_policy",
    "issue_grant",
    "materialize_plan_bound_root_grant",
    "materialize_approved_source_authority_recovery",
}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _json_bytes(value: Any) -> bytes:
    return canonical_json(value)


def _binding(root: Path, path: Path, payload: bytes | None = None) -> dict[str, str]:
    raw = read_regular(path, label="authority-interaction artifact") if payload is None else payload
    assert raw is not None
    return {"ref": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(raw).hexdigest()}


def _require_secure_directory(path: Path, *, create: bool = False) -> None:
    if create and not path.exists():
        path.mkdir(mode=0o700, parents=True)
    try:
        observed = path.lstat()
    except OSError as exc:
        raise SystemExit("authority_interaction_config_unavailable") from exc
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode) or observed.st_uid != os.geteuid() or stat.S_IMODE(observed.st_mode) != 0o700:
        raise SystemExit("authority_interaction_config_unsafe_directory")


def _require_secure_file(path: Path) -> bytes:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise SystemExit("authority_interaction_config_unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode) or observed.st_uid != os.geteuid() or stat.S_IMODE(observed.st_mode) != 0o600:
        raise SystemExit("authority_interaction_config_unsafe_file")
    payload = read_regular(path, label="authority interaction config", max_bytes=MAX_CONFIG_BYTES)
    assert payload is not None
    return payload


def _toml_load(payload: bytes) -> dict[str, Any]:
    try:
        import tomllib  # type: ignore[attr-defined]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError as exc:
            raise SystemExit("authority_interaction_toml_parser_unavailable") from exc
    try:
        value = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, Exception) as exc:
        raise SystemExit("authority_interaction_config_invalid") from exc
    if not isinstance(value, dict):
        raise SystemExit("authority_interaction_config_invalid")
    return value


def _closed(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise SystemExit(f"authority_interaction_{label}_keys_invalid")


def _list_of(value: Any, allowed: set[str], label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SystemExit(f"authority_interaction_{label}_invalid")
    result = sorted(set(value))
    if len(result) != len(value) or not set(result).issubset(allowed):
        raise SystemExit(f"authority_interaction_{label}_invalid")
    return result


def _normalize_profile(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit("authority_interaction_profile_invalid")
    expected = {"max_operation_source_floor", "max_risk", "decision_classes", "mutation_classes", "cardinalities", "operation_groups"}
    _closed(value, expected, "profile")
    source = str(value["max_operation_source_floor"])
    risk = str(value["max_risk"])
    if source not in {"S1", "S2"} or risk not in {"R1", "R2"}:
        raise SystemExit("authority_interaction_profile_expansion_denied")
    return {
        "max_operation_source_floor": source,
        "max_risk": risk,
        "decision_classes": _list_of(value["decision_classes"], {"D2", "D3"}, "decision_classes"),
        "mutation_classes": _list_of(value["mutation_classes"], {"local_mutation"}, "mutation_classes"),
        "cardinalities": _list_of(value["cardinalities"], {"single_use", "bounded_reusable", "task_lease", "improvement_lease"}, "cardinalities"),
        "operation_groups": _list_of(value["operation_groups"], set(OPERATION_REGISTRY), "operation_groups"),
    }


def _normalize_config(value: dict[str, Any]) -> dict[str, Any]:
    _closed(value, {"schema_version", "enabled", "default_mode", "activation_scope", "activation_ttl_days", "runtime_mode_policy", "limits", "profiles", "always_ask"}, "config")
    if value.get("schema_version") != 1 or not isinstance(value.get("enabled"), bool):
        raise SystemExit("authority_interaction_config_invalid")
    if value["default_mode"] not in {"manual", "observe", "workspace", "governed"} or value["activation_scope"] != "workspace_goal" or value["activation_ttl_days"] != 30 or value["runtime_mode_policy"] != "narrow_only":
        raise SystemExit("authority_interaction_config_expansion_denied")
    limits = value.get("limits")
    if not isinstance(limits, dict):
        raise SystemExit("authority_interaction_limits_invalid")
    _closed(limits, set(DEFAULT_CONFIG["limits"]), "limits")
    normalized_limits: dict[str, int] = {}
    for key, maximum in DEFAULT_CONFIG["limits"].items():
        candidate = limits.get(key)
        if not isinstance(candidate, int) or isinstance(candidate, bool) or candidate < 1 or candidate > maximum:
            raise SystemExit("authority_interaction_limit_expansion_denied")
        normalized_limits[key] = candidate
    profiles = value.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != {"workspace", "governed"}:
        raise SystemExit("authority_interaction_profiles_invalid")
    always = value.get("always_ask")
    if not isinstance(always, dict) or set(always) != set(DEFAULT_CONFIG["always_ask"]) or any(item is not True for item in always.values()):
        raise SystemExit("authority_interaction_always_ask_invalid")
    return {
        "schema_version": 1,
        "enabled": value["enabled"],
        "default_mode": value["default_mode"],
        "activation_scope": "workspace_goal",
        "activation_ttl_days": 30,
        "runtime_mode_policy": "narrow_only",
        "limits": normalized_limits,
        "profiles": {key: _normalize_profile(key, profiles[key]) for key in sorted(profiles)},
        "always_ask": {key: True for key in sorted(always)},
    }


def load_config() -> tuple[dict[str, Any], str, bool]:
    """Load secure host config; a missing config is a disabled feature, not an error."""
    if not CONFIG_PATH.exists() and not CONFIG_PATH.is_symlink():
        return _normalize_config(DEFAULT_CONFIG), "absent", False
    _require_secure_directory(INTERACTION_HOME)
    payload = _require_secure_file(CONFIG_PATH)
    return _normalize_config(_toml_load(payload)), hashlib.sha256(payload).hexdigest(), True


def _manifest_paths() -> list[Path]:
    return [
        SKILL_ROOT / "authority.operations.json",
        SKILL_ROOT.parent / "orchestrate-task-cycle" / "authority.operations.json",
        SKILL_ROOT.parent / "repo-change-commit" / "authority.operations.json",
        SKILL_ROOT.parent / "run-task-code-and-log" / "authority.operations.json",
    ]


def manifest_bindings() -> list[dict[str, str]]:
    bindings = []
    for path in _manifest_paths():
        payload = read_regular(path, label="authority interaction operation manifest", max_bytes=512 * 1024)
        assert payload is not None
        bindings.append({"ref": str(path), "sha256": hashlib.sha256(payload).hexdigest()})
    return bindings


def _file_digest(path: Path) -> str:
    try:
        return hashlib.sha256(read_regular(path, label="authority interaction workspace binding", max_bytes=2 * 1024 * 1024) or b"").hexdigest()
    except SystemExit:
        return "absent"


def workspace_identity(root: Path) -> dict[str, Any]:
    root = root.resolve()
    observed = root.stat()
    try:
        common = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-common-dir"], check=True, capture_output=True, text=True, timeout=5).stdout.strip()
        common_path = (root / common).resolve() if not Path(common).is_absolute() else Path(common).resolve()
        git_common = {"path": str(common_path), "device": common_path.stat().st_dev, "inode": common_path.stat().st_ino}
    except (OSError, subprocess.SubprocessError):
        git_common = None
    return {"realpath": str(root), "device": observed.st_dev, "inode": observed.st_ino, "git_common_dir": git_common}


def goal_policy_snapshot(root: Path) -> dict[str, str]:
    return {
        "final_goal_sha256": _file_digest(root / ".agent_goal" / "final_goal.md"),
        "authority_policy_sha256": _file_digest(root / ".agent_goal" / "agent_authority.md"),
        "goal_contract_sha256": _file_digest(root / ".agent_goal" / "goal_contract.yaml"),
    }


def _mode_at_most(mode: str, ceiling: str) -> bool:
    return MODES.index(mode) <= MODES.index(ceiling)


def _runtime_ceiling() -> str:
    raw = " ".join(os.environ.get(key, "") for key in ("CODEX_SANDBOX", "CODEX_SANDBOX_MODE", "CLAUDE_CODE_PERMISSION_MODE"))
    return "manual" if any(token in raw for token in ("danger-full-access", "bypassPermissions")) else "governed"


def current_mode(config: dict[str, Any]) -> str:
    if not config["enabled"]:
        return "manual"
    if not STATE_PATH.exists():
        return config["default_mode"]
    _require_secure_directory(INTERACTION_HOME)
    payload = _require_secure_file(STATE_PATH)
    try:
        state = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("authority_interaction_state_invalid") from exc
    if not isinstance(state, dict) or set(state) != {"schema_version", "mode"} or state.get("schema_version") != 1 or state.get("mode") not in MODES:
        raise SystemExit("authority_interaction_state_invalid")
    return state["mode"] if _mode_at_most(state["mode"], config["default_mode"]) else config["default_mode"]


def set_mode(mode: str, *, disable: bool = False) -> dict[str, Any]:
    config, _digest, _exists = load_config()
    if mode not in MODES:
        raise SystemExit("authority_interaction_mode_invalid")
    if not disable and not _mode_at_most(mode, current_mode(config)):
        raise SystemExit("authority_interaction_mode_raise_requires_activation")
    _require_secure_directory(INTERACTION_HOME, create=True)
    payload = _json_bytes({"schema_version": 1, "mode": "manual" if disable else mode})
    # State is intentionally host-local and does not contain authority evidence.
    temporary = STATE_PATH.with_name(f".{STATE_PATH.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, STATE_PATH)
        os.chmod(STATE_PATH, 0o600)
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass
    return {"status": "disabled" if disable else "downgraded", "mode": "manual" if disable else mode}


def record_last_attempt(*, code: str, plan_binding: dict[str, str] | None, retryable: bool, next_action: str) -> bool:
    """Persist only body-free retry diagnostics for host-side status."""
    try:
        _require_secure_directory(INTERACTION_HOME, create=True)
    except (OSError, SystemExit):
        # A diagnostic cache must never replace the signer/TTY result.  A normal
        # host records it; a restricted execution surface still gets the stable
        # reason code and exact retry command.
        return False
    value = {
        "schema_version": 1,
        "code": str(code),
        "plan_binding": plan_binding,
        "retryable": bool(retryable),
        "next_action": str(next_action),
    }
    payload = _json_bytes(value)
    temporary = LAST_ATTEMPT_PATH.with_name(f".{LAST_ATTEMPT_PATH.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, LAST_ATTEMPT_PATH)
        os.chmod(LAST_ATTEMPT_PATH, 0o600)
    except OSError:
        return False
    finally:
        try:
            temporary.unlink()
        except OSError:
            pass
    return True


def last_attempt() -> dict[str, Any] | None:
    if not LAST_ATTEMPT_PATH.exists():
        return None
    _require_secure_directory(INTERACTION_HOME)
    payload = _require_secure_file(LAST_ATTEMPT_PATH)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("authority_interaction_last_attempt_invalid") from exc
    if not isinstance(value, dict) or set(value) != {"schema_version", "code", "plan_binding", "retryable", "next_action"} or value.get("schema_version") != 1:
        raise SystemExit("authority_interaction_last_attempt_invalid")
    return value


def build_activation_plan(root: Path, *, mode: str, prepared_at: str | None = None) -> tuple[dict[str, str], dict[str, Any]]:
    root = root.resolve()
    config, config_digest, _exists = load_config()
    if not config["enabled"] or mode not in {"workspace", "governed"} or not _mode_at_most(mode, config["default_mode"]):
        raise SystemExit("authority_interaction_activation_not_enabled")
    at = parse_time(prepared_at or _utc_now(), "activation prepared_at")
    expires = at + dt.timedelta(days=30)
    body = {
        "schema_version": 1,
        "artifact_kind": "authority_interaction_activation_plan",
        "prepared_at": at.isoformat(),
        "expires_at": expires.isoformat(),
        "workspace": workspace_identity(root),
        "goal_policy_snapshot": goal_policy_snapshot(root),
        "config_sha256": config_digest,
        "config": config,
        "authority_interaction_mode": mode,
        "broker": {"issuer_rank": "S3", "holder_rank": "S2", "deterministic": True},
        "manifest_bindings": manifest_bindings(),
        "profile": config["profiles"][mode],
        "always_ask": config["always_ask"],
        "limits": config["limits"],
        "non_sliding_ttl_days": 30,
    }
    payload = _json_bytes(body)
    digest = hashlib.sha256(payload).hexdigest()
    path = root / PLAN_ROOT / f"{digest}.json"
    publish_immutable(path, payload)
    return _binding(root, path, payload), body


def load_activation_plan(root: Path, binding: dict[str, str]) -> tuple[dict[str, str], dict[str, Any]]:
    root = root.resolve()
    path = verify_binding(root, binding, "authority interaction activation plan")
    if path.parent != root / PLAN_ROOT or path.name != f"{binding['sha256']}.json":
        raise SystemExit("authority_interaction_plan_binding_invalid")
    try:
        plan = json.loads((read_regular(path, label="authority interaction activation plan") or b"").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("authority_interaction_plan_invalid") from exc
    expected = {"schema_version", "artifact_kind", "prepared_at", "expires_at", "workspace", "goal_policy_snapshot", "config_sha256", "config", "authority_interaction_mode", "broker", "manifest_bindings", "profile", "always_ask", "limits", "non_sliding_ttl_days"}
    if not isinstance(plan, dict) or set(plan) != expected or plan.get("schema_version") != 1 or plan.get("artifact_kind") != "authority_interaction_activation_plan":
        raise SystemExit("authority_interaction_plan_invalid")
    # Re-run all config validation over the signed projection; no caller fields.
    normalized_config = _normalize_config(plan["config"])
    if plan["config"] != normalized_config or plan["authority_interaction_mode"] not in {"workspace", "governed"} or plan["profile"] != normalized_config["profiles"][plan["authority_interaction_mode"]]:
        raise SystemExit("authority_interaction_plan_invalid")
    if parse_time(plan["expires_at"], "activation expiry") - parse_time(plan["prepared_at"], "activation prepared_at") != dt.timedelta(days=30):
        raise SystemExit("authority_interaction_plan_invalid")
    return {"ref": path.relative_to(root).as_posix(), "sha256": binding["sha256"]}, plan


__all__ = [
    "ACTIVATION_ROOT", "CONFIG_PATH", "INTERACTION_HOME", "LAST_ATTEMPT_PATH",
    "STATE_PATH", "activation_child_eligible", "activation_evidence_unsigned",
    "build_activation_plan", "current_mode", "last_attempt", "load_activation_plan",
    "load_config", "materialize_activation", "materialize_mode_child",
    "publish_activation_evidence", "record_last_attempt", "set_mode", "status",
    "validate_activation_evidence", "validate_mode_child_source",
]
