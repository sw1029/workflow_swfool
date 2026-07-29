from __future__ import annotations

from typing import Any

from .context import PacketBuildContext


def build_issue(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$manage-implementation-issues",
        "routing": {
            "issue_lifecycle": "after validation, before commit",
            "issue_fit_agent": ctx.route("issue_fit"),
        },
        "required_inputs": [
            "validation_verdict",
            "progress_verdict",
            "remaining blockers",
            "run/log/miss evidence",
            "current task.md that was just validated",
        ],
        "required_outputs": [
            "issue_packet_id",
            "task_id",
            "issue_status",
            "issue_provenance.source_task_id matching task_id",
            "issue_provenance.validation_id or validation_report_path",
            "durable issue ID/path/URL for lifecycle mutations",
            "resolution evidence for close/resolve",
            "blockers including explicit []",
            "evidence_paths",
        ],
    }


def build_commit(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$repo-change-commit",
        "routing": {"commit_finalization": ctx.route("commit")},
        "required_inputs": [
            "validation_verdict",
            "progress_verdict",
            "changed files",
            "remaining blockers",
            "issue IDs/paths when present",
            "schema status",
            "validation set artifact status and not_gold/quality_tier when relevant",
            "advice status",
        ],
        "commit_gates": [
            "run after validation and issue tracking",
            "partial verdict requires partial/checkpoint commit intent",
            "use commit_role: implementation",
            "created implementation commit hash belongs only to $repo-change-commit result until report assembly",
            "track used `.agent_advice` active/adopted files by default unless marked local_only with a reason",
        ],
        "required_outputs": [
            "commit_role",
            "commit_status",
            "commit_hash and commit_subject when created",
            "commit_skipped_reason when skipped/blocked/failed",
            "evidence_paths",
        ],
    }


def build_dashboard(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$render-cycle-dashboard",
        "routing": {
            "agent_routing_applicability": "deterministic_only",
            "phase": "post-commit ledger snapshot before report",
        },
        "required_inputs": [
            "stage.jsonl with explicit canonical step/status rows",
            "current_stage.json snapshot when present",
            "verified current_finalization.json pointer and immutable snapshot when a finalized attempt exists",
            "current task/completed task/next task IDs",
            "validation and progress verdicts/axes",
            "issue and commit results",
            "blockers, changed files, artifact/evidence paths",
            "adapter/caller record_retention_policy budgets when supplied",
        ],
        "required_outputs": [
            "step: dashboard",
            "task_id",
            "dashboard_status",
            "event_count and explicit current_stage_event_count",
            "snapshot_status",
            "validation_verdict and progress_verdict",
            "bounded read-only retention_summary with inventory, configured overage or fail-quiet nulls, duplicate packet candidates, regenerable projections, and protected evidence counts",
            "authoritative_final, authoritative_projection, finalization_receipt, and exact finalization_consumption echo when finalized truth exists",
            "blockers including explicit []",
            "dashboard_path",
            "evidence_paths",
        ],
        "fail_closed": [
            "malformed ledger JSON is an error, never a skipped row",
            "noncanonical or incomplete event envelopes remain visible in a separate section",
            "dashboard never upgrades validation or progress truth",
            "dashboard projects the verified current-finalization pointer; a later ledger echo cannot replace or contradict it",
            "retention dry-run never archives, deletes, applies, or changes close truth; absent/malformed policy is fail-quiet",
        ],
    }


def build_report(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$orchestrate-task-cycle",
        "routing": {
            "language": "Korean",
            "template": "references/cycle-report-template.md",
        },
        "required_inputs": [
            "verified current cycle_finalization_receipt and authoritative_projection for any predecessor final attempt",
            "report inputs whose legacy validation/progress fields converge with the receipt-bound projection",
            "dashboard retention_summary",
        ],
        "required_outputs": [
            "authoritative_final and authoritative_projection from the verified immutable snapshot",
            "finalization_receipt and exact finalization_consumption echo",
            "report/dashboard authoritative_projection_digest convergence",
        ],
        "required_fields_order": [
            "기준 GT",
            "비-GT 방향성 문서",
            "주 진행 skill",
            "모델/effort 라우팅",
            "수행한 task",
            "변경한 파일",
            "실행한 검증",
            "validation verdict",
            "progress verdict",
            "progress axes",
            "남은 blocker",
            "다음 task/방향성",
            "완료 여부",
        ],
    }


def build_closeout_commit(ctx: PacketBuildContext) -> dict[str, Any]:
    return {
        "skill": "$repo-change-commit",
        "routing": {
            "commit_finalization": ctx.route("commit"),
            "phase": "closeout artifact commit after report",
        },
        "required_inputs": [
            "rendered dashboard.md",
            "final_report.md or report draft path",
            "commit-result.json for implementation commit when present",
            "stage.jsonl/current_stage.json updates",
            "used `.agent_advice/active` or `.agent_advice/applied` files",
            "local_only reason for any closeout artifact intentionally not tracked",
            "for an adaptive session, exact authority request/reservation/pre-commit bindings and the deterministic settlement anchor path",
        ],
        "commit_gates": [
            "use commit_role: closeout",
            "do not backfill the closeout commit hash into a report that is part of that same commit",
            "create a closeout commit when report/dashboard/advice artifacts are intentional and coherent",
            "for an adaptive session, embed and verify git_embedded_settlement@v1 in the same commit",
            "skip only with commit_skipped_reason",
        ],
        "required_outputs": [
            "commit_role",
            "commit_status",
            "tracked_artifacts",
            "commit_hash and commit_subject when created",
            "settlement_anchor_path and settlement_verification for an adaptive session commit",
            "commit_skipped_reason when skipped/blocked/failed",
            "evidence_paths",
        ],
    }
