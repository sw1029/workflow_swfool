"""Independent source classification and record reconstruction."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from agent_log_migration_verifier_core import (
    ALLOWED_CLASSIFICATIONS,
    CURRENT_STATUSES,
    _body_metadata,
    _body_text,
    _candidate_score,
    _canonical_json,
    _expected_record_id,
    _is_current_record,
    _is_int,
    _records,
    _require,
    _sha256,
    _source_rows,
    _status_mappings,
)


ROW_BASE_KEYS = frozenset(
    "source_line source_row_sha256 original_status source_path source_body_sha256 classification normalized_status status_mapping_reason canonical_target_path canonical_target_source_line disposition unresolved_reason".split()
)
ROW_DUPLICATE_KEYS = frozenset(
    {"duplicate_candidate_count", "duplicate_candidate_score", "duplicate_selection_basis"}
)
ROW_BODY_CANONICAL_KEYS = frozenset(
    {"body_alias_selection_basis", "body_alias_candidate_count"}
)
ROW_BODY_ALIAS_KEYS = frozenset(
    {"alias_reason", "body_alias_candidate_score", "body_alias_selection_basis"}
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


def _verify_orphans(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    inventory_by_path: dict[str, dict[str, Any]],
    path_rows: dict[str, list[dict[str, Any]]],
    canonical_by_line: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    orphans = plan.get("orphans")
    _require(
        isinstance(orphans, list) and orphans == manifest.get("orphans"),
        "plan and manifest orphan inventories differ",
    )
    _require(
        orphans
        == sorted(
            orphans,
            key=lambda entry: entry.get("path", "") if isinstance(entry, dict) else "",
        ),
        "orphan inventory order is not independently reproducible",
    )
    orphan_by_path = {
        entry.get("path"): entry for entry in orphans if isinstance(entry, dict)
    }
    _require(len(orphan_by_path) == len(orphans), "orphan inventory has duplicate paths")
    _require(
        set(orphan_by_path) == set(inventory_by_path) - set(path_rows),
        "orphan disposition is missing or stale",
    )
    targets = {
        inventory_by_path[entry["source_path"]]["body_sha256"]: entry["source_path"]
        for entry in canonical_by_line.values()
    }
    for path in sorted(orphan_by_path):
        entry = orphan_by_path[path]
        inventory_entry = inventory_by_path[path]
        _require(
            entry.get("body_sha256") == inventory_entry.get("body_sha256")
            and _is_int(entry.get("size"))
            and entry.get("size") == inventory_entry.get("size"),
            f"orphan body binding mismatch: {path}",
        )
        _require(
            entry.get("structured_fields_status") == "not_evaluated",
            f"orphan structured-fields status mismatch: {path}",
        )
        target = targets.get(entry["body_sha256"])
        if target is None:
            _require(
                entry.get("disposition") == "bind_as_legacy_import"
                and entry.get("canonical_target_path") is None
                and set(entry)
                == {
                    "path",
                    "body_sha256",
                    "size",
                    "disposition",
                    "structured_fields_status",
                },
                f"independent orphan disposition mismatch: {path}",
            )
            targets[entry["body_sha256"]] = path
        else:
            _require(
                entry.get("disposition") == "quarantine_nonlog_body"
                and entry.get("canonical_target_path") == target
                and entry.get("alias_reason")
                == "byte_identical_body_different_path"
                and set(entry)
                == {
                    "path",
                    "body_sha256",
                    "size",
                    "disposition",
                    "structured_fields_status",
                    "canonical_target_path",
                    "alias_reason",
                },
                f"independent orphan disposition mismatch: {path}",
            )
    return orphans, orphan_by_path


def _verify_resolutions(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    inventory_by_path: dict[str, dict[str, Any]],
    path_rows: dict[str, list[dict[str, Any]]],
    orphan_by_path: dict[str, dict[str, Any]],
) -> None:
    resolutions = plan.get("body_resolutions")
    _require(
        isinstance(resolutions, list)
        and resolutions == manifest.get("markdown_resolutions"),
        "plan and manifest body resolutions differ",
    )
    _require(
        resolutions
        == sorted(
            resolutions,
            key=lambda entry: entry.get("path", "") if isinstance(entry, dict) else "",
        ),
        "body resolution order is not independently reproducible",
    )
    by_path = {
        entry.get("path"): entry for entry in resolutions if isinstance(entry, dict)
    }
    _require(len(by_path) == len(resolutions), "body resolutions have duplicate paths")
    _require(set(by_path) == set(inventory_by_path), "body resolution accounting is incomplete")
    for path, resolution in by_path.items():
        source = inventory_by_path[path]
        _require(
            set(resolution) == {"path", "body_sha256", "size", "disposition"}
            and resolution.get("body_sha256") == source.get("body_sha256")
            and _is_int(resolution.get("size"))
            and resolution.get("size") == source.get("size"),
            f"body resolution drift: {path}",
        )
        if path in orphan_by_path:
            expected = orphan_by_path[path]["disposition"]
        elif any(row["classification"] == "canonical_log" for row in path_rows[path]):
            expected = "bind_existing_body"
        else:
            expected = "retain_as_alias_evidence"
        _require(
            resolution.get("disposition") == expected,
            f"body resolution disposition mismatch: {path}",
        )


def _verified_counts(
    plan: dict[str, Any],
    manifest: dict[str, Any],
    plan_rows: list[dict[str, Any]],
    orphans: list[dict[str, Any]],
    counts: Counter[str],
) -> dict[str, int]:
    counts["orphan_markdown"] = len(orphans)
    counts["legacy_import_markdown"] = sum(
        entry["disposition"] == "bind_as_legacy_import" for entry in orphans
    )
    alias_paths = {
        entry["source_path"]
        for entry in plan_rows
        if entry.get("classification") == "duplicate_alias"
        and entry.get("source_path") != entry.get("canonical_target_path")
    }
    alias_paths.update(
        entry["path"]
        for entry in orphans
        if entry.get("disposition") == "quarantine_nonlog_body"
    )
    counts["body_alias_markdown"] = len(alias_paths)
    expected = dict(sorted(counts.items()))
    for observed, label in (
        (plan.get("classification_counts"), "plan"),
        (manifest.get("classification_counts"), "manifest"),
    ):
        _require(
            isinstance(observed, dict)
            and all(
                isinstance(key, str) and _is_int(value)
                for key, value in observed.items()
            ),
            f"{label} classification counts are malformed",
        )
        _require(observed == expected, f"{label} classification counts mismatch")
    _require(
        _is_int(plan.get("unresolved_count"))
        and plan["unresolved_count"] == 0
        and _is_int(manifest.get("unresolved_count"))
        and manifest["unresolved_count"] == 0,
        "unresolved migration cannot verify",
    )
    return expected


def _verify_rows_and_inventory(
    *,
    root: Path,
    source_payload: bytes,
    plan: dict[str, Any],
    manifest: dict[str, Any],
    status_map: dict[str, Any],
    actual_markdown: list[dict[str, Any]],
) -> dict[str, Any]:
    source_rows = _source_rows(source_payload)
    source_by_line = {row["source_line"]: row for row in source_rows}
    plan_rows = plan.get("rows")
    _require(isinstance(plan_rows, list), "plan rows are missing")
    _require(
        all(
            isinstance(entry, dict) and _is_int(entry.get("source_line"))
            for entry in plan_rows
        )
        and plan_rows == sorted(plan_rows, key=lambda entry: entry["source_line"]),
        "plan source-row order is not independently reproducible",
    )
    _require(len(plan_rows) == len(source_rows), "plan source-row accounting mismatch")
    _require(
        plan_rows == manifest.get("source_rows"),
        "plan and manifest source classifications differ",
    )
    inventory, inventory_by_path, actual_by_path = _prepare_inventory(
        manifest, actual_markdown
    )
    counts, path_rows = _verify_plan_rows(
        source_by_line,
        plan_rows,
        _status_mappings(status_map),
        inventory_by_path,
    )
    canonical = _recompute_canonical_rows(
        root, path_rows, source_by_line, inventory_by_path
    )
    orphans, orphan_by_path = _verify_orphans(
        plan, manifest, inventory_by_path, path_rows, canonical
    )
    _verify_resolutions(
        plan, manifest, inventory_by_path, path_rows, orphan_by_path
    )
    expected_counts = _verified_counts(
        plan, manifest, plan_rows, orphans, counts
    )
    inventory_basis = {
        "index_sha256": _sha256(source_payload),
        "index_size": len(source_payload),
        "source_row_count": len(source_rows),
        "markdown": inventory,
    }
    inventory_sha = _sha256(_canonical_json(inventory_basis))
    _require(
        plan.get("source_inventory_sha256") == inventory_sha
        and manifest.get("source_inventory_sha256") == inventory_sha,
        "source inventory hash mismatch",
    )
    _require(
        _is_int(plan.get("source_markdown_count"))
        and plan["source_markdown_count"] == len(inventory),
        "plan Markdown count mismatch",
    )
    return {
        "source_rows": source_rows,
        "inventory_sha256": inventory_sha,
        "inventory_by_path": inventory_by_path,
        "canonical_by_line": canonical,
        "orphans": orphans,
        "counts": expected_counts,
        "actual_markdown": actual_by_path,
    }


def _expected_committed_records(
    *,
    root: Path,
    migration_id: str,
    source_rows: list[dict[str, Any]],
    inventory_by_path: dict[str, dict[str, Any]],
    canonical_by_line: dict[int, dict[str, Any]],
    orphans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_by_line = {row["source_line"]: row for row in source_rows}

    def build(
        path: str,
        normalized_status: str,
        mapping_reason: str,
        original_status: str | None,
        source: dict[str, Any] | None,
        orphan: bool,
    ) -> dict[str, Any]:
        body_sha = inventory_by_path[path]["body_sha256"]
        parsed = source["parsed"] if source is not None else None
        if isinstance(parsed, dict) and _is_current_record(parsed, body_sha):
            return dict(parsed)
        metadata = _body_metadata(root / path)
        log_id = parsed.get("log_id") if isinstance(parsed, dict) else None
        if not isinstance(log_id, str) or not log_id:
            log_id = metadata.get("log_id")
        if not isinstance(log_id, str) or not log_id:
            log_id = "log-legacy-" + _sha256((path + "\0" + body_sha).encode("utf-8"))[:32]
        timestamp = parsed.get("timestamp") if isinstance(parsed, dict) else None
        if not isinstance(timestamp, str) or not timestamp:
            timestamp = metadata.get("timestamp") or "1970-01-01T00:00:00Z"
        title = parsed.get("title") if isinstance(parsed, dict) else None
        if not isinstance(title, str) or not title:
            title = metadata.get("title") or Path(path).stem
        record: dict[str, Any] = {
            "format_version": 3,
            "schema_version": 2,
            "log_id": log_id,
            "body_sha256": body_sha,
            "content_id": "log-content-" + body_sha[:32],
            "timestamp": timestamp,
            "status": normalized_status,
            "title": title,
            "path": path,
            "migration_id": migration_id,
            "legacy_import": True,
            "structured_fields_status": (
                "not_evaluated" if orphan else "source_index_limited"
            ),
            "original_status": original_status,
            "status_mapping_reason": mapping_reason,
            "status_evidence": (
                "not_evaluated" if original_status is None else "legacy_source_only"
            ),
            "source_line": source["source_line"] if source is not None else None,
            "source_row_sha256": (
                source["source_row_sha256"] if source is not None else None
            ),
            "historical_claims_upgraded": False,
        }
        record["record_id"] = _expected_record_id(record)
        return record

    records: list[dict[str, Any]] = []
    for line, plan_row in sorted(canonical_by_line.items()):
        source = source_by_line[line]
        records.append(
            build(
                plan_row["source_path"],
                plan_row["normalized_status"],
                plan_row["status_mapping_reason"],
                plan_row["original_status"],
                source,
                False,
            )
        )
    for orphan in orphans:
        if orphan.get("disposition") == "bind_as_legacy_import":
            records.append(
                build(
                    orphan["path"],
                    "informational",
                    "orphan_body_structure_not_evaluated",
                    None,
                    None,
                    True,
                )
            )
    seen_log_ids: set[str] = set()
    for record in records:
        log_id = record["log_id"]
        if log_id in seen_log_ids:
            record["original_log_id"] = log_id
            record["log_id"] = "log-legacy-" + _sha256(
                (record["path"] + "\0" + record["body_sha256"]).encode("utf-8")
            )[:32]
            record["record_id"] = _expected_record_id(record)
        seen_log_ids.add(record["log_id"])
    return records


def _verify_committed_records(
    *,
    root: Path,
    migration_id: str,
    prefix: bytes,
    plan: dict[str, Any],
    source_rows: list[dict[str, Any]],
    inventory_by_path: dict[str, dict[str, Any]],
    canonical_by_line: dict[int, dict[str, Any]],
    orphans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = _records(prefix)
    expected_rows = _expected_committed_records(
        root=root,
        migration_id=migration_id,
        source_rows=source_rows,
        inventory_by_path=inventory_by_path,
        canonical_by_line=canonical_by_line,
        orphans=orphans,
    )
    _require(rows == expected_rows, "committed records differ from independent source reconstruction")
    _require(
        prefix == b"".join(_canonical_json(record) for record in expected_rows),
        "committed prefix bytes differ from independent source reconstruction",
    )
    expected_paths = {entry["source_path"] for entry in canonical_by_line.values()}
    expected_paths.update(entry["path"] for entry in orphans if entry.get("disposition") == "bind_as_legacy_import")
    by_path = {row.get("path"): row for row in rows}
    _require(len(by_path) == len(rows), "committed index contains duplicate or missing paths")
    _require(set(by_path) == expected_paths, "committed index paths differ from independently resolved paths")
    status_by_path = {entry["source_path"]: entry["normalized_status"] for entry in canonical_by_line.values()}
    for orphan in orphans:
        if orphan.get("disposition") == "bind_as_legacy_import":
            status_by_path[orphan["path"]] = "informational"
    for path, record in by_path.items():
        _require(record.get("body_sha256") == inventory_by_path[path].get("body_sha256"), f"committed body hash mismatch: {path}")
        _require(record.get("status") == status_by_path[path], f"committed status mismatch: {path}")
        _require(record.get("historical_claims_upgraded") is not True, f"committed record upgrades historical claims: {path}")
        content_id = record.get("content_id")
        if record.get("content_id_scheme") is None:
            _require(content_id == "log-content-" + record["body_sha256"][:32], f"committed content ID mismatch: {path}")
        _require(record.get("record_id") == _expected_record_id(record), f"committed record ID mismatch: {path}")
    _require(len(rows) == plan.get("expected_after_row_count"), "committed row count differs from plan")
    return rows


def _verify_current_store(
    payload: bytes,
    actual_markdown: dict[str, dict[str, Any]],
    *,
    committed_row_count: int,
    migration_id: str,
) -> list[dict[str, Any]]:
    rows = _records(payload)
    unique_fields = ("log_id", "path", "content_id", "record_id")
    seen = {field: set() for field in unique_fields}
    for position, record in enumerate(rows, start=1):
        for field in ("timestamp", "status", "path"):
            _require(
                isinstance(record.get(field), str) and record[field].strip(),
                f"current index row {position} missing non-empty {field}",
            )
        _require(record.get("format_version") == 3, f"current index row {position} format version mismatch")
        _require(record.get("schema_version") == 2, f"current index row {position} schema version mismatch")
        _require(record.get("status") in CURRENT_STATUSES, f"current index row {position} status mismatch")
        _require(record.get("content_id_scheme") is None, f"current index row {position} content ID scheme is unsupported")
        if position <= committed_row_count:
            _require(record.get("migration_id") in {None, migration_id}, f"committed prefix row {position} migration identity mismatch")
        else:
            _require(record.get("migration_id") is None, f"migration-derived row appears after the sealed boundary at row {position}")
        path = record.get("path")
        relative = Path(path)
        _require(
            not relative.is_absolute()
            and path == relative.as_posix()
            and len(relative.parts) >= 3
            and relative.parts[0] == ".agent_log"
            and relative.suffix.lower() == ".md"
            and all(part not in {"", ".", ".."} for part in relative.parts),
            f"current index row {position} path is unsafe",
        )
        _require(isinstance(path, str) and path in actual_markdown, f"current index row {position} body is missing")
        _require(record.get("body_sha256") == actual_markdown[path].get("body_sha256"), f"current index row {position} body hash mismatch")
        _require(record.get("content_id") == "log-content-" + record["body_sha256"][:32], f"current index row {position} content ID mismatch")
        _require(record.get("record_id") == _expected_record_id(record), f"current index row {position} record ID mismatch")
        for field in unique_fields:
            value = record.get(field)
            _require(isinstance(value, str) and value and value not in seen[field], f"current index row {position} duplicate or missing {field}")
            seen[field].add(value)
    return rows
