from __future__ import annotations

from ..runtime_dependencies import (
    Path,
    default_high_water,
    finalized_projection_rows,
    finalized_seal_projection,
    load_registry,
    load_verified_finalized_loopback_state,
    normalize_family_key,
)

from ..evaluation_frame import _EvaluationFrame


def _prepare_registry_state(frame: _EvaluationFrame) -> None:
    args = frame.require('args')
    root = Path(args.root).resolve()
    registry_path = Path(args.registry_path)
    if not registry_path.is_absolute():
        registry_path = root / registry_path
    finalized_cycle_id = str(getattr(args, "finalized_cycle_id", None) or args.cycle_id)
    finalized_state, finalized_state_status, finalized_state_error = load_verified_finalized_loopback_state(
        root,
        finalized_cycle_id,
    )
    finalized_projections = (
        finalized_state.get("projections")
        if isinstance(finalized_state.get("projections"), dict)
        else {}
    )
    finalized_registry_rows, finalized_registry_present = finalized_projection_rows(
        finalized_projections,
        "family_progress_registry",
    )
    finalized_root_cause_rows, finalized_root_cause_present = finalized_projection_rows(
        finalized_projections,
        "root_cause_ledger",
    )
    finalized_seal_state, finalized_seal_present = finalized_seal_projection(finalized_projections)
    legacy_registry_rows = load_registry(registry_path)
    if finalized_state_status == "invalid":
        registry_rows = []
        registry_state_source = "invalid_finalized_state"
    elif finalized_registry_present:
        registry_rows = finalized_registry_rows
        registry_state_source = "verified_finalization"
    else:
        registry_rows = legacy_registry_rows
        registry_state_source = "legacy_registry_fallback"
    legacy_family_key = normalize_family_key(args.artifact_family, args.semantic_signature)
    family_key = legacy_family_key
    existing_cycle = next(
        (row for row in reversed(registry_rows) if row.get("family_key") == family_key and row.get("cycle_id") == args.cycle_id),
        None,
    )
    latest = next((row for row in reversed(registry_rows) if row.get("family_key") == family_key), None)
    prev_high = dict((latest or {}).get("high_water_mark") or default_high_water())
    prev_count = int((latest or {}).get("micro_hardening_count") or 0)
    prev_fingerprint = (latest or {}).get("current_output_fingerprint")
    frame.update({
        "existing_cycle": existing_cycle,
        "family_key": family_key,
        "finalized_cycle_id": finalized_cycle_id,
        "finalized_root_cause_present": finalized_root_cause_present,
        "finalized_root_cause_rows": finalized_root_cause_rows,
        "finalized_seal_present": finalized_seal_present,
        "finalized_seal_state": finalized_seal_state,
        "finalized_state_error": finalized_state_error,
        "finalized_state_status": finalized_state_status,
        "latest": latest,
        "legacy_family_key": legacy_family_key,
        "prev_count": prev_count,
        "prev_fingerprint": prev_fingerprint,
        "prev_high": prev_high,
        "registry_path": registry_path,
        "registry_rows": registry_rows,
        "registry_state_source": registry_state_source,
        "root": root,
    })
