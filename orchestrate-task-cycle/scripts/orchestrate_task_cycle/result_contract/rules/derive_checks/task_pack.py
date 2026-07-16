from __future__ import annotations

from .shared import (
    PACK_DISPOSITIONS,
    PACK_MUTATION_DISPOSITIONS,
    _workspace_root,
    active_task_pack_present,
    add,
    allowed_task_kinds_from_basis,
    first_present,
    has_value,
    list_values,
    non_empty,
    selected_disposition,
    selected_task_kind_value,
    task_pack_in_scope,
    task_pack_queue,
    value_for,
)
from .state import DeriveFacts

def _validate_mutation_contract(
    facts: DeriveFacts,
    pack_disposition: str,
    mutation_plan: object,
    mutation_receipt: object,
) -> None:
    context = facts.context
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    if isinstance(mutation_plan, dict) and pack_disposition == "replace_pack":
        replacement_result = task_pack_queue.validate_replacement_receipt(
            _workspace_root(context),
            mutation_plan,
            mutation_receipt if isinstance(mutation_receipt, dict) else None,
            current_pack_path=str(value_for(result, "task_pack_path") or "") or None,
            current_render_path=str(value_for(result, "task_pack_render_path") or "") or None,
        )
        for replacement_finding in replacement_result.get("findings", []):
            add(
                findings,
                "block" if mode == "block" else "warn",
                f"derive_{replacement_finding.get('code')}",
                str(replacement_finding.get("message") or "Pack replacement validation failed."),
                replacement_finding.get("evidence"),
            )
    elif isinstance(mutation_plan, dict):
        plan_for_validation = dict(mutation_plan)
        plan_for_validation.setdefault("pack_path", value_for(result, "task_pack_path"))
        if isinstance(mutation_receipt, dict):
            plan_for_validation["pack_mutation_receipt"] = mutation_receipt
        coherence_version = task_pack_queue.pack_coherence_contract_version(mutation_plan)
        current_contract = coherence_version == task_pack_queue.PACK_COHERENCE_VERSION
        explicit_legacy_contract = coherence_version == 0
        coherence_result = task_pack_queue.validate_pack_coherence_contract(
            _workspace_root(context),
            plan_for_validation,
            receipt=mutation_receipt if isinstance(mutation_receipt, dict) else None,
            require_declared=True,
            require_receipt=current_contract,
        )
        for coherence_finding in coherence_result.get("findings", []):
            add(
                findings,
                "block" if mode == "block" else "warn",
                f"derive_{coherence_finding.get('code')}",
                str(coherence_finding.get("message") or "Pack coherence validation failed."),
                coherence_finding.get("evidence"),
            )
        if explicit_legacy_contract:
            add(
                findings,
                "warn",
                "derive_pack_coherence_legacy_normalized",
                "Legacy pack mutation input was normalized against the current body; emit explicit before-snapshot fields on the next mutation.",
            )


def _check_promotion_receipt(
    facts: DeriveFacts,
    pack_disposition: str,
    mutation_plan: object,
) -> None:
    mode = facts.mode
    findings = facts.findings
    if pack_disposition != "promote_next_item" or not isinstance(mutation_plan, dict):
        return
    origin = str(mutation_plan.get("promotion_origin") or "predecessor_completion").strip().lower()
    if origin not in task_pack_queue.PROMOTION_ORIGINS:
        add(findings, "block", "promotion_origin_invalid", "Task-pack promotion origin is invalid.")
    elif origin in {"bootstrap_initial_selection", "authorized_initial_selection"}:
        receipt = mutation_plan.get("initial_selection_receipt")
        if not isinstance(receipt, dict):
            add(findings, "block", "initial_selection_receipt_missing", "Initial pack promotion requires a bounded initial-selection receipt.")
        else:
            required_receipt = (
                "pack_ref", "pack_creation_sha256", "initial_item_id", "initial_order",
                "task_snapshot_sha256", "authority_receipt_ref", "selection_reason", "created_at",
            )
            missing_receipt = [field for field in required_receipt if not non_empty(receipt.get(field))]
            if missing_receipt:
                add(
                    findings,
                    "block",
                    "initial_selection_receipt_incomplete",
                    "Initial selection receipt is incomplete.",
                    {"missing_fields": missing_receipt},
                )
    elif not non_empty(
        mutation_plan.get("predecessor_completion_receipt_ref")
        or mutation_plan.get("validation_report_path")
    ):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "predecessor_completion_receipt_missing",
            "Successor promotion requires predecessor-completion receipt provenance.",
        )


def _check_initial_selection_normalization(
    facts: DeriveFacts,
    pack_disposition: str,
    mutation_plan: object,
) -> None:
    if pack_disposition != "normalize_initial_selection_provenance":
        return
    context = facts.context
    result = facts.result
    findings = facts.findings
    if not isinstance(mutation_plan, dict):
        add(
            findings,
            "block",
            "initial_selection_normalization_plan_missing",
            "Initial-selection normalization requires the exact helper mutation plan.",
        )
        return
    try:
        workspace = _workspace_root(context)
        pack_ref = str(mutation_plan.get("pack_path") or value_for(result, "task_pack_path") or "")
        pack_path = task_pack_queue.resolve_pack_path(workspace, pack_ref)
        pack_data = task_pack_queue.load_json(pack_path)
        supplied_receipt = mutation_plan.get("initial_selection_receipt")
        if not isinstance(supplied_receipt, dict):
            raise SystemExit("Normalization plan is missing initial_selection_receipt.")
        item_id = str(supplied_receipt.get("initial_item_id") or "")
        target = next(
            (
                item for item in pack_data.get("items", [])
                if isinstance(item, dict) and str(item.get("item_id") or "") == item_id
            ),
            None,
        )
        promotion = target.get("promotion") if isinstance(target, dict) else None
        if not isinstance(promotion, dict):
            raise SystemExit("Normalized pack does not preserve first promotion provenance.")
        stored_receipt = promotion.get("initial_selection_receipt")
        if stored_receipt != supplied_receipt:
            raise SystemExit("Normalized pack receipt differs from the helper mutation plan.")
        task_pack_queue.validate_initial_selection_receipt(
            workspace,
            pack_path,
            pack_data,
            stored_receipt,
            task_id=str(promotion.get("task_id") or ""),
            task_digest=str(promotion.get("task_sha256") or ""),
            operation="normalize_initial_selection_provenance",
        )
        normalization = promotion.get("provenance_normalization")
        if not isinstance(normalization, dict):
            raise SystemExit("Normalized pack is missing provenance_normalization.")
        if normalization.get("authority_mode") == "current_ratification" and (
            normalization.get("historical_authority_verdict") != "partial"
            or normalization.get("retroactive_claim_allowed") is not False
        ):
            raise SystemExit("Current ratification overstates historical authority.")
    except SystemExit as exc:
        add(findings, "block", "initial_selection_normalization_invalid", str(exc))


def _check_pack_mutation(facts: DeriveFacts, pack_disposition: str) -> None:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    require_context_field = facts.require_context_field
    require_context_field("pack_mutation_plan", "pack_mutation_plan_missing", "Pack mutation dispositions require \x60pack_mutation_plan\x60.")
    require_context_field("task_pack_path", "task_pack_path_missing", "Pack mutation dispositions require \x60task_pack_path\x60.")
    require_context_field("task_pack_render_path", "task_pack_render_path_missing", "Pack mutation dispositions require a refreshed Markdown render path.")
    mutation_plan = first_present(
        result,
        ["pack_mutation_plan", "derive.pack_mutation_plan", "result.pack_mutation_plan", "task_pack_packet.pack_mutation_plan"],
    )
    mutation_receipt = first_present(
        result,
        ["pack_mutation_receipt", "derive.pack_mutation_receipt", "result.pack_mutation_receipt", "task_pack_packet.pack_mutation_receipt"],
    )
    _validate_mutation_contract(facts, pack_disposition, mutation_plan, mutation_receipt)
    if not has_value(result, "pack_mutation_log") and not has_value(result, "pack_mutation_plan"):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "pack_mutation_evidence_missing",
            "Pack mutation dispositions should carry mutation-log evidence or a durable mutation plan.",
        )
    _check_promotion_receipt(facts, pack_disposition, mutation_plan)
    _check_initial_selection_normalization(facts, pack_disposition, mutation_plan)


def _check_pack_selection(facts: DeriveFacts) -> tuple[str, str]:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    require_context_field = facts.require_context_field
    status = str(value_for(result, "status") or "").lower()
    if status in {"deferred", "pending", "blocked", "failed"} and not has_value(result, "derive_pending_reason") and not has_value(result, "blockers"):
        add(findings, "block" if mode == "block" else "warn", "derive_pending_reason_missing", "Deferred or blocked derivation requires a pending/blocker reason.")
    selected_source = str(value_for(result, "selected_task_source") or "").lower()
    pack_disposition = str(
        first_present(
            result,
            [
                "pack_disposition",
                "derive.pack_disposition",
                "result.pack_disposition",
                "task_pack_packet.pack_disposition",
                "task_pack.disposition",
            ],
        )
        or ""
    ).lower()
    pack_scope = task_pack_in_scope(result) or bool(pack_disposition)
    if active_task_pack_present(result) and selected_source != "task_pack" and not has_value(result, "task_pack_status"):
        add(findings, "block" if mode == "block" else "warn", "task_pack_status_missing", "Active task pack in scope requires `task_pack_status` in derive result.")
    if pack_scope and not pack_disposition:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "pack_disposition_missing",
            "`derive` with task-pack scope requires exactly one `pack_disposition`.",
            {"allowed": sorted(PACK_DISPOSITIONS)},
        )
    if pack_disposition and pack_disposition not in PACK_DISPOSITIONS:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "pack_disposition_invalid",
            "`pack_disposition` is not an allowed task-pack transaction.",
            {"pack_disposition": pack_disposition, "allowed": sorted(PACK_DISPOSITIONS)},
        )
    if selected_source and selected_source not in {"task_pack", "candidate_task", "standalone", "terminal_blocked"}:
        add(findings, "warn", "selected_task_source_invalid", "`selected_task_source` should be task_pack, candidate_task, standalone, or terminal_blocked.", {"selected_task_source": selected_source})
    if selected_source == "task_pack":
        require_context_field("task_pack_status", "task_pack_status_missing", "`selected_task_source: task_pack` requires `task_pack_status`.")
        require_context_field("task_pack_path", "task_pack_path_missing", "`selected_task_source: task_pack` requires `task_pack_path`.")
        require_context_field("task_pack_item_id", "task_pack_item_id_missing", "`selected_task_source: task_pack` requires `task_pack_item_id` or `promoted_item_id`.")
        require_context_field("pack_disposition", "pack_disposition_missing", "`selected_task_source: task_pack` requires `pack_disposition`.")
    if pack_disposition in PACK_MUTATION_DISPOSITIONS | {"promote_next_item"}:
        _check_pack_mutation(facts, pack_disposition)
    if pack_disposition in {"skip_items", "exclude_items"}:
        require_context_field("skipped_item_ids", "skipped_item_ids_missing", "Skipping/excluding pack items requires `skipped_item_ids` or `exclude_item_ids`.")
    if pack_disposition == "derive_standalone":
        require_context_field("derive_standalone_rationale", "derive_standalone_rationale_missing", "`derive_standalone` with an active pack requires a rationale.")
    if pack_disposition == "terminal_blocked" and selected_source not in {"", "terminal_blocked"}:
        add(
            findings,
            "block" if mode == "block" else "warn",
            "pack_terminal_selected_source_mismatch",
            "`pack_disposition: terminal_blocked` should use `selected_task_source: terminal_blocked`.",
            {"selected_task_source": selected_source},
        )
    if selected_source == "terminal_blocked" and not has_value(result, "terminal_blocker"):
        add(findings, "block", "terminal_blocker_missing", "`selected_task_source: terminal_blocked` requires `terminal_blocker`.")
    if selected_source == "terminal_blocked" and not has_value(result, "semantic_signature"):
        add(findings, "block" if mode == "block" else "warn", "terminal_semantic_signature_missing", "`selected_task_source: terminal_blocked` should include `semantic_signature` so the family can be sealed.")
    return status, selected_source


def _lifecycle_axis_status(result: dict[str, object], axis: str) -> str:
    nested_result = result.get("result") if isinstance(result.get("result"), dict) else {}
    sources = [
        result,
        result.get("verdict_axes") if isinstance(result.get("verdict_axes"), dict) else {},
        nested_result,
        nested_result.get("verdict_axes") if isinstance(nested_result.get("verdict_axes"), dict) else {},
    ]
    observed: set[str] = set()
    for source in sources:
        if axis not in source:
            continue
        value = source.get(axis)
        raw = value.get("status") or value.get("verdict") if isinstance(value, dict) else value
        normalized = str(raw or "").strip().lower()
        observed.add(
            "not_evaluated"
            if normalized in {"", "missing", "unknown", "unobserved"}
            else normalized
        )
    if len(observed) > 1:
        return "conflicted"
    return next(iter(observed), "")


def _check_successor_selection(facts: DeriveFacts, status: str, selected_source: str) -> str:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    completed_task_id = str(value_for(result, "completed_task_id") or "").strip()
    next_task_id = str(value_for(result, "next_task_id") or "").strip()
    task_acceptance_status = _lifecycle_axis_status(result, "task_acceptance_verdict")
    goal_readiness_status = _lifecycle_axis_status(result, "goal_readiness_verdict")
    bounded_complete_global_wait = bool(
        completed_task_id
        and task_acceptance_status == "pass"
        and goal_readiness_status in {"blocked", "not_evaluated"}
        and status in {"deferred", "pending", "blocked"}
        and not selected_source
        and not next_task_id
    )
    if selected_source != "terminal_blocked" and not next_task_id and not bounded_complete_global_wait:
        add(findings, "block" if mode == "block" else "warn", "next_task_id_missing", "Non-terminal derive result requires `next_task_id`.")
    if (
        completed_task_id
        and next_task_id
        and completed_task_id == next_task_id
        and task_acceptance_status == "pass"
    ):
        add(
            findings,
            "block" if mode == "block" else "warn",
            "derive_completed_task_reselected",
            "A bounded-complete task cannot be selected again as its own successor; preserve it as current history and use a distinct successor identity when one exists.",
            {"completed_task_id": completed_task_id},
        )
    progress_kind = str(
        first_present(
            result,
            [
                "progress_kind",
                "selected_progress_kind",
                "expected_progress_kind",
                "derive.progress_kind",
                "derive.selected_progress_kind",
                "result.progress_kind",
                "result.selected_progress_kind",
            ],
        )
        or ""
    ).lower()
    if progress_kind and progress_kind not in {"goal_productive", "governance_only"}:
        add(findings, "warn", "progress_kind_invalid", "`derive` progress_kind should be `goal_productive` or `governance_only`.", {"progress_kind": progress_kind})
    if progress_kind == "governance_only" and selected_source != "terminal_blocked":
        add(
            findings,
            "warn",
            "derive_governance_only_selected",
            "`derive` selected a governance-only task; ensure this is not another sidecar/narrowing loop.",
        )
    return progress_kind


def _bind_pack_routing_facts(facts: DeriveFacts, selected_source: str, progress_kind: str) -> None:
    result = facts.result
    mode = facts.mode
    findings = facts.findings
    effective_allowed = list_values(
        first_present(
            result,
            [
                "effective_allowed_dispositions",
                "anti_loop_progress_gate.effective_allowed_dispositions",
                "loop_breaker_packet.effective_allowed_dispositions",
                "result.anti_loop_progress_gate.effective_allowed_dispositions",
                "result.loop_breaker_packet.effective_allowed_dispositions",
            ],
        )
    )
    if effective_allowed:
        disposition = selected_disposition(result, selected_source, progress_kind)
        if disposition and disposition not in {item.lower() for item in effective_allowed}:
            add(
                findings,
                "block" if mode == "block" else "warn",
                "disposition_not_effectively_allowed",
                "Derive selected a disposition outside `effective_allowed_dispositions`; active gates must be consumed as an intersection, not a union.",
                {"selected_disposition": disposition, "effective_allowed_dispositions": effective_allowed},
            )
    disposition_basis = first_present(
        result,
        [
            "disposition_intersection_basis",
            "anti_loop_progress_gate.disposition_intersection_basis",
            "loop_breaker_packet.disposition_intersection_basis",
            "result.anti_loop_progress_gate.disposition_intersection_basis",
            "result.loop_breaker_packet.disposition_intersection_basis",
        ],
    )
    allowed_task_kinds = allowed_task_kinds_from_basis(disposition_basis)
    selected_kind = selected_task_kind_value(result)
    terminal_selected = selected_source == "terminal_blocked" or has_value(result, "terminal_blocker")

    facts.allowed_task_kinds = allowed_task_kinds
    facts.progress_kind = progress_kind
    facts.selected_kind = selected_kind
    facts.selected_source = selected_source
    facts.terminal_selected = terminal_selected


def check_task_pack(facts: DeriveFacts) -> None:
    status, selected_source = _check_pack_selection(facts)
    progress_kind = _check_successor_selection(facts, status, selected_source)
    _bind_pack_routing_facts(facts, selected_source, progress_kind)
