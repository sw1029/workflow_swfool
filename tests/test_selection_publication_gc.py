from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path

import pytest

import orchestrate_task_cycle.selection_publication_gc as gc
import orchestrate_task_cycle.selection_publication_gc_apply as gc_apply
import orchestrate_task_cycle.selection_publication_gc_hooks as gc_hooks
import orchestrate_task_cycle.selection_publication_gc_restore as gc_restore
import orchestrate_task_cycle.selection_publication_gc_scan as gc_scan
import orchestrate_task_cycle.selection_publication_cli as publication_cli
import manage_agent_authority.effect_lease as effect_lease
from manage_agent_authority.artifact_store import (
    snapshot_file,
    update_current_policy,
)
from manage_agent_authority.canonical import (
    sha256_file,
    write_immutable_json,
)
from manage_agent_authority.evaluator import evaluate
from manage_agent_authority.lifecycle import reserve
from manage_agent_authority.operation_batch import (
    load_operation_batch,
    publish_operation_batch,
    publish_operation_set,
)
from manage_agent_authority.root_grant import (
    materialize_exact_echo_root_grant,
    prepare_root_approval_plan,
)
from manage_agent_authority.root_decision_seed import (
    compile_root_decision_seed,
)
from manage_agent_authority.settlement import settle_owner_result
from manage_agent_authority.semantic_context import (
    publish_shared_semantic_context,
)
from manage_agent_authority.verification_publication import (
    verify_and_publish_precommit,
    verify_and_publish_predispatch,
)
from orchestrate_task_cycle.authority_packet import build_authority_packet
from orchestrate_task_cycle.selection_publication_gc import (
    _archive_bytes,
    _archive_path,
    _load_plan,
    apply_gc,
    plan_gc,
    restore_gc,
)
from orchestrate_task_cycle.selection_publication_state import write_empty_state
from orchestrate_task_cycle.selection_publication_reference_barrier import (
    REFERENCE_BARRIER_REF,
    adopt_reference_barrier,
)
from orchestrate_task_cycle.selection_publication_store import (
    _canonical_json,
    _sha256_bytes,
)
from root_authorization_test_support import (
    install_test_trust_anchor,
    signed_root_authorization,
)

SKILLS_ROOT = Path(__file__).resolve().parents[1]
AT = "2026-07-23T10:00:00+09:00"
LATER = "2026-07-23T10:05:00+09:00"
EXPIRY = "2026-07-24T10:00:00+09:00"


@pytest.fixture(autouse=True)
def _host_authorization_trust(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_test_trust_anchor(monkeypatch, tmp_path)


def _initialize_gc(root: Path) -> None:
    write_empty_state(root)
    adopted = adopt_reference_barrier(root)
    assert adopted["status"] == "adopted"


def _write_blob(root: Path, payload: bytes) -> tuple[Path, str]:
    digest = hashlib.sha256(payload).hexdigest()
    path = root / ".task/selection_publication/blobs/sha256" / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path, digest


def _real_authority(
    root: Path,
    subject: dict[str, str],
    *,
    operation: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    policy = root / ".agent_goal/agent_authority.md"
    goal = root / ".agent_goal/goal_architecture.md"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("# Authority\n", encoding="utf-8")
    goal.write_text("# Goal\n", encoding="utf-8")
    policy_binding = snapshot_file(
        root, policy.relative_to(root).as_posix(), "policy"
    )
    if not (
        root / ".task/authorization/state/current_policy.json"
    ).exists():
        update_current_policy(root, policy_binding, expected_version=0)
    capability = (
        "cycle.selection_publication.retention.apply"
        if operation == "apply_selection_publication_retention"
        else "cycle.selection_publication.retention.restore"
    )
    initialization = root / ".task/cycle/cycle-gc/initialization.json"
    initialization.parent.mkdir(parents=True, exist_ok=True)
    initialization.write_text(
        json.dumps(
            {
                "format_version": 1,
                "cycle_id": "cycle-gc",
                "task_id": "task-gc",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    semantic = {
        "actor_rank": "S0",
        "request_context": {
            "external_input_status": "not_required",
            "goal_truth_status": "aligned",
            "risk_acceptance_status": "not_required",
            "design_selection_status": "not_required",
            "external_input_evidence_ref": None,
            "risk_acceptance_evidence_ref": None,
            "design_selection_evidence_ref": None,
        },
        "session_ceiling": {
            "capabilities": [capability],
            "risk_ceiling": "R3",
            "mutation_classes": ["local_mutation"],
            "evidence_id": f"{operation}-session",
        },
        "goal_autonomy_envelope": {
            "envelope_id": f"{operation}-envelope",
            "capabilities": [capability],
            "risk_ceiling": "R3",
            "decision_classes": ["D3"],
            "subjects": [subject["digest"]],
            "operations": [
                "orchestrate-task-cycle:2.0.0:" + operation + ":1"
            ],
            "source_ref": goal.relative_to(root).as_posix(),
        },
    }
    context_result = publish_shared_semantic_context(
        root,
        {
            "ref": initialization.relative_to(root).as_posix(),
            "sha256": sha256_file(initialization),
        },
        semantic,
    )
    operation_set = publish_operation_set(
        root,
        [
            {
                "skill_id": "orchestrate-task-cycle",
                "operation_id": operation,
                "subject": {
                    "ref": subject["ref"],
                    "revision": subject["revision"],
                },
                "scope": {"task_id": "task-gc", "pack_id": None},
            }
        ],
    )
    batch_result = publish_operation_batch(
        root,
        context_result["semantic_context"],
        operation_set["operation_set"],
        compiled_at=AT,
        skills_root=SKILLS_ROOT,
    )
    _binding, _batch, compilations = load_operation_batch(
        root, batch_result["operation_batch"], skills_root=SKILLS_ROOT
    )
    request = compilations[0]["request"]
    context = compilations[0]["evaluation_context"]
    root_plan = prepare_root_approval_plan(
        root,
        batch_result["operation_batch"],
        policy_binding,
        {
            "source_kind": "explicit_user_instruction",
            "holder_rank": "S0",
            "expires_at": EXPIRY,
            "session_id": None,
        },
        prepared_at=AT,
        skills_root=SKILLS_ROOT,
    )
    approval = compile_root_decision_seed(
        root,
        root_plan["root_approval_plan"],
        authorization_evidence=signed_root_authorization(
            root,
            root_plan["root_approval_plan"],
            decided_at=LATER,
            evidence_id=f"{operation}-explicit-user-decision",
            skills_root=SKILLS_ROOT,
        ),
        skills_root=SKILLS_ROOT,
    )
    materialize_exact_echo_root_grant(
        root,
        root_plan["root_approval_plan"],
        approval["decision_seed"],
        skills_root=SKILLS_ROOT,
    )
    decision = evaluate(
        root, request, context, evaluated_at=LATER, skills_root=SKILLS_ROOT
    )
    assert decision["decision"] == "allowed"
    decision_path = (
        root
        / ".task/authorization/decisions"
        / f"{decision['decision_id']}.json"
    )
    decision_sha = write_immutable_json(
        decision_path, decision, "GC authority decision"
    )
    reserved = reserve(
        root,
        decision_path.relative_to(root).as_posix(),
        decision_sha,
        reserved_at=LATER,
        idempotency_key=f"{operation}-reserve-key",
        skills_root=SKILLS_ROOT,
    )
    predispatch = verify_and_publish_predispatch(
        root,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        verified_at=LATER,
        expected_version=0,
        skills_root=SKILLS_ROOT,
    )
    precommit = verify_and_publish_precommit(
        root,
        reserved["reservation_ref"],
        reserved["reservation_sha256"],
        verified_at=LATER,
        expected_version=0,
        skills_root=SKILLS_ROOT,
    )
    packet = build_authority_packet(
        root,
        {
            "ref": decision_path.relative_to(root).as_posix(),
            "sha256": decision_sha,
        },
        reservation_binding={
            "ref": reserved["reservation_ref"],
            "sha256": reserved["reservation_sha256"],
        },
        verification_binding={
            "ref": predispatch["verification_ref"],
            "sha256": predispatch["verification_sha256"],
        },
    )
    packet_path = (
        root / f".task/authorization/gc-authority-packet-{operation}.json"
    )
    packet_sha = write_immutable_json(
        packet_path, packet, "GC orchestrator authority packet"
    )
    return (
        {
            "ref": packet_path.relative_to(root).as_posix(),
            "sha256": packet_sha,
        },
        {
            "ref": precommit["verification_ref"],
            "sha256": precommit["verification_sha256"],
        },
        {
            "ref": predispatch["verification_ref"],
            "sha256": predispatch["verification_sha256"],
        },
    )


@pytest.fixture
def authority(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, str], dict[str, str]]:
    packet = {"ref": ".task/authorization/packet.json", "sha256": "1" * 64}
    precommit = {
        "ref": ".task/authorization/precommit.json",
        "sha256": "2" * 64,
    }

    def validate(
        _root: Path,
        *,
        operation: str,
        subject: dict[str, str],
        authority_packet: object,
        pre_commit_verification: object,
        require_current: bool = True,
    ) -> dict[str, dict[str, str]]:
        assert operation in {
            "apply_selection_publication_retention",
            "restore_selection_publication_retention",
        }
        assert subject["revision"].startswith("spgc-")
        assert authority_packet == packet
        assert pre_commit_verification == precommit
        assert isinstance(require_current, bool)
        return {
            "authority_packet": packet,
            "pre_commit_verification": precommit,
            "reservation": {
                "ref": ".task/authorization/reservation.json",
                "sha256": "3" * 64,
            },
            "reservation_state_version": 0,
        }

    @contextlib.contextmanager
    def acquire(
        _root: Path,
        **_kwargs: object,
    ) -> object:
        yield {
            "ref": ".task/authorization/effect-lease.json",
            "sha256": "4" * 64,
        }

    monkeypatch.setattr(gc_apply, "validate_effect_authority", validate)
    monkeypatch.setattr(gc_restore, "validate_effect_authority", validate)
    monkeypatch.setattr(effect_lease, "acquire_effect_lease", acquire)
    monkeypatch.setattr(effect_lease, "validate_effect_lease", lambda *_a, **_k: {})
    return packet, precommit


def test_gc_archives_only_unreferenced_cas_and_restores_exact_bytes(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
) -> None:
    _initialize_gc(tmp_path)
    retained, retained_sha = _write_blob(tmp_path, b"retained\n")
    orphan, orphan_sha = _write_blob(tmp_path, b"orphan\n")
    reference = tmp_path / ".task/cycle/reference.json"
    reference.parent.mkdir(parents=True)
    reference.write_text(
        json.dumps({"ref": retained.relative_to(tmp_path).as_posix()}) + "\n",
        encoding="utf-8",
    )

    planned = plan_gc(tmp_path)
    plan = json.loads((tmp_path / planned["plan"]["ref"]).read_text())

    assert planned["status"] == "planned"
    assert planned["candidate_count"] == 1
    assert plan["candidates"] == [
        {
            "reason": "unreferenced_cas",
            "ref": orphan.relative_to(tmp_path).as_posix(),
            "sha256": orphan_sha,
            "size_bytes": len(b"orphan\n"),
        }
    ]

    packet, precommit = authority
    applied = apply_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )
    assert applied["removed_count"] == 1
    assert not orphan.exists()
    assert retained.read_bytes() == b"retained\n"
    assert hashlib.sha256(retained.read_bytes()).hexdigest() == retained_sha
    assert (tmp_path / applied["archive"]["ref"]).is_file()

    restored = restore_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )
    assert restored["status"] == "restored"
    assert orphan.read_bytes() == b"orphan\n"
    assert restore_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )["idempotent_replay"] is True


def test_gc_apply_blocks_if_candidate_becomes_referenced(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
) -> None:
    _initialize_gc(tmp_path)
    orphan, _digest = _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)
    late = tmp_path / ".task/late-reference.json"
    late.write_text(
        json.dumps({"ref": orphan.relative_to(tmp_path).as_posix()}) + "\n",
        encoding="utf-8",
    )

    packet, precommit = authority
    with pytest.raises(ValueError, match="became referenced"):
        apply_gc(
            tmp_path,
            planned["plan_id"],
            authority_packet=packet,
            pre_commit_verification=precommit,
        )

    assert orphan.is_file()
    assert not (
        tmp_path
        / ".task/selection_publication/gc/archives"
        / f"{planned['plan_id']}.tar.gz"
    ).exists()


def test_gc_requires_explicit_storage_v4_migration(tmp_path: Path) -> None:
    _write_blob(tmp_path, b"legacy\n")

    with pytest.raises(ValueError, match="storage v4"):
        plan_gc(tmp_path)


def test_gc_apply_api_fails_closed_without_authority(tmp_path: Path) -> None:
    _initialize_gc(tmp_path)
    candidate, _ = _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)

    with pytest.raises(ValueError, match="authority packet"):
        apply_gc(tmp_path, planned["plan_id"])

    assert candidate.read_bytes() == b"candidate\n"


def test_gc_apply_fails_closed_without_compiler_adopted_reference_barrier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_empty_state(tmp_path)
    candidate, _ = _write_blob(tmp_path, b"candidate\n")

    def unexpected_cas_scan(_root: Path) -> list[dict[str, object]]:
        raise AssertionError("CAS scan must not run before barrier validation")

    monkeypatch.setattr(gc_scan, "_cas_files", unexpected_cas_scan)
    with pytest.raises(ValueError, match="cannot prove workspace-wide"):
        plan_gc(tmp_path)

    assert candidate.read_bytes() == b"candidate\n"
    plans = tmp_path / ".task/selection_publication/gc/plans"
    assert not plans.exists()


def test_reference_barrier_adoption_is_compiler_owned_and_idempotent(
    tmp_path: Path,
) -> None:
    write_empty_state(tmp_path)
    first = adopt_reference_barrier(tmp_path)
    second = adopt_reference_barrier(tmp_path)

    assert first["mutation_performed"] is True
    assert first["model_authored_mechanical_bytes"] == 0
    assert second["idempotent_replay"] is True
    assert second["reference_barrier"] == first["reference_barrier"]
    assert (
        first["coverage"]
        == "registered_selection_publication_producers_only"
    )
    assert first["external_writer_coverage"] == "not_claimed"
    assert first["producer_inventory"]["producers"]
    assert (tmp_path / REFERENCE_BARRIER_REF).is_file()


@pytest.mark.parametrize("drift", ("storage_state", "producer_inventory"))
def test_gc_rejects_forged_reference_barrier_bindings(
    tmp_path: Path, drift: str
) -> None:
    _initialize_gc(tmp_path)
    candidate, _ = _write_blob(tmp_path, b"candidate\n")
    path = tmp_path / REFERENCE_BARRIER_REF
    policy = json.loads(path.read_text(encoding="utf-8"))
    if drift == "storage_state":
        policy["storage_state"]["sha256"] = "0" * 64
        message = "storage-state binding is stale"
    else:
        inventory = policy["producer_inventory"]
        inventory["producers"][0]["source_sha256"] = "0" * 64
        body = {
            key: value
            for key, value in inventory.items()
            if key != "inventory_sha256"
        }
        inventory["inventory_sha256"] = _sha256_bytes(
            _canonical_json(body)
        )
        message = "producer inventory has drifted"
    path.write_bytes(_canonical_json(policy))

    with pytest.raises(ValueError, match=message):
        plan_gc(tmp_path)

    assert candidate.read_bytes() == b"candidate\n"


def test_reference_barrier_adoption_is_exposed_by_production_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_empty_state(tmp_path)

    assert publication_cli.main(
        ["--root", str(tmp_path), "adopt-reference-barrier"]
    ) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "adopted"
    assert result["model_authored_mechanical_bytes"] == 0
    assert result["reference_barrier"]["ref"] == REFERENCE_BARRIER_REF
    assert (tmp_path / REFERENCE_BARRIER_REF).is_file()


def test_reference_barrier_preflight_failure_leaves_no_lock_residue(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="storage v4"):
        adopt_reference_barrier(tmp_path)

    assert not (
        tmp_path
        / ".task/selection_publication/.reference-barrier.lock"
    ).exists()
    assert not (tmp_path / REFERENCE_BARRIER_REF).exists()


def test_gc_apply_recovers_after_archive_and_partial_deletion(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
) -> None:
    _initialize_gc(tmp_path)
    first, _first_sha = _write_blob(tmp_path, b"first orphan\n")
    second, _second_sha = _write_blob(tmp_path, b"second orphan\n")
    planned = plan_gc(tmp_path)
    plan = json.loads((tmp_path / planned["plan"]["ref"]).read_text())
    archive = _archive_path(tmp_path, planned["plan_id"])
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(_archive_bytes(plan, tmp_path))
    first.unlink()

    packet, precommit = authority
    applied = apply_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )

    assert applied["status"] == "applied"
    assert not first.exists()
    assert not second.exists()
    assert restore_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )["status"] == "restored"
    assert first.read_bytes() == b"first orphan\n"
    assert second.read_bytes() == b"second orphan\n"


def test_gc_plan_loader_rejects_lexical_cas_traversal(tmp_path: Path) -> None:
    _initialize_gc(tmp_path)
    _write_blob(tmp_path, b"orphan\n")
    planned = plan_gc(tmp_path)
    plan = json.loads((tmp_path / planned["plan"]["ref"]).read_text())
    state = tmp_path / ".task/selection_publication/state.json"
    plan["candidates"][0] = {
        "reason": "unreferenced_cas",
        "ref": ".task/selection_publication/blobs/sha256/../../state.json",
        "sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
        "size_bytes": state.stat().st_size,
    }
    plan["scan_metrics"]["candidate_bytes"] = state.stat().st_size
    body = {
        key: value
        for key, value in plan.items()
        if key not in {"plan_id", "plan_content_sha256"}
    }
    fingerprint = _sha256_bytes(_canonical_json(body))
    plan_id = f"spgc-{fingerprint}"
    plan["plan_id"] = plan_id
    plan["plan_content_sha256"] = fingerprint
    path = (
        tmp_path
        / ".task/selection_publication/gc/plans"
        / f"{plan_id}.json"
    )
    path.write_bytes(_canonical_json(plan))

    with pytest.raises(ValueError, match="exact CAS path"):
        _load_plan(tmp_path, plan_id)


def test_gc_retains_refs_under_docs_var_and_with_json_escaped_slashes(
    tmp_path: Path,
) -> None:
    _initialize_gc(tmp_path)
    docs_blob, _ = _write_blob(tmp_path, b"docs-retained\n")
    var_blob, _ = _write_blob(tmp_path, b"var-retained\n")
    escaped_blob, _ = _write_blob(tmp_path, b"escaped-retained\n")
    orphan, orphan_sha = _write_blob(tmp_path, b"orphan\n")
    docs = tmp_path / "docs/reference.txt"
    docs.parent.mkdir(parents=True)
    docs.write_text(docs_blob.relative_to(tmp_path).as_posix(), encoding="utf-8")
    var = tmp_path / "var/reference.jsonl"
    var.parent.mkdir(parents=True)
    var.write_text(
        json.dumps({"nested": [{"ref": var_blob.relative_to(tmp_path).as_posix()}]})
        + "\n",
        encoding="utf-8",
    )
    escaped = tmp_path / "evidence/escaped.json"
    escaped.parent.mkdir(parents=True)
    escaped.write_text(
        '{"nested":{"ref":"'
        + escaped_blob.relative_to(tmp_path).as_posix().replace("/", "\\/")
        + '"}}\n',
        encoding="utf-8",
    )

    planned = plan_gc(tmp_path)
    plan = json.loads((tmp_path / planned["plan"]["ref"]).read_text())

    assert plan["candidates"] == [
        {
            "reason": "unreferenced_cas",
            "ref": orphan.relative_to(tmp_path).as_posix(),
            "sha256": orphan_sha,
            "size_bytes": len(b"orphan\n"),
        }
    ]


def test_gc_apply_fails_closed_on_candidate_ancestor_symlink_swap(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_gc(tmp_path)
    candidate, digest = _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)
    blobs = tmp_path / ".task/selection_publication/blobs"
    original = tmp_path / ".task/selection_publication/blobs-original"
    external = tmp_path / "outside"
    external_sha = external / "sha256"
    external_sha.mkdir(parents=True)
    (external_sha / digest).write_bytes(b"external-must-survive\n")

    def swap(stage: str, _path: Path) -> None:
        if stage == "before_apply_effect":
            blobs.rename(original)
            blobs.symlink_to(external, target_is_directory=True)

    monkeypatch.setattr(gc_hooks, "race_hook", swap)
    packet, precommit = authority
    with pytest.raises(ValueError, match="ancestor"):
        apply_gc(
            tmp_path,
            planned["plan_id"],
            authority_packet=packet,
            pre_commit_verification=precommit,
        )

    assert (external_sha / digest).read_bytes() == b"external-must-survive\n"
    assert (original / "sha256" / digest).read_bytes() == b"candidate\n"
    assert candidate.is_symlink() is False


def test_gc_apply_binds_archived_inode_and_bytes_to_unlink(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_gc(tmp_path)
    candidate, _digest = _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)
    displaced = candidate.with_name(candidate.name + ".displaced")

    def replace_leaf(stage: str, _path: Path) -> None:
        if stage == "before_apply_effect":
            candidate.rename(displaced)
            candidate.write_bytes(b"candidate\n")

    monkeypatch.setattr(gc_hooks, "race_hook", replace_leaf)
    packet, precommit = authority
    with pytest.raises(ValueError, match="changed after acquisition"):
        apply_gc(
            tmp_path,
            planned["plan_id"],
            authority_packet=packet,
            pre_commit_verification=precommit,
        )

    assert candidate.read_bytes() == b"candidate\n"
    assert displaced.read_bytes() == b"candidate\n"
    assert not (
        tmp_path
        / ".task/selection_publication/gc/receipts"
        / f"{planned['plan_id']}.json"
    ).exists()


def test_gc_apply_final_absence_check_precedes_receipt(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_gc(tmp_path)
    candidate, _digest = _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)

    def recreate(stage: str, _path: Path) -> None:
        if stage == "before_apply_receipt":
            candidate.write_bytes(b"candidate\n")

    monkeypatch.setattr(gc_hooks, "race_hook", recreate)
    packet, precommit = authority
    with pytest.raises(ValueError, match="found restored file"):
        apply_gc(
            tmp_path,
            planned["plan_id"],
            authority_packet=packet,
            pre_commit_verification=precommit,
        )

    assert candidate.is_file()
    assert not (
        tmp_path
        / ".task/selection_publication/gc/receipts"
        / f"{planned['plan_id']}.json"
    ).exists()


def test_gc_restore_fails_closed_on_candidate_ancestor_symlink_swap(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_gc(tmp_path)
    _candidate, digest = _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)
    packet, precommit = authority
    apply_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )
    blobs = tmp_path / ".task/selection_publication/blobs"
    original = tmp_path / ".task/selection_publication/blobs-original"
    external = tmp_path / "outside"
    (external / "sha256").mkdir(parents=True)

    def swap(stage: str, _path: Path) -> None:
        if stage == "before_restore_effect":
            blobs.rename(original)
            blobs.symlink_to(external, target_is_directory=True)

    monkeypatch.setattr(gc_hooks, "race_hook", swap)
    with pytest.raises(ValueError, match="ancestor"):
        restore_gc(
            tmp_path,
            planned["plan_id"],
            authority_packet=packet,
            pre_commit_verification=precommit,
        )

    assert not (external / "sha256" / digest).exists()
    assert not (original / "sha256" / digest).exists()


def test_gc_restore_exact_final_check_precedes_receipt(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_gc(tmp_path)
    candidate, _digest = _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)
    packet, precommit = authority
    apply_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )

    def mutate(stage: str, _path: Path) -> None:
        if stage == "before_restore_receipt":
            candidate.write_bytes(b"drifted\n")

    monkeypatch.setattr(gc_hooks, "race_hook", mutate)
    with pytest.raises(ValueError, match="restored candidate drifted"):
        restore_gc(
            tmp_path,
            planned["plan_id"],
            authority_packet=packet,
            pre_commit_verification=precommit,
        )

    assert not (
        tmp_path
        / ".task/selection_publication/gc/restores"
        / f"{planned['plan_id']}.json"
    ).exists()


def test_gc_revalidates_authority_lease_at_first_effect(
    tmp_path: Path,
    authority: tuple[dict[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_gc(tmp_path)
    candidate, _digest = _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)

    @contextlib.contextmanager
    def stale(*_args: object, **_kwargs: object) -> object:
        raise SystemExit("stale reservation")
        yield {}

    monkeypatch.setattr(effect_lease, "acquire_effect_lease", stale)
    packet, precommit = authority
    with pytest.raises(ValueError, match="current authority effect lease"):
        apply_gc(
            tmp_path,
            planned["plan_id"],
            authority_packet=packet,
            pre_commit_verification=precommit,
        )

    assert candidate.read_bytes() == b"candidate\n"
    assert not (
        tmp_path
        / ".task/selection_publication/gc/archives"
        / f"{planned['plan_id']}.tar.gz"
    ).exists()


def test_gc_effect_authority_reopens_exact_current_chain_and_precommit(
    tmp_path: Path,
) -> None:
    _initialize_gc(tmp_path)
    _write_blob(tmp_path, b"candidate\n")
    planned = plan_gc(tmp_path)
    plan, plan_path, plan_sha = _load_plan(tmp_path, planned["plan_id"])
    subject = gc._expected_subject(
        tmp_path,
        operation="apply_selection_publication_retention",
        plan_id=planned["plan_id"],
        plan_path=plan_path,
        plan_sha=plan_sha,
    )
    packet, precommit, predispatch = _real_authority(
        tmp_path,
        subject,
        operation="apply_selection_publication_retention",
    )

    validated = gc._validate_effect_authority(
        tmp_path,
        operation="apply_selection_publication_retention",
        subject=subject,
        authority_packet=packet,
        pre_commit_verification=precommit,
    )

    assert validated["authority_packet"] == packet
    assert validated["pre_commit_verification"] == precommit
    with pytest.raises(ValueError, match="operation or subject"):
        gc._validate_effect_authority(
            tmp_path,
            operation="apply_selection_publication_retention",
            subject={**subject, "revision": "spgc-" + "0" * 64},
            authority_packet=packet,
            pre_commit_verification=precommit,
        )
    with pytest.raises(ValueError, match="pre-commit"):
        gc._validate_effect_authority(
            tmp_path,
            operation="apply_selection_publication_retention",
            subject=subject,
            authority_packet=packet,
            pre_commit_verification=predispatch,
        )
    applied = apply_gc(
        tmp_path,
        plan["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )
    assert applied["authority_settlement_required"] is True
    assert applied["owner_result"]["ref"].endswith(f"{plan['plan_id']}.json")
    packet_value = json.loads((tmp_path / packet["ref"]).read_text())
    reservation = {
        "ref": packet_value["reservation_binding"]["artifact_ref"],
        "sha256": packet_value["reservation_binding"]["artifact_sha256"],
    }
    settlement = settle_owner_result(
        tmp_path,
        reservation["ref"],
        reservation["sha256"],
        applied["owner_result"],
        precommit,
        settled_at="2026-07-23T10:10:00+09:00",
        expected_version=0,
        idempotency_key="gc-apply-settlement-key",
        skills_root=SKILLS_ROOT,
    )
    assert settlement["status"] == "consumed"

    replay = apply_gc(
        tmp_path,
        plan["plan_id"],
        authority_packet=packet,
        pre_commit_verification=precommit,
    )

    assert replay["idempotent_replay"] is True
    assert replay["mutation_performed"] is False


def test_gc_restore_owner_result_settles_through_fixed_registry(
    tmp_path: Path,
) -> None:
    _initialize_gc(tmp_path)
    candidate, _digest = _write_blob(tmp_path, b"settled restore\n")
    planned = plan_gc(tmp_path)
    plan, plan_path, plan_sha = _load_plan(tmp_path, planned["plan_id"])
    apply_subject = gc._expected_subject(
        tmp_path,
        operation="apply_selection_publication_retention",
        plan_id=planned["plan_id"],
        plan_path=plan_path,
        plan_sha=plan_sha,
    )
    apply_packet, apply_precommit, _ = _real_authority(
        tmp_path,
        apply_subject,
        operation="apply_selection_publication_retention",
    )
    applied = apply_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=apply_packet,
        pre_commit_verification=apply_precommit,
    )
    apply_packet_value = json.loads(
        (tmp_path / apply_packet["ref"]).read_text()
    )
    apply_reservation = apply_packet_value["reservation_binding"]
    assert settle_owner_result(
        tmp_path,
        apply_reservation["artifact_ref"],
        apply_reservation["artifact_sha256"],
        applied["owner_result"],
        apply_precommit,
        settled_at="2026-07-23T10:10:00+09:00",
        expected_version=0,
        idempotency_key="gc-apply-before-restore",
        skills_root=SKILLS_ROOT,
    )["status"] == "consumed"
    assert not candidate.exists()

    restore_subject = gc._expected_subject(
        tmp_path,
        operation="restore_selection_publication_retention",
        plan_id=planned["plan_id"],
        plan_path=plan_path,
        plan_sha=plan_sha,
    )
    restore_packet, restore_precommit, _ = _real_authority(
        tmp_path,
        restore_subject,
        operation="restore_selection_publication_retention",
    )
    restored = restore_gc(
        tmp_path,
        planned["plan_id"],
        authority_packet=restore_packet,
        pre_commit_verification=restore_precommit,
    )
    restore_packet_value = json.loads(
        (tmp_path / restore_packet["ref"]).read_text()
    )
    restore_reservation = restore_packet_value["reservation_binding"]
    settlement = settle_owner_result(
        tmp_path,
        restore_reservation["artifact_ref"],
        restore_reservation["artifact_sha256"],
        restored["owner_result"],
        restore_precommit,
        settled_at="2026-07-23T10:15:00+09:00",
        expected_version=0,
        idempotency_key="gc-restore-settlement",
        skills_root=SKILLS_ROOT,
    )
    assert settlement["status"] == "consumed"
    assert candidate.read_bytes() == b"settled restore\n"
