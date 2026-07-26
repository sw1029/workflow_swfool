"""Closed schema-v6 source approvals for authority-interaction child grants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import source_approval_contract as base
from .canonical import parse_time
from .contracts import CARDINALITIES, RISK_TIERS, SOURCE_RANKS, validate_subject


ACTIVATION_CHILD_KEYS = {
    "grant_id", "lineage_id", "grant_idempotency_key", "request_sha256",
    "holder_rank", "capabilities", "subjects", "operations", "risk_ceiling",
    "decision_classes", "cardinality", "max_uses", "session_id", "task_id",
    "improvement_id", "policy_snapshot", "activation_materialization_ref",
}


def _child(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != ACTIVATION_CHILD_KEYS:
        raise SystemExit("Schema-v6 source approval activation_child is not closed.")
    request_sha256 = str(value["request_sha256"])
    if len(request_sha256) != 64 or any(char not in "0123456789abcdef" for char in request_sha256):
        raise SystemExit("Schema-v6 activation child request_sha256 is invalid.")
    holder_rank, risk, cardinality, max_uses = str(value["holder_rank"]), str(value["risk_ceiling"]), str(value["cardinality"]), value["max_uses"]
    if holder_rank not in SOURCE_RANKS or holder_rank not in {"S0", "S1"} or risk not in RISK_TIERS or cardinality not in CARDINALITIES or not isinstance(max_uses, int) or isinstance(max_uses, bool) or max_uses < 1:
        raise SystemExit("Schema-v6 activation child scope is invalid.")
    subjects, operations = value["subjects"], value["operations"]
    if not isinstance(subjects, list) or len(subjects) != 1 or not isinstance(operations, list) or len(operations) != 1:
        raise SystemExit("Schema-v6 activation child requires one subject and operation.")
    ref = str(value["activation_materialization_ref"] or "").strip()
    if not ref.startswith(".task/authorization/authority_interaction_activations/") or not ref.endswith("/receipt.json") or "*" in ref or ".." in Path(ref).parts:
        raise SystemExit("Schema-v6 activation child materialization ref is invalid.")
    return {"grant_id": base._exact_identifier(value["grant_id"], "activation_child.grant_id"), "lineage_id": base._exact_identifier(value["lineage_id"], "activation_child.lineage_id"), "grant_idempotency_key": base._exact_identifier(value["grant_idempotency_key"], "activation_child.grant_idempotency_key"), "request_sha256": request_sha256, "holder_rank": holder_rank, "capabilities": base._unique_strings(value["capabilities"], "activation_child.capabilities"), "subjects": [validate_subject(subjects[0], "activation_child.subject")], "operations": base._operations(operations), "risk_ceiling": risk, "decision_classes": base._unique_strings(value["decision_classes"], "activation_child.decision_classes"), "cardinality": cardinality, "max_uses": max_uses, "session_id": base._exact_identifier(value["session_id"], "activation_child.session_id", nullable=True), "task_id": base._exact_identifier(value["task_id"], "activation_child.task_id", nullable=True), "improvement_id": base._exact_identifier(value["improvement_id"], "activation_child.improvement_id", nullable=True), "policy_snapshot": base._delegation_binding(value["policy_snapshot"], True), "activation_materialization_ref": ref}


def validate_activation_source_approval(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != base.APPROVAL_V6_KEYS or value.get("artifact_kind") != "authority_source_approval" or value.get("schema_version") != 6:
        raise SystemExit("Schema-v6 source approval is invalid.")
    if value.get("source_kind") != "delegated_policy_steward" or value.get("source_rank") != "S2" or value.get("decision_type") != "grant_authority" or value.get("decision_trust_class") != "host_user_signed_mode_activation_child":
        raise SystemExit("Schema-v6 source approval trust scope is invalid.")
    child = _child(value["activation_child"])
    bindings = {field: base._delegation_binding(value[field], True) for field in ("delegation_binding", "decision_binding", "activation_plan", "activation_evidence", "activation_materialization")}
    if bindings["delegation_binding"] != bindings["activation_plan"] or bindings["decision_binding"] != bindings["activation_evidence"]:
        raise SystemExit("Schema-v6 source approval activation bindings diverge.")
    if base._unique_strings(value["grant_ids"], "source approval grant_ids") != [child["grant_id"]] or base._unique_strings(value["lineage_ids"], "source approval lineage_ids") != [child["lineage_id"]] or base._digests(value["request_digests"]) != [child["request_sha256"]] or base._unique_strings(value["capabilities"], "source approval capabilities") != sorted(set(child["capabilities"]) | {"authority.grant.issue"}) or [validate_subject(item, "source approval subject") for item in value["subjects"]] != child["subjects"] or base._operations(value["operations"]) != child["operations"] or value["risk_ceiling"] != child["risk_ceiling"] or base._unique_strings(value["decision_classes"], "source approval decision_classes") != child["decision_classes"] or base._unique_strings(value["cardinalities"], "source approval cardinalities") != [child["cardinality"]] or value["max_uses"] != child["max_uses"]:
        raise SystemExit("Schema-v6 source approval child projection differs.")
    if value["expires_at"] is not None:
        raise SystemExit("Schema-v6 source approval expiry is activation-owned.")
    return {"schema_version": 6, "artifact_kind": "authority_source_approval", "approval_id": base._exact_identifier(value["approval_id"], "source approval approval_id"), "source_kind": "delegated_policy_steward", "source_rank": "S2", "decision_type": "grant_authority", "capabilities": sorted(set(child["capabilities"]) | {"authority.grant.issue"}), "subjects": child["subjects"], "operations": child["operations"], "risk_ceiling": child["risk_ceiling"], "decision_classes": child["decision_classes"], "cardinalities": [child["cardinality"]], "max_uses": child["max_uses"], "grant_ids": [child["grant_id"]], "request_digests": [child["request_sha256"]], "lineage_ids": [child["lineage_id"]], "delegation_binding": bindings["delegation_binding"], "not_before": parse_time(value["not_before"], "source approval not_before").isoformat(), "expires_at": None, "evidence_id": base._exact_identifier(value["evidence_id"], "source approval evidence_id"), "decision_binding": bindings["decision_binding"], "decision_trust_class": "host_user_signed_mode_activation_child", "activation_plan": bindings["activation_plan"], "activation_evidence": bindings["activation_evidence"], "activation_materialization": bindings["activation_materialization"], "activation_child": child}
