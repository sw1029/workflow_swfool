from __future__ import annotations

from abc import ABC, abstractmethod
import re
from typing import Any

from .constants import *
from .values import *


class SignatureNormalizer(ABC):
    """Base class for stable loop-family normalizers."""

    @abstractmethod
    def normalize(self, value: dict[str, Any], blockers: list[str]) -> str | None:
        raise NotImplementedError


def normalized_signature(value: dict[str, Any], blockers: list[str]) -> str | None:
    explicit = value.get("blocker_signature") or value.get("normalized_blocker_signature")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    parts: list[str] = []
    for key in ("blocker_taxonomy", "issue_path", "task_miss_path", "target_surface", "provider_dependency", "missing_input_kind", "evidence_family"):
        parts.extend(list_field(value.get(key)))
    if not parts:
        parts.extend(blockers)
    if not parts:
        return None
    text = "|".join(str(part).strip().lower() for part in parts if part and str(part).strip())
    text = VOLATILE_SIGNATURE_RE.sub("-", text)
    return f"blocker:{stable_digest([text])[:32]}"


def semantic_signature(
    value: dict[str, Any],
    blockers: list[str],
    policy: dict[str, Any] | None = None,
) -> str | None:
    explicit = value.get("semantic_signature") or value.get("normalized_semantic_signature")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()

    raw_parts: list[str] = []
    for key in (
        "blocker_taxonomy",
        "issue_path",
        "task_miss_path",
        "provider_dependency",
        "missing_input_kind",
        "evidence_family",
        "target_surface",
        "blocker_signature",
    ):
        raw_parts.extend(list_field(value.get(key)))
    raw_parts.extend(blockers)

    normalized = normalized_signature(value, blockers)
    if normalized:
        raw_parts.append(normalized)
    if not raw_parts:
        return None

    raw_text = "|".join(str(part).strip().lower() for part in raw_parts if str(part).strip())
    stable_text = VOLATILE_SIGNATURE_RE.sub("-", raw_text)
    stable_text = SIGNATURE_TOKEN_RE.sub("-", stable_text).strip("-")

    patterns = (policy or {}).get("semantic_axis_patterns") or []
    axes = [axis for axis, pattern in patterns if re.search(pattern, raw_text, re.IGNORECASE)]
    taxonomies = list_field(value.get("blocker_taxonomy"))
    provider_dependency = list_field(value.get("provider_dependency"))
    missing_kind = list_field(value.get("missing_input_kind"))

    parts = [*(item.lower() for item in taxonomies), *axes, *(item.lower() for item in provider_dependency), *(item.lower() for item in missing_kind)]
    if parts:
        text = "|".join(dict.fromkeys(parts))
        return f"semantic:{stable_digest([text])[:32]}"
    return f"semantic:{stable_digest([stable_text])[:32]}" if stable_text else None


def root_axis(
    value: dict[str, Any],
    blockers: list[str],
    semantic: str | None,
    signature: str | None,
    policy: dict[str, Any] | None = None,
) -> str | None:
    explicit = value.get("root_axis") or value.get("goal_root_axis") or value.get("loop_root_axis")
    if isinstance(explicit, str) and explicit.strip():
        return SIGNATURE_TOKEN_RE.sub("_", explicit.strip().lower()).strip("_")[:120] or None

    parts: list[str] = []
    for key in (
        "root_axis",
        "goal_axis",
        "blocker_taxonomy",
        "issue_path",
        "task_miss_path",
        "provider_dependency",
        "missing_input_kind",
        "evidence_family",
        "target_surface",
        "semantic_signature",
        "blocker_signature",
        "task_id",
        "output_delta_kind",
    ):
        parts.extend(list_field(value.get(key)))
    parts.extend(blockers)
    if semantic:
        parts.append(semantic)
    if signature:
        parts.append(signature)
    if not parts:
        return None

    raw_text = "|".join(str(part).strip().lower() for part in parts if str(part).strip())
    patterns = (policy or {}).get("root_axis_patterns") or []
    for axis, pattern in patterns:
        if re.search(pattern, raw_text, re.IGNORECASE):
            return axis
    return None


def root_key(value: dict[str, Any], blockers: list[str], semantic: str | None, signature: str | None) -> str | None:
    explicit = value.get("root_key") or value.get("semantic_root_key") or value.get("loop_root_key")
    raw_parts: list[str] = []
    if isinstance(explicit, str) and explicit.strip():
        raw_parts.append(explicit)
    for item in (semantic, signature):
        if item:
            raw_parts.append(item)
    for key in (
        "semantic_signature",
        "normalized_semantic_signature",
        "blocker_signature",
        "target_surface",
        "evidence_family",
        "blocker_taxonomy",
        "issue_path",
        "task_miss_path",
    ):
        raw_parts.extend(list_field(value.get(key)))
    raw_parts.extend(blockers)
    if not raw_parts:
        return None
    raw_text = "|".join(str(part).strip().lower() for part in raw_parts if str(part).strip())
    stable_text = VOLATILE_SIGNATURE_RE.sub("-", raw_text)
    stable_text = re.sub(r"(?:^|[-_.|:/])(?:v|ver|version)[-_.]?\d+\b", "-", stable_text, flags=re.IGNORECASE)
    stable_text = re.sub(r"(?:^|[-_.|:/])(?:\d{8,14}|\d{4}[-_.]?\d{2}[-_.]?\d{2})\b", "-", stable_text)
    stable_text = SIGNATURE_TOKEN_RE.sub("-", stable_text).strip("-_./:")
    if not stable_text:
        return None
    return f"root:{stable_digest([stable_text])[:32]}"
