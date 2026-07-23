"""Static owner-result validator registry and trusted subprocess adapter.

Authority never executes a callable named by workspace data.  The exact
operation identity selects one checked-in owner command, and the command
returns a closed validation receipt that authority binds into settlement.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from .canonical import object_sha256, parse_time, write_immutable_json
from .canonical import resolve_workspace_path
from .owner_validation_io import read_bound_owner_validation_receipt
from .owner_validator_process import MAX_OWNER_VALIDATOR_STDERR_BYTES
from .owner_validator_process import MAX_OWNER_VALIDATOR_STDOUT_BYTES
from .owner_validator_process import run_bounded_owner_validator
from .owner_validator_registry import (
    OWNER_VALIDATORS,
    OperationIdentity,
    OwnerValidatorSpec,
)


Runner = Callable[..., subprocess.CompletedProcess[str]]

RECEIPT_REQUIRED_KEYS = {
    "schema_version",
    "artifact_kind",
    "validation_status",
    "outcome",
    "operation",
    "owner_result",
    "reservation",
    "pre_commit_verification",
    "phase",
    "subject",
    "event_batch",
    "descendant_event_count",
    "validated_at",
    "receipt_sha256",
}
RECEIPT_OPTIONAL_KEYS = {"projection", "plan"}
SUBJECT_KEYS = {"kind", "ref", "before_sha256", "after_sha256"}
EVENT_BATCH_KEYS = {
    "plan_id",
    "before_event_count",
    "event_count",
    "event_payload_sha256",
}
BINDING_KEYS = {"ref", "sha256"}
OUTCOMES = {"confirmed_effect", "confirmed_no_effect", "unknown_effect"}


def operation_identity(request: dict[str, Any]) -> OperationIdentity:
    identity = tuple(
        str(request.get(field) or "")
        for field in (
            "skill_id",
            "skill_version",
            "operation_id",
            "operation_version",
        )
    )
    if not all(identity):
        raise SystemExit("Authority request has an incomplete owner operation identity.")
    return identity  # type: ignore[return-value]


def registered_owner_validator(request: dict[str, Any]) -> OwnerValidatorSpec:
    identity = operation_identity(request)
    spec = OWNER_VALIDATORS.get(identity)
    if spec is None:
        raise SystemExit(
            "No trusted owner-result validator is registered for operation "
            + ":".join(identity)
            + "."
        )
    return spec


def require_registered_owner_settlement(
    request: Any, owner_validation: dict[str, str] | None
) -> None:
    """Prevent a registered owner operation from creating a new legacy result."""

    if not isinstance(request, dict):
        raise SystemExit("Authority decision request is invalid.")
    if owner_validation is None and operation_identity(request) in OWNER_VALIDATORS:
        raise SystemExit(
            "Registered owner operations require authority settle and "
            "a schema-v3 owner-validation receipt."
        )


def _binding(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != BINDING_KEYS:
        raise SystemExit(f"{label} must be an exact ref/sha256 binding.")
    ref = value.get("ref")
    digest = value.get("sha256")
    if (
        not isinstance(ref, str)
        or not ref
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise SystemExit(f"{label} binding is invalid.")
    return {"ref": ref, "sha256": digest}


def _sha(value: Any, label: str) -> str:
    digest = str(value or "")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise SystemExit(f"{label} must be a full lowercase SHA-256 digest.")
    return digest


def _validate_receipt_header(
    receipt: Any, request: dict[str, Any], phase: str
) -> dict[str, Any]:
    if not isinstance(receipt, dict):
        raise SystemExit("Owner validator did not return a JSON object.")
    keys = set(receipt)
    if not RECEIPT_REQUIRED_KEYS <= keys or keys - (
        RECEIPT_REQUIRED_KEYS | RECEIPT_OPTIONAL_KEYS
    ):
        raise SystemExit("Owner validation receipt is not a closed schema-v1 object.")
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind") != "owner_validation_receipt"
        or receipt.get("validation_status") not in {"valid", "legacy_opaque"}
        or receipt.get("outcome") not in OUTCOMES
        or receipt.get("operation") != request.get("operation_id")
        or receipt.get("phase") != phase
    ):
        raise SystemExit("Owner validation receipt header is invalid.")
    if receipt["validation_status"] == "legacy_opaque" and receipt["outcome"] != "unknown_effect":
        raise SystemExit("Legacy opaque owner results cannot confirm an effect outcome.")
    return receipt


def _validate_receipt_inputs(
    receipt: dict[str, Any],
    owner_result: dict[str, str],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
) -> None:
    if (
        _binding(receipt.get("owner_result"), "owner validation owner_result")
        != _binding(owner_result, "owner_result")
        or _binding(receipt.get("reservation"), "owner validation reservation")
        != _binding(reservation, "reservation")
        or _binding(
            receipt.get("pre_commit_verification"),
            "owner validation pre_commit_verification",
        )
        != _binding(pre_commit_verification, "pre_commit_verification")
    ):
        raise SystemExit("Owner validation receipt binds different authority inputs.")


def _validate_receipt_digest(receipt: dict[str, Any]) -> None:
    supplied_digest = _sha(
        receipt.get("receipt_sha256"), "owner validation receipt_sha256"
    )
    core = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if supplied_digest != object_sha256(core):
        raise SystemExit("Owner validation receipt_sha256 is invalid.")


def _validate_legacy_receipt(receipt: dict[str, Any]) -> None:
    if (
        receipt.get("event_batch") is not None
        or receipt.get("plan") is not None
        or receipt.get("descendant_event_count") != 0
    ):
        raise SystemExit("Legacy opaque owner validation claims typed effect proof.")
    _validate_receipt_digest(receipt)


def _validate_receipt_subject(
    receipt: dict[str, Any], request: dict[str, Any]
) -> tuple[str, str]:
    subject = receipt.get("subject")
    if not isinstance(subject, dict) or set(subject) != SUBJECT_KEYS:
        raise SystemExit("Owner validation receipt subject is not closed.")
    request_subject = request.get("subject") or {}
    before = _sha(subject.get("before_sha256"), "owner validation before_sha256")
    after = _sha(subject.get("after_sha256"), "owner validation after_sha256")
    if request_subject.get("kind") == "task_index":
        if (
            subject.get("kind") != "task_index"
            or subject.get("ref") != request_subject.get("ref")
            or before != request_subject.get("digest")
        ):
            raise SystemExit("Owner validation receipt subject does not match the request.")
    elif request_subject.get("kind") in {
        "task_index_transition_plan",
        "task_state_transition_plan",
    }:
        if (
            receipt.get("plan")
            != {
                "ref": request_subject.get("ref"),
                "sha256": request_subject.get("digest"),
            }
            or subject.get("kind") != "task_index"
            or subject.get("ref") != ".task/index.jsonl"
        ):
            raise SystemExit(
                "Owner validation receipt does not bind the authorized transition plan."
            )
    elif request_subject.get("kind") == "selection_publication_binding":
        if (
            receipt.get("plan")
            != {
                "ref": request_subject.get("ref"),
                "sha256": request_subject.get("digest"),
            }
            or subject.get("kind") != "task_alias"
            or subject.get("ref") != "task.md"
        ):
            raise SystemExit(
                "Owner validation receipt does not bind the authorized publication prepare."
            )
    elif request_subject.get("kind") in {
        "selection_publication_gc_plan",
        "selection_publication_gc_receipt",
    }:
        if (
            receipt.get("plan")
            != {
                "ref": request_subject.get("ref"),
                "sha256": request_subject.get("digest"),
            }
            or subject.get("kind") != "selection_publication_cas_set"
            or subject.get("ref") != ".task/selection_publication/blobs/sha256"
        ):
            raise SystemExit(
                "Owner validation receipt does not bind the authorized "
                "selection-publication retention boundary."
            )
    else:
        raise SystemExit("Registered owner validation received an unsupported subject kind.")
    return before, after


def _validate_receipt_effect(
    receipt: dict[str, Any], before: str, after: str
) -> None:
    if receipt["outcome"] == "confirmed_no_effect" and after != before:
        raise SystemExit("Confirmed no-effect owner validation changed the subject digest.")
    event_batch = receipt.get("event_batch")
    if not isinstance(event_batch, dict) or set(event_batch) != EVENT_BATCH_KEYS:
        raise SystemExit("Owner validation receipt event_batch is not closed.")
    if not isinstance(event_batch.get("plan_id"), str) or not event_batch["plan_id"]:
        raise SystemExit("Owner validation receipt plan_id is invalid.")
    if any(
        type(event_batch.get(field)) is not int or event_batch[field] < 0
        for field in ("before_event_count", "event_count")
    ):
        raise SystemExit("Owner validation receipt event counts are invalid.")
    _sha(
        event_batch.get("event_payload_sha256"),
        "owner validation event_payload_sha256",
    )
    projection = receipt.get("projection")
    projection_changed = bool(
        isinstance(projection, dict)
        and projection.get("before_sha256") != projection.get("after_sha256")
    )
    if (
        receipt["outcome"] == "confirmed_effect"
        and after == before
        and not projection_changed
    ):
        raise SystemExit("Confirmed effect lacks a changed owner boundary.")
    if receipt["outcome"] == "confirmed_no_effect" and event_batch["event_count"]:
        raise SystemExit("Confirmed no-effect owner validation contains events.")
    if type(receipt.get("descendant_event_count")) is not int or receipt[
        "descendant_event_count"
    ] < 0:
        raise SystemExit("Owner validation descendant_event_count is invalid.")
    parse_time(receipt.get("validated_at"), "owner validation validated_at")
    _validate_receipt_digest(receipt)


def validate_owner_validation_receipt(
    receipt: Any,
    *,
    request: dict[str, Any],
    owner_result: dict[str, str],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
    phase: str,
) -> dict[str, Any]:
    """Validate the common authority-facing envelope of an owner receipt."""

    receipt = _validate_receipt_header(receipt, request, phase)
    _validate_receipt_inputs(
        receipt, owner_result, reservation, pre_commit_verification
    )
    if receipt["validation_status"] == "legacy_opaque":
        _validate_legacy_receipt(receipt)
        return receipt
    before, after = _validate_receipt_subject(receipt, request)
    _validate_receipt_effect(receipt, before, after)
    return receipt


def _trusted_import_path(skills_root: Path, skill: str) -> Path:
    return resolve_workspace_path(
        skills_root,
        f"{skill}/scripts",
        f"registered owner validator import root {skill}",
        regular_file=False,
    )


def invoke_registered_owner_validator(
    root: Path,
    request: dict[str, Any],
    owner_result: dict[str, str],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
    *,
    phase: str,
    skills_root: Path | None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    if phase not in {"current", "historical"}:
        raise SystemExit("Owner validation phase must be current or historical.")
    spec = registered_owner_validator(request)
    trusted_root = Path(__file__).resolve().parents[3]
    if skills_root is not None and skills_root.resolve() != trusted_root:
        raise SystemExit(
            "Registered owner validators require the co-located checked-in skills root."
        )
    import_roots = [
        _trusted_import_path(trusted_root, skill) for skill in spec.import_skills
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in import_roots)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONSAFEPATH"] = "1"
    argv = [
        sys.executable,
        "-P",
        "-m",
        spec.module,
        spec.argv_prefix[0],
        "--root",
        str(root.resolve()),
        *spec.argv_prefix[1:],
        "--owner-result-ref",
        owner_result["ref"],
        "--owner-result-sha256",
        owner_result["sha256"],
        "--reservation-ref",
        reservation["ref"],
        "--reservation-sha256",
        reservation["sha256"],
        "--pre-commit-ref",
        pre_commit_verification["ref"],
        "--pre-commit-sha256",
        pre_commit_verification["sha256"],
        "--phase",
        phase,
    ]
    try:
        if runner is subprocess.run:
            completed = run_bounded_owner_validator(
                argv, cwd=trusted_root, env=environment, timeout=30
            )
        else:
            completed = runner(
                argv,
                # Test/custom runners retain the public adapter shape.
                cwd=trusted_root,
                env=environment,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"Registered owner validator could not run: {exc}") from exc
    if (
        len(completed.stdout.encode("utf-8")) > MAX_OWNER_VALIDATOR_STDOUT_BYTES
        or len(completed.stderr.encode("utf-8")) > MAX_OWNER_VALIDATOR_STDERR_BYTES
    ):
        raise SystemExit("Registered owner validator output exceeds its safety limit.")
    if completed.returncode != 0:
        message = completed.stderr.strip() or "registered owner validator failed"
        raise SystemExit(message[:2000])
    try:
        receipt = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit("Registered owner validator returned malformed JSON.") from exc
    return validate_owner_validation_receipt(
        receipt,
        request=request,
        owner_result=owner_result,
        reservation=reservation,
        pre_commit_verification=pre_commit_verification,
        phase=phase,
    )


def publish_owner_validation_receipt(
    root: Path, receipt: dict[str, Any]
) -> dict[str, str]:
    digest = receipt["receipt_sha256"]
    path = (
        root.resolve()
        / ".task"
        / "authorization"
        / "owner_validations"
        / f"owner-validation-{digest}.json"
    )
    file_digest = write_immutable_json(path, receipt, "owner validation receipt")
    return {"ref": path.relative_to(root.resolve()).as_posix(), "sha256": file_digest}


def load_owner_validation_receipt(
    root: Path,
    binding: dict[str, str],
    *,
    request: dict[str, Any],
    owner_result: dict[str, str],
    reservation: dict[str, str],
    pre_commit_verification: dict[str, str],
    phase: str = "current",
) -> dict[str, Any]:
    normalized = _binding(binding, "owner_validation")
    _, receipt = read_bound_owner_validation_receipt(root, normalized)
    validated = validate_owner_validation_receipt(
        receipt,
        request=request,
        owner_result=owner_result,
        reservation=reservation,
        pre_commit_verification=pre_commit_verification,
        phase=phase,
    )
    expected_ref = (
        ".task/authorization/owner_validations/"
        f"owner-validation-{validated['receipt_sha256']}.json"
    )
    if normalized["ref"] != expected_ref:
        raise SystemExit("owner_validation is not at its canonical receipt path.")
    return validated


__all__ = (
    "OWNER_VALIDATORS",
    "invoke_registered_owner_validator",
    "require_registered_owner_settlement",
    "load_owner_validation_receipt",
    "operation_identity",
    "publish_owner_validation_receipt",
    "registered_owner_validator",
    "validate_owner_validation_receipt",
)
