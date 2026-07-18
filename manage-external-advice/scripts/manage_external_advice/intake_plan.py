"""Deterministic plan/apply publication for external-advice intake."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from .common import extract_fingerprint_claims, now_iso, rel_path, sha256_text, slugify
from .intake_plan_contract import (
    PLAN_KIND,
    PLAN_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    canonical_plan_output_path,
    canonical_bytes,
    opaque_source_snapshot_ref,
    publish_plan_file,
    regular_payload,
    sha256_bytes,
    source_snapshot_path,
    validate_intake_plan,
    workspace_path,
)
from .normalization import analyze_advice, advice_fidelity, classify_scope, normalize_text
from .source_metadata import opaque_source_id, safe_title
from .stable_store import read_regular
from .storage import (
    advice_root,
    event_bytes,
    find_exact_raw_digest,
    index_jsonl,
    index_md,
    merge_state,
    parse_events,
    publish_immutable,
    render_index_payload,
)


class IntakePlan(dict[str, Any]):
    """Canonical plan mapping with non-serializable source bytes for publication."""

    def __init__(self, value: dict[str, Any], source_payload: bytes) -> None:
        super().__init__(value)
        self.source_payload = source_payload


def _registry_snapshot_read_only(root: Path) -> tuple[bytes, list[dict[str, Any]]]:
    path = index_jsonl(root)
    payload = regular_payload(root, path, missing=b"")
    return payload, parse_events(payload, path) if payload else []


def _digest_or_none(payload: bytes) -> str | None:
    return sha256_bytes(payload) if payload else None


def _source_text(root: Path, source_ref: str, expected_sha256: str) -> str:
    source = workspace_path(root, source_ref)
    payload = regular_payload(root, source)
    if sha256_bytes(payload) != expected_sha256:
        raise SystemExit("External-advice intake source digest mismatch")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit("External-advice intake source must be valid UTF-8") from exc


def _fixed_stamp(timestamp: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit("Advice intake plan timestamp must be RFC3339") from exc
    if parsed.tzinfo is None:
        raise SystemExit("Advice intake plan timestamp must include a timezone")
    return parsed.strftime("%Y%m%d-%H%M%S")


def _unique_key(
    root: Path,
    events: list[dict[str, Any]],
    title: str,
    timestamp: str,
) -> tuple[str, str]:
    state = merge_state(events)
    base = f"{_fixed_stamp(timestamp)}-{slugify(title)}"
    candidate = base
    suffix = 2
    while (
        f"adv-{candidate}" in state
        or (advice_root(root) / "raw" / f"{candidate}.md").exists()
        or (advice_root(root) / "active" / f"{candidate}.md").exists()
    ):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return f"adv-{candidate}", f"{candidate}.md"


def _duplicate_result(raw_sha256: str, duplicate: dict[str, Any]) -> dict[str, Any]:
    return {
        "result_kind": "external_advice_intake_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "duplicate_exact_raw_source",
        "apply_status": "duplicate_noop",
        "raw_sha256": raw_sha256,
        "deduplicated": True,
        "mutation_performed": False,
        **duplicate,
    }


def exact_duplicate_result(root: Path, text: str) -> dict[str, Any] | None:
    raw_sha256 = sha256_text(text)
    duplicate = find_exact_raw_digest(root.resolve(), raw_sha256)
    return _duplicate_result(raw_sha256, duplicate) if duplicate else None


def _build_event(
    *,
    advice_id: str,
    plan_id: str,
    title: str,
    title_policy: str,
    priority: str,
    timestamp: str,
    raw_path: str,
    active_path: str,
    raw_sha256: str,
    normalized_sha256: str,
    source_id: str,
    text: str,
) -> dict[str, Any]:
    claims, directives, extraction_stats, directive_records = analyze_advice(
        text, raw_sha256
    )
    directive_ids = [record["directive_id"] for record in directive_records]
    if len(directive_ids) != len(set(directive_ids)):
        raise SystemExit("Duplicate explicit directive_id values in one raw advice source.")
    fidelity = advice_fidelity(claims, directives, extraction_stats)
    return {
        "event": "intake",
        "intake_plan_id": plan_id,
        "advice_id": advice_id,
        "type": "external_advice",
        "status": "active",
        "title": title,
        "path": active_path,
        "raw_source_path": raw_path,
        "source_label": source_id,
        "source_id": source_id,
        "source_label_policy": "opaque_content_id",
        "title_policy": title_policy,
        "priority": priority,
        "content_sha256": normalized_sha256,
        "raw_sha256": raw_sha256,
        "updated_at": timestamp,
        "fields": {
            "not_goal_truth": "true",
            "scope": classify_scope(text),
            "priority": priority,
            "fidelity_status": fidelity["fidelity_status"],
            "fidelity_reason": fidelity["fidelity_reason"],
            "raw_direct_reference_required": str(
                fidelity["raw_direct_reference_required"]
            ).lower(),
            "normalization_complete": str(fidelity["fidelity_status"] == "ok").lower(),
            "execution_plan_eligible": "false",
            "normalized_packet_use": (
                "direction_evidence_only"
                if fidelity["fidelity_status"] == "ok"
                else "warning_only_raw_review"
            ),
            "canonical_declaration_count": fidelity.get("canonical_declaration_count", 0),
            "reference_echo_count": fidelity.get("reference_echo_count", 0),
            "raw_direct_fallback_used": fidelity.get("raw_direct_fallback_used", False),
            "advice_metrics_stale": "unknown",
            "declared_output_fingerprints": extract_fingerprint_claims(text),
            "current_output_fingerprint": "unknown",
            "directives": directive_records,
            "semantic_dedup_policy": "explicit_directive_id_only",
        },
    }


def build_intake_plan(
    root: Path,
    text: str,
    title_value: str | None,
    priority: str,
    *,
    at: str | None = None,
    source_ref: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if priority not in {"low", "normal", "high"}:
        raise SystemExit("Unsupported external-advice priority")
    raw_sha256 = sha256_text(text)
    duplicate = exact_duplicate_result(root, text)
    if duplicate:
        return duplicate
    if not source_ref:
        raise SystemExit(
            "Advice intake planning requires a bounded workspace-relative source_ref"
        )
    transient_source = rel_path(root, workspace_path(root, source_ref))
    if _source_text(root, transient_source, raw_sha256) != text:
        raise SystemExit("External-advice intake source text does not match source_ref")
    bounded_source = opaque_source_snapshot_ref(raw_sha256)
    registry_before, events = _registry_snapshot_read_only(root)
    timestamp = at or now_iso()
    title, title_policy = safe_title(title_value, raw_sha256)
    advice_id, filename = _unique_key(root, events, title, timestamp)
    raw_path = f".agent_advice/raw/{filename}"
    active_path = f".agent_advice/active/{filename}"
    source_id = opaque_source_id(raw_sha256)
    normalized = normalize_text(
        advice_id,
        text,
        raw_path,
        title,
        priority,
        raw_sha256,
        source_id=source_id,
        received_at=timestamp,
        normalized_at=timestamp,
    )
    identity = {
        "advice_id": advice_id,
        "created_at": timestamp,
        "raw_sha256": raw_sha256,
        "registry_before_sha256": sha256_bytes(registry_before),
    }
    plan_id = f"intake-{sha256_bytes(canonical_bytes(identity))[:32]}"
    event = _build_event(
        advice_id=advice_id,
        plan_id=plan_id,
        title=title,
        title_policy=title_policy,
        priority=priority,
        timestamp=timestamp,
        raw_path=raw_path,
        active_path=active_path,
        raw_sha256=raw_sha256,
        normalized_sha256=sha256_text(normalized),
        source_id=source_id,
        text=text,
    )
    registry_after = registry_before
    if registry_after and not registry_after.endswith(b"\n"):
        registry_after += b"\n"
    registry_after += event_bytes(event)
    markdown_before = regular_payload(root, index_md(root), missing=b"")
    markdown_after = render_index_payload(merge_state([*events, event]), timestamp)
    body: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_kind": PLAN_KIND,
        "plan_id": plan_id,
        "advice_id": advice_id,
        "created_at": timestamp,
        "raw": {
            "source_ref": bounded_source,
            "path": raw_path,
            "sha256": raw_sha256,
        },
        "normalized": {
            "path": active_path,
            "sha256": sha256_text(normalized),
        },
        "metadata": {
            "title": title,
            "title_policy": title_policy,
            "priority": priority,
            "source_id": source_id,
        },
        "event_sha256": sha256_bytes(canonical_bytes(event)),
        "registry": {
            "path": ".agent_advice/index.jsonl",
            "before_sha256": sha256_bytes(registry_before),
            "after_sha256": sha256_bytes(registry_after),
            "before_size": len(registry_before),
        },
        "markdown": {
            "path": ".agent_advice/index.md",
            "before_sha256": _digest_or_none(markdown_before),
            "after_sha256": sha256_bytes(markdown_after),
        },
    }
    plan = {**body, "plan_sha256": sha256_bytes(canonical_bytes(body))}
    return IntakePlan(plan, text.encode("utf-8"))


def publish_intake_plan(
    root: Path, plan: dict[str, Any], output: str | Path | None = None
) -> dict[str, Any]:
    if plan.get("plan_kind") != PLAN_KIND:
        return plan
    root = root.resolve()
    validate_intake_plan(plan)
    snapshot = source_snapshot_path(
        root, plan["raw"]["sha256"], ensure_parent=True
    )
    snapshot_payload = read_regular(
        root, snapshot, missing=None, label="Advice intake source snapshot"
    )
    snapshot_existed = snapshot_payload is not None
    source_payload = getattr(plan, "source_payload", None)
    if not snapshot_existed and not isinstance(source_payload, bytes):
        raise SystemExit(
            "Advice intake source snapshot publication requires transient source bytes"
        )
    if isinstance(source_payload, bytes):
        if sha256_bytes(source_payload) != plan["raw"]["sha256"]:
            raise SystemExit("Advice intake transient source bytes changed")
        snapshot_created = publish_immutable(root, snapshot, source_payload)
    elif sha256_bytes(snapshot_payload) != plan["raw"]["sha256"]:
        raise SystemExit("Advice intake source snapshot digest mismatch")
    else:
        snapshot_created = False
    path = canonical_plan_output_path(
        root,
        output
        or f".agent_advice/journal/intake/{plan['plan_id']}.plan.json",
    )
    created, file_sha256 = publish_plan_file(root, path, plan)
    return {
        "result_kind": "external_advice_intake_plan_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "planned" if created else "already_planned",
        "plan_id": plan["plan_id"],
        "advice_id": plan["advice_id"],
        "plan_ref": rel_path(root, path),
        "plan_sha256": plan["plan_sha256"],
        "plan_content_sha256": sha256_bytes(canonical_bytes(plan)),
        "plan_file_sha256": file_sha256,
        "source_snapshot_ref": plan["raw"]["source_ref"],
        "source_snapshot_sha256": plan["raw"]["sha256"],
        "source_snapshot_created": snapshot_created,
        "mutation_performed": created or snapshot_created,
    }


def apply_intake_plan(root: Path, path_value: str | Path) -> dict[str, Any]:
    from .intake_apply import apply_intake_plan as apply

    return apply(root, path_value)


def verify_intake_plan(root: Path, path_value: str | Path) -> dict[str, Any]:
    """Read-only verification for a published immutable intake plan."""

    from .intake_verify import verify_intake_plan as verify

    return verify(root, path_value)
