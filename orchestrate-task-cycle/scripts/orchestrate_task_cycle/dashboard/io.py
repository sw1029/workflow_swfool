from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import DashboardDataError


def _load_raw_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DashboardDataError(
                        f"malformed ledger JSON on line {line_number}: {exc}"
                    ) from exc
                if not isinstance(value, dict):
                    raise DashboardDataError(
                        f"ledger line {line_number} must contain a JSON object"
                    )
                value = dict(value)
                value.setdefault("_ledger_line", line_number)
                events.append(value)
    except (OSError, UnicodeError) as exc:
        raise DashboardDataError(f"cannot read cycle ledger: {exc}") from exc
    return events


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DashboardDataError(f"cycle ledger does not exist: {path}")
    if path.name == "stage.jsonl" and path.parent.parent.name == "cycle":
        try:
            from ..cycle_ledger import read_events

            return read_events(path.parents[3], path.parent.name)
        except ValueError as exc:
            if "changed during read-only snapshot" in str(exc):
                raise DashboardDataError(str(exc)) from exc
            from ..ledger.repository import read_cycle_files_stable

            try:
                legacy = read_cycle_files_stable(
                    path.parents[3],
                    path.parent.name,
                    lambda: _load_raw_events(path),
                    [path],
                )
            except (OSError, UnicodeError, ValueError) as stable_exc:
                raise DashboardDataError(str(stable_exc)) from stable_exc
            if not legacy or any("format_version" in event for event in legacy):
                raise DashboardDataError(str(exc)) from exc
            # Versionless format-v0 rows stay opaque and read-only. They are
            # never upgraded to compact result envelopes by the dashboard.
            return legacy
    return _load_raw_events(path)


def _load_current_unlocked(path: Path) -> tuple[dict[str, Any], str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}, "malformed"
    if not isinstance(value, dict):
        return {"error": "current_stage.json must contain an object"}, "malformed"
    return value, "loaded"


def load_current(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    if path.name == "current_stage.json" and path.parent.parent.name == "cycle":
        from ..ledger.repository import read_cycle_files_stable

        try:
            value, status = read_cycle_files_stable(
                path.parents[3],
                path.parent.name,
                lambda: _load_current_unlocked(path),
                [path],
            )
        except (OSError, UnicodeError, ValueError) as exc:
            return {"error": str(exc)}, "malformed"
    else:
        value, status = _load_current_unlocked(path)
    if status != "loaded":
        return value, status
    if (
        value.get("projection_version") == 2
        and path.name == "current_stage.json"
        and path.parent.parent.name == "cycle"
    ):
        try:
            from ..cycle_ledger import read_current_expanded

            return read_current_expanded(path.parents[3], path.parent.name), "loaded"
        except (OSError, UnicodeError, ValueError) as exc:
            return {"error": str(exc)}, "malformed"
    version = value.get("format_version", 0)
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version not in {0, 1}
    ):
        return {
            "error": f"unsupported current_stage format_version: {version!r}"
        }, "malformed"
    return value, status


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_value = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_value)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = None
        if directory_descriptor is not None:
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()
