from __future__ import annotations

import pytest

from manage_agent_authority.recovery_materialization import (
    validate_recovery_user_decision,
)


RECIPE_BINDING = {"ref": ".task/recovery/recipe.json", "sha256": "a" * 64}
PROJECTION = {
    "projection_id": "authp-exact",
    "typed_intent": "grant_authority",
    "grant_id": "grant-exact",
}


def recipe() -> dict[str, object]:
    return {
        "prepared_at": "2026-07-23T09:00:00+09:00",
        "approval_projection": PROJECTION,
        "source_approval_requirements": {
            "expires_at_ceiling": "2026-07-23T11:00:00+09:00"
        },
    }


def decision() -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_kind": "authority_recovery_user_decision",
        "decision": "approved",
        "recovery_recipe": RECIPE_BINDING,
        "approval_projection": PROJECTION,
        "decided_at": "2026-07-23T10:00:00+09:00",
        "evidence_id": "explicit-user-decision-1",
    }


def test_recovery_materializer_requires_exact_external_projection_echo() -> None:
    assert validate_recovery_user_decision(
        decision(), recipe_binding=RECIPE_BINDING, recipe=recipe()
    )["decision"] == "approved"
    broader = decision()
    broader["approval_projection"] = {**PROJECTION, "grant_id": "other"}
    with pytest.raises(SystemExit, match="exact projection"):
        validate_recovery_user_decision(
            broader, recipe_binding=RECIPE_BINDING, recipe=recipe()
        )


def test_recovery_materializer_rejects_stale_or_self_invented_decisions() -> None:
    stale = decision()
    stale["decided_at"] = "2026-07-23T12:00:00+09:00"
    with pytest.raises(SystemExit, match="outside the approval window"):
        validate_recovery_user_decision(
            stale, recipe_binding=RECIPE_BINDING, recipe=recipe()
        )
    malformed = decision()
    malformed["model_asserted_approval"] = True
    with pytest.raises(SystemExit, match="closed typed object"):
        validate_recovery_user_decision(
            malformed, recipe_binding=RECIPE_BINDING, recipe=recipe()
        )
