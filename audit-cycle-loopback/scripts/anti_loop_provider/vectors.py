from __future__ import annotations

from .common import *

def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []

def numeric_vector(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    vector: dict[str, float] = {}
    for key, child in value.items():
        if isinstance(child, dict):
            continue
        text_key = str(key).strip()
        if not text_key:
            continue
        if isinstance(child, bool):
            vector[text_key] = 1.0 if child else 0.0
        elif isinstance(child, (int, float)):
            vector[text_key] = float(child)
        elif isinstance(child, str):
            try:
                vector[text_key] = float(child.strip())
            except ValueError:
                continue
    return vector

def normalize_previous_accepted_baseline(value: Any) -> tuple[str | None, dict[str, Any], str | None]:
    if value is None:
        return None, {}, None
    if isinstance(value, (str, int, float)):
        fingerprint = str(value).strip()
        return (fingerprint or None), {}, None
    if not isinstance(value, dict):
        return None, {}, "previous_accepted_fp_unrecognized"
    fingerprint = None
    for key in (
        "previous_accepted_fp",
        "previous_accepted_fingerprint",
        "previous_output_fingerprint",
        "output_fingerprint",
        "current_output_fingerprint",
        "fingerprint",
    ):
        raw = value.get(key)
        if raw is not None and str(raw).strip():
            fingerprint = str(raw).strip()
            break
    vector_source: Any = None
    for key in (
        "previous_quality_vector",
        "quality_vector",
        "previous_high_water_mark",
        "high_water_mark",
        "coverage_quality_vector",
    ):
        if isinstance(value.get(key), dict):
            vector_source = value[key]
            break
    reason = value.get("insufficient_reason") or value.get("blocked_reason") or value.get("error")
    return fingerprint, numeric_vector(vector_source), str(reason) if reason else None

def find_coverage_quality_delta_gate(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            found = find_coverage_quality_delta_gate(item)
            if found:
                return found
        return None
    if not isinstance(value, dict):
        return None
    child = value.get("coverage_quality_delta_gate")
    if isinstance(child, dict):
        return child
    gate_name = str(value.get("gate") or value.get("name") or "").strip().lower()
    if (
        gate_name in {"g-cov", "coverage_quality_delta_gate"}
        or (
            "quality_delta_pass" in value
            and any(key in value for key in ("current_quality_vector", "previous_high_water_vector", "improved_fields"))
        )
    ):
        return value
    for child in value.values():
        found = find_coverage_quality_delta_gate(child)
        if found:
            return found
    return None

def coverage_gate_pass_value(gate: dict[str, Any]) -> bool | None:
    status = str(gate.get("status") or "").strip().lower()
    evaluation_status = str(gate.get("evaluation_status") or "").strip().lower()
    if status in {"not_evaluated", "not_applicable", "missing"} or evaluation_status == "not_evaluated":
        return None
    if "quality_delta_pass" in gate:
        return bool_value(gate.get("quality_delta_pass"))
    if status in {"pass", "passed", "ok"}:
        return True
    if status in {"block", "blocked", "fail", "failed"}:
        return False
    return None

def coverage_gate_vector(gate: dict[str, Any], *keys: str) -> dict[str, float]:
    for key in keys:
        vector = numeric_vector(gate.get(key))
        if vector:
            return vector
    return {}

def compact_coverage_gate(gate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(gate, dict):
        return None
    return {
        "quality_delta_pass": coverage_gate_pass_value(gate),
        "status": gate.get("status"),
        "improved_fields": list_values(gate.get("improved_fields")),
        "current_quality_vector": coverage_gate_vector(gate, "current_quality_vector", "quality_vector"),
        "previous_high_water_vector": coverage_gate_vector(
            gate,
            "previous_high_water_vector",
            "previous_quality_vector",
            "high_water_mark",
        ),
    }

def coverage_quality_delta_reconciliation_gate(local_gate: dict[str, Any], external_gate: dict[str, Any] | None, epsilon: float) -> dict[str, Any]:
    if not isinstance(external_gate, dict):
        return {
            "gate": "R-GCOV",
            "status": "not_applicable",
            "compared_sources": ["audit_cycle_loopback"],
            "validator_disagreement": False,
            "gcov_metric_name_collision": False,
            "constrains_disposition": False,
        }
    local_pass = coverage_gate_pass_value(local_gate)
    external_pass = coverage_gate_pass_value(external_gate)
    pass_disagreement = external_pass is not None and local_pass is not None and external_pass != local_pass
    local_current = coverage_gate_vector(local_gate, "current_quality_vector", "quality_vector")
    external_current = coverage_gate_vector(external_gate, "current_quality_vector", "quality_vector")
    value_conflicts = []
    for key in sorted(set(local_current) & set(external_current)):
        if abs(local_current[key] - external_current[key]) > (epsilon if abs(local_current[key]) <= 1.0 else 0.0):
            value_conflicts.append(
                {
                    "metric": key,
                    "audit_cycle_loopback_value": local_current[key],
                    "output_delta_value": external_current[key],
                }
            )
    blocked = pass_disagreement or bool(value_conflicts)
    return {
        "gate": "R-GCOV",
        "status": "block" if blocked else "pass",
        "compared_sources": ["audit_cycle_loopback", "output_delta"],
        "validator_disagreement": pass_disagreement,
        "gcov_metric_name_collision": bool(value_conflicts),
        "metric_value_conflicts": value_conflicts,
        "local_coverage_quality_delta_gate": compact_coverage_gate(local_gate),
        "external_coverage_quality_delta_gate": compact_coverage_gate(external_gate),
        "constrains_disposition": blocked,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }

def structure_metrics_gate(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("structure_metrics"), dict):
        metrics = dict(value["structure_metrics"])
    elif isinstance(value, dict):
        metrics = dict(value)
    else:
        metrics = {}
    source = value if isinstance(value, dict) else {}
    semantic_metrics = source.get("semantic_structure_metrics")
    if isinstance(semantic_metrics, dict):
        metrics.update(semantic_metrics)
    recommended = any(
        bool_value(metrics.get(key))
        for key in (
            "structure_consolidation_recommended",
            "consolidation_recommended",
            "budget_exceeded",
            "over_budget",
        )
    )
    high_water_moved = bool_value(
        source.get("structure_high_water_moved")
        or source.get("target_structure_improved")
        or source.get("structure_metric_improved")
        or metrics.get("structure_high_water_moved")
        or metrics.get("target_structure_improved")
        or metrics.get("structure_metric_improved")
    )
    improved_axes = source.get("improved_structure_axes") or source.get("improved_axes") or metrics.get("improved_structure_axes") or []
    if isinstance(improved_axes, str):
        improved_axes = [improved_axes]
    if not isinstance(improved_axes, list):
        improved_axes = []
    global_metric_source = (
        source.get("global_invariants")
        or source.get("global_invariant_metrics")
        or metrics.get("global_invariants")
        or metrics.get("global_invariant_metrics")
        or {}
    )
    global_metrics = numeric_vector(global_metric_source)
    for key, metric_value in numeric_vector(metrics).items():
        if str(key).startswith("global_"):
            global_metrics.setdefault(str(key), metric_value)
    global_high_water_moved = bool_value(
        source.get("global_structure_high_water_moved")
        or source.get("global_invariant_high_water_moved")
        or metrics.get("global_structure_high_water_moved")
        or metrics.get("global_invariant_high_water_moved")
    )
    refactor_effect_required = bool_value(
        source.get("refactor_effect_required")
        or source.get("behavior_preserving_refactor")
        or metrics.get("refactor_effect_required")
        or metrics.get("behavior_preserving_refactor")
    )
    return {
        "gate": "S-STRUCT",
        "structure_metrics": numeric_vector(metrics),
        "structure_global_invariant_metrics": global_metrics,
        "structure_high_water_key_scope": "global_invariant" if global_metrics else ("per_scope" if metrics else "not_evaluated"),
        "structure_consolidation_recommended": recommended,
        "structure_high_water_moved": high_water_moved or global_high_water_moved,
        "global_structure_high_water_moved": global_high_water_moved,
        "improved_structure_axes": [str(axis) for axis in improved_axes if str(axis).strip()],
        "refactor_effect_required": refactor_effect_required,
        "status": "warn" if recommended else ("not_applicable" if not metrics else "ok"),
        "constrains_disposition": False,
    }

def vector_delta_gate(
    *,
    gate_name: str,
    current: Any,
    previous: Any,
    pass_field: str,
    current_field: str,
    previous_field: str,
    epsilon: float,
) -> dict[str, Any]:
    current_vector = numeric_vector(current)
    previous_vector = numeric_vector(previous)
    improved_axes = [
        key
        for key, value in current_vector.items()
        if value > previous_vector.get(key, 0.0) + (epsilon if abs(value) <= 1.0 else 0.0)
    ]
    missing = not current_vector
    passed = bool(improved_axes)
    return {
        "gate": gate_name,
        current_field: current_vector,
        previous_field: previous_vector,
        "improved_axes": improved_axes,
        pass_field: passed,
        "status": "missing" if missing else ("pass" if passed else "block"),
        "fail_closed": missing,
        "constrains_disposition": missing or not passed,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
    }


INDEPENDENT_PROVENANCE_VALUES = {
    "independently_verified",
    "independent",
    "verified",
    "adapter_recomputed",
    "recomputed",
    "source_recomputed",
}
ATTESTED_PROVENANCE_VALUES = {
    "producer_attested",
    "attested",
    "producer_claim",
    "self_report",
    "self_reported",
    "declared",
}


def normalize_provenance_label(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in INDEPENDENT_PROVENANCE_VALUES:
        return "independently_verified"
    if text in ATTESTED_PROVENANCE_VALUES:
        return "producer_attested"
    return text or "producer_attested"

def normalize_evidence_provenance(value: Any) -> tuple[dict[str, str], bool]:
    if value is None:
        return {}, False
    source = value
    if isinstance(value, dict):
        for key in ("evidence_provenance", "metric_provenance", "provenance_by_metric", "metrics"):
            if isinstance(value.get(key), (dict, list)):
                source = value.get(key)
                break
    provenance: dict[str, str] = {}

    def add(metric_key: Any, provenance_value: Any) -> None:
        key = normalize_gate_key(metric_key)
        label_source = provenance_value
        if isinstance(provenance_value, dict):
            label_source = (
                provenance_value.get("evidence_provenance")
                or provenance_value.get("provenance")
                or provenance_value.get("source")
                or provenance_value.get("status")
            )
        provenance[key] = normalize_provenance_label(label_source)

    if isinstance(source, dict):
        for metric_key, provenance_value in source.items():
            add(metric_key, provenance_value)
    elif isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            metric_key = item.get("metric") or item.get("metric_key") or item.get("field") or item.get("name")
            if metric_key:
                add(metric_key, item)
    return provenance, True

def provenance_for_metric(metric_key: str, provenance: dict[str, str], hook_provided: bool) -> str:
    if not hook_provided:
        return "legacy_unclassified"
    return provenance.get(normalize_gate_key(metric_key), "producer_attested")

def metric_is_independently_verified(metric_key: str, provenance: dict[str, str], hook_provided: bool) -> bool:
    if not hook_provided:
        return True
    return provenance_for_metric(metric_key, provenance, hook_provided) == "independently_verified"

def apply_evidence_provenance_filter(
    gate: dict[str, Any],
    *,
    improved_key: str,
    pass_key: str,
    provenance: dict[str, str],
    hook_provided: bool,
) -> tuple[dict[str, Any], list[str], list[str]]:
    if not hook_provided:
        return gate, [], []
    updated = dict(gate)
    improved = list_values(updated.get(improved_key))
    independent = [field for field in improved if metric_is_independently_verified(field, provenance, hook_provided)]
    attested = [field for field in improved if field not in independent]
    updated[improved_key] = independent
    updated[pass_key] = bool(independent)
    if improved and not independent:
        updated["status"] = "block"
    elif independent:
        updated["status"] = "pass"
    updated["evidence_provenance_status"] = "provided"
    updated["independently_verified_fields"] = independent
    updated["producer_attested_fields"] = attested
    updated["attested_only_movement"] = bool(attested and not independent)
    return updated, independent, attested

def evidence_provenance_gate(
    *,
    hook_provided: bool,
    provenance: dict[str, str],
    independent_fields: list[str],
    attested_fields: list[str],
    adapter_error: str | None,
    source_separation_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attested_only = bool(attested_fields and not independent_fields)
    source_separation_gate = source_separation_gate or {}
    return {
        "gate": "F2-EVIDENCE-PROVENANCE",
        "evidence_provenance_status": "provided" if hook_provided else ("error" if adapter_error else "not_provided"),
        "adapter_error": adapter_error,
        "provenance_by_metric": provenance,
        "independently_verified_fields": sorted(set(independent_fields)),
        "producer_attested_fields": sorted(set(attested_fields)),
        "attested_only_movement": attested_only,
        "verification_source_separation_gate": source_separation_gate,
        "verification_input_paths": source_separation_gate.get("verification_input_paths") or [],
        "verified_artifact_paths": source_separation_gate.get("verified_artifact_paths") or [],
        "independent_source_separation_status": source_separation_gate.get("independent_source_separation_status"),
        "independently_verified_downgraded_fields": source_separation_gate.get("independently_verified_downgraded_fields") or [],
        "status": "warn" if attested_only else ("pass" if independent_fields else ("not_evaluated" if not hook_provided else "ok")),
        "constrains_disposition": False,
    }
