"""Static contracts and records for structure-first Markdown advice parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


CANONICAL_ID_PATTERN = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"
EXPLICIT_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}"
CANONICAL_ID_RE = re.compile(rf"^{CANONICAL_ID_PATTERN}$")
EXPLICIT_ID_RE = re.compile(rf"^{EXPLICIT_ID_PATTERN}$")
CANONICAL_ID_SEARCH_RE = re.compile(
    rf"(?<![A-Za-z0-9])({CANONICAL_ID_PATTERN})(?![A-Za-z0-9])"
)
HEADING_RE = re.compile(
    rf"^(?P<marks>#{{1,6}})\s+(?:`)?(?P<id>{CANONICAL_ID_PATTERN})(?:`)?"
    r"(?:\s*(?:—|–|:|-)?\s*(?P<title>.*))?$"
)
ANY_HEADING_RE = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
METADATA_RE = re.compile(
    r"^\s*[-*]\s+(?P<key>[A-Za-z][A-Za-z0-9_.-]{1,95})\s*:\s*"
    r"(?P<value>.+?)\s*$"
)
INLINE_DECLARATION_RE = re.compile(
    rf"^\s*(?:[-*]\s+)?`?(?P<id>{CANONICAL_ID_PATTERN})`?\s*"
    r"(?:[:：]|\s+[—–-]\s+)\s*(?P<body>.+?)\s*$"
)
BRACKET_DECLARATION_RE = re.compile(
    rf"^\s*(?:[-*]\s+)?\[(?P<id>{EXPLICIT_ID_PATTERN})\]\s*(?P<body>.+?)\s*$"
)
NUMBERED_DECLARATION_RE = re.compile(
    rf"^\s*\d+[.)]\s+`?(?P<id>{CANONICAL_ID_PATTERN})`?\s*,\s*"
    r"(?P<metadata>(?:`[^`]+`\s*,?\s*)+)\s*:\s*(?P<body>.+?)\s*$"
)
INLINE_METADATA_RE = re.compile(
    r"`?(?P<key>[A-Za-z][A-Za-z0-9_.-]{1,95})\s*:\s*(?P<value>[^`,]+)`?"
)
TABLE_SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
STRONG_HEADING_DIRECTIVE_RE = re.compile(
    r"(?:\bmust\b|\bshould\b|\brequire[sd]?\b|\bdo not\b|\bnever\b|"
    r"해야\s*한다|금지|강제|필수\s*규칙)",
    re.IGNORECASE,
)

DIRECTIVE_METADATA_KEYS = {
    "actionable_child",
    "actionable_child_consumption_state",
    "activation_rule",
    "change_class",
    "classification",
    "conditional_grouping",
    "consumption_state",
    "default_state",
    "grouping_only",
    "requires_adapter_or_task_contract_adoption",
    "selection_disposition",
    "selection_disposition_when_capability_absent",
    "target_owner",
}
CONDITIONAL_METADATA_KEYS = {
    "activation_rule",
    "selection_disposition",
    "selection_disposition_when_capability_absent",
}
HEADING_OWNER_KEYS = DIRECTIVE_METADATA_KEYS - {"actionable_child"}


@dataclass(slots=True)
class SourceLine:
    number: int
    raw: str
    cleaned: str
    in_table: bool = False


@dataclass(slots=True)
class Heading:
    number: int
    level: int
    title: str
    directive_id: str | None
    parent: Heading | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class DirectiveParseResult:
    records: list[dict[str, Any]]
    stats: dict[str, Any]


__all__ = [
    "ANY_HEADING_RE",
    "CANONICAL_ID_RE",
    "CANONICAL_ID_SEARCH_RE",
    "BRACKET_DECLARATION_RE",
    "CONDITIONAL_METADATA_KEYS",
    "DIRECTIVE_METADATA_KEYS",
    "DirectiveParseResult",
    "EXPLICIT_ID_RE",
    "HEADING_OWNER_KEYS",
    "HEADING_RE",
    "Heading",
    "INLINE_DECLARATION_RE",
    "INLINE_METADATA_RE",
    "METADATA_RE",
    "NUMBERED_DECLARATION_RE",
    "STRONG_HEADING_DIRECTIVE_RE",
    "SourceLine",
    "TABLE_SEPARATOR_RE",
]
