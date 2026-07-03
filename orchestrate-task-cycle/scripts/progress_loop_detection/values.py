from __future__ import annotations

import datetime as dt
import hashlib
import re
from typing import Any

from .constants import *

def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def stable_digest(parts: list[str] | tuple[str, ...] | set[str]) -> str:
    digest = hashlib.sha256()
    for part in sorted(str(item) for item in parts if item is not None and str(item) != ""):
        digest.update(part.encode("utf-8", errors="replace"))
        digest.update(b"\0")
    return digest.hexdigest()


def scalar_values(value: Any) -> list[str]:
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(scalar_values(item))
        return items
    if isinstance(value, dict):
        items: list[str] = []
        for item in value.values():
            items.extend(scalar_values(item))
        return items
    return []


def collect_by_key(value: Any, keys: set[str]) -> list[str]:
    collected: list[str] = []

    def collect_matching_keys(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key.lower() in keys:
                    collected.extend(scalar_values(child))
                collect_matching_keys(child)
        elif isinstance(item, list):
            for child in item:
                collect_matching_keys(child)

    collect_matching_keys(value)
    return sorted(set(collected))


def list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item) != ""]
    if isinstance(value, str) and value:
        return [value]
    return []


def structured_progress(value: dict[str, Any]) -> str | None:
    for key in ("progress_verdict", "progress", "progress_status"):
        raw = value.get(key)
        if isinstance(raw, dict):
            raw = raw.get("verdict") or raw.get("progress_verdict")
        if isinstance(raw, str) and raw.lower() in {"advanced", "safety_only", "no_progress", "regressed"}:
            return raw.lower()
    return None


def structured_blockers(value: dict[str, Any]) -> list[str]:
    blockers = []
    for key in ("blockers", "remaining_blockers", "blocking_findings"):
        blockers.extend(list_values(value.get(key)))
    return blockers[:5]


def list_field(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "required", "present", "added"}
    return False


def number_value(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def float_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def value_at(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for key in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_value(value: dict[str, Any], paths: tuple[str, ...]) -> Any:
    for path in paths:
        current = value_at(value, path) if "." in path else value.get(path)
        if current is None:
            continue
        if isinstance(current, (list, dict)) and not current:
            continue
        if isinstance(current, str) and not current.strip():
            continue
        return current
    return None


def first_mapping(value: dict[str, Any], paths: tuple[str, ...]) -> dict[str, Any]:
    for path in paths:
        current = value_at(value, path) if "." in path else value.get(path)
        if isinstance(current, dict) and current:
            return current
    return {}


def list_field_paths(value: dict[str, Any], paths: tuple[str, ...]) -> list[str]:
    items: list[str] = []
    for path in paths:
        raw = value_at(value, path) if "." in path else value.get(path)
        items.extend(list_field(raw))
    return sorted(set(items))


def normalize_root_family_key(*values: Any) -> str:
    raw = "|".join(str(value or "") for value in values if value is not None and str(value).strip()).lower()
    if not raw:
        return "unknown"
    raw = VOLATILE_SIGNATURE_RE.sub("-", raw)
    raw = re.sub(r"\bv\d+\b|[-_]v\d+\b", "vnnn", raw)
    raw = SIGNATURE_TOKEN_RE.sub("-", raw).strip("-_.:/|")
    for _ in range(6):
        updated = FACET_SUFFIX_RE.sub("", raw).strip("-_.:/|")
        if updated == raw:
            break
        raw = updated
    tokens = [token for token in re.split(r"[|._:/-]+", raw) if token and not token.isdigit()]
    return "_".join(dict.fromkeys(tokens[:16]))[:200] or "unknown"


def explicit_result_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in PASS_STATUS_VALUES:
            return True
        if lowered in FAIL_STATUS_VALUES:
            return False
    return None


def mapping_result_bool(mapping: dict[str, Any]) -> bool | None:
    for key, value in mapping.items():
        if str(key).strip().lower() in VALIDATOR_RESULT_KEYS:
            result = explicit_result_bool(value)
            if result is not None:
                return result
    return None


def collect_result_bools(value: Any) -> list[bool]:
    results: list[bool] = []

    def collect_result_flags(item: Any) -> None:
        if isinstance(item, dict):
            result = mapping_result_bool(item)
            if result is not None:
                results.append(result)
            for child in item.values():
                collect_result_flags(child)
        elif isinstance(item, list):
            for child in item:
                collect_result_flags(child)

    collect_result_flags(value)
    return results


def first_count_by_key(mapping: dict[str, Any], keys: set[str]) -> int | None:
    for key, value in mapping.items():
        if str(key).strip().lower() not in keys:
            continue
        count = number_value(value)
        if count is not None:
            return count
    return None
