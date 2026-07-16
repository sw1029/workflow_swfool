from __future__ import annotations

from typing import Any

from .constants import INSPECTED_COUNT_KEYS, POPULATION_COUNT_KEYS, VALIDATOR_CHILD_KEYS
from .values import collect_result_bools, first_count_by_key, mapping_result_bool

def validator_integrity_gate(value: Any) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    def inspect(item: Any, path: str = "$") -> None:
        if isinstance(item, dict):
            top_result = mapping_result_bool(item)
            child_results: list[bool] = []
            for key in VALIDATOR_CHILD_KEYS:
                child = item.get(key)
                if isinstance(child, (dict, list)):
                    child_results.extend(collect_result_bools(child))
            if top_result is True and any(result is False for result in child_results):
                findings.append(
                    {
                        "kind": "integrity_mismatch",
                        "path": path,
                        "top_level_result": True,
                        "embedded_result_count": len(child_results),
                        "embedded_failed_count": sum(1 for result in child_results if result is False),
                    }
                )
            declared = first_count_by_key(item, POPULATION_COUNT_KEYS)
            inspected = first_count_by_key(item, INSPECTED_COUNT_KEYS)
            if declared is not None and inspected is not None and declared > 0 and inspected < declared:
                findings.append(
                    {
                        "kind": "under_detection",
                        "path": path,
                        "declared_population_count": declared,
                        "inspected_count": inspected,
                    }
                )
            for key, child in item.items():
                inspect(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                inspect(child, f"{path}[{index}]")

    inspect(value)
    mismatch = any(item["kind"] == "integrity_mismatch" for item in findings)
    under_detection = any(item["kind"] == "under_detection" for item in findings)
    blocked = mismatch or under_detection
    return {
        "gate": "G-INTEGRITY",
        "validator_integrity": "mismatch" if mismatch else "ok",
        "validator_coverage": "under_detection" if under_detection else "ok",
        "status": "block" if blocked else "ok",
        "hard_stop_required": blocked,
        "constrains_disposition": blocked,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "findings": findings[:20],
    }
