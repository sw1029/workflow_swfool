"""Git plumbing for preparing and verifying an embedded closeout anchor."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Iterator

from .git_embedded_settlement import (
    GitEmbeddedSettlementError,
    build_git_embedded_settlement,
    build_payload_projection,
    canonical_file_bytes,
    settlement_anchor_path,
    validate_git_embedded_settlement,
    verify_final_commit,
)
from .authority_provenance import validate_authority_provenance


def _git(
    root: Path,
    *arguments: str,
    environment: dict[str, str] | None = None,
) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        env=environment,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise GitEmbeddedSettlementError(
            f"git {' '.join(arguments)} failed: {detail}"
        )
    return result.stdout


def _environment(index_path: Path) -> dict[str, str]:
    value = os.environ.copy()
    value["GIT_INDEX_FILE"] = str(index_path)
    return value


@contextmanager
def _payload_index(
    root: Path, *, anchor_path: str, treeish: str | None = None
) -> Iterator[dict[str, str]]:
    descriptor, temporary = tempfile.mkstemp(prefix="git-settlement-index-")
    os.close(descriptor)
    index_path = Path(temporary)
    try:
        environment = _environment(index_path)
        if treeish is None:
            raw_index = _git(root, "rev-parse", "--git-path", "index").decode().strip()
            source = Path(raw_index)
            if not source.is_absolute():
                source = root / source
            if not source.is_file():
                raise GitEmbeddedSettlementError("repository index is missing")
            shutil.copyfile(source, index_path)
        else:
            index_path.unlink()
            _git(root, "read-tree", treeish, environment=environment)
        _git(
            root,
            "update-index",
            "--force-remove",
            "--",
            anchor_path,
            environment=environment,
        )
        yield environment
    finally:
        index_path.unlink(missing_ok=True)


def _tree_entries(root: Path, environment: dict[str, str]) -> list[dict[str, str]]:
    output = _git(
        root, "ls-files", "--stage", "-z", environment=environment
    )
    rows: list[dict[str, str]] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        header, separator, path_bytes = raw.partition(b"\t")
        if not separator:
            raise GitEmbeddedSettlementError("git index row is malformed")
        parts = header.decode("ascii").split()
        if len(parts) != 3 or parts[2] != "0":
            raise GitEmbeddedSettlementError(
                "settlement requires an index without conflict stages"
            )
        mode, object_id, _stage = parts
        path = path_bytes.decode("utf-8", errors="strict")
        rows.append(
            {
                "path": path,
                "mode": mode,
                "object_id": object_id,
                "object_type": "commit" if mode == "160000" else "blob",
            }
        )
    return rows


def _nullable_mode(value: str) -> str | None:
    return None if set(value) == {"0"} else value


def _nullable_oid(value: str) -> str | None:
    return None if set(value) == {"0"} else value


def _raw_diff_rows(output: bytes) -> list[dict[str, Any]]:
    tokens = output.split(b"\0")
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(tokens) and tokens[index]:
        header = tokens[index].decode("ascii")
        index += 1
        if index >= len(tokens):
            raise GitEmbeddedSettlementError("raw Git diff lacks a path")
        path = tokens[index].decode("utf-8", errors="strict")
        index += 1
        parts = header.removeprefix(":").split()
        if len(parts) != 5:
            raise GitEmbeddedSettlementError("raw Git diff row is malformed")
        before_mode, after_mode, before_oid, after_oid, status = parts
        status = status[:1]
        rows.append(
            {
                "path": path,
                "status": status,
                "before_mode": _nullable_mode(before_mode),
                "before_object_id": _nullable_oid(before_oid),
                "after_mode": _nullable_mode(after_mode),
                "after_object_id": _nullable_oid(after_oid),
            }
        )
    return rows


def _index_projection(
    root: Path, anchor_path: str
) -> dict[str, Any]:
    with _payload_index(root, anchor_path=anchor_path) as environment:
        tree_oid = _git(root, "write-tree", environment=environment).decode().strip()
        tree = _tree_entries(root, environment)
        diff = _raw_diff_rows(
            _git(
                root,
                "diff",
                "--cached",
                "--raw",
                "--no-renames",
                "--no-abbrev",
                "-z",
                "--",
                environment=environment,
            )
        )
    return build_payload_projection(
        anchor_path=anchor_path,
        payload_tree_oid=tree_oid,
        tree_entries=tree,
        diff_entries=diff,
    )


def _safe_anchor_target(root: Path, anchor_path: str) -> Path:
    relative = PurePosixPath(anchor_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in anchor_path:
        raise GitEmbeddedSettlementError("anchor path must be repository relative")
    target = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise GitEmbeddedSettlementError("anchor path traverses a symlink")
    if target.is_symlink():
        raise GitEmbeddedSettlementError("anchor target must not be a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.resolve().is_relative_to(root) is False:
        raise GitEmbeddedSettlementError("anchor target escapes the repository")
    return target


def _read_anchor_nofollow(target: Path) -> bytes:
    descriptor = os.open(
        target,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise GitEmbeddedSettlementError(
                "existing settlement anchor is not a regular file"
            )
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def _publish_anchor_once(target: Path, payload: bytes) -> bool:
    """Atomically create an anchor, reusing only byte-identical retries."""

    directory = os.open(
        target.parent,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    temporary: str | None = None
    try:
        fcntl.flock(directory, fcntl.LOCK_EX)
        if target.exists() or target.is_symlink():
            if target.is_symlink() or _read_anchor_nofollow(target) != payload:
                raise GitEmbeddedSettlementError(
                    "settlement anchor already exists with different bytes"
                )
            return False
        descriptor, temporary = tempfile.mkstemp(
            prefix=".settlement-", dir=target.parent
        )
        try:
            os.fchmod(descriptor, 0o644)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError:
                if _read_anchor_nofollow(target) != payload:
                    raise GitEmbeddedSettlementError(
                        "settlement anchor raced with different bytes"
                    )
                return False
            os.fsync(directory)
            return True
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
    finally:
        fcntl.flock(directory, fcntl.LOCK_UN)
        os.close(directory)


def message_sha256(message: bytes) -> str:
    normalized = message.rstrip(b"\n") + b"\n"
    return hashlib.sha256(normalized).hexdigest()


def prepare_anchor(
    root: str | Path,
    *,
    anchor_path: str,
    commit_message: bytes,
    intent: dict[str, Any],
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    fields = {
        "commit_role",
        "goal_id",
        "task_id",
        "cycle_id",
        "session_id",
        "authority_request",
        "authority_reservation",
        "precommit_evidence",
    }
    if not isinstance(intent, dict) or set(intent) != fields:
        raise GitEmbeddedSettlementError("settlement intent is not closed")
    expected_anchor = settlement_anchor_path(intent["cycle_id"])
    if anchor_path != expected_anchor:
        raise GitEmbeddedSettlementError(
            "anchor path does not match the reserved cycle settlement path"
        )
    validate_authority_provenance(workspace, intent)
    parent = _git(workspace, "rev-parse", "HEAD").decode().strip()
    projection = _index_projection(workspace, anchor_path)
    settlement = build_git_embedded_settlement(
        anchor_path=anchor_path,
        parent_head=parent,
        commit_message_sha256=message_sha256(commit_message),
        commit_role=intent["commit_role"],
        goal_id=intent["goal_id"],
        task_id=intent["task_id"],
        cycle_id=intent["cycle_id"],
        session_id=intent["session_id"],
        authority_request=intent["authority_request"],
        authority_reservation=intent["authority_reservation"],
        precommit_evidence=intent["precommit_evidence"],
        payload_projection=projection,
    )
    target = _safe_anchor_target(workspace, anchor_path)
    payload = canonical_file_bytes(settlement)
    _publish_anchor_once(target, payload)
    if _git(workspace, "rev-parse", "HEAD").decode().strip() != parent:
        raise GitEmbeddedSettlementError(
            "HEAD changed while preparing the settlement anchor"
        )
    if _index_projection(workspace, anchor_path) != projection:
        raise GitEmbeddedSettlementError(
            "index changed while preparing the settlement anchor"
        )
    _git(workspace, "add", "--", anchor_path)
    if (
        _git(workspace, "rev-parse", "HEAD").decode().strip() != parent
        or _index_projection(workspace, anchor_path) != projection
    ):
        raise GitEmbeddedSettlementError(
            "Git state changed while staging the settlement anchor"
        )
    return settlement


def _commit_observation(
    root: Path, *, commit_oid: str, settlement: dict[str, Any]
) -> dict[str, Any]:
    anchor_path = settlement["anchor_path"]
    lineage = _git(
        root, "rev-list", "--parents", "-n", "1", commit_oid
    ).decode().split()
    parents = lineage[1:]
    if len(parents) != 1:
        raise GitEmbeddedSettlementError("settled commit must have one parent")
    with _payload_index(
        root, anchor_path=anchor_path, treeish=commit_oid
    ) as environment:
        payload_tree_oid = _git(
            root, "write-tree", environment=environment
        ).decode().strip()
        tree_entries = _tree_entries(root, environment)
    diff_entries = _raw_diff_rows(
        _git(
            root,
            "diff-tree",
            "--raw",
            "--no-renames",
            "--no-abbrev",
            "-r",
            "-z",
            parents[0],
            payload_tree_oid,
            "--",
        )
    )
    message = _git(root, "show", "-s", "--format=%B", commit_oid)
    anchor_blob = _git(root, "show", f"{commit_oid}:{anchor_path}")
    return {
        "commit_oid": commit_oid,
        "parent_heads": parents,
        "commit_message_sha256": message_sha256(message),
        "anchor_path": anchor_path,
        "anchor_blob_sha256": hashlib.sha256(anchor_blob).hexdigest(),
        "payload_tree_oid": payload_tree_oid,
        "tree_entries": tree_entries,
        "diff_entries": diff_entries,
    }


def verify_head(
    root: str | Path,
    *,
    anchor_path: str,
    expected: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    workspace = Path(root).resolve(strict=True)
    commit_oid = _git(workspace, "rev-parse", "HEAD").decode().strip()
    payload = _git(workspace, "show", f"{commit_oid}:{anchor_path}")
    try:
        raw = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitEmbeddedSettlementError(
            "committed settlement anchor is not JSON"
        ) from exc
    settlement = validate_git_embedded_settlement(raw)
    if payload != canonical_file_bytes(settlement):
        raise GitEmbeddedSettlementError(
            "committed settlement anchor is not canonical"
        )
    if expected is not None:
        allowed = {
            "commit_role",
            "goal_id",
            "task_id",
            "cycle_id",
            "session_id",
        }
        if set(expected) != allowed:
            raise GitEmbeddedSettlementError(
                "expected settlement identity is not closed"
            )
        for field in sorted(allowed):
            if settlement[field] != expected[field]:
                raise GitEmbeddedSettlementError(
                    f"committed settlement binds another {field}"
                )
    validate_authority_provenance(
        workspace,
        {
            key: settlement[key]
            for key in (
                "commit_role",
                "goal_id",
                "task_id",
                "cycle_id",
                "session_id",
                "authority_request",
                "authority_reservation",
                "precommit_evidence",
            )
        },
        require_current_state=False,
    )
    observation = _commit_observation(
        workspace, commit_oid=commit_oid, settlement=settlement
    )
    return verify_final_commit(settlement, observation)


def recover_verified_closeout(
    root: str | Path,
    *,
    anchor_path: str,
    expected: dict[str, str | None],
) -> dict[str, Any]:
    """Derive an owner result from an already committed verified anchor."""

    workspace = Path(root).resolve(strict=True)
    verification = verify_head(
        workspace,
        anchor_path=anchor_path,
        expected=expected,
    )
    subject = _git(
        workspace, "show", "-s", "--format=%s", verification["commit_oid"]
    ).decode("utf-8", errors="strict").strip()
    paths = [
        item.decode("utf-8", errors="strict")
        for item in _git(
            workspace,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "-z",
            verification["commit_oid"],
        ).split(b"\0")
        if item
    ]
    return {
        "commit_role": "closeout",
        "commit_status": "committed",
        "tracked_artifacts": sorted(paths),
        "evidence_paths": [anchor_path],
        "commit_hash": verification["commit_oid"],
        "commit_subject": subject,
        "settlement_anchor_path": anchor_path,
        "settlement_verification": verification,
    }


__all__ = (
    "message_sha256",
    "prepare_anchor",
    "recover_verified_closeout",
    "verify_head",
)
