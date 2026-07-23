from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from manage_agent_authority.artifact_store import (
    snapshot_file,
    update_current_policy,
)
from manage_agent_authority.canonical import object_sha256, sha256_file
from manage_agent_authority.operation_batch import (
    load_operation_batch,
    publish_projected_operation_batch,
)
from manage_agent_authority.root_decision_seed import compile_root_decision_seed
from manage_agent_authority.root_grant_materialization import (
    materialize_plan_bound_root_grant,
)
from manage_agent_authority.root_grant_plan import (
    load_root_approval_plan,
    prepare_root_approval_plan,
)
from orchestrate_task_cycle.selected_successor_authority_artifacts import (
    load_packet,
    load_projection,
)
from orchestrate_task_cycle.selected_successor_authority_resume import (
    resume_selected_successor_authority,
)
from orchestrate_task_cycle.selected_successor_authority_validation import (
    validate_authority_packet,
)
from orchestrate_task_cycle.selected_successor_execution import (
    execute_selected_successor_bundle,
)
from root_authorization_test_support import (
    install_test_trust_anchor,
    signed_root_authorization,
)
from selected_successor_authority_support import AT, SKILLS_ROOT
from test_selected_successor_authority_preparation import (
    _prepare_authority,
    _prepared,
)


PLAN_AT = "2026-07-17T10:01:00+09:00"
DECIDED_AT = "2026-07-17T10:02:00+09:00"
RESUMED_AT = "2026-07-17T10:03:00+09:00"
REPLAYED_AT = "2026-07-17T10:03:30+09:00"
EXECUTED_AT = "2026-07-17T10:04:00+09:00"
EXPIRES_AT = "2026-07-17T10:30:00+09:00"


@pytest.fixture(autouse=True)
def _host_authorization_trust(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install_test_trust_anchor(monkeypatch, tmp_path)


def _projection(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared, _bundle, inputs = _prepared(root, capsys, grants=False)
    result = _prepare_authority(root, prepared, inputs)
    _binding, projection = load_projection(root, result["approval_projection"])
    return result["approval_projection"], projection


def _root_plan(
    root: Path, projection_binding: dict[str, str]
) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    batch_result = publish_projected_operation_batch(
        root, projection_binding, skills_root=SKILLS_ROOT
    )
    policy = snapshot_file(root, ".agent_goal/agent_authority.md", "policy")
    update_current_policy(root, policy, expected_version=0)
    prepared = prepare_root_approval_plan(
        root,
        batch_result["operation_batch"],
        policy,
        {
            "source_kind": "explicit_user_instruction",
            "holder_rank": "S0",
            "expires_at": EXPIRES_AT,
            "session_id": "selected-successor-compiler-session",
        },
        prepared_at=PLAN_AT,
        skills_root=SKILLS_ROOT,
    )
    _binding, plan = load_root_approval_plan(
        root, prepared["root_approval_plan"], skills_root=SKILLS_ROOT
    )
    return prepared["root_approval_plan"], plan, batch_result


def _materialize(root: Path, plan_binding: dict[str, str]) -> dict[str, Any]:
    evidence = signed_root_authorization(
        root,
        plan_binding,
        decided_at=DECIDED_AT,
        evidence_id="selected-successor-bridge",
        skills_root=SKILLS_ROOT,
    )
    seed = compile_root_decision_seed(
        root,
        plan_binding,
        authorization_evidence=evidence,
        skills_root=SKILLS_ROOT,
    )
    return materialize_plan_bound_root_grant(
        root,
        plan_binding,
        seed["decision_seed"],
        skills_root=SKILLS_ROOT,
    )


def test_projection_bridge_builds_exact_root_plan_and_replays(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projection_binding, projection = _projection(tmp_path, capsys)
    plan_binding, plan, batch_result = _root_plan(tmp_path, projection_binding)
    normalized, batch, compilations = load_operation_batch(
        tmp_path, batch_result["operation_batch"], skills_root=SKILLS_ROOT
    )
    replay = publish_projected_operation_batch(
        tmp_path, projection_binding, skills_root=SKILLS_ROOT
    )

    projected_requests = [
        operation["request_sha256"] for operation in projection["operations"]
    ]
    assert normalized == batch_result["operation_batch"]
    assert batch["schema_version"] == 2
    assert batch["projection_source"]["binding"] == projection_binding
    assert [item["request_sha256"] for item in compilations] == projected_requests
    assert {
        (item["request"]["cycle_id"], item["request"]["task_id"])
        for item in compilations
    } == {("cycle-A", "task-next")}
    assert sorted(
        grant["request_sha256"] for grant in plan["approval_projection"]["grants"]
    ) == sorted(projected_requests)
    assert replay["operation_batch"] == batch_result["operation_batch"]
    assert replay["idempotent_replay"] is True
    assert plan_binding["ref"].startswith(
        ".task/authorization/root_approval_plans/sha256/"
    )


def test_projected_batch_source_validator_ignores_workspace_shadow_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection_binding, _projection_value = _projection(tmp_path, capsys)
    marker = tmp_path / "workspace-shadow-ran"
    shadow = tmp_path / "orchestrate_task_cycle"
    shadow.mkdir()
    payload = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('shadowed', encoding='utf-8')\n"
        "raise SystemExit(97)\n"
    )
    (shadow / "__init__.py").write_text(payload, encoding="utf-8")
    (shadow / "__main__.py").write_text(payload, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))

    result = publish_projected_operation_batch(
        tmp_path, projection_binding, skills_root=SKILLS_ROOT
    )

    assert result["status"] == "published"
    assert not marker.exists()


def test_projected_batch_source_validator_rejects_noncolocated_skills_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projection_binding, _projection_value = _projection(tmp_path, capsys)
    batch_result = publish_projected_operation_batch(
        tmp_path, projection_binding, skills_root=SKILLS_ROOT
    )
    alternate = tmp_path / "alternate-skills"
    alternate.mkdir()

    with pytest.raises(SystemExit, match="co-located skills root"):
        load_operation_batch(
            tmp_path,
            batch_result["operation_batch"],
            skills_root=alternate,
        )


def test_projected_root_plan_must_follow_projection_compilation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projection_binding, _projection_value = _projection(tmp_path, capsys)
    batch_result = publish_projected_operation_batch(
        tmp_path, projection_binding, skills_root=SKILLS_ROOT
    )
    policy = snapshot_file(tmp_path, ".agent_goal/agent_authority.md", "policy")
    update_current_policy(tmp_path, policy, expected_version=0)

    with pytest.raises(
        SystemExit,
        match="must be prepared after compilation",
    ):
        prepare_root_approval_plan(
            tmp_path,
            batch_result["operation_batch"],
            policy,
            {
                "source_kind": "explicit_user_instruction",
                "holder_rank": "S0",
                "expires_at": EXPIRES_AT,
                "session_id": "same-time-projected-root-plan",
            },
            prepared_at=AT,
            skills_root=SKILLS_ROOT,
        )


def test_signed_root_grants_resume_exact_projection_at_later_time(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projection_binding, projection = _projection(tmp_path, capsys)
    plan_binding, _plan, _batch = _root_plan(tmp_path, projection_binding)
    materialized = _materialize(tmp_path, plan_binding)
    compilation_root = tmp_path / ".task/authorization/operation_compilations"
    before = {path.name: path.read_bytes() for path in compilation_root.glob("*.json")}

    with pytest.raises(
        ValueError,
        match="predates its signed decision",
    ):
        resume_selected_successor_authority(
            tmp_path,
            projection_binding=projection_binding,
            materialization_binding=materialized["root_grant_materialization"],
            at=PLAN_AT,
            skills_root=SKILLS_ROOT,
        )

    resumed = resume_selected_successor_authority(
        tmp_path,
        projection_binding=projection_binding,
        materialization_binding=materialized["root_grant_materialization"],
        at=RESUMED_AT,
        skills_root=SKILLS_ROOT,
    )
    packet_binding, packet = load_packet(tmp_path, resumed["authority_packet"])
    validated = validate_authority_packet(
        tmp_path, packet_binding, skills_root=SKILLS_ROOT
    )

    assert resumed["status"] == "prepared"
    assert packet["schema_version"] == 2
    assert packet["compiled_at"] == AT
    assert packet["prepared_at"] == RESUMED_AT
    assert packet["source_projection"] == projection_binding
    assert (
        packet["root_grant_materialization"]
        == materialized["root_grant_materialization"]
    )
    assert [operation["request_sha256"] for operation in packet["operations"]] == [
        operation["request_sha256"] for operation in projection["operations"]
    ]
    assert all(
        chain_time == RESUMED_AT
        for operation in packet["operations"]
        for chain_time in (
            json.loads(
                (tmp_path / operation["decision"]["ref"]).read_text(encoding="utf-8")
            )["evaluated_at"],
            json.loads(
                (
                    tmp_path
                    / packet["authority_proofs"][operation["action"]]["reservation"][
                        "ref"
                    ]
                ).read_text(encoding="utf-8")
            )["reserved_at"],
            json.loads(
                (
                    tmp_path
                    / packet["authority_proofs"][operation["action"]][
                        "pre_commit_verification"
                    ]["ref"]
                ).read_text(encoding="utf-8")
            )["verified_at"],
        )
    )
    assert validated == packet
    verification_root = tmp_path / ".task/authorization/verifications"
    verification_count = len(list(verification_root.glob("*.json")))
    with pytest.raises(ValueError, match="reservation conflicts"):
        resume_selected_successor_authority(
            tmp_path,
            projection_binding=projection_binding,
            materialization_binding=materialized["root_grant_materialization"],
            at=REPLAYED_AT,
            skills_root=SKILLS_ROOT,
        )
    assert len(list(verification_root.glob("*.json"))) == verification_count
    executed = execute_selected_successor_bundle(
        tmp_path,
        bundle_binding=packet["bundle"],
        authority_proofs=packet["authority_proofs"],
        settled_at=EXECUTED_AT,
        skills_root=SKILLS_ROOT,
    )
    assert executed["status"] == "complete"
    for operation in packet["operations"]:
        action = operation["action"]
        reservation = json.loads(
            (
                tmp_path / packet["authority_proofs"][action]["reservation"]["ref"]
            ).read_text(encoding="utf-8")
        )
        reservation_state = json.loads(
            (
                tmp_path
                / ".task/authorization/state/reservations"
                / f"{reservation['reservation_id']}.json"
            ).read_text(encoding="utf-8")
        )
        decision = json.loads(
            (tmp_path / operation["decision"]["ref"]).read_text(encoding="utf-8")
        )
        grant_id = decision["selected_grants"][0]["grant_id"]
        grant_state = json.loads(
            (
                tmp_path / ".task/authorization/state/grants" / f"{grant_id}.json"
            ).read_text(encoding="utf-8")
        )
        assert (
            reservation_state["status"],
            reservation_state["version"],
        ) == ("consumed", 1)
        assert (
            grant_state["status"],
            grant_state["remaining_uses"],
            grant_state["reserved_uses"],
            grant_state["consumed_uses"],
            grant_state["version"],
        ) == ("exhausted", 0, 0, 1, 2)
    assert (
        validate_authority_packet(tmp_path, packet_binding, skills_root=SKILLS_ROOT)
        == packet
    )
    assert {
        path.name: path.read_bytes() for path in compilation_root.glob("*.json")
    } == before


def test_projected_batch_rejects_self_sealed_compilation_injection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    projection_binding, _projection_value = _projection(tmp_path, capsys)
    _plan_binding, _plan, batch_result = _root_plan(tmp_path, projection_binding)
    source_path = tmp_path / batch_result["operation_batch"]["ref"]
    forged = json.loads(source_path.read_text(encoding="utf-8"))
    forged["operation_compilations"] = list(reversed(forged["operation_compilations"]))
    body = {key: value for key, value in forged.items() if key != "batch_fingerprint"}
    forged["batch_fingerprint"] = object_sha256(body)
    target = (
        tmp_path
        / ".task/authorization/operation_batches/sha256"
        / f"{forged['batch_fingerprint']}.json"
    )
    target.write_text(
        json.dumps(forged, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    binding = {
        "ref": target.relative_to(tmp_path).as_posix(),
        "sha256": sha256_file(target),
    }

    with pytest.raises(SystemExit, match="differs from its owner projection"):
        load_operation_batch(tmp_path, binding, skills_root=SKILLS_ROOT)
