from __future__ import annotations

from .common import *

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
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    if path.is_file():
        return read_json(path)
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
    normalized_keys = {normalize_root_family_key(key) for key in keys}
    for value in values:
        for item in iter_dicts(value):
            for key, child in item.items():
                if normalize_root_family_key(key) in normalized_keys and child not in (None, "", []):
                    return child
    return None
