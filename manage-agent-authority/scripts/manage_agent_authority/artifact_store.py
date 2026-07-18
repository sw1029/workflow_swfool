from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .canonical import authority_lock
from .canonical import object_sha256
from .canonical import parse_time
from .canonical import read_object
from .canonical import resolve_workspace_path
from .canonical import sha256_file
from .canonical import write_immutable_json
from .canonical import write_json_atomic
from .contracts import cardinality_covers
from .contracts import rank_value
from .contracts import risk_value
from .contracts import validate_grant
from .source_approval import load_source_approval
from .source_approval import validate_for_grant
from .source_approval import validate_for_transition
from .projection_recovery import apply_projection_changes
from .projection_recovery import projection_change
from .projection_recovery import recover_projection_intents
from .projection_recovery import validated_settled_intent


AUTHORIZATION_ROOT = Path(".task/authorization")


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root.resolve()).as_posix()


def _source_signature(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _stage_snapshot(source: Path, directory: Path) -> tuple[Path, str]:
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=".snapshot.", suffix=".tmp", dir=directory
    )
    temporary = Path(temporary_value)
    source_descriptor: int | None = None
    staged = False
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        source_descriptor = os.open(source, flags)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            with os.fdopen(source_descriptor, "rb") as input_handle:
                source_descriptor = None
                before = os.fstat(input_handle.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise SystemExit("Snapshot source must remain a regular file.")
                digest = hashlib.sha256()
                for chunk in iter(lambda: input_handle.read(1024 * 1024), b""):
                    digest.update(chunk)
                    output.write(chunk)
                after = os.fstat(input_handle.fileno())
                path_after = os.stat(source, follow_symlinks=False)
                if _source_signature(before) != _source_signature(
                    after
                ) or _source_signature(before) != _source_signature(path_after):
                    raise SystemExit("Snapshot source changed during acquisition.")
                output.flush()
                os.fsync(output.fileno())
        staged = True
        return temporary, digest.hexdigest()
    except OSError as exc:
        raise SystemExit(
            f"Snapshot source could not be acquired safely: {exc}"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if source_descriptor is not None:
            os.close(source_descriptor)
        if not staged and temporary.exists():
            temporary.unlink()


def _install_snapshot(temporary: Path, target: Path, digest: str) -> None:
    created = False
    try:
        try:
            os.link(temporary, target)
            created = True
        except FileExistsError:
            pass
        if target.is_symlink() or not target.is_file():
            raise SystemExit("A conflicting content-addressed snapshot exists.")
        if sha256_file(target) != digest:
            if created:
                target.unlink(missing_ok=True)
            raise SystemExit("A conflicting content-addressed snapshot exists.")
    finally:
        temporary.unlink(missing_ok=True)


def snapshot_file(root: Path, source_ref: str, kind: str) -> dict[str, str]:
    if kind not in {"policy", "source_approval"}:
        raise SystemExit("Snapshot kind must be policy or source_approval.")
    root = root.resolve()
    source = resolve_workspace_path(root, source_ref, "snapshot source")
    with authority_lock(root):
        directory = "policy_snapshots" if kind == "policy" else "source_snapshots"
        snapshot_directory = root / AUTHORIZATION_ROOT / directory
        temporary, digest = _stage_snapshot(source, snapshot_directory)
        extension = (
            source.suffix if source.suffix in {".md", ".json", ".txt"} else ".bin"
        )
        target = snapshot_directory / f"{kind}-{digest}{extension}"
        try:
            if kind == "source_approval":
                load_source_approval(temporary)
            _install_snapshot(temporary, target, digest)
            if kind == "source_approval":
                load_source_approval(target)
        finally:
            temporary.unlink(missing_ok=True)
        metadata = {
            "schema_version": 2,
            "artifact_kind": f"{kind}_snapshot",
            "source_ref": _relative(source, root),
            "source_sha256": digest,
            "snapshot_ref": _relative(target, root),
            "snapshot_sha256": digest,
        }
        metadata_path = target.with_suffix(target.suffix + ".json")
        write_immutable_json(metadata_path, metadata, f"{kind} snapshot metadata")
    return {"ref": _relative(target, root), "sha256": digest}


def update_current_policy(
    root: Path,
    binding: dict[str, str],
    *,
    expected_version: int | None,
) -> dict[str, Any]:
    root = root.resolve()
    pointer_path = root / AUTHORIZATION_ROOT / "state" / "current_policy.json"
    with authority_lock(root):
        current = (
            read_object(pointer_path, "current policy pointer")
            if pointer_path.exists()
            else None
        )
        version = int(current.get("version", 0)) if current else 0
        if expected_version is not None and version != expected_version:
            raise SystemExit(
                f"Current policy CAS conflict: expected version {expected_version}, found {version}."
            )
        pointer = {
            "schema_version": 2,
            "artifact_kind": "current_policy_pointer",
            "policy_snapshot": binding,
            "version": version + 1,
        }
        write_json_atomic(pointer_path, pointer)
    return pointer


def verify_binding(root: Path, binding: dict[str, str], label: str) -> Path:
    path = resolve_workspace_path(root, binding.get("ref"), f"{label}.ref")
    if sha256_file(path) != binding.get("sha256"):
        raise SystemExit(f"{label} SHA-256 does not match its immutable artifact.")
    return path


def grant_path(root: Path, grant_id: str) -> Path:
    return root.resolve() / AUTHORIZATION_ROOT / "grants" / f"{grant_id}.json"


def state_path(root: Path, grant_id: str) -> Path:
    return root.resolve() / AUTHORIZATION_ROOT / "state" / "grants" / f"{grant_id}.json"


def load_grant(root: Path, grant_id: str) -> tuple[dict[str, Any], str, dict[str, Any]]:
    artifact = grant_path(root, grant_id)
    projection = state_path(root, grant_id)
    if not artifact.is_file() or not projection.is_file():
        raise SystemExit(f"Authority grant is missing: {grant_id}")
    raw = read_object(artifact, "authority grant")
    grant = validate_grant(raw)
    digest = sha256_file(artifact)
    state = read_object(projection, "authority grant state")
    if state.get("grant_sha256") != digest:
        raise SystemExit(f"Authority grant state digest mismatch: {grant_id}")
    return grant, digest, state


def list_grants(root: Path) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    directory = root.resolve() / AUTHORIZATION_ROOT / "grants"
    if not directory.is_dir():
        return []
    return [load_grant(root, path.stem) for path in sorted(directory.glob("*.json"))]


def _scope_set(items: list[dict[str, Any]]) -> set[str]:
    return {object_sha256(item) for item in items}


def _validate_child(
    parent: dict[str, Any], parent_state: dict[str, Any], child: dict[str, Any]
) -> None:
    if parent_state.get("status") != "active":
        raise SystemExit("Delegation requires an active parent grant.")
    if (
        child["parent_grant_id"] != parent["grant_id"]
        or child["lineage_id"] != parent["lineage_id"]
    ):
        raise SystemExit("Child grant must preserve its parent and lineage identities.")
    if child["issuer_rank"] != parent["holder_rank"]:
        raise SystemExit("Child issuer_rank must equal the parent holder_rank.")
    if rank_value(child["issuer_rank"]) >= rank_value(parent["issuer_rank"]):
        raise SystemExit(
            "Delegation cannot increase or preserve the parent issuer rank."
        )
    if not set(child["capabilities"]).issubset(parent["capabilities"]):
        raise SystemExit("Delegated capabilities must be a subset of the parent grant.")
    if not _scope_set(child["subjects"]).issubset(_scope_set(parent["subjects"])):
        raise SystemExit(
            "Delegated subjects must be an exact subset of the parent grant."
        )
    if not _scope_set(child["operations"]).issubset(_scope_set(parent["operations"])):
        raise SystemExit(
            "Delegated operations must be an exact subset of the parent grant."
        )
    if risk_value(child["risk_ceiling"]) > risk_value(parent["risk_ceiling"]):
        raise SystemExit("Delegation cannot increase the risk ceiling.")
    if not set(child["decision_classes"]).issubset(parent["decision_classes"]):
        raise SystemExit(
            "Delegated decision classes must be a subset of the parent grant."
        )
    if not cardinality_covers(parent["cardinality"], child["cardinality"]):
        raise SystemExit("Delegation cannot broaden the parent cardinality.")
    if parse_time(child["not_before"], "child.not_before") < parse_time(
        parent["not_before"], "parent.not_before"
    ):
        raise SystemExit("Delegation cannot begin before its parent.")
    parent_expiry = parent.get("expires_at")
    child_expiry = child.get("expires_at")
    if parent_expiry and (
        not child_expiry
        or parse_time(child_expiry, "child.expires_at")
        > parse_time(parent_expiry, "parent.expires_at")
    ):
        raise SystemExit("Delegation cannot outlive its parent.")
    parent_budget = parent.get("max_uses")
    child_budget = child.get("max_uses")
    if parent_budget is not None and (
        child_budget is None or child_budget > parent_budget
    ):
        raise SystemExit("Delegation cannot increase the parent use budget.")
    if parent["task_id"] and child["task_id"] != parent["task_id"]:
        raise SystemExit("Delegation cannot change a bounded task scope.")
    if parent["improvement_id"] and (
        child["improvement_id"] != parent["improvement_id"]
    ):
        raise SystemExit("Delegation cannot change a bounded improvement scope.")
    if parent["session_id"] and child["session_id"] != parent["session_id"]:
        raise SystemExit("Delegation cannot escape a bounded session scope.")


def register_grant(
    root: Path, raw: dict[str, Any], *, parent_id: str | None = None
) -> dict[str, Any]:
    root = root.resolve()
    grant = validate_grant(raw)
    if parent_id != grant["parent_grant_id"]:
        raise SystemExit("parent_id must exactly match parent_grant_id.")
    source_path = verify_binding(root, grant["source_approval"], "source_approval")
    verify_binding(root, grant["policy_snapshot"], "policy_snapshot")
    artifact = grant_path(root, grant["grant_id"])
    projection = state_path(root, grant["grant_id"])
    with authority_lock(root):
        recover_projection_intents(root)
        parent: dict[str, Any] | None = None
        if parent_id:
            parent, parent_digest, parent_state = load_grant(root, parent_id)
            _validate_child(parent, parent_state, grant)
            expected_source = {
                "ref": _relative(grant_path(root, parent_id), root),
                "sha256": parent_digest,
            }
            if grant["source_approval"] != expected_source:
                raise SystemExit(
                    "A delegated grant must bind its exact immutable parent grant as source approval."
                )
        else:
            validate_for_grant(root, load_source_approval(source_path), grant)
        digest = write_immutable_json(artifact, grant, "authority grant")
        if projection.exists():
            state = read_object(projection, "authority grant state")
            if state.get("grant_sha256") != digest:
                raise SystemExit(
                    "Existing grant state conflicts with the immutable grant."
                )
        else:
            state = {
                "schema_version": 2,
                "artifact_kind": "authority_grant_state",
                "grant_id": grant["grant_id"],
                "grant_sha256": digest,
                "status": "active",
                "remaining_uses": grant["max_uses"],
                "reserved_uses": 0,
                "consumed_uses": 0,
                "version": 0,
                "last_event_id": None,
            }
            write_json_atomic(projection, state)
    return {"grant": grant, "grant_sha256": digest, "state": state}


def descendant_ids(root: Path, grant_id: str) -> list[str]:
    parent_map = {
        grant["grant_id"]: grant.get("parent_grant_id")
        for grant, _, _ in list_grants(root)
    }
    descendants: list[str] = []
    frontier = [grant_id]
    while frontier:
        parent = frontier.pop(0)
        children = sorted(
            item
            for item, candidate_parent in parent_map.items()
            if candidate_parent == parent
        )
        descendants.extend(children)
        frontier.extend(children)
    return descendants


def transition_grants(
    root: Path,
    grant_id: str,
    status: str,
    *,
    event_id: str,
    expected_version: int,
    source_approval: dict[str, str],
    transitioned_at: str,
) -> dict[str, Any]:
    if status not in {"revoked", "suspended", "expired", "reactivated"}:
        raise SystemExit("Unsupported grant transition.")
    root = root.resolve()
    source_path = verify_binding(root, source_approval, "transition source_approval")
    event_path = root / AUTHORIZATION_ROOT / "events" / f"{event_id}.json"
    with authority_lock(root):
        recover_projection_intents(root)
        grant, _, state = load_grant(root, grant_id)
        validate_for_transition(
            root, load_source_approval(source_path), grant, transitioned_at
        )
        transition_time = parse_time(transitioned_at, "transitioned_at")
        grant_expiry = (
            parse_time(grant["expires_at"], "grant.expires_at")
            if grant["expires_at"]
            else None
        )
        if status == "expired" and (
            grant_expiry is None or grant_expiry > transition_time
        ):
            raise SystemExit("Grant cannot expire before its exact expires_at.")
        if status == "reactivated" and (
            grant_expiry is not None and grant_expiry <= transition_time
        ):
            raise SystemExit("An expired grant cannot be reactivated.")
        if event_path.exists():
            event = validated_settled_intent(root, event_path)
            expected = {
                "root_grant_id": grant_id,
                "transition": status,
                "source_approval": source_approval,
                "transitioned_at": transitioned_at,
            }
            if any(event.get(key) != value for key, value in expected.items()):
                raise SystemExit("Authority transition idempotency conflict.")
            return {
                "event_ref": _relative(event_path, root),
                "event_sha256": sha256_file(event_path),
                "affected_grant_ids": event["affected_grant_ids"],
            }
        if state["version"] != expected_version:
            raise SystemExit(
                f"Grant CAS conflict: expected version {expected_version}, found {state['version']}."
            )
        current_status = state["status"]
        if status == "reactivated" and current_status != "suspended":
            raise SystemExit("Only a suspended grant may be reactivated.")
        if status == "suspended" and current_status != "active":
            raise SystemExit("Only an active grant may be suspended.")
        if status in {"revoked", "expired"} and current_status not in {
            "active",
            "suspended",
        }:
            raise SystemExit("Only an active or suspended grant may become terminal.")
        targets = [grant_id]
        if status in {"revoked", "expired"}:
            targets.extend(descendant_ids(root, grant_id))
        target_status = "active" if status == "reactivated" else status
        before: list[dict[str, Any]] = []
        changes: list[dict[str, Any]] = []
        for target in targets:
            _, _, current = load_grant(root, target)
            before.append(
                {
                    "grant_id": target,
                    "status": current["status"],
                    "version": current["version"],
                }
            )
            updated = {
                **current,
                "status": target_status,
                "version": current["version"] + 1,
                "last_event_id": event_id,
            }
            changes.append(
                projection_change(
                    root,
                    state_path(root, target),
                    current,
                    updated,
                )
            )
        event = {
            "schema_version": 2,
            "artifact_kind": "authority_grant_transition",
            "event_id": event_id,
            "root_grant_id": grant_id,
            "transition": status,
            "source_approval": source_approval,
            "transitioned_at": transitioned_at,
            "affected_before": before,
            "affected_grant_ids": targets,
            "state_changes": changes,
        }
        event_sha = write_immutable_json(
            event_path, event, "authority transition event"
        )
        apply_projection_changes(root, changes)
    return {
        "event_ref": _relative(event_path, root),
        "event_sha256": event_sha,
        "affected_grant_ids": targets,
    }
