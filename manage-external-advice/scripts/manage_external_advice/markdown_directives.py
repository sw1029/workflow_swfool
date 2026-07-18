"""Structure-first Markdown directive extraction.

Canonical owners come from explicit Markdown structure.  Tables and prose that
only repeat an existing ID remain references to that owner and never become a
second declaration.  Heuristic body extraction is retained solely for advice
without a structured directive registry.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any

from .contracts import DIRECTIVE_LINE_RE, METADATA_LINE_RE
from .markdown_directive_contracts import (
    ANY_HEADING_RE,
    BRACKET_DECLARATION_RE,
    CONDITIONAL_METADATA_KEYS,
    DIRECTIVE_METADATA_KEYS,
    DirectiveParseResult,
    EXPLICIT_ID_RE,
    HEADING_OWNER_KEYS,
    HEADING_RE,
    Heading,
    INLINE_DECLARATION_RE,
    INLINE_METADATA_RE,
    METADATA_RE,
    NUMBERED_DECLARATION_RE,
    STRONG_HEADING_DIRECTIVE_RE,
    SourceLine,
    TABLE_SEPARATOR_RE,
)


def _strip_markup(value: str) -> str:
    cleaned = value.strip().strip("|").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] == "`":
        cleaned = cleaned[1:-1].strip()
    return re.sub(r"\s+", " ", cleaned).strip()


def _clean_body_line(value: str) -> str:
    cleaned = re.sub(r"^\s{0,3}>\s*", "", value)
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned)
    return _strip_markup(cleaned)[:500]


def _visible_lines(text: str) -> list[SourceLine]:
    visible: list[SourceLine] = []
    in_fence = False
    for number, raw in enumerate(text.splitlines(), start=1):
        if raw.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = raw.strip()
        in_table = stripped.startswith("|") and stripped.count("|") >= 2
        visible.append(
            SourceLine(
                number=number,
                raw=raw,
                cleaned=_clean_body_line(raw),
                in_table=in_table,
            )
        )
    return visible


def _metadata(line: SourceLine) -> tuple[str, str] | None:
    match = METADATA_RE.match(line.raw)
    if not match:
        return None
    key = match.group("key").lower().replace("-", "_")
    return key, _strip_markup(match.group("value"))


def _headings(lines: list[SourceLine]) -> list[Heading]:
    headings: list[Heading] = []
    stack: list[Heading] = []
    for line in lines:
        match = ANY_HEADING_RE.match(line.raw.strip())
        if match:
            level = len(match.group("marks"))
            while stack and stack[-1].level >= level:
                stack.pop()
            canonical = HEADING_RE.match(line.raw.strip())
            heading = Heading(
                number=line.number,
                level=level,
                title=_strip_markup(
                    canonical.group("title") if canonical else match.group("title")
                ),
                directive_id=canonical.group("id") if canonical else None,
                parent=stack[-1] if stack else None,
            )
            headings.append(heading)
            stack.append(heading)
            continue
        if not stack or line.in_table:
            continue
        parsed = _metadata(line)
        if parsed and parsed[0] != "directive_id":
            stack[-1].metadata[parsed[0]] = parsed[1]
    return headings


def _heading_at(headings: list[Heading], line_number: int) -> Heading | None:
    current: Heading | None = None
    for heading in headings:
        if heading.number >= line_number:
            break
        if current is None or heading.number > current.number:
            current = heading
    return current


def _inherited_metadata(heading: Heading) -> dict[str, str]:
    ancestors: list[Heading] = []
    current = heading.parent
    while current is not None:
        ancestors.append(current)
        current = current.parent
    inherited: dict[str, str] = {}
    for ancestor in reversed(ancestors):
        for key in CONDITIONAL_METADATA_KEYS:
            if key in ancestor.metadata:
                inherited[key] = ancestor.metadata[key]
    return inherited


def _canonical_heading(heading: Heading) -> bool:
    if not heading.directive_id:
        return False
    inherited = _inherited_metadata(heading)
    return bool(
        HEADING_OWNER_KEYS.intersection(heading.metadata)
        or inherited
        or STRONG_HEADING_DIRECTIVE_RE.search(heading.title)
    )


def _record(
    directive_id: str | None,
    body: str,
    declaration_kind: str,
    line_number: int,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    values = {
        key: value
        for key, value in (metadata or {}).items()
        if key in DIRECTIVE_METADATA_KEYS and value not in (None, "")
    }
    if values.get("classification") and not values.get("change_class"):
        values["change_class"] = values["classification"]
    state = values.get("consumption_state") or values.get("default_state")
    if not state and values.get("grouping_only", "").lower() == "true":
        state = "grouping_only"
    if not state and str(values.get("selection_disposition", "")).startswith(
        "deferred"
    ):
        state = "deferred"
    return {
        "directive_id": directive_id,
        "directive_state": state or "pending",
        "id_origin": "explicit" if directive_id else "source_digest_ordinal",
        "semantic_equivalence_claimed": "false",
        "directive_text": _strip_markup(body) or str(directive_id or "directive"),
        "declaration_kind": declaration_kind,
        "_line_number": line_number,
        **values,
    }


def _heading_records(headings: list[Heading]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for heading in headings:
        if not _canonical_heading(heading):
            continue
        inherited = _inherited_metadata(heading)
        metadata = {**inherited, **heading.metadata}
        if inherited:
            metadata["conditional_grouping"] = "true"
        records.append(
            _record(
                heading.directive_id,
                heading.title,
                "heading",
                heading.number,
                metadata,
            )
        )
    return records


def _split_table_row(line: SourceLine) -> list[str]:
    stripped = line.raw.strip().strip("|")
    return [_strip_markup(cell) for cell in stripped.split("|")]


def _table_key(value: str) -> str:
    normalized = re.sub(r"[^0-9a-z가-힣]+", "_", value.lower()).strip("_")
    aliases = {
        "directive_id": "directive_id",
        "directiveid": "directive_id",
        "change_class": "change_class",
        "consumption_state": "consumption_state",
        "default_state": "default_state",
        "directive_text": "directive_text",
        "role": "directive_text",
        "역할": "directive_text",
        "필수_행동": "directive_text",
    }
    return aliases.get(normalized, normalized)


def _table_groups(lines: list[SourceLine]) -> list[list[SourceLine]]:
    groups: list[list[SourceLine]] = []
    current: list[SourceLine] = []
    for line in lines:
        if line.in_table:
            current.append(line)
            continue
        if current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    return groups


def _table_records(lines: list[SourceLine]) -> tuple[list[dict[str, Any]], set[int]]:
    records: list[dict[str, Any]] = []
    declaration_lines: set[int] = set()
    for group in _table_groups(lines):
        if len(group) < 3:
            continue
        headers = [_table_key(cell) for cell in _split_table_row(group[0])]
        separator = _split_table_row(group[1])
        if "directive_id" not in headers or not all(
            TABLE_SEPARATOR_RE.match(cell.replace(" ", "")) for cell in separator
        ):
            continue
        for line in group[2:]:
            cells = _split_table_row(line)
            row = dict(zip(headers, cells, strict=False))
            directive_id = row.get("directive_id")
            if not directive_id or not EXPLICIT_ID_RE.fullmatch(directive_id):
                continue
            metadata = {
                key: value
                for key, value in row.items()
                if key in DIRECTIVE_METADATA_KEYS and value
            }
            body = row.get("directive_text") or directive_id
            records.append(
                _record(
                    directive_id,
                    body,
                    "directive_table",
                    line.number,
                    metadata,
                )
            )
            declaration_lines.add(line.number)
    return records, declaration_lines


def _explicit_block_records(
    lines: list[SourceLine], headings: list[Heading]
) -> tuple[list[dict[str, Any]], set[int]]:
    records: list[dict[str, Any]] = []
    declaration_lines: set[int] = set()
    for index, line in enumerate(lines):
        parsed = _metadata(line)
        if not parsed or parsed[0] != "directive_id":
            continue
        directive_id = parsed[1]
        if not EXPLICIT_ID_RE.fullmatch(directive_id):
            continue
        metadata: dict[str, str] = {}
        for following in lines[index + 1 :]:
            if not following.cleaned:
                continue
            item = _metadata(following)
            if item and item[0] != "directive_id":
                metadata[item[0]] = item[1]
                continue
            break
        heading = _heading_at(headings, line.number)
        body = heading.title if heading else directive_id
        records.append(
            _record(
                directive_id,
                body,
                "directive_id_block",
                line.number,
                metadata,
            )
        )
        declaration_lines.add(line.number)
    return records, declaration_lines


def _inline_metadata(value: str) -> dict[str, str]:
    return {
        match.group("key").lower().replace("-", "_"): _strip_markup(
            match.group("value")
        )
        for match in INLINE_METADATA_RE.finditer(value)
    }


def _inline_records(
    lines: list[SourceLine], occupied: set[int]
) -> tuple[list[dict[str, Any]], set[int]]:
    records: list[dict[str, Any]] = []
    declaration_lines: set[int] = set()
    for line in lines:
        if line.number in occupied or line.in_table or ANY_HEADING_RE.match(line.raw):
            continue
        numbered = NUMBERED_DECLARATION_RE.match(line.raw)
        if numbered:
            metadata = _inline_metadata(numbered.group("metadata"))
            if DIRECTIVE_METADATA_KEYS.intersection(metadata):
                records.append(
                    _record(
                        numbered.group("id"),
                        numbered.group("body"),
                        "inline_grouped_declaration",
                        line.number,
                        metadata,
                    )
                )
                declaration_lines.add(line.number)
            continue
        match = INLINE_DECLARATION_RE.match(line.raw)
        if not match:
            match = BRACKET_DECLARATION_RE.match(line.raw)
        if not match:
            continue
        records.append(
            _record(
                match.group("id"),
                match.group("body"),
                "inline_declaration",
                line.number,
            )
        )
        declaration_lines.add(line.number)
    return records, declaration_lines


def _heuristic_records(
    lines: list[SourceLine], occupied: set[int]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    candidates = [
        line
        for line in lines
        if line.number not in occupied
        and not line.in_table
        and not ANY_HEADING_RE.match(line.raw)
        and line.cleaned
        and not METADATA_LINE_RE.search(line.cleaned)
        and len(line.cleaned) >= 12
    ]
    directives = [line for line in candidates if DIRECTIVE_LINE_RE.search(line.cleaned)]
    if not directives:
        directives = [
            line
            for line in candidates
            if line.cleaned.startswith(("G-", "A", "Capability"))
        ]
    for line in directives:
        records.append(
            _record(
                None,
                line.cleaned,
                "raw_direct_fallback",
                line.number,
            )
        )
    return records


def _reference_fields(
    lines: list[SourceLine], records: list[dict[str, Any]], declaration_lines: set[int]
) -> dict[str, dict[str, Any]]:
    known_ids = {
        str(record.get("directive_id"))
        for record in records
        if record.get("directive_id")
    }
    counts: Counter[str] = Counter()
    kinds: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        if line.number in declaration_lines:
            continue
        for directive_id in known_ids:
            boundary = r"[A-Za-z0-9._:/#-]"
            if not re.search(
                rf"(?<!{boundary}){re.escape(directive_id)}(?!{boundary})", line.raw
            ):
                continue
            counts[directive_id] += 1
            if line.in_table:
                kinds[directive_id].add("table_reference")
            elif _metadata(line):
                kinds[directive_id].add("metadata_reference")
            else:
                kinds[directive_id].add("body_reference")
    return {
        directive_id: {
            "reference_classification": "owning_clause_reference",
            "reference_count": count,
            "reference_kinds": sorted(kinds[directive_id]),
        }
        for directive_id, count in counts.items()
    }


def _assign_generated_ids(
    records: list[dict[str, Any]], raw_sha256: str
) -> list[dict[str, Any]]:
    ordered = sorted(records, key=lambda row: int(row["_line_number"]))
    for ordinal, record in enumerate(ordered, start=1):
        if not record.get("directive_id"):
            record["directive_id"] = f"dir-{raw_sha256}-{ordinal:04d}"
    return ordered


def parse_directive_document(text: str, raw_sha256: str) -> DirectiveParseResult:
    """Parse canonical owner clauses before using raw-body heuristics."""

    lines = _visible_lines(text)
    headings = _headings(lines)
    heading_records = _heading_records(headings)
    table_records, table_lines = _table_records(lines)
    block_records, block_lines = _explicit_block_records(lines, headings)
    heading_lines = {record["_line_number"] for record in heading_records}
    occupied = {*heading_lines, *table_lines, *block_lines}
    inline_records, inline_lines = _inline_records(lines, occupied)
    occupied.update(inline_lines)
    structural_records = [*heading_records, *table_records, *block_records]
    heuristic_records = (
        [] if structural_records else _heuristic_records(lines, occupied)
    )
    records = _assign_generated_ids(
        [*structural_records, *inline_records, *heuristic_records], raw_sha256
    )
    declaration_lines = {*occupied, *inline_lines}
    references = _reference_fields(lines, records, declaration_lines)
    for record in records:
        record.update(references.get(str(record["directive_id"]), {}))
        record.pop("_line_number", None)
    ids = [str(record["directive_id"]) for record in records]
    duplicate_ids = sorted(
        directive_id for directive_id, count in Counter(ids).items() if count > 1
    )
    stats = {
        "canonical_declaration_count": len(structural_records) + len(inline_records),
        "canonical_heading_count": len(heading_records),
        "canonical_table_declaration_count": len(table_records),
        "explicit_declaration_count": len(block_records) + len(inline_records),
        "generated_directive_count": len(heuristic_records),
        "raw_direct_fallback_used": bool(heuristic_records),
        "structured_directive_document": bool(structural_records),
        "reference_echo_count": sum(
            int(value["reference_count"]) for value in references.values()
        ),
        "duplicate_canonical_ids": duplicate_ids,
    }
    return DirectiveParseResult(records=records, stats=stats)


__all__ = [
    "DirectiveParseResult",
    "parse_directive_document",
]
