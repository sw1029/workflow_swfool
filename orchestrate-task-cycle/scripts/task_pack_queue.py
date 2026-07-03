#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


PACK_STATUSES = {"active", "completed", "blocked", "terminal_blocked", "superseded"}
ITEM_STATUSES = {
    "planned",
    "promoted",
    "in_progress",
    "consumed",
    "inserted",
    "reordered",
    "skipped",
    "blocked",
    "terminal_blocked",
    "superseded",
}
VALIDATION_PROFILES = {"current_only", "affected_chain", "full_chain"}
PROGRESS_TARGETS = {"advanced", "safety_only", "no_progress", "regressed"}
PROGRESS_KINDS = {"goal_productive", "governance_only"}
OPEN_RESIDUAL_STATUSES = {"planned", "promoted", "in_progress", "inserted", "reordered", "blocked"}


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def pack_dir(root: Path) -> Path:
    return root / ".task" / "task_pack"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load task pack {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Task pack must be a JSON object: {path}")
    return value


def load_plan(value: str | None) -> dict[str, Any]:
    if not value or value == "-":
        raw = sys.stdin.read()
        plan = json.loads(raw) if raw.strip() else {}
    else:
        stripped = value.strip()
        if stripped.startswith("{"):
            plan = json.loads(stripped)
        else:
            path = Path(stripped)
            plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise SystemExit("Mutation plan must be a JSON object.")
    return plan


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "passed", "pass", "met", "ok"}
    return bool(value)


def non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def scope_fidelity_records(item: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    value = item.get("scope_fidelity", item.get("scope_fidelity_records"))
    if value is None:
        return [], True
    if isinstance(value, dict):
        return [value], True
    if isinstance(value, list) and all(isinstance(record, dict) for record in value):
        return value, True
    return [], False


def write_json(path: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pack_paths(root: Path) -> list[Path]:
    directory = pack_dir(root)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)


def validate_pack(data: dict[str, Any], path: Path | None = None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(severity: str, code: str, message: str, evidence: Any = None) -> None:
        item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
        if evidence is not None:
            item["evidence"] = evidence
        findings.append(item)

    for field in ("schema_version", "pack_id", "status", "goal", "items", "mutation_log"):
        if field not in data:
            add("block", "missing_required_field", f"Task pack is missing `{field}`.", {"path": str(path) if path else None})
    if data.get("schema_version") != 1:
        add("block", "unsupported_schema_version", "`schema_version` must be 1.", {"value": data.get("schema_version")})
    status = data.get("status")
    if status not in PACK_STATUSES:
        add("block", "invalid_pack_status", "Invalid task pack status.", {"status": status})

    items = data.get("items")
    if not isinstance(items, list) or not items:
        add("block", "items_missing", "`items` must be a non-empty list.")
        return findings

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    item_by_id: dict[str, dict[str, Any]] = {}
    residual_links: list[tuple[str, str]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            add("block", "invalid_item", "Task pack item must be an object.", {"index": index})
            continue
        for field in ("item_id", "order", "status", "title", "objective", "validation_profile", "progress_target"):
            if field not in item:
                add("block", "missing_item_field", f"Task pack item is missing `{field}`.", {"index": index})
        item_id = str(item.get("item_id") or "")
        if not item_id:
            add("block", "empty_item_id", "Task pack item has empty item_id.", {"index": index})
        elif item_id in seen_ids:
            add("block", "duplicate_item_id", "Task pack item_id is duplicated.", {"item_id": item_id})
        seen_ids.add(item_id)
        if item_id:
            item_by_id[item_id] = item
        order = item.get("order")
        if not isinstance(order, int) or order <= 0:
            add("block", "invalid_item_order", "Task pack item order must be a positive integer.", {"item_id": item_id, "order": order})
        elif order in seen_orders:
            add("block", "duplicate_item_order", "Task pack item order is duplicated.", {"order": order})
        seen_orders.add(order) if isinstance(order, int) else None
        if item.get("status") not in ITEM_STATUSES:
            add("block", "invalid_item_status", "Invalid task pack item status.", {"item_id": item_id, "status": item.get("status")})
        if item.get("validation_profile") not in VALIDATION_PROFILES:
            add("warn", "invalid_validation_profile", "Unexpected validation profile.", {"item_id": item_id, "validation_profile": item.get("validation_profile")})
        if item.get("progress_target") not in PROGRESS_TARGETS:
            add("warn", "invalid_progress_target", "Unexpected progress target.", {"item_id": item_id, "progress_target": item.get("progress_target")})
        progress_kind_expected = item.get("progress_kind_expected")
        if progress_kind_expected is not None and progress_kind_expected not in PROGRESS_KINDS:
            add(
                "warn",
                "invalid_progress_kind_expected",
                "`progress_kind_expected` should be goal_productive or governance_only.",
                {"item_id": item_id, "progress_kind_expected": progress_kind_expected},
            )
        if progress_kind_expected == "goal_productive" and item.get("progress_target") in {"safety_only", "no_progress"}:
            add(
                "warn",
                "progress_kind_target_mismatch",
                "A goal_productive pack item should not declare a safety_only/no_progress progress target.",
                {"item_id": item_id, "progress_target": item.get("progress_target")},
            )
        if item.get("positive_input_delta_required") is True and not item.get("required_new_input_kinds"):
            add("block", "positive_delta_kinds_missing", "Positive input delta gate requires `required_new_input_kinds`.", {"item_id": item_id})
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        if item.get("positive_input_delta_required") is True and item.get("status") in {"consumed", "terminal_blocked"}:
            gate = result.get("positive_input_delta_gate") if isinstance(result.get("positive_input_delta_gate"), dict) else {}
            has_supplied = bool(
                result.get("has_supplied_input_delta")
                or gate.get("has_supplied_input_delta")
                or result.get("produced_domain_delta")
                or gate.get("produced_domain_delta")
                or result.get("supplied_input_artifact_paths")
                or gate.get("supplied_input_artifact_paths")
            )
            if not has_supplied:
                add(
                    "warn",
                    "consumed_item_missing_supplied_input_delta",
                    "Consumed evidence-family pack items should record a supplied input artifact or produced_domain_delta=true; derive/result-contract gates enforce this for new progress claims.",
                    {"item_id": item_id},
                )

        records, valid_scope_shape = scope_fidelity_records(item)
        if not valid_scope_shape:
            add("block", "scope_fidelity_invalid", "`scope_fidelity` must be an object or a list of objects.", {"item_id": item_id})
            records = []
        for record_index, record in enumerate(records):
            directive_id = str(record.get("directive_id") or "").strip()
            original_target = record.get("original_target", record.get("measurable_target"))
            item_acceptance = record.get("item_acceptance", item.get("acceptance"))
            has_target = non_empty(original_target)
            narrowed = truthy(record.get("narrowed"))
            residual_item_id = str(record.get("residual_item_id") or "").strip()
            verifier_contract = (
                record.get("acceptance_verifier_contract")
                if isinstance(record.get("acceptance_verifier_contract"), dict)
                else item.get("acceptance_verifier_contract") if isinstance(item.get("acceptance_verifier_contract"), dict)
                else {}
            )

            if has_target and not directive_id:
                add(
                    "block",
                    "scope_fidelity_directive_id_missing",
                    "Measurable scope_fidelity records require `directive_id`.",
                    {"item_id": item_id, "record_index": record_index},
                )
            if has_target and not non_empty(item_acceptance):
                add(
                    "block",
                    "scope_fidelity_item_acceptance_missing",
                    "Measurable scope_fidelity records require item acceptance copied from or traceable to the directive target.",
                    {"item_id": item_id, "directive_id": directive_id or None},
                )
            if narrowed:
                if not non_empty(record.get("narrow_reason")):
                    add(
                        "block",
                        "scope_fidelity_narrow_reason_missing",
                        "Narrowed measurable directives require `narrow_reason`.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                if not residual_item_id:
                    add(
                        "block",
                        "scope_fidelity_residual_item_missing",
                        "Narrowed measurable directives require `residual_item_id` so remaining scope stays open.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                else:
                    residual_links.append((item_id, residual_item_id))

            if has_target and item.get("status") == "consumed":
                acceptance_gate = result.get("acceptance_provenance_gate") if isinstance(result.get("acceptance_provenance_gate"), dict) else {}
                acceptance_gate = acceptance_gate or (result.get("scope_fidelity_gate") if isinstance(result.get("scope_fidelity_gate"), dict) else {})
                if not acceptance_gate:
                    add(
                        "block",
                        "acceptance_provenance_gate_missing",
                        "Consumed measurable pack items require an `acceptance_provenance_gate` result comparing actual achievement to the original directive target.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                    continue
                if truthy(acceptance_gate.get("acceptance_diluted")):
                    add(
                        "block",
                        "acceptance_diluted_item_consumed",
                        "A pack item with `acceptance_diluted=true` cannot be `consumed`; keep the residual target open and mark validation partial.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                target_met = truthy(acceptance_gate.get("target_met"))
                explicit_descope = truthy(acceptance_gate.get("explicit_descope_decision"))
                if not target_met and not explicit_descope:
                    add(
                        "block",
                        "measurable_target_unmet_without_descope",
                        "Consumed measurable pack items must meet the original target or record an explicit descope decision with residual scope.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                verifier_gate = result.get("acceptance_verifier_gate") if isinstance(result.get("acceptance_verifier_gate"), dict) else {}
                verifier_gate = verifier_gate or (
                    result.get("acceptance_verifier_contract")
                    if isinstance(result.get("acceptance_verifier_contract"), dict)
                    else {}
                )
                verifier_required = truthy(
                    verifier_contract.get("verifier_required")
                    or verifier_contract.get("required")
                    or verifier_gate.get("verifier_required")
                    or verifier_gate.get("required")
                ) or non_empty(verifier_contract.get("required_verifier")) or non_empty(verifier_gate.get("required_verifier"))
                evaluation_status = str(
                    verifier_gate.get("evaluation_status")
                    or verifier_contract.get("evaluation_status")
                    or ""
                ).strip().lower()
                required_hooks = (
                    verifier_gate.get("required_gate_hooks")
                    or verifier_contract.get("required_gate_hooks")
                    or record.get("required_gate_hooks")
                    or item.get("required_gate_hooks")
                )
                hook_status = str(
                    verifier_gate.get("gate_hook_status")
                    or verifier_contract.get("gate_hook_status")
                    or record.get("gate_hook_status")
                    or item.get("gate_hook_status")
                    or ""
                ).strip().lower()
                pass_with_coupled_verifier = truthy(
                    verifier_gate.get("pass_with_coupled_verifier")
                    or verifier_contract.get("pass_with_coupled_verifier")
                    or result.get("pass_with_coupled_verifier")
                    or (
                        result.get("coupled_verifier_gate", {}).get("pass_with_coupled_verifier")
                        if isinstance(result.get("coupled_verifier_gate"), dict)
                        else False
                    )
                )
                if verifier_required and (evaluation_status != "pass" or pass_with_coupled_verifier) and not explicit_descope:
                    add(
                        "block",
                        "acceptance_verifier_not_passed_item_consumed",
                        "Consumed measurable pack items require each required live verifier to pass without same-changeset verifier-source coupling, or an explicit descope decision with residual scope.",
                        {
                            "item_id": item_id,
                            "directive_id": directive_id or None,
                            "evaluation_status": evaluation_status or None,
                            "pass_with_coupled_verifier": pass_with_coupled_verifier,
                        },
                    )
                if non_empty(required_hooks) and hook_status in {"", "not_supplied", "absent", "missing", "fail_quiet", "not_evaluated"} and not explicit_descope:
                    add(
                        "block",
                        "required_gate_hook_missing_item_consumed",
                        "Consumed measurable pack items cannot depend on an acceptance-required gate hook that is absent, fail-quiet, or not_evaluated; preserve hook-supply work or residual scope.",
                        {
                            "item_id": item_id,
                            "directive_id": directive_id or None,
                            "gate_hook_status": hook_status or None,
                        },
                    )
                goal_axis_contract = (
                    record.get("goal_axis_contract")
                    if isinstance(record.get("goal_axis_contract"), dict)
                    else item.get("goal_axis_contract") if isinstance(item.get("goal_axis_contract"), dict)
                    else {}
                )
                goal_axis_gate = result.get("goal_axis_completeness_gate") if isinstance(result.get("goal_axis_completeness_gate"), dict) else {}
                pass_with_unobserved_axes = truthy(
                    goal_axis_gate.get("pass_with_unobserved_axes")
                    or goal_axis_contract.get("pass_with_unobserved_axes")
                    or result.get("pass_with_unobserved_axes")
                    or item.get("pass_with_unobserved_axes")
                )
                unobserved_goal_axes = (
                    goal_axis_gate.get("unobserved_goal_axes")
                    or goal_axis_contract.get("unobserved_goal_axes")
                    or result.get("unobserved_goal_axes")
                    or item.get("unobserved_goal_axes")
                )
                if (pass_with_unobserved_axes or non_empty(unobserved_goal_axes)) and not explicit_descope:
                    add(
                        "block",
                        "unobserved_goal_axes_item_consumed",
                        "Consumed review-backed measurable pack items require at least one mapped observing axis per active goal, or explicit residual/descope handling.",
                        {
                            "item_id": item_id,
                            "directive_id": directive_id or None,
                            "unobserved_goal_axes": unobserved_goal_axes or None,
                        },
                    )
                evidence_gate = result.get("evidence_provenance_gate") if isinstance(result.get("evidence_provenance_gate"), dict) else {}
                attested_only = truthy(result.get("attested_only_movement") or evidence_gate.get("attested_only_movement"))
                producer_attested = result.get("producer_attested_fields") or evidence_gate.get("producer_attested_fields")
                independently_verified = result.get("independently_verified_fields") or evidence_gate.get("independently_verified_fields")
                if (attested_only or (producer_attested and not independently_verified)) and not explicit_descope:
                    add(
                        "block",
                        "producer_attested_progress_item_consumed",
                        "Consumed measurable pack items cannot rely on producer-attested metric movement without independently verified evidence or explicit residual descope.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                verification_gate = result.get("verification_source_separation_gate") if isinstance(result.get("verification_source_separation_gate"), dict) else {}
                independent_source_status = str(
                    result.get("independent_source_separation_status")
                    or verification_gate.get("independent_source_separation_status")
                    or evidence_gate.get("independent_source_separation_status")
                    or ""
                ).strip().lower()
                independently_verified_downgraded = (
                    result.get("independently_verified_downgraded_fields")
                    or verification_gate.get("independently_verified_downgraded_fields")
                    or evidence_gate.get("independently_verified_downgraded_fields")
                )
                if independently_verified and independent_source_status in {"missing", "overlap", "blocked"} and not explicit_descope:
                    add(
                        "block",
                        "independent_verification_source_not_disjoint_item_consumed",
                        "Consumed measurable pack items cannot rely on independently_verified evidence unless verification_input_paths are disjoint from verified artifacts or the axis is self_grounded.",
                        {
                            "item_id": item_id,
                            "directive_id": directive_id or None,
                            "independent_source_separation_status": independent_source_status,
                        },
                    )
                if non_empty(independently_verified_downgraded) and not explicit_descope:
                    add(
                        "block",
                        "downgraded_independent_verification_item_consumed",
                        "Consumed measurable pack items cannot count independently_verified fields that were auto-downgraded to attested.",
                        {"item_id": item_id, "directive_id": directive_id or None, "downgraded_fields": independently_verified_downgraded},
                    )
                reachability_gate = result.get("acceptance_reachability_gate") if isinstance(result.get("acceptance_reachability_gate"), dict) else {}
                envelope_thaw_required = truthy(result.get("envelope_thaw_item_required") or reachability_gate.get("envelope_thaw_item_required"))
                envelope_thaw_item = result.get("envelope_thaw_item") or reachability_gate.get("envelope_thaw_item")
                if envelope_thaw_required and not (explicit_descope or non_empty(envelope_thaw_item)):
                    add(
                        "block",
                        "envelope_thaw_item_missing_item_consumed",
                        "Consumed measurable pack items cannot close acceptance that is unreachable under a frozen envelope without a reserved envelope_thaw_item or explicit residual/descope handling.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                diagnostics_gate = result.get("diagnostics_unavailable_gate") if isinstance(result.get("diagnostics_unavailable_gate"), dict) else {}
                instrumentation_required = truthy(result.get("instrumentation_supply_required") or diagnostics_gate.get("instrumentation_supply_required"))
                observable_without_instrumentation = truthy(
                    result.get("diagnostics_observable_without_new_instrumentation")
                    or result.get("existing_diagnostics_sufficient")
                    or result.get("success_failure_observable_without_instrumentation")
                )
                if instrumentation_required and not observable_without_instrumentation and not explicit_descope:
                    add(
                        "block",
                        "instrumentation_supply_missing_item_consumed",
                        "Consumed measurable pack items cannot close repeated diagnostics_unavailable without instrumentation supply or an explicit observability rationale.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                marginal_repair = truthy(record.get("marginal_repair") or item.get("marginal_repair"))
                next_rung = record.get("next_capability_rung") or item.get("next_capability_rung")
                higher_value = truthy(record.get("marginal_repair_higher_value") or item.get("marginal_repair_higher_value"))
                cost_policy = result.get("residual_gap_cost_policy") if isinstance(result.get("residual_gap_cost_policy"), dict) else {}
                residual_cost_below_policy = truthy(
                    record.get("residual_gap_cost_below_policy")
                    or item.get("residual_gap_cost_below_policy")
                    or result.get("residual_gap_cost_below_policy")
                    or cost_policy.get("below_policy")
                    or cost_policy.get("cost_disproportionate")
                )
                cycle_fixed_cost = record.get("cycle_fixed_cost") or item.get("cycle_fixed_cost") or result.get("cycle_fixed_cost") or cost_policy.get("cycle_fixed_cost")
                marginal_value_per_cycle_cost = (
                    record.get("marginal_value_per_cycle_cost")
                    or item.get("marginal_value_per_cycle_cost")
                    or result.get("marginal_value_per_cycle_cost")
                    or cost_policy.get("marginal_value_per_cycle_cost")
                )
                if marginal_repair and item.get("status") == "consumed" and not (explicit_descope and non_empty(next_rung)) and not higher_value:
                    add(
                        "block",
                        "marginal_repair_item_consumed_without_value_case",
                        "Consumed below-threshold residual-gap repairs require explicit descope plus the next capability rung, or recorded higher marginal value.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                if cycle_fixed_cost is not None and marginal_repair and not non_empty(marginal_value_per_cycle_cost):
                    add(
                        "block",
                        "residual_cycle_cost_ratio_missing_item_consumed",
                        "Consumed residual-gap repairs with cycle-cost evidence require `marginal_value_per_cycle_cost`.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                if residual_cost_below_policy and not (explicit_descope and non_empty(next_rung)) and not higher_value:
                    add(
                        "block",
                        "residual_cost_below_policy_item_consumed",
                        "Consumed residual-gap repairs below value-per-cycle-cost policy require residual descope plus the next capability rung, or recorded higher value.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                count_key_gate = result.get("count_key_hygiene_gate") if isinstance(result.get("count_key_hygiene_gate"), dict) else {}
                generation_dependent_count_key = truthy(
                    result.get("generation_dependent_count_key")
                    or count_key_gate.get("generation_dependent_count_key")
                    or item.get("generation_dependent_count_key")
                )
                generation_key_reset_claim = truthy(
                    result.get("family_novelty_claim")
                    or result.get("stall_reset_claim")
                    or count_key_gate.get("family_novelty_claim")
                    or count_key_gate.get("stall_reset_claim")
                )
                effective_count_key = result.get("effective_count_key") or count_key_gate.get("effective_count_key") or result.get("terminal_outcome_family_key")
                if generation_dependent_count_key and not non_empty(effective_count_key):
                    add(
                        "block",
                        "generation_count_key_without_effective_key_item_consumed",
                        "Consumed pack items with generation-dependent raw keys must preserve an effective adapter-collapsed count key or terminal-outcome fallback.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )
                if generation_dependent_count_key and generation_key_reset_claim:
                    add(
                        "block",
                        "generation_key_reset_claim_item_consumed",
                        "Consumed pack items cannot treat task/advice/pack/cycle/run/date/hash/version churn as a new family or stall reset.",
                        {"item_id": item_id, "directive_id": directive_id or None},
                    )

    for item_id, residual_item_id in residual_links:
        residual = item_by_id.get(residual_item_id)
        if residual is None:
            add(
                "block",
                "scope_fidelity_residual_item_unknown",
                "`residual_item_id` must reference another pack item.",
                {"item_id": item_id, "residual_item_id": residual_item_id},
            )
        elif residual.get("status") not in OPEN_RESIDUAL_STATUSES:
            add(
                "block",
                "scope_fidelity_residual_item_not_open",
                "`residual_item_id` must remain open when the current item narrows a measurable directive.",
                {"item_id": item_id, "residual_item_id": residual_item_id, "residual_status": residual.get("status")},
            )

    current = data.get("current_item_id")
    if current and current not in seen_ids:
        add("block", "current_item_missing", "`current_item_id` does not match any item.", {"current_item_id": current})
    if data.get("status") == "terminal_blocked" and not data.get("terminal_blocker"):
        add("block", "terminal_blocker_missing", "`terminal_blocked` pack requires `terminal_blocker`.")
    terminal = data.get("terminal_blocker")
    if isinstance(terminal, dict):
        for field in ("semantic_signature", "blocker_signature", "required_handoff", "evidence_paths"):
            if not terminal.get(field):
                add("block", "terminal_blocker_field_missing", f"`terminal_blocker` requires `{field}`.", {"field": field})
        if terminal.get("provider_reattempt_required") is True:
            add(
                "block",
                "provider_terminal_seal_before_bounded_retry",
                "Task pack cannot terminal-block a provider family while bounded provider retry is still required.",
            )
        if terminal.get("authorized_alternative_path_exists") is True and not terminal.get("authorized_alternative_path_attempted"):
            add(
                "block",
                "seal_denied_authorized_alternative_unattempted",
                "Task pack cannot seal a family while an authority-permitted productive alternative remains unattempted.",
            )
        if terminal.get("untried_actionable_root_cause_exists") is True:
            add(
                "block",
                "seal_denied_untried_actionable_root_cause",
                "Task pack cannot terminal-block while a local, bounded, provider-free, in-scope, authority-allowed root-cause hypothesis remains untried.",
            )
        if terminal.get("terminal_quiescence") is True and terminal.get("commit_skipped_reason") != "terminal_quiescence":
            add(
                "warn",
                "terminal_quiescence_missing_commit_skip_reason",
                "Terminal quiescence should record `commit_skipped_reason: terminal_quiescence` to prevent closeout/report/recheck reproduction.",
            )
    if not isinstance(data.get("mutation_log", []), list):
        add("block", "mutation_log_invalid", "`mutation_log` must be a list.")
    return findings


def status_from_findings(findings: list[dict[str, Any]]) -> str:
    if any(item.get("severity") == "block" for item in findings):
        return "block"
    if findings:
        return "warn"
    return "ok"


def active_pack(root: Path) -> tuple[Path | None, dict[str, Any] | None]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in pack_paths(root):
        data = load_json(path)
        loaded.append((path, data))
        if data.get("status") == "active":
            return path, data
    return loaded[0] if loaded else (None, None)


def sorted_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted((item for item in data.get("items", []) if isinstance(item, dict)), key=lambda item: item.get("order", 0))


def item_order(data: dict[str, Any]) -> list[str]:
    return [str(item.get("item_id")) for item in sorted_items(data) if item.get("item_id")]


def renumber_items(data: dict[str, Any]) -> None:
    for index, item in enumerate(sorted_items(data), start=1):
        item["order"] = index


def planned_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in sorted_items(data) if item.get("status") in {"planned", "inserted", "reordered", "blocked"}]


def refresh_current_item(data: dict[str, Any]) -> None:
    remaining = [item for item in planned_items(data) if item.get("status") in {"planned", "inserted", "reordered"}]
    data["current_item_id"] = remaining[0].get("item_id") if remaining else None
    if not remaining and data.get("status") == "active":
        data["status"] = "completed"


def evidence_paths_from(plan: dict[str, Any]) -> list[str]:
    value = plan.get("evidence_paths") or plan.get("evidence") or []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def mutation_entry(action: str, plan: dict[str, Any], before_order: list[str], after_order: list[str]) -> dict[str, Any]:
    reason = str(plan.get("reason") or plan.get("mutation_reason") or "").strip()
    if not reason:
        raise SystemExit("Mutation plan requires `reason`.")
    return {
        "timestamp": now_iso(),
        "action": action,
        "reason": reason,
        "evidence_paths": evidence_paths_from(plan),
        "before_order": before_order,
        "after_order": after_order,
        "actor": "$derive-improvement-task",
    }


def next_item(data: dict[str, Any]) -> dict[str, Any] | None:
    current = data.get("current_item_id")
    items = sorted_items(data)
    if current:
        for item in items:
            if item.get("item_id") == current and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                return item
    for item in items:
        if item.get("status") in {"planned", "inserted", "reordered"}:
            return item
    return None


def render_markdown(root: Path, path: Path, data: dict[str, Any], language: str) -> str:
    ko = language.lower().startswith("ko")
    title = "Task Pack" if not ko else "Task Pack"
    labels = {
        "status": "Status" if not ko else "상태",
        "goal": "Goal" if not ko else "목표",
        "current": "Current Item" if not ko else "현재 item",
        "terminal": "Terminal Blocker" if not ko else "terminal blocker",
        "items": "Items" if not ko else "Items",
        "mutations": "Mutation Log" if not ko else "Mutation Log",
    }
    lines = [
        f"# {title}: {data.get('pack_id', path.stem)}",
        "",
        f"- {labels['status']}: {data.get('status')}",
        f"- {labels['goal']}: {data.get('goal')}",
        f"- {labels['current']}: {data.get('current_item_id') or 'none'}",
        f"- JSON: `{rel_path(root, path)}`",
        "",
        f"## {labels['items']}",
        "",
    ]
    for item in sorted_items(data):
        scope_records, _ = scope_fidelity_records(item)
        scope_summary = "none"
        if scope_records:
            parts = []
            for record in scope_records:
                directive_id = str(record.get("directive_id") or "unknown")
                narrowed = "narrowed" if truthy(record.get("narrowed")) else "full"
                residual = str(record.get("residual_item_id") or "none")
                parts.append(f"{directive_id}:{narrowed}:residual={residual}")
            scope_summary = "; ".join(parts)
        lines.extend(
            [
                f"### {item.get('order')}. {item.get('title')}",
                "",
                f"- item_id: `{item.get('item_id')}`",
                f"- status: `{item.get('status')}`",
                f"- progress_target: `{item.get('progress_target')}`",
                f"- progress_kind_expected: `{item.get('progress_kind_expected') or 'none'}`",
                f"- validation_profile: `{item.get('validation_profile')}`",
                f"- semantic_signature_expected: `{item.get('semantic_signature_expected') or 'none'}`",
                f"- positive_input_delta_required: `{item.get('positive_input_delta_required', False)}`",
                f"- required_new_input_kinds: {', '.join(str(value) for value in item.get('required_new_input_kinds', [])) or 'none'}",
                f"- scope_fidelity: {scope_summary}",
                "",
                str(item.get("objective") or "").strip(),
                "",
            ]
        )
    if data.get("terminal_blocker"):
        lines.extend([f"## {labels['terminal']}", "", "```json", json.dumps(data["terminal_blocker"], ensure_ascii=False, indent=2, sort_keys=True), "```", ""])
    if data.get("mutation_log"):
        lines.extend([f"## {labels['mutations']}", ""])
        for mutation in data.get("mutation_log", []):
            if isinstance(mutation, dict):
                lines.append(f"- {mutation.get('timestamp')}: {mutation.get('action')} - {mutation.get('reason')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_path(path: Path) -> Path:
    return path.with_suffix(".md")


def command_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path, data = active_pack(root)
    if not path or not data:
        output = {"status": "not_applicable", "active_pack": None, "pack_count": 0}
    else:
        findings = validate_pack(data, path)
        item = next_item(data)
        output = {
            "status": status_from_findings(findings),
            "active_pack": rel_path(root, path),
            "render_path": rel_path(root, render_path(path)) if render_path(path).exists() else None,
            "pack_id": data.get("pack_id"),
            "pack_status": data.get("status"),
            "goal": data.get("goal"),
            "current_item_id": data.get("current_item_id"),
            "next_item": item,
            "planned_item_count": sum(1 for item_data in data.get("items", []) if isinstance(item_data, dict) and item_data.get("status") in {"planned", "inserted", "reordered"}),
            "terminal_blocker": data.get("terminal_blocker"),
            "findings": findings,
            "pack_count": len(pack_paths(root)),
        }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] not in {"block"} else 2


def command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = [root / args.pack] if args.pack else pack_paths(root)
    results = []
    status = "ok"
    for path in paths:
        data = load_json(path)
        findings = validate_pack(data, path)
        result_status = status_from_findings(findings)
        if result_status == "block":
            status = "block"
        elif result_status == "warn" and status == "ok":
            status = "warn"
        results.append({"path": rel_path(root, path), "status": result_status, "findings": findings})
    output = {"status": status, "results": results, "pack_count": len(results)}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if status != "block" else 2


def command_render(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    paths = [root / args.pack] if args.pack else pack_paths(root)
    rendered = []
    for path in paths:
        data = load_json(path)
        findings = validate_pack(data, path)
        if any(item.get("severity") == "block" for item in findings):
            rendered.append({"path": rel_path(root, path), "status": "block", "findings": findings})
            continue
        output_path = render_path(path)
        output_path.write_text(render_markdown(root, path, data, args.language), encoding="utf-8")
        rendered.append({"path": rel_path(root, path), "status": "rendered", "render_path": rel_path(root, output_path), "findings": findings})
    output = {"status": "block" if any(item["status"] == "block" for item in rendered) else "ok", "rendered": rendered}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if output["status"] != "block" else 2


def command_next(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path, data = active_pack(root)
    if not path or not data:
        output = {"status": "not_applicable", "next_item": None}
    else:
        item = next_item(data)
        output = {
            "status": "ok" if item else "terminal_candidate",
            "pack_path": rel_path(root, path),
            "pack_id": data.get("pack_id"),
            "next_item": item,
            "terminal_blocker": data.get("terminal_blocker"),
        }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def normalize_action(action: str) -> str:
    normalized = action.strip().lower()
    mapping = {
        "insert_items": "insert",
        "insert_item": "insert",
        "reorder_items": "reorder",
        "skip_items": "skip",
        "exclude_items": "skip",
        "supersede_pack": "supersede",
        "terminal_blocked": "terminal_block",
        "terminal_block": "terminal_block",
        "create_pack": "create",
    }
    return mapping.get(normalized, normalized)


def command_apply_mutation(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    plan = load_plan(args.plan)
    action = normalize_action(args.action or str(plan.get("action") or plan.get("pack_disposition") or ""))
    if action not in {"insert", "reorder", "skip", "supersede", "terminal_block", "create"}:
        raise SystemExit("Mutation action must be insert, reorder, skip, supersede, terminal_block, or create.")

    if action == "create":
        pack_data = plan.get("pack") if isinstance(plan.get("pack"), dict) else plan
        pack_id = str(pack_data.get("pack_id") or "").strip()
        if not pack_id:
            raise SystemExit("Create mutation requires `pack_id`.")
        path = pack_dir(root) / f"{pack_id}.json"
        if path.exists():
            raise SystemExit(f"Task pack already exists: {rel_path(root, path)}")
        pack_data.setdefault("schema_version", 1)
        pack_data.setdefault("status", "active")
        pack_data.setdefault("language", args.language)
        pack_data.setdefault("created_at", now_iso())
        pack_data.setdefault("updated_at", now_iso())
        pack_data.setdefault("mutation_log", [])
        pack_data.setdefault("terminal_blocker", None)
        if not pack_data.get("current_item_id") and isinstance(pack_data.get("items"), list) and pack_data["items"]:
            pack_data["current_item_id"] = sorted(pack_data["items"], key=lambda item: item.get("order", 0))[0].get("item_id")
        pack_data.setdefault("mutation_log", []).append(mutation_entry("create", plan, [], item_order(pack_data)))
        findings = validate_pack(pack_data, path)
        if any(item.get("severity") == "block" for item in findings):
            output = {"status": "block", "pack_path": rel_path(root, path), "findings": findings}
            json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
            sys.stdout.write("\n")
            return 2
        write_json(path, pack_data)
        render_output_path = None
        if args.render:
            render_output_path = render_path(path)
            render_output_path.write_text(render_markdown(root, path, pack_data, args.language), encoding="utf-8")
        output = {
            "status": "ok",
            "action": "create",
            "pack_path": rel_path(root, path),
            "render_path": rel_path(root, render_output_path) if render_output_path else None,
            "pack_id": pack_data.get("pack_id"),
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    path = root / str(plan.get("pack_path") or args.pack) if (plan.get("pack_path") or args.pack) else active_pack(root)[0]
    if path is None:
        raise SystemExit("No active task pack found.")
    data = load_json(path)
    before_order = item_order(data)
    items = data.get("items")
    if not isinstance(items, list):
        raise SystemExit("Task pack has invalid `items`.")

    if action == "insert":
        new_items = plan.get("items") or plan.get("insert_items")
        if not isinstance(new_items, list) or not new_items:
            raise SystemExit("Insert mutation requires non-empty `items`.")
        existing_ids = {str(item.get("item_id")) for item in items if isinstance(item, dict)}
        for item in new_items:
            if not isinstance(item, dict):
                raise SystemExit("Inserted items must be JSON objects.")
            item_id = str(item.get("item_id") or "").strip()
            if not item_id or item_id in existing_ids:
                raise SystemExit(f"Inserted item_id is empty or duplicated: {item_id}")
            item.setdefault("status", "inserted")
            item.setdefault("dependencies", [])
            item.setdefault("source_evidence", evidence_paths_from(plan))
            item.setdefault("promotion", {"task_id": None, "task_path": None, "promoted_at": None})
            item.setdefault("result", {"validation_verdict": None, "progress_verdict": None, "progress_kind": None, "semantic_signature": None, "blocker_signature": None})
            existing_ids.add(item_id)
        insert_before = plan.get("insert_before_item_id") or data.get("current_item_id")
        rebuilt: list[dict[str, Any]] = []
        inserted = False
        for item in sorted_items(data):
            if insert_before and item.get("item_id") == insert_before:
                rebuilt.extend(new_items)
                inserted = True
            rebuilt.append(item)
        if not inserted:
            rebuilt.extend(new_items)
        data["items"] = rebuilt
        renumber_items(data)
        data.setdefault("mutation_log", []).append(mutation_entry("insert", plan, before_order, item_order(data)))

    elif action == "reorder":
        requested = plan.get("item_order") or plan.get("order")
        if not isinstance(requested, list) or not requested:
            raise SystemExit("Reorder mutation requires full `item_order` list.")
        requested_ids = [str(item) for item in requested]
        current_ids = item_order(data)
        if set(requested_ids) != set(current_ids) or len(requested_ids) != len(current_ids):
            raise SystemExit("Reorder mutation must name every existing item exactly once.")
        by_id = {str(item.get("item_id")): item for item in items if isinstance(item, dict)}
        data["items"] = [by_id[item_id] for item_id in requested_ids]
        for item in data["items"]:
            if item.get("status") == "planned":
                item["status"] = "reordered"
        renumber_items(data)
        data.setdefault("mutation_log", []).append(mutation_entry("reorder", plan, before_order, item_order(data)))

    elif action == "skip":
        item_ids = plan.get("item_ids") or plan.get("skip_item_ids") or plan.get("exclude_item_ids")
        if not isinstance(item_ids, list) or not item_ids:
            raise SystemExit("Skip mutation requires non-empty `item_ids`.")
        targets = {str(item_id) for item_id in item_ids}
        found: set[str] = set()
        for item in items:
            if isinstance(item, dict) and str(item.get("item_id")) in targets:
                item["status"] = "skipped"
                result = item.setdefault("result", {})
                result["skip_reason"] = plan.get("reason")
                result["evidence_paths"] = evidence_paths_from(plan)
                found.add(str(item.get("item_id")))
        missing = sorted(targets - found)
        if missing:
            raise SystemExit(f"Unknown task pack item(s): {', '.join(missing)}")
        data.setdefault("mutation_log", []).append(mutation_entry("skip", plan, before_order, item_order(data)))

    elif action == "supersede":
        data["status"] = "superseded"
        for item in items:
            if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                item["status"] = "superseded"
        data.setdefault("mutation_log", []).append(mutation_entry("supersede", plan, before_order, item_order(data)))

    elif action == "terminal_block":
        terminal = plan.get("terminal_blocker")
        if not isinstance(terminal, dict):
            raise SystemExit("terminal_block mutation requires `terminal_blocker` object.")
        data["status"] = "terminal_blocked"
        data["terminal_blocker"] = terminal
        current = data.get("current_item_id")
        for item in items:
            if isinstance(item, dict) and (not current or item.get("item_id") == current) and item.get("status") in {"planned", "inserted", "reordered", "blocked"}:
                item["status"] = "terminal_blocked"
                break
        data.setdefault("mutation_log", []).append(mutation_entry("terminal_block", plan, before_order, item_order(data)))

    refresh_current_item(data)
    findings = validate_pack(data, path)
    if any(item.get("severity") == "block" for item in findings):
        output = {"status": "block", "action": action, "pack_path": rel_path(root, path), "findings": findings}
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    write_json(path, data)
    render_output_path = None
    if args.render:
        render_output_path = render_path(path)
        render_output_path.write_text(render_markdown(root, path, data, args.language), encoding="utf-8")
    output = {
        "status": "ok",
        "action": action,
        "pack_path": rel_path(root, path),
        "render_path": rel_path(root, render_output_path) if render_output_path else None,
        "pack_id": data.get("pack_id"),
        "pack_status": data.get("status"),
        "current_item_id": data.get("current_item_id"),
        "before_order": before_order,
        "after_order": item_order(data),
        "findings": findings,
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def command_mark_consumed(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = root / args.pack if args.pack else active_pack(root)[0]
    if path is None:
        raise SystemExit("No active task pack found.")
    data = load_json(path)
    found = False
    for item in data.get("items", []):
        if isinstance(item, dict) and item.get("item_id") == args.item_id:
            item["status"] = "consumed"
            promotion = item.setdefault("promotion", {})
            if args.task_id:
                promotion["task_id"] = args.task_id
            if args.task_path:
                promotion["task_path"] = args.task_path
            promotion.setdefault("promoted_at", now_iso())
            result = item.setdefault("result", {})
            for key, value in (
                ("validation_verdict", args.validation_verdict),
                ("progress_verdict", args.progress_verdict),
                ("progress_kind", args.progress_kind),
                ("semantic_signature", args.semantic_signature),
                ("blocker_signature", args.blocker_signature),
            ):
                if value:
                    result[key] = value
            if args.has_supplied_input_delta:
                gate = result.setdefault("positive_input_delta_gate", {})
                gate["has_supplied_input_delta"] = True
            if args.supplied_input_artifact_path:
                gate = result.setdefault("positive_input_delta_gate", {})
                paths = gate.setdefault("supplied_input_artifact_paths", [])
                for supplied_path in args.supplied_input_artifact_path:
                    if supplied_path not in paths:
                        paths.append(supplied_path)
            if (
                args.acceptance_target_met
                or args.acceptance_diluted
                or args.explicit_descope_decision
                or args.acceptance_provenance_evidence_path
                or args.residual_item_id
            ):
                gate = result.setdefault("acceptance_provenance_gate", {})
                if args.acceptance_target_met:
                    gate["target_met"] = True
                if args.acceptance_diluted:
                    gate["acceptance_diluted"] = True
                if args.explicit_descope_decision:
                    gate["explicit_descope_decision"] = True
                if args.residual_item_id:
                    gate["residual_item_id"] = args.residual_item_id
                if args.acceptance_provenance_evidence_path:
                    paths = gate.setdefault("evidence_paths", [])
                    for evidence_path in args.acceptance_provenance_evidence_path:
                        if evidence_path not in paths:
                            paths.append(evidence_path)
            if args.required_verifier or args.acceptance_verifier_status or args.acceptance_verifier_evidence_path:
                gate = result.setdefault("acceptance_verifier_gate", {})
                if args.required_verifier:
                    gate["required_verifier"] = args.required_verifier
                    gate["verifier_required"] = True
                if args.acceptance_verifier_status:
                    gate["evaluation_status"] = args.acceptance_verifier_status
                    gate["acceptance_verifier_not_evaluated"] = args.acceptance_verifier_status == "not_evaluated"
                    gate["unverifiable_acceptance_contract"] = args.acceptance_verifier_status == "not_evaluated"
                if args.acceptance_verifier_evidence_path:
                    paths = gate.setdefault("evidence_paths", [])
                    for evidence_path in args.acceptance_verifier_evidence_path:
                        if evidence_path not in paths:
                            paths.append(evidence_path)
            if args.required_gate_hook or args.gate_hook_status:
                gate = result.setdefault("acceptance_verifier_gate", {})
                if args.required_gate_hook:
                    hooks = gate.setdefault("required_gate_hooks", [])
                    for hook in args.required_gate_hook:
                        if hook not in hooks:
                            hooks.append(hook)
                if args.gate_hook_status:
                    gate["gate_hook_status"] = args.gate_hook_status
                    if args.gate_hook_status in {"not_supplied", "absent", "fail_quiet", "not_evaluated"}:
                        gate["unverifiable_acceptance_contract"] = True
            if args.pass_with_unobserved_axes or args.unobserved_goal_axis:
                gate = result.setdefault("goal_axis_completeness_gate", {})
                if args.pass_with_unobserved_axes:
                    gate["pass_with_unobserved_axes"] = True
                if args.unobserved_goal_axis:
                    axes = gate.setdefault("unobserved_goal_axes", [])
                    for axis in args.unobserved_goal_axis:
                        if axis not in axes:
                            axes.append(axis)
            if (
                args.independently_verified_field
                or args.producer_attested_field
                or args.independent_source_separation_status
                or args.independently_verified_downgraded_field
                or args.verification_input_path
                or args.verified_artifact_path
            ):
                gate = result.setdefault("evidence_provenance_gate", {})
                if args.independently_verified_field:
                    fields = gate.setdefault("independently_verified_fields", [])
                    for field in args.independently_verified_field:
                        if field not in fields:
                            fields.append(field)
                if args.producer_attested_field:
                    fields = gate.setdefault("producer_attested_fields", [])
                    for field in args.producer_attested_field:
                        if field not in fields:
                            fields.append(field)
                if args.independent_source_separation_status:
                    gate["independent_source_separation_status"] = args.independent_source_separation_status
                if args.independently_verified_downgraded_field:
                    fields = gate.setdefault("independently_verified_downgraded_fields", [])
                    for field in args.independently_verified_downgraded_field:
                        if field not in fields:
                            fields.append(field)
                if args.verification_input_path:
                    paths = gate.setdefault("verification_input_paths", [])
                    for path_value in args.verification_input_path:
                        if path_value not in paths:
                            paths.append(path_value)
                if args.verified_artifact_path:
                    paths = gate.setdefault("verified_artifact_paths", [])
                    for path_value in args.verified_artifact_path:
                        if path_value not in paths:
                            paths.append(path_value)
            if args.generation_dependent_count_key or args.effective_count_key:
                gate = result.setdefault("count_key_hygiene_gate", {})
                if args.generation_dependent_count_key:
                    gate["generation_dependent_count_key"] = True
                    gate["count_key_trace_only"] = True
                if args.effective_count_key:
                    gate["effective_count_key"] = args.effective_count_key
            if args.envelope_thaw_item_required or args.envelope_thaw_item or args.thaw_condition or args.thaw_schedule:
                gate = result.setdefault("acceptance_reachability_gate", {})
                if args.envelope_thaw_item_required:
                    gate["envelope_thaw_item_required"] = True
                if args.envelope_thaw_item:
                    gate["envelope_thaw_item"] = args.envelope_thaw_item
                if args.thaw_condition:
                    gate["thaw_condition"] = args.thaw_condition
                if args.thaw_schedule:
                    gate["thaw_schedule"] = args.thaw_schedule
            if args.instrumentation_supply_required or args.diagnostics_unavailable_streak is not None or args.existing_diagnostics_sufficient:
                gate = result.setdefault("diagnostics_unavailable_gate", {})
                if args.instrumentation_supply_required:
                    gate["instrumentation_supply_required"] = True
                if args.diagnostics_unavailable_streak is not None:
                    gate["diagnostics_unavailable_streak"] = args.diagnostics_unavailable_streak
                if args.existing_diagnostics_sufficient:
                    result["existing_diagnostics_sufficient"] = True
            if (
                args.cycle_fixed_cost is not None
                or args.marginal_value_per_cycle_cost is not None
                or args.residual_gap_cost_below_policy
                or args.marginal_repair_higher_value
            ):
                policy = result.setdefault("residual_gap_cost_policy", {})
                if args.cycle_fixed_cost is not None:
                    policy["cycle_fixed_cost"] = args.cycle_fixed_cost
                if args.marginal_value_per_cycle_cost is not None:
                    policy["marginal_value_per_cycle_cost"] = args.marginal_value_per_cycle_cost
                if args.residual_gap_cost_below_policy:
                    policy["below_policy"] = True
                if args.marginal_repair_higher_value:
                    policy["marginal_repair_higher_value"] = True
            found = True
            break
    if not found:
        raise SystemExit(f"Unknown task pack item: {args.item_id}")
    remaining = [item for item in data.get("items", []) if isinstance(item, dict) and item.get("status") in {"planned", "inserted", "reordered"}]
    data["current_item_id"] = remaining[0].get("item_id") if remaining else None
    if not remaining and data.get("status") == "active":
        data["status"] = "completed"
    data.setdefault("mutation_log", []).append(
        {
            "timestamp": now_iso(),
            "action": "mark_consumed",
            "reason": args.reason or "pack item consumed by completed task",
            "item_id": args.item_id,
            "actor": "$derive-improvement-task",
        }
    )
    findings = validate_pack(data, path)
    if any(item.get("severity") == "block" for item in findings):
        output = {"status": "block", "pack_path": rel_path(root, path), "pack_id": data.get("pack_id"), "findings": findings}
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    write_json(path, data)
    if args.render:
        render_path(path).write_text(render_markdown(root, path, data, args.language), encoding="utf-8")
    output = {"status": "ok", "pack_path": rel_path(root, path), "pack_id": data.get("pack_id"), "current_item_id": data.get("current_item_id")}
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect and render orchestrate-task-cycle task pack queues.")
    parser.add_argument("--root", default=".", help="Workspace root.")
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status")
    status_p.add_argument("--format", choices=("json",), default="json")
    status_p.set_defaults(func=command_status)

    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to all packs.")
    validate_p.set_defaults(func=command_validate)

    render_p = sub.add_parser("render")
    render_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to all packs.")
    render_p.add_argument("--language", default="ko", help="Markdown render language label.")
    render_p.set_defaults(func=command_render)

    next_p = sub.add_parser("next")
    next_p.set_defaults(func=command_next)

    consumed_p = sub.add_parser("mark-consumed")
    consumed_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to active pack.")
    consumed_p.add_argument("--item-id", required=True)
    consumed_p.add_argument("--task-id")
    consumed_p.add_argument("--task-path")
    consumed_p.add_argument("--validation-verdict")
    consumed_p.add_argument("--progress-verdict")
    consumed_p.add_argument("--progress-kind")
    consumed_p.add_argument("--semantic-signature")
    consumed_p.add_argument("--blocker-signature")
    consumed_p.add_argument("--has-supplied-input-delta", action="store_true")
    consumed_p.add_argument("--supplied-input-artifact-path", action="append")
    consumed_p.add_argument("--acceptance-target-met", action="store_true")
    consumed_p.add_argument("--acceptance-diluted", action="store_true")
    consumed_p.add_argument("--explicit-descope-decision", action="store_true")
    consumed_p.add_argument("--residual-item-id")
    consumed_p.add_argument("--acceptance-provenance-evidence-path", action="append")
    consumed_p.add_argument("--required-verifier")
    consumed_p.add_argument("--acceptance-verifier-status", choices=["pass", "fail", "not_evaluated"])
    consumed_p.add_argument("--acceptance-verifier-evidence-path", action="append")
    consumed_p.add_argument("--required-gate-hook", action="append")
    consumed_p.add_argument("--gate-hook-status", choices=["pass", "supplied", "present", "not_supplied", "absent", "fail_quiet", "not_evaluated"])
    consumed_p.add_argument("--pass-with-unobserved-axes", action="store_true")
    consumed_p.add_argument("--unobserved-goal-axis", action="append")
    consumed_p.add_argument("--independently-verified-field", action="append")
    consumed_p.add_argument("--producer-attested-field", action="append")
    consumed_p.add_argument("--independent-source-separation-status", choices=["pass", "missing", "overlap", "blocked", "self_grounded"])
    consumed_p.add_argument("--independently-verified-downgraded-field", action="append")
    consumed_p.add_argument("--verification-input-path", action="append")
    consumed_p.add_argument("--verified-artifact-path", action="append")
    consumed_p.add_argument("--generation-dependent-count-key", action="store_true")
    consumed_p.add_argument("--effective-count-key")
    consumed_p.add_argument("--envelope-thaw-item-required", action="store_true")
    consumed_p.add_argument("--envelope-thaw-item")
    consumed_p.add_argument("--thaw-condition")
    consumed_p.add_argument("--thaw-schedule")
    consumed_p.add_argument("--instrumentation-supply-required", action="store_true")
    consumed_p.add_argument("--diagnostics-unavailable-streak")
    consumed_p.add_argument("--existing-diagnostics-sufficient", action="store_true")
    consumed_p.add_argument("--cycle-fixed-cost")
    consumed_p.add_argument("--marginal-value-per-cycle-cost")
    consumed_p.add_argument("--residual-gap-cost-below-policy", action="store_true")
    consumed_p.add_argument("--marginal-repair-higher-value", action="store_true")
    consumed_p.add_argument("--reason")
    consumed_p.add_argument("--language", default="ko")
    consumed_p.add_argument("--render", action="store_true")
    consumed_p.set_defaults(func=command_mark_consumed)

    mutate_p = sub.add_parser("apply-mutation")
    mutate_p.add_argument("--plan", required=True, help="Mutation plan JSON path, inline JSON, or '-' for stdin.")
    mutate_p.add_argument("--action", help="Override action from the plan.")
    mutate_p.add_argument("--pack", help="Workspace-relative pack JSON path. Defaults to active pack or plan.pack_path.")
    mutate_p.add_argument("--language", default="ko")
    mutate_p.add_argument("--render", action="store_true")
    mutate_p.set_defaults(func=command_apply_mutation)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
