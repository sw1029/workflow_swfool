"""Cooperative workspace-wide barrier for selection-CAS reference producers.

Deletion coordinates every registered selection-publication producer through
the shared side of this barrier. GC takes the exclusive side. The policy binds
the exact compact state and exact registered producer code inventory. It never
claims control over arbitrary external or legacy writers.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Iterator

from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY,
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    _reference_barrier_proof,
    _require_selection_publication_producer,
)
from .selection_publication_producer_manifest import (
    registered_producer_inventory,
    valid_producer_inventory,
)

REFERENCE_BARRIER_PROTOCOL = "selection_publication_reference_barrier_v2"
REFERENCE_BARRIER_REF = ".task/selection_publication/reference-barrier.json"
MAX_REFERENCE_BARRIER_BYTES = 64 * 1024
REFERENCE_BARRIER_KEYS = {
    "schema_version",
    "kind",
    "protocol",
    "coverage",
    "required_producer_api",
    "external_writer_coverage",
    "external_writer_requirement",
    "adoption_preflight",
    "storage_state",
    "producer_inventory",
}
REFERENCE_BARRIER_BASE = {
    "schema_version": 2,
    "kind": "selection_publication_reference_barrier",
    "protocol": REFERENCE_BARRIER_PROTOCOL,
    "coverage": "registered_selection_publication_producers_only",
    "required_producer_api": (
        "orchestrate_task_cycle.selection_publication_reference_barrier."
        "registered_producer_barrier"
    ),
    "external_writer_coverage": "not_claimed",
    "external_writer_requirement": (
        "external_and_legacy_writers_must_be_quiesced_or_host_enforced"
    ),
}
ADOPTION_PREFLIGHT_KEYS = {
    "workspace_epoch_sha256",
    "workspace_file_count",
    "workspace_bytes",
}


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def reference_barrier_payload(
    adoption_preflight: dict[str, Any],
    storage_state: dict[str, str],
    producer_inventory: dict[str, Any],
) -> bytes:
    """Render the exact policy payload after compiler-owned preflight."""

    return _canonical_json(
        {
            **REFERENCE_BARRIER_BASE,
            "adoption_preflight": adoption_preflight,
            "storage_state": storage_state,
            "producer_inventory": producer_inventory,
        }
    )


def _safe_lock_descriptor(root: Path) -> int:
    """Open the already-existing workspace inode used as the barrier lock.

    Locking the workspace directory itself keeps read-only conflicts and
    validation failures free of lock-file residue.  Every registered producer
    and GC process resolves and verifies this same inode before taking flock.
    """

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(root, flags)
    except OSError as exc:
        raise ValueError("selection-publication workspace barrier is unsafe") from exc
    try:
        observed = os.fstat(descriptor)
        current = root.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or (observed.st_dev, observed.st_ino) != (current.st_dev, current.st_ino)
        ):
            raise ValueError("selection-publication workspace barrier identity changed")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextlib.contextmanager
def _barrier(root: Path, mode: int, proof_mode: str) -> Iterator[None]:
    if not hasattr(fcntl, "flock"):
        raise ValueError("selection-publication reference barrier requires POSIX flock")
    requested_root = root.expanduser().absolute()
    resolved_root = requested_root.resolve(strict=True)
    descriptor = _safe_lock_descriptor(resolved_root)
    try:
        fcntl.flock(descriptor, mode)
        proof_roots = [resolved_root]
        if requested_root != resolved_root:
            proof_roots.append(requested_root)
        with contextlib.ExitStack() as stack:
            for proof_root in proof_roots:
                stack.enter_context(
                    _reference_barrier_proof(proof_root, proof_mode, descriptor)
                )
            yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


@contextlib.contextmanager
def reference_producer_barrier(root: Path) -> Iterator[None]:
    """Shared barrier required around every selection-CAS reference publish."""

    with _barrier(root, fcntl.LOCK_SH, "shared"):
        yield


@contextlib.contextmanager
def registered_producer_barrier(
    root: Path, *, producer_capability: object
) -> Iterator[None]:
    """Bootstrap safely and acquire the shared side for a built-in producer."""

    _require_selection_publication_producer(producer_capability)
    root = root.expanduser().resolve(strict=True)
    from .selection_publication_store import _create_store_directories

    with reference_producer_barrier(root):
        _create_store_directories(root)
        yield


@contextlib.contextmanager
def reference_gc_barrier(root: Path) -> Iterator[None]:
    """Exclusive barrier held from the final mark through effect receipt."""

    with _barrier(root, fcntl.LOCK_EX, "exclusive"):
        yield


def _valid_binding(value: Any, *, expected_ref: str) -> bool:
    return bool(
        isinstance(value, dict)
        and set(value) == {"ref", "sha256"}
        and value.get("ref") == expected_ref
        and isinstance(value.get("sha256"), str)
        and len(value["sha256"]) == 64
        and all(character in "0123456789abcdef" for character in value["sha256"])
    )


def validate_reference_barrier_payload(
    payload: bytes,
    *,
    root: Path | None = None,
    require_current: bool = False,
) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "selection-publication reference barrier policy is unreadable"
        ) from exc
    preflight = value.get("adoption_preflight") if isinstance(value, dict) else None
    valid_preflight = bool(
        isinstance(preflight, dict)
        and set(preflight) == ADOPTION_PREFLIGHT_KEYS
        and isinstance(preflight.get("workspace_epoch_sha256"), str)
        and len(preflight["workspace_epoch_sha256"]) == 64
        and all(
            character in "0123456789abcdef"
            for character in preflight["workspace_epoch_sha256"]
        )
        and type(preflight.get("workspace_file_count")) is int
        and preflight["workspace_file_count"] >= 0
        and type(preflight.get("workspace_bytes")) is int
        and preflight["workspace_bytes"] >= 0
    )
    storage_state = value.get("storage_state") if isinstance(value, dict) else None
    producer_inventory = (
        value.get("producer_inventory") if isinstance(value, dict) else None
    )
    expected = (
        {
            **REFERENCE_BARRIER_BASE,
            "adoption_preflight": preflight,
            "storage_state": storage_state,
            "producer_inventory": producer_inventory,
        }
        if valid_preflight
        and _valid_binding(
            storage_state,
            expected_ref=".task/selection_publication/state.json",
        )
        and valid_producer_inventory(producer_inventory)
        else None
    )
    if (
        not isinstance(value, dict)
        or set(value) != REFERENCE_BARRIER_KEYS
        or value != expected
        or payload != _canonical_json(value)
    ):
        raise ValueError(
            "selection-publication reference barrier is not a closed "
            "registered-producer policy"
        )
    if require_current:
        if root is None:
            raise ValueError(
                "current reference-barrier validation requires a workspace root"
            )
        from .selection_publication_gc_fs import artifact_binding

        current_state = artifact_binding(root, ".task/selection_publication/state.json")
        if value["storage_state"] != current_state:
            raise ValueError(
                "selection-publication reference barrier storage-state binding is stale"
            )
        if value["producer_inventory"] != registered_producer_inventory():
            raise ValueError(
                "selection-publication reference barrier producer inventory has drifted"
            )
    return value


def reference_barrier_binding(payload: bytes) -> dict[str, str]:
    validate_reference_barrier_payload(payload)
    return {
        "ref": REFERENCE_BARRIER_REF,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def refresh_reference_barrier_state(root: Path, state_binding: dict[str, str]) -> bool:
    """Refresh an adopted policy after a state mutation under the shared lock."""

    from .selection_publication_gc_fs import read_relative, replace_relative

    existing = read_relative(
        root,
        REFERENCE_BARRIER_REF,
        "selection-publication reference barrier policy",
        required=False,
        max_bytes=MAX_REFERENCE_BARRIER_BYTES,
    )
    if existing is None:
        return False
    policy = validate_reference_barrier_payload(existing)
    payload = reference_barrier_payload(
        policy["adoption_preflight"],
        state_binding,
        registered_producer_inventory(),
    )
    _digest, changed = replace_relative(
        root,
        REFERENCE_BARRIER_REF,
        payload,
        "selection-publication reference barrier policy",
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    )
    return changed


def adopt_reference_barrier(root: Path) -> dict[str, Any]:
    """Adopt cooperative-only writer mode after a bounded, quiescent scan."""

    from .selection_publication_gc_fs import (
        artifact_binding,
        read_relative,
        replace_relative,
    )
    from .selection_publication_gc_scan import (
        validate_quiescent_state,
        workspace_reference_epoch,
    )
    from .selection_publication_store import _publication_lock

    root = root.expanduser().resolve(strict=True)
    # Read-only failure must precede lock-file creation.  A valid v4 migration
    # already created the stable store and producer lock through `_lock`.
    validate_quiescent_state(root)
    with reference_gc_barrier(root):
        with _publication_lock(
            root,
            producer_capability=(_SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY),
        ):
            _state, state_binding = validate_quiescent_state(root)
            existing = read_relative(
                root,
                REFERENCE_BARRIER_REF,
                "selection-publication reference barrier policy",
                required=False,
                max_bytes=MAX_REFERENCE_BARRIER_BYTES,
            )
            if existing is not None:
                try:
                    policy = validate_reference_barrier_payload(
                        existing, root=root, require_current=True
                    )
                except ValueError:
                    policy = None
                if policy is not None:
                    return {
                        "schema_version": 2,
                        "result_kind": "selection_publication_reference_barrier_adoption",
                        "status": "adopted",
                        "coverage": "registered_selection_publication_producers_only",
                        "external_writer_coverage": "not_claimed",
                        "reference_barrier": artifact_binding(
                            root, REFERENCE_BARRIER_REF
                        ),
                        "adoption_preflight": policy["adoption_preflight"],
                        "producer_inventory": policy["producer_inventory"],
                        "idempotent_replay": True,
                        "mutation_performed": False,
                        "model_authored_mechanical_bytes": 0,
                    }
            epoch = workspace_reference_epoch(root)
            preflight = {
                "workspace_epoch_sha256": epoch["workspace_epoch_sha256"],
                "workspace_file_count": epoch["workspace_file_count"],
                "workspace_bytes": epoch["workspace_bytes"],
            }
            inventory = registered_producer_inventory()
            payload = reference_barrier_payload(preflight, state_binding, inventory)
            digest, created = replace_relative(
                root,
                REFERENCE_BARRIER_REF,
                payload,
                "selection-publication reference barrier policy",
                producer_capability=(_SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY),
            )
            binding = artifact_binding(root, REFERENCE_BARRIER_REF)
            if binding["sha256"] != digest:
                raise ValueError(
                    "selection-publication reference barrier publication drifted"
                )
    return {
        "schema_version": 2,
        "result_kind": "selection_publication_reference_barrier_adoption",
        "status": "adopted",
        "coverage": "registered_selection_publication_producers_only",
        "external_writer_coverage": "not_claimed",
        "reference_barrier": binding,
        "adoption_preflight": preflight,
        "producer_inventory": inventory,
        "idempotent_replay": not created,
        "mutation_performed": created,
        "model_authored_mechanical_bytes": 0,
    }


__all__ = (
    "REFERENCE_BARRIER_BASE",
    "MAX_REFERENCE_BARRIER_BYTES",
    "REFERENCE_BARRIER_PROTOCOL",
    "REFERENCE_BARRIER_REF",
    "adopt_reference_barrier",
    "reference_barrier_binding",
    "reference_barrier_payload",
    "refresh_reference_barrier_state",
    "registered_producer_inventory",
    "registered_producer_barrier",
    "reference_gc_barrier",
    "reference_producer_barrier",
    "validate_reference_barrier_payload",
)
