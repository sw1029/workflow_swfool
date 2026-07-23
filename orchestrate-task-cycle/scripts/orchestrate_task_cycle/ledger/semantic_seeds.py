"""Opaque closed semantic seeds for non-result compiled ledger producers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .support import canonical_json_bytes


_SEED_CAPABILITY = object()
_OBSERVATION_FIELDS = {
    "observation_kind",
    "source_status",
    "execution_status",
    "long_run_branch",
    "long_run_role",
    "task_id",
    "run_id",
    "command_argv",
    "workdir",
    "output_dir",
    "log_path",
    "startup_or_heartbeat_evidence",
    "monitor_command",
    "stop_command",
    "remaining_validation",
    "expected_completion_signal",
    "expected_completion_artifacts",
    "cycle_reachability_gate",
    "unreachable_within_cycle",
    "residual_acceptance",
    "harvest_validation_plan",
    "harvest_validation_receipt",
    "recomputed_cycle_reachability_gate",
    "artifacts",
    "blockers",
    "monitor_result",
    "reason",
}
_TERMINAL_FIELDS = {
    "task_id",
    "terminal_justified",
    "terminal_outcome_key",
    "terminal_outcome_family_key",
    "terminal_latch_key_version",
    "blocker_signature",
    "input_state_fingerprint",
    "authority_state_fingerprint",
    "external_state_fingerprint",
    "input_delta",
    "material_delta",
    "required_missing_input_count",
    "authority_policy",
    "authority_policy_source",
    "residual_classification",
    "residuals",
    "lifecycle_transition_result",
    "terminal_lifecycle_kind",
    "reason",
}


@dataclass(frozen=True, slots=True)
class StageObservationSeed:
    canonical_semantics: bytes
    _capability: object


@dataclass(frozen=True, slots=True)
class TerminalLifecycleSeed:
    canonical_semantics: bytes
    _capability: object


def _seal_semantics(
    semantic: dict[str, Any],
    allowed: set[str],
    label: str,
) -> bytes:
    if not isinstance(semantic, dict):
        raise ValueError(f"{label} semantic seed must be an object")
    unsupported = set(semantic) - allowed
    if unsupported:
        raise ValueError(
            f"{label} semantic seed contains unsupported fields: "
            + ",".join(sorted(unsupported))
        )
    return canonical_json_bytes(semantic)


def make_stage_observation_seed(
    semantic: dict[str, Any],
) -> StageObservationSeed:
    if not semantic.get("observation_kind"):
        raise ValueError("stage observation semantic seed requires observation_kind")
    return StageObservationSeed(
        _seal_semantics(semantic, _OBSERVATION_FIELDS, "stage observation"),
        _SEED_CAPABILITY,
    )


def make_terminal_lifecycle_seed(
    semantic: dict[str, Any],
) -> TerminalLifecycleSeed:
    return TerminalLifecycleSeed(
        _seal_semantics(semantic, _TERMINAL_FIELDS, "terminal lifecycle"),
        _SEED_CAPABILITY,
    )


def _open_seed(value: object, expected: type, label: str) -> dict[str, Any]:
    if not isinstance(value, expected) or value._capability is not _SEED_CAPABILITY:
        raise ValueError(f"{label} publication requires a compiler-owned semantic seed")
    try:
        semantic = json.loads(value.canonical_semantics)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} semantic seed is malformed") from exc
    if (
        not isinstance(semantic, dict)
        or canonical_json_bytes(semantic) != value.canonical_semantics
    ):
        raise ValueError(f"{label} semantic seed integrity failed")
    return semantic


def open_stage_observation_seed(value: object) -> dict[str, Any]:
    semantic = _open_seed(value, StageObservationSeed, "stage observation")
    _seal_semantics(semantic, _OBSERVATION_FIELDS, "stage observation")
    if not semantic.get("observation_kind"):
        raise ValueError("stage observation semantic seed requires observation_kind")
    return semantic


def open_terminal_lifecycle_seed(value: object) -> dict[str, Any]:
    semantic = _open_seed(value, TerminalLifecycleSeed, "terminal lifecycle")
    _seal_semantics(semantic, _TERMINAL_FIELDS, "terminal lifecycle")
    return semantic


__all__ = [
    "StageObservationSeed",
    "TerminalLifecycleSeed",
    "make_stage_observation_seed",
    "make_terminal_lifecycle_seed",
    "open_stage_observation_seed",
    "open_terminal_lifecycle_seed",
]
