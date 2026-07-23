"""Authority-gated exact restore effect for selection-publication GC."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

from . import selection_publication_gc_hooks as gc_hooks
from .selection_publication_gc_archive import archive_payloads
from .selection_publication_gc_authority import (
    expected_subject,
    normalize_binding,
    receipt_result,
    validate_apply_receipt_contract,
    validate_completed_replay_authority,
    validate_effect_authority,
    validate_restore_receipt_contract,
)
from .selection_publication_gc_contract import (
    GC_SCHEMA_VERSION,
    MAX_CANDIDATE_BYTES,
    MAX_SCAN_FILE_BYTES,
    receipt_path,
    restore_receipt_path,
)
from .selection_publication_gc_fs import (
    BoundParent,
    PinnedLeaf,
    bound_parent,
    open_pinned_leaf,
    read_json_relative,
    read_relative,
    write_once_relative,
    write_payload,
)
from .selection_publication_gc_scan import (
    load_plan,
    validate_plan_reference_barrier,
)
from .selection_publication_reference_barrier import reference_gc_barrier
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY,
)
from .selection_publication_store import (
    _canonical_json,
    _publication_lock,
    _sha256_bytes,
)


Target = tuple[dict[str, Any], BoundParent, bytes, PinnedLeaf | None]


def _load_apply_receipt(
    root: Path,
    *,
    plan: dict[str, Any],
    plan_path: Path,
    plan_sha: str,
) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    path = receipt_path(root, plan["plan_id"])
    ref = path.relative_to(root).as_posix()
    receipt, payload = read_json_relative(
        root, ref, "selection-publication gc receipt"
    )
    if payload != _canonical_json(receipt):
        raise ValueError("selection-publication gc receipt is non-canonical")
    validate_apply_receipt_contract(
        receipt,
        plan=plan,
        plan_path=plan_path,
        plan_sha=plan_sha,
        root=root,
    )
    binding = {"ref": ref, "sha256": _sha256_bytes(payload)}
    return receipt, payload, binding


def _load_archive(
    root: Path, receipt: dict[str, Any], plan: dict[str, Any]
) -> dict[str, bytes]:
    binding = normalize_binding(
        receipt.get("archive"), "selection-publication gc receipt archive"
    )
    payload = read_relative(
        root,
        binding["ref"],
        "selection-publication gc archive",
        max_bytes=MAX_CANDIDATE_BYTES + MAX_SCAN_FILE_BYTES,
    )
    assert payload is not None
    if _sha256_bytes(payload) != binding["sha256"]:
        raise ValueError("selection-publication gc archive binding drifted")
    return archive_payloads(payload, plan)


def _completed_replay(
    root: Path,
    *,
    plan: dict[str, Any],
    gc_receipt: dict[str, str],
    subject: dict[str, str],
    authority_packet: Any,
    pre_commit_verification: Any,
) -> dict[str, Any] | None:
    path = restore_receipt_path(root, plan["plan_id"])
    ref = path.relative_to(root).as_posix()
    payload = read_relative(
        root,
        ref,
        "selection-publication gc restore receipt",
        required=False,
        max_bytes=MAX_SCAN_FILE_BYTES,
    )
    if payload is None:
        return None
    try:
        receipt = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "selection-publication gc restore receipt is unreadable"
        ) from exc
    if not isinstance(receipt, dict) or payload != _canonical_json(receipt):
        raise ValueError(
            "selection-publication gc restore receipt is non-canonical"
        )
    validate_restore_receipt_contract(
        receipt,
        plan_id=plan["plan_id"],
        gc_receipt=gc_receipt,
        candidate_count=len(plan["candidates"]),
    )
    validate_completed_replay_authority(
        root,
        receipt=receipt,
        operation="restore_selection_publication_retention",
        subject=subject,
        authority_packet=authority_packet,
        pre_commit_verification=pre_commit_verification,
        effect_validator=validate_effect_authority,
    )
    _validate_restored_candidates(root, plan)
    return receipt_result(
        root,
        receipt,
        path,
        idempotent_replay=True,
        mutation_performed=False,
    )


def _validate_restored_candidates(root: Path, plan: dict[str, Any]) -> None:
    for row in plan["candidates"]:
        observed = read_relative(
            root,
            row["ref"],
            "selection-publication gc restored candidate",
            max_bytes=MAX_CANDIDATE_BYTES,
        )
        assert observed is not None
        if (
            len(observed) != row["size_bytes"]
            or _sha256_bytes(observed) != row["sha256"]
        ):
            raise ValueError(
                "selection-publication gc restored candidate drifted"
            )


@contextlib.contextmanager
def _target_handles(
    root: Path,
    plan: dict[str, Any],
    payloads: dict[str, bytes],
) -> Iterator[list[Target]]:
    with contextlib.ExitStack() as stack:
        targets: list[Target] = []
        for row in plan["candidates"]:
            parent = stack.enter_context(
                bound_parent(root, row["ref"], create=True)
            )
            payload = payloads[f"files/{row['ref']}"]
            existing = open_pinned_leaf(
                parent,
                "selection-publication gc restore target",
                required=False,
                max_bytes=MAX_CANDIDATE_BYTES,
            )
            if existing is not None:
                stack.callback(existing.close)
                if (
                    existing.payload != payload
                    or len(existing.payload) != row["size_bytes"]
                    or _sha256_bytes(existing.payload) != row["sha256"]
                ):
                    raise ValueError(
                        "selection-publication gc restore target conflicts"
                    )
            targets.append((row, parent, payload, existing))
        yield targets


def _restore_one(
    target: Target,
    *,
    index: int,
) -> bool:
    row, parent, payload, existing = target
    if existing is not None:
        existing.verify_bytes(max_bytes=MAX_CANDIDATE_BYTES)
        if existing.payload != payload:
            raise ValueError(
                "selection-publication gc restore target changed"
            )
        return False
    temporary = f".{parent.name}.restore.{os.getpid()}.{index:x}.tmp"
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(
            temporary, flags, 0o600, dir_fd=parent.descriptor
        )
        try:
            write_payload(
                descriptor,
                payload,
                root=parent.root,
                producer_capability=(
                    _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY
                ),
            )
            _link_restored(parent, temporary)
        finally:
            os.close(descriptor)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent.descriptor)
        except FileNotFoundError:
            pass
    parent.verify()
    verified_leaf = open_pinned_leaf(
        parent,
        "selection-publication gc restored candidate",
        max_bytes=MAX_CANDIDATE_BYTES,
    )
    assert verified_leaf is not None
    verified = verified_leaf.payload
    verified_leaf.close()
    if verified != payload or _sha256_bytes(verified) != row["sha256"]:
        raise ValueError("selection-publication gc restore verification failed")
    return True


def _link_restored(parent: BoundParent, temporary: str) -> None:
    parent.verify()
    try:
        os.link(
            temporary,
            parent.name,
            src_dir_fd=parent.descriptor,
            dst_dir_fd=parent.descriptor,
            follow_symlinks=False,
        )
    except FileExistsError as exc:
        raise ValueError(
            "selection-publication gc restore target changed"
        ) from exc
    os.fsync(parent.descriptor)


def _restore_candidates(
    root: Path,
    plan: dict[str, Any],
    payloads: dict[str, bytes],
    receipt: Path,
) -> int:
    with _target_handles(root, plan, payloads) as targets:
        hook_path = (
            root / plan["candidates"][0]["ref"]
            if plan["candidates"]
            else receipt
        )
        gc_hooks.race_hook("before_restore_effect", hook_path)
        for _row, parent, _payload, _existing in targets:
            parent.verify()
        return sum(
            _restore_one(target, index=index)
            for index, target in enumerate(targets)
        )


def _publish_restore_receipt(
    root: Path,
    *,
    plan: dict[str, Any],
    gc_receipt: dict[str, str],
    authority: dict[str, Any],
    restored: int,
) -> dict[str, Any]:
    receipt = {
        "schema_version": GC_SCHEMA_VERSION,
        "result_kind": "selection_publication_gc_restore_receipt",
        "status": "restored",
        "plan_id": plan["plan_id"],
        "gc_receipt": gc_receipt,
        "authority": authority,
        "restored_count": len(plan["candidates"]),
        "model_authored_mechanical_bytes": 0,
    }
    path = restore_receipt_path(root, plan["plan_id"])
    _digest, created = write_once_relative(
        root,
        path.relative_to(root).as_posix(),
        _canonical_json(receipt),
        "selection-publication gc restore receipt",
        producer_capability=_SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY,
    )
    return receipt_result(
        root,
        receipt,
        path,
        idempotent_replay=not created and restored == 0,
        mutation_performed=restored > 0 or created,
    )


def restore_gc(
    root: Path,
    plan_id: str,
    *,
    authority_packet: dict[str, str] | None = None,
    pre_commit_verification: dict[str, str] | None = None,
) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    with reference_gc_barrier(root):
        with _publication_lock(
            root,
            producer_capability=(
                _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY
            ),
        ):
            plan, path, digest = load_plan(root, plan_id)
            receipt, _payload, gc_binding = _load_apply_receipt(
                root, plan=plan, plan_path=path, plan_sha=digest
            )
            subject = expected_subject(
                root,
                operation="restore_selection_publication_retention",
                plan_id=plan_id,
                plan_path=path,
                plan_sha=digest,
            )
            archived = _load_archive(root, receipt, plan)
            replay = _completed_replay(
                root,
                plan=plan,
                gc_receipt=gc_binding,
                subject=subject,
                authority_packet=authority_packet,
                pre_commit_verification=pre_commit_verification,
            )
            if replay is not None:
                return replay
            initial = validate_effect_authority(
                root,
                operation="restore_selection_publication_retention",
                subject=subject,
                authority_packet=authority_packet,
                pre_commit_verification=pre_commit_verification,
            )
            validate_plan_reference_barrier(root, plan)
            return _restore_under_authority_lease(
                root,
                plan=plan,
                archived=archived,
                gc_binding=gc_binding,
                subject=subject,
                authority_packet=authority_packet,
                pre_commit_verification=pre_commit_verification,
                initial=initial,
            )


def _restore_under_authority_lease(
    root: Path,
    *,
    plan: dict[str, Any],
    archived: dict[str, bytes],
    gc_binding: dict[str, str],
    subject: dict[str, str],
    authority_packet: Any,
    pre_commit_verification: Any,
    initial: dict[str, Any],
) -> dict[str, Any]:
    try:
        from manage_agent_authority.effect_lease import acquire_effect_lease

        with acquire_effect_lease(
            root,
            operation="restore_selection_publication_retention",
            subject=subject,
            reservation=initial["reservation"],
            pre_commit_verification=initial["pre_commit_verification"],
            expected_version=initial["reservation_state_version"],
        ) as lease:
            current = validate_effect_authority(
                root,
                operation="restore_selection_publication_retention",
                subject=subject,
                authority_packet=authority_packet,
                pre_commit_verification=pre_commit_verification,
            )
            if current != initial:
                raise ValueError(
                    "selection-publication gc authority changed before restore"
                )
            restored = _restore_candidates(
                root,
                plan,
                archived,
                receipt_path(root, plan["plan_id"]),
            )
            hook_path = (
                root / plan["candidates"][0]["ref"]
                if plan["candidates"]
                else receipt_path(root, plan["plan_id"])
            )
            gc_hooks.race_hook("before_restore_receipt", hook_path)
            _validate_restored_candidates(root, plan)
            return _publish_restore_receipt(
                root,
                plan=plan,
                gc_receipt=gc_binding,
                authority={**current, "effect_lease": lease},
                restored=restored,
            )
    except (ImportError, SystemExit) as exc:
        raise ValueError(
            "selection-publication gc could not acquire current authority effect lease"
        ) from exc


__all__ = ("restore_gc",)
