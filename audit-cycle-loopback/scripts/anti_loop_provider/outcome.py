from __future__ import annotations

from .common import *

def first_scalar_by_key(value: Any, keys: set[str]) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in keys:
                scalars = scalar_strings(child)
                if scalars:
                    return scalars[0]
            found = first_scalar_by_key(child, keys)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_scalar_by_key(child, keys)
            if found:
                return found
    return None

def observed_delta_class(output_delta: Any, changed_vs_previous: bool, semantic_progress: bool) -> str:
    observed = first_scalar_by_key(
        output_delta,
        {"observed_delta_class", "observed_output_class", "output_class", "effective_progress_kind"},
    )
    if observed:
        return observed.strip().lower()
    if changed_vs_previous and semantic_progress:
        return "changed_semantic_output"
    return "no_observed_domain_delta"

def terminal_outcome_changed(output_delta: Any, changed_vs_previous: bool, semantic_progress: bool) -> bool:
    produced = first_scalar_by_key(output_delta, {"produced_domain_delta", "domain_delta", "positive_output_delta"})
    changed = first_scalar_by_key(output_delta, {"changed_vs_previous"})
    semantic = first_scalar_by_key(output_delta, {"semantic_progress"})
    metadata = first_scalar_by_key(output_delta, {"metadata_only"})
    observed = observed_delta_class(output_delta, changed_vs_previous, semantic_progress)
    strict_changed = bool_value(changed) if changed is not None else changed_vs_previous
    strict_semantic = bool_value(semantic) if semantic is not None else semantic_progress
    if bool_value(metadata):
        return False
    if observed in {"material_delta", "semantic_delta", "changed_semantic_output", "primary_output_delta"}:
        return strict_changed and strict_semantic
    if produced is not None and not bool_value(produced):
        return False
    return bool_value(produced) and strict_changed and strict_semantic


def terminal_self_resolution_gate(*values: Any) -> dict[str, Any]:
    allowed = {
        "self_resolvable_local",
        "offline_recompute",
        "existing_authority",
        "genuine_new_authority",
        "external_state_change",
        "unverified",
    }
    residual_rows: list[dict[str, Any]] = []
    terminal_requested = False
    for value in values:
        for row in iter_dicts(value):
            terminal_requested = terminal_requested or any(
                bool_value(row.get(key)) for key in ("terminal_justified", "terminal_requested", "user_escalation_required")
            )
            raw_rows = row.get("residual_classification") or row.get("residuals")
            if isinstance(raw_rows, list):
                for item in raw_rows:
                    if isinstance(item, dict):
                        residual_rows.append(item)
                    elif item is not None:
                        residual_rows.append({"residual_id": str(item), "classification": "unverified"})
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(residual_rows):
        classification = str(row.get("classification") or row.get("residual_class") or "unverified").strip().lower()
        if classification not in allowed:
            classification = "unverified"
        normalized.append({
            "residual_id": row.get("residual_id") or row.get("id") or f"residual-{index + 1}",
            "classification": classification,
        })
    local_classes = {"self_resolvable_local", "offline_recompute", "existing_authority"}
    self_resolvable = [row for row in normalized if row["classification"] in local_classes]
    unverified = [row for row in normalized if row["classification"] == "unverified"]
    classification_missing = terminal_requested and not normalized
    return {
        "residual_classification": normalized,
        "self_resolvable_residual_count": len(self_resolvable),
        "unverified_residual_count": len(unverified),
        "offline_scope_unverified": classification_missing or bool(unverified),
        "goal_terminal_prohibited": bool(self_resolvable) or classification_missing or bool(unverified),
        "status": "block" if bool(self_resolvable) else ("not_evaluated" if classification_missing or unverified else "pass"),
    }

def terminal_outcome_key(output_delta: Any, changed_vs_previous: bool, semantic_progress: bool) -> str:
    observed = observed_delta_class(output_delta, changed_vs_previous, semantic_progress)
    status = first_scalar_by_key(
        output_delta,
        {
            "terminal_outcome",
            "output_delta_status",
            "status",
            "failure_class",
            "blocked_reason",
            "blocker_signature",
        },
    )
    produced = first_scalar_by_key(output_delta, {"produced_domain_delta", "domain_delta", "positive_output_delta"})
    metadata = first_scalar_by_key(output_delta, {"metadata_only"})
    if bool_value(metadata):
        base = "metadata_only"
    elif terminal_outcome_changed(output_delta, changed_vs_previous, semantic_progress):
        base = "changed_semantic_output"
    elif produced is not None and not bool_value(produced):
        base = "no_primary_output_delta"
    elif observed and observed not in {"unknown", "none", "null"}:
        base = observed
    else:
        base = "no_semantic_output_delta"
    return normalize_root_family_key(base, status or "")

def terminal_outcome_root_family(
    facet_map: dict[str, str],
    *,
    artifact_family: str,
    outcome_key: str,
    root_key: str,
    semantic_signature: str,
) -> tuple[str, str, bool]:
    if facet_map:
        mapped = collapse_root_family(facet_map, root_key, semantic_signature, artifact_family, outcome_key)
        return mapped, "facet_root_map", False
    return normalize_root_family_key(artifact_family, outcome_key), "terminal_outcome_fallback", True

def latest_root_family_row(rows: list[dict[str, Any]], root_family_key: str) -> dict[str, Any] | None:
    return next((row for row in reversed(rows) if row_root_family(row) == root_family_key), None)

def row_effective_count_key(row: dict[str, Any]) -> str:
    return str(row.get("failure_surface_count_key") or row.get("effective_count_key") or row_root_family(row))

def previous_micro_hardening_count(rows: list[dict[str, Any]], root_family_key: str) -> int:
    family_rows = [row for row in rows if row_root_family(row) == root_family_key]
    if not family_rows:
        return 0
    return max(int_metric(row.get("same_family_micro_hardening_count") or row.get("micro_hardening_count") or 0) for row in family_rows)

def previous_micro_hardening_count_for_count_key(rows: list[dict[str, Any]], count_key: str) -> int:
    family_rows = [row for row in rows if row_effective_count_key(row) == count_key]
    if not family_rows:
        return 0
    return max(int_metric(row.get("same_family_micro_hardening_count") or row.get("micro_hardening_count") or 0) for row in family_rows)

def normalize_root_cause_slug(value: Any) -> str:
    return normalize_root_family_key(str(value or "unknown_root_cause"))
