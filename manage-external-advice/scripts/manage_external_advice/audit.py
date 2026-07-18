"""Audit active advice for integrity, freshness, and dead-hypothesis reuse."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .common import (
    current_fingerprint_from_args,
    dead_root_cause_rows,
    extract_fingerprint_claims,
    extract_root_cause_claims,
    rel_path,
)
from .contracts import ROOT_CAUSE_LEDGER_REL_PATH
from .storage import ensure_dirs, load_events, merge_state


def _dead_claim_index(
    dead_rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    dead_by_slug: dict[str, list[dict[str, Any]]] = {}
    for row in dead_rows:
        dead_by_slug.setdefault(str(row["hypothesized_root_cause"]), []).append(row)
    return dead_by_slug


def _audit_active_item(
    root: Path,
    item: dict[str, Any],
    current_output_fingerprint: str | None,
    dead_by_slug: dict[str, list[dict[str, Any]]],
    findings: list[dict[str, Any]],
    declared_claims: list[dict[str, Any]],
    stale_advice: list[dict[str, Any]],
    dead_hypothesis_claims: list[dict[str, Any]],
) -> None:
    path_value = item.get("path")
    text = (
        (root / str(path_value)).read_text(encoding="utf-8", errors="replace")
        if path_value and (root / str(path_value)).is_file()
        else ""
    )
    for claim in extract_root_cause_claims(text):
        matches = dead_by_slug.get(claim) or []
        if not matches:
            continue
        dead_claim = {
            "advice_id": item.get("advice_id"),
            "path": path_value,
            "hypothesized_root_cause": claim,
            "dead_ledger_rows": matches[:5],
        }
        dead_hypothesis_claims.append(dead_claim)
        findings.append(
            {
                "severity": "warn",
                "code": "re_advised_dead_hypothesis",
                "advice_id": item.get("advice_id"),
                "path": path_value,
                "message": "active advice re-supplies a root-cause hypothesis already attempted without terminal_outcome_changed; do not use it as fresh untried evidence without new input delta.",
                "evidence": dead_claim,
            }
        )
    declared_fingerprints = extract_fingerprint_claims(text)
    if declared_fingerprints:
        fingerprint_claim = {
            "advice_id": item.get("advice_id"),
            "path": path_value,
            "declared_output_fingerprints": declared_fingerprints,
        }
        declared_claims.append(fingerprint_claim)
        if (
            current_output_fingerprint
            and current_output_fingerprint not in declared_fingerprints
        ):
            stale_advice.append(fingerprint_claim)
            findings.append(
                {
                    "severity": "warn",
                    "code": "advice_metrics_stale",
                    "advice_id": item.get("advice_id"),
                    "path": path_value,
                    "message": "active advice declares output fingerprints that do not match the supplied current output fingerprint; refresh, defer, reject, or justify use against current evidence.",
                    "evidence": {
                        "current_output_fingerprint": current_output_fingerprint,
                        "declared_output_fingerprints": declared_fingerprints,
                    },
                }
            )
    if "not_goal_truth: true" not in text:
        findings.append(
            {
                "severity": "medium",
                "code": "missing_not_goal_truth",
                "advice_id": item.get("advice_id"),
            }
        )
    fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
    if (
        fields.get("fidelity_status") == "degenerate"
        or "fidelity_status: degenerate" in text
    ):
        findings.append(
            {
                "severity": "medium",
                "code": "advice_fidelity_degenerate",
                "advice_id": item.get("advice_id"),
            }
        )
    if "raw_direct_reference_required: true" in text and not item.get(
        "raw_source_path"
    ):
        findings.append(
            {
                "severity": "medium",
                "code": "raw_reference_required_but_missing",
                "advice_id": item.get("advice_id"),
            }
        )


def _ledger_path(
    root: Path, args: argparse.Namespace, dead_rows: list[dict[str, Any]]
) -> str:
    if dead_rows:
        return str(dead_rows[0]["path"])
    return rel_path(
        root,
        root
        / (getattr(args, "root_cause_ledger_path", None) or ROOT_CAUSE_LEDGER_REL_PATH),
    )


def cmd_audit(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    ensure_dirs(root)
    state = merge_state(load_events(root))
    findings: list[dict[str, Any]] = []
    current_output_fingerprint = current_fingerprint_from_args(root, args)
    declared_claims: list[dict[str, Any]] = []
    stale_advice: list[dict[str, Any]] = []
    dead_rows = dead_root_cause_rows(
        root, getattr(args, "root_cause_ledger_path", None)
    )
    dead_by_slug = _dead_claim_index(dead_rows)
    dead_hypothesis_claims: list[dict[str, Any]] = []
    for item in state.values():
        path_value = item.get("path")
        if (
            path_value
            and not (root / str(path_value)).exists()
            and item.get("status") != "deleted"
        ):
            findings.append(
                {
                    "severity": "high",
                    "code": "missing_path",
                    "advice_id": item.get("advice_id"),
                    "path": path_value,
                }
            )
        if item.get("status") == "active":
            _audit_active_item(
                root,
                item,
                current_output_fingerprint,
                dead_by_slug,
                findings,
                declared_claims,
                stale_advice,
                dead_hypothesis_claims,
            )
    active_count = sum(1 for item in state.values() if item.get("status") == "active")
    result = {
        "status": "ok"
        if not any(f["severity"] == "high" for f in findings)
        else "block",
        "active_count": active_count,
        "finding_count": len(findings),
        "findings": findings,
        "advice_freshness_gate": {
            "current_output_fingerprint": current_output_fingerprint or None,
            "declared_fingerprint_claims": declared_claims,
            "advice_metrics_stale": bool(stale_advice),
            "stale_advice": stale_advice,
            "re_advised_dead_hypothesis": bool(dead_hypothesis_claims),
            "dead_hypothesis_claims": dead_hypothesis_claims,
            "root_cause_ledger_path": _ledger_path(root, args, dead_rows),
            "status": "warn"
            if stale_advice or dead_hypothesis_claims
            else (
                "not_applicable"
                if not declared_claims and not dead_hypothesis_claims
                else "pass"
            ),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] == "block":
        raise SystemExit(2)
