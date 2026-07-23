from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "manage-agent-authority" / "scripts"))

from manage_agent_authority import authority_cli  # noqa: E402
from manage_agent_authority import composition_intent_compiler  # noqa: E402
from manage_agent_authority import root_authority_admin  # noqa: E402
from manage_agent_authority import root_authorization_evidence  # noqa: E402
from manage_agent_authority import root_authorization_signer  # noqa: E402
from manage_agent_authority.artifact_store import (  # noqa: E402
    load_grant,
    register_grant,
    snapshot_file,
    update_current_policy,
)
from manage_agent_authority.canonical import read_object, sha256_file  # noqa: E402
from manage_agent_authority.contracts import validate_grant  # noqa: E402
from manage_agent_authority.operation_batch import (  # noqa: E402
    MAX_OPERATION_SET_BYTES,
    load_operation_batch,
    publish_operation_set,
    publish_operation_batch,
)
from manage_agent_authority.root_grant import (  # noqa: E402
    compile_root_decision_seed,
    load_root_approval_plan,
    materialize_exact_echo_root_grant,
    prepare_root_approval_plan,
)
from manage_agent_authority.semantic_context import (  # noqa: E402
    load_shared_semantic_context,
    publish_shared_semantic_context,
)
from manage_agent_authority.source_approval import (  # noqa: E402
    load_source_approval,
    validate_for_grant,
    validate_source_approval,
)
from manage_agent_authority import root_grant_transaction  # noqa: E402
from root_authorization_test_support import (  # noqa: E402
    install_test_trust_anchor,
    signed_root_authorization,
)
from root_tty_test_support import run_with_tty  # noqa: E402
from manage_agent_authority.root_authority_registry import (  # noqa: E402
    canonical_json as canonical_registry_json,
    empty_registry,
    sha256_bytes,
)


AT = "2026-07-23T10:00:00+09:00"
DECIDED_AT = "2026-07-23T10:05:00+09:00"
EXPIRES_AT = "2026-07-23T11:00:00+09:00"


@pytest.fixture(autouse=True)
def _host_authorization_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_test_trust_anchor(monkeypatch, tmp_path)


def _write(path: Path, value: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def _tree_image(root: Path) -> list[tuple[str, str, bytes]]:
    image: list[tuple[str, str, bytes]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            image.append(
                (relative, "symlink", path.readlink().as_posix().encode())
            )
        elif path.is_dir():
            image.append((relative, "directory", b""))
        else:
            image.append((relative, "file", path.read_bytes()))
    return image


def _semantic(root: Path) -> tuple[dict[str, object], str]:
    subject = _write(root / "plans/task-transition.json", '{"plan":true}\n')
    goal = _write(root / ".agent_goal/goal_architecture.md", "# Goal\n")
    digest = hashlib.sha256(subject.read_bytes()).hexdigest()
    return (
        {
            "actor_rank": "S0",
            "request_context": {
                "external_input_status": "not_required",
                "goal_truth_status": "aligned",
                "risk_acceptance_status": "resolved",
                "design_selection_status": "resolved",
                "risk_acceptance_evidence_ref": "evidence/risk.json",
                "design_selection_evidence_ref": "evidence/design.json",
            },
            "session_ceiling": {
                "capabilities": ["task.scope.mutate"],
                "risk_ceiling": "R3",
                "mutation_classes": ["local_mutation"],
                "evidence_id": "session-exact",
            },
            "goal_autonomy_envelope": {
                "envelope_id": "goal-envelope-exact",
                "capabilities": ["task.scope.mutate"],
                "risk_ceiling": "R3",
                "decision_classes": ["D2"],
                "subjects": [digest],
                "operations": ["task-doctor:2.2.0:mutate_task_scope:1"],
                "source_ref": str(goal.relative_to(root)),
            },
        },
        digest,
    )


def _prepare_inputs(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    _write(root / "evidence/risk.json", "{}\n")
    _write(root / "evidence/design.json", "{}\n")
    semantic, _digest = _semantic(root)
    initialization_path = _write(
        root / ".task/cycle/cycle-compiler-first/initialization.json",
        json.dumps(
            {
                "format_version": 1,
                "cycle_id": "cycle-compiler-first",
                "task_id": "task-1",
            },
            sort_keys=True,
        )
        + "\n",
    )
    initialization_binding = {
        "ref": str(initialization_path.relative_to(root)),
        "sha256": sha256_file(initialization_path),
    }
    context_result = publish_shared_semantic_context(
        root, initialization_binding, semantic
    )
    context_binding = context_result["semantic_context"]
    operation_set = publish_operation_set(
        root,
        [
            {
                "skill_id": "task-doctor",
                "operation_id": "mutate_task_scope",
                "subject": {
                    "ref": "plans/task-transition.json",
                    "revision": "plan-1",
                },
                "scope": {
                    "task_id": "task-1",
                    "pack_id": None,
                },
            }
        ],
    )
    batch_result = publish_operation_batch(
        root,
        context_binding,
        operation_set["operation_set"],
        compiled_at=AT,
        skills_root=ROOT,
    )
    return context_binding, batch_result["operation_batch"]


def _prepared_root_materialization(
    root: Path,
) -> tuple[dict[str, str], dict[str, str], dict[str, object]]:
    _context, batch = _prepare_inputs(root)
    policy = _write(root / ".agent_goal/agent_authority.md", "# Authority\n")
    policy_binding = snapshot_file(
        root, policy.relative_to(root).as_posix(), "policy"
    )
    update_current_policy(root, policy_binding, expected_version=0)
    prepared = prepare_root_approval_plan(
        root,
        batch,
        policy_binding,
        {
            "source_kind": "explicit_user_instruction",
            "holder_rank": "S0",
            "expires_at": EXPIRES_AT,
            "session_id": "session-exact",
        },
        prepared_at=AT,
        skills_root=ROOT,
    )
    plan_binding = prepared["root_approval_plan"]
    _normalized, plan = load_root_approval_plan(
        root, plan_binding, skills_root=ROOT
    )
    decision_result = compile_root_decision_seed(
        root,
        plan_binding,
        authorization_evidence=signed_root_authorization(
            root,
            plan_binding,
            decided_at=DECIDED_AT,
            evidence_id="transaction-decision",
            skills_root=ROOT,
        ),
        skills_root=ROOT,
    )
    return (
        plan_binding,
        decision_result["decision_seed"],
        plan,
    )


def test_cycle_shared_context_and_batch_are_producer_owned_cas(
    tmp_path: Path,
) -> None:
    context_binding, batch_binding = _prepare_inputs(tmp_path)

    normalized_context, context = load_shared_semantic_context(
        tmp_path, context_binding
    )
    normalized_batch, batch, compilations = load_operation_batch(
        tmp_path, batch_binding
    )

    assert normalized_context == context_binding
    assert normalized_batch == batch_binding
    assert context["cycle_id"] == "cycle-compiler-first"
    assert context["task_id"] == "task-1"
    assert context["field_provenance"]["authority_effect"] == "none"
    assert batch["operation_count"] == 1
    assert len(compilations) == 1
    assert compilations[0]["request"]["context"] == context["request_context"]
    assert compilations[0]["field_provenance"]["authority_effect"] == (
        "none; evaluator must verify independent authority"
    )
    copied = _write(
        tmp_path / "copied-context.json",
        (tmp_path / context_binding["ref"]).read_text(encoding="utf-8"),
    )
    with pytest.raises(SystemExit, match="producer-owned CAS"):
        load_shared_semantic_context(
            tmp_path,
            {
                "ref": str(copied.relative_to(tmp_path)),
                "sha256": sha256_file(copied),
            },
        )
    operation_set_binding = batch["operation_set"]
    copied_set = _write(
        tmp_path / "copied-operation-set.json",
        (tmp_path / operation_set_binding["ref"]).read_text(encoding="utf-8"),
    )
    with pytest.raises(SystemExit, match="producer-owned CAS"):
        publish_operation_batch(
            tmp_path,
            context_binding,
            {
                "ref": str(copied_set.relative_to(tmp_path)),
                "sha256": sha256_file(copied_set),
            },
            compiled_at=AT,
            skills_root=ROOT,
        )
    with pytest.raises(SystemExit, match="unknown=.*skill_version"):
        publish_operation_set(
            tmp_path,
            [
                {
                    "skill_id": "task-doctor",
                    "skill_version": "2.2.0",
                    "operation_id": "mutate_task_scope",
                    "subject": {
                        "ref": "plans/task-transition.json",
                        "revision": "plan-1",
                    },
                    "scope": {"pack_id": None},
                }
            ],
        )


def test_composition_compiler_derives_receipt_from_producer_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _context_binding, batch_binding = _prepare_inputs(tmp_path)
    _normalized, _batch, compilations = load_operation_batch(
        tmp_path, batch_binding, skills_root=ROOT
    )
    request_sha256 = compilations[0]["request_sha256"]
    observed: list[dict[str, object]] = []

    monkeypatch.setattr(
        composition_intent_compiler,
        "load_grant",
        lambda _root, grant_id: (
            {"grant_id": grant_id},
            hashlib.sha256(grant_id.encode()).hexdigest(),
            {"status": "active"},
        ),
    )
    monkeypatch.setattr(
        composition_intent_compiler,
        "validate_composition_source_binding",
        lambda _root, binding: binding,
    )

    def capture_composition(
        _root: Path,
        value: dict[str, object],
        *,
        producer_capability: object,
    ) -> dict[str, object]:
        assert producer_capability is not None
        observed.append(value)
        return {
            "composition": value,
            "ref": ".task/authorization/compositions/compiled.json",
            "sha256": "a" * 64,
        }

    monkeypatch.setattr(
        composition_intent_compiler,
        "_create_compiled_composition",
        capture_composition,
    )
    source = {"ref": "source.json", "sha256": "b" * 64}
    first = composition_intent_compiler.compile_grant_composition(
        tmp_path,
        batch_binding,
        request_sha256,
        ["grant-b", "grant-a"],
        source,
        created_at=DECIDED_AT,
        skills_root=ROOT,
    )
    second = composition_intent_compiler.compile_grant_composition(
        tmp_path,
        batch_binding,
        request_sha256,
        ["grant-b", "grant-a"],
        source,
        created_at=DECIDED_AT,
        skills_root=ROOT,
    )

    assert first == second
    assert first["model_authored_mechanical_bytes"] == 0
    assert observed[0]["grant_ids"] == ["grant-a", "grant-b"]
    assert observed[0]["composition_id"].startswith("authcomp-")
    assert observed[0]["idempotency_key"].startswith("authcompk-")
    assert observed[0]["request_sha256"] == request_sha256

    copied = _write(
        tmp_path / "copied-batch.json",
        (tmp_path / batch_binding["ref"]).read_text(encoding="utf-8"),
    )
    with pytest.raises(SystemExit, match="producer-owned CAS"):
        composition_intent_compiler.compile_grant_composition(
            tmp_path,
            {
                "ref": str(copied.relative_to(tmp_path)),
                "sha256": sha256_file(copied),
            },
            request_sha256,
            ["grant-a", "grant-b"],
            source,
            created_at=DECIDED_AT,
            skills_root=ROOT,
        )


def test_operation_set_is_bounded_canonical_and_duplicate_free(
    tmp_path: Path,
) -> None:
    first = {
        "skill_id": "task-doctor",
        "operation_id": "mutate_task_scope",
        "subject": {"ref": "plans/a.json", "revision": "a"},
        "scope": {"pack_id": None},
    }
    second = {
        "skill_id": "task-doctor",
        "operation_id": "mutate_task_scope",
        "subject": {"ref": "plans/b.json", "revision": "b"},
        "scope": {"pack_id": None},
    }
    forward = publish_operation_set(tmp_path, [first, second])
    reverse = publish_operation_set(tmp_path, [second, first])
    assert forward["operation_set"] == reverse["operation_set"]
    with pytest.raises(SystemExit, match="duplicate semantic operation"):
        publish_operation_set(tmp_path, [first, first])
    explicit_defaults = {
        **first,
        "scope": {
            "cycle_id": None,
            "task_id": None,
            "pack_id": None,
        },
        "cardinality_requested": "single_use",
        "use_budget_requested": 1,
        "reservation_units": 1,
        "classification": {},
        "composition_receipt": None,
    }
    with pytest.raises(SystemExit, match="duplicate semantic operation"):
        publish_operation_set(tmp_path, [first, explicit_defaults])
    with pytest.raises(SystemExit, match="128-operation limit"):
        publish_operation_set(
            tmp_path,
            [
                {
                    **first,
                    "subject": {
                        "ref": f"plans/{index}.json",
                        "revision": str(index),
                    },
                }
                for index in range(129)
            ],
        )
    oversized = {
        **first,
        "subject": {
            "ref": "x" * MAX_OPERATION_SET_BYTES,
            "revision": "oversized",
        },
    }
    with pytest.raises(SystemExit, match="byte limit"):
        publish_operation_set(tmp_path, [oversized])


def test_batch_rejects_compiled_time_provenance_and_classification_drift(
    tmp_path: Path,
) -> None:
    context_binding, original_batch_binding = _prepare_inputs(tmp_path)
    original_path = tmp_path / original_batch_binding["ref"]
    original = json.loads(original_path.read_text(encoding="utf-8"))

    for label, mutate in (
        (
            "compiled-at",
            lambda value: value.update(
                {"compiled_at": "2026-07-23T10:01:00+09:00"}
            ),
        ),
        (
            "provenance",
            lambda value: value["field_provenance"].update(
                {"authority_effect": "caller supplied"}
            ),
        ),
    ):
        forged = json.loads(json.dumps(original))
        mutate(forged)
        body = {
            key: value
            for key, value in forged.items()
            if key != "batch_fingerprint"
        }
        forged["batch_fingerprint"] = hashlib.sha256(
            json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        forged_path = _write(
            tmp_path
            / ".task/authorization/operation_batches/sha256"
            / f"{forged['batch_fingerprint']}.json",
            json.dumps(forged, indent=2, sort_keys=True) + "\n",
        )
        with pytest.raises(SystemExit):
            load_operation_batch(
                tmp_path,
                {
                    "ref": forged_path.relative_to(tmp_path).as_posix(),
                    "sha256": sha256_file(forged_path),
                },
                skills_root=ROOT,
            )

    original_set_binding = original["operation_set"]
    original_set = json.loads(
        (tmp_path / original_set_binding["ref"]).read_text(encoding="utf-8")
    )
    classified_seed = json.loads(json.dumps(original_set["operations"][0]))
    classified_seed["classification"] = {"risk_tier": "R3"}
    classified_set = publish_operation_set(tmp_path, [classified_seed])
    classified_batch = publish_operation_batch(
        tmp_path,
        context_binding,
        classified_set["operation_set"],
        compiled_at=AT,
        skills_root=ROOT,
    )
    classified_value = json.loads(
        (tmp_path / classified_batch["operation_batch"]["ref"]).read_text(
            encoding="utf-8"
        )
    )
    forged = {
        **original,
        "operation_compilations": classified_value["operation_compilations"],
    }
    forged_body = {
        key: value for key, value in forged.items() if key != "batch_fingerprint"
    }
    forged["batch_fingerprint"] = hashlib.sha256(
        json.dumps(
            forged_body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    forged_path = _write(
        tmp_path
        / ".task/authorization/operation_batches/sha256"
        / f"{forged['batch_fingerprint']}.json",
        json.dumps(forged, indent=2, sort_keys=True) + "\n",
    )
    with pytest.raises(SystemExit, match="exact compiler rendering"):
        load_operation_batch(
            tmp_path,
            {
                "ref": forged_path.relative_to(tmp_path).as_posix(),
                "sha256": sha256_file(forged_path),
            },
            skills_root=ROOT,
        )


def test_semantic_context_derives_cycle_and_task_from_exact_initialization(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "evidence/risk.json", "{}\n")
    _write(tmp_path / "evidence/design.json", "{}\n")
    semantic, _digest = _semantic(tmp_path)
    initialization_path = _write(
        tmp_path / ".task/cycle/cycle-compiler-first/initialization.json",
        json.dumps(
            {
                "format_version": 1,
                "cycle_id": "cycle-compiler-first",
                "task_id": "task-1",
            }
        )
        + "\n",
    )
    binding = {
        "ref": str(initialization_path.relative_to(tmp_path)),
        "sha256": sha256_file(initialization_path),
    }
    conflicting = {**semantic, "cycle_id": "cycle-other"}
    with pytest.raises(SystemExit, match="unknown fields"):
        publish_shared_semantic_context(tmp_path, binding, conflicting)
    conflicting = {**semantic, "task_id": "task-other"}
    with pytest.raises(SystemExit, match="unknown fields"):
        publish_shared_semantic_context(tmp_path, binding, conflicting)

    copied = _write(
        tmp_path / "copied-initialization.json",
        initialization_path.read_text(encoding="utf-8"),
    )
    with pytest.raises(SystemExit, match="canonical cycle path"):
        publish_shared_semantic_context(
            tmp_path,
            {
                "ref": str(copied.relative_to(tmp_path)),
                "sha256": sha256_file(copied),
            },
            semantic,
        )


def test_root_plan_uses_compact_decision_seed_and_materializes_plan_bound_source(
    tmp_path: Path,
) -> None:
    _context_binding, batch_binding = _prepare_inputs(tmp_path)
    policy = _write(tmp_path / ".agent_goal/agent_authority.md", "# Authority\n")
    policy_binding = snapshot_file(
        tmp_path, str(policy.relative_to(tmp_path)), "policy"
    )
    update_current_policy(tmp_path, policy_binding, expected_version=0)
    semantics = {
        "source_kind": "explicit_user_instruction",
        "holder_rank": "S0",
        "expires_at": EXPIRES_AT,
        "session_id": "session-exact",
    }
    prepared = prepare_root_approval_plan(
        tmp_path,
        batch_binding,
        policy_binding,
        semantics,
        prepared_at=AT,
        skills_root=ROOT,
    )
    assert prepared["authority_effects_applied"] is False
    assert "approval_projection" not in prepared
    assert prepared["approval_summary"]["grant_count"] == 1
    plan_binding = prepared["root_approval_plan"]
    _normalized, plan = load_root_approval_plan(
        tmp_path, plan_binding, skills_root=ROOT
    )
    projection = plan["approval_projection"]
    assert projection["decision_trust_class"] == "host_user_signed_exact_plan"
    assert (
        "no unsigned or caller-selected trust-anchor fallback"
        in projection["excluded_effects"]
    )
    authorization_evidence = signed_root_authorization(
        tmp_path,
        plan_binding,
        decided_at=DECIDED_AT,
        evidence_id="caller-decision-1",
        skills_root=ROOT,
    )
    decision_result = compile_root_decision_seed(
        tmp_path,
        plan_binding,
        authorization_evidence=authorization_evidence,
        skills_root=ROOT,
    )
    decision_binding = decision_result["decision_seed"]
    result = materialize_exact_echo_root_grant(
        tmp_path,
        plan_binding,
        decision_binding,
        skills_root=ROOT,
    )
    source = load_source_approval(tmp_path / result["source_approval"]["ref"])
    assert result["decision_trust_class"] == "host_user_signed_exact_plan"
    assert source["schema_version"] == 5
    assert source["decision_binding"] == decision_binding
    assert source["decision_trust_class"] == "host_user_signed_exact_plan"
    assert source["grant_projections"] == projection["grants"]
    assert "integrity_status" not in source
    historical_source = {
        **source,
        "schema_version": 4,
        "decision_trust_class": "caller_asserted_plan_decision",
    }
    validated_historical = validate_source_approval(historical_source)
    grant, _grant_sha, _grant_state = load_grant(
        tmp_path, projection["grants"][0]["grant_id"]
    )
    with pytest.raises(SystemExit, match="schema-v2/v4"):
        validate_for_grant(
            tmp_path, validated_historical, grant, prospective=True
        )

    forged_evidence = json.loads(
        (tmp_path / authorization_evidence["ref"]).read_text(encoding="utf-8")
    )
    forged_evidence["evidence_id"] = "caller-decision-denied"
    from manage_agent_authority.root_authorization_evidence import (
        publish_root_authorization_evidence,
    )

    with pytest.raises(SystemExit, match="not signed by an active trusted"):
        publish_root_authorization_evidence(
            tmp_path, forged_evidence, skills_root=ROOT
        )
    with pytest.raises(SystemExit, match="does not identify an existing path"):
        compile_root_decision_seed(
            tmp_path,
            plan_binding,
            authorization_evidence={
                "ref": "forged-evidence.json",
                "sha256": "0" * 64,
            },
            skills_root=ROOT,
        )
    altered = {
        "schema_version": 2,
        "artifact_kind": "authority_root_approval_decision_seed",
        "approved": True,
        "approval_plan": plan_binding,
        "decided_at": DECIDED_AT,
        "evidence_id": "caller-decision-manual",
    }
    altered_path = _write(
        tmp_path / ".task/authorization/root-decision-altered.json",
        json.dumps(altered, indent=2, sort_keys=True) + "\n",
    )
    with pytest.raises(SystemExit, match="producer CAS"):
        materialize_exact_echo_root_grant(
            tmp_path,
            plan_binding,
            {
                "ref": str(altered_path.relative_to(tmp_path)),
                "sha256": sha256_file(altered_path),
            },
            skills_root=ROOT,
        )


def test_root_authorization_fails_closed_without_trusted_host_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_binding, decision_binding, _plan = _prepared_root_materialization(
        tmp_path
    )
    empty_registry = tmp_path / "empty-root-authorization.trust.json"
    empty_registry.write_bytes(
        _canonical_trust_registry([])
    )
    monkeypatch.setattr(
        root_authorization_evidence,
        "TRUST_ANCHOR_REGISTRY",
        empty_registry,
    )

    with pytest.raises(SystemExit, match="not signed by an active trusted"):
        materialize_exact_echo_root_grant(
            tmp_path,
            plan_binding,
            decision_binding,
            skills_root=ROOT,
        )


def test_agent_managed_signer_full_root_grant_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = tmp_path / "host"
    host.mkdir(mode=0o700)
    registry = host / "root-authorization.trust.json"
    empty_payload = canonical_registry_json(empty_registry())
    registry.write_bytes(empty_payload)
    registry.chmod(0o600)
    store = host / "root-authorization"
    monkeypatch.setattr(
        root_authority_admin,
        "TRUST_ANCHOR_REGISTRY",
        registry,
    )
    monkeypatch.setattr(
        root_authority_admin,
        "ROOT_AUTHORIZATION_HOME",
        store,
    )
    monkeypatch.setattr(
        root_authorization_signer,
        "TRUST_ANCHOR_REGISTRY",
        registry,
    )
    monkeypatch.setattr(
        root_authorization_signer,
        "ROOT_AUTHORIZATION_HOME",
        store,
    )
    monkeypatch.setattr(
        root_authorization_evidence,
        "TRUST_ANCHOR_REGISTRY",
        registry,
    )
    provisioned = root_authority_admin.provision(
        expected_registry_sha256=sha256_bytes(empty_payload)
    )

    _context, batch = _prepare_inputs(tmp_path)
    policy = _write(tmp_path / ".agent_goal/agent_authority.md", "# Authority\n")
    policy_binding = snapshot_file(
        tmp_path,
        policy.relative_to(tmp_path).as_posix(),
        "policy",
    )
    update_current_policy(tmp_path, policy_binding, expected_version=0)
    prepared = prepare_root_approval_plan(
        tmp_path,
        batch,
        policy_binding,
        {
            "source_kind": "explicit_user_instruction",
            "holder_rank": "S0",
            "expires_at": EXPIRES_AT,
            "session_id": "session-exact",
        },
        prepared_at=AT,
        skills_root=ROOT,
    )
    plan_binding = prepared["root_approval_plan"]
    monkeypatch.setattr(
        root_authorization_signer,
        "_utc_now",
        lambda: DECIDED_AT,
    )
    expected_confirmation = f"APPROVE ROOT PLAN {plan_binding['sha256']}"
    declined = run_with_tty(
        lambda: root_authorization_signer.approve_root_plan(
            tmp_path,
            approval_plan_ref=plan_binding["ref"],
            approval_plan_sha256=plan_binding["sha256"],
            key_id=provisioned["key_id"],
        ),
        input_bytes=(expected_confirmation + ".\n").encode("utf-8"),
    )
    assert declined.status == "system_exit"
    assert declined.message == "root_confirmation_mismatch"
    assert not (store / "outbox").exists()

    prompt_window = iter((DECIDED_AT, EXPIRES_AT))
    monkeypatch.setattr(
        root_authorization_signer,
        "_utc_now",
        lambda: next(prompt_window),
    )
    expired_during_confirmation = run_with_tty(
        lambda: root_authorization_signer.approve_root_plan(
            tmp_path,
            approval_plan_ref=plan_binding["ref"],
            approval_plan_sha256=plan_binding["sha256"],
            key_id=provisioned["key_id"],
        ),
        input_bytes=(expected_confirmation + "\n").encode("utf-8"),
    )
    assert expired_during_confirmation.status == "system_exit"
    assert expired_during_confirmation.message == (
        "Root approval plan is outside its approval window."
    )
    assert not (store / "outbox").exists()
    monkeypatch.setattr(
        root_authorization_signer,
        "_utc_now",
        lambda: DECIDED_AT,
    )

    signed_result = run_with_tty(
        lambda: root_authorization_signer.approve_root_plan(
            tmp_path,
            approval_plan_ref=plan_binding["ref"],
            approval_plan_sha256=plan_binding["sha256"],
            key_id=provisioned["key_id"],
        ),
        input_bytes=(expected_confirmation + "\n").encode("utf-8"),
    )
    assert signed_result.status == "ok"
    signed = signed_result.value
    evidence_path = Path(signed["evidence_path"])
    assert evidence_path.is_file()
    assert stat.S_IMODE(evidence_path.stat().st_mode) == 0o600
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    published = (
        root_authorization_evidence.publish_root_authorization_evidence(
            tmp_path,
            evidence,
            skills_root=ROOT,
        )
    )
    decision = compile_root_decision_seed(
        tmp_path,
        plan_binding,
        authorization_evidence=published["authorization_evidence"],
        skills_root=ROOT,
    )
    materialized = materialize_exact_echo_root_grant(
        tmp_path,
        plan_binding,
        decision["decision_seed"],
        skills_root=ROOT,
    )
    assert materialized["status"] == "materialized"
    assert materialized["decision_trust_class"] == (
        "host_user_signed_exact_plan"
    )
    replay = run_with_tty(
        lambda: root_authorization_signer.approve_root_plan(
            tmp_path,
            approval_plan_ref=plan_binding["ref"],
            approval_plan_sha256=plan_binding["sha256"],
            key_id=provisioned["key_id"],
        ),
        input_bytes=(expected_confirmation + "\n").encode("utf-8"),
    )
    assert replay.status == "system_exit"
    assert "already exists" in replay.message
    revocation_confirmation = (
        f"REVOKE {provisioned['key_id']} "
        "AND INVALIDATE EXISTING EVIDENCE"
    )
    monkeypatch.setattr(
        root_authority_admin,
        "_tty_confirmation",
        lambda expected: revocation_confirmation,
    )
    root_authority_admin.revoke_public_key(
        provisioned["key_id"],
        reason="integration-revocation",
        expected_registry_sha256=provisioned["registry_sha256_after"],
    )
    with pytest.raises(SystemExit, match="not signed by an active trusted"):
        root_authorization_evidence.publish_root_authorization_evidence(
            tmp_path,
            evidence,
            skills_root=ROOT,
        )


def _canonical_trust_registry(keys: list[dict[str, object]]) -> bytes:
    return (
        json.dumps(
            {
                "artifact_kind":
                    "authority_root_authorization_trust_anchors",
                "keys": keys,
                "schema_version": 1,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def test_root_signature_verifier_rejects_representative_at_modulus() -> None:
    modulus_hex = "f1" + ("00" * 255)
    modulus = int(modulus_hex, 16)
    signature = modulus.to_bytes(256, "big")

    assert root_authorization_evidence._verify_rsa_signature(  # noqa: SLF001
        b"exact-plan",
        signature,
        modulus_hex=modulus_hex,
        exponent=65537,
    ) is False


def test_ordinary_root_exact_echo_rejects_platform_s4(
    tmp_path: Path,
) -> None:
    _context_binding, batch_binding = _prepare_inputs(tmp_path)
    policy = _write(tmp_path / ".agent_goal/agent_authority.md", "# Authority\n")
    policy_binding = snapshot_file(
        tmp_path, str(policy.relative_to(tmp_path)), "policy"
    )
    update_current_policy(tmp_path, policy_binding, expected_version=0)
    with pytest.raises(SystemExit, match="platform-attested producer"):
        prepare_root_approval_plan(
            tmp_path,
            batch_binding,
            policy_binding,
            {
                "source_kind": "platform_session_ceiling",
                "holder_rank": "S0",
                "expires_at": EXPIRES_AT,
                "session_id": "session-exact",
            },
            prepared_at=AT,
            skills_root=ROOT,
        )


def test_root_plan_uses_current_policy_and_compilation_minimum_grants(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "evidence/risk.json", "{}\n")
    _write(tmp_path / "evidence/design.json", "{}\n")
    first = _write(tmp_path / "plans/first.json", '{"plan":1}\n')
    second = _write(tmp_path / "plans/second.json", '{"plan":2}\n')
    goal = _write(tmp_path / ".agent_goal/goal_architecture.md", "# Goal\n")
    initialization = _write(
        tmp_path / ".task/cycle/cycle-minimum/initialization.json",
        json.dumps(
            {"format_version": 1, "cycle_id": "cycle-minimum", "task_id": "task-1"}
        )
        + "\n",
    )
    context = publish_shared_semantic_context(
        tmp_path,
        {
            "ref": str(initialization.relative_to(tmp_path)),
            "sha256": sha256_file(initialization),
        },
        {
            "actor_rank": "S0",
            "request_context": {
                "external_input_status": "not_required",
                "goal_truth_status": "aligned",
                "risk_acceptance_status": "resolved",
                "design_selection_status": "resolved",
                "risk_acceptance_evidence_ref": "evidence/risk.json",
                "design_selection_evidence_ref": "evidence/design.json",
            },
            "session_ceiling": {
                "capabilities": ["task.scope.mutate"],
                "risk_ceiling": "R3",
                "mutation_classes": ["local_mutation"],
                "evidence_id": "session-minimum",
            },
            "goal_autonomy_envelope": {
                "envelope_id": "envelope-minimum",
                "capabilities": ["task.scope.mutate"],
                "risk_ceiling": "R3",
                "decision_classes": ["D2"],
                "subjects": [
                    hashlib.sha256(first.read_bytes()).hexdigest(),
                    hashlib.sha256(second.read_bytes()).hexdigest(),
                ],
                "operations": ["task-doctor:2.2.0:mutate_task_scope:1"],
                "source_ref": str(goal.relative_to(tmp_path)),
            },
        },
    )
    operation_set = publish_operation_set(
        tmp_path,
        [
            {
                "skill_id": "task-doctor",
                "operation_id": "mutate_task_scope",
                "subject": {"ref": "plans/first.json", "revision": "first"},
                "scope": {"pack_id": None},
            },
            {
                "skill_id": "task-doctor",
                "operation_id": "mutate_task_scope",
                "subject": {"ref": "plans/second.json", "revision": "second"},
                "scope": {"pack_id": None},
            },
        ],
    )
    batch = publish_operation_batch(
        tmp_path,
        context["semantic_context"],
        operation_set["operation_set"],
        compiled_at=AT,
        skills_root=ROOT,
    )
    current_policy = _write(
        tmp_path / ".agent_goal/agent_authority.md", "# Authority 1\n"
    )
    current_binding = snapshot_file(
        tmp_path, str(current_policy.relative_to(tmp_path)), "policy"
    )
    update_current_policy(tmp_path, current_binding, expected_version=0)
    semantics = {
        "source_kind": "explicit_user_instruction",
        "holder_rank": "S0",
        "expires_at": EXPIRES_AT,
        "session_id": "session-minimum",
    }
    prepared = prepare_root_approval_plan(
        tmp_path,
        batch["operation_batch"],
        current_binding,
        semantics,
        prepared_at=AT,
        skills_root=ROOT,
    )
    _binding_value, plan = load_root_approval_plan(
        tmp_path, prepared["root_approval_plan"], skills_root=ROOT
    )
    projection = plan["approval_projection"]
    assert len(projection["grants"]) == 2
    assert len({grant["grant_id"] for grant in projection["grants"]}) == 2
    assert all(len(grant["subjects"]) == 1 for grant in projection["grants"])
    assert all(len(grant["operations"]) == 1 for grant in projection["grants"])
    assert all(
        grant["capabilities"] == ["task.scope.mutate"]
        for grant in projection["grants"]
    )
    assert len(projection["source_coverage"]["subjects"]) == 2
    decision_result = compile_root_decision_seed(
        tmp_path,
        prepared["root_approval_plan"],
        authorization_evidence=signed_root_authorization(
            tmp_path,
            prepared["root_approval_plan"],
            decided_at=DECIDED_AT,
            evidence_id="minimum-decision",
            skills_root=ROOT,
        ),
        skills_root=ROOT,
    )
    materialized = materialize_exact_echo_root_grant(
        tmp_path,
        prepared["root_approval_plan"],
        decision_result["decision_seed"],
        skills_root=ROOT,
    )
    source = load_source_approval(
        tmp_path / materialized["source_approval"]["ref"]
    )
    for field, forged_value, message in (
        ("max_uses", None, "max_uses must be positive"),
        (
            "subjects",
            projection["grants"][0]["subjects"]
            + projection["grants"][1]["subjects"],
            "exactly one subject",
        ),
        (
            "operations",
            projection["grants"][0]["operations"]
            + projection["grants"][1]["operations"],
            "exactly one operation",
        ),
    ):
        forged_source = json.loads(json.dumps(source))
        forged_source["grant_projections"][0][field] = forged_value
        with pytest.raises(SystemExit, match=message):
            validate_source_approval(forged_source)
    first_grant = read_object(
        tmp_path / materialized["grants"][0]["ref"], "first root grant"
    )
    other_projection = next(
        item
        for item in source["grant_projections"]
        if item["grant_id"] != first_grant["grant_id"]
    )
    for field, value in (
        ("subjects", other_projection["subjects"]),
        ("request_sha256", "f" * 64),
        ("task_id", "task-other"),
        ("session_id", "session-other"),
    ):
        forged = {**first_grant, field: value}
        with pytest.raises(SystemExit, match="exact per-request projection"):
            validate_for_grant(tmp_path, source, validate_grant(forged))

    later_policy = _write(
        tmp_path / ".agent_goal/agent_authority-later.md", "# Authority 2\n"
    )
    later_binding = snapshot_file(
        tmp_path, str(later_policy.relative_to(tmp_path)), "policy"
    )
    update_current_policy(tmp_path, later_binding, expected_version=1)
    with pytest.raises(SystemExit, match="exact current policy"):
        prepare_root_approval_plan(
            tmp_path,
            batch["operation_batch"],
            current_binding,
            semantics,
            prepared_at=AT,
            skills_root=ROOT,
        )


def test_source_schema_v2_remains_historical_and_v3_cannot_claim_verified() -> None:
    base = {
        "schema_version": 2,
        "artifact_kind": "authority_source_approval",
        "approval_id": "approval-1",
        "source_kind": "explicit_user_instruction",
        "source_rank": "S3",
        "decision_type": "grant_authority",
        "capabilities": ["authority.grant.issue"],
        "subjects": [
            {
                "kind": "task",
                "ref": "task.md",
                "digest": "a" * 64,
                "revision": "r1",
            }
        ],
        "operations": [
            {
                "skill_id": "task-doctor",
                "skill_version": "2.2.0",
                "operation_id": "mutate_task_scope",
                "operation_version": "1",
            }
        ],
        "risk_ceiling": "R1",
        "decision_classes": ["D2"],
        "cardinalities": ["single_use"],
        "max_uses": 1,
        "grant_ids": ["grant-1"],
        "request_digests": [],
        "lineage_ids": ["lineage-1"],
        "delegation_binding": None,
        "not_before": AT,
        "expires_at": EXPIRES_AT,
        "evidence_id": "historical-evidence",
        "integrity_status": "verified",
    }
    assert validate_source_approval(base)["integrity_status"] == "verified"
    invalid_v3 = {
        **{key: value for key, value in base.items() if key != "integrity_status"},
        "schema_version": 3,
        "decision_binding": {"ref": "decision.json", "sha256": "b" * 64},
        "decision_trust_class": "verified",
    }
    with pytest.raises(SystemExit, match="trust class"):
        validate_source_approval(invalid_v3)


def test_raw_root_transaction_api_rejects_mechanical_inputs_without_writes(
    tmp_path: Path,
) -> None:
    plan_binding, decision_binding, plan = _prepared_root_materialization(
        tmp_path
    )
    transaction_root = (
        tmp_path
        / ".task/authorization/root_grant_materializations"
        / plan["approval_projection"]["projection_id"]
    )
    before = _tree_image(tmp_path)

    with pytest.raises(SystemExit, match="transaction inputs are sealed"):
        root_grant_transaction.commit_root_grant_transaction(
            tmp_path,
            transaction_root,
            plan_binding,
            decision_binding,
            DECIDED_AT,
            {"capabilities": ["forged.authority"]},
            [{"grant_id": "forged-grant"}],
        )

    assert _tree_image(tmp_path) == before


def test_root_transaction_reopens_forged_binding_without_writes(
    tmp_path: Path,
) -> None:
    plan_binding, decision_binding, _plan = _prepared_root_materialization(
        tmp_path
    )
    forged_decision_binding = {
        **decision_binding,
        "sha256": "0" * 64,
    }
    before = _tree_image(tmp_path)

    with pytest.raises(SystemExit, match="digest changed"):
        root_grant_transaction.commit_root_grant_transaction(
            tmp_path,
            plan_binding,
            forged_decision_binding,
            skills_root=ROOT,
        )

    assert _tree_image(tmp_path) == before


def test_visibility_rejects_active_forged_capability_transaction(
    tmp_path: Path,
) -> None:
    plan_binding, decision_binding, _plan = _prepared_root_materialization(
        tmp_path
    )
    expected = root_grant_transaction._derive_root_grant_assets(  # noqa: SLF001
        tmp_path,
        plan_binding,
        decision_binding,
        skills_root=ROOT,
    )
    forged_source = json.loads(
        expected["source_payload"].decode("utf-8")
    )
    forged_grant = json.loads(
        expected["grant_assets"][0]["artifact_payload"].decode("utf-8")
    )
    forged_capability = "forged.authority"
    forged_source["capabilities"] = sorted(
        [*forged_source["capabilities"], forged_capability]
    )
    forged_source["grant_projections"][0]["capabilities"] = sorted(
        [
            *forged_source["grant_projections"][0]["capabilities"],
            forged_capability,
        ]
    )
    forged_grant["capabilities"] = sorted(
        [*forged_grant["capabilities"], forged_capability]
    )
    forged = root_grant_transaction._build_assets(  # noqa: SLF001
        tmp_path,
        expected["receipt_path"].parent,
        plan_binding,
        decision_binding,
        DECIDED_AT,
        forged_source,
        [forged_grant],
    )
    root_grant_transaction._apply(forged)  # noqa: SLF001
    state = read_object(
        forged["grant_assets"][0]["state_path"],
        "forged root grant state",
    )
    assert state["status"] == "active"

    with pytest.raises(SystemExit, match="signed-plan rendering"):
        load_grant(tmp_path, forged_grant["grant_id"])


def test_visibility_reopens_exact_source_and_signed_evidence(
    tmp_path: Path,
) -> None:
    plan_binding, decision_binding, plan = _prepared_root_materialization(
        tmp_path
    )
    materialize_exact_echo_root_grant(
        tmp_path,
        plan_binding,
        decision_binding,
        skills_root=ROOT,
    )
    grant_id = plan["approval_projection"]["grants"][0]["grant_id"]
    materialization_root = (
        tmp_path
        / ".task/authorization/root_grant_materializations"
        / plan["approval_projection"]["projection_id"]
    )
    source_path = materialization_root / "source_approval.json"
    source_path.write_text('{"forged":true}\n', encoding="utf-8")
    before_source_read = _tree_image(tmp_path)
    with pytest.raises(SystemExit, match="source approval drifted"):
        load_grant(tmp_path, grant_id)
    assert _tree_image(tmp_path) == before_source_read

    source_path.write_bytes(
        (
            tmp_path
            / read_object(
                materialization_root / "receipt.json",
                "root receipt",
            )["source_approval"]["ref"]
        ).read_bytes()
    )
    decision = read_object(
        tmp_path / decision_binding["ref"],
        "root decision seed",
    )
    evidence_path = tmp_path / decision["authorization_evidence"]["ref"]
    evidence_path.write_text('{"forged":true}\n', encoding="utf-8")
    before_evidence_read = _tree_image(tmp_path)
    with pytest.raises(SystemExit, match="digest changed"):
        load_grant(tmp_path, grant_id)
    assert _tree_image(tmp_path) == before_evidence_read


def test_visibility_bounds_root_receipt_reopen(
    tmp_path: Path,
) -> None:
    plan_binding, decision_binding, plan = _prepared_root_materialization(
        tmp_path
    )
    materialize_exact_echo_root_grant(
        tmp_path,
        plan_binding,
        decision_binding,
        skills_root=ROOT,
    )
    grant_id = plan["approval_projection"]["grants"][0]["grant_id"]
    receipt_path = (
        tmp_path
        / plan["approval_projection"]["grants"][0][
            "root_materialization_ref"
        ]
    )
    receipt_path.write_bytes(
        b"x" * (root_grant_transaction.MAX_ROOT_TRANSACTION_BYTES + 1)
    )

    with pytest.raises(SystemExit, match="byte safety limit"):
        load_grant(tmp_path, grant_id)


@pytest.mark.parametrize(
    ("crash_stage", "interrupted_status"),
    (("after_drafts", "draft"), ("after_grant_activation", "active")),
)
def test_root_materialization_recovers_exact_write_ahead_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_stage: str,
    interrupted_status: str,
) -> None:
    plan_binding, decision_binding, plan = _prepared_root_materialization(
        tmp_path
    )
    crashed = False

    def crash_once(stage: str, _path: Path) -> None:
        nonlocal crashed
        if stage == crash_stage and not crashed:
            crashed = True
            raise RuntimeError("simulated root materialization crash")

    monkeypatch.setattr(
        root_grant_transaction, "_materialization_hook", crash_once
    )
    with pytest.raises(RuntimeError, match="simulated"):
        materialize_exact_echo_root_grant(
            tmp_path,
            plan_binding,
            decision_binding,
            skills_root=ROOT,
        )
    materialization_root = (
        tmp_path
        / ".task/authorization/root_grant_materializations"
        / plan["approval_projection"]["projection_id"]
    )
    assert (materialization_root / "prepare.json").is_file()
    assert not (materialization_root / "receipt.json").exists()
    grant_id = plan["approval_projection"]["grants"][0]["grant_id"]
    interrupted = read_object(
        tmp_path / f".task/authorization/state/grants/{grant_id}.json",
        "interrupted root grant state",
    )
    assert interrupted["status"] == interrupted_status
    _grant_value, _grant_sha, effective_state = load_grant(
        tmp_path, grant_id
    )
    assert effective_state["status"] == "draft"
    replay = register_grant(
        tmp_path,
        read_object(
            tmp_path / f".task/authorization/grants/{grant_id}.json",
            "interrupted root grant",
        ),
    )
    assert replay["state"]["status"] == "draft"

    monkeypatch.setattr(
        root_grant_transaction,
        "_materialization_hook",
        lambda _stage, _path: None,
    )
    recovered = materialize_exact_echo_root_grant(
        tmp_path,
        plan_binding,
        decision_binding,
        skills_root=ROOT,
    )
    assert recovered["status"] == "recovered"
    assert (materialization_root / "receipt.json").is_file()
    active = read_object(
        tmp_path / f".task/authorization/state/grants/{grant_id}.json",
        "recovered root grant state",
    )
    assert active["status"] == "active"


def test_root_materialization_conflict_preflight_has_no_transaction_effect(
    tmp_path: Path,
) -> None:
    plan_binding, decision_binding, plan = _prepared_root_materialization(
        tmp_path
    )
    projection = plan["approval_projection"]
    grant_id = projection["grants"][0]["grant_id"]
    _write(
        tmp_path / f".task/authorization/grants/{grant_id}.json",
        '{"conflict":true}\n',
    )
    with pytest.raises(SystemExit, match="Conflicting root grant artifact"):
        materialize_exact_echo_root_grant(
            tmp_path,
            plan_binding,
            decision_binding,
            skills_root=ROOT,
        )
    transaction_root = (
        tmp_path
        / ".task/authorization/root_grant_materializations"
        / projection["projection_id"]
    )
    assert not (transaction_root / "prepare.json").exists()
    assert not (transaction_root / "source_approval.json").exists()


def test_cli_exposes_compiler_first_root_grant_commands() -> None:
    parser = authority_cli.build_parser()
    assert parser.parse_args(
        [
            "compile-root-decision-seed",
            "--approval-plan",
            "{}",
            "--authorization-evidence",
            "{}",
        ]
    ).command == "compile-root-decision-seed"
    assert parser.parse_args(
        [
            "compile-semantic-context",
            "--initialization",
            "{}",
            "--semantic",
            "{}",
        ]
    ).command == "compile-semantic-context"
    assert parser.parse_args(
        [
            "publish-operation-set",
            "--operations",
            "[]",
        ]
    ).command == "publish-operation-set"
    assert parser.parse_args(
        [
            "compile-operation-batch",
            "--at",
            AT,
            "--semantic-context",
            "{}",
            "--operation-set",
            "{}",
        ]
    ).command == "compile-operation-batch"
    assert parser.parse_args(
        [
            "materialize-plan-bound-root-grant",
            "--approval-plan",
            "{}",
            "--decision-seed",
            "{}",
        ]
    ).command == "materialize-plan-bound-root-grant"
