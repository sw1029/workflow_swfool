from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manage-agent-authority" / "scripts"))

from manage_agent_authority import lifecycle as lifecycle_module  # noqa: E402
from manage_agent_authority import lifecycle_preflight as preflight_module  # noqa: E402
from manage_agent_authority import projection_reservations as projection_module  # noqa: E402
from manage_agent_authority.canonical import object_sha256  # noqa: E402
from manage_agent_authority.lifecycle import verify_reservation  # noqa: E402
from manage_agent_authority.verification_publication import (  # noqa: E402
    verify_and_publish_precommit,
    verify_and_publish_predispatch,
)


VERIFIED_AT = "2026-07-24T10:00:00+09:00"


def _request() -> dict[str, Any]:
    return {
        "cycle_id": "cycle-exact",
        "request_id": "request-exact",
        "subject": {"digest": "a" * 64},
    }


def _grant(
    grant_id: str,
    *,
    schema_version: int,
    request_sha256: str | None = None,
) -> dict[str, Any]:
    grant = {
        "schema_version": schema_version,
        "grant_id": grant_id,
        "expires_at": None,
        "policy_snapshot": {
            "ref": f".task/authorization/policy_snapshots/{grant_id}.json",
            "sha256": "b" * 64,
        },
    }
    if request_sha256 is not None:
        grant["request_sha256"] = request_sha256
    return grant


def _binding(grant: dict[str, Any]) -> dict[str, Any]:
    return {
        "grant_id": grant["grant_id"],
        "grant_sha256": f"{len(grant['grant_id']):064x}",
        "state_version": 0,
        "policy_snapshot": grant["policy_snapshot"],
    }


def _projection(binding: dict[str, Any]) -> dict[str, Any]:
    return {
        "grant_id": binding["grant_id"],
        "grant_sha256": binding["grant_sha256"],
        "status": "active",
        "version": 1,
        "remaining_uses": 1,
        "reserved_uses": 1,
    }


def _reservation_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    root_role: str,
    root_schema_version: int = 3,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request = _request()
    root_grant = _grant(
        "root-grant",
        schema_version=root_schema_version,
        request_sha256="f" * 64,
    )
    selected_grant = (
        root_grant
        if root_role == "selected"
        else _grant("selected-grant", schema_version=2)
    )
    selected_binding = _binding(selected_grant)
    lineage_bindings = [] if root_role == "selected" else [_binding(root_grant)]
    bindings = [selected_binding, *lineage_bindings]
    grants = {
        selected_grant["grant_id"]: selected_grant,
        root_grant["grant_id"]: root_grant,
    }
    projections = {binding["grant_id"]: _projection(binding) for binding in bindings}
    decision = {
        "decision": "allowed",
        "request": request,
        "request_sha256": object_sha256(request),
        "selected_grants": [selected_binding],
        "lineage_grants": lineage_bindings,
        "effective_authority_fingerprint": "e" * 64,
    }
    reservation = {
        "reservation_id": "existing",
        "request_id": request["request_id"],
        "request_sha256": decision["request_sha256"],
        "decision": {
            "ref": ".task/authorization/decisions/existing.json",
            "sha256": "c" * 64,
        },
        "effective_authority_fingerprint": decision["effective_authority_fingerprint"],
        "grant_uses": [
            {
                "grant_id": binding["grant_id"],
                "grant_sha256": binding["grant_sha256"],
                "units": 1,
                "state_version_before": 0,
                "state_version_after": 1,
            }
            for binding in bindings
        ],
    }
    state = {"status": "reserved", "version": 0}

    monkeypatch.setattr(
        lifecycle_module,
        "load_bound_decision",
        lambda *_args, **_kwargs: (decision, Path("existing.json")),
    )
    monkeypatch.setattr(
        lifecycle_module,
        "_validate_stored_reservation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(lifecycle_module, "subject_preflight", lambda *_args: None)
    monkeypatch.setattr(lifecycle_module, "verify_manifest", lambda *_args: None)
    monkeypatch.setattr(
        lifecycle_module,
        "verify_bound_decision_evidence",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        preflight_module,
        "load_grant",
        lambda _root, grant_id: (
            grants[grant_id],
            _binding(grants[grant_id])["grant_sha256"],
            projections[grant_id],
        ),
    )
    monkeypatch.setattr(preflight_module, "verify_binding", lambda *_args: None)
    return decision, reservation, state


@pytest.mark.parametrize("root_role", ["selected", "ancestor"])
def test_verify_rejects_mismatched_schema_v3_root_grant_in_full_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_role: str,
) -> None:
    _decision, reservation, state = _reservation_fixture(
        monkeypatch,
        root_role=root_role,
    )

    with pytest.raises(
        SystemExit,
        match="Plan-bound root grant does not cover the decision's exact request",
    ):
        verify_reservation(
            tmp_path,
            reservation,
            state,
            verified_at=VERIFIED_AT,
            expected_version=0,
        )


@pytest.mark.parametrize(
    "publisher",
    [verify_and_publish_predispatch, verify_and_publish_precommit],
)
def test_verification_publication_rejects_existing_mismatched_schema_v3_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    publisher: Any,
) -> None:
    _decision, reservation, state = _reservation_fixture(
        monkeypatch,
        root_role="selected",
    )
    monkeypatch.setattr(
        lifecycle_module,
        "recover_projection_intents",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        lifecycle_module,
        "load_reservation",
        lambda *_args, **_kwargs: (reservation, Path("existing.json"), state),
    )

    with pytest.raises(
        SystemExit,
        match="Plan-bound root grant does not cover the decision's exact request",
    ):
        publisher(
            tmp_path,
            ".task/authorization/reservations/existing.json",
            "d" * 64,
            verified_at=VERIFIED_AT,
            expected_version=0,
        )

    assert not (tmp_path / ".task/authorization/verifications").exists()


@pytest.mark.parametrize("root_role", ["selected", "ancestor"])
def test_verify_preserves_schema_v2_grant_compatibility_across_full_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_role: str,
) -> None:
    _decision, reservation, state = _reservation_fixture(
        monkeypatch,
        root_role=root_role,
        root_schema_version=2,
    )

    verified = verify_reservation(
        tmp_path,
        reservation,
        state,
        verified_at=VERIFIED_AT,
        expected_version=0,
    )

    expected_ids = (
        {"root-grant"} if root_role == "selected" else {"root-grant", "selected-grant"}
    )
    assert {item["grant_id"] for item in verified["grant_states"]} == expected_ids
    assert all(
        item["state_version"] == 1
        and item["status"] == "active"
        and item["remaining_uses"] == 1
        and item["reserved_uses"] == 1
        for item in verified["grant_states"]
    )


@pytest.mark.parametrize("root_role", ["selected", "ancestor"])
def test_projection_recovery_rejects_mismatched_schema_v3_root_request_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_role: str,
) -> None:
    request = _request()
    root_grant = _grant(
        "root-grant",
        schema_version=3,
        request_sha256="f" * 64,
    )
    selected_grant = (
        root_grant
        if root_role == "selected"
        else _grant("selected-grant", schema_version=2)
    )
    selected_binding = _binding(selected_grant)
    lineage_bindings = [] if root_role == "selected" else [_binding(root_grant)]
    decision_bindings = {
        binding["grant_id"]: binding
        for binding in [selected_binding, *lineage_bindings]
    }
    grants = {
        selected_grant["grant_id"]: selected_grant,
        root_grant["grant_id"]: root_grant,
    }
    decision = {"decision": "allowed"}
    monkeypatch.setattr(
        projection_module,
        "validate_decision_artifact",
        lambda *_args, **_kwargs: (request, decision_bindings),
    )
    monkeypatch.setattr(
        projection_module,
        "load_grant_artifact",
        lambda _root, grant_id: (grants[grant_id], _binding(grants[grant_id])),
    )

    with pytest.raises(
        SystemExit,
        match="Plan-bound root grant does not cover the decision's exact request",
    ):
        projection_module._validate_decision(
            tmp_path,
            decision,
            tmp_path / ".task/authorization/decisions/existing.json",
        )


@pytest.mark.parametrize("root_role", ["selected", "ancestor"])
def test_projection_recovery_preserves_schema_v2_request_binding_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    root_role: str,
) -> None:
    request = _request()
    root_grant = _grant("root-grant", schema_version=2)
    selected_grant = (
        root_grant
        if root_role == "selected"
        else _grant("selected-grant", schema_version=2)
    )
    selected_binding = _binding(selected_grant)
    lineage_bindings = [] if root_role == "selected" else [_binding(root_grant)]
    decision_bindings = {
        binding["grant_id"]: binding
        for binding in [selected_binding, *lineage_bindings]
    }
    grants = {
        selected_grant["grant_id"]: selected_grant,
        root_grant["grant_id"]: root_grant,
    }
    decision = {"decision": "allowed"}
    monkeypatch.setattr(
        projection_module,
        "validate_decision_artifact",
        lambda *_args, **_kwargs: (request, decision_bindings),
    )
    monkeypatch.setattr(
        projection_module,
        "load_grant_artifact",
        lambda _root, grant_id: (grants[grant_id], _binding(grants[grant_id])),
    )

    recovered_request, recovered_bindings = projection_module._validate_decision(
        tmp_path,
        decision,
        tmp_path / ".task/authorization/decisions/existing.json",
    )

    assert recovered_request == request
    assert recovered_bindings == decision_bindings


def test_reserve_existing_replay_reopens_recovery_decision_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    decision = {
        "decision": "allowed",
        "request": request,
        "request_sha256": object_sha256(request),
        "selected_grants": [_binding(_grant("root-grant", schema_version=2))],
    }
    key = "existing-replay"
    reservation_id = (
        "authz-"
        + object_sha256({"request": decision["request_sha256"], "key": key})[:24]
    )
    artifact_path = (
        tmp_path / ".task/authorization/reservations" / f"{reservation_id}.json"
    )
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_text("{}\n", encoding="utf-8")
    existing = {
        "decision": {
            "ref": ".task/authorization/decisions/existing.json",
            "sha256": "c" * 64,
        },
        "idempotency_key": key,
    }
    decision_path = tmp_path / existing["decision"]["ref"]
    monkeypatch.setattr(
        lifecycle_module,
        "load_bound_decision",
        lambda *_args, **_kwargs: (decision, decision_path),
    )
    monkeypatch.setattr(
        lifecycle_module,
        "validate_decision_artifact",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        lifecycle_module,
        "recover_projection_intents",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        lifecycle_module,
        "validated_settled_intent",
        lambda *_args, **_kwargs: existing,
    )
    validation_calls: list[tuple[dict[str, Any], Path]] = []

    def reject_mismatched_replay(
        _root: Path, artifact: dict[str, Any], path: Path
    ) -> None:
        validation_calls.append((artifact, path))
        raise SystemExit(
            "Plan-bound root grant does not cover the decision's exact request."
        )

    monkeypatch.setattr(
        lifecycle_module,
        "validate_reservation",
        reject_mismatched_replay,
    )

    with pytest.raises(
        SystemExit,
        match="Plan-bound root grant does not cover the decision's exact request",
    ):
        lifecycle_module.reserve(
            tmp_path,
            existing["decision"]["ref"],
            existing["decision"]["sha256"],
            reserved_at=VERIFIED_AT,
            idempotency_key=key,
        )

    assert validation_calls == [(existing, artifact_path)]
