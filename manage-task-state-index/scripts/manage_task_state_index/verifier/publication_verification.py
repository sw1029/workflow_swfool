"""Verify publication surfaces against independent document reconstruction."""

from __future__ import annotations

from typing import Any

from .core import _canonical_json, _require, _sha256
from .correction_evidence import _anchor_event
from .graph_contracts import JOURNAL_KEYS, MARKER_KEYS, PREPARE_KEYS
from .projection_evidence import _render_markdown
from .publication_documents import (
    _journal_document,
    _marker_document,
    _prepare_document,
    _receipt_document,
)

def _verify_publication(
    bundle: dict[str, Any], rebuilt: dict[str, Any], expected_recovery_status: str
) -> dict[str, Any]:
    _require(expected_recovery_status in {"not_required", "forward_completed"}, "caller recovery expectation is invalid")
    plan, receipt = rebuilt["plan"], bundle["receipt"]
    publication_recovery_status = receipt.get("recovery_status")
    _require(
        publication_recovery_status in {"not_required", "forward_completed"},
        "receipt recovery state is invalid",
    )
    plan_sha = bundle["plan_sha256"]
    prepare = _prepare_document(plan, plan_sha)
    prepare_payload = _canonical_json(prepare)
    _require(set(bundle["prepare_journal"]) == PREPARE_KEYS and bundle["refs"]["prepare_journal"][1] == prepare_payload, "prepare journal differs from independent reconstruction")
    placeholder = _anchor_event(plan, "0" * 64, "0" * 64, "0" * 64)
    rendered = _render_markdown(rebuilt["normalized"] + rebuilt["corrections"] + [plan["seal"]["event"], placeholder], plan["effective_at"])
    _require(bundle["refs"]["rendered_index"][1] == rendered, "rendered migration snapshot differs from independent projection")
    render_sha = _sha256(rendered)
    committed_at = receipt.get("transaction_committed_at")
    _require(isinstance(committed_at, str) and committed_at and receipt.get("transaction_started_at") == committed_at, "receipt completion time is malformed")
    journal = _journal_document(
        prepare, plan, committed_at, render_sha, publication_recovery_status,
    )
    journal_payload = _canonical_json(journal)
    _require(set(bundle["journal"]) == JOURNAL_KEYS and bundle["refs"]["journal"][1] == journal_payload, "committed journal differs from independent reconstruction")
    marker = _marker_document(
        plan, _sha256(prepare_payload), _sha256(journal_payload), render_sha,
        publication_recovery_status, committed_at, plan_sha,
    )
    marker_payload = _canonical_json(marker)
    _require(set(bundle["completion_marker"]) == MARKER_KEYS and bundle["refs"]["completion_marker"][1] == marker_payload, "completion marker differs from independent reconstruction")
    expected_receipt = _receipt_document(
        plan, rebuilt, plan_sha, _sha256(prepare_payload), _sha256(journal_payload),
        _sha256(marker_payload), render_sha, publication_recovery_status,
        committed_at,
    )
    _require(receipt == expected_receipt and bundle["receipt_payload"] == _canonical_json(expected_receipt), "receipt differs from independent reconstruction")
    return {"prepare_sha": _sha256(prepare_payload), "journal_sha": _sha256(journal_payload),
            "marker_sha": _sha256(marker_payload), "render_sha": render_sha,
            "receipt_sha": _sha256(bundle["receipt_payload"]), "plan_sha": plan_sha,
            "recovery_status": publication_recovery_status}

def _phase_receipt_sha256(
    rebuilt: dict[str, Any],
    publication: dict[str, Any],
    observation: dict[str, Any] | None,
) -> str | None:
    if not isinstance(observation, dict) or not observation.get("receipt_present"):
        return None
    recovery_status = observation.get("receipt_recovery_status")
    committed_at = observation.get("receipt_committed_at")
    _require(
        recovery_status in {"not_required", "forward_completed"}
        and isinstance(committed_at, str)
        and bool(committed_at),
        "pre-recovery receipt identity is invalid",
    )
    plan = rebuilt["plan"]
    plan_sha = publication["plan_sha"]
    render_sha = publication["render_sha"]
    prepare = _prepare_document(plan, plan_sha)
    prepare_sha = _sha256(_canonical_json(prepare))
    journal = _journal_document(
        prepare, plan, committed_at, render_sha, recovery_status,
    )
    journal_sha = _sha256(_canonical_json(journal))
    marker = _marker_document(
        plan, prepare_sha, journal_sha, render_sha, recovery_status,
        committed_at, plan_sha,
    )
    receipt = _receipt_document(
        plan, rebuilt, plan_sha, prepare_sha, journal_sha,
        _sha256(_canonical_json(marker)), render_sha, recovery_status,
        committed_at,
    )
    return _sha256(_canonical_json(receipt))
