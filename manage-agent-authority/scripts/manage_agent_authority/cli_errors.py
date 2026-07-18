from __future__ import annotations

from typing import Any, Callable


Emitter = Callable[[Any], int]


def _classification(message: str) -> tuple[str, bool, bool, str]:
    rules = (
        ("explicit exact pre_commit", "pre_commit_verification_required", False, False, "supply_exact_pre_commit_binding"),
        ("expected_subject_after_sha256", "expected_after_digest_required", False, False, "supply_expected_after_digest"),
        ("CAS", "authority_cas_conflict", True, False, "resolve_or_resume_current_state"),
        ("idempotency conflict", "authority_idempotency_conflict", False, False, "use_original_replay_key_or_replan"),
        ("quarantined", "authority_effect_reconciliation_required", True, False, "reconcile_effect"),
        ("subject changed", "authority_subject_stale", True, False, "reprepare_exact_plan"),
        ("digest mismatch", "authority_binding_digest_mismatch", False, False, "repair_exact_binding"),
    )
    lowered = message.lower()
    for phrase, code, retryable, user_action, next_action in rules:
        if phrase.lower() in lowered:
            return code, retryable, user_action, next_action
    return "authority_operation_failed", False, False, "inspect_error_and_reprepare"


def emit_error(command: str, exc: SystemExit, emit: Emitter) -> int:
    message = str(exc) or "Authority operation failed."
    code, retryable, user_action, next_action = _classification(message)
    emit(
        {
            "schema_version": 2,
            "status": "error",
            "command": command,
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "user_action_required": user_action,
                "next_action": next_action,
            },
        }
    )
    return 2
