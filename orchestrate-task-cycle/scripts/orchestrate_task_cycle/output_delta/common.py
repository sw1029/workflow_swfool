from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONTRACT_PATHS = (
    ".task/contracts/output_delta_contract.json",
    ".agent_goal/output_delta_contract.json",
)
QUALITY_DELTA_KEYS: tuple[str, ...] = ()
METRIC_APPLICABILITY_STATUSES = {
    "applicable",
    "not_applicable",
    "insufficient_evidence",
    "invalid_contract",
}
METRIC_POLICY_CONTRACT_ERROR_CODES = {
    "declared_metric_id_malformed",
    "metric_alias_contract_malformed",
    "metric_policy_contract_malformed",
}
OPAQUE_ID_MAX_LENGTH = 256


def opaque_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > OPAQUE_ID_MAX_LENGTH:
        return None
    return normalized


def applicability_reason_code(value: Any, *, fallback: str | None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return fallback
    normalized = opaque_id(value)
    if (
        normalized is None
        or not normalized[0].isascii()
        or not normalized[0].isalnum()
        or any(
            not character.isascii() or not (character.isalnum() or character in "._-")
            for character in normalized
        )
    ):
        return "applicability_reason_code_malformed"
    return normalized


def legacy_applicability_projection(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and all(
            isinstance(row, dict)
            and str(row.get("evaluation_status") or "").strip().lower() == "applicable"
            and row.get("reason_code") == "legacy_declared_metric"
            for row in value.values()
        )
    )


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def discover_contract(
    root: Path, explicit: str | None = None
) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    candidates = [explicit] if explicit else list(DEFAULT_CONTRACT_PATHS)
    for value in candidates:
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            continue
        loaded = read_json(path)
        if not isinstance(loaded, dict):
            return path, None, "malformed_contract_json"
        return path, loaded, None
    return None, None, "not_applicable_no_contract"


def as_list(value: Any) -> list[str]:
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
        return value.strip().lower() in {
            "true",
            "yes",
            "1",
            "present",
            "produced",
            "changed",
        }
    return False


def number_value(value: Any) -> float:
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


def policy_items(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [normalized for item in value if (normalized := opaque_id(item)) is not None]


def policy_items_contract(
    value: Any, *, absent_allowed: bool = False
) -> tuple[list[str], bool]:
    """Return string contract items without stringifying malformed values."""
    if value is None:
        return ([], absent_allowed)
    if isinstance(value, str):
        normalized = opaque_id(value)
        return ([normalized], True) if normalized is not None else ([], False)
    if not isinstance(value, (list, tuple, set)):
        return ([], False)
    items: list[str] = []
    valid = True
    for item in value:
        normalized = opaque_id(item)
        if normalized is None:
            valid = False
            continue
        items.append(normalized)
    return (items, valid)


def opaque_id_list_valid(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return opaque_id(value) is not None
    return isinstance(value, (list, tuple, set)) and all(
        opaque_id(item) is not None for item in value
    )
