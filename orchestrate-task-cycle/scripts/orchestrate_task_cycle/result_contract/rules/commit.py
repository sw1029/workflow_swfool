from __future__ import annotations

import hashlib
import json

from ..base import RuleContext, TargetContractRule
from ..common import add, has_value, value_for


COMMIT_STATUSES = {
    "blocked",
    "committed",
    "created",
    "failed",
    "not_applicable",
    "passed",
    "skipped",
    "success",
}


class CommitRule(TargetContractRule):
    """Validate implementation and closeout commit evidence."""

    targets = frozenset({'closeout_commit', 'commit'})

    def check(self, context: RuleContext) -> None:
        target = context.target
        result = context.result
        mode = context.mode
        findings = context.findings
        commit_hash = has_value(result, "commit_hash")
        commit_subject = has_value(result, "commit_subject")
        skipped_reason = has_value(result, "commit_skipped_reason")
        status = str(value_for(result, "commit_status") or value_for(result, "status") or "").lower()
        role = str(value_for(result, "commit_role") or value_for(result, "role") or "").lower()
        expected_role = "closeout" if target == "closeout_commit" else "implementation"
        if role and role != expected_role:
            add(findings, "block" if mode == "block" else "warn", "commit_role_mismatch", f"`{target}` expected `commit_role: {expected_role}`.", {"commit_role": role})
        if status and status not in COMMIT_STATUSES:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "unknown_commit_status",
                "Commit status must use the documented closed lifecycle vocabulary.",
                {"commit_status": status, "allowed": sorted(COMMIT_STATUSES)},
            )
        if status in {"created", "committed", "success", "passed"} and not commit_hash:
            add(findings, "block" if mode == "block" else "warn", "commit_hash_missing", "Created commit result is missing `commit_hash`.")
        if status in {"created", "committed", "success", "passed"} and not commit_subject:
            add(findings, "block" if mode == "block" else "warn", "commit_subject_missing", "Created commit result is missing `commit_subject`.")
        if status in {"skipped", "not_applicable", "blocked", "failed"} and not skipped_reason:
            add(findings, "block" if mode == "block" else "warn", "commit_skipped_reason_missing", "Skipped/blocked commit result is missing `commit_skipped_reason`.")
        anchor = value_for(result, "settlement_anchor_path")
        verification = value_for(result, "settlement_verification")
        if target == "closeout_commit" and (anchor is not None or verification is not None):
            if not isinstance(anchor, str) or not anchor.strip():
                add(
                    findings,
                    "block",
                    "settlement_anchor_missing",
                    "Embedded closeout verification requires its exact anchor path.",
                )
            fields = {
                "contract_id",
                "settlement_id",
                "commit_oid",
                "terminal",
                "tracked_post_commit_receipt_required",
                "verification_sha256",
            }
            valid = isinstance(verification, dict) and set(verification) == fields
            if valid:
                material = {
                    key: verification[key]
                    for key in verification
                    if key != "verification_sha256"
                }
                expected = hashlib.sha256(
                    json.dumps(
                        material,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                ).hexdigest()
                valid = (
                    verification["contract_id"]
                    == "git_embedded_settlement_verification@v1"
                    and verification["terminal"] is True
                    and verification[
                        "tracked_post_commit_receipt_required"
                    ]
                    is False
                    and verification["commit_oid"] == value_for(
                        result, "commit_hash"
                    )
                    and verification["verification_sha256"] == expected
                )
            if not valid:
                add(
                    findings,
                    "block",
                    "settlement_verification_invalid",
                    "Closeout settlement verification is missing, altered, or bound to another commit.",
                )
