"""Crash-safe, idempotent publication for one advice-container retirement."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Callable

from record_agent_work_log.integrity import (
    AgentLogIntegrityError,
    validate_store_for_append,
)

from .common import now_iso, rel_path, sha256_file, sha256_text
from .publication_journal import (
    JOURNAL_KIND,
    canonical as _canonical,
    digest as _digest,
    journal_path as _journal_path,
    matching_prepare as _matching_prepare,
    read_sealed as _read_sealed,
    sealed as _sealed,
    sealed_bytes as _sealed_bytes,
)
from .storage import (
    advice_root,
    atomic_replace,
    event_bytes,
    fsync_directory,
    index_jsonl,
    merge_state,
    publish_immutable,
    rebuild_index,
    registry_lock,
    registry_snapshot,
)


OPERATION_TAG_PREFIX = "advice-operation:"


def _safe_relative(root: Path, value: Any, label: str) -> tuple[str, Path]:
    raw = str(value or "").strip()
    candidate_rel = Path(raw)
    if not raw or candidate_rel.is_absolute() or ".." in candidate_rel.parts:
        raise SystemExit(f"Unsafe {label} path in advice publication: {raw!r}")
    candidate = root / candidate_rel
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"{label} path escapes workspace: {raw}") from exc
    return candidate_rel.as_posix(), candidate


def _regular_file(root: Path, value: Any, label: str) -> tuple[str, Path]:
    relative, candidate = _safe_relative(root, value, label)
    if candidate.is_symlink() or not candidate.is_file():
        raise SystemExit(f"{label} is not a regular workspace file: {relative}")
    return relative, candidate


def _applied_payload(source: Path) -> bytes:
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(
            f"Cannot read normalized advice source {source}: {exc}"
        ) from exc
    updated, count = re.subn(
        r"^- status:\s*active\s*$",
        "- status: applied",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit(
            "Normalized active advice must contain one active status line."
        )
    return updated.encode("utf-8")


def _request(
    advice_id: str,
    evidence: str,
    dispositions: list[dict[str, str]],
    note: str,
) -> dict[str, Any]:
    return {
        "advice_id": advice_id,
        "container_evidence": evidence,
        "directive_dispositions": sorted(
            dispositions, key=lambda row: row["directive_id"]
        ),
        "note": note,
    }


def _advice_revision(events: list[dict[str, Any]], advice_id: str) -> dict[str, Any]:
    rows = [event for event in events if event.get("advice_id") == advice_id]
    if not rows:
        raise SystemExit(f"Advice has no canonical source event: {advice_id}")
    return {
        "event_revision": len(rows),
        "event_digest": _digest(rows[-1]),
        "latest_event": rows[-1],
    }


def _destination(
    root: Path, source: Path, request_digest: str, applied_digest: str
) -> Path:
    primary = advice_root(root) / "applied" / source.name
    if not primary.exists() and not primary.is_symlink():
        return primary
    if primary.is_file() and not primary.is_symlink():
        if sha256_file(primary) == applied_digest:
            return primary
    return primary.with_name(f"{primary.stem}-{request_digest[:12]}{primary.suffix}")


def _new_prepare(
    root: Path,
    item: dict[str, Any],
    request: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    advice_id = str(item.get("advice_id") or "")
    if item.get("status") != "active":
        raise SystemExit(
            f"Advice is not active and cannot be marked applied: {advice_id}"
        )
    source_rel, source = _regular_file(root, item.get("path"), "active advice")
    observed_source_digest = sha256_file(source)
    expected_source_digest = str(item.get("content_sha256") or "")
    if not expected_source_digest or observed_source_digest != expected_source_digest:
        raise SystemExit(
            "Active advice content digest changed before mark-applied prepare."
        )
    revision = _advice_revision(events, advice_id)
    applied_payload = _applied_payload(source)
    applied_digest = sha256_text(applied_payload.decode("utf-8"))
    request_digest = _digest(request)
    destination = _destination(root, source, request_digest, applied_digest)
    applied_rel = rel_path(root, destination)
    operation_basis = {
        "kind": JOURNAL_KIND,
        "request_digest": request_digest,
        "expected_source": {
            "path": source_rel,
            "content_sha256": expected_source_digest,
            "event_revision": revision["event_revision"],
            "event_digest": revision["event_digest"],
        },
        "applied_artifact": {
            "path": applied_rel,
            "content_sha256": applied_digest,
        },
    }
    operation_digest = _digest(operation_basis)
    return _sealed(
        "prepare",
        {
            "operation_digest": operation_digest,
            "operation_basis": operation_basis,
            "request": request,
            "request_digest": request_digest,
            "prepared_at": now_iso(),
            "event_context": {
                "title": item.get("title"),
                "raw_source_path": item.get("raw_source_path"),
            },
        },
    )


def _operation_event(
    events: list[dict[str, Any]], prepare: dict[str, Any]
) -> dict[str, Any] | None:
    operation_digest = prepare["operation_digest"]
    matches = [
        event
        for event in events
        if event.get("event") == "mark_applied"
        and event.get("operation_digest") == operation_digest
    ]
    if len(matches) > 1:
        raise SystemExit(
            "Canonical advice registry contains a duplicate operation event."
        )
    if matches:
        advice_id = prepare["request"]["advice_id"]
        latest = _advice_revision(events, advice_id)["latest_event"]
        if latest is not matches[0]:
            raise SystemExit("The recovered mark-applied operation was superseded.")
        return matches[0]
    return None


def _verify_source_cas(
    root: Path, events: list[dict[str, Any]], prepare: dict[str, Any]
) -> bytes:
    expected = prepare["operation_basis"]["expected_source"]
    _source_rel, source = _regular_file(root, expected["path"], "active advice")
    if sha256_file(source) != expected["content_sha256"]:
        raise SystemExit("Active advice source CAS content digest mismatch.")
    revision = _advice_revision(events, prepare["request"]["advice_id"])
    if (
        revision["event_revision"] != expected["event_revision"]
        or revision["event_digest"] != expected["event_digest"]
    ):
        raise SystemExit("Active advice source CAS event revision/digest mismatch.")
    projected = merge_state(events)[prepare["request"]["advice_id"]]
    if (
        projected.get("status") != "active"
        or projected.get("path") != expected["path"]
        or projected.get("content_sha256") != expected["content_sha256"]
    ):
        raise SystemExit("Active advice source CAS projection mismatch.")
    payload = _applied_payload(source)
    if (
        sha256_text(payload.decode("utf-8"))
        != prepare["operation_basis"]["applied_artifact"]["content_sha256"]
    ):
        raise SystemExit("Prepared applied artifact digest cannot be reproduced.")
    return payload


def _verify_disposition_evidence(root: Path, prepare: dict[str, Any]) -> None:
    for row in prepare["request"]["directive_dispositions"]:
        reference, evidence_path = _regular_file(
            root, row.get("evidence_ref"), "directive disposition evidence"
        )
        if sha256_file(evidence_path) != row.get("evidence_sha256"):
            raise SystemExit(
                f"Directive disposition evidence CAS digest mismatch: {reference}"
            )


def _agent_log_record(root: Path, operation_digest: str) -> dict[str, Any] | None:
    index_path = root / ".agent_log" / "index.jsonl"
    if not index_path.is_file() or index_path.is_symlink():
        return None
    try:
        payload = index_path.read_bytes()
        records = validate_store_for_append(root, payload, index_path)
    except (OSError, AgentLogIntegrityError) as exc:
        raise SystemExit(f"Invalid agent-log store during recovery: {exc}") from exc
    tag = f"{OPERATION_TAG_PREFIX}{operation_digest}"
    matches = [record for record in records if tag in (record.get("tags") or [])]
    if len(matches) > 1:
        raise SystemExit("Multiple past_advice logs match one operation digest.")
    if not matches:
        return None
    record = matches[0]
    log_rel, log_path = _regular_file(root, record.get("path"), "past_advice log")
    if sha256_file(log_path) != record.get("body_sha256"):
        raise SystemExit("Recovered past_advice log body digest mismatch.")
    return {
        "path": log_rel,
        "body_sha256": record.get("body_sha256"),
        "record_id": record.get("record_id"),
    }


def _crash_point(name: str) -> None:
    """Test-only deterministic crash injection; never changes publication state."""

    if os.environ.get("MANAGE_EXTERNAL_ADVICE_CRASH_POINT") == name:
        raise RuntimeError(f"Injected mark-applied crash at {name}")


def _ensure_log(
    root: Path,
    item: dict[str, Any],
    prepare: dict[str, Any],
    log_writer: Callable[..., str],
) -> tuple[str, dict[str, Any]]:
    operation_digest = prepare["operation_digest"]
    receipt_path = _journal_path(root, operation_digest, "log")
    indexed = _agent_log_record(root, operation_digest)
    if receipt_path.exists() or receipt_path.is_symlink():
        receipt = _read_sealed(receipt_path, "log_receipt")
        if receipt.get("operation_digest") != operation_digest or indexed is None:
            raise SystemExit(
                "Past_advice log receipt cannot be recovered from its index."
            )
        if receipt.get("log") != indexed:
            raise SystemExit("Past_advice log receipt/index binding mismatch.")
        return indexed["path"], receipt
    if indexed is None:
        evidence_summary = _canonical(
            {
                "container_evidence": prepare["request"]["container_evidence"],
                "directive_dispositions": prepare["request"]["directive_dispositions"],
                "operation_digest": operation_digest,
            }
        )
        log_writer(
            root,
            item,
            evidence_summary,
            prepare["request"]["note"],
            operation_digest=operation_digest,
        )
        _crash_point("after_log")
        indexed = _agent_log_record(root, operation_digest)
        if indexed is None:
            raise SystemExit(
                "Past_advice writer did not publish an operation-bound log."
            )
    receipt = _sealed(
        "log_receipt",
        {"operation_digest": operation_digest, "log": indexed},
    )
    publish_immutable(root, receipt_path, _sealed_bytes(receipt))
    return indexed["path"], receipt


def _build_event(prepare: dict[str, Any], log_path: str) -> dict[str, Any]:
    request = prepare["request"]
    operation_basis = prepare["operation_basis"]
    expected = operation_basis["expected_source"]
    applied = operation_basis["applied_artifact"]
    dispositions = request["directive_dispositions"]
    return {
        "event": "mark_applied",
        "advice_id": request["advice_id"],
        "type": "external_advice",
        "status": "applied",
        "title": prepare["event_context"].get("title"),
        "path": applied["path"],
        "raw_source_path": prepare["event_context"].get("raw_source_path"),
        "applied_evidence": request["container_evidence"],
        "directive_dispositions": dispositions,
        "past_advice_log": log_path,
        "updated_at": prepare["prepared_at"],
        "content_sha256": applied["content_sha256"],
        "operation_digest": prepare["operation_digest"],
        "retirement_request_digest": prepare["request_digest"],
        "expected_source_revision": expected["event_revision"],
        "expected_source_event_digest": expected["event_digest"],
        "expected_source_content_sha256": expected["content_sha256"],
        "publication_state": "committed",
        "links": [{"rel": "applied_by", "id": log_path}],
        "fields": {
            "directive_states": {
                row["directive_id"]: row["disposition"] for row in dispositions
            },
            "container_lifecycle_separate_from_clause_state": True,
        },
    }


def _verify_event(
    event: dict[str, Any], prepare: dict[str, Any], log_path: str
) -> None:
    if event != _build_event(prepare, log_path):
        raise SystemExit(
            "Committed mark-applied event does not match its prepare journal."
        )


def _cleanup_source(root: Path, prepare: dict[str, Any]) -> str:
    expected = prepare["operation_basis"]["expected_source"]
    _relative, source = _safe_relative(root, expected["path"], "active advice")
    if not source.exists() and not source.is_symlink():
        return "already_absent"
    if source.is_symlink() or not source.is_file():
        raise SystemExit("Committed mark-applied source cleanup found an unsafe path.")
    if sha256_file(source) != expected["content_sha256"]:
        raise SystemExit(
            "mark-applied committed, but active-source cleanup CAS digest mismatched"
        )
    source.unlink()
    fsync_directory(source.parent)
    return "removed"


def _finalize(
    root: Path,
    prepare: dict[str, Any],
    event: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    operation_digest = prepare["operation_digest"]
    commit_path = _journal_path(root, operation_digest, "committed")
    if commit_path.exists() or commit_path.is_symlink():
        commit = _read_sealed(commit_path, "commit_receipt")
        if commit.get("operation_digest") != operation_digest or commit.get(
            "event_digest"
        ) != _digest(event):
            raise SystemExit("Mark-applied commit receipt binding mismatch.")
        result = rebuild_index(root)
        return commit, result
    cleanup = _cleanup_source(root, prepare)
    result = rebuild_index(root)
    commit = _sealed(
        "commit_receipt",
        {
            "operation_digest": operation_digest,
            "event_digest": _digest(event),
            "past_advice_log": event["past_advice_log"],
            "applied_artifact": prepare["operation_basis"]["applied_artifact"],
            "source_cleanup": cleanup,
        },
    )
    publish_immutable(root, commit_path, _sealed_bytes(commit))
    return commit, result


def publish_mark_applied(
    root: Path,
    item: dict[str, Any],
    dispositions: list[dict[str, str]],
    evidence: str,
    note: str,
    log_writer: Callable[..., str],
) -> dict[str, Any]:
    """Prepare artifacts, commit one canonical event last, and recover on retry."""

    advice_id = str(item.get("advice_id") or "")
    request = _request(advice_id, evidence, dispositions, note)
    request_digest = _digest(request)
    with registry_lock(root):
        from .intake_intent import assert_no_pending_intake_intents

        assert_no_pending_intake_intents(root)
        _payload, events = registry_snapshot(root)
        prepare = _matching_prepare(root, advice_id, request_digest)
        if prepare is None:
            prepare = _new_prepare(root, item, request, events)
            prepare_path = _journal_path(root, prepare["operation_digest"], "prepare")
            publish_immutable(root, prepare_path, _sealed_bytes(prepare))
            _crash_point("after_prepare")
        operation_digest = prepare["operation_digest"]
        operation_event = _operation_event(events, prepare)
        recovering_committed_event = operation_event is not None
        applied = prepare["operation_basis"]["applied_artifact"]
        _applied_rel, applied_path = _safe_relative(
            root, applied["path"], "applied advice"
        )
        if operation_event is None:
            applied_payload = _verify_source_cas(root, events, prepare)
            publish_immutable(root, applied_path, applied_payload)
            if sha256_file(applied_path) != applied["content_sha256"]:
                raise SystemExit("Staged applied advice digest mismatch.")
            _crash_point("after_applied_copy")
        elif sha256_file(applied_path) != applied["content_sha256"]:
            raise SystemExit("Committed applied advice artifact digest mismatch.")
        log_path, _log_receipt = _ensure_log(root, item, prepare, log_writer)
        if operation_event is None:
            payload, events = registry_snapshot(root)
            _verify_source_cas(root, events, prepare)
            _verify_disposition_evidence(root, prepare)
            operation_event = _operation_event(events, prepare)
            if operation_event is None:
                operation_event = _build_event(prepare, log_path)
                if payload and not payload.endswith(b"\n"):
                    payload += b"\n"
                atomic_replace(
                    root,
                    index_jsonl(root),
                    payload + event_bytes(operation_event),
                )
                _crash_point("after_event")
            else:
                _verify_event(operation_event, prepare, log_path)
        else:
            _verify_event(operation_event, prepare, log_path)
        commit, index_result = _finalize(root, prepare, operation_event)
        return {
            "status": "ok",
            "event": operation_event,
            "operation_digest": operation_digest,
            "publication_recovered": recovering_committed_event,
            "journal": {
                "prepare": rel_path(
                    root, _journal_path(root, operation_digest, "prepare")
                ),
                "log_receipt": rel_path(
                    root, _journal_path(root, operation_digest, "log")
                ),
                "commit_receipt": rel_path(
                    root, _journal_path(root, operation_digest, "committed")
                ),
            },
            **index_result,
        }


__all__ = ("publish_mark_applied",)
