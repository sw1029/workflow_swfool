from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from orchestrate_task_cycle import mode_profile, validate_cycle_transition


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "orchestrate-task-cycle" / "references" / "mode-profiles.json"


def profile(profile_id: str, **overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "format_version": 1,
        "artifact_kind": "workflow_mode_profile",
        "profile_id": profile_id,
        "profile_version": 1,
        "capture": "conversation_projection",
        "consume": "advisory",
        "reaction": "proposal_only",
        "allowed_repairs": [],
        "required_hook_signatures": ["session_observation"],
        "required_consumer_ids": ["orchestrate-session-audit"],
        "local_override": False,
        "not_goal_truth": True,
        "not_validation_evidence": True,
    }
    value.update(overrides)
    return value


def test_tracked_registry_profiles_validate_and_keep_workflow_phases_unchanged() -> (
    None
):
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert [item["profile_id"] for item in registry["profiles"]] == [
        "observation-shadow",
        "observation-advisory",
        "audit-index-repair",
    ]
    for item in registry["profiles"]:
        mode_profile.validate_profile(item)
    with pytest.raises(ValueError, match="unsupported workflow mode"):
        validate_cycle_transition.validate(
            {}, {}, "pre_context", workflow_mode="profile"
        )


def test_observation_cannot_self_activate_required_or_repair_profile() -> None:
    repair = profile(
        "repair",
        reaction="derived_metadata_only",
        allowed_repairs=[
            {"operation": "rebuild_index", "target": ".task/session_audit/index.json"}
        ],
    )
    with pytest.raises(mode_profile.ModeProfileError, match="activation source"):
        mode_profile.resolve_profile(repair, activation_source="session_observation")
    with pytest.raises(mode_profile.ModeProfileError, match="needs user"):
        mode_profile.resolve_profile(repair, activation_source="default")


def test_exact_index_repair_is_the_only_auto_repair() -> None:
    valid = profile(
        "repair",
        reaction="derived_metadata_only",
        allowed_repairs=[
            {"operation": "rebuild_index", "target": ".task/session_audit/index.json"}
        ],
    )
    resolved = mode_profile.resolve_profile(valid, activation_source="caller_policy")
    assert resolved["allowed_effects"]["derived_metadata_repair_allowed"] is True
    assert resolved["allowed_effects"]["semantic_mutation_allowed"] is False
    assert resolved["repair_receipt_required"] is True

    forged = profile(
        "forged",
        reaction="derived_metadata_only",
        allowed_repairs=[{"operation": "rewrite_task", "target": "task.md"}],
    )
    with pytest.raises(
        mode_profile.ModeProfileError, match="outside the exact allowlist"
    ):
        mode_profile.validate_profile(forged)


def test_local_override_can_only_reduce_capability_and_add_probe_requirements() -> None:
    base = profile("base")
    reducing = profile(
        "local-off",
        capture="off",
        consume="shadow",
        reaction="observe",
        required_hook_signatures=["session_observation", "retention_policy"],
        required_consumer_ids=["orchestrate-session-audit", "local-retention-check"],
        local_override=True,
    )
    resolved = mode_profile.resolve_profile(base, override_value=reducing)
    assert resolved["effective_profile"]["capture"] == "off"
    assert resolved["allowed_effects"]["authority_expansion_allowed"] is False

    escalating = profile("local-required", consume="required", local_override=True)
    with pytest.raises(
        mode_profile.ModeProfileError, match="increase consumption authority"
    ):
        mode_profile.resolve_profile(base, override_value=escalating)

    alternate_capture = profile(
        "local-telemetry", capture="structured_telemetry", local_override=True
    )
    with pytest.raises(mode_profile.ModeProfileError, match="another active capture"):
        mode_profile.resolve_profile(base, override_value=alternate_capture)


def test_unknown_fields_and_authority_flags_fail_closed() -> None:
    unknown = profile("unknown")
    unknown["semantic_mutation_allowed"] = True
    with pytest.raises(mode_profile.ModeProfileError, match="closed"):
        mode_profile.validate_profile(unknown)

    promoted = profile("promoted", not_goal_truth=False)
    with pytest.raises(mode_profile.ModeProfileError, match="non-GT"):
        mode_profile.validate_profile(promoted)


def test_resolution_is_deterministically_revalidated_against_tracked_registry() -> None:
    repair = mode_profile.load_profile(REGISTRY, "audit-index-repair")
    resolution = mode_profile.resolve_profile(
        repair,
        activation_source="caller_policy",
    )
    assert (
        mode_profile.validate_resolution(
            resolution,
            registry_path=REGISTRY,
        )
        == resolution
    )

    forged = json.loads(json.dumps(resolution))
    forged["allowed_effects"]["semantic_mutation_allowed"] = True
    with pytest.raises(mode_profile.ModeProfileError, match="deterministic"):
        mode_profile.validate_resolution(forged, registry_path=REGISTRY)
