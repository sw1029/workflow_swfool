from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .constants import (
    LEDGER_FORMAT_VERSION,
    STAGE_COMPILER_PROTOCOL_VERSION,
)
from .compiled_events import append_compiled_terminal_lifecycle
from .current_projection import stage_compiler_protocol_version as _protocol_version
from .event_model import default_cycle_id, now_iso
from .initialization_provenance import (
    PROVENANCE_SCHEMA_VERSION,
    PROVENANCE_VERSION_FIELD,
    provenance_path,
    publish_initialization_provenance,
)
from .initialization_contract import (
    require_existing_v1_recovery,
    requested_contract_versions as _requested_contract_versions,
)
from .repository import (
    AtomicTextWriter,
    _write_current_unlocked,
    read_all_cycle_events,
    read_events_unlocked,
)
from .support import (
    atomic_write_text,
    current_stage_path,
    cycle_dir,
    initialization_path,
    ledger_lock,
    ledger_path,
    read_initialization_metadata,
    rel_path,
    validate_cycle_id,
)
from .semantic_seeds import make_terminal_lifecycle_seed
from .terminal import terminal_latch_state, verify_terminal_reopen_receipt
from .workflow_contract import (
    require_cycle_mutation_contract,
    workflow_contract_state,
)


EventAppender = Callable[..., dict[str, Any]]


def cli_init_protocol(
    root: Path,
    cycle_id: str | None,
    requested: int | None,
) -> int | None:
    """Default new CLI cycles to v2 without migrating initialized cycles."""

    if requested is not None:
        return requested
    if cycle_id is None:
        return STAGE_COMPILER_PROTOCOL_VERSION
    return (
        None
        if initialization_path(root, cycle_id).is_file()
        else STAGE_COMPILER_PROTOCOL_VERSION
    )


def _validate_terminal_state(
    root: Path,
    terminal_state: dict[str, Any],
) -> dict[str, Any]:
    latch = terminal_latch_state(read_all_cycle_events(root), terminal_state)
    if latch.get("terminal_latch_status") == "not_evaluated":
        missing = ", ".join(str(field) for field in latch.get("terminal_latch_missing_fields") or [])
        raise ValueError(f"terminal latch contract is not evaluated; missing or invalid fields: {missing}")
    if latch.get("terminal_latch_status") == "reopen_incomplete":
        raise ValueError("terminal reopen requires one atomic seal/registry/pack/index lifecycle transition receipt")
    if latch.get("terminal_latch_status") == "reopened":
        verified, receipt_errors = verify_terminal_reopen_receipt(
            root, terminal_state.get("lifecycle_transition_result")
        )
        if not verified:
            raise ValueError("terminal reopen receipt failed content verification: " + ", ".join(receipt_errors))
    return latch


def _terminal_observation(
    root: Path,
    terminal_state: dict[str, Any],
    latch: dict[str, Any],
    append_event: EventAppender,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not latch.get("suppress_full_cycle") and latch.get("terminal_latch_status") != "reopened":
        return None, None
    source_cycle_id = validate_cycle_id(str(latch.get("terminal_latch_source_cycle_id") or ""))
    observation = dict(terminal_state)
    observation.pop("cycle_id", None)
    observation.setdefault("step", "report")
    observation.setdefault("status", "complete")
    enforced = (
        workflow_contract_state(
            read_initialization_metadata(root, source_cycle_id)
        )
        == "enforced"
    )
    if enforced:
        prior_kind = observation.get("event_kind")
        if prior_kind:
            observation["terminal_lifecycle_kind"] = prior_kind
        for field in (
            "event_kind",
            "event_id",
            "format_version",
            "step",
            "status",
            "created_at",
            "producer_kind",
            "request_fingerprint",
            "ledger_sequence",
            "source_status",
        ):
            observation.pop(field, None)
        seed = make_terminal_lifecycle_seed(observation)
    if latch.get("suppress_full_cycle"):
        result = (
            append_compiled_terminal_lifecycle(
                root, source_cycle_id, seed
            )
            if enforced
            else append_event(root, source_cycle_id, observation, False)
        )
        return {
            "cycle_suppressed": True,
            "reason": "quiescent_terminal_latched",
            **latch,
            "observation_cycle_id": source_cycle_id,
            "observation_result": result,
        }, None
    if enforced:
        observation.setdefault("terminal_lifecycle_kind", "terminal_reopen_receipt")
        seed = make_terminal_lifecycle_seed(observation)
    else:
        observation.setdefault("event_kind", "terminal_reopen_receipt")
    return None, (
        append_compiled_terminal_lifecycle(root, source_cycle_id, seed)
        if enforced
        else append_event(root, source_cycle_id, observation, False)
    )


def _load_existing_metadata(
    root: Path, cycle_id: str, path: Path
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed cycle initialization metadata: {path}") from exc
    if not isinstance(loaded, dict):
        return None
    from .initialization_provenance import verify_initialization_provenance

    verify_initialization_provenance(root, cycle_id, loaded)
    return loaded


def _initialization_payload(metadata: dict[str, Any]) -> str:
    return (
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )


def _recoverable_initialization_metadata(
    root: Path,
    cycle_id: str,
    path: Path,
    *,
    task_id: str | None,
    reason: str,
    allow_missing_task_for_bootstrap: bool,
    protocol: int | None,
    preparation: int | None,
    profile: str | None,
) -> dict[str, Any] | None:
    """Recognize only the exact metadata-only residue of a first-init crash."""

    blocked_paths = (
        provenance_path(root, cycle_id),
        ledger_path(root, cycle_id),
        current_stage_path(root, cycle_id),
    )
    if any(item.exists() or item.is_symlink() for item in blocked_paths):
        return None
    try:
        payload = path.read_text(encoding="utf-8")
        loaded = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict) or payload != _initialization_payload(loaded):
        return None
    requested_protocol, requested_preparation, requested_profile = (
        _requested_contract_versions(
            metadata_exists=False,
            protocol=protocol,
            preparation=preparation,
            profile=profile,
        )
    )
    initialized_at = loaded.get("initialized_at")
    if not isinstance(initialized_at, str) or not initialized_at.strip():
        return None
    expected: dict[str, Any] = {
        "format_version": LEDGER_FORMAT_VERSION,
        "cycle_id": cycle_id,
        "initialized_at": initialized_at,
        "task_id": task_id,
        "reason": reason,
        "storage_bootstrap_only": True,
        "first_canonical_step": "context",
        "allow_missing_task_for_bootstrap": allow_missing_task_for_bootstrap,
        PROVENANCE_VERSION_FIELD: PROVENANCE_SCHEMA_VERSION,
    }
    if requested_protocol is not None:
        expected["stage_compiler_protocol_version"] = requested_protocol
    if requested_preparation is not None:
        expected["stage_preparation_schema_version"] = requested_preparation
    if requested_profile is not None:
        expected["workflow_contract_profile"] = requested_profile
    return loaded if loaded == expected else None


def _load_existing_for_init(
    root: Path,
    cycle_id: str,
    path: Path,
    **recovery_inputs: Any,
) -> tuple[dict[str, Any] | None, bool]:
    try:
        return _load_existing_metadata(root, cycle_id, path), False
    except ValueError:
        recoverable = _recoverable_initialization_metadata(
            root,
            cycle_id,
            path,
            **recovery_inputs,
        )
        if recoverable is None:
            raise
        return recoverable, True


def _initialization_result(
    root: Path,
    directory: Path,
    metadata_path: Path,
    cycle_id: str,
    cycle_existing: bool,
    metadata: dict[str, Any],
    current: dict[str, Any],
    terminal_reopen_result: dict[str, Any] | None,
) -> dict[str, Any]:
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


def _preflight_existing_initialization(
    root: Path,
    cycle_id: str,
    metadata_path: Path,
    metadata_exists: bool,
    recovery_inputs: dict[str, Any],
) -> None:
    if not metadata_exists:
        return
    metadata, recover_provenance = _load_existing_for_init(
        root,
        cycle_id,
        metadata_path,
        **recovery_inputs,
    )
    if metadata is None:
        raise ValueError(
            f"cycle initialization metadata must be a JSON object: {metadata_path}"
        )
    if not recover_provenance:
        require_cycle_mutation_contract(metadata, "init")


def init_cycle(
    root: Path,
    cycle_id: str | None,
    task_id: str | None,
    reason: str,
    terminal_state: dict[str, Any] | None = None,
    allow_missing_task_for_bootstrap: bool = False,
    stage_compiler_protocol_version: int | None = None,
    stage_preparation_schema_version: int | None = None,
    workflow_contract_profile: str | None = None,
    *,
    atomic_writer: AtomicTextWriter = atomic_write_text,
    append_event: EventAppender,
) -> dict[str, Any]:
    require_existing_v1_recovery(
        root, cycle_id, stage_compiler_protocol_version
    )
    terminal_reopen_result: dict[str, Any] | None = None
    if terminal_state:
        latch = _validate_terminal_state(root, terminal_state)
        suppressed, terminal_reopen_result = _terminal_observation(root, terminal_state, latch, append_event)
        if suppressed is not None:
            return suppressed
    cycle_id = validate_cycle_id(cycle_id or default_cycle_id())
    if task_id is None and not allow_missing_task_for_bootstrap:
        raise ValueError("task_id is required unless allow_missing_task_for_bootstrap is explicitly enabled")
    if task_id is not None and allow_missing_task_for_bootstrap:
        raise ValueError("allow_missing_task_for_bootstrap is valid only when task_id is absent")
    directory = cycle_dir(root, cycle_id)
    metadata_path = initialization_path(root, cycle_id)
    metadata_exists = metadata_path.is_file()
    expected_reason = str(reason or "cycle ledger initialized")
    recovery_inputs = {
        "task_id": task_id,
        "reason": expected_reason,
        "allow_missing_task_for_bootstrap": allow_missing_task_for_bootstrap,
        "protocol": stage_compiler_protocol_version,
        "preparation": stage_preparation_schema_version,
        "profile": workflow_contract_profile,
    }
    _preflight_existing_initialization(
        root,
        cycle_id,
        metadata_path,
        metadata_exists,
        recovery_inputs,
    )
    requested_protocol, requested_preparation, requested_profile = (
        _requested_contract_versions(
            metadata_exists=metadata_exists,
            protocol=stage_compiler_protocol_version,
            preparation=stage_preparation_schema_version,
            profile=workflow_contract_profile,
        )
    )
    (directory / "packets").mkdir(parents=True, exist_ok=True)
    with ledger_lock(root, cycle_id, exclusive=True):
        existing_metadata, recover_provenance = _load_existing_for_init(
            root,
            cycle_id,
            metadata_path,
            **recovery_inputs,
        )
        if existing_metadata is not None:
            if recover_provenance:
                publish_initialization_provenance(
                    root,
                    cycle_id,
                    existing_metadata,
                )
            require_cycle_mutation_contract(existing_metadata, "init")
            if (
                existing_metadata.get("task_id") != task_id
                or str(existing_metadata.get("reason") or "") != expected_reason
                or existing_metadata.get("allow_missing_task_for_bootstrap", False)
                is not allow_missing_task_for_bootstrap
                or (
                    requested_protocol is not None
                    and _protocol_version(existing_metadata) != requested_protocol
                )
                or (
                    requested_preparation is not None
                    and existing_metadata.get(
                        "stage_preparation_schema_version",
                        2
                        if existing_metadata.get("stage_compiler_protocol_version") == 2
                        else 1,
                    )
                    != requested_preparation
                )
                or (
                    requested_profile is not None
                    and existing_metadata.get("workflow_contract_profile")
                    != requested_profile
                )
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
                PROVENANCE_VERSION_FIELD: PROVENANCE_SCHEMA_VERSION,
            }
            if requested_protocol is not None:
                metadata["stage_compiler_protocol_version"] = requested_protocol
            if requested_preparation is not None:
                metadata["stage_preparation_schema_version"] = requested_preparation
            if requested_profile is not None:
                metadata["workflow_contract_profile"] = requested_profile
            atomic_writer(metadata_path, _initialization_payload(metadata))
            publish_initialization_provenance(root, cycle_id, metadata)
            cycle_existing = False
        events = read_events_unlocked(root, cycle_id)
        current = _write_current_unlocked(
            root,
            cycle_id,
            events,
            protocol_version=_protocol_version(metadata),
            atomic_writer=atomic_writer,
        )
    return _initialization_result(
        root,
        directory,
        metadata_path,
        cycle_id,
        cycle_existing,
        metadata,
        current,
        terminal_reopen_result,
    )
