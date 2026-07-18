"""Capture and compare repository-local retained-change baselines.

The baseline records only safe relative paths, existence, and full content
digests.  It deliberately stores no source body and makes no semantic-progress
claim.  Git is an inventory aid, not the source of truth for file bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


CONTRACT_VERSION = 1
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_INVENTORY_FILES = 100_000
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_git(root: Path, arguments: list[str]) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("git inventory is unavailable") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git inventory failed: {detail or arguments[0]}")
    return completed.stdout


def _safe_relative_path(root: Path, raw: str) -> tuple[Path, str]:
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"retained-change path is unsafe: {raw}")
    lexical = root.joinpath(candidate)
    current = root
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"retained-change path traverses a symlink: {raw}")
    normalized = candidate.as_posix()
    return lexical, normalized


def _entry(root: Path, raw: str) -> dict[str, Any]:
    path, normalized = _safe_relative_path(root, raw)
    exists = path.exists()
    if exists:
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise ValueError(f"retained-change path is not a regular file: {raw}")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(
                f"retained-change path exceeds {MAX_FILE_BYTES} bytes: {raw}"
            )
    return {
        "path": normalized,
        "subject_id": "file-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "exists": exists,
        "content_sha256": _sha256_file(path) if exists else None,
    }


def _git_changed_paths(root: Path, baseline_revision: str) -> list[str]:
    output = _run_git(
        root,
        ["diff", "--name-status", "-z", "--find-renames", baseline_revision, "--"],
    )
    fields = output.decode("utf-8", errors="surrogateescape").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index]
        index += 1
        width = 2 if status.startswith(("R", "C")) else 1
        if index + width > len(fields):
            raise ValueError("git changed-path inventory is malformed")
        paths.extend(fields[index : index + width])
        index += width
    untracked = (
        _run_git(
            root,
            ["ls-files", "-z", "--others", "--exclude-standard"],
        )
        .decode("utf-8", errors="surrogateescape")
        .split("\0")
    )
    paths.extend(path for path in untracked if path)
    result = sorted(set(paths))
    if len(result) > MAX_INVENTORY_FILES:
        raise ValueError("retained-change inventory exceeds its bounded file count")
    return result


def _git_revision(root: Path) -> str:
    revision = _run_git(root, ["rev-parse", "HEAD"]).decode("ascii").strip()
    if not GIT_OID_RE.fullmatch(revision):
        raise ValueError("git baseline revision is not a full object ID")
    return revision


def _git_blob_entry(root: Path, revision: str, raw: str) -> dict[str, Any]:
    _path, normalized = _safe_relative_path(root, raw)
    try:
        size_probe = subprocess.run(
            ["git", "cat-file", "-s", f"{revision}:{normalized}"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
        if size_probe.returncode == 0:
            size = int(size_probe.stdout.decode("ascii").strip())
            if size > MAX_FILE_BYTES:
                raise ValueError(
                    f"retained-change baseline blob exceeds {MAX_FILE_BYTES} bytes"
                )
        completed = subprocess.run(
            ["git", "cat-file", "blob", f"{revision}:{normalized}"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError) as exc:
        raise ValueError("git baseline blob lookup is unavailable") from exc
    exists = completed.returncode == 0
    return {
        "path": normalized,
        "subject_id": "file-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "exists": exists,
        "content_sha256": hashlib.sha256(completed.stdout).hexdigest()
        if exists
        else None,
    }


def _inventory_entries(root: Path, paths: Iterable[str]) -> list[dict[str, Any]]:
    normalized = sorted(set(str(path).strip() for path in paths if str(path).strip()))
    if not normalized or len(normalized) > MAX_INVENTORY_FILES:
        raise ValueError("retained-change inventory must be non-empty and bounded")
    return [_entry(root, path) for path in normalized]


def capture_baseline(root: Path, explicit_paths: Iterable[str] = ()) -> dict[str, Any]:
    """Capture current bytes for dirty Git paths or an explicit non-Git scope."""

    root = root.resolve()
    supplied = [str(path) for path in explicit_paths]
    if supplied:
        inventory_kind = "explicit_path_scope"
        revision = None
        entries = _inventory_entries(root, supplied)
    else:
        inventory_kind = "git_dirty_scope"
        revision = _git_revision(root)
        dirty_paths = _git_changed_paths(root, revision)
        # A clean baseline is valid.  The after comparison discovers newly dirty
        # tracked/untracked paths relative to the bound revision.
        entries = [_entry(root, path) for path in dirty_paths]
    body: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "retained_change_baseline",
        "inventory_kind": inventory_kind,
        "baseline_revision": revision,
        "entries": entries,
    }
    body["baseline_sha256"] = _canonical_sha256(body)
    return body


def validate_baseline(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("retained-change baseline must be an object")
    expected = {
        "contract_version",
        "artifact_kind",
        "inventory_kind",
        "baseline_revision",
        "entries",
        "baseline_sha256",
    }
    if set(value) != expected or value.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("retained-change baseline schema is invalid")
    if value.get("artifact_kind") != "retained_change_baseline":
        raise ValueError("retained-change baseline kind is invalid")
    kind = value.get("inventory_kind")
    revision = value.get("baseline_revision")
    if kind == "git_dirty_scope":
        if not isinstance(revision, str) or not GIT_OID_RE.fullmatch(revision):
            raise ValueError("retained-change Git revision is invalid")
    elif kind == "explicit_path_scope":
        if revision is not None:
            raise ValueError(
                "explicit retained-change baseline cannot carry a Git revision"
            )
    else:
        raise ValueError("retained-change inventory kind is invalid")
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_INVENTORY_FILES:
        raise ValueError("retained-change baseline entries are invalid")
    seen: set[str] = set()
    for row in entries:
        if not isinstance(row, dict) or set(row) != {
            "path",
            "subject_id",
            "exists",
            "content_sha256",
        }:
            raise ValueError("retained-change baseline entry schema is invalid")
        path = row.get("path")
        if not isinstance(path, str) or path in seen:
            raise ValueError("retained-change baseline paths are invalid")
        seen.add(path)
        expected_subject = "file-" + hashlib.sha256(path.encode("utf-8")).hexdigest()
        digest = row.get("content_sha256")
        if row.get("subject_id") != expected_subject or not isinstance(
            row.get("exists"), bool
        ):
            raise ValueError("retained-change baseline entry identity is invalid")
        if row["exists"] != bool(
            isinstance(digest, str) and SHA256_RE.fullmatch(digest)
        ):
            raise ValueError("retained-change baseline entry digest is invalid")
    expected_digest = _canonical_sha256(
        {key: child for key, child in value.items() if key != "baseline_sha256"}
    )
    if value.get("baseline_sha256") != expected_digest:
        raise ValueError("retained-change baseline digest is invalid")
    return value


def _change_receipt(row: dict[str, Any]) -> str:
    return _canonical_sha256(
        {
            "path": row.get("path"),
            "change_kind": row.get("change_kind"),
            "subject_id": row.get("subject_id"),
            "before_sha256": row.get("before_sha256"),
            "after_sha256": row.get("after_sha256"),
        }
    )


def compare_baseline(root: Path, baseline: object) -> dict[str, Any]:
    """Return file-change rows derived from current bytes versus the baseline."""

    bound = validate_baseline(baseline)
    root = root.resolve()
    before = {str(row["path"]): row for row in bound["entries"]}
    if bound["inventory_kind"] == "git_dirty_scope":
        revision = str(bound["baseline_revision"])
        current_paths = sorted(set(_git_changed_paths(root, revision)) | set(before))
        for path in current_paths:
            if path not in before:
                before[path] = _git_blob_entry(root, revision, path)
    else:
        current_paths = sorted(before)
    after = {path: _entry(root, path) for path in current_paths}
    changes: list[dict[str, Any]] = []
    for path in sorted(set(before) | set(after)):
        old = before.get(path)
        new = after.get(path)
        old_exists = bool(old and old.get("exists"))
        new_exists = bool(new and new.get("exists"))
        old_digest = old.get("content_sha256") if old_exists and old else None
        new_digest = new.get("content_sha256") if new_exists and new else None
        if old_exists == new_exists and old_digest == new_digest:
            continue
        row = {
            "path": path,
            "change_kind": "added"
            if not old_exists
            else "deleted"
            if not new_exists
            else "modified",
            "subject_id": (new or old or {})["subject_id"],
            "before_sha256": old_digest,
            "after_sha256": new_digest,
        }
        row["receipt_sha256"] = _change_receipt(row)
        changes.append(row)
    evidence = {
        "actual_changed_files": [row["path"] for row in changes],
        "file_changes": changes,
    }
    comparison_basis = {
        "baseline_sha256": bound["baseline_sha256"],
        "retained_change_evidence": evidence,
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "artifact_kind": "retained_change_comparison",
        "baseline_sha256": bound["baseline_sha256"],
        "retained_change_evidence": evidence,
        "comparison_sha256": _canonical_sha256(comparison_basis),
    }


def _read_json(path: str) -> object:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture or compare body-free retained-change evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--root", default=".")
    capture.add_argument("--path", action="append", default=[])
    compare = subparsers.add_parser("compare")
    compare.add_argument("--root", default=".")
    compare.add_argument("--baseline-json", required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "capture":
            result = capture_baseline(Path(arguments.root), arguments.path)
        else:
            result = compare_baseline(
                Path(arguments.root), _read_json(arguments.baseline_json)
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
