"""Scalar event fields retained in the bounded model/context projection."""

from __future__ import annotations


DECISION_SCALARS = (
    "validation_verdict",
    "progress_verdict",
    "authoritative_final",
    "execution_status",
    "review_status",
    "quality_verdict",
    "selection_outcome",
    "index_status",
    "audit_observation_scope",
    "live_revalidation_required",
    "commit_status",
    "validation_set_need",
    "adapter_change_count",
    "changed_vs_previous",
    "output_delta_status",
    "semantic_progress",
    "produced_domain_delta",
    "same_family_micro_hardening_count",
    "recommended_disposition",
    "hard_stop_required",
    "schema_status",
    "issue_status",
)


__all__ = ("DECISION_SCALARS",)
