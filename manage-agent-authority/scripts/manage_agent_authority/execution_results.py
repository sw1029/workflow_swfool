from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import object_sha256, parse_time, read_object
from .canonical import resolve_workspace_path, sha256_file, write_immutable_json
from .projection_contracts import AUTHORIZATION_ROOT


VERIFICATION_KEYS = {
    "schema_version",
    "artifact_kind",
    "verification_id",
    "stage",
    "reservation",
    "reservation_state",
    "grant_states",
    "request_id",
    "effective_authority_fingerprint",
    "verified_at",
}
EXECUTION_RESULT_KEYS = {
    "schema_version",
    "artifact_kind",
    "result_id",
    "reservation",
    "pre_commit_verification",
    "owner_result",
    "effect_status",
    "subject_before",
    "subject_after",
    "expected_subject_after_sha256",
    "completed_at",
}


def _closed(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise SystemExit(f"{label} is not a closed typed JSON object.")
    return value


def _artifact_binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root.resolve()).as_posix(),
        "sha256": sha256_file(path),
    }


def _verify_binding(root: Path, binding: dict[str, str], label: str) -> Path:
    if not isinstance(binding, dict) or set(binding) != {"ref", "sha256"}:
        raise SystemExit(f"{label} must be an exact ref/sha256 binding.")
    path = resolve_workspace_path(root, binding["ref"], f"{label}.ref")
    if sha256_file(path) != binding["sha256"]:
        raise SystemExit(f"{label} SHA-256 does not match its immutable artifact.")
    return path


def validate_pre_commit_verification(
    root: Path,
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    binding: dict[str, str],
    *,
    expected_version: int,
    require_current_state: bool,
) -> dict[str, Any]:
    path = _verify_binding(root, binding, "pre_commit_verification")
    artifact = _closed(
        read_object(path, "pre-commit authority verification"),
        VERIFICATION_KEYS,
        "pre-commit authority verification",
    )
    if (
        artifact["schema_version"] != 2
        or artifact["artifact_kind"] != "authority_verification"
        or artifact["stage"] != "pre_commit"
    ):
        raise SystemExit("A typed pre_commit authority verification is required.")
    core = {key: value for key, value in artifact.items() if key != "verification_id"}
    expected_id = f"authv-{object_sha256(core)[:24]}"
    expected_ref = (
        AUTHORIZATION_ROOT / "verifications" / f"{expected_id}.json"
    ).as_posix()
    if artifact["verification_id"] != expected_id or binding["ref"] != expected_ref:
        raise SystemExit("Pre-commit verification identity is not deterministic.")
    if artifact["reservation"] != reservation_binding:
        raise SystemExit("Pre-commit verification binds a different reservation.")
    state = artifact["reservation_state"]
    expected_state_ref = (
        AUTHORIZATION_ROOT
        / "state"
        / "reservations"
        / f"{reservation['reservation_id']}.json"
    ).as_posix()
    if (
        not isinstance(state, dict)
        or state.get("ref") != expected_state_ref
        or state.get("version") != expected_version
        or state.get("status") != "reserved"
        or artifact["request_id"] != reservation["request_id"]
        or artifact["effective_authority_fingerprint"]
        != reservation["effective_authority_fingerprint"]
    ):
        raise SystemExit("Pre-commit verification does not bind the reserved CAS state.")
    if require_current_state:
        current = resolve_workspace_path(root, expected_state_ref, "reservation state")
        if sha256_file(current) != state.get("sha256"):
            raise SystemExit("Pre-commit verification reservation state is stale.")
    parse_time(artifact["verified_at"], "verification.verified_at")
    return artifact


def resolve_pre_commit_verification(
    root: Path,
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    binding: dict[str, str] | None,
    *,
    expected_version: int,
) -> tuple[dict[str, str], dict[str, Any]]:
    if binding is None:
        raise SystemExit(
            "Consume requires an explicit exact pre_commit verification binding."
        )
    return binding, validate_pre_commit_verification(
        root,
        reservation,
        reservation_binding,
        binding,
        expected_version=expected_version,
        require_current_state=True,
    )


def create_execution_result(
    root: Path,
    reservation: dict[str, Any],
    decision: dict[str, Any],
    reservation_binding: dict[str, str],
    verification_binding: dict[str, str],
    owner_result: dict[str, str],
    *,
    completed_at: str,
    expected_subject_after_sha256: str | None,
) -> tuple[dict[str, Any], dict[str, str]]:
    owner_path = _verify_binding(root, owner_result, "owner execution_result")
    # The owner artifact remains opaque because each effect owner has its own
    # closed schema. Authority supplies the cross-owner typed settlement wrapper.
    read_object(owner_path, "owner execution_result")
    subject_before = decision["request"]["subject"]
    subject_path = resolve_workspace_path(
        root,
        subject_before["ref"],
        "post-effect authority subject",
        must_exist=True,
        regular_file=True,
    )
    actual_after = sha256_file(subject_path)
    if expected_subject_after_sha256 is None:
        raise SystemExit(
            "Consume requires expected_subject_after_sha256 for the exact effect target."
        )
    expected_after = expected_subject_after_sha256
    if actual_after != expected_after:
        raise SystemExit("Post-effect authority subject does not match expected after digest.")
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_execution_result",
        "reservation": reservation_binding,
        "pre_commit_verification": verification_binding,
        "owner_result": owner_result,
        "effect_status": "confirmed_effect",
        "subject_before": subject_before,
        "subject_after": {"ref": subject_before["ref"], "sha256": actual_after},
        "expected_subject_after_sha256": expected_after,
        "completed_at": parse_time(completed_at, "completed_at").isoformat(),
    }
    result = {"result_id": f"authr-{object_sha256(core)[:24]}", **core}
    path = (
        root.resolve()
        / AUTHORIZATION_ROOT
        / "execution_results"
        / f"{result['result_id']}.json"
    )
    write_immutable_json(path, result, "authority execution result")
    return result, _artifact_binding(root, path)


def validate_execution_result(
    root: Path,
    binding: dict[str, str],
    reservation: dict[str, Any],
    reservation_binding: dict[str, str],
    verification_binding: dict[str, str],
    expected_subject_before: dict[str, Any],
) -> dict[str, Any]:
    path = _verify_binding(root, binding, "authority execution_result")
    result = _closed(
        read_object(path, "authority execution result"),
        EXECUTION_RESULT_KEYS,
        "authority execution result",
    )
    core = {key: value for key, value in result.items() if key != "result_id"}
    expected_id = f"authr-{object_sha256(core)[:24]}"
    expected_ref = (
        AUTHORIZATION_ROOT / "execution_results" / f"{expected_id}.json"
    ).as_posix()
    if (
        result["schema_version"] != 2
        or result["artifact_kind"] != "authority_execution_result"
        or result["result_id"] != expected_id
        or binding["ref"] != expected_ref
        or result["reservation"] != reservation_binding
        or result["pre_commit_verification"] != verification_binding
        or result["effect_status"] != "confirmed_effect"
    ):
        raise SystemExit("Authority execution result binding is invalid.")
    if result["subject_before"] != expected_subject_before:
        raise SystemExit("Authority execution result subject binding is invalid.")
    if (
        not isinstance(result["subject_after"], dict)
        or result["subject_after"].get("ref") != result["subject_before"].get("ref")
        or result["subject_after"].get("sha256")
        != result["expected_subject_after_sha256"]
    ):
        raise SystemExit("Authority execution result after-state is invalid.")
    _verify_binding(root, result["owner_result"], "owner execution_result")
    parse_time(result["completed_at"], "execution_result.completed_at")
    return result
