from __future__ import annotations

from typing import Any

from .payload_family_fields import FAMILY_PROGRESS_ROW_FIELDS
from .payload_metric_privacy import validate_primary_metric_gate_privacy
from .payload_schema_common import (
    exact_object,
    exact_rows_payload,
    require_bool,
    require_digest,
    require_non_negative_int,
    require_opaque_id,
    require_unique_opaque_ids,
)
from .support import canonical_sha256


_ROOT_CAUSE_FIELDS = frozenset(
    {
        "schema_version",
        "cycle_id",
        "attempt_identity",
        "input_state_fingerprint",
        "family_key",
        "root_key",
        "root_family_key",
        "hypothesized_root_cause",
        "target_surface",
        "blocker_signature",
        "repair_attempted",
        "terminal_outcome_changed",
        "observed_delta_class",
        "local",
        "bounded",
        "provider_free",
        "in_scope",
        "authority_allowed",
        "actionable",
        "provenance_refs",
        "actionability_status",
        "actionability_basis",
        "label_correction",
        "correction_of_attempt_identity",
        "attempt_count",
        "vacuous_attempt_count",
        "first_cycle_id",
        "previous_cycle_id",
        "hypothesis_aliases",
        "self_report_rejected_fields",
    }
)
_ACTIONABILITY_BASIS_FIELDS = frozenset(
    {
        "asserted_actionable",
        "structural_actionable",
        "provenance_derived_actionable",
        "repo_owned_source_ref_count",
        "repo_owned_source_refs",
        "provenance_ref_count",
        "required_structural_fields",
    }
)
_SEAL_RECORD_FIELDS = frozenset(
    {
        "semantic_signature",
        "blocker_signature",
        "root_key",
        "root_family_key",
        "hypothesis_exhausted",
        "vacuous_untried_attempt_count",
        "untried_promotion_budget",
        "source",
    }
)
_RECURRENCE_FIELDS = frozenset(
    {
        "applicability",
        "stable_root_id",
        "root_predicate_id",
        "root_scope_id",
        "root_identity_sha256",
        "prior_stable_root_id",
        "prior_root_predicate_id",
        "prior_root_scope_id",
        "prior_root_identity_sha256",
        "facet_id",
        "local_family_id",
        "root_recurrence_count",
        "prior_root_recurrence_count",
        "facet_recurrence_count",
        "local_family_attempt_count",
        "evaluation_debt_streak",
        "prior_evaluation_debt_streak",
        "root_predicate_unchanged",
        "binding_status",
        "supplied_input_delta",
        "lineage_transition",
    }
)
_RECURRENCE_REQUIRED_FIELDS = frozenset(
    {
        "applicability",
        "stable_root_id",
        "root_predicate_id",
        "root_scope_id",
        "root_identity_sha256",
        "prior_stable_root_id",
        "prior_root_predicate_id",
        "prior_root_scope_id",
        "prior_root_identity_sha256",
        "facet_id",
        "local_family_id",
        "root_recurrence_count",
        "facet_recurrence_count",
        "local_family_attempt_count",
        "evaluation_debt_streak",
        "root_predicate_unchanged",
        "binding_status",
    }
)
_MATERIAL_DELTA_FIELDS = frozenset(
    {
        "classification",
        "delta_id",
        "rationale_id",
        "rationale_evidence_digest",
        "full_content_sha256",
        "typed_difference_ids",
        "violated_relation_effect",
        "authority_premise_changed",
        "external_state_changed",
        "toolchain_premise_changed",
        "delta_receipt_sha256",
    }
)
_LINEAGE_FIELDS = frozenset(
    {
        "kind",
        "transition_id",
        "parent_root_ids",
        "child_root_ids",
        "prior_attempt_lower_bound",
        "aggregate_recurrence_count",
        "logical_attempt_id",
        "attempt_revision",
        "supersedes_attempt_revision",
    }
)


def validate_family_progress_registry_payload(value: object) -> None:
    rows = exact_rows_payload(value, label="family-progress-registry-v1")
    for row in rows:
        parsed = exact_object(
            row,
            allowed=FAMILY_PROGRESS_ROW_FIELDS,
            required=frozenset({"cycle_id"}),
            label="family-progress-registry-v1 row",
        )
        require_opaque_id(parsed["cycle_id"], label="family progress cycle_id")
        if not any(
            parsed.get(field)
            for field in (
                "family_key",
                "root_key",
                "root_family_key",
                "semantic_signature",
                "artifact_family",
            )
        ):
            raise ValueError("family progress row must retain a stable family identity")
        if parsed.get("family_key") is not None:
            require_opaque_id(
                parsed["family_key"],
                label="family progress family_key",
            )
        if parsed.get("schema_version") not in (None, "anti-loop-progress-gate-v1"):
            raise ValueError("family progress row schema_version is invalid")
        if parsed.get("attempt_identity") is not None:
            require_opaque_id(
                parsed["attempt_identity"], label="family progress attempt_identity"
            )
        if "registry_updated" in parsed:
            require_bool(
                parsed["registry_updated"],
                label="family progress registry_updated",
            )
        for field in ("progress_verdict", "status"):
            if parsed.get(field) is not None:
                require_opaque_id(
                    parsed[field],
                    label=f"family progress {field}",
                )
        for field in (
            "event_event_relation_output",
            "produced_domain_delta",
            "quality_delta_pass",
        ):
            if field in parsed:
                require_bool(
                    parsed[field],
                    label=f"family progress {field}",
                )
        for field in (
            "edge_count",
            "genuine_relation_count",
            "local_model_request_count",
        ):
            if field in parsed:
                require_non_negative_int(
                    parsed[field],
                    label=f"family progress {field}",
                )
        if "primary_metric_gate" in parsed:
            validate_primary_metric_gate_privacy(parsed["primary_metric_gate"])
        findings = parsed.get("findings")
        if findings is not None:
            if not isinstance(findings, list):
                raise ValueError("family progress findings must be a list")
            for finding in findings:
                exact_object(
                    finding,
                    allowed=frozenset({"severity", "code"}),
                    required=frozenset({"severity", "code"}),
                    label="family progress finding",
                )


def validate_root_cause_ledger_payload(value: object) -> None:
    rows = exact_rows_payload(value, label="root-cause-ledger-v1")
    for row in rows:
        parsed = exact_object(
            row,
            allowed=_ROOT_CAUSE_FIELDS,
            required=frozenset({"cycle_id", "root_key"}),
            label="root-cause-ledger-v1 row",
        )
        require_opaque_id(parsed["cycle_id"], label="root cause cycle_id")
        require_opaque_id(parsed["root_key"], label="root cause root_key")
        if parsed.get("schema_version") not in (
            None,
            "root-cause-hypothesis-ledger-v1",
        ):
            raise ValueError("root cause row schema_version is invalid")
        for field in (
            "repair_attempted",
            "terminal_outcome_changed",
            "local",
            "bounded",
            "provider_free",
            "in_scope",
            "authority_allowed",
            "actionable",
            "label_correction",
        ):
            if field in parsed:
                require_bool(parsed[field], label=f"root cause {field}")
        for field in ("attempt_count", "vacuous_attempt_count"):
            if field in parsed:
                require_non_negative_int(parsed[field], label=f"root cause {field}")
        if "actionability_basis" in parsed:
            exact_object(
                parsed["actionability_basis"],
                allowed=_ACTIONABILITY_BASIS_FIELDS,
                required=frozenset(),
                label="root cause actionability_basis",
            )


def validate_sealed_blocker_families_payload(value: object) -> None:
    payload = exact_object(
        value,
        allowed=frozenset({"state"}),
        required=frozenset({"state"}),
        label="sealed-blocker-families-v1",
    )
    state = exact_object(
        payload["state"],
        allowed=frozenset({"schema_version", "families"}),
        required=frozenset({"schema_version", "families"}),
        label="sealed blocker state",
    )
    if state["schema_version"] != "sealed-blocker-families-v1":
        raise ValueError("sealed blocker state schema_version is invalid")
    if not isinstance(state["families"], list):
        raise ValueError("sealed blocker families must be a list")
    for family in state["families"]:
        parsed = exact_object(
            family,
            allowed=_SEAL_RECORD_FIELDS,
            required=frozenset(),
            label="sealed blocker family",
        )
        if not any(
            parsed.get(field)
            for field in (
                "semantic_signature",
                "blocker_signature",
                "root_key",
                "root_family_key",
            )
        ):
            raise ValueError("sealed blocker family must retain a stable identity")
        if (
            "hypothesis_exhausted" in parsed
            and parsed["hypothesis_exhausted"] is not True
        ):
            raise ValueError("sealed blocker family must be hypothesis-exhausted")


def validate_recurrence_identity_payload(value: object) -> None:
    payload = exact_object(
        value,
        allowed=frozenset({"state"}),
        required=frozenset({"state"}),
        label="recurrence-identity-v1",
    )
    state = exact_object(
        payload["state"],
        allowed=_RECURRENCE_FIELDS,
        required=_RECURRENCE_REQUIRED_FIELDS,
        label="recurrence identity state",
    )
    if state["applicability"] != "applicable":
        raise ValueError("durable recurrence identity must be applicable")
    for field in (
        "stable_root_id",
        "root_predicate_id",
        "root_scope_id",
        "prior_stable_root_id",
        "prior_root_predicate_id",
        "prior_root_scope_id",
        "facet_id",
        "local_family_id",
        "binding_status",
    ):
        require_opaque_id(state[field], label=f"recurrence {field}")
    _validate_root_identity_binding(state, prior=False)
    _validate_root_identity_binding(state, prior=True)
    for field in (
        "root_recurrence_count",
        "facet_recurrence_count",
        "local_family_attempt_count",
        "evaluation_debt_streak",
    ):
        require_non_negative_int(state[field], label=f"recurrence {field}")
    for field in ("prior_root_recurrence_count", "prior_evaluation_debt_streak"):
        if state.get(field) is not None:
            require_non_negative_int(state[field], label=f"recurrence {field}")
    require_bool(
        state["root_predicate_unchanged"],
        label="recurrence root_predicate_unchanged",
    )
    if "supplied_input_delta" in state:
        _validate_material_delta(state["supplied_input_delta"])
    if "lineage_transition" in state:
        _validate_lineage_transition(state["lineage_transition"])


def _validate_root_identity_binding(state: dict[str, Any], *, prior: bool) -> None:
    prefix = "prior_" if prior else ""
    material = {
        "stable_root_id": state[f"{prefix}stable_root_id"],
        "root_predicate_id": state[f"{prefix}root_predicate_id"],
        "root_scope_id": state[f"{prefix}root_scope_id"],
    }
    digest_field = f"{prefix}root_identity_sha256"
    require_digest(state[digest_field], label=f"recurrence {digest_field}")
    if state[digest_field] != canonical_sha256(material):
        raise ValueError("recurrence root identity digest mismatch")


def _validate_material_delta(value: object) -> None:
    delta = exact_object(
        value,
        allowed=_MATERIAL_DELTA_FIELDS,
        required=_MATERIAL_DELTA_FIELDS,
        label="recurrence material delta",
    )
    if delta["classification"] != "material":
        raise ValueError("durable supplied_input_delta must be material")
    require_digest(
        delta["rationale_evidence_digest"],
        label="recurrence rationale_evidence_digest",
    )
    require_digest(delta["full_content_sha256"], label="recurrence content digest")
    require_unique_opaque_ids(
        delta["typed_difference_ids"],
        label="recurrence typed_difference_ids",
    )
    receipt = require_digest(
        delta["delta_receipt_sha256"],
        label="recurrence delta_receipt_sha256",
    )
    if receipt != canonical_sha256(
        {key: item for key, item in delta.items() if key != "delta_receipt_sha256"}
    ):
        raise ValueError("recurrence material delta receipt mismatch")


def _validate_lineage_transition(value: object) -> None:
    transition = exact_object(
        value,
        allowed=_LINEAGE_FIELDS,
        required=frozenset({"kind"}),
        label="recurrence lineage transition",
    )
    kind = transition["kind"]
    if kind not in {"none", "split", "merge", "reclassification", "correction"}:
        raise ValueError("recurrence lineage transition kind is invalid")
    if kind == "none" and set(transition) != {"kind"}:
        raise ValueError("none lineage transition cannot carry mutation fields")


__all__ = [
    "validate_family_progress_registry_payload",
    "validate_recurrence_identity_payload",
    "validate_root_cause_ledger_payload",
    "validate_sealed_blocker_families_payload",
]
