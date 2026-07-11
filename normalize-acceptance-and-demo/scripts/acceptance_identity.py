#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ACCEPTANCE_STATUSES = {"normalized", "partial", "blocked", "needs_review"}


class AcceptanceIdentityError(ValueError):
    pass


def criterion_is_semantically_non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if not isinstance(value, dict) or not value:
        return False

    def has_content(item: Any) -> bool:
        if isinstance(item, str):
            return bool(item.strip())
        if isinstance(item, dict):
            return bool(item) and any(has_content(nested) for nested in item.values())
        if isinstance(item, (list, tuple)):
            return any(has_content(nested) for nested in item)
        return item is not None

    return any(has_content(item) for item in value.values())


def bounded_file(root: Path, value: str) -> Path:
    raw = Path(value)
    path = (raw if raw.is_absolute() else root / raw).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise AcceptanceIdentityError(f"task path escapes the workspace root, including through a symlink: {value}") from exc
    if not path.is_file():
        raise AcceptanceIdentityError(f"task path does not identify a file: {value}")
    return path


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def load_packet(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value == "-":
        raw = sys.stdin.read()
    else:
        stripped = value.strip()
        if stripped.startswith("{"):
            raw = stripped
        else:
            path = Path(value)
            try:
                raw = path.read_text(encoding="utf-8") if path.is_file() else value
            except OSError as exc:
                raise AcceptanceIdentityError(f"cannot read packet JSON: {exc}") from exc
    try:
        packet = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AcceptanceIdentityError(f"packet is not valid JSON: {exc}") from exc
    if not isinstance(packet, dict):
        raise AcceptanceIdentityError("packet JSON must contain an object")
    return packet


def validate_final_packet(packet: dict[str, Any]) -> None:
    status = packet.get("acceptance_status")
    if status not in ACCEPTANCE_STATUSES:
        raise AcceptanceIdentityError(
            "final acceptance packet requires acceptance_status: normalized|partial|blocked|needs_review"
        )
    criteria = packet.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        raise AcceptanceIdentityError("final acceptance packet requires non-empty acceptance_criteria")
    invalid_criteria = [index for index, criterion in enumerate(criteria) if not criterion_is_semantically_non_empty(criterion)]
    if invalid_criteria:
        raise AcceptanceIdentityError(
            f"final acceptance packet contains semantically empty acceptance_criteria at indexes: {invalid_criteria}"
        )
    blockers = packet.get("blockers")
    if not isinstance(blockers, list):
        raise AcceptanceIdentityError("final acceptance packet requires explicit blockers list")
    if any(not criterion_is_semantically_non_empty(blocker) for blocker in blockers):
        raise AcceptanceIdentityError("final acceptance packet contains a semantically empty blocker")
    if status == "normalized" and blockers:
        raise AcceptanceIdentityError("normalized acceptance cannot retain blockers")
    if status in {"blocked", "needs_review"} and not blockers:
        raise AcceptanceIdentityError("blocked/needs_review acceptance requires a concrete blocker")
    if not isinstance(packet.get("evidence_paths"), list):
        raise AcceptanceIdentityError("final acceptance packet requires explicit evidence_paths list")


def bind(root: Path, task_id: str, task_path_value: str, packet: dict[str, Any], final: bool) -> dict[str, Any]:
    if not TASK_ID_PATTERN.fullmatch(task_id):
        raise AcceptanceIdentityError("task_id must be a non-empty path-safe token of at most 128 characters")
    task_path = bounded_file(root, task_path_value)
    task_body = task_path.read_bytes()
    if not task_body.strip():
        raise AcceptanceIdentityError("cannot normalize acceptance from an empty task file")
    supplied_task_id = packet.get("task_id")
    if supplied_task_id is not None and str(supplied_task_id) != task_id:
        raise AcceptanceIdentityError("packet task_id does not match the active task_id")

    fingerprint = hashlib.sha256(task_body).hexdigest()
    result = copy.deepcopy(packet)
    result.update(
        {
            "format_version": 1,
            "step": "acceptance",
            "acceptance_id": f"acceptance-{task_id}-{fingerprint[:16]}",
            "task_id": task_id,
            "acceptance_provenance": {
                "source_task_id": task_id,
                "source_task_path": relative_path(root, task_path),
                "source_task_fingerprint": fingerprint,
            },
        }
    )
    if final:
        validate_final_packet(result)
        task_evidence = relative_path(root, task_path)
        if task_evidence not in result["evidence_paths"]:
            result["evidence_paths"].append(task_evidence)
    else:
        result.setdefault("acceptance_status", "needs_review")
        result.setdefault("blockers", ["acceptance_packet_not_finalized"])
        result.setdefault("evidence_paths", [relative_path(root, task_path)])
    return result


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bind a normalized acceptance packet to one exact task revision.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-path", default="task.md")
    parser.add_argument("--packet-json")
    parser.add_argument("--final", action="store_true", help="Require the complete acceptance result contract.")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    try:
        result = bind(root, args.task_id, args.task_path, load_packet(args.packet_json), args.final)
        if args.output:
            output = Path(args.output)
            output = (output if output.is_absolute() else root / output).resolve(strict=False)
            try:
                output.relative_to(root)
            except ValueError as exc:
                raise AcceptanceIdentityError("output path must stay inside the workspace root") from exc
            atomic_write(output, result)
    except (AcceptanceIdentityError, OSError, UnicodeError) as exc:
        json.dump({"format_version": 1, "status": "block", "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
