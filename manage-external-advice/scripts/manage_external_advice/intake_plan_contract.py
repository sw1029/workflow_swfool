"""Integrity and immutable-file contract for external-advice intake plans."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath
import stat
from typing import Any

from .storage import publish_immutable
from .stable_store import ensure_parent as stable_ensure_parent
from .stable_store import read_regular


PLAN_SCHEMA_VERSION = 1
PLAN_KIND = "external_advice_intake_plan"
RESULT_SCHEMA_VERSION = 1
_DESTINATION_DIRS = {"raw": "raw", "normalized": "active"}


def opaque_source_snapshot_ref(raw_sha256: str) -> str:
    if not _is_sha256(raw_sha256):
        raise SystemExit("Advice intake source snapshot needs a lowercase SHA-256")
    return (
        ".agent_advice/journal/intake/source_snapshots/"
        f"src-sha256-{raw_sha256}.md"
    )


def source_snapshot_path(
    root: Path, raw_sha256: str, *, ensure_parent: bool = False
) -> Path:
    """Resolve the digest-derived source snapshot without caller locator metadata."""

    relative = PurePosixPath(opaque_source_snapshot_ref(raw_sha256))
    root = root.resolve()
    leaf = root / relative
    if ensure_parent:
        stable_ensure_parent(root, leaf)
    current = root
    for part in relative.parts[:-1]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise SystemExit(
                "External-advice source snapshot ancestor must be a regular directory"
            )
    leaf = current / relative.name
    try:
        mode = leaf.lstat().st_mode
    except FileNotFoundError:
        return leaf
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise SystemExit("External-advice source snapshot must be a regular file")
    return leaf


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_source_ref(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise SystemExit("External-advice source_ref must be a path string")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or candidate.as_posix() != value
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise SystemExit(
            "External-advice source_ref must be an exact canonical workspace-relative path"
        )
    return value


def workspace_path(root: Path, value: str | Path) -> Path:
    root = root.resolve()
    raw_value = Path(value).as_posix()
    lexical = PurePosixPath(raw_value)
    if lexical.is_absolute():
        candidate = Path(raw_value)
        try:
            relative = candidate.relative_to(root)
        except ValueError as exc:
            raise SystemExit(
                f"Advice intake plan path escapes workspace: {value}"
            ) from exc
        relative_value = relative.as_posix()
    else:
        relative = Path(raw_value)
        relative_value = raw_value
    canonical = PurePosixPath(relative_value)
    if (
        not relative_value
        or canonical.is_absolute()
        or canonical.as_posix() != relative_value
        or any(part in {"", ".", ".."} for part in canonical.parts)
    ):
        raise SystemExit(f"Advice intake plan path must be canonical: {value}")
    current = root
    for index, part in enumerate(canonical.parts):
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise SystemExit(
                f"Advice intake plan path must not traverse symlinks: {value}"
            )
        if index < len(canonical.parts) - 1 and not stat.S_ISDIR(mode):
            raise SystemExit(
                f"Advice intake plan path ancestor must be a directory: {value}"
            )
    resolved = current
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"Advice intake plan path escapes workspace: {value}") from exc
    return resolved


def _canonical_destination_parts(value: Any, *, kind: str) -> tuple[str, str, str]:
    directory = _DESTINATION_DIRS.get(kind)
    if directory is None:
        raise SystemExit(f"Unsupported external-advice destination kind: {kind}")
    if not isinstance(value, str) or not value:
        raise SystemExit(f"External-advice {kind} destination must be a path string")
    candidate = PurePosixPath(value)
    parts = candidate.parts
    if (
        candidate.is_absolute()
        or len(parts) != 3
        or parts[:2] != (".agent_advice", directory)
        or candidate.as_posix() != value
    ):
        raise SystemExit(
            f"External-advice {kind} destination must be an exact canonical "
            f".agent_advice/{directory}/<file>.md path"
        )
    filename = parts[2]
    if filename in {".", ".."} or not filename.endswith(".md"):
        raise SystemExit(
            f"External-advice {kind} destination must name one Markdown file"
        )
    return parts[0], parts[1], filename


def canonical_destination_path(
    root: Path,
    value: Any,
    *,
    kind: str,
    ensure_parent: bool = False,
) -> Path:
    """Resolve only a canonical raw/active leaf without following ancestors.

    Intake plans are caller-supplied integrity documents, so a valid self-hash is
    not authority to redirect raw or normalized publication elsewhere.  Inspect
    every owned ancestor with ``lstat`` and create missing owned directories one
    level at a time only when publication is imminent.
    """

    parts = _canonical_destination_parts(value, kind=kind)
    root = root.resolve()
    ancestors = (root / parts[0], root / parts[0] / parts[1])
    leaf = ancestors[-1] / parts[2]
    if ensure_parent:
        stable_ensure_parent(root, leaf)
    for ancestor in ancestors:
        try:
            mode = ancestor.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise SystemExit(
                f"External-advice {kind} destination ancestor must be a regular "
                f"directory: {ancestor}"
            )
    try:
        mode = leaf.lstat().st_mode
    except FileNotFoundError:
        return leaf
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise SystemExit(
            f"External-advice {kind} destination must be a regular file: {leaf}"
        )
    return leaf


def canonical_plan_output_path(root: Path, value: str | Path) -> Path:
    raw_value = Path(value).as_posix()
    candidate = PurePosixPath(raw_value)
    parts = candidate.parts
    if (
        candidate.is_absolute()
        or len(parts) != 4
        or parts[:3] != (".agent_advice", "journal", "intake")
        or candidate.as_posix() != raw_value
        or not parts[3].endswith(".plan.json")
    ):
        raise SystemExit(
            "Advice intake plan output must be an exact canonical "
            ".agent_advice/journal/intake/<file>.plan.json path"
        )
    root = root.resolve()
    leaf = root / candidate
    stable_ensure_parent(root, leaf)
    current = root
    for part in parts[:-1]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise SystemExit("Advice intake plan ancestor must be a regular directory")
    leaf = current / parts[-1]
    if leaf.exists() or leaf.is_symlink():
        mode = leaf.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise SystemExit("Advice intake plan output must be a regular file")
    return leaf


def canonical_intake_artifact_path(
    root: Path,
    plan_id: str,
    artifact: str,
    *,
    ensure_parent: bool = False,
) -> Path:
    """Resolve one plan-owned journal artifact without following symlinks."""

    if (
        not isinstance(plan_id, str)
        or not plan_id.startswith("intake-")
        or len(plan_id) != 39
        or any(character not in "0123456789abcdef" for character in plan_id[7:])
        or artifact not in {"intent", "receipt"}
    ):
        raise SystemExit("Invalid external-advice intake journal identity")
    root = root.resolve()
    leaf = root / ".agent_advice" / "journal" / "intake" / (
        f"{plan_id}.{artifact}.json"
    )
    if ensure_parent:
        stable_ensure_parent(root, leaf)
    current = root
    for part in (".agent_advice", "journal", "intake"):
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise SystemExit(
                "External-advice intake journal ancestor must be a regular directory"
            )
    leaf = current / f"{plan_id}.{artifact}.json"
    try:
        mode = leaf.lstat().st_mode
    except FileNotFoundError:
        return leaf
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise SystemExit(
            "External-advice intake journal artifact must be a regular file"
        )
    return leaf


def regular_payload(
    root: Path, path: Path, *, missing: bytes | None = None
) -> bytes:
    sentinel = object()
    observed = read_regular(
        root,
        path,
        missing=sentinel if missing is None else missing,
        label="Advice intake plan path",
    )
    if observed is sentinel:
        raise SystemExit(f"Required advice intake plan file is missing: {path}")
    assert isinstance(observed, bytes)
    return observed


def validate_intake_plan(plan: dict[str, Any]) -> None:
    if (
        plan.get("schema_version") != PLAN_SCHEMA_VERSION
        or plan.get("plan_kind") != PLAN_KIND
    ):
        raise SystemExit("Unsupported external-advice intake plan")
    supplied = plan.get("plan_sha256")
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    if not _is_sha256(supplied) or supplied != sha256_bytes(canonical_bytes(body)):
        raise SystemExit("External-advice intake plan digest mismatch")
    raw = plan.get("raw") if isinstance(plan.get("raw"), dict) else {}
    normalized = plan.get("normalized") if isinstance(plan.get("normalized"), dict) else {}
    if not all(isinstance(raw.get(field), str) and raw.get(field) for field in ("source_ref", "path", "sha256")):
        raise SystemExit("External-advice intake plan lacks a bounded raw source binding")
    _canonical_source_ref(raw["source_ref"])
    if not all(isinstance(normalized.get(field), str) and normalized.get(field) for field in ("path", "sha256")):
        raise SystemExit("External-advice intake plan lacks a normalized digest binding")
    if "content" in raw or "content" in normalized:
        raise SystemExit("External-advice intake plan must not embed advice bodies")
    raw_parts = _canonical_destination_parts(raw.get("path"), kind="raw")
    normalized_parts = _canonical_destination_parts(
        normalized.get("path"), kind="normalized"
    )
    if raw_parts[2] != normalized_parts[2]:
        raise SystemExit(
            "External-advice intake raw and normalized destinations must share one filename"
        )
    advice_id = plan.get("advice_id")
    if advice_id != f"adv-{PurePosixPath(raw_parts[2]).stem}":
        raise SystemExit(
            "External-advice intake advice_id must bind the canonical destination filename"
        )
    if not _is_sha256(raw.get("sha256")) or not _is_sha256(normalized.get("sha256")):
        raise SystemExit("External-advice intake content digests must be lowercase SHA-256")
    metadata = plan.get("metadata") if isinstance(plan.get("metadata"), dict) else {}
    if not all(
        isinstance(metadata.get(field), str) and metadata.get(field)
        for field in ("title", "title_policy", "priority", "source_id")
    ):
        raise SystemExit("External-advice intake plan lacks fixed event metadata")
    if metadata["source_id"] != f"src-sha256-{raw['sha256']}":
        raise SystemExit("External-advice intake source identity does not bind the raw digest")
    if raw["source_ref"] != opaque_source_snapshot_ref(raw["sha256"]):
        raise SystemExit(
            "External-advice intake source_ref must use its opaque digest snapshot"
        )
    event_digest = plan.get("event_sha256")
    if not _is_sha256(event_digest):
        raise SystemExit("External-advice intake plan lacks an event digest")
    if "event" in plan:
        raise SystemExit("External-advice intake plan must not embed the registry event")
    registry = plan.get("registry") if isinstance(plan.get("registry"), dict) else {}
    markdown = plan.get("markdown") if isinstance(plan.get("markdown"), dict) else {}
    if (
        registry.get("path") != ".agent_advice/index.jsonl"
        or not all(
            _is_sha256(registry.get(field))
            for field in ("before_sha256", "after_sha256")
        )
        or not isinstance(registry.get("before_size"), int)
        or isinstance(registry.get("before_size"), bool)
        or registry.get("before_size") < 0
    ):
        raise SystemExit("External-advice intake registry binding is not canonical")
    if (
        markdown.get("path") != ".agent_advice/index.md"
        or (
            markdown.get("before_sha256") is not None
            and not _is_sha256(markdown.get("before_sha256"))
        )
        or not _is_sha256(markdown.get("after_sha256"))
    ):
        raise SystemExit("External-advice intake Markdown binding is not canonical")
    identity = {
        "advice_id": advice_id,
        "created_at": plan.get("created_at"),
        "raw_sha256": raw["sha256"],
        "registry_before_sha256": registry["before_sha256"],
    }
    expected_plan_id = f"intake-{sha256_bytes(canonical_bytes(identity))[:32]}"
    if plan.get("plan_id") != expected_plan_id:
        raise SystemExit("External-advice intake plan_id identity binding mismatch")


def publish_plan_file(
    root: Path, path: Path, plan: dict[str, Any]
) -> tuple[bool, str]:
    validate_intake_plan(plan)
    payload = canonical_bytes(plan) + b"\n"
    created = publish_immutable(root, path, payload)
    return created, sha256_bytes(payload)


def load_intake_plan(
    root: Path, path_value: str | Path
) -> tuple[Path, dict[str, Any], str]:
    path = workspace_path(root.resolve(), path_value)
    payload = regular_payload(root, path)
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Invalid external-advice intake plan: {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit("External-advice intake plan must be a JSON object")
    validate_intake_plan(value)
    if payload != canonical_bytes(value) + b"\n":
        raise SystemExit("External-advice intake plan file bytes are not canonical")
    return path, value, sha256_bytes(payload)


def receipt_for_plan(
    plan: dict[str, Any], plan_ref: str, plan_file_sha256: str
) -> dict[str, Any]:
    body = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "receipt_kind": "external_advice_intake_apply_receipt",
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "advice_id": plan["advice_id"],
        "applied_at": plan["created_at"],
        "registry_after_sha256": plan["registry"]["after_sha256"],
        "raw_sha256": plan["raw"]["sha256"],
        "normalized_sha256": plan["normalized"]["sha256"],
        "markdown_after_sha256": plan["markdown"]["after_sha256"],
    }
    return {**body, "receipt_content_sha256": sha256_bytes(canonical_bytes(body))}


def receipt_status(
    root: Path, path: Path, expected: dict[str, Any]
) -> tuple[str, str | None]:
    payload = read_regular(
        root, path, missing=None, label="External-advice intake receipt"
    )
    if payload is None:
        return "missing", None
    if payload != canonical_bytes(expected) + b"\n":
        return "conflict", sha256_bytes(payload)
    return "current", sha256_bytes(payload)
