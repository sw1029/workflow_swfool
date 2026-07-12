#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any


DEFAULT_STEPS = [
    "context",
    "authority",
    "repo_skill_adapter_scan",
    "acceptance",
    "route_plan",
    "validation_scope_plan",
    "validation_set_plan",
    "governance",
    "result_contract",
    "repo_skill_adapter_validate",
    "ledger_append",
    "code_structure_audit",
    "run",
    "qualitative_review",
    "loopback_audit",
    "validation_set_build",
    "visible_increment",
    "repo_skill_gap_analysis",
    "cycle_efficiency_profile",
    "validation_scope_finalize",
    "index_pre_validate",
    "validate",
    "issue",
    "schema_pre_derive",
    "derive",
    "schema_post_derive",
    "index",
    "commit",
    "dashboard",
    "report",
    "closeout_commit",
]

CANONICAL_STEPS = set(DEFAULT_STEPS)

LEDGER_FORMAT_VERSION = 1
SUPPORTED_LEDGER_FORMAT_VERSIONS = {0, LEDGER_FORMAT_VERSION}
TERMINAL_LATCH_KEY_VERSION = 2
CYCLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
EVENT_ID_PATTERN = re.compile(r"^[^\x00-\x20/\\]{1,255}$")

MIN_FIELDS = [
    "format_version",
    "cycle_id",
    "event_id",
    "step",
    "status",
    "reason",
    "task_id",
    "completed_task_id",
    "next_task_id",
    "changed_files",
    "artifacts",
    "artifact_refs",
    "unchanged_refs",
    "validation_verdict",
    "progress_verdict",
    "blockers",
    "code_structure_audit",
    "qualitative_review",
    "anti_loop_progress_gate",
    "validation_set",
    "task_pack_id",
    "task_pack_item_id",
    "task_pack_path",
    "task_pack_status",
    "selected_task_source",
    "promoted_item_id",
    "completed_item_id",
    "blocker_signature",
    "input_delta_gate",
    "terminal_blocker",
    "used_advice",
    "authority_policy",
    "authority_policy_source",
    "created_at",
]

STAGE_STATUS_NORMALIZATION = {
    "success": "complete",
    "succeeded": "complete",
    "block": "blocked",
}

TERMINAL_OBSERVATION_FIELDS = {
    "event_id",
    "step",
    "status",
    "reason",
    "task_id",
    "terminal_justified",
    "terminal_outcome_key",
    "terminal_outcome_family_key",
    "terminal_latch_key_version",
    "blocker_signature",
    "input_state_fingerprint",
    "authority_state_fingerprint",
    "external_state_fingerprint",
    "input_delta",
    "material_delta",
    "required_missing_input_count",
    "authority_policy",
    "authority_policy_source",
    "created_at",
}


def normalize_stage_status(value: Any) -> str:
    if value is None or not str(value).strip():
        raise ValueError("stage event requires an explicit non-empty `status`")
    raw = str(value).strip().lower()
    return STAGE_STATUS_NORMALIZATION.get(raw, raw)


def truthy_delta(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "none", "null", "unchanged", "no_delta"}
    return bool(value)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="microseconds")


def default_cycle_id() -> str:
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"cycle-{stamp}-{uuid.uuid4().hex}"


def validate_cycle_id(cycle_id: str) -> str:
    value = str(cycle_id or "").strip()
    if not CYCLE_ID_PATTERN.fullmatch(value):
        raise ValueError("cycle_id must be 1-128 path-safe letters, digits, dots, underscores, or hyphens")
    return value


def validate_event_id(event_id: Any) -> str:
    value = str(event_id or "").strip()
    if not EVENT_ID_PATTERN.fullmatch(value):
        raise ValueError("event_id must be a non-empty path-free token of at most 255 characters")
    return value


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def cycle_dir(root: Path, cycle_id: str) -> Path:
    resolved_root = root.resolve()
    cycle_root = (resolved_root / ".task" / "cycle").resolve(strict=False)
    try:
        cycle_root.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("cycle ledger root escapes the workspace, including through a symlink") from exc
    path = (cycle_root / validate_cycle_id(cycle_id)).resolve(strict=False)
    try:
        path.relative_to(cycle_root)
    except ValueError as exc:
        raise ValueError("cycle directory escapes .task/cycle, including through a symlink") from exc
    return path


def ledger_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "stage.jsonl"


def current_stage_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "current_stage.json"


def initialization_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / "initialization.json"


def read_initialization_metadata(root: Path, cycle_id: str) -> dict[str, Any]:
    path = initialization_path(root, cycle_id)
    if not path.is_file():
        raise ValueError(f"cycle `{cycle_id}` must be initialized before stage append")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed cycle initialization metadata: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"cycle initialization metadata must be a JSON object: {path}")
    if str(value.get("cycle_id") or "") != cycle_id:
        raise ValueError(f"cycle initialization metadata does not match cycle `{cycle_id}`")
    return value


def ledger_lock_path(root: Path, cycle_id: str) -> Path:
    return cycle_dir(root, cycle_id) / ".ledger.lock"


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def ledger_lock(root: Path, cycle_id: str, *, exclusive: bool):
    directory = cycle_dir(root, cycle_id)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = ledger_lock_path(root, cycle_id)
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+b", closefd=True) as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def durable_append_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    with path.open("ab") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if not existed:
        fsync_directory(path.parent)


def load_json_value(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    path = Path(value)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(value)


def normalize_list(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            result.extend(str(item) for item in value if item is not None and str(item) != "")
        elif isinstance(value, tuple):
            result.extend(str(item) for item in value if item is not None and str(item) != "")
        elif str(value) != "":
            result.append(str(value))
    return result


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def artifact_path(root: Path, artifact: str) -> Path:
    path = Path(artifact)
    return path if path.is_absolute() else root / path


def prior_artifact_refs(root: Path, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    del root  # Historical hashes are immutable event evidence; never re-hash their paths.
    refs: list[dict[str, Any]] = []
    for event in events:
        for ref in event.get("artifact_refs") or []:
            if isinstance(ref, dict) and ref.get("path") and ref.get("sha256"):
                refs.append({"path": str(ref["path"]), "sha256": str(ref["sha256"])})
    return refs


def annotate_artifact_refs(root: Path, event: dict[str, Any], previous_events: list[dict[str, Any]]) -> None:
    previous = prior_artifact_refs(root, previous_events)
    authoritative_unchanged = {(str(ref["path"]), str(ref["sha256"]).lower()) for ref in previous}
    authoritative_unchanged.update(
        terminal_event_reference(previous_event)
        for previous_event in previous_events
        if previous_event.get("terminal_justified") and previous_event.get("event_id")
    )
    artifact_refs: list[dict[str, Any]] = []
    unchanged_refs: list[dict[str, str]] = []
    for supplied in event.get("unchanged_refs") or []:
        if not isinstance(supplied, dict):
            continue
        supplied_path = str(supplied.get("path") or "").strip()
        supplied_hash = str(supplied.get("sha256") or "").strip()
        if supplied_path and supplied_hash:
            if not re.fullmatch(r"[0-9a-f]{64}", supplied_hash.lower()):
                raise ValueError("supplied unchanged_ref requires a full lowercase SHA-256 digest")
            if (supplied_path, supplied_hash.lower()) not in authoritative_unchanged:
                raise ValueError("supplied unchanged_ref does not match prior authoritative path+hash evidence")
            unchanged_refs.append({"path": supplied_path, "sha256": supplied_hash.lower()})
    artifacts = normalize_list(event.get("artifacts"))
    supplied_refs = event.get("artifact_refs") if isinstance(event.get("artifact_refs"), list) else []
    if not artifacts:
        for supplied in supplied_refs:
            if not isinstance(supplied, dict) or not supplied.get("path") or not supplied.get("sha256"):
                raise ValueError("supplied artifact_refs require non-empty path and sha256")
            supplied_path = str(supplied["path"])
            supplied_hash = str(supplied["sha256"])
            current_hash = file_sha256(artifact_path(root, supplied_path))
            if current_hash != supplied_hash:
                raise ValueError(f"supplied artifact_ref hash does not match current artifact: {supplied_path}")
            ref: dict[str, Any] = {"path": supplied_path, "sha256": current_hash, "exists": True}
            prior = next(
                (
                    item
                    for item in reversed(previous)
                    if item.get("sha256") == current_hash and item.get("path") == supplied_path
                ),
                None,
            )
            if prior:
                ref["unchanged_ref"] = {"path": supplied_path, "sha256": current_hash}
                unchanged_refs.append(ref["unchanged_ref"])
            artifact_refs.append(ref)
    for artifact in artifacts:
        digest = file_sha256(artifact_path(root, artifact))
        if not digest:
            artifact_refs.append({"path": artifact, "sha256": None, "exists": False})
            continue
        ref: dict[str, Any] = {"path": artifact, "sha256": digest, "exists": True}
        prior = next(
            (
                item
                for item in reversed(previous)
                if item.get("sha256") == digest and item.get("path") == artifact
            ),
            None,
        )
        if prior and prior.get("path") and prior.get("sha256"):
            ref["unchanged_ref"] = {"path": str(prior["path"]), "sha256": str(prior["sha256"])}
            unchanged_refs.append(ref["unchanged_ref"])
        artifact_refs.append(ref)
    event["artifact_refs"] = artifact_refs
    event["unchanged_refs"] = list(
        {
            (ref["path"], ref["sha256"]): ref
            for ref in unchanged_refs
            if ref.get("path") and ref.get("sha256")
        }.values()
    )


def make_event_id(cycle_id: str, step: str, created_at: str, event: dict[str, Any]) -> str:
    del event
    stamp = created_at.replace(":", "").replace("-", "").split("+")[0]
    return f"{cycle_id}-{step}-{stamp}-{uuid.uuid4().hex}"


def request_fingerprint(cycle_id: str, event: dict[str, Any]) -> str:
    normalized = dict(event)
    normalized["cycle_id"] = cycle_id
    normalized["step"] = str(normalized.get("step") or "").strip()
    normalized["status"] = normalize_stage_status(normalized.get("status"))
    for field in ("changed_files", "artifacts", "blockers"):
        if field in normalized:
            normalized[field] = normalize_list(normalized.get(field))
    for field in (
        "format_version",
        "created_at",
        "artifact_refs",
        "unchanged_refs",
        "request_fingerprint",
        "source_status",
    ):
        normalized.pop(field, None)
    canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def complete_event(cycle_id: str, event: dict[str, Any]) -> dict[str, Any]:
    event = dict(event)
    cycle_id = validate_cycle_id(cycle_id)
    claimed_cycle_id = event.get("cycle_id")
    if claimed_cycle_id is not None and str(claimed_cycle_id) != cycle_id:
        raise ValueError(f"stage event cycle_id `{claimed_cycle_id}` does not match ledger cycle `{cycle_id}`")
    supplied_version = event.get("format_version")
    if supplied_version is not None and (
        isinstance(supplied_version, bool)
        or not isinstance(supplied_version, int)
        or supplied_version not in (0, LEDGER_FORMAT_VERSION)
    ):
        raise ValueError(f"unsupported ledger format_version: {supplied_version}")
    created_at = str(event.get("created_at") or now_iso())
    step = str(event.get("step") or "unknown")
    raw_status = event.get("status")
    event["format_version"] = LEDGER_FORMAT_VERSION
    event["cycle_id"] = cycle_id
    event["created_at"] = created_at
    if event.get("event_id") is None:
        event["event_id"] = validate_event_id(make_event_id(cycle_id, step, created_at, event))
    else:
        event["event_id"] = validate_event_id(event.get("event_id"))
    event["status"] = normalize_stage_status(raw_status)
    if raw_status is not None and event["status"] != str(raw_status).strip().lower():
        event.setdefault("source_status", str(raw_status).strip().lower())
    event.setdefault("reason", "")
    event.setdefault("task_id", None)
    event.setdefault("completed_task_id", None)
    event.setdefault("next_task_id", None)
    event["changed_files"] = normalize_list(event.get("changed_files"))
    event["artifacts"] = normalize_list(event.get("artifacts"))
    event["blockers"] = normalize_list(event.get("blockers"))
    event.setdefault("validation_verdict", None)
    event.setdefault("progress_verdict", None)
    event.setdefault("authority_policy", None)
    event.setdefault("authority_policy_source", None)
    for field in MIN_FIELDS:
        event.setdefault(field, None)
    return event


def validate_event_envelope(
    cycle_id: str,
    event: dict[str, Any],
    allow_noncanonical_step: bool,
) -> dict[str, Any]:
    event = dict(event)
    cycle_id = validate_cycle_id(cycle_id)
    claimed_cycle_id = event.get("cycle_id")
    if claimed_cycle_id is not None and str(claimed_cycle_id) != cycle_id:
        raise ValueError(f"stage event cycle_id `{claimed_cycle_id}` does not match ledger cycle `{cycle_id}`")
    supplied_version = event.get("format_version")
    if supplied_version is not None and (
        isinstance(supplied_version, bool)
        or not isinstance(supplied_version, int)
        or supplied_version not in (0, LEDGER_FORMAT_VERSION)
    ):
        raise ValueError(f"unsupported ledger format_version: {supplied_version}")
    raw_status = event.get("status")
    event["status"] = normalize_stage_status(raw_status)
    if event["status"] != str(raw_status).strip().lower():
        event.setdefault("source_status", str(raw_status).strip().lower())
    raw_step = event.get("step")
    step = str(raw_step).strip() if raw_step is not None else ""
    if not step:
        raise ValueError("stage event requires a non-empty `step`")
    event["step"] = step
    if step not in CANONICAL_STEPS:
        if not allow_noncanonical_step:
            raise ValueError(f"noncanonical stage step `{step}` requires --allow-noncanonical-step")
        event["noncanonical_step"] = True
    if event.get("event_id") is not None:
        event["event_id"] = validate_event_id(event.get("event_id"))
    return event


def content_bound_material_delta(value: Any) -> tuple[str | None, list[str]]:
    if value in (None, False, "", [], {}):
        return None, []
    if not isinstance(value, dict):
        return None, ["material_delta_content_identity"]
    identity_fields = (
        "artifact_sha256",
        "input_state_fingerprint",
        "authority_state_fingerprint",
        "external_state_fingerprint",
        "blocker_signature",
        "delta_sha256",
    )
    identity = {field: value.get(field) for field in identity_fields if value.get(field) not in (None, "")}
    if not identity:
        return None, ["material_delta_content_identity"]
    for field in ("artifact_sha256", "delta_sha256"):
        if field in identity and not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", str(identity[field]).lower()):
            return None, [field]
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), []


def terminal_reopen_contract(transition: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(transition, dict):
        return {}, ["lifecycle_transition_result"]
    transaction_id = str(transition.get("transaction_id") or "").strip()
    normalized: dict[str, Any] = {"transaction_id": transaction_id, "artifacts": {}}
    missing: list[str] = []
    if not transaction_id:
        missing.append("transaction_id")
    artifacts = transition.get("artifacts") if isinstance(transition.get("artifacts"), dict) else {}
    for name in ("seal", "registry", "pack", "index"):
        supplied = artifacts.get(name) if isinstance(artifacts.get(name), dict) else {}
        ref = str(supplied.get("ref") or transition.get(f"{name}_ref") or "").strip()
        sha256 = str(supplied.get("sha256") or transition.get(f"{name}_sha256") or "").strip().lower().removeprefix("sha256:")
        if not ref:
            missing.append(f"{name}_ref")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            missing.append(f"{name}_sha256")
        normalized["artifacts"][name] = {"ref": ref, "sha256": sha256}
    expected_transaction_sha = hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    supplied_transaction_sha = str(transition.get("transaction_sha256") or "").strip().lower().removeprefix("sha256:")
    if supplied_transaction_sha != expected_transaction_sha:
        missing.append("transaction_sha256")
    normalized["transaction_sha256"] = expected_transaction_sha
    return normalized, sorted(set(missing))


def verify_terminal_reopen_receipt(root: Path, transition: Any) -> tuple[bool, list[str]]:
    normalized, missing = terminal_reopen_contract(transition)
    if missing:
        return False, missing
    failures: list[str] = []
    root_resolved = root.resolve()
    for name, artifact in normalized["artifacts"].items():
        raw_ref = Path(str(artifact["ref"]))
        if raw_ref.is_absolute() or "#" in str(artifact["ref"]):
            failures.append(f"{name}_ref")
            continue
        path = (root_resolved / raw_ref).resolve(strict=False)
        try:
            path.relative_to(root_resolved)
        except ValueError:
            failures.append(f"{name}_ref")
            continue
        if file_sha256(path) != artifact["sha256"]:
            failures.append(f"{name}_sha256")
    return not failures, sorted(set(failures))


def terminal_latch_contract(event: dict[str, Any]) -> tuple[int, tuple[str, ...], tuple[str, ...], list[str]]:
    raw_version = event.get("terminal_latch_key_version")
    if raw_version is None:
        # Preserve truly old three-field rows. A blocker/external-state field is
        # evidence of the current five-field contract and must not silently
        # downgrade to v1 when another required identity is missing.
        version = (
            TERMINAL_LATCH_KEY_VERSION
            if any(event.get(field) is not None for field in ("blocker_signature", "external_state_fingerprint"))
            else 1
        )
    elif (
        isinstance(raw_version, bool)
        or not isinstance(raw_version, int)
        or raw_version not in {1, TERMINAL_LATCH_KEY_VERSION}
    ):
        return 0, (), (), ["terminal_latch_key_version"]
    else:
        version = raw_version
    fields = (
        (
            "terminal_outcome_family_key",
            "blocker_signature",
            "input_state_fingerprint",
            "authority_state_fingerprint",
            "external_state_fingerprint",
        )
        if version == 2
        else ("terminal_outcome_family_key", "input_state_fingerprint", "authority_state_fingerprint")
    )
    key = tuple(str(event.get(field) or "").strip() for field in fields)
    missing = [field for field, value in zip(fields, key) if not value]
    return version, fields, key, missing


def terminal_event_reference(event: dict[str, Any]) -> tuple[str, str]:
    event_ref = ".task/cycle/{}/stage.jsonl#{}".format(
        str(event.get("cycle_id") or "unknown_cycle"),
        str(event.get("event_id") or "unknown_event"),
    )
    canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return event_ref, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def terminal_latch_state(previous_events: list[dict[str, Any]], event: dict[str, Any]) -> dict[str, Any]:
    if not event.get("terminal_justified"):
        return {}
    version, _tuple_fields, current_key, missing_fields = terminal_latch_contract(event)
    if missing_fields:
        return {
            "terminal_latch_status": "not_evaluated",
            "terminal_latch_key_version": version or None,
            "terminal_latch_missing_fields": missing_fields,
            "quiescent_terminal_latched": False,
        }
    residuals = event.get("residual_classification") or event.get("residuals") or []
    residual_classes = {
        str(item.get("classification") or item.get("residual_class") or item)
        for item in residuals
        if isinstance(item, (dict, str))
    }
    if residual_classes & {"self_resolvable_local", "offline_recompute", "existing_authority", "unverified"}:
        return {"terminal_latch_status": "prohibited", "quiescent_terminal_latched": False, "terminal_latch_residual_classes": sorted(residual_classes)}
    previous_terminal_rows: list[tuple[dict[str, Any], int, tuple[str, ...]]] = []
    for row in previous_events:
        if not row.get("terminal_justified"):
            continue
        row_version, _row_fields, row_key, row_missing = terminal_latch_contract(row)
        if not row_missing:
            previous_terminal_rows.append((row, row_version, row_key))
    latest_terminal = previous_terminal_rows[-1] if previous_terminal_rows else None
    previous = (
        latest_terminal[0]
        if latest_terminal is not None and latest_terminal[1] == version and latest_terminal[2] == current_key
        else None
    )
    raw_material_delta = event.get("material_delta")
    if raw_material_delta in (None, False, "", [], {}):
        raw_material_delta = event.get("input_delta")
    material_delta_fingerprint, material_delta_errors = content_bound_material_delta(raw_material_delta)
    if material_delta_errors:
        return {
            "terminal_latch_status": "not_evaluated",
            "terminal_latch_key_version": version,
            "terminal_latch_missing_fields": material_delta_errors,
            "quiescent_terminal_latched": False,
        }
    latest_material_delta_fingerprint = None
    if latest_terminal is not None:
        latest_raw_delta = latest_terminal[0].get("material_delta")
        if latest_raw_delta in (None, False, "", [], {}):
            latest_raw_delta = latest_terminal[0].get("input_delta")
        latest_material_delta_fingerprint, _latest_delta_errors = content_bound_material_delta(latest_raw_delta)
    material_delta = bool(
        material_delta_fingerprint and material_delta_fingerprint != latest_material_delta_fingerprint
    )
    if previous is not None and not material_delta:
        prior_ref, prior_sha256 = terminal_event_reference(previous)
        unchanged_streak = int(previous.get("terminal_latch_streak") or 1) + 1
        return {
            "terminal_latch_status": "latched",
            "terminal_latch_key_version": version,
            "quiescent_terminal_latched": True,
            "suppress_full_cycle": True,
            "terminal_latch_streak": unchanged_streak,
            "unchanged_terminal_ref": previous.get("event_id"),
            "unchanged_ref": {
                "prior_packet_ref": prior_ref,
                "prior_packet_sha256": prior_sha256,
                "latch_key": list(current_key),
                "observed_at": str(event.get("created_at") or now_iso()),
                "unchanged_streak": unchanged_streak,
                "material_delta": False,
            },
            "unchanged_refs": [{"path": prior_ref, "sha256": prior_sha256}],
            "terminal_latch_source_cycle_id": previous.get("cycle_id"),
        }
    latest_latched = next((row for row in reversed(previous_events) if row.get("quiescent_terminal_latched")), None)
    # Reopening is meaningful only after a terminal state was actually latched.
    # A merely observed terminal row does not authorize a lifecycle transition.
    reopen_source = latest_latched
    latest_latched_contract = terminal_latch_contract(reopen_source) if reopen_source is not None else None
    key_changed = bool(
        latest_latched_contract is not None
        and not latest_latched_contract[3]
        and (latest_latched_contract[0] != version or latest_latched_contract[2] != current_key)
    )
    if reopen_source is not None and (key_changed or material_delta):
        transition = event.get("lifecycle_transition_result") if isinstance(event.get("lifecycle_transition_result"), dict) else {}
        normalized_transition, transition_errors = terminal_reopen_contract(transition)
        atomic = not transition_errors
        return {
            "terminal_latch_status": "reopened" if atomic else "reopen_incomplete",
            "terminal_latch_key_version": version,
            "quiescent_terminal_latched": False,
            "terminal_latch_source_cycle_id": reopen_source.get("cycle_id"),
            "terminal_latch_key_changed": key_changed,
            "material_delta_fingerprint": material_delta_fingerprint,
            "lifecycle_transition_result": {
                **normalized_transition,
                "atomic": atomic,
                "validation_errors": transition_errors,
            },
        }
    return {
        "terminal_latch_status": "observed",
        "terminal_latch_key_version": version,
        "quiescent_terminal_latched": False,
        "terminal_latch_streak": 1,
    }


def compact_terminal_observation(event: dict[str, Any], latch: dict[str, Any]) -> dict[str, Any]:
    compact = {field: event[field] for field in TERMINAL_OBSERVATION_FIELDS if field in event}
    compact.update(latch)
    compact["event_kind"] = "terminal_latch_observation"
    compact["compact_observation"] = True
    compact["reason"] = str(event.get("reason") or "quiescent terminal observation")
    compact["artifacts"] = []
    compact["changed_files"] = []
    compact["blockers"] = []
    return compact


def validate_stored_event(value: Any, cycle_id: str, line_no: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"ledger line {line_no} must contain a JSON object")
    version = value.get("format_version", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version not in SUPPORTED_LEDGER_FORMAT_VERSIONS:
        raise ValueError(f"unsupported ledger format_version {version!r} on line {line_no}")
    if str(value.get("cycle_id") or "") != cycle_id:
        raise ValueError(f"ledger line {line_no} cycle_id does not match directory cycle `{cycle_id}`")
    if not str(value.get("step") or "").strip():
        raise ValueError(f"ledger line {line_no} lacks a non-empty step")
    if not str(value.get("status") or "").strip():
        raise ValueError(f"ledger line {line_no} lacks a non-empty status")
    validate_event_id(value.get("event_id"))
    return value


def read_events_unlocked(root: Path, cycle_id: str) -> list[dict[str, Any]]:
    path = ledger_path(root, cycle_id)
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed ledger JSON on line {line_no}: {exc}") from exc
            event = validate_stored_event(value, cycle_id, line_no)
            event_id = str(event["event_id"])
            if event_id in seen_event_ids:
                raise ValueError(f"duplicate ledger event_id `{event_id}` on line {line_no}")
            seen_event_ids.add(event_id)
            events.append(event)
    return events


def read_events(root: Path, cycle_id: str) -> list[dict[str, Any]]:
    cycle_id = validate_cycle_id(cycle_id)
    path = ledger_path(root, cycle_id)
    if not path.is_file():
        return []
    with ledger_lock(root, cycle_id, exclusive=False):
        return read_events_unlocked(root, cycle_id)


def read_all_cycle_events(root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cycle_root = root / ".task" / "cycle"
    if not cycle_root.is_dir():
        return events
    for path in sorted(cycle_root.glob("*/stage.jsonl")):
        events.extend(read_events(root, path.parent.name))
    return sorted(
        events,
        key=lambda event: (
            str(event.get("created_at") or ""),
            str(event.get("cycle_id") or ""),
            int(event.get("ledger_sequence") or 0),
        ),
    )


def write_current_unlocked(root: Path, cycle_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_by_step: dict[str, dict[str, Any]] = {}
    malformed_events: list[dict[str, Any]] = []
    for event in events:
        step = str(event.get("step") or "unknown")
        if step in CANONICAL_STEPS:
            latest_by_step[step] = event
        else:
            malformed_events.append(event)
    latest = events[-1] if events else {}
    status = "empty"
    if any(str(event.get("status")).lower() in {"blocked", "failed"} for event in latest_by_step.values()):
        status = "blocked"
    elif latest:
        status = str(latest.get("status") or "unknown")
    current = {
        "format_version": LEDGER_FORMAT_VERSION,
        "cycle_id": cycle_id,
        "updated_at": now_iso(),
        "status": status,
        "latest_event": latest,
        "steps": {step: latest_by_step[step] for step in sorted(latest_by_step)},
        "malformed_event_count": len(malformed_events),
        "malformed_events": malformed_events[-10:],
        "event_count": len(events),
    }
    path = current_stage_path(root, cycle_id)
    atomic_write_text(path, json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return current


def write_current(root: Path, cycle_id: str, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    with ledger_lock(root, cycle_id, exclusive=True):
        stored_events = read_events_unlocked(root, cycle_id)
        effective_events = stored_events if ledger_path(root, cycle_id).is_file() else list(events or [])
        return write_current_unlocked(root, cycle_id, effective_events)


def duplicate_event(previous_events: list[dict[str, Any]], event: dict[str, Any], fingerprint: str) -> dict[str, Any] | None:
    event_id = event.get("event_id")
    if event_id is None:
        return None
    existing = next((row for row in previous_events if row.get("event_id") == event_id), None)
    if existing is None:
        return None
    existing_fingerprint = existing.get("request_fingerprint")
    if existing_fingerprint == fingerprint:
        return existing
    if existing_fingerprint is None:
        comparable = dict(event)
        for key in ("format_version", "created_at", "artifact_refs", "unchanged_refs"):
            comparable.pop(key, None)
        if all(existing.get(key) == value for key, value in comparable.items()):
            return existing
    raise ValueError(f"event_id `{event_id}` already exists with different content")


def append_event(root: Path, cycle_id: str, event: dict[str, Any], allow_noncanonical_step: bool = False) -> dict[str, Any]:
    cycle_id = validate_cycle_id(cycle_id)
    event = validate_event_envelope(cycle_id, event, allow_noncanonical_step)
    fingerprint = request_fingerprint(cycle_id, event)
    path = ledger_path(root, cycle_id)
    with ledger_lock(root, cycle_id, exclusive=True):
        initialization = read_initialization_metadata(root, cycle_id)
        previous_events = read_events_unlocked(root, cycle_id)
        step = str(event.get("step") or "").strip()
        if not previous_events:
            if step != "context":
                raise ValueError("the first canonical stage event must be `context`")
            initialized_task_id = initialization.get("task_id")
            context_task_id = event.get("task_id")
            allow_missing_task = initialization.get("allow_missing_task_for_bootstrap") is True
            if initialized_task_id is not None:
                if str(context_task_id or "").strip() != str(initialized_task_id):
                    raise ValueError("context task_id must match initialization task_id")
            elif not allow_missing_task:
                raise ValueError("missing initialization task_id is allowed only for an explicit bootstrap transaction")
            elif context_task_id is not None and str(context_task_id).strip():
                raise ValueError("task-absent bootstrap context must not invent a task_id")
            elif not (
                event.get("task_absent") is True
                or event.get("task_md_exists") is False
                or (
                    isinstance(event.get("task_md"), dict)
                    and event["task_md"].get("exists") is False
                )
            ):
                raise ValueError("bootstrap context must explicitly record task.md absence")
        elif str(previous_events[0].get("step") or "") != "context":
            raise ValueError("cycle ledger is invalid: first canonical stage event is not `context`")
        (cycle_dir(root, cycle_id) / "packets").mkdir(parents=True, exist_ok=True)
        duplicate = duplicate_event(previous_events, event, fingerprint)
        if duplicate is not None:
            current = write_current_unlocked(root, cycle_id, previous_events)
            return {
                "event": duplicate,
                "event_duplicate": True,
                "current_stage": current,
                "ledger_path": rel_path(root, path),
                "current_stage_path": rel_path(root, current_stage_path(root, cycle_id)),
            }

        latch = terminal_latch_state(previous_events, event)
        if latch.get("terminal_latch_status") == "reopen_incomplete":
            raise ValueError("terminal reopen requires one atomic seal/registry/pack/index lifecycle transition receipt")
        if latch.get("terminal_latch_status") == "reopened":
            verified, receipt_errors = verify_terminal_reopen_receipt(root, event.get("lifecycle_transition_result"))
            if not verified:
                raise ValueError(
                    "terminal reopen receipt failed content verification: " + ", ".join(receipt_errors)
                )
        full_event_suppressed = bool(latch.get("suppress_full_cycle"))
        event_to_write = compact_terminal_observation(event, latch) if full_event_suppressed else {**event, **latch}
        event_to_write["request_fingerprint"] = fingerprint
        event_to_write["ledger_sequence"] = len(previous_events) + 1
        completed = complete_event(cycle_id, event_to_write)
        annotate_artifact_refs(root, completed, previous_events)
        durable_append_json(path, completed)
        current = write_current_unlocked(root, cycle_id, previous_events + [completed])
        return {
            "event": completed,
            "event_suppressed": full_event_suppressed,
            "observation_appended": full_event_suppressed,
            "current_stage": current,
            "ledger_path": rel_path(root, path),
            "current_stage_path": rel_path(root, current_stage_path(root, cycle_id)),
        }


def init_cycle(
    root: Path,
    cycle_id: str | None,
    task_id: str | None,
    reason: str,
    terminal_state: dict[str, Any] | None = None,
    allow_missing_task_for_bootstrap: bool = False,
) -> dict[str, Any]:
    terminal_reopen_result: dict[str, Any] | None = None
    if terminal_state:
        latch = terminal_latch_state(read_all_cycle_events(root), terminal_state)
        if latch.get("terminal_latch_status") == "not_evaluated":
            missing = ", ".join(str(field) for field in latch.get("terminal_latch_missing_fields") or [])
            raise ValueError(f"terminal latch contract is not evaluated; missing or invalid fields: {missing}")
        if latch.get("terminal_latch_status") == "reopen_incomplete":
            raise ValueError("terminal reopen requires one atomic seal/registry/pack/index lifecycle transition receipt")
        if latch.get("terminal_latch_status") == "reopened":
            verified, receipt_errors = verify_terminal_reopen_receipt(root, terminal_state.get("lifecycle_transition_result"))
            if not verified:
                raise ValueError(
                    "terminal reopen receipt failed content verification: " + ", ".join(receipt_errors)
                )
        if latch.get("suppress_full_cycle"):
            source_cycle_id = validate_cycle_id(str(latch.get("terminal_latch_source_cycle_id") or ""))
            observation = dict(terminal_state)
            observation.pop("cycle_id", None)
            observation.setdefault("step", "report")
            observation.setdefault("status", "complete")
            observation_result = append_event(root, source_cycle_id, observation)
            return {
                "cycle_suppressed": True,
                "reason": "quiescent_terminal_latched",
                **latch,
                "observation_cycle_id": source_cycle_id,
                "observation_result": observation_result,
            }
        if latch.get("terminal_latch_status") == "reopened":
            source_cycle_id = validate_cycle_id(str(latch.get("terminal_latch_source_cycle_id") or ""))
            reopen_observation = dict(terminal_state)
            reopen_observation.pop("cycle_id", None)
            reopen_observation.setdefault("step", "report")
            reopen_observation.setdefault("status", "complete")
            reopen_observation.setdefault("event_kind", "terminal_reopen_receipt")
            terminal_reopen_result = append_event(root, source_cycle_id, reopen_observation)
    cycle_id = validate_cycle_id(cycle_id or default_cycle_id())
    if task_id is None and not allow_missing_task_for_bootstrap:
        raise ValueError("task_id is required unless allow_missing_task_for_bootstrap is explicitly enabled")
    if task_id is not None and allow_missing_task_for_bootstrap:
        raise ValueError("allow_missing_task_for_bootstrap is valid only when task_id is absent")
    directory = cycle_dir(root, cycle_id)
    (directory / "packets").mkdir(parents=True, exist_ok=True)
    metadata_path = initialization_path(root, cycle_id)
    expected_reason = str(reason or "cycle ledger initialized")
    with ledger_lock(root, cycle_id, exclusive=True):
        existing_metadata: dict[str, Any] | None = None
        if metadata_path.is_file():
            try:
                loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed cycle initialization metadata: {metadata_path}") from exc
            if isinstance(loaded, dict):
                existing_metadata = loaded
        if existing_metadata is not None:
            if (
                existing_metadata.get("task_id") != task_id
                or str(existing_metadata.get("reason") or "") != expected_reason
                or existing_metadata.get("allow_missing_task_for_bootstrap", False) is not allow_missing_task_for_bootstrap
            ):
                raise ValueError(f"cycle `{cycle_id}` is already initialized with different task or reason")
            metadata = existing_metadata
            cycle_existing = True
        else:
            metadata = {
                "format_version": LEDGER_FORMAT_VERSION,
                "cycle_id": cycle_id,
                "initialized_at": now_iso(),
                "task_id": task_id,
                "reason": expected_reason,
                "storage_bootstrap_only": True,
                "first_canonical_step": "context",
                "allow_missing_task_for_bootstrap": allow_missing_task_for_bootstrap,
            }
            atomic_write_text(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            cycle_existing = False
        events = read_events_unlocked(root, cycle_id)
        current = write_current_unlocked(root, cycle_id, events)
    result = {
        "cycle_id": cycle_id,
        "cycle_dir": rel_path(root, directory),
        "cycle_existing": cycle_existing,
        "initialization": metadata,
        "initialization_path": rel_path(root, metadata_path),
        "current_stage": current,
        "ledger_path": rel_path(root, ledger_path(root, cycle_id)),
        "current_stage_path": rel_path(root, current_stage_path(root, cycle_id)),
    }
    if terminal_reopen_result is not None:
        result["terminal_reopen_result"] = terminal_reopen_result
    return result


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    latest_by_step: dict[str, dict[str, Any]] = {}
    changed_files: list[str] = []
    artifacts: list[str] = []
    unchanged_refs: list[dict[str, Any]] = []
    blockers: list[str] = []
    task_pack_values: list[str] = []
    malformed_events: list[dict[str, Any]] = []
    for event in events:
        step = str(event.get("step") or "unknown")
        if step in CANONICAL_STEPS:
            latest_by_step[step] = event
        else:
            malformed_events.append(event)
        changed_files.extend(normalize_list(event.get("changed_files")))
        artifacts.extend(normalize_list(event.get("artifacts")))
        unchanged_refs.extend(ref for ref in event.get("unchanged_refs") or [] if isinstance(ref, dict))
        blockers.extend(normalize_list(event.get("blockers")))
        task_pack_values.extend(
            normalize_list(
                event.get("task_pack_id"),
                event.get("task_pack_path"),
                event.get("task_pack_status"),
                event.get("task_pack_item_id"),
                event.get("promoted_item_id"),
                event.get("completed_item_id"),
            )
        )
    latest = events[-1] if events else {}
    return {
        "format_version": LEDGER_FORMAT_VERSION,
        "cycle_id": latest.get("cycle_id") if latest else None,
        "event_count": len(events),
        "latest_status": latest.get("status") if latest else None,
        "latest_step": latest.get("step") if latest else None,
        "steps": {step: {"status": event.get("status"), "reason": event.get("reason")} for step, event in latest_by_step.items()},
        "changed_files": sorted(set(changed_files)),
        "artifacts": sorted(set(artifacts)),
        "unchanged_ref_count": len(unchanged_refs),
        "unchanged_refs": unchanged_refs[-20:],
        "blockers": sorted(set(blockers)),
        "task_pack": sorted(set(task_pack_values)),
        "malformed_events": [
            {
                "event_id": event.get("event_id"),
                "step": event.get("step"),
                "status": event.get("status"),
                "reason": event.get("reason"),
            }
            for event in malformed_events[-10:]
        ],
        "validation_verdict": latest.get("validation_verdict") or next((event.get("validation_verdict") for event in reversed(events) if event.get("validation_verdict")), None),
        "progress_verdict": latest.get("progress_verdict") or next((event.get("progress_verdict") for event in reversed(events) if event.get("progress_verdict")), None),
        "task_id": latest.get("task_id") or next((event.get("task_id") for event in reversed(events) if event.get("task_id")), None),
        "completed_task_id": next((event.get("completed_task_id") for event in reversed(events) if event.get("completed_task_id")), None),
        "next_task_id": next((event.get("next_task_id") for event in reversed(events) if event.get("next_task_id")), None),
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# 사이클 대시보드: {summary.get('cycle_id') or 'unknown'}",
        "",
        f"- 이벤트 수(event_count): {summary.get('event_count') or 0}",
        f"- 최신 단계(latest_step): {summary.get('latest_step') or 'none'}",
        f"- 최신 상태(latest_status): {summary.get('latest_status') or 'none'}",
        f"- unchanged_ref 수(unchanged_ref_count): {summary.get('unchanged_ref_count') or 0}",
        f"- 검증 판정(validation_verdict): {summary.get('validation_verdict') or 'not_run'}",
        f"- 진행 판정(progress_verdict): {summary.get('progress_verdict') or 'not_run'}",
        f"- task ID(task_id): {summary.get('task_id') or 'unknown'}",
        f"- 완료 task ID(completed_task_id): {summary.get('completed_task_id') or 'unknown'}",
        f"- 다음 task ID(next_task_id): {summary.get('next_task_id') or 'unknown'}",
        "",
        "## 단계 상태",
    ]
    steps = summary.get("steps") or {}
    for step in DEFAULT_STEPS:
        if step in steps:
            value = steps[step]
            lines.append(f"- {step}: {value.get('status') or 'unknown'} - {value.get('reason') or ''}".rstrip())
    for step in sorted(set(steps) - set(DEFAULT_STEPS)):
        value = steps[step]
        lines.append(f"- {step}: {value.get('status') or 'unknown'} - {value.get('reason') or ''}".rstrip())
    malformed_events = summary.get("malformed_events") or []
    if malformed_events:
        lines.extend(["", "## 비정상 이벤트"])
        for event in malformed_events:
            lines.append(
                f"- {event.get('step') or 'missing_step'}: {event.get('status') or 'unknown'}"
                + (f" - {event.get('reason')}" if event.get("reason") else "")
            )
    for title, key in (("변경 파일", "changed_files"), ("아티팩트", "artifacts"), ("Task Pack", "task_pack"), ("블로커", "blockers")):
        lines.extend(["", f"## {title}"])
        values = summary.get(key) or []
        if values:
            lines.extend(f"- {item}" for item in values)
        else:
            lines.append("- 없음")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Maintain .task/cycle/<cycle-id> stage ledger artifacts.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Initialize a cycle ledger.")
    init_p.add_argument("--cycle-id")
    init_p.add_argument("--task-id")
    init_p.add_argument("--allow-missing-task-for-bootstrap", action="store_true")
    init_p.add_argument("--reason", default="cycle ledger initialized")
    init_p.add_argument("--terminal-state-json", help="Optional terminal state used to suppress an unchanged full-cycle restart.")

    append_p = sub.add_parser("append", help="Append a stage event.")
    append_p.add_argument("--cycle-id", required=True)
    append_p.add_argument("--event-json", help="JSON object, JSON file path, or '-' for stdin.")
    append_p.add_argument("--step")
    append_p.add_argument("--status")
    append_p.add_argument("--reason")
    append_p.add_argument("--task-id")
    append_p.add_argument("--completed-task-id")
    append_p.add_argument("--next-task-id")
    append_p.add_argument("--changed-file", action="append", default=[])
    append_p.add_argument("--artifact", action="append", default=[])
    append_p.add_argument("--blocker", action="append", default=[])
    append_p.add_argument("--validation-verdict")
    append_p.add_argument("--progress-verdict")
    append_p.add_argument("--task-pack-id")
    append_p.add_argument("--task-pack-item-id")
    append_p.add_argument("--task-pack-path")
    append_p.add_argument("--task-pack-status")
    append_p.add_argument("--selected-task-source")
    append_p.add_argument("--promoted-item-id")
    append_p.add_argument("--completed-item-id")
    append_p.add_argument("--blocker-signature")
    append_p.add_argument("--input-delta-gate")
    append_p.add_argument("--terminal-blocker")
    append_p.add_argument("--authority-policy")
    append_p.add_argument("--authority-policy-source")
    append_p.add_argument("--allow-noncanonical-step", action="store_true", help="Allow a noncanonical step and mark it as malformed/noncanonical evidence.")

    render_p = sub.add_parser("render", help="Render a ledger summary.")
    render_p.add_argument("--cycle-id", required=True)
    render_p.add_argument("--format", choices=("json", "markdown"), default="markdown")
    render_p.add_argument("--write-dashboard", action="store_true")

    current_p = sub.add_parser("current", help="Refresh and print current_stage.json.")
    current_p.add_argument("--cycle-id", required=True)

    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.command == "init":
        result = init_cycle(
            root,
            args.cycle_id,
            args.task_id,
            args.reason,
            load_json_value(args.terminal_state_json),
            args.allow_missing_task_for_bootstrap,
        )
    elif args.command == "append":
        event = load_json_value(args.event_json)
        for attr, key in (
            ("step", "step"),
            ("status", "status"),
            ("reason", "reason"),
            ("task_id", "task_id"),
            ("completed_task_id", "completed_task_id"),
            ("next_task_id", "next_task_id"),
            ("validation_verdict", "validation_verdict"),
            ("progress_verdict", "progress_verdict"),
            ("task_pack_id", "task_pack_id"),
            ("task_pack_item_id", "task_pack_item_id"),
            ("task_pack_path", "task_pack_path"),
            ("task_pack_status", "task_pack_status"),
            ("selected_task_source", "selected_task_source"),
            ("promoted_item_id", "promoted_item_id"),
            ("completed_item_id", "completed_item_id"),
            ("blocker_signature", "blocker_signature"),
            ("input_delta_gate", "input_delta_gate"),
            ("terminal_blocker", "terminal_blocker"),
            ("authority_policy", "authority_policy"),
            ("authority_policy_source", "authority_policy_source"),
        ):
            value = getattr(args, attr)
            if value is not None:
                event[key] = value
        if args.changed_file:
            event["changed_files"] = normalize_list(event.get("changed_files"), args.changed_file)
        if args.artifact:
            event["artifacts"] = normalize_list(event.get("artifacts"), args.artifact)
        if args.blocker:
            event["blockers"] = normalize_list(event.get("blockers"), args.blocker)
        result = append_event(root, args.cycle_id, event, allow_noncanonical_step=args.allow_noncanonical_step)
    elif args.command == "render":
        summary = summarize(read_events(root, args.cycle_id))
        if args.write_dashboard:
            dashboard = cycle_dir(root, args.cycle_id) / "dashboard.md"
            atomic_write_text(dashboard, render_markdown(summary))
            summary["dashboard_path"] = rel_path(root, dashboard)
        if args.format == "markdown":
            sys.stdout.write(render_markdown(summary))
            return 0
        result = summary
    else:
        result = write_current(root, args.cycle_id)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
