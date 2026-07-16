"""Independent source inventory and row reconstruction."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .core import (
    ALLOWED_CLASSIFICATIONS,
    _body_metadata,
    _body_text,
    _candidate_score,
    _is_current_record,
    _is_int,
    _require,
)

from .evidence_contracts import (
    ROW_BASE_KEYS,
    ROW_BODY_ALIAS_KEYS,
    ROW_BODY_CANONICAL_KEYS,
    ROW_DUPLICATE_KEYS,
)


def _exact_int_vector(value: Any, expected: tuple[int, ...]) -> bool:
    return (
        isinstance(value, list)
        and all(_is_int(item) for item in value)
        and value == list(expected)
    )

def _prepare_inventory(
    manifest: dict[str, Any], actual_markdown: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    inventory = manifest.get("markdown_inventory")
    _require(isinstance(inventory, list), "manifest Markdown inventory is missing")
    _require(
        inventory
        == sorted(
            inventory,
            key=lambda entry: entry.get("path", "") if isinstance(entry, dict) else "",
        ),
        "manifest Markdown inventory is not canonical",
    )
    inventory_by_path = {
        entry.get("path"): entry for entry in inventory if isinstance(entry, dict)
    }
    _require(
        len(inventory_by_path) == len(inventory),
        "manifest Markdown inventory has duplicate paths",
    )
    for path, entry in inventory_by_path.items():
        _require(
            set(entry) == {"path", "body_sha256", "size"}
            and isinstance(path, str)
            and isinstance(entry.get("body_sha256"), str)
            and _is_int(entry.get("size")),
            "manifest Markdown inventory entry is malformed",
        )
    actual_by_path = {entry.get("path"): entry for entry in actual_markdown}
    _require(
        len(actual_by_path) == len(actual_markdown),
        "current Markdown inventory has duplicate paths",
    )
    for path, entry in inventory_by_path.items():
        _require(
            actual_by_path.get(path) == entry,
            f"migration-time Markdown is missing or changed: {path}",
        )
    return inventory, inventory_by_path, actual_by_path

def _verify_plan_rows(
    source_by_line: dict[int, dict[str, Any]],
    plan_rows: list[dict[str, Any]],
    mappings: dict[str | None, dict[str, Any]],
    inventory_by_path: dict[str, dict[str, Any]],
) -> tuple[Counter[str], dict[str, list[dict[str, Any]]]]:
    seen_lines: set[int] = set()
    counts: Counter[str] = Counter()
    path_rows: dict[str, list[dict[str, Any]]] = {}
    for entry in plan_rows:
        _require(isinstance(entry, dict), "plan row is not an object")
        line = entry.get("source_line")
        _require(
            _is_int(line) and line in source_by_line and line not in seen_lines,
            "plan row line is missing, duplicate, or stale",
        )
        seen_lines.add(line)
        source = source_by_line[line]
        _require(
            entry.get("source_row_sha256") == source["source_row_sha256"],
            f"source row drift at line {line}",
        )
        parsed = source["parsed"]
        _require(isinstance(parsed, dict), f"unresolved malformed source row at line {line}")
        raw_status = parsed.get("status") if "status" in parsed else None
        _require(
            raw_status is None or (isinstance(raw_status, str) and raw_status),
            f"source status is malformed at line {line}",
        )
        _require(entry.get("original_status") == raw_status, f"original status mismatch at line {line}")
        mapping = mappings.get(raw_status)
        _require(mapping is not None, f"source status is not exact-map bound at line {line}")
        _require(
            entry.get("normalized_status") == mapping.get("normalized_status"),
            f"normalized status is not exact-map bound at line {line}",
        )
        _require(
            entry.get("status_mapping_reason") == mapping.get("reason"),
            f"status reason is not exact-map bound at line {line}",
        )
        declared_body = parsed.get("body_sha256")
        _require(
            entry.get("source_body_sha256")
            == (declared_body if isinstance(declared_body, str) else None),
            f"source body declaration mismatch at line {line}",
        )
        classification = entry.get("classification")
        _require(
            classification in ALLOWED_CLASSIFICATIONS,
            f"unresolved or unknown classification at line {line}",
        )
        counts[classification] += 1
        _require(
            entry.get("unresolved_reason") is None,
            f"resolved row carries an unresolved reason at line {line}",
        )
        path = parsed.get("path")
        if path is None:
            _require(
                classification == "foreign_event"
                and entry.get("disposition") == "quarantine_foreign_event",
                f"foreign row classification mismatch at line {line}",
            )
            _require(
                entry.get("source_path") is None
                and entry.get("canonical_target_path") is None,
                f"foreign row gained a path at line {line}",
            )
            _require(
                entry.get("canonical_target_source_line") is None
                and set(entry) == ROW_BASE_KEYS,
                f"foreign row projection mismatch at line {line}",
            )
            continue
        _require(
            isinstance(path, str) and path in inventory_by_path,
            f"source path is absent from inventory at line {line}",
        )
        _require(entry.get("source_path") == path, f"source path binding mismatch at line {line}")
        format_version = parsed.get("format_version", 1)
        schema_version = parsed.get("schema_version", 1)
        _require(
            _is_int(format_version) and 1 <= format_version <= 3,
            f"source format version is invalid at line {line}",
        )
        _require(
            _is_int(schema_version) and 1 <= schema_version <= 2,
            f"source schema version is invalid at line {line}",
        )
        body_sha = inventory_by_path[path]["body_sha256"]
        if format_version >= 3 or schema_version >= 2:
            _require(
                _is_current_record(parsed, body_sha),
                f"current integrity-bound source is invalid at line {line}",
            )
            _require(
                mapping.get("normalized_status") == parsed.get("status"),
                f"current integrity-bound status is rewritten at line {line}",
            )
        _require(
            classification in {"canonical_log", "duplicate_alias"},
            f"path-bearing row is not resolved at line {line}",
        )
        _require(
            _is_int(entry.get("canonical_target_source_line")),
            f"canonical target source line is malformed at line {line}",
        )
        path_rows.setdefault(path, []).append(entry)
    _require(seen_lines == set(source_by_line), "plan omits a source row")
    return counts, path_rows

def _select_path_winners(
    root: Path,
    path_rows: dict[str, list[dict[str, Any]]],
    source_by_line: dict[int, dict[str, Any]],
    inventory_by_path: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[int, tuple[int, ...]]]:
    winners: dict[str, dict[str, Any]] = {}
    scores: dict[int, tuple[int, ...]] = {}
    for path, rows in path_rows.items():
        body_sha = inventory_by_path[path]["body_sha256"]
        metadata = _body_metadata(root / path)
        text = _body_text(root / path)
        current_rows = [
            row
            for row in rows
            if _is_current_record(source_by_line[row["source_line"]]["parsed"], body_sha)
        ]
        _require(
            not (len(rows) > 1 and current_rows),
            f"duplicate current integrity-bound path is unresolved: {path}",
        )
        scored: list[tuple[tuple[int, ...], dict[str, Any]]] = []
        for row in rows:
            score = _candidate_score(
                source_by_line[row["source_line"]]["parsed"],
                body_sha,
                metadata,
                text,
            )
            _require(score is not None, f"source/body evidence mismatch at line {row['source_line']}")
            scores[row["source_line"]] = score
            scored.append((score, row))
        best = max(score for score, _ in scored)
        tied = [row for score, row in scored if score == best]
        if len(tied) > 1:
            hashes = {
                source_by_line[row["source_line"]]["source_row_sha256"]
                for row in tied
            }
            _require(
                len(hashes) == 1,
                f"duplicate path has an unresolved evidence tie: {path}",
            )
            tied.sort(key=lambda row: row["source_line"])
        selection_basis = (
            "exact_row_bytes_equivalent"
            if len(tied) > 1
            else "body_sha_log_metadata_content_token_score_v1"
        )
        for row in rows:
            _require(
                _is_int(row.get("duplicate_candidate_count"))
                and row["duplicate_candidate_count"] == len(rows)
                and _exact_int_vector(
                    row.get("duplicate_candidate_score"),
                    scores[row["source_line"]],
                )
                and row.get("duplicate_selection_basis") == selection_basis,
                f"duplicate evidence projection mismatch at line {row['source_line']}",
            )
        winners[path] = tied[0]
    return winners, scores

def _recompute_canonical_rows(
    root: Path,
    path_rows: dict[str, list[dict[str, Any]]],
    source_by_line: dict[int, dict[str, Any]],
    inventory_by_path: dict[str, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    provisional, scores = _select_path_winners(
        root, path_rows, source_by_line, inventory_by_path
    )
    by_body: dict[str, list[dict[str, Any]]] = {}
    for path, row in provisional.items():
        by_body.setdefault(inventory_by_path[path]["body_sha256"], []).append(row)
    target_by_path: dict[str, dict[str, Any]] = {}
    body_extra_keys: dict[int, frozenset[str]] = {}
    for body_sha, candidates in by_body.items():
        winner = candidates[0]
        if len(candidates) > 1:
            _require(
                not any(
                    _is_current_record(
                        source_by_line[row["source_line"]]["parsed"], body_sha
                    )
                    for row in candidates
                ),
                "duplicate current integrity-bound content ID is unresolved",
            )
            winner = sorted(
                candidates,
                key=lambda row: (
                    scores[row["source_line"]],
                    row["source_path"],
                    source_by_line[row["source_line"]]["source_row_sha256"],
                ),
                reverse=True,
            )[0]
            body_basis = "body_sha_log_metadata_content_token_score_then_path_hash_v1"
            _require(
                winner.get("body_alias_selection_basis") == body_basis
                and _is_int(winner.get("body_alias_candidate_count"))
                and winner["body_alias_candidate_count"] == len(candidates),
                "canonical body-alias evidence mismatch",
            )
            body_extra_keys[winner["source_line"]] = ROW_BODY_CANONICAL_KEYS
            for candidate in candidates:
                if candidate is winner:
                    continue
                _require(
                    candidate.get("alias_reason")
                    == "byte_identical_body_different_path"
                    and _exact_int_vector(
                        candidate.get("body_alias_candidate_score"),
                        scores[candidate["source_line"]],
                    )
                    and candidate.get("body_alias_selection_basis") == body_basis,
                    f"body-alias evidence mismatch at line {candidate['source_line']}",
                )
                body_extra_keys[candidate["source_line"]] = ROW_BODY_ALIAS_KEYS
        for row in candidates:
            target_by_path[row["source_path"]] = winner
    canonical: dict[int, dict[str, Any]] = {}
    for path, rows in path_rows.items():
        target = target_by_path[path]
        for entry in rows:
            expected_keys = (
                ROW_BASE_KEYS
                | ROW_DUPLICATE_KEYS
                | body_extra_keys.get(entry["source_line"], frozenset())
            )
            _require(
                set(entry) == expected_keys,
                f"source row schema projection mismatch at line {entry['source_line']}",
            )
            is_canonical = entry["source_line"] == target["source_line"]
            expected_class = "canonical_log" if is_canonical else "duplicate_alias"
            expected_disposition = (
                "bind_existing_body" if is_canonical else "retain_as_alias_evidence"
            )
            _require(
                entry.get("classification") == expected_class,
                f"independent source classification mismatch at line {entry['source_line']}",
            )
            _require(
                entry.get("disposition") == expected_disposition,
                f"independent source disposition mismatch at line {entry['source_line']}",
            )
            _require(
                entry.get("canonical_target_source_line") == target["source_line"]
                and entry.get("canonical_target_path") == target["source_path"],
                f"independent canonical target mismatch at line {entry['source_line']}",
            )
            if is_canonical:
                canonical[entry["source_line"]] = entry
    return canonical
