from __future__ import annotations

from ..runtime_dependencies import (
    attempt_revision_value,
    bool_value,
    terminal_self_resolution_gate,
)

from ..evaluation_frame import _EvaluationFrame


def _finalize_replay_state(frame: _EvaluationFrame) -> None:
    (
        args, attempt_identity, current_blocker_signature, current_root_family_key,
        current_root_key, existing_cycle, family_key, gate_inputs, output_delta,
        registry_rows, runner_validation,
    ) = frame.require(
        "args", "attempt_identity", "current_blocker_signature",
        "current_root_family_key", "current_root_key", "existing_cycle", "family_key",
        "gate_inputs", "output_delta", "registry_rows", "runner_validation",
    )
    existing_attempt = next(
        (
            registry_row
            for registry_row in reversed(registry_rows)
            if str(registry_row.get("attempt_identity") or "") == attempt_identity
        ),
        None,
    )
    registry_label_correction = False
    attempt_revision_candidate = 1
    supersedes_attempt_revision_candidate: int | None = None
    supersedes_attempt_identity_candidate: str | None = None
    if existing_attempt is not None:
        previous_attempt_revision = max(1, attempt_revision_value(existing_attempt))
        attempt_revision_candidate = previous_attempt_revision
        registry_label_correction = any(
            str(existing_attempt.get(field) or "") != str(value or "")
            for field, value in {
                "family_key": family_key,
                "root_key": current_root_key,
                "root_family_key": current_root_family_key,
                "artifact_family": args.artifact_family,
                "blocker_signature": current_blocker_signature,
            }.items()
        )
        if registry_label_correction:
            attempt_revision_candidate = previous_attempt_revision + 1
            supersedes_attempt_revision_candidate = previous_attempt_revision
            supersedes_attempt_identity_candidate = str(
                existing_attempt.get("attempt_identity") or attempt_identity
            )
        existing_cycle = existing_attempt
    elif existing_cycle is not None:
        # A same-cycle legacy row without the finalized content-bound identity
        # is history only. It cannot restore stale decisions by label match.
        existing_cycle = None

    gate_inputs = [
        gate for gate in gate_inputs
        if gate.get("name") != "terminal_self_resolution"
    ]
    terminal_self_resolution = terminal_self_resolution_gate(
        runner_validation,
        output_delta,
        *gate_inputs,
    )
    if bool_value(terminal_self_resolution.get("goal_terminal_prohibited")):
        gate_inputs.append(
            {
                "name": "terminal_self_resolution",
                **terminal_self_resolution,
                "constrains_disposition": True,
                "allowed_dispositions": ["goal_productive"],
            }
        )
    frame.update({
        "attempt_revision_candidate": attempt_revision_candidate,
        "existing_cycle": existing_cycle,
        "gate_inputs": gate_inputs,
        "registry_label_correction": registry_label_correction,
        "supersedes_attempt_identity_candidate": supersedes_attempt_identity_candidate,
        "supersedes_attempt_revision_candidate": supersedes_attempt_revision_candidate,
        "terminal_self_resolution": terminal_self_resolution,
    })
