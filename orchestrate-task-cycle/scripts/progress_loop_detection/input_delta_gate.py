from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import *
from .values import *
from .io_utils import *
from .provider import *

def existing_artifact_paths(root: Path, paths: list[str]) -> list[str]:
    existing: list[str] = []
    for item in paths:
        if not item or "://" in item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = root / path
        try:
            if path.is_file() and path.stat().st_size > 0:
                existing.append(rel_path(root, path))
        except OSError:
            continue
    return sorted(set(existing))


def artifact_role_paths(value: Any, roles: set[str]) -> list[str]:
    if not roles:
        return []
    paths: list[str] = []
    normalized_roles = {role.strip().lower() for role in roles if role and role.strip()}

    def collect_role_paths(item: Any) -> None:
        if isinstance(item, dict):
            role = str(item.get("role") or item.get("artifact_role") or "").strip().lower()
            artifact_path = item.get("artifact_path") or item.get("path")
            exists = item.get("exists")
            if role in normalized_roles and artifact_path and exists is not False:
                paths.extend(list_field(artifact_path))
            for child in item.values():
                collect_role_paths(child)
        elif isinstance(item, list):
            for child in item:
                collect_role_paths(child)

    collect_role_paths(value)
    return sorted(set(paths))


def artifact_summary_role_paths(root: Path, paths: list[str], roles: set[str]) -> list[str]:
    if not roles:
        return []
    collected: list[str] = []
    for item in paths:
        if not item or "://" in item:
            continue
        path = Path(item)
        if not path.is_absolute():
            path = root / path
        if not path.is_file() or path.suffix.lower() not in {".json", ".jsonl"}:
            continue
        if path.suffix.lower() == ".jsonl":
            for record in read_jsonl(path):
                collected.extend(artifact_role_paths(record, roles))
        else:
            summary = read_json(path)
            if summary is not None:
                collected.extend(artifact_role_paths(summary, roles))
    return sorted(set(collected))


def supplied_input_delta_gate(root: Path, value: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    raw_paths = list_field_paths(
        value,
        (
            "supplied_input_artifact_paths",
            "input_artifact_paths",
            "new_input_artifact_paths",
            "positive_input_delta_gate.supplied_input_artifact_paths",
            "positive_input_delta_gate.input_artifact_paths",
            "loop_breaker_packet.supplied_input_artifact_paths",
            "loop_breaker_packet.positive_input_delta_gate.supplied_input_artifact_paths",
            "result.positive_input_delta_gate.supplied_input_artifact_paths",
        ),
    )
    input_roles = {
        role.strip().lower()
        for role in list_field_paths(
            value,
            (
                "new_input_kinds",
                "input_kinds",
                "required_new_input_kinds",
                "introduced_input_kinds",
                "positive_input_delta_gate.new_input_kinds",
                "positive_input_delta_gate.input_kinds",
                "positive_input_delta_gate.required_new_input_kinds",
                "loop_breaker_packet.new_input_kinds",
                "loop_breaker_packet.required_new_input_kinds",
                "result.positive_input_delta_gate.new_input_kinds",
                "result.positive_input_delta_gate.required_new_input_kinds",
            ),
        )
        if role.strip()
    }
    role_paths = artifact_role_paths(value, input_roles)
    role_paths.extend(artifact_summary_role_paths(root, raw_paths, input_roles))
    existing_paths = existing_artifact_paths(root, raw_paths + role_paths)
    produced = boolish(delta.get("produced_domain_delta"))
    return {
        "has_supplied_input_delta": produced or bool(existing_paths),
        "supplied_input_artifact_paths": existing_paths,
        "missing_or_empty_input_artifact_paths": sorted(set(raw_paths + role_paths) - set(existing_paths)),
        "produced_domain_delta": produced,
    }
