from __future__ import annotations

from ..base import RuleContext, TargetContractRule
from ..common import add, has_value, value_for


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
            add(findings, "warn", "commit_role_mismatch", f"`{target}` expected `commit_role: {expected_role}`.", {"commit_role": role})
        if status in {"created", "committed", "success", "passed"} and not commit_hash:
            add(findings, "block" if mode == "block" else "warn", "commit_hash_missing", "Created commit result is missing `commit_hash`.")
        if status in {"created", "committed", "success", "passed"} and not commit_subject:
            add(findings, "block" if mode == "block" else "warn", "commit_subject_missing", "Created commit result is missing `commit_subject`.")
        if status in {"skipped", "not_applicable", "blocked", "failed"} and not skipped_reason:
            add(findings, "block" if mode == "block" else "warn", "commit_skipped_reason_missing", "Skipped/blocked commit result is missing `commit_skipped_reason`.")
