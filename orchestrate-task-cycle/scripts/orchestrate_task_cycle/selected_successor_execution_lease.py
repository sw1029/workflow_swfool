"""Durable per-effect leases for selected-successor owner execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .selection_decision_store import normalize_binding, read_bound_bytes
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)
from .selection_publication_reference_barrier import (
    registered_producer_barrier,
)
from .selection_publication_store import (
    SHA256,
    _canonical_json,
    _safe_regular_file,
    _safe_store_directory,
    _sha256_bytes,
    _successor_gate_path,
    _write_once_with_status,
)
from .selected_successor_execution_support import ACTIONS
from .selected_successor_execution_authority import authority_preflight


def _execution_lease_path(root: Path, digest: str) -> Path:
    if not SHA256.fullmatch(digest):
        raise ValueError("invalid selected-successor execution-lease digest")
    directory = _safe_store_directory(
        root, ("successor_execution_leases", "sha256")
    )
    path = directory / f"{digest}.json"
    _safe_regular_file(path, "selected-successor execution lease")
    return path


def authority_gate(
    root: Path,
    bundle_binding: dict[str, str],
    rows: list[dict[str, Any]],
    proofs: dict[str, dict[str, Any]],
    *,
    publish: bool,
) -> tuple[dict[str, str], bool]:
    body = {
        "schema_version": 1,
        "artifact_kind": "selected_successor_authority_gate",
        "gate_status": "per_effect_current_authority_lease_required",
        "bundle": normalize_binding(bundle_binding, "selected-successor bundle"),
        "checked_operations": [
            {
                "action": row["action"],
                "operation": row["operation"],
                "subject": row["subject"],
                "idempotency_key": row["idempotency_key"],
                "reservation": proofs[row["action"]]["reservation"],
                "pre_commit_verification": proofs[row["action"]][
                    "pre_commit_verification"
                ],
                "expected_version": proofs[row["action"]]["expected_version"],
            }
            for row in rows
        ],
    }
    content_sha256 = _sha256_bytes(_canonical_json(body))
    gate = {**body, "gate_content_sha256": content_sha256}
    payload = _canonical_json(gate)
    path = _successor_gate_path(root, content_sha256)
    if publish:
        digest, created = _write_once_with_status(
            path,
            payload,
            "selected-successor pre-effect authority gate",
            producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
        )
    else:
        binding = {
            "ref": path.relative_to(root).as_posix(),
            "sha256": _sha256_bytes(payload),
        }
        read_bound_bytes(
            root, binding, "selected-successor pre-effect authority gate"
        )
        digest = binding["sha256"]
        created = False
    return {"ref": path.relative_to(root).as_posix(), "sha256": digest}, (
        publish and created
    )


def _execution_lease_hook(
    stage: str, root: Path, action: str, proofs: dict[str, dict[str, Any]]
) -> None:
    """Test seam for a reservation change between preview and an effect."""

    _ = stage, root, action, proofs


def publish_execution_lease(
    root: Path,
    bundle_binding: dict[str, str],
    rows: list[dict[str, Any]],
    proofs: dict[str, dict[str, Any]],
    *,
    action: str,
    skills_root: Path | None,
) -> tuple[dict[str, str], dict[str, str], bool]:
    """Revalidate all proofs under the authority lock, then seal one epoch."""

    if action not in ACTIONS:
        raise ValueError("Selected-successor execution lease action is invalid")
    from .selected_successor import load_selected_successor_bundle

    bundle = load_selected_successor_bundle(root, bundle_binding)
    if bundle.get("execution_order") != rows:
        raise ValueError(
            "Selected-successor execution lease rows differ from the exact bundle"
        )
    _execution_lease_hook(
        "before_current_authority_revalidation", root, action, proofs
    )
    from manage_agent_authority.canonical import authority_lock

    with registered_producer_barrier(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        with authority_lock(root):
            authority_preflight(
                root,
                rows,
                proofs,
                require_current=True,
                skills_root=skills_root,
            )
            gate, gate_created = authority_gate(
                root, bundle_binding, rows, proofs, publish=True
            )
            epoch = ACTIONS.index(action)
            core = {
                "schema_version": 1,
                "artifact_kind": "selected_successor_execution_lease",
                "lease_epoch": epoch,
                "bundle": normalize_binding(
                    bundle_binding, "selected-successor bundle"
                ),
                "authority_gate": gate,
                "authority_proofs": proofs,
                "execution_order": rows,
                "action": action,
                "prior_checkpoint": (
                    None if epoch == 0 else rows[epoch - 1]["expected_result"]
                ),
                "skills_root": (
                    str(skills_root.resolve()) if skills_root is not None else None
                ),
            }
            lease = {
                **core,
                "lease_id": "ssel-" + _sha256_bytes(_canonical_json(core))[:32],
            }
            payload = _canonical_json(lease)
            digest = _sha256_bytes(payload)
            path = _execution_lease_path(root, digest)
            observed, _created = _write_once_with_status(
                path,
                payload,
                "selected-successor execution lease",
                producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
            )
    return (
        {"ref": path.relative_to(root).as_posix(), "sha256": observed},
        gate,
        gate_created,
    )


__all__ = ("authority_gate", "publish_execution_lease")
