"""Closed authority grant field sets."""

GRANT_KEYS = {
    "schema_version",
    "artifact_kind",
    "grant_id",
    "lineage_id",
    "parent_grant_id",
    "issuer_rank",
    "holder_rank",
    "capabilities",
    "subjects",
    "operations",
    "risk_ceiling",
    "decision_classes",
    "cardinality",
    "max_uses",
    "not_before",
    "expires_at",
    "session_id",
    "task_id",
    "improvement_id",
    "source_approval",
    "policy_snapshot",
    "created_at",
    "idempotency_key",
}
GRANT_V3_KEYS = GRANT_KEYS | {
    "request_sha256",
    "root_materialization_ref",
}


__all__ = ("GRANT_KEYS", "GRANT_V3_KEYS")
