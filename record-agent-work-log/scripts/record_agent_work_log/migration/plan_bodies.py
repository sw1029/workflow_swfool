"""Body-alias and orphan resolution stages for migration planning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..integrity import LOG_FORMAT_VERSION, LOG_SCHEMA_VERSION
from .classification import _body_metadata, _body_text_for_matching, _candidate_score


def deduplicate_body_aliases(
    root: Path,
    canonical_sources: list[dict[str, Any]],
    row_plans: dict[int, dict[str, Any]],
    markdown_by_path: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str]]:
    """Keep one canonical source for identical bodies at distinct paths."""

    canonical_by_body: dict[str, list[dict[str, Any]]] = {}
    for source in canonical_sources:
        path = row_plans[source["source_line"]]["source_path"]
        assert isinstance(path, str)
        canonical_by_body.setdefault(markdown_by_path[path]["body_sha256"], []).append(
            source
        )
    body_alias_paths: set[str] = set()
    retained_sources: list[dict[str, Any]] = []
    for body_sha, candidates in sorted(canonical_by_body.items()):
        if len(candidates) == 1:
            retained_sources.append(candidates[0])
            continue
        if any(
            candidate["parsed"].get("format_version") == LOG_FORMAT_VERSION
            or candidate["parsed"].get("schema_version") == LOG_SCHEMA_VERSION
            for candidate in candidates
        ):
            for candidate in candidates:
                row_plans[candidate["source_line"]].update(
                    classification="unresolved",
                    disposition="block",
                    unresolved_reason=(
                        "duplicate current integrity-bound content_id requires separate governed resolution"
                    ),
                )
            retained_sources.extend(candidates)
            continue
        ranked: list[tuple[tuple[int, ...], str, str, dict[str, Any]]] = []
        for candidate in candidates:
            entry = row_plans[candidate["source_line"]]
            path = entry["source_path"]
            assert isinstance(path, str)
            score = _candidate_score(
                candidate["parsed"],
                body_sha,
                _body_metadata(root / path),
                _body_text_for_matching(root / path),
            )
            ranked.append(
                (score or tuple(), path, candidate["source_row_sha256"], candidate)
            )
        ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        canonical = ranked[0][3]
        canonical_entry = row_plans[canonical["source_line"]]
        canonical_path = canonical_entry["source_path"]
        canonical_entry.update(
            body_alias_selection_basis=(
                "body_sha_log_metadata_content_token_score_then_path_hash_v1"
            ),
            body_alias_candidate_count=len(candidates),
        )
        retained_sources.append(canonical)
        for alias_score, alias_path, _, alias in ranked[1:]:
            row_plans[alias["source_line"]].update(
                classification="duplicate_alias",
                canonical_target_path=canonical_path,
                canonical_target_source_line=canonical["source_line"],
                disposition="retain_as_alias_evidence",
                unresolved_reason=None,
                alias_reason="byte_identical_body_different_path",
                body_alias_candidate_score=list(alias_score),
                body_alias_selection_basis=canonical_entry[
                    "body_alias_selection_basis"
                ],
            )
            body_alias_paths.add(alias_path)
    return retained_sources, body_alias_paths


def build_body_resolutions(
    inventory: dict[str, Any],
    grouped: dict[str, list[dict[str, Any]]],
    canonical_sources: list[dict[str, Any]],
    row_plans: dict[int, dict[str, Any]],
    markdown_by_path: dict[str, dict[str, Any]],
    body_alias_paths: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Classify every Markdown body as canonical, import, alias, or blocked."""

    orphan_entries = [
        {
            "path": item["path"],
            "body_sha256": item["body_sha256"],
            "size": item["size"],
            "disposition": "bind_as_legacy_import",
            "structured_fields_status": "not_evaluated",
        }
        for item in inventory["markdown"]
        if item["path"] not in set(grouped)
    ]
    canonical_body_targets: dict[str, str] = {}
    for source in canonical_sources:
        path = row_plans[source["source_line"]]["source_path"]
        assert isinstance(path, str)
        canonical_body_targets[markdown_by_path[path]["body_sha256"]] = path
    for orphan in sorted(orphan_entries, key=lambda item: item["path"]):
        target = canonical_body_targets.get(orphan["body_sha256"])
        if target is None:
            canonical_body_targets[orphan["body_sha256"]] = orphan["path"]
            continue
        orphan.update(
            disposition="quarantine_nonlog_body",
            canonical_target_path=target,
            alias_reason="byte_identical_body_different_path",
        )
        body_alias_paths.add(orphan["path"])
    canonical_paths = {
        row_plans[source["source_line"]]["source_path"]
        for source in canonical_sources
    }
    orphan_paths = {
        item["path"]
        for item in orphan_entries
        if item["disposition"] == "bind_as_legacy_import"
    }
    quarantined_orphans = {
        item["path"]
        for item in orphan_entries
        if item["disposition"] == "quarantine_nonlog_body"
    }
    body_resolutions: list[dict[str, Any]] = []
    for item in inventory["markdown"]:
        path = item["path"]
        if path in canonical_paths:
            disposition = "bind_existing_body"
        elif path in orphan_paths:
            disposition = "bind_as_legacy_import"
        elif path in body_alias_paths:
            disposition = (
                "quarantine_nonlog_body"
                if path in quarantined_orphans
                else "retain_as_alias_evidence"
            )
        else:
            disposition = "block"
        body_resolutions.append(
            {
                "path": path,
                "body_sha256": item["body_sha256"],
                "size": item["size"],
                "disposition": disposition,
            }
        )
    return orphan_entries, body_resolutions
