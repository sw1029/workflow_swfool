"""Registry initialization and raw-to-normalized advice intake."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .common import (
    extract_fingerprint_claims,
    now_iso,
    read_title_from_text,
    rel_path,
    sha256_file,
)
from .normalization import (
    advice_fidelity,
    classify_scope,
    extract_claims_and_directives,
    normalize_text,
)
from .storage import (
    advice_root,
    append_event,
    ensure_dirs,
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
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2, sort_keys=True))

def cmd_intake(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    ensure_dirs(root)
    text, source_label = load_source(args.source)
    title = args.title or read_title_from_text(text, Path(source_label).stem if source_label != "stdin" else "external advice")
    advice_id, raw_name = unique_advice_key(root, title)
    raw_path = advice_root(root) / "raw" / raw_name
    raw_path.write_text(text, encoding="utf-8")
    claims, directives, extraction_stats = extract_claims_and_directives(text)
    fidelity = advice_fidelity(claims, directives, extraction_stats)
    declared_fingerprints = extract_fingerprint_claims(text)
    normalized = normalize_text(advice_id, text, rel_path(root, raw_path), title, args.priority)
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
        "source_label": source_label,
        "priority": args.priority,
        "content_sha256": sha256_file(active_path),
        "raw_sha256": sha256_file(raw_path),
        "updated_at": now_iso(),
        "fields": {
            "not_goal_truth": "true",
            "scope": classify_scope(text),
            "priority": args.priority,
            "fidelity_status": fidelity["fidelity_status"],
            "fidelity_reason": fidelity["fidelity_reason"],
            "raw_direct_reference_required": str(fidelity["raw_direct_reference_required"]).lower(),
            "advice_metrics_stale": "unknown",
            "declared_output_fingerprints": declared_fingerprints,
            "current_output_fingerprint": "unknown",
        },
    }
    append_event(root, event)
    result = rebuild_index(root)
    print(json.dumps({"status": "ok", "event": event, **result}, ensure_ascii=False, indent=2, sort_keys=True))
