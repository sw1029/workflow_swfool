from __future__ import annotations

from .runtime_dependencies import (
    Any,
    IDEMPOTENT_REPLAY_KEYS,
    bool_value,
    compact_registry,
)

from .evaluation_frame import _EvaluationFrame
from .evaluation_stages.finalize_consumer import _finalize_consumer_conformance
from .evaluation_stages.finalize_identity import _finalize_attempt_identity
from .evaluation_stages.finalize_replay import _finalize_replay_state
from .assembly import build_base_packet
from .findings import apply_disposition_and_findings
from .root_cause_runtime import apply_root_cause_ledger


def _finalize_evaluation(frame: _EvaluationFrame) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    _finalize_attempt_identity(frame)
    _finalize_consumer_conformance(frame)
    _finalize_replay_state(frame)
    row = build_base_packet(frame.snapshot())
    frame.update({"row": row})
    chain_untried_override, untried, ledger_entries = apply_root_cause_ledger(frame.snapshot())
    frame.update({
        "chain_untried_override": chain_untried_override,
        "untried": untried,
        "ledger_entries": ledger_entries,
    })
    apply_disposition_and_findings(frame.snapshot())
    (
        args, attempt_identity, attempt_revision_candidate, count, disagreement,
        disposition, existing_cycle, high_water, registry_label_correction,
        registry_rows, supersedes_attempt_identity_candidate,
        supersedes_attempt_revision_candidate,
    ) = frame.require(
        "args", "attempt_identity", "attempt_revision_candidate", "count",
        "disagreement", "disposition", "existing_cycle", "high_water",
        "registry_label_correction", "registry_rows",
        "supersedes_attempt_identity_candidate",
        "supersedes_attempt_revision_candidate",
    )
    if existing_cycle:
        row["registry_idempotent_replay"] = True
        row["same_family_micro_hardening_count"] = existing_cycle.get("same_family_micro_hardening_count", count)
        row["micro_hardening_count"] = existing_cycle.get("micro_hardening_count", row["same_family_micro_hardening_count"])
        row["high_water_mark"] = existing_cycle.get("high_water_mark", high_water)
        row["semantic_progress"] = bool_value(existing_cycle.get("semantic_progress"))
        row["changed_vs_previous"] = bool_value(existing_cycle.get("changed_vs_previous"))
        row["recommended_disposition"] = existing_cycle.get("recommended_disposition", disposition)
        row["hard_stop_required"] = bool_value(existing_cycle.get("hard_stop_required"))
        for key in IDEMPOTENT_REPLAY_KEYS:
            if key in existing_cycle:
                row[key] = existing_cycle[key]
        if disagreement:
            existing_codes = {
                str(finding.get("code") or "")
                for finding in row.get("findings", [])
                if isinstance(finding, dict)
            }
            if "validator_disagreement" not in existing_codes:
                row.setdefault("findings", []).append(disagreement)
            row["authoritative_semantic_progress"] = False
            row["hard_stop_required"] = True
        if registry_label_correction:
            row["registry_idempotent_replay"] = False
            row["registry_label_correction"] = True
            row["correction_of_attempt_identity"] = (
                supersedes_attempt_identity_candidate or attempt_identity
            )
            row["attempt_revision_candidate"] = attempt_revision_candidate
            row["supersedes_attempt_revision_candidate"] = supersedes_attempt_revision_candidate
            row["supersedes_attempt_identity_candidate"] = supersedes_attempt_identity_candidate
            return row, compact_registry([*registry_rows, dict(row)], args.max_rows_per_family), True
        return row, registry_rows, False
    registry_row = dict(row)
    return row, compact_registry([*registry_rows, registry_row], args.max_rows_per_family), True
