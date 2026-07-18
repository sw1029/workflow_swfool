"""Registry initialization and raw-to-normalized advice intake."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .common import (
    extract_fingerprint_claims,
    now_iso,
    rel_path,
    sha256_file,
    sha256_text,
)
from .normalization import (
    analyze_advice,
    advice_fidelity,
    classify_scope,
    normalize_text,
)
from .source_metadata import opaque_source_id, safe_title
from .storage import (
    advice_root,
    append_event,
    ensure_dirs,
    find_exact_raw_digest,
    rebuild_index,
    unique_advice_key,
)


def load_source(source: str) -> tuple[str, str]:
    if source == "-":
        text = sys.stdin.read()
        return text, "stdin"
    path = Path(source)
    text = path.read_text(encoding="utf-8", errors="replace")
    return text, str(path)


def cmd_init(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    ensure_dirs(root)
    result = rebuild_index(root)
    print(
        json.dumps(
            {"status": "ok", **result}, ensure_ascii=False, indent=2, sort_keys=True
        )
    )


def cmd_intake(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    text, _transient_source_locator = load_source(args.source)
    raw_sha256 = sha256_text(text)
    duplicate = find_exact_raw_digest(root, raw_sha256)
    if duplicate:
        print(
            json.dumps(
                {
                    "status": "duplicate_exact_raw_source",
                    "raw_sha256": raw_sha256,
                    "deduplicated": True,
                    **duplicate,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return
    source_id = opaque_source_id(raw_sha256)
    title, title_policy = safe_title(args.title, raw_sha256)
    claims, directives, extraction_stats, directive_records = analyze_advice(
        text, raw_sha256
    )
    directive_ids = [record["directive_id"] for record in directive_records]
    if len(directive_ids) != len(set(directive_ids)):
        raise SystemExit(
            "Duplicate explicit directive_id values in one raw advice source."
        )
    ensure_dirs(root)
    advice_id, raw_name = unique_advice_key(root, title)
    raw_path = advice_root(root) / "raw" / raw_name
    raw_path.write_text(text, encoding="utf-8")
    fidelity = advice_fidelity(claims, directives, extraction_stats)
    declared_fingerprints = extract_fingerprint_claims(text)
    normalized = normalize_text(
        advice_id,
        text,
        rel_path(root, raw_path),
        title,
        args.priority,
        raw_sha256,
        source_id=source_id,
    )
    active_path = advice_root(root) / "active" / raw_name
    active_path.write_text(normalized, encoding="utf-8")
    event = {
        "event": "intake",
        "advice_id": advice_id,
        "type": "external_advice",
        "status": "active",
        "title": title,
        "path": rel_path(root, active_path),
        "raw_source_path": rel_path(root, raw_path),
        "source_label": source_id,
        "source_id": source_id,
        "source_label_policy": "opaque_content_id",
        "title_policy": title_policy,
        "priority": args.priority,
        "content_sha256": sha256_file(active_path),
        "raw_sha256": raw_sha256,
        "updated_at": now_iso(),
        "fields": {
            "not_goal_truth": "true",
            "scope": classify_scope(text),
            "priority": args.priority,
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
            "canonical_declaration_count": fidelity.get(
                "canonical_declaration_count", 0
            ),
            "reference_echo_count": fidelity.get("reference_echo_count", 0),
            "raw_direct_fallback_used": fidelity.get("raw_direct_fallback_used", False),
            "advice_metrics_stale": "unknown",
            "declared_output_fingerprints": declared_fingerprints,
            "current_output_fingerprint": "unknown",
            "directives": directive_records,
            "semantic_dedup_policy": "explicit_directive_id_only",
        },
    }
    append_event(root, event)
    result = rebuild_index(root)
    print(
        json.dumps(
            {"status": "ok", "event": event, **result},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
