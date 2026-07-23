from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from orchestrate_task_cycle.selected_successor_authority_artifacts import (
    MAX_INDEX_BYTES,
    MAX_OUTCOME_BYTES,
    load_packet,
    load_projection,
)
from orchestrate_task_cycle.selected_successor_authority_context import (
    MAX_CONTEXT_BYTES,
)
from orchestrate_task_cycle.selected_successor_authority_validation import (
    validate_authority_packet,
    validate_authority_projection,
)
from orchestrate_task_cycle.selected_successor_cli import main as successor_cli
from orchestrate_task_cycle.selection_publication_store import _canonical_json
from selected_successor_authority_support import (
    AT,
    SKILLS_ROOT,
    _snapshot_historical_source,
    register_grant,
)
from test_selected_successor_authority_preparation import (
    _prepare_authority,
    _prepared,
)


def _binding(root: Path, path: Path) -> dict[str, str]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _tree_state(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def _rewrite_request_context(
    root: Path,
    binding: dict[str, str],
    mutation: Callable[[dict[str, Any]], None],
) -> dict[str, str]:
    source = root / binding["ref"]
    value = json.loads(source.read_text(encoding="utf-8"))
    body = {
        key: item
        for key, item in value.items()
        if key != "context_content_sha256"
    }
    mutation(body)
    value = {
        **body,
        "context_content_sha256": hashlib.sha256(_canonical_json(body)).hexdigest(),
    }
    path = (
        root
        / ".task/selection_publication/successor_authority_request_contexts/sha256"
        / f"{value['context_content_sha256']}.json"
    )
    path.write_bytes(_canonical_json(value))
    return _binding(root, path)


def _forge_outcome(
    root: Path,
    binding: dict[str, str],
    *,
    kind: str,
    mutation: Callable[[dict[str, Any]], None],
) -> dict[str, str]:
    source = root / binding["ref"]
    value = json.loads(source.read_text(encoding="utf-8"))
    field = (
        "packet_content_sha256"
        if kind == "packet"
        else "projection_content_sha256"
    )
    body = {key: item for key, item in value.items() if key != field}
    mutation(body)
    content_sha = hashlib.sha256(_canonical_json(body)).hexdigest()
    forged = {**body, field: content_sha}
    plural = "packets" if kind == "packet" else "projections"
    path = (
        root
        / f".task/selection_publication/successor_authority_{plural}/sha256"
        / f"{content_sha}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json(forged))
    return _binding(root, path)


def _write_owner_json(
    root: Path, path: Path, value: dict[str, Any]
) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return _binding(root, path)


def _register_unrelated_grant(
    root: Path, packet: dict[str, Any]
) -> dict[str, Any]:
    action = "settle_selected_successor_task_state"
    template_path = root / packet["grants"][action]["binding"]["ref"]
    template = json.loads(template_path.read_text(encoding="utf-8"))
    source_path = root / ".task/authorization/selected-successor-compiler-approval.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source.update(
        {
            "approval_id": "selected-successor-unrelated-approval",
            "grant_ids": ["selected-compiler-unrelated-grant"],
            "lineage_ids": ["selected-compiler-unrelated-lineage"],
            "evidence_id": "selected-successor-unrelated-user-message",
        }
    )
    unrelated_source = root / ".task/authorization/unrelated-approval.json"
    _write_owner_json(root, unrelated_source, source)
    source_binding = _snapshot_historical_source(root, unrelated_source)
    grant = {
        **template,
        "grant_id": "selected-compiler-unrelated-grant",
        "lineage_id": "selected-compiler-unrelated-lineage",
        "source_approval": source_binding,
        "idempotency_key": "selected-compiler-unrelated-grant-key",
    }
    return register_grant(root, grant)


def _forge_unrelated_owner_chain(
    root: Path, packet_binding: dict[str, str], packet: dict[str, Any]
) -> tuple[dict[str, str], dict[str, Any]]:
    from manage_agent_authority.canonical import object_sha256
    from manage_agent_authority.evaluator import effective_authority_fingerprint

    action = "apply_task_state_plan_pending"
    unrelated = _register_unrelated_grant(root, packet)
    operation = packet["operations"][0]
    compilation = json.loads(
        (root / operation["compilation"]["ref"]).read_text(encoding="utf-8")
    )
    grant = unrelated["grant"]
    selected = [
        {
            "grant_id": grant["grant_id"],
            "grant_sha256": unrelated["grant_sha256"],
            "state_version": 0,
            "policy_snapshot": grant["policy_snapshot"],
        }
    ]
    fingerprint = effective_authority_fingerprint(
        compilation["request"],
        compilation["evaluation_context"],
        compilation["operation_manifest"],
        selected,
        [],
    )
    decision_core = {
        "schema_version": 2,
        "artifact_kind": "authority_decision",
        "request": compilation["request"],
        "request_sha256": compilation["request_sha256"],
        "evaluation_context": compilation["evaluation_context"],
        "evaluation_context_sha256": object_sha256(
            compilation["evaluation_context"]
        ),
        "decision": "allowed",
        "reason_codes": [],
        "approval_projection": None,
        "selected_grants": selected,
        "lineage_grants": [],
        "operation_manifest": compilation["operation_manifest"],
        "effective_authority_fingerprint": fingerprint,
        "evaluated_at": packet["prepared_at"],
    }
    decision = {
        "decision_id": f"authd-{object_sha256(decision_core)[:24]}",
        **decision_core,
    }
    decision_path = (
        root
        / ".task/authorization/decisions"
        / f"{decision['decision_id']}.json"
    )
    decision_binding = _write_owner_json(root, decision_path, decision)

    proof = packet["authority_proofs"][action]
    reservation_path = root / proof["reservation"]["ref"]
    reservation = json.loads(reservation_path.read_text(encoding="utf-8"))
    grant_change = next(
        change
        for change in reservation["state_changes"]
        if "/state/grants/" in change["ref"]
    )
    _write_owner_json(root, root / grant_change["ref"], grant_change["before"])
    before = unrelated["state"]
    after = {
        **before,
        "reserved_uses": before["reserved_uses"] + 1,
        "version": before["version"] + 1,
        "last_event_id": reservation["reservation_id"],
    }
    unrelated_ref = (
        f".task/authorization/state/grants/{grant['grant_id']}.json"
    )
    _write_owner_json(root, root / unrelated_ref, after)
    state_change = next(
        change
        for change in reservation["state_changes"]
        if "/state/reservations/" in change["ref"]
    )
    reservation.update(
        {
            "decision": decision_binding,
            "effective_authority_fingerprint": fingerprint,
            "grant_uses": [
                {
                    "grant_id": grant["grant_id"],
                    "grant_sha256": unrelated["grant_sha256"],
                    "units": 1,
                    "state_version_before": 0,
                    "state_version_after": 1,
                }
            ],
            "state_changes": [
                {"ref": unrelated_ref, "before": before, "after": after},
                state_change,
            ],
        }
    )
    reservation_binding = _write_owner_json(root, reservation_path, reservation)
    reservation_state = root / state_change["ref"]
    verification_core = {
        "schema_version": 2,
        "artifact_kind": "authority_verification",
        "stage": "pre_commit",
        "reservation": reservation_binding,
        "reservation_state": {
            **_binding(root, reservation_state),
            "version": 0,
            "status": "reserved",
        },
        "grant_states": [
            {
                "grant_id": grant["grant_id"],
                "grant_sha256": unrelated["grant_sha256"],
                "state_version": 1,
                "status": "active",
                "remaining_uses": after["remaining_uses"],
                "reserved_uses": after["reserved_uses"],
            }
        ],
        "request_id": compilation["request"]["request_id"],
        "effective_authority_fingerprint": fingerprint,
        "verified_at": packet["prepared_at"],
    }
    verification = {
        "verification_id": f"authv-{object_sha256(verification_core)[:24]}",
        **verification_core,
    }
    verification_path = (
        root
        / ".task/authorization/verifications"
        / f"{verification['verification_id']}.json"
    )
    verification_binding = _write_owner_json(
        root, verification_path, verification
    )

    descriptor = {
        "status": "bound",
        "binding": {
            "ref": f".task/authorization/grants/{grant['grant_id']}.json",
            "sha256": unrelated["grant_sha256"],
        },
    }

    def mutate(body: dict[str, Any]) -> None:
        body["grants"][action] = descriptor
        body["operations"][0]["selected_grant"] = descriptor
        body["operations"][0]["decision"] = decision_binding
        body["authority_proofs"][action] = {
            "reservation": reservation_binding,
            "pre_commit_verification": verification_binding,
            "expected_version": 0,
        }

    forged_binding = _forge_outcome(
        root, packet_binding, kind="packet", mutation=mutate
    )
    return forged_binding, json.loads(
        (root / forged_binding["ref"]).read_text(encoding="utf-8")
    )


def test_self_sealed_actor_rank_mismatch_has_zero_lifecycle_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    inputs["request_context"] = _rewrite_request_context(
        tmp_path,
        inputs["request_context"],
        lambda body: body.__setitem__("actor_rank", "S1"),
    )
    before = _tree_state(tmp_path)

    with pytest.raises(ValueError, match="grant holder ranks differ from request actor_rank"):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _tree_state(tmp_path) == before
    assert not (tmp_path / ".task/authorization/operation_compilations").exists()


def test_cross_bundle_request_context_is_rejected_before_any_write(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    other_bundle = {
        "ref": prepared["bundle"]["ref"],
        "sha256": "f" * 64,
    }
    inputs["request_context"] = _rewrite_request_context(
        tmp_path,
        inputs["request_context"],
        lambda body: body.__setitem__("bundle", other_bundle),
    )
    before = _tree_state(tmp_path)

    with pytest.raises(ValueError, match="request context integrity failed"):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _tree_state(tmp_path) == before
    assert not (tmp_path / ".task/authorization/operation_compilations").exists()


def test_legacy_explicit_bundle_and_twelve_proof_values_remain_usable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    authority = _prepare_authority(tmp_path, prepared, inputs)
    _packet_binding, packet = load_packet(
        tmp_path, authority["authority_packet"]
    )
    proofs = packet["authority_proofs"]
    argv = [
        "--root",
        str(tmp_path),
        "execute",
        "--bundle-ref",
        prepared["bundle"]["ref"],
        "--bundle-sha256",
        prepared["bundle"]["sha256"],
        "--at",
        AT,
        "--skills-root",
        str(SKILLS_ROOT),
    ]
    prefixes = {
        "apply_task_state_plan_pending": "index",
        "publish_selected_successor_topology": "publication",
        "settle_selected_successor_task_state": "settlement",
    }
    proof_values = 0
    for action, prefix in prefixes.items():
        proof = proofs[action]
        for name, binding in (
            ("reservation", proof["reservation"]),
            ("pre-commit", proof["pre_commit_verification"]),
        ):
            argv.extend(
                (
                    f"--{prefix}-{name}-ref",
                    binding["ref"],
                    f"--{prefix}-{name}-sha256",
                    binding["sha256"],
                )
            )
            proof_values += 2

    assert proof_values == 12
    assert successor_cli(argv) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "complete"
    assert "--authority-packet-ref" not in argv


@pytest.mark.parametrize("kind", ("packet", "projection"))
@pytest.mark.parametrize("failure", ("malformed", "cross_bound"))
def test_compact_authority_outcomes_fail_closed_when_forged(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    kind: str,
    failure: str,
) -> None:
    prepared, _bundle, inputs = _prepared(
        tmp_path, capsys, grants=kind == "packet"
    )
    result = _prepare_authority(tmp_path, prepared, inputs)
    outcome = (
        result["authority_packet"]
        if kind == "packet"
        else result["approval_projection"]
    )

    def malformed_mutation(body: dict[str, Any]) -> None:
        body["unexpected"] = True

    def cross_bound_mutation(body: dict[str, Any]) -> None:
        body["bundle"] = {
            "ref": prepared["bundle"]["ref"],
            "sha256": "0" * 64,
        }

    if failure == "malformed":
        mutation = malformed_mutation
        expected = "integrity failed"
    else:
        mutation = cross_bound_mutation
        expected = "bundle binding has drifted"
    forged = _forge_outcome(
        tmp_path, outcome, kind=kind, mutation=mutation
    )
    before = _tree_state(tmp_path)
    validator = (
        validate_authority_packet
        if kind == "packet"
        else validate_authority_projection
    )

    with pytest.raises(ValueError, match=expected):
        validator(tmp_path, forged, skills_root=SKILLS_ROOT)

    assert _tree_state(tmp_path) == before


@pytest.mark.parametrize("surface", ("packet", "legacy_executor"))
def test_unrelated_real_grant_forged_chain_is_blocked_before_first_effect(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    surface: str,
) -> None:
    from orchestrate_task_cycle.selected_successor_execution import (
        execute_selected_successor_bundle,
    )

    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    authority = _prepare_authority(tmp_path, prepared, inputs)
    packet_binding, packet = load_packet(tmp_path, authority["authority_packet"])
    forged_binding, forged = _forge_unrelated_owner_chain(
        tmp_path, packet_binding, packet
    )
    before = _tree_state(tmp_path)

    with pytest.raises(SystemExit, match="failed decision-time coverage"):
        if surface == "packet":
            validate_authority_packet(
                tmp_path, forged_binding, skills_root=SKILLS_ROOT
            )
        else:
            execute_selected_successor_bundle(
                tmp_path,
                bundle_binding=forged["bundle"],
                authority_proofs=forged["authority_proofs"],
                settled_at=AT,
                skills_root=SKILLS_ROOT,
            )

    assert _tree_state(tmp_path) == before
    assert not (
        tmp_path / ".task/selection_publication/selected-successor-authority-gates"
    ).exists()


def test_compact_authority_contract_exposes_bounded_read_surfaces() -> None:
    assert {
        "request_context": MAX_CONTEXT_BYTES,
        "evaluation_context": MAX_CONTEXT_BYTES,
        "packet": MAX_OUTCOME_BYTES,
        "projection": MAX_OUTCOME_BYTES,
        "index": MAX_INDEX_BYTES,
    } == {
        "request_context": 64 * 1024,
        "evaluation_context": 64 * 1024,
        "packet": 256 * 1024,
        "projection": 256 * 1024,
        "index": 64 * 1024,
    }
    assert load_packet is not None and load_projection is not None


def test_projection_rejects_self_sealed_nonderived_reason_and_approval(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, grants=False)
    result = _prepare_authority(tmp_path, prepared, inputs)

    def mutate(body: dict[str, Any]) -> None:
        row = body["operations"][0]
        row["reason_codes"] = sorted(row["reason_codes"] + ["invented_reason"])

    forged = _forge_outcome(
        tmp_path,
        result["approval_projection"],
        kind="projection",
        mutation=mutate,
    )
    before = _tree_state(tmp_path)

    with pytest.raises(ValueError, match="projection is not canonically derived"):
        validate_authority_projection(tmp_path, forged, skills_root=SKILLS_ROOT)

    assert _tree_state(tmp_path) == before


def test_indexed_absent_projection_conflicts_when_covering_grants_appear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from selected_successor_authority_support import prepare_authority_inputs

    prepared, bundle, inputs = _prepared(tmp_path, capsys, grants=False)
    first = _prepare_authority(tmp_path, prepared, inputs)
    assert first["status"] == "approval_required"
    prepare_authority_inputs(
        tmp_path,
        bundle,
        prepared["bundle"],
        register_existing_grants=True,
    )
    before = _tree_state(tmp_path)

    with pytest.raises(ValueError, match="conflicts with the exact input"):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _tree_state(tmp_path) == before


def test_packet_mode_rejects_explicit_legacy_expected_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    authority = _prepare_authority(tmp_path, prepared, inputs)
    before = _tree_state(tmp_path)

    code = successor_cli(
        [
            "--root",
            str(tmp_path),
            "execute",
            "--authority-packet-ref",
            authority["authority_packet"]["ref"],
            "--authority-packet-sha256",
            authority["authority_packet"]["sha256"],
            "--index-expected-version",
            "0",
            "--at",
            AT,
            "--skills-root",
            str(SKILLS_ROOT),
        ]
    )
    blocked = json.loads(capsys.readouterr().out)

    assert code == 2
    assert blocked["status"] == "blocked"
    assert blocked["mutation_performed"] is None
    assert blocked["mutation_status"] == "unknown_after_failure"
    assert _tree_state(tmp_path) == before


def test_authority_automation_modules_stay_within_architecture_bounds() -> None:
    repo = Path(__file__).resolve().parents[1]
    paths = sorted(
        (repo / "orchestrate-task-cycle/scripts/orchestrate_task_cycle").glob(
            "selected_successor_authority*.py"
        )
    )
    paths.extend(
        repo / relative
        for relative in (
            "orchestrate-task-cycle/scripts/orchestrate_task_cycle/selected_successor_cli.py",
            "orchestrate-task-cycle/scripts/orchestrate_task_cycle/selection_publication_store.py",
            "manage-agent-authority/scripts/manage_agent_authority/operation_compiler.py",
            "manage-agent-authority/scripts/manage_agent_authority/operation_request.py",
            "manage-agent-authority/scripts/manage_agent_authority/decision_publication.py",
            "manage-agent-authority/scripts/manage_agent_authority/historical_proof_chain.py",
            "manage-agent-authority/scripts/manage_agent_authority/verification_publication.py",
            "manage-agent-authority/scripts/manage_agent_authority/authority_cli.py",
        )
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) <= 500, path
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 <= 140, (
                    path,
                    node.name,
                )
