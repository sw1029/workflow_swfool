"""Verify one reservation and publish only the derived typed verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT
from .canonical import object_sha256, parse_time, write_immutable_json
from .lifecycle import verify_reservation_with_recovery


def _verify_and_publish(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    *,
    stage: str,
    verified_at: str,
    expected_version: int,
    skills_root: Path | None,
) -> dict[str, Any]:
    if stage not in {"pre_dispatch", "pre_commit"}:
        raise SystemExit("Authority verification stage is invalid.")
    root = root.resolve()
    reservation, state, verification, state_sha256 = (
        verify_reservation_with_recovery(
            root,
            reservation_ref,
            reservation_sha256,
            verified_at=verified_at,
            expected_version=expected_version,
            skills_root=skills_root,
        )
    )
    state_path = (
        root
        / AUTHORIZATION_ROOT
        / "state"
        / "reservations"
        / f"{reservation['reservation_id']}.json"
    )
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_verification",
        "stage": stage,
        "reservation": {"ref": reservation_ref, "sha256": reservation_sha256},
        "reservation_state": {
            "ref": state_path.relative_to(root).as_posix(),
            "sha256": state_sha256,
            "version": state["version"],
            "status": state["status"],
        },
        "grant_states": verification["grant_states"],
        "request_id": verification["decision"]["request"]["request_id"],
        "effective_authority_fingerprint": reservation[
            "effective_authority_fingerprint"
        ],
        "verified_at": parse_time(verified_at, "at").isoformat(),
    }
    artifact = {"verification_id": f"authv-{object_sha256(core)[:24]}", **core}
    path = (
        root
        / AUTHORIZATION_ROOT
        / "verifications"
        / f"{artifact['verification_id']}.json"
    )
    digest = write_immutable_json(path, artifact, "authority verification")
    return {
        "status": "verified",
        **artifact,
        "verification_ref": path.relative_to(root).as_posix(),
        "verification_sha256": digest,
    }


def verify_and_publish_precommit(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    *,
    verified_at: str,
    expected_version: int,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Publish a pre-commit verification derived from current reservation state."""

    return _verify_and_publish(
        root,
        reservation_ref,
        reservation_sha256,
        stage="pre_commit",
        verified_at=verified_at,
        expected_version=expected_version,
        skills_root=skills_root,
    )


def verify_and_publish_predispatch(
    root: Path,
    reservation_ref: str,
    reservation_sha256: str,
    *,
    verified_at: str,
    expected_version: int,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Publish a pre-dispatch verification for the compatibility CLI route."""

    return _verify_and_publish(
        root,
        reservation_ref,
        reservation_sha256,
        stage="pre_dispatch",
        verified_at=verified_at,
        expected_version=expected_version,
        skills_root=skills_root,
    )


__all__ = ("verify_and_publish_precommit", "verify_and_publish_predispatch")
