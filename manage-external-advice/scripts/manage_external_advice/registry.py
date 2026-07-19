#!/usr/bin/env python3
"""Static CLI composition and stable import surface for external advice."""

from __future__ import annotations

import argparse

from .audit import cmd_audit
from .common import (
    bool_value,
    current_fingerprint_from_args,
    dead_root_cause_rows,
    extract_fingerprint_claims,
    extract_root_cause_claims,
    first_fingerprint_value,
    load_json_value,
    normalize_root_cause_slug,
    now_iso,
    read_jsonl,
    read_title_from_text,
    rel_path,
    sha256_file,
    sha256_text,
    slugify,
    stamp,
)
from .contracts import (
    ADVICE_DIR,
    CLAIM_LINE_RE,
    DIRECTIVE_LINE_RE,
    FINGERPRINT_CLAIM_RE,
    METADATA_LINE_RE,
    ROOT_CAUSE_CLAIM_RE,
    ROOT_CAUSE_LEDGER_REL_PATH,
    SENSITIVE_PATTERNS,
)
from .disposition_compiler import (
    cmd_compile_dispositions,
    cmd_render_disposition_template,
)
from .intake import cmd_init, cmd_intake, load_source
from .intake_plan import apply_intake_plan, build_intake_plan, publish_intake_plan
from .lifecycle import (
    cmd_defer,
    cmd_mark_applied,
    cmd_reject,
    find_item,
    move_item,
    update_advice_status,
    write_past_advice_log,
)
from .normalization import (
    advice_fidelity,
    bulletize,
    candidate_advice_lines,
    classify_scope,
    clean_advice_line,
    extract_claims_and_directives,
    normalize_text,
    normalized_line_set,
)
from .rendering import active_items, cmd_list, cmd_render_packet
from .storage import (
    advice_root,
    append_event,
    ensure_dirs,
    index_jsonl,
    index_md,
    load_events,
    merge_state,
    rebuild_index,
    unique_advice_key,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage .agent_advice non-GT external advice artifacts."
    )
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create .agent_advice directories and indexes.")
    init.set_defaults(func=cmd_init)

    intake = sub.add_parser(
        "intake",
        help="Preserve raw advice and create a normalized active advice document.",
    )
    intake.add_argument("--source", help="Markdown source path, or '-' for stdin.")
    intake.add_argument("--title", help="Human label for the advice.")
    intake.add_argument(
        "--priority", choices=("low", "normal", "high"), default="normal"
    )
    intake_mode = intake.add_mutually_exclusive_group()
    intake_mode.add_argument(
        "--plan",
        metavar="PATH",
        help="Publish a frozen immutable intake plan without applying it.",
    )
    intake_mode.add_argument(
        "--apply-plan",
        metavar="PATH",
        help="Apply an existing immutable intake plan; --source is not required.",
    )
    intake.add_argument(
        "--at",
        help="Fixed RFC3339 plan timestamp; primarily for deterministic orchestration.",
    )
    intake.add_argument(
        "--staging-ref",
        help="Existing workspace-relative UTF-8 source used when --source is stdin or outside the workspace.",
    )
    intake.set_defaults(func=cmd_intake)

    list_parser = sub.add_parser("list", help="List advice lifecycle entries.")
    list_parser.add_argument(
        "--status", choices=("active", "applied", "rejected", "deferred")
    )
    list_parser.set_defaults(func=cmd_list)

    packet = sub.add_parser("render-packet", help="Render active advice packet.")
    packet.add_argument("--format", choices=("markdown", "json"), default="markdown")
    packet.set_defaults(func=cmd_render_packet)

    disposition_template = sub.add_parser(
        "render-disposition-template",
        help="Render a fillable decision template for actionable directives.",
    )
    disposition_template.add_argument("--advice-id", required=True)
    disposition_template.set_defaults(func=cmd_render_disposition_template)

    compile_disposition = sub.add_parser(
        "compile-dispositions",
        help="Compile a compact directive decision map and derive evidence digests.",
    )
    compile_disposition.add_argument("--advice-id", required=True)
    compile_disposition.add_argument(
        "--decision-map",
        required=True,
        help="JSON text, '-', or a regular file keyed by directive ID.",
    )
    compile_disposition.set_defaults(func=cmd_compile_dispositions)

    applied = sub.add_parser(
        "mark-applied",
        help="Move active advice to applied and write a past_advice log.",
    )
    applied.add_argument("--advice-id", required=True)
    applied.add_argument(
        "--evidence",
        required=True,
        help="Path, ID, or concise evidence proving application/retirement.",
    )
    disposition_input = applied.add_mutually_exclusive_group(required=True)
    disposition_input.add_argument(
        "--directive-dispositions-json",
        help="JSON text or path covering every directive with disposition, evidence_ref, and evidence_sha256.",
    )
    disposition_input.add_argument(
        "--decision-map",
        help="Compact decision map; evidence SHA-256 values are derived locally.",
    )
    applied.add_argument("--note", default="")
    applied.set_defaults(func=cmd_mark_applied)

    reject = sub.add_parser("reject", help="Move active advice to rejected.")
    reject.add_argument("--advice-id", required=True)
    reject.add_argument("--reason", required=True)
    reject.set_defaults(func=cmd_reject)

    defer = sub.add_parser(
        "defer",
        help="Move active advice to deferred with a blocker or prerequisite reason.",
    )
    defer.add_argument("--advice-id", required=True)
    defer.add_argument("--reason", required=True)
    defer.set_defaults(func=cmd_defer)

    audit = sub.add_parser("audit", help="Audit advice registry consistency.")
    audit.add_argument(
        "--current-output-fingerprint",
        help="Current adapter/output fingerprint to compare against active advice claims.",
    )
    audit.add_argument(
        "--current-output-fingerprint-json",
        help="Path or JSON packet containing current_output_fingerprint or equivalent.",
    )
    audit.add_argument(
        "--root-cause-ledger-path",
        default=ROOT_CAUSE_LEDGER_REL_PATH,
        help="Root-cause ledger used to flag re-advised dead hypotheses.",
    )
    audit.set_defaults(func=cmd_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


__all__ = [
    "ADVICE_DIR",
    "CLAIM_LINE_RE",
    "DIRECTIVE_LINE_RE",
    "FINGERPRINT_CLAIM_RE",
    "METADATA_LINE_RE",
    "ROOT_CAUSE_CLAIM_RE",
    "ROOT_CAUSE_LEDGER_REL_PATH",
    "SENSITIVE_PATTERNS",
    "active_items",
    "apply_intake_plan",
    "advice_fidelity",
    "advice_root",
    "append_event",
    "bool_value",
    "build_intake_plan",
    "build_parser",
    "bulletize",
    "candidate_advice_lines",
    "classify_scope",
    "clean_advice_line",
    "cmd_audit",
    "cmd_defer",
    "cmd_init",
    "cmd_intake",
    "cmd_list",
    "cmd_mark_applied",
    "cmd_reject",
    "cmd_render_packet",
    "current_fingerprint_from_args",
    "dead_root_cause_rows",
    "ensure_dirs",
    "extract_claims_and_directives",
    "extract_fingerprint_claims",
    "extract_root_cause_claims",
    "find_item",
    "first_fingerprint_value",
    "index_jsonl",
    "index_md",
    "load_events",
    "load_json_value",
    "load_source",
    "main",
    "merge_state",
    "move_item",
    "normalize_root_cause_slug",
    "normalize_text",
    "normalized_line_set",
    "now_iso",
    "read_jsonl",
    "read_title_from_text",
    "publish_intake_plan",
    "rebuild_index",
    "rel_path",
    "sha256_file",
    "sha256_text",
    "slugify",
    "stamp",
    "unique_advice_key",
    "update_advice_status",
    "write_past_advice_log",
]

if __name__ == "__main__":
    raise SystemExit(main())
