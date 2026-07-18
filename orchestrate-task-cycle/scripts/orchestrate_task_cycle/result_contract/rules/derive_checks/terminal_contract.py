from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ....selection_decision_receipt import (
    acknowledgement_binding,
    read_selection_decision_receipt,
)
from ....selection_tick_contract import (
    ACKNOWLEDGEMENT_KEYS,
    validate_selection_tick_v2,
)
from ....selection_tick_premise import VERIFIED_PREMISE_CONTRACT
from .shared import DERIVE_SELECTION_OUTCOMES, _workspace_root, add
from .state import DeriveFacts
from .authority_terminal import check_authority_terminal


TERMINAL_OUTCOMES = {"terminal_wait", "terminal_blocked", "user_escalation"}


def _finding(
    facts: DeriveFacts, code: str, message: str, evidence: dict[str, Any] | None = None
) -> None:
    add(facts.findings, "block", code, message, evidence)


def _nonempty_strings(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
    )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _tick_rebase_valid(
    baseline: dict[str, Any], last_receipt: object, root: Path
) -> bool:
    if baseline.get("baseline_rebased") is not True:
        return True
    binding = baseline.get("selection_acknowledgement_binding")
    if not isinstance(binding, dict) or set(binding) != ACKNOWLEDGEMENT_KEYS:
        return False
    try:
        receipt_binding = {
            "ref": binding["selection_receipt_ref"],
            "sha256": binding["selection_receipt_sha256"],
        }
        receipt = read_selection_decision_receipt(
            root,
            receipt_binding,
            expected_trigger_binding={
                "trigger_selection_tick_id": binding["trigger_tick_id"],
                "trigger_selection_tick_sha256": binding["trigger_tick_sha256"],
            },
        )
        expected = acknowledgement_binding(receipt_binding, receipt)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return bool(
        binding == expected
        and baseline.get("selection_acknowledgement_status") == "accepted"
        and baseline.get("acknowledged_selection_tick_id")
        == binding.get("trigger_tick_id")
        and str(last_receipt or "") == binding.get("selection_receipt_id")
    )


def _check_selected(facts: DeriveFacts, source: str) -> None:
    result = facts.result
    if not str(result.get("next_task_id") or "").strip():
        _finding(
            facts,
            "derive_selected_next_task_missing",
            "Selected outcome requires a concrete next task ID.",
        )
    if source not in {"task_pack", "candidate_task", "standalone"}:
        _finding(
            facts,
            "derive_selected_task_source_invalid",
            "Selected outcome requires task_pack, candidate_task, or standalone source.",
        )
    contradictions = [
        field
        for field in ("terminal_blocker", "terminal_wait", "user_escalation")
        if result.get(field) not in (None, "", [], {})
    ]
    if str(result.get("terminal_disposition") or "").strip():
        contradictions.append("terminal_disposition")
    if (
        str(result.get("selected_disposition") or "").strip().lower()
        in TERMINAL_OUTCOMES
    ):
        contradictions.append("selected_disposition")
    if (
        result.get("terminal_justified") is True
        or result.get("hard_stop_required") is True
    ):
        contradictions.extend(("terminal_justified", "hard_stop_required"))
    if contradictions:
        _finding(
            facts,
            "derive_selected_terminal_fields_present",
            "Selected outcome cannot carry terminal, wait, or escalation claims.",
            {"fields": sorted(set(contradictions))},
        )


def _check_terminal_wait(facts: DeriveFacts, source: str) -> None:
    result = facts.result
    if source != "terminal_wait":
        _finding(
            facts,
            "derive_terminal_wait_source_mismatch",
            "terminal_wait outcome requires selected_task_source=terminal_wait.",
        )
    if str(result.get("next_task_id") or "").strip():
        _finding(
            facts,
            "derive_terminal_wait_has_next_task",
            "terminal_wait cannot publish a next task.",
        )
    if (
        result.get("terminal_justified") is not False
        or result.get("hard_stop_required") is not False
    ):
        _finding(
            facts,
            "derive_terminal_wait_hard_stop_contradiction",
            "terminal_wait requires terminal_justified=false and hard_stop_required=false.",
        )
    wait = result.get("terminal_wait")
    required = (
        "selection_epoch",
        "analysis_evidence_manifest_sha256",
        "observed_input_manifest_sha256",
        "selection_tick_baseline",
        "selection_tick_baseline_sha256",
        "wake_predicates",
        "watched_evidence_classes",
        "minimum_material_delta",
        "last_selection_receipt",
    )
    missing = [
        field
        for field in required
        if not isinstance(wait, dict) or wait.get(field) in (None, "", [], {})
    ]
    if missing:
        _finding(
            facts,
            "derive_terminal_wait_contract_incomplete",
            "terminal_wait must bind the observed input and concrete wake predicates.",
            {"fields": missing},
        )
    elif not _nonempty_strings(wait.get("wake_predicates")) or not _nonempty_strings(
        wait.get("watched_evidence_classes")
    ):
        _finding(
            facts,
            "derive_terminal_wait_wake_predicates_invalid",
            "terminal_wait wake predicates and watched evidence classes must be non-empty opaque IDs.",
        )
    else:
        analysis = result.get("improvement_analysis_manifest")
        expected = (
            analysis.get("shared_evidence_manifest_sha256")
            if isinstance(analysis, dict)
            else None
        )
        if not expected or wait.get("analysis_evidence_manifest_sha256") != expected:
            _finding(
                facts,
                "derive_terminal_wait_analysis_binding_mismatch",
                "terminal_wait must bind the exact evidence manifest used for selection.",
            )
        baseline = wait.get("selection_tick_baseline")
        try:
            shared_baseline_valid = bool(
                isinstance(baseline, dict)
                and validate_selection_tick_v2(baseline)
                and baseline.get("premise_input_contract")
                == VERIFIED_PREMISE_CONTRACT
            )
        except (TypeError, ValueError):
            shared_baseline_valid = False
        baseline_valid = (
            shared_baseline_valid
            and baseline.get("status") in {"baseline_recorded", "no_op"}
            and baseline.get("selection_required") is False
            and baseline.get("agent_fanout_allowed") is False
            and baseline.get("full_cycle_allowed") is False
            and baseline.get("mutation_performed") is False
            and baseline.get("not_goal_truth") is True
            and baseline.get("not_authority") is True
            and wait.get("observed_input_manifest_sha256")
            == baseline.get("observed_input_manifest_sha256")
            and wait.get("selection_tick_baseline_sha256")
            == _canonical_sha256(baseline)
            and wait.get("wake_predicates") == baseline.get("wake_predicates")
            and wait.get("watched_evidence_classes")
            == baseline.get("watched_evidence_classes")
            and wait.get("minimum_material_delta")
            == baseline.get("minimum_material_delta")
            and _tick_rebase_valid(
                baseline,
                wait.get("last_selection_receipt"),
                _workspace_root(facts.context),
            )
        )
        if not baseline_valid:
            _finding(
                facts,
                "derive_terminal_wait_tick_baseline_invalid",
                "terminal_wait must carry a read-only selection-tick baseline bound to the watched input digest.",
            )
    conflicting = [
        field
        for field in ("terminal_blocker", "user_escalation")
        if result.get(field) not in (None, "", [], {})
    ]
    if conflicting:
        _finding(
            facts,
            "derive_terminal_wait_outcome_contradiction",
            "terminal_wait cannot also claim terminal_blocked or user escalation.",
            {"fields": conflicting},
        )


def _check_terminal_blocked(facts: DeriveFacts, source: str) -> None:
    result = facts.result
    if source != "terminal_blocked":
        _finding(
            facts,
            "derive_terminal_blocked_source_mismatch",
            "terminal_blocked outcome requires selected_task_source=terminal_blocked.",
        )
    if str(result.get("next_task_id") or "").strip():
        _finding(
            facts,
            "derive_terminal_blocked_has_next_task",
            "terminal_blocked cannot publish a next task.",
        )
    if (
        result.get("terminal_justified") is not True
        or result.get("hard_stop_required") is not True
    ):
        _finding(
            facts,
            "derive_terminal_blocked_not_justified",
            "terminal_blocked requires terminal_justified=true and hard_stop_required=true.",
        )
    blocker = result.get("terminal_blocker")
    if (
        not isinstance(blocker, dict)
        or not str(blocker.get("reason_code") or "").strip()
        or not _nonempty_strings(blocker.get("evidence_ids"))
    ):
        _finding(
            facts,
            "derive_terminal_blocker_contract_incomplete",
            "terminal_blocked requires a structured reason code and evidence IDs.",
        )
    if result.get("terminal_wait") not in (None, "", [], {}) or result.get(
        "user_escalation"
    ) not in (None, "", [], {}):
        _finding(
            facts,
            "derive_terminal_blocked_outcome_contradiction",
            "terminal_blocked cannot also claim wait or user escalation.",
        )


def _check_user_escalation(facts: DeriveFacts, source: str) -> None:
    result = facts.result
    if source != "user_escalation":
        _finding(
            facts,
            "derive_user_escalation_source_mismatch",
            "user_escalation outcome requires selected_task_source=user_escalation.",
        )
    if str(result.get("next_task_id") or "").strip():
        _finding(
            facts,
            "derive_user_escalation_has_next_task",
            "user_escalation cannot publish a next task.",
        )
    if (
        result.get("terminal_justified") is not False
        or result.get("hard_stop_required") is not False
    ):
        _finding(
            facts,
            "derive_user_escalation_terminal_contradiction",
            "user_escalation is not terminal_blocked and must keep both terminal flags false.",
        )
    escalation = result.get("user_escalation")
    valid = (
        isinstance(escalation, dict)
        and str(escalation.get("reason_code") or "").strip()
        and str(escalation.get("requested_input_or_authority") or "").strip()
        and _nonempty_strings(escalation.get("evidence_ids"))
    )
    if not valid:
        _finding(
            facts,
            "derive_user_escalation_contract_incomplete",
            "User escalation requires a bounded request, reason code, and evidence IDs.",
        )
    if result.get("terminal_blocker") not in (None, "", [], {}) or result.get(
        "terminal_wait"
    ) not in (None, "", [], {}):
        _finding(
            facts,
            "derive_user_escalation_outcome_contradiction",
            "user_escalation cannot also claim terminal wait or block.",
        )


def check_terminal_contract(facts: DeriveFacts) -> None:
    result = facts.result
    outcome = str(result.get("selection_outcome") or "").strip().lower()
    source = str(result.get("selected_task_source") or "").strip().lower()
    if outcome not in DERIVE_SELECTION_OUTCOMES:
        _finding(
            facts,
            "derive_selection_outcome_missing_or_invalid",
            "Derive must publish one canonical selection outcome.",
        )
        return
    disposition = str(result.get("pack_disposition") or "").strip().lower()
    terminal_disposition = str(result.get("terminal_disposition") or "").strip().lower()
    selected_disposition = str(result.get("selected_disposition") or "").strip().lower()
    if outcome in TERMINAL_OUTCOMES:
        if str(result.get("selected_candidate_id") or "").strip():
            _finding(
                facts,
                "derive_terminal_candidate_selected",
                "Terminal, wait, and escalation outcomes cannot carry a selected candidate ID.",
            )
        mismatches = [
            name
            for name, value in (
                ("pack_disposition", disposition),
                ("terminal_disposition", terminal_disposition),
                ("selected_disposition", selected_disposition),
            )
            if value and value != outcome
        ]
        if disposition != outcome or mismatches:
            _finding(
                facts,
                "derive_terminal_disposition_mismatch",
                "All declared terminal disposition fields must match selection_outcome.",
                {
                    "fields": sorted(
                        set(
                            mismatches
                            + (["pack_disposition"] if disposition != outcome else [])
                        )
                    )
                },
            )
    if outcome == "selected":
        _check_selected(facts, source)
    elif outcome == "terminal_wait":
        _check_terminal_wait(facts, source)
    elif outcome == "terminal_blocked":
        _check_terminal_blocked(facts, source)
    else:
        _check_user_escalation(facts, source)
    check_authority_terminal(facts)
