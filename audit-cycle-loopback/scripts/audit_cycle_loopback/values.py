from __future__ import annotations

from typing import Any
from pathlib import Path
import json
from . import families as _families
from . import io_utils as _io_utils


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present"}
    return False

def float_value(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0

def int_metric(value: Any) -> int:
    return int(max(0.0, float_value(value)))


def positive_int_or_none(value: Any) -> int | None:
    """Return an explicitly supplied positive integer without inventing one."""
    if isinstance(value, bool) or value is None:
        return None
    raw = value
    if isinstance(value, dict):
        raw = next(
            (
                value.get(key)
                for key in (
                    "budget_value",
                    "budget",
                    "cap",
                    "threshold",
                    "limit",
                    "max_attempts",
                    "value",
                )
                if value.get(key) is not None
            ),
            None,
        )
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        numeric = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if numeric <= 0 or not numeric.is_integer():
        return None
    return int(numeric)


def budget_evaluation(
    budget_id: str,
    value: Any,
    *,
    source: str | None = None,
    applicable: bool = True,
    error: str | None = None,
) -> dict[str, Any]:
    """Normalize a caller/adapter budget into a typed, fail-quiet contract."""
    normalized_id = _families.normalize_root_family_key(budget_id) or str(budget_id)
    if not applicable:
        status = "not_evaluated"
        reason = "budget_not_applicable"
        parsed = None
    else:
        parsed = positive_int_or_none(value)
        status = "evaluated" if parsed is not None else "budget_unverified"
        reason = None if parsed is not None else ("budget_provider_error" if error else "budget_not_supplied_or_invalid")
    supplied_source = source
    if isinstance(value, dict):
        supplied_source = str(
            value.get("budget_source")
            or value.get("source")
            or value.get("provided_by")
            or supplied_source
            or ""
        ).strip() or None
    result = {
        "budget_id": normalized_id,
        "budget_value": parsed,
        "evaluation_status": status,
        "budget_evaluation_status": status,
        "source": supplied_source if parsed is not None else None,
        "reason_code": reason,
    }
    if error:
        result["provider_error"] = error
    return result


def budget_value(contract: Any) -> int | None:
    if not isinstance(contract, dict):
        return None
    if contract.get("budget_evaluation_status") != "evaluated":
        return None
    return positive_int_or_none(contract.get("budget_value"))


def truthy_observation(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        text = value.strip().lower()
        return bool(text) and text not in {"false", "none", "null", "unknown", "0", "no"}
    if isinstance(value, (list, dict)):
        return bool(value)
    return False

def list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []

def load_json_value(root: Path, raw: str | None) -> Any:
    if not raw:
        return None
    if raw.lstrip().startswith(("{", "[")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    try:
        if path.is_file():
            return _io_utils.read_json(path)
    except OSError:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None

def load_json_values(root: Path, raws: list[str] | None) -> list[Any]:
    values: list[Any] = []
    for raw in raws or []:
        loaded = load_json_value(root, raw)
        if loaded is not None:
            values.append(loaded)
    return values

def iter_dicts(value: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 6:
        return []
    items: list[dict[str, Any]] = []
    if isinstance(value, dict):
        items.append(value)
        for child in value.values():
            items.extend(iter_dicts(child, depth=depth + 1))
    elif isinstance(value, list):
        for child in value:
            items.extend(iter_dicts(child, depth=depth + 1))
    return items

def first_field_value(values: list[Any], keys: set[str]) -> Any:
    normalized_keys = {_families.normalize_root_family_key(key) for key in keys}
    for value in values:
        for item in iter_dicts(value):
            for key, child in item.items():
                if _families.normalize_root_family_key(key) in normalized_keys and child not in (None, "", []):
                    return child
    return None
