from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import load_grant, verify_binding
from .canonical import parse_time, resolve_workspace_path, sha256_file
from .evaluation_context import validate_evaluation_context, verify_request_evidence
from .operations import load_operation
from .root_grant_request_binding import root_grant_request_binding_covers


def subject_preflight(root: Path, request: dict[str, Any]) -> None:
    ref = str(request["subject"]["ref"])
    candidate = resolve_workspace_path(
        root,
        ref,
        "authority subject",
        must_exist=True,
        regular_file=True,
    )
    try:
        current_digest = sha256_file(candidate)
    except OSError as exc:
        raise SystemExit(
            "Authority subject must remain an existing readable regular file."
        ) from exc
    if current_digest != request["subject"]["digest"]:
        raise SystemExit("Authority subject changed after its exact digest was bound.")


def verify_manifest(decision: dict[str, Any], skills_root: Path | None) -> None:
    request = decision["request"]
    _, binding = load_operation(
        request["skill_id"],
        request["skill_version"],
        request["operation_id"],
        request["operation_version"],
        skills_root=skills_root,
    )
    if binding != decision["operation_manifest"]:
        raise SystemExit("Operation manifest changed after authority evaluation.")


def validate_selected_grants(
    root: Path,
    selected: list[dict[str, Any]],
    *,
    expected_versions: dict[str, int] | None = None,
    minimum_versions: bool = False,
    request: dict[str, Any] | None = None,
    at: str,
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    records: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    now = parse_time(at, "verification time")
    for binding in selected:
        grant, digest, state = load_grant(root, binding["grant_id"])
        if digest != binding["grant_sha256"]:
            raise SystemExit("Authority grant changed after evaluation.")
        if request is not None and not root_grant_request_binding_covers(
            grant, request
        ):
            raise SystemExit(
                "Plan-bound root grant does not cover the decision's exact request: "
                f"{grant['grant_id']}."
            )
        expected = (
            binding["state_version"]
            if expected_versions is None
            else expected_versions[grant["grant_id"]]
        )
        version_conflict = (
            state["version"] < expected
            if minimum_versions
            else state["version"] != expected
        )
        if version_conflict:
            raise SystemExit(
                f"Authority grant CAS conflict for {grant['grant_id']}: "
                f"expected {expected}, found {state['version']}."
            )
        if state["status"] != "active":
            raise SystemExit(
                f"Authority grant is no longer active: {grant['grant_id']}"
            )
        if grant.get("expires_at") and (
            parse_time(grant["expires_at"], "grant.expires_at") <= now
        ):
            raise SystemExit(
                f"Authority grant expired before dispatch: {grant['grant_id']}"
            )
        verify_binding(root, grant["policy_snapshot"], "grant policy_snapshot")
        records.append((grant, digest, state))
    return records


def decision_grant_bindings(decision: dict[str, Any]) -> list[dict[str, Any]]:
    combined = decision.get("selected_grants", []) + decision.get("lineage_grants", [])
    by_id: dict[str, dict[str, Any]] = {}
    for binding in combined:
        existing = by_id.get(binding["grant_id"])
        if existing is not None and existing != binding:
            raise SystemExit("Authority decision has conflicting lineage bindings.")
        by_id[binding["grant_id"]] = binding
    return [by_id[key] for key in sorted(by_id)]


def verify_bound_decision_evidence(root: Path, decision: dict[str, Any]) -> None:
    validate_evaluation_context(root, decision["evaluation_context"])
    verify_request_evidence(root, decision["request"])
