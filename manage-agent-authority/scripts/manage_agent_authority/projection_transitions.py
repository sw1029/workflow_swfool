from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import parse_time
from .canonical import resolve_workspace_path
from .contracts import validate_grant
from .projection_contracts import AUTHORIZATION_ROOT
from .projection_contracts import GRANT_STATUSES
from .projection_contracts import STATE_ROOT
from .projection_contracts import TRANSITION_KEYS
from .projection_contracts import closed
from .projection_contracts import identifier
from .projection_contracts import nonnegative_int
from .projection_io import changes_by_ref
from .projection_io import expected_path
from .projection_io import intent_changes
from .projection_io import load_grant_artifact
from .projection_io import safe_json
from .projection_io import validate_grant_state
from .projection_io import verify_file_binding
from .source_approval import load_source_approval
from .source_approval import validate_for_transition


def _all_grants(root: Path) -> dict[str, dict[str, Any]]:
    directory = root.resolve() / AUTHORIZATION_ROOT / "grants"
    if not directory.exists() and not directory.is_symlink():
        return {}
    ref = directory.relative_to(root.resolve()).as_posix()
    resolved = resolve_workspace_path(
        root, ref, "authority grants directory", regular_file=False
    )
    if not resolved.is_dir():
        raise SystemExit("Authority grants directory must be a real directory.")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(resolved.iterdir()):
        if path.suffix != ".json":
            continue
        raw, _ = safe_json(root, path, "authority grant")
        grant = validate_grant(raw)
        if path.name != f"{grant['grant_id']}.json" or grant["grant_id"] in result:
            raise SystemExit("Authority grant path or identity is duplicated.")
        result[grant["grant_id"]] = grant
    return result


def _descendants(grants: dict[str, dict[str, Any]], grant_id: str) -> list[str]:
    result: list[str] = []
    frontier = [grant_id]
    seen = {grant_id}
    while frontier:
        parent = frontier.pop(0)
        children = sorted(
            candidate
            for candidate, grant in grants.items()
            if grant.get("parent_grant_id") == parent
        )
        for child in children:
            if child in seen:
                raise SystemExit("Authority grant lineage is circular.")
            seen.add(child)
            result.append(child)
            frontier.append(child)
    return result


def validate_transition(
    root: Path, artifact: dict[str, Any], path: Path
) -> list[dict[str, Any]]:
    event = closed(artifact, TRANSITION_KEYS, "authority transition event")
    if (
        event["schema_version"] != 2
        or event["artifact_kind"] != "authority_grant_transition"
    ):
        raise SystemExit("Authority transition event contract is invalid.")
    event_id = identifier(event["event_id"], "transition event ID")
    expected_path(
        root,
        path,
        AUTHORIZATION_ROOT / "events" / f"{event_id}.json",
        "authority transition event",
    )
    root_grant_id = identifier(event["root_grant_id"], "transition root_grant_id")
    if event["transition"] not in {"revoked", "suspended", "expired", "reactivated"}:
        raise SystemExit("Authority transition kind is invalid.")
    _, source_path = verify_file_binding(
        root, event["source_approval"], "transition source_approval"
    )
    transitioned_at = parse_time(event["transitioned_at"], "transitioned_at")
    grants = _all_grants(root)
    if root_grant_id not in grants:
        raise SystemExit("Authority transition root grant is missing.")
    grant = grants[root_grant_id]
    validate_for_transition(
        root, load_source_approval(source_path), grant, event["transitioned_at"]
    )
    if event["transition"] == "expired":
        if (
            grant["expires_at"] is None
            or parse_time(grant["expires_at"], "grant.expires_at") > transitioned_at
        ):
            raise SystemExit(
                "Authority transition expires a grant before its exact expiry."
            )
    if (
        event["transition"] == "reactivated"
        and grant["expires_at"] is not None
        and parse_time(grant["expires_at"], "grant.expires_at") <= transitioned_at
    ):
        raise SystemExit("Authority transition reactivates an expired grant.")
    targets = [root_grant_id]
    if event["transition"] in {"revoked", "expired"}:
        targets.extend(_descendants(grants, root_grant_id))
    if event["affected_grant_ids"] != targets:
        raise SystemExit("Authority transition affected-grant closure is invalid.")
    before_records = event["affected_before"]
    if not isinstance(before_records, list) or len(before_records) != len(targets):
        raise SystemExit("Authority transition affected_before is invalid.")
    changes = intent_changes(root, event, path)
    by_ref = changes_by_ref(changes)
    expected_refs: set[str] = set()
    target_status = (
        "active" if event["transition"] == "reactivated" else event["transition"]
    )
    for index, target in enumerate(targets):
        record = closed(
            before_records[index],
            {"grant_id", "status", "version"},
            f"transition affected_before[{index}]",
        )
        if record["grant_id"] != target or record["status"] not in GRANT_STATUSES:
            raise SystemExit(
                "Authority transition affected_before identity is invalid."
            )
        nonnegative_int(
            record["version"], f"transition affected_before[{index}].version"
        )
        _, digest = load_grant_artifact(root, target)
        ref = (STATE_ROOT / "grants" / f"{target}.json").as_posix()
        expected_refs.add(ref)
        change = by_ref.get(ref)
        if change is None or change["before"] is None:
            raise SystemExit("Authority transition is missing an exact grant change.")
        before = validate_grant_state(
            change["before"], grants[target], digest, f"transition {event_id} before"
        )
        after = validate_grant_state(
            change["after"], grants[target], digest, f"transition {event_id} after"
        )
        if record != {
            "grant_id": target,
            "status": before["status"],
            "version": before["version"],
        }:
            raise SystemExit(
                "Authority transition affected_before does not bind its state change."
            )
        expected_after = {
            **before,
            "status": target_status,
            "version": before["version"] + 1,
            "last_event_id": event_id,
        }
        if after != expected_after:
            raise SystemExit("Authority transition state change is forged.")
        if index == 0:
            if event["transition"] == "reactivated" and before["status"] != "suspended":
                raise SystemExit("Authority transition reactivation source is invalid.")
            if event["transition"] == "suspended" and before["status"] != "active":
                raise SystemExit("Authority transition suspension source is invalid.")
            if event["transition"] in {"revoked", "expired"} and before[
                "status"
            ] not in {"active", "suspended"}:
                raise SystemExit("Authority terminal transition source is invalid.")
    if set(by_ref) != expected_refs:
        raise SystemExit("Authority transition contains an unknown projection ref.")
    return changes
