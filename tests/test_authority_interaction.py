"""Focused contract tests for optional signed authority-interaction mode."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import pytest

from manage_agent_authority import authority_interaction as interaction
from manage_agent_authority.canonical import object_sha256
from manage_agent_authority.root_grant_request_binding import (
    root_grant_request_binding_covers,
)
from manage_agent_authority.stable_store import publish_immutable


CONFIG = """schema_version = 1
enabled = true
default_mode = "governed"
activation_scope = "workspace_goal"
activation_ttl_days = 30
runtime_mode_policy = "narrow_only"

[limits]
max_child_grants = 256
max_total_uses = 512
max_bounded_reusable_uses = 8
max_task_lease_uses = 32
max_improvement_lease_uses = 64
max_concurrent_long_runs = 1

[profiles.governed]
max_operation_source_floor = "S2"
max_risk = "R2"
decision_classes = ["D2", "D3"]
mutation_classes = ["local_mutation"]
cardinalities = ["single_use", "bounded_reusable", "task_lease", "improvement_lease"]
operation_groups = ["local_edit", "local_worker", "monitor_state", "task_lifecycle", "task_topology", "validation_assets", "local_long_run", "local_git_commit"]

[profiles.workspace]
max_operation_source_floor = "S1"
max_risk = "R1"
decision_classes = ["D3"]
mutation_classes = ["local_mutation"]
cardinalities = ["single_use", "bounded_reusable", "task_lease"]
operation_groups = ["local_edit", "local_worker", "monitor_state", "task_lifecycle", "validation_assets"]

[always_ask]
ssh_push = true
external_mutation = true
destructive = true
credentials = true
authority_or_policy_change = true
goal_or_design_change = true
dependency_or_model_acquisition = true
selection_retention_maintenance = true
"""


def _configure_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "authority-interaction"
    home.mkdir(mode=0o700)
    os.chmod(home, 0o700)
    config = home / "config.toml"
    config.write_text(CONFIG, encoding="utf-8")
    os.chmod(config, 0o600)
    monkeypatch.setattr(interaction, "INTERACTION_HOME", home)
    monkeypatch.setattr(interaction, "CONFIG_PATH", config)
    monkeypatch.setattr(interaction, "STATE_PATH", home / "state.json")
    monkeypatch.setattr(interaction, "LAST_ATTEMPT_PATH", home / "last_attempt.json")
    return home


def _request(cycle_id: str = "cycle-a") -> dict[str, object]:
    return {
        "schema_version": 2,
        "request_kind": "authority_operation",
        "request_id": f"request-{cycle_id}",
        "skill_id": "repo-change-commit",
        "skill_version": "2.0.0",
        "operation_id": "finalize_git_state",
        "operation_version": "1",
        "cycle_id": cycle_id,
        "task_id": "task-a",
        "pack_id": None,
        "attempt_id": "attempt-a",
        "actor_rank": "S1",
        "subject": {"kind": "repository", "ref": "repo", "digest": "a" * 64, "revision": "head-a"},
        "required_capabilities": ["repository.git.finalize"],
        "effect_class": "create_local_commit",
        "data_class": "repository_state",
        "mutation_class": "local_mutation",
        "reversibility": "conditionally_reversible",
        "risk_tier": "R2",
        "decision_class": "D3",
        "intent_type": "grant_authority",
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "reservation_units": 1,
        "idempotency_key": f"use-{cycle_id}",
        "context": {
            "external_input_status": "not_required",
            "goal_truth_status": "aligned",
            "risk_acceptance_status": "not_required",
            "design_selection_status": "not_required",
            "external_input_evidence": None,
            "risk_acceptance_evidence": None,
            "design_selection_evidence": None,
        },
        "composition_receipt": None,
    }


def _workspace(root: Path) -> dict[str, str]:
    (root / ".agent_goal").mkdir()
    for name, body in {
        "final_goal.md": "final goal\n",
        "agent_authority.md": "policy\n",
        "goal_contract.yaml": "goal: test\n",
    }.items():
        (root / ".agent_goal" / name).write_text(body, encoding="utf-8")
    policy = root / ".task/authorization/policy_snapshots/policy-test.md"
    policy.parent.mkdir(parents=True)
    policy.write_text("policy\n", encoding="utf-8")
    digest = hashlib.sha256(policy.read_bytes()).hexdigest()
    pointer = root / ".task/authorization/state/current_policy.json"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({"schema_version": 2, "artifact_kind": "current_policy_pointer", "policy_snapshot": {"ref": policy.relative_to(root).as_posix(), "sha256": digest}, "version": 1}), encoding="utf-8")
    return {"ref": policy.relative_to(root).as_posix(), "sha256": digest}


def test_config_is_secure_and_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = _configure_home(monkeypatch, tmp_path)
    config, digest, present = interaction.load_config()
    assert present and config["enabled"] and len(digest) == 64

    os.chmod(home / "config.toml", 0o644)
    with pytest.raises(SystemExit, match="unsafe_file"):
        interaction.load_config()
    os.chmod(home / "config.toml", 0o600)
    (home / "config.toml").write_text(CONFIG + "unexpected = true\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="always_ask_invalid"):
        interaction.load_config()
    (home / "config.toml").unlink()
    (home / "config.toml").symlink_to(home / "missing.toml")
    with pytest.raises(SystemExit, match="unsafe_file"):
        interaction.load_config()


def test_mode_child_is_request_bound_and_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _configure_home(monkeypatch, tmp_path)
    root = tmp_path / "workspace"
    root.mkdir()
    policy_binding = _workspace(root)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    plan_binding, _plan = interaction.build_activation_plan(root, mode="governed", prepared_at=now)
    evidence = {
        "schema_version": 1,
        "artifact_kind": "authority_interaction_activation_evidence",
        "audience": "manage-agent-authority/authority-interaction-activation",
        "issuer": "local-agent-managed-root-authorizer",
        "activation_id": "authia-test",
        "activation_plan": plan_binding,
        "approved": True,
        "decided_at": now,
        "evidence_id": "activation-evidence-test",
        "signature": {"algorithm": "rsassa-pkcs1-v1_5-sha256", "key_id": "test", "value_base64": "AA=="},
    }
    # This test exercises broker/scope/lineage mechanics independently from the
    # RSA signer, which is covered by its isolated signer contract.
    monkeypatch.setattr(interaction, "validate_activation_evidence", lambda value, **_kwargs: value)
    evidence_payload = interaction._json_bytes(evidence)
    evidence_path = root / interaction.EVIDENCE_ROOT / f"{hashlib.sha256(evidence_payload).hexdigest()}.json"
    publish_immutable(evidence_path, evidence_payload)
    evidence_binding = {"ref": evidence_path.relative_to(root).as_posix(), "sha256": hashlib.sha256(evidence_payload).hexdigest()}
    interaction.materialize_activation(root, evidence_binding)

    request = _request()
    first = interaction.materialize_mode_child(root, request, evaluated_at=now)
    second = interaction.materialize_mode_child(root, request, evaluated_at=now)
    assert first is not None and second is not None
    assert first["grant_id"] == second["grant_id"]
    grant_path = root / first["grant_binding"]["ref"]
    grant = json.loads(grant_path.read_text(encoding="utf-8"))
    assert grant["policy_snapshot"] == policy_binding
    assert grant["request_sha256"] == object_sha256(request)
    assert not root_grant_request_binding_covers(grant, _request("cycle-b"))


def test_profile_refuses_external_and_ssh_push() -> None:
    request = _request()
    profile = interaction.DEFAULT_CONFIG["profiles"]["governed"]
    external = {**request, "operation_id": "push_git_ssh", "mutation_class": "external_mutation", "risk_tier": "R3"}
    operation = {"source_rank_floor": "S3"}
    assert not interaction._operation_allowed(external, operation, profile)
