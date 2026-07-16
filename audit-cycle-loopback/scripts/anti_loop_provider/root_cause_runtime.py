from __future__ import annotations

from .common import *

def apply_root_cause_ledger(ns: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    globals().update(ns)
    root_cause_ledger_path = Path(getattr(args, "root_cause_ledger_path", ROOT_CAUSE_LEDGER_REL_PATH))
    if not root_cause_ledger_path.is_absolute():
        root_cause_ledger_path = root / root_cause_ledger_path
    hypotheses_prefetched = "root_cause_hypotheses_value" in ns
    hypotheses_value = (
        ns.get("root_cause_hypotheses_value")
        if hypotheses_prefetched
        else load_json_value(root, getattr(args, "root_cause_hypotheses_json", None))
    )
    root_cause_adapter_error: str | None = (
        ns.get("root_cause_hypotheses_error") if hypotheses_prefetched else None
    )
    if hypotheses_value is None and not hypotheses_prefetched:
        hypotheses_value, root_cause_adapter_error = call_adapter(
            domain_adapter,
            "root_cause_hypotheses",
            root=root,
            artifact_paths=[rel_path(root, path) for path in paths],
            quality_vector=quality,
            output_delta=output_delta,
            runner_validation=runner_validation,
            family_key=family_key,
            root_key=current_root_key,
            root_family_key=current_root_family_key,
            blocker_signature=current_blocker_signature,
            blocker_ladder_rung=current_rung,
        )
    hypotheses = normalize_root_cause_hypotheses(hypotheses_value)
    if getattr(args, "hypothesized_root_cause", None):
        hypotheses.append(
            {
                "hypothesized_root_cause": normalize_root_cause_slug(args.hypothesized_root_cause),
                "repair_attempted": bool_value(getattr(args, "root_cause_repair_attempted", False)),
                "repair_task_id": getattr(args, "root_cause_repair_task_id", None),
                "actionable": bool_value(getattr(args, "root_cause_actionable", False)),
            }
        )
    ledger_entries: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        repair_task_id_raw = (
            hypothesis.get("repair_task_id")
            or hypothesis.get("task_id")
            or getattr(args, "root_cause_repair_task_id", None)
        )
        repair_task_id = str(repair_task_id_raw).strip() if repair_task_id_raw is not None else ""
        if repair_task_id.lower() in {"", "unknown", "none", "null"}:
            repair_task_id = ""
        repair_attempted = (
            bool_value(hypothesis.get("repair_attempted"))
            or bool_value(getattr(args, "root_cause_repair_attempted", False))
            or bool(repair_task_id)
        )
        hypothesis_evidence_paths = sorted(set(string_list(hypothesis.get("evidence_paths")) + evidence_paths))
        entry: dict[str, Any] = {
            "schema_version": "root-cause-hypothesis-ledger-v1",
            "cycle_id": args.cycle_id,
            "attempt_identity": attempt_identity,
            "input_state_fingerprint": input_state_fingerprint,
            "family_key": str(hypothesis.get("family_key") or family_key),
            "root_key": str(hypothesis.get("root_key") or current_root_key),
            "root_family_key": str(hypothesis.get("root_family_key") or current_root_family_key),
            "hypothesized_root_cause": normalize_root_cause_slug(hypothesis.get("hypothesized_root_cause")),
            "target_surface": str(hypothesis.get("target_surface") or current_blocker_signature or current_root_key),
            "blocker_signature": current_blocker_signature,
            "repair_attempted": repair_attempted,
            "repair_task_id": repair_task_id or None,
            "terminal_outcome_changed": outcome_changed,
            "observed_delta_class": hypothesis.get("observed_delta_class") or delta_class,
            "local": bool_value(hypothesis.get("local")),
            "bounded": bool_value(hypothesis.get("bounded")),
            "provider_free": bool_value(hypothesis.get("provider_free") or hypothesis.get("provider-free")),
            "in_scope": bool_value(hypothesis.get("in_scope")),
            "authority_allowed": bool_value(hypothesis.get("authority_allowed")),
            "actionable": bool_value(hypothesis.get("actionable") or hypothesis.get("root_cause_actionable")),
            "provenance_refs": root_cause_provenance_refs({**hypothesis, "evidence_paths": hypothesis_evidence_paths}),
            "evidence_paths": hypothesis_evidence_paths,
            "updated_at": now_iso(),
        }
        actionability = harden_repo_owned_actionability(
            entry,
            root=root,
            repo_owned_source_roots=repo_owned_source_roots,
        )
        entry["actionability_status"] = actionability["status"]
        entry["actionability_basis"] = actionability["basis"]
        ledger_entries.append(entry)
    if finalized_state_status == "invalid":
        existing_root_cause_rows = []
        root_cause_state_source = "invalid_finalized_state"
    elif finalized_root_cause_present:
        existing_root_cause_rows = list(finalized_root_cause_rows)
        root_cause_state_source = "verified_finalization"
    else:
        existing_root_cause_rows = read_jsonl(root_cause_ledger_path)
        root_cause_state_source = "legacy_ledger_fallback"
    root_cause_rows = compact_root_cause_ledger(
        [*existing_root_cause_rows, *ledger_entries],
        getattr(args, "max_root_cause_rows_per_family", ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT),
    )
    root_cause_gate = root_cause_hypothesis_gate(
        root_cause_rows,
        family_key,
        current_root_key,
        current_root_family_key,
        getattr(args, "untried_promotion_budget", None),
        root=root,
        repo_owned_source_roots=repo_owned_source_roots,
    )
    untried = root_cause_gate["untried_root_cause_hypotheses"]
    row["root_cause_ledger_path"] = rel_path(root, root_cause_ledger_path)
    row["root_cause_ledger_status"] = (
        "prepared_not_finalized" if ledger_entries else "not_applicable_no_hypotheses"
    )
    row["root_cause_ledger_updated"] = False
    row["root_cause_ledger_update_candidate"] = bool(ledger_entries)
    row["root_cause_ledger_entries"] = ledger_entries
    row["root_cause_ledger_projection"] = root_cause_rows
    row["root_cause_ledger_state_source"] = root_cause_state_source
    row["root_cause_unverified_hypotheses"] = root_cause_gate["root_cause_unverified_hypotheses"][:10]
    row["root_cause_duplicate_hypotheses"] = root_cause_gate["root_cause_duplicate_hypotheses"][:10]
    row["untried_promotion_budget"] = root_cause_gate["untried_promotion_budget"]
    row["root_cause_budget_evaluation"] = root_cause_gate["budget_evaluation"]
    row["root_cause_budget_evaluation_status"] = root_cause_gate[
        "budget_evaluation_status"
    ]
    row["vacuous_untried_attempt_count"] = root_cause_gate["vacuous_untried_attempt_count"]
    row["vacuous_untried_streak"] = root_cause_gate["vacuous_untried_streak"]
    row["hypothesis_exhausted"] = root_cause_gate["hypothesis_exhausted"]
    row["untried_actionable_root_cause_exists"] = bool(untried)
    row["untried_root_cause_hypotheses"] = untried[:10]
    chain_untried_override = (
        bool(untried)
        and bool_value(row.get("cumulative_goal_distance_stalled"))
        and not bool_value(row.get("adapter_mandate_required"))
    )
    row["cumulative_untried_chain_without_quality_delta"] = chain_untried_override
    row["untried_veto_overridden_by_chain_stall"] = chain_untried_override
    row["terminal_blocked_invalid_due_to_untried_root_cause"] = bool(untried) and not chain_untried_override
    if root_cause_adapter_error:
        row["root_cause_ledger_adapter_error"] = root_cause_adapter_error
    seal_path = root / ".task" / "sealed_blocker_families.json"
    if finalized_state_status == "invalid":
        existing_seal_state = {}
        seal_state_source = "invalid_finalized_state"
    elif finalized_seal_present:
        existing_seal_state = finalized_seal_state
        seal_state_source = "verified_finalization"
    else:
        existing_seal_state = read_json(seal_path)
        seal_state_source = "legacy_seal_fallback"
    if row["hypothesis_exhausted"]:
        row["hypothesis_exhaustion_seal_path"] = rel_path(root, seal_path)
        row["hypothesis_exhaustion_seal_status"] = "prepared_not_finalized"
        row["hypothesis_exhaustion_seal_candidate"] = exhausted_family_seal_record(row)
        row["sealed_blocker_families_projection"] = project_exhausted_family_seal(
            existing_seal_state,
            row,
        )
    elif isinstance(existing_seal_state, dict):
        row["sealed_blocker_families_projection"] = existing_seal_state
    else:
        row["sealed_blocker_families_projection"] = {
            "schema_version": "sealed-blocker-families-v1",
            "families": [],
        }
    row["sealed_blocker_families_state_source"] = seal_state_source
    return chain_untried_override, untried, ledger_entries
