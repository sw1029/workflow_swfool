"""Marker, publication-binding, and live-index verification."""

from __future__ import annotations

from typing import Any

from .core import (
    SUPPORTED_TOOL_VERSIONS,
    _canonical_json,
    _current_prefix,
    _is_int,
    _load_json,
    _regular_file,
    _require,
    _sha256,
)

from .committed_evidence import _verify_committed_records, _verify_current_store


def _verify_marker(bundle: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    root = bundle["root"]
    receipt = bundle["receipt"]
    journal = bundle["journal"]
    plan_payload = bundle["refs"]["plan"][1]
    receipt_payload = bundle["receipt_payload"]
    journal_payload = bundle["journal_payload"]
    marker, payload = _load_json(
        root / ".agent_log" / "migrations" / "active.json",
        "publication marker",
    )
    tool_version = bundle["plan"].get("tool_version")
    _require(
        tool_version in SUPPORTED_TOOL_VERSIONS,
        "migration tool version is unsupported",
    )
    for document, label in (
        (receipt, "receipt"),
        (journal, "journal"),
        (marker, "marker"),
    ):
        _require(
            document.get("tool_version") == tool_version,
            f"{label} tool version mismatch",
        )
    expected = {
        "schema_version": 1,
        "kind": "agent_log_migration_commit_marker",
        "transaction_status": "committed",
        "migration_id": bundle["migration_id"],
        "tool_version": tool_version,
        "plan_sha256": _sha256(plan_payload),
        "receipt_ref": bundle["receipt_relative"],
        "receipt_sha256": _sha256(receipt_payload),
        "journal_ref": bundle["journal_path"].relative_to(root).as_posix(),
        "journal_sha256": _sha256(journal_payload),
        "after_index_sha256": journal.get("after_index_sha256"),
        "after_index_size": journal.get("after_index_size"),
    }
    _require(marker == expected, "publication marker is not the exact schema-v1 projection")
    _require(payload == _canonical_json(expected), "publication marker bytes are not canonical")
    return marker, payload

def _verify_publication_bindings(
    bundle: dict[str, Any],
    independent: dict[str, Any],
    marker: dict[str, Any],
) -> dict[str, Any]:
    root = bundle["root"]
    receipt = bundle["receipt"]
    journal = bundle["journal"]
    refs = bundle["refs"]
    bindings = {
        "source_index_sha256": _sha256(refs["source"][1]),
        "source_index_size": len(refs["source"][1]),
        "source_inventory_sha256": independent["inventory_sha256"],
        "source_snapshot_ref": refs["source"][0].relative_to(root).as_posix(),
        "source_snapshot_sha256": _sha256(refs["source"][1]),
        "status_map_ref": refs["status"][0].relative_to(root).as_posix(),
        "status_map_sha256": _sha256(refs["status"][1]),
        "plan_ref": refs["plan"][0].relative_to(root).as_posix(),
        "plan_sha256": _sha256(refs["plan"][1]),
        "manifest_ref": refs["manifest"][0].relative_to(root).as_posix(),
        "manifest_sha256": _sha256(refs["manifest"][1]),
        "staged_index_ref": bundle["staged_path"].relative_to(root).as_posix(),
        "after_index_sha256": bundle["plan"].get("expected_after_index_sha256"),
        "after_index_size": bundle["plan"].get("expected_after_index_size"),
        "after_row_count": bundle["plan"].get("expected_after_row_count"),
    }
    for field in ("source_index_size", "after_index_size", "after_row_count"):
        _require(_is_int(bindings[field]), f"plan/journal {field} is malformed")
    for field, expected in bindings.items():
        if _is_int(expected):
            _require(_is_int(journal.get(field)), f"journal {field} type mismatch")
        _require(journal.get(field) == expected, f"journal {field} binding mismatch")
    _require(
        journal.get("receipt_ref") == bundle["receipt_relative"]
        and journal.get("receipt_sha256") == _sha256(bundle["receipt_payload"]),
        "journal receipt binding mismatch",
    )
    _require(
        _is_int(receipt.get("after_index_size"))
        and _is_int(marker.get("after_index_size"))
        and receipt.get("after_index_sha256") == bindings["after_index_sha256"]
        and marker.get("after_index_sha256") == bindings["after_index_sha256"]
        and receipt["after_index_size"] == bindings["after_index_size"]
        and marker["after_index_size"] == bindings["after_index_size"],
        "publication after-index binding mismatch",
    )
    _require(
        _is_int(receipt.get("after_row_count"))
        and receipt["after_row_count"] == bindings["after_row_count"]
        and _is_int(receipt.get("before_row_count"))
        and receipt["before_row_count"] == len(independent["source_rows"]),
        "receipt row count mismatch",
    )
    count_bindings = {
        "canonicalized_count": "canonical_log",
        "legacy_import_count": "legacy_import_markdown",
        "duplicate_alias_count": "duplicate_alias",
        "body_alias_count": "body_alias_markdown",
        "foreign_event_count": "foreign_event",
        "orphan_count": "orphan_markdown",
        "unresolved_count": "unresolved",
    }
    for receipt_field, count_field in count_bindings.items():
        _require(
            _is_int(receipt.get(receipt_field))
            and receipt[receipt_field]
            == independent["counts"].get(count_field, 0),
            f"receipt {receipt_field} mismatch",
        )
    return bindings

def _verify_index_projection(
    bundle: dict[str, Any],
    independent: dict[str, Any],
    bindings: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    index_payload = _regular_file(
        bundle["root"] / ".agent_log" / "index.jsonl", "current index"
    ).read_bytes()
    prefix = _current_prefix(
        index_payload,
        bindings["after_index_size"],
        bindings["after_index_sha256"],
    )
    _require(
        bundle["staged_path"].read_bytes() == prefix,
        "staged index and committed prefix differ",
    )
    committed = _verify_committed_records(
        root=bundle["root"],
        migration_id=bundle["migration_id"],
        prefix=prefix,
        plan=bundle["plan"],
        source_rows=independent["source_rows"],
        inventory_by_path=independent["inventory_by_path"],
        canonical_by_line=independent["canonical_by_line"],
        orphans=independent["orphans"],
    )
    current = _verify_current_store(
        index_payload,
        independent["actual_markdown"],
        committed_row_count=len(committed),
        migration_id=bundle["migration_id"],
    )
    appended = {record["path"] for record in current[len(committed) :]}
    new_markdown = set(independent["actual_markdown"]) - set(
        independent["inventory_by_path"]
    )
    _require(
        appended == new_markdown,
        "post-migration Markdown/index accounting mismatch",
    )
    return committed, current
