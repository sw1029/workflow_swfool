"""Merge a small semantic judgment with protected coordinator-owned fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import validate_preparation
from .specs import DERIVED_FIELD_NAMES, TARGET_COMPILE_SPECS


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return dict(value)


@dataclass(frozen=True, slots=True)
class ResultBuilder:
    """Build a legacy-compatible result without allowing derived overrides."""

    def build(
        self,
        preparation: dict[str, Any],
        judgment: dict[str, Any],
    ) -> dict[str, Any]:
        preparation = validate_preparation(preparation)
        if not isinstance(judgment, dict):
            raise ValueError("stage judgment must be a JSON object")
        unknown_sections = set(judgment) - {
            "semantic",
            "owner_result",
            "reasoned_not_applicable",
        }
        if unknown_sections:
            raise ValueError(
                "stage judgment contains unknown sections: "
                + ", ".join(sorted(unknown_sections))
            )
        target = str(preparation["target"])
        spec = TARGET_COMPILE_SPECS[target]
        semantic = _mapping(judgment.get("semantic"), "semantic")
        owner_result = _mapping(judgment.get("owner_result"), "owner_result")
        reasoned = _mapping(
            judgment.get("reasoned_not_applicable"), "reasoned_not_applicable"
        )
        protected = set(DERIVED_FIELD_NAMES)
        override = protected & (set(semantic) | set(owner_result) | set(reasoned))
        if override:
            raise ValueError(
                "conflicting_derived_field: " + ", ".join(sorted(override))
            )
        allowed_semantic = set(spec.semantic_fields) | set(
            spec.optional_semantic_fields
        )
        unknown_semantic = set(semantic) - allowed_semantic
        if unknown_semantic:
            raise ValueError(
                "semantic judgment contains unclassified fields: "
                + ", ".join(sorted(unknown_semantic))
            )
        allowed_owner = set(spec.owner_receipt_fields) | set(spec.optional_owner_fields)
        unknown_owner = set(owner_result) - allowed_owner
        if unknown_owner:
            raise ValueError(
                "owner_result contains unclassified fields: "
                + ", ".join(sorted(unknown_owner))
            )
        unknown_reasoned = set(reasoned) - set(spec.reasoned_not_applicable_fields)
        if unknown_reasoned:
            raise ValueError(
                "reasoned_not_applicable contains unsupported fields: "
                + ", ".join(sorted(unknown_reasoned))
            )
        overlap = set(semantic) & set(owner_result)
        if overlap:
            raise ValueError(
                "semantic and owner_result both provide: " + ", ".join(sorted(overlap))
            )
        result = dict(owner_result)
        result.update(semantic)
        result.update(preparation.get("derived_values") or {})
        if reasoned:
            result["reasoned_not_applicable"] = reasoned
        return result


__all__ = ["ResultBuilder"]
