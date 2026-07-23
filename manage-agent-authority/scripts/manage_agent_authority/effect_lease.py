"""Authority-owned lock lease for a bounded local effect.

The lease does not spend authority.  It atomically proves that the reservation
is still in its exact reserved CAS state at the first owner effect, and keeps
the authority projection lock held until the owner receipt is durable.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Iterator

from .canonical import (
    authority_lock,
    object_sha256,
    read_object,
    sha256_file,
    write_immutable_json,
)
from .evaluator import load_bound_decision
from .execution_results import validate_pre_commit_verification
from .lifecycle import load_reservation
from .projection_recovery import recover_projection_intents


LEASE_KEYS = {
    "schema_version",
    "artifact_kind",
    "lease_id",
    "operation",
    "subject",
    "reservation",
    "reservation_state",
    "pre_commit_verification",
    "acquired_at",
}


def _binding(value: Any, label: str) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"ref", "sha256"}
        or not isinstance(value.get("ref"), str)
        or not isinstance(value.get("sha256"), str)
        or len(value["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in value["sha256"])
    ):
        raise SystemExit(f"{label} must be an exact ref/sha256 binding.")
    return {"ref": value["ref"], "sha256": value["sha256"]}


def _lease_body(
    *,
    operation: str,
    subject: dict[str, Any],
    reservation: dict[str, str],
    reservation_state: dict[str, Any],
    pre_commit_verification: dict[str, str],
    acquired_at: str,
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "artifact_kind": "authority_effect_lease",
        "operation": operation,
        "subject": subject,
        "reservation": reservation,
        "reservation_state": reservation_state,
        "pre_commit_verification": pre_commit_verification,
        "acquired_at": acquired_at,
    }
    return {
        **core,
        "lease_id": f"authe-{object_sha256(core)[:24]}",
    }


def _validate_request(
    root: Path,
    reservation: dict[str, Any],
    *,
    operation: str,
    subject: dict[str, Any],
) -> None:
    decision, _ = load_bound_decision(
        root,
        reservation["decision"]["ref"],
        reservation["decision"]["sha256"],
    )
    request = decision.get("request")
    if (
        not isinstance(request, dict)
        or request.get("operation_id") != operation
        or request.get("subject") != subject
    ):
        raise SystemExit(
            "Authority effect lease operation or subject differs from its decision."
        )


def _lease_path(root: Path, lease_id: str) -> Path:
    return (
        root.resolve()
        / ".task"
        / "authorization"
        / "effect_leases"
        / f"{lease_id}.json"
    )


def validate_effect_lease(
    root: Path,
    value: Any,
    *,
    operation: str,
    subject: dict[str, Any],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
) -> dict[str, Any]:
    binding = _binding(value, "authority effect lease")
    path = (root.resolve() / binding["ref"]).resolve(strict=False)
    expected_parent = root.resolve() / ".task" / "authorization" / "effect_leases"
    if path.parent != expected_parent or path.is_symlink() or not path.is_file():
        raise SystemExit("Authority effect lease path is not canonical.")
    if sha256_file(path) != binding["sha256"]:
        raise SystemExit("Authority effect lease digest differs.")
    lease = read_object(path, "authority effect lease")
    if (
        not isinstance(lease, dict)
        or set(lease) != LEASE_KEYS
        or lease.get("schema_version") != 1
        or lease.get("artifact_kind") != "authority_effect_lease"
        or lease.get("operation") != operation
        or lease.get("subject") != subject
        or lease.get("reservation") != reservation
        or lease.get("pre_commit_verification") != pre_commit_verification
        or path != _lease_path(root, str(lease.get("lease_id") or ""))
    ):
        raise SystemExit("Authority effect lease contract differs.")
    core = {key: value for key, value in lease.items() if key != "lease_id"}
    if lease["lease_id"] != f"authe-{object_sha256(core)[:24]}":
        raise SystemExit("Authority effect lease identity differs.")
    return lease


@contextlib.contextmanager
def acquire_effect_lease(
    root: Path,
    *,
    operation: str,
    subject: dict[str, Any],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
    expected_version: int,
    skills_root: Path | None = None,
) -> Iterator[dict[str, str]]:
    """Hold the authority lock across one exact owner effect."""

    root = root.resolve()
    reservation_binding = _binding(reservation, "authority reservation")
    precommit_binding = _binding(
        pre_commit_verification, "pre_commit_verification"
    )
    with authority_lock(root):
        recover_projection_intents(root, skills_root=skills_root)
        artifact, path, state = load_reservation(
            root,
            reservation_binding["ref"],
            reservation_binding["sha256"],
        )
        if path.relative_to(root).as_posix() != reservation_binding["ref"]:
            raise SystemExit("Authority effect lease reservation path differs.")
        if (
            state.get("status") != "reserved"
            or state.get("version") != expected_version
        ):
            raise SystemExit(
                "Authority effect lease requires the expected reserved CAS state."
            )
        _validate_request(
            root, artifact, operation=operation, subject=subject
        )
        verification = validate_pre_commit_verification(
            root,
            artifact,
            reservation_binding,
            precommit_binding,
            expected_version=expected_version,
            require_current_state=True,
        )
        state_binding = dict(verification["reservation_state"])
        lease = _lease_body(
            operation=operation,
            subject=subject,
            reservation=reservation_binding,
            reservation_state=state_binding,
            pre_commit_verification=precommit_binding,
            acquired_at=verification["verified_at"],
        )
        lease_path = _lease_path(root, lease["lease_id"])
        digest = write_immutable_json(
            lease_path, lease, "authority effect lease"
        )
        binding = {
            "ref": lease_path.relative_to(root).as_posix(),
            "sha256": digest,
        }
        validate_effect_lease(
            root,
            binding,
            operation=operation,
            subject=subject,
            reservation=reservation_binding,
            pre_commit_verification=precommit_binding,
        )
        yield binding
        # The lock excludes authority-owned transitions.  A final exact state
        # check also detects direct projection tampering before owner receipt.
        current = root / state_binding["ref"]
        if sha256_file(current) != state_binding["sha256"]:
            raise SystemExit(
                "Authority reservation changed while its effect lease was held."
            )


__all__ = ("acquire_effect_lease", "validate_effect_lease")
