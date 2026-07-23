"""Authority-gated archive-and-remove effect for selection-publication GC."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any

from . import selection_publication_gc_hooks as gc_hooks
from .selection_publication_gc_archive import (
    archive_bytes,
    archive_payloads,
    candidate_handles,
    validate_plan_state,
)
from .selection_publication_gc_authority import (
    expected_subject,
    normalize_binding,
    receipt_result,
    validate_apply_receipt_contract,
    validate_completed_replay_authority,
    validate_effect_authority,
)
from .selection_publication_gc_contract import (
    GC_SCHEMA_VERSION,
    MAX_CANDIDATE_BYTES,
    MAX_SCAN_FILE_BYTES,
    archive_path,
    receipt_path,
)
from .selection_publication_gc_fs import read_relative, write_once_relative
from .selection_publication_gc_scan import (
    load_plan,
    referenced_paths,
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


def _completed_replay(
    root: Path,
    *,
    plan: dict[str, Any],
    plan_path: Path,
    plan_sha: str,
    subject: dict[str, str],
    authority_packet: Any,
    pre_commit_verification: Any,
) -> dict[str, Any] | None:
    path = receipt_path(root, plan["plan_id"])
    ref = path.relative_to(root).as_posix()
    payload = read_relative(
        root,
        ref,
        "selection-publication gc receipt",
        required=False,
        max_bytes=MAX_SCAN_FILE_BYTES,
    )
    if payload is None:
        return None
    try:
        receipt = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("selection-publication gc receipt is unreadable") from exc
    if not isinstance(receipt, dict) or payload != _canonical_json(receipt):
        raise ValueError("selection-publication gc receipt is non-canonical")
    validate_apply_receipt_contract(
        receipt,
        plan=plan,
        plan_path=plan_path,
        plan_sha=plan_sha,
        root=root,
    )
    validate_completed_replay_authority(
        root,
        receipt=receipt,
        operation="apply_selection_publication_retention",
        subject=subject,
        authority_packet=authority_packet,
        pre_commit_verification=pre_commit_verification,
        effect_validator=validate_effect_authority,
    )
    _validate_replay_archive(root, plan, receipt)
    _validate_candidates_absent(root, plan)
    return receipt_result(
        root,
        receipt,
        path,
        idempotent_replay=True,
        mutation_performed=False,
    )


def _validate_replay_archive(
    root: Path, plan: dict[str, Any], receipt: dict[str, Any]
) -> None:
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
    archive_payloads(payload, plan)


def _validate_candidates_absent(root: Path, plan: dict[str, Any]) -> None:
    for row in plan["candidates"]:
        if read_relative(
            root,
            row["ref"],
            "selection-publication gc replay candidate",
            required=False,
            max_bytes=MAX_CANDIDATE_BYTES,
        ) is not None:
            raise ValueError("selection-publication gc replay found restored file")


def _existing_archive(root: Path, plan_id: str) -> tuple[Path, bytes | None]:
    path = archive_path(root, plan_id)
    payload = read_relative(
        root,
        path.relative_to(root).as_posix(),
        "selection-publication gc archive",
        required=False,
        max_bytes=MAX_CANDIDATE_BYTES + MAX_SCAN_FILE_BYTES,
    )
    return path, payload


def _archive_and_remove(
    root: Path, plan: dict[str, Any]
) -> tuple[Path, str]:
    path, existing = _existing_archive(root, plan["plan_id"])
    ref = path.relative_to(root).as_posix()
    with candidate_handles(
        root, plan, allow_missing=existing is not None
    ) as candidates:
        live = {
            row["ref"]: pinned.payload
            for row, _parent, pinned in candidates
            if pinned is not None
        }
        archive = (
            existing
            if existing is not None
            else archive_bytes(plan, root, candidate_payloads=live)
        )
        archived = archive_payloads(archive, plan)
        _validate_missing_candidates(candidates, archived)
        hook_path = (
            root / plan["candidates"][0]["ref"]
            if plan["candidates"]
            else path
        )
        gc_hooks.race_hook("before_apply_effect", hook_path)
        for _row, parent, _pinned in candidates:
            parent.verify()
        digest, _created = write_once_relative(
            root,
            ref,
            archive,
            "selection-publication gc archive",
            producer_capability=(
                _SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY
            ),
        )
        verified = read_relative(
            root,
            ref,
            "selection-publication gc archive",
            max_bytes=MAX_CANDIDATE_BYTES + MAX_SCAN_FILE_BYTES,
        )
        assert verified is not None
        archive_payloads(verified, plan)
        _remove_candidates(candidates)
    return path, digest


def _validate_missing_candidates(
    candidates: list[tuple[dict[str, Any], Any, Any]],
    archived: dict[str, bytes],
) -> None:
    for row, _parent, pinned in candidates:
        if pinned is None and archived.get(f"files/{row['ref']}") is None:
            raise ValueError("selection-publication gc candidate is missing")


def _remove_candidates(
    candidates: list[tuple[dict[str, Any], Any, Any]],
) -> None:
    for row, parent, pinned in candidates:
        parent.verify()
        if pinned is not None:
            pinned.verify_bytes(max_bytes=MAX_CANDIDATE_BYTES)
            if (
                len(pinned.payload) != row["size_bytes"]
                or _sha256_bytes(pinned.payload) != row["sha256"]
            ):
                raise ValueError(
                    "selection-publication gc delete binding differs from archive"
                )
            try:
                os.unlink(parent.name, dir_fd=parent.descriptor)
                os.fsync(parent.descriptor)
            except OSError as exc:
                raise ValueError(
                    "selection-publication gc candidate removal failed"
                ) from exc
            try:
                visible = os.stat(
                    parent.name,
                    dir_fd=parent.descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                visible = None
            if visible is not None:
                kind = "regular" if stat.S_ISREG(visible.st_mode) else "unsafe"
                raise ValueError(
                    "selection-publication gc candidate remained after removal "
                    f"as {kind}"
                )
        parent.verify()


def _publish_receipt(
    root: Path,
    *,
    plan: dict[str, Any],
    plan_path: Path,
    plan_sha: str,
    authority: dict[str, Any],
    archive_path: Path,
    archive_sha: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": GC_SCHEMA_VERSION,
        "result_kind": "selection_publication_gc_receipt",
        "status": "applied",
        "plan": {
            "ref": plan_path.relative_to(root).as_posix(),
            "sha256": plan_sha,
        },
        "plan_id": plan["plan_id"],
        "authority": authority,
        "archive": {
            "ref": archive_path.relative_to(root).as_posix(),
            "sha256": archive_sha,
        },
        "removed_count": len(plan["candidates"]),
        "removed_bytes": sum(
            int(row["size_bytes"]) for row in plan["candidates"]
        ),
        "restore_supported": True,
        "model_authored_mechanical_bytes": 0,
    }
    path = receipt_path(root, plan["plan_id"])
    write_once_relative(
        root,
        path.relative_to(root).as_posix(),
        _canonical_json(receipt),
        "selection-publication gc receipt",
        producer_capability=_SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY,
    )
    return receipt_result(
        root,
        receipt,
        path,
        idempotent_replay=False,
        mutation_performed=True,
    )


def apply_gc(
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
            subject = expected_subject(
                root,
                operation="apply_selection_publication_retention",
                plan_id=plan_id,
                plan_path=path,
                plan_sha=digest,
            )
            replay = _completed_replay(
                root,
                plan=plan,
                plan_path=path,
                plan_sha=digest,
                subject=subject,
                authority_packet=authority_packet,
                pre_commit_verification=pre_commit_verification,
            )
            if replay is not None:
                return replay
            initial = validate_effect_authority(
                root,
                operation="apply_selection_publication_retention",
                subject=subject,
                authority_packet=authority_packet,
                pre_commit_verification=pre_commit_verification,
            )
            validate_plan_reference_barrier(root, plan)
            validate_plan_state(root, plan)
            referenced, _scanned = referenced_paths(
                root, {str(row["ref"]) for row in plan["candidates"]}
            )
            if referenced:
                raise ValueError(
                    "selection-publication gc candidate became referenced after planning"
                )
            return _apply_under_authority_lease(
                root,
                plan=plan,
                plan_path=path,
                plan_sha=digest,
                subject=subject,
                authority_packet=authority_packet,
                pre_commit_verification=pre_commit_verification,
                initial=initial,
            )


def _apply_under_authority_lease(
    root: Path,
    *,
    plan: dict[str, Any],
    plan_path: Path,
    plan_sha: str,
    subject: dict[str, str],
    authority_packet: Any,
    pre_commit_verification: Any,
    initial: dict[str, Any],
) -> dict[str, Any]:
    try:
        from manage_agent_authority.effect_lease import acquire_effect_lease

        with acquire_effect_lease(
            root,
            operation="apply_selection_publication_retention",
            subject=subject,
            reservation=initial["reservation"],
            pre_commit_verification=initial["pre_commit_verification"],
            expected_version=initial["reservation_state_version"],
        ) as lease:
            current = validate_effect_authority(
                root,
                operation="apply_selection_publication_retention",
                subject=subject,
                authority_packet=authority_packet,
                pre_commit_verification=pre_commit_verification,
            )
            if current != initial:
                raise ValueError(
                    "selection-publication gc authority changed before effect"
                )
            archive_file, archive_sha = _archive_and_remove(root, plan)
            hook_path = (
                root / plan["candidates"][0]["ref"]
                if plan["candidates"]
                else archive_file
            )
            gc_hooks.race_hook("before_apply_receipt", hook_path)
            _validate_candidates_absent(root, plan)
            return _publish_receipt(
                root,
                plan=plan,
                plan_path=plan_path,
                plan_sha=plan_sha,
                authority={**current, "effect_lease": lease},
                archive_path=archive_file,
                archive_sha=archive_sha,
            )
    except (ImportError, SystemExit) as exc:
        raise ValueError(
            "selection-publication gc could not acquire current authority effect lease"
        ) from exc


__all__ = ("apply_gc",)
