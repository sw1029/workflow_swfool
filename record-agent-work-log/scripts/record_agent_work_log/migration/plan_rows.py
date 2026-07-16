"""Source-row classification and canonical path selection for migration plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..integrity import LOG_FORMAT_VERSION, LOG_SCHEMA_VERSION, sha256_file
from .classification import (
    _body_metadata,
    _body_text_for_matching,
    _candidate_score,
    _is_current_record_valid,
    _safe_source_path,
    _status_mapping,
)


def _base_row(row: dict[str, Any]) -> dict[str, Any]:
    parsed = row.get("parsed")
    original = (
        parsed.get("status")
        if isinstance(parsed, dict) and isinstance(parsed.get("status"), str)
        else None
    )
    source_path = (
        parsed.get("path")
        if isinstance(parsed, dict) and isinstance(parsed.get("path"), str)
        else None
    )
    source_body_sha = (
        parsed.get("body_sha256")
        if isinstance(parsed, dict) and isinstance(parsed.get("body_sha256"), str)
        else None
    )
    return {
        "source_line": row["source_line"],
        "source_row_sha256": row["source_row_sha256"],
        "original_status": original,
        "source_path": source_path,
        "source_body_sha256": source_body_sha,
        "classification": "unresolved",
        "normalized_status": None,
        "status_mapping_reason": None,
        "canonical_target_path": None,
        "canonical_target_source_line": None,
        "disposition": "block",
        "unresolved_reason": None,
    }


def classify_source_rows(
    root: Path,
    source_rows: list[dict[str, Any]],
    mappings: dict[str | None, dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Classify rows independently before duplicate selection."""

    row_plans: dict[int, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in source_rows:
        entry = _base_row(row)
        row_plans[row["source_line"]] = entry
        parsed = row.get("parsed")
        if not isinstance(parsed, dict):
            entry["unresolved_reason"] = (
                f"malformed_json:{row.get('parse_error') or 'unknown'}"
            )
            continue
        original, normalized, mapping_reason, status_error = _status_mapping(
            parsed, mappings
        )
        entry.update(
            original_status=original,
            normalized_status=normalized,
            status_mapping_reason=mapping_reason,
        )
        if status_error:
            entry["unresolved_reason"] = status_error
            continue
        if parsed.get("path") is None:
            entry.update(
                classification="foreign_event",
                disposition="quarantine_foreign_event",
                unresolved_reason=None,
            )
            continue
        if not isinstance(parsed.get("path"), str) or not parsed["path"]:
            entry["unresolved_reason"] = "source path is not a non-empty string or null"
            continue
        body_path, path_error = _safe_source_path(root, parsed["path"])
        if path_error or body_path is None:
            entry["unresolved_reason"] = path_error or "source body is unavailable"
            continue
        entry["source_path"] = parsed["path"]
        versions = (
            ("format_version", parsed.get("format_version", 1), LOG_FORMAT_VERSION),
            ("schema_version", parsed.get("schema_version", 1), LOG_SCHEMA_VERSION),
        )
        version_error = next(
            (
                f"invalid or future {field}: {value!r}"
                for field, value, current in versions
                if isinstance(value, bool)
                or not isinstance(value, int)
                or value < 1
                or value > current
            ),
            None,
        )
        if version_error:
            entry["unresolved_reason"] = version_error
            continue
        integrity_bound = (
            parsed.get("format_version", 1) >= LOG_FORMAT_VERSION
            or parsed.get("schema_version", 1) >= LOG_SCHEMA_VERSION
        )
        if integrity_bound:
            if not _is_current_record_valid(parsed, sha256_file(body_path)):
                entry["unresolved_reason"] = (
                    "current integrity-bound record is invalid or tampered"
                )
                continue
            if normalized != parsed.get("status"):
                entry["unresolved_reason"] = (
                    "current integrity-bound status mapping is not identity-preserving"
                )
                continue
        grouped.setdefault(parsed["path"], []).append(row)
    return row_plans, grouped


def select_canonical_sources(
    root: Path,
    grouped: dict[str, list[dict[str, Any]]],
    row_plans: dict[int, dict[str, Any]],
    markdown_by_path: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select one deterministic canonical row per indexed Markdown path."""

    canonical_sources: list[dict[str, Any]] = []
    for path, candidates in sorted(grouped.items()):
        inventory_entry = markdown_by_path.get(path)
        if inventory_entry is None:
            for candidate in candidates:
                row_plans[candidate["source_line"]]["unresolved_reason"] = (
                    "indexed Markdown is absent from inventory"
                )
            continue
        body_sha = inventory_entry["body_sha256"]
        if len(candidates) > 1 and any(
            candidate["parsed"].get("format_version") == LOG_FORMAT_VERSION
            or candidate["parsed"].get("schema_version") == LOG_SCHEMA_VERSION
            for candidate in candidates
        ):
            for candidate in candidates:
                row_plans[candidate["source_line"]]["unresolved_reason"] = (
                    "duplicate current integrity-bound path requires separate governed resolution"
                )
            continue
        metadata = _body_metadata(root / path)
        body_text = _body_text_for_matching(root / path)
        scored = [
            (_candidate_score(candidate["parsed"], body_sha, metadata, body_text), candidate)
            for candidate in candidates
        ]
        scored = [(score, candidate) for score, candidate in scored if score is not None]
        if not scored:
            for candidate in candidates:
                row_plans[candidate["source_line"]]["unresolved_reason"] = (
                    "declared body integrity does not match Markdown"
                )
            continue
        best_score = max(score for score, _ in scored)
        winners = [candidate for score, candidate in scored if score == best_score]
        score_by_line = {
            candidate["source_line"]: list(score) for score, candidate in scored
        }
        if len(winners) > 1:
            if len({candidate["source_row_sha256"] for candidate in winners}) != 1:
                for candidate in candidates:
                    unresolved = row_plans[candidate["source_line"]]
                    unresolved.update(
                        unresolved_reason="duplicate path has a metadata tie or conflict",
                        duplicate_candidate_score=score_by_line.get(
                            candidate["source_line"]
                        ),
                        duplicate_selection_basis=(
                            "body_sha_log_metadata_content_token_score_v1"
                        ),
                    )
                continue
            winners.sort(key=lambda candidate: candidate["source_line"])
        canonical = winners[0]
        canonical_entry = row_plans[canonical["source_line"]]
        canonical_entry.update(
            classification="canonical_log",
            canonical_target_path=path,
            canonical_target_source_line=canonical["source_line"],
            disposition="bind_existing_body",
            unresolved_reason=None,
            duplicate_candidate_count=len(candidates),
            duplicate_candidate_score=score_by_line.get(canonical["source_line"]),
            duplicate_selection_basis=(
                "exact_row_bytes_equivalent"
                if len(winners) > 1
                else "body_sha_log_metadata_content_token_score_v1"
            ),
        )
        canonical_sources.append(canonical)
        for candidate in candidates:
            if candidate is canonical:
                continue
            alias = row_plans[candidate["source_line"]]
            if alias.get("unresolved_reason") and candidate not in winners:
                continue
            alias.update(
                classification="duplicate_alias",
                canonical_target_path=path,
                canonical_target_source_line=canonical["source_line"],
                disposition="retain_as_alias_evidence",
                unresolved_reason=None,
                duplicate_candidate_count=len(candidates),
                duplicate_candidate_score=score_by_line.get(candidate["source_line"]),
                duplicate_selection_basis=canonical_entry["duplicate_selection_basis"],
            )
    return canonical_sources
