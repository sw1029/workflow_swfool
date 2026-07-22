from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from manage_agent_authority.canonical import (
    object_sha256,
    parse_time,
    sha256_file,
    write_immutable_json,
)
from manage_agent_authority.execution_results import create_execution_result
from manage_agent_authority.historical_proof_chain import (
    validate_historical_proof_chain,
    validate_historical_proof_chains,
)
from manage_agent_authority.projection_recovery import apply_projection_changes
from orchestrate_task_cycle.selected_successor_authority_artifacts import load_packet
from orchestrate_task_cycle.selected_successor_cli import main as successor_cli
from selected_successor_authority_support import AT, SKILLS_ROOT
from test_selected_successor_authority_preparation import (
    _prepare_authority,
    _prepared,
)


def _proof_inputs(packet: dict[str, object]) -> list[tuple[dict, dict, int]]:
    return [
        (
            proof["reservation"],
            proof["pre_commit_verification"],
            proof["expected_version"],
        )
        for proof in packet["authority_proofs"].values()
    ]


def _settle_registered_schema_v2_use(
    root: Path, proof: dict[str, object], *, key: str
) -> dict[str, str]:
    reservation_binding = proof["reservation"]
    reservation = json.loads(
        (root / reservation_binding["ref"]).read_text(encoding="utf-8")
    )
    decision = json.loads(
        (root / reservation["decision"]["ref"]).read_text(encoding="utf-8")
    )
    owner_path = root / ".task/authorization/legacy-unrelated-owner-result.json"
    owner_path.write_text('{"status":"historical_owner_result"}\n', encoding="utf-8")
    owner_binding = {
        "ref": owner_path.relative_to(root).as_posix(),
        "sha256": sha256_file(owner_path),
    }
    _, execution_binding = create_execution_result(
        root,
        reservation,
        decision,
        reservation_binding,
        proof["pre_commit_verification"],
        owner_binding,
        completed_at=AT,
        expected_subject_after_sha256=sha256_file(
            root / decision["request"]["subject"]["ref"]
        ),
    )
    receipt_id = "authu-" + object_sha256(
        {"reservation": reservation_binding["sha256"], "key": key}
    )[:24]
    changes: list[dict[str, object]] = []
    grant_versions: dict[str, int] = {}
    for use in reservation["grant_uses"]:
        path = root / ".task/authorization/state/grants" / f"{use['grant_id']}.json"
        before = json.loads(path.read_text(encoding="utf-8"))
        remaining = before["remaining_uses"]
        after = {
            **before,
            "status": "exhausted" if remaining == use["units"] else "active",
            "remaining_uses": (
                remaining - use["units"] if remaining is not None else None
            ),
            "reserved_uses": before["reserved_uses"] - use["units"],
            "consumed_uses": before["consumed_uses"] + use["units"],
            "version": before["version"] + 1,
            "last_event_id": receipt_id,
        }
        grant_versions[use["grant_id"]] = after["version"]
        changes.append(
            {"ref": path.relative_to(root).as_posix(), "before": before, "after": after}
        )
    state_path = (
        root
        / ".task/authorization/state/reservations"
        / f"{reservation['reservation_id']}.json"
    )
    before_state = json.loads(state_path.read_text(encoding="utf-8"))
    changes.append(
        {
            "ref": state_path.relative_to(root).as_posix(),
            "before": before_state,
            "after": {
                **before_state,
                "status": "consumed",
                "version": before_state["version"] + 1,
                "last_event_id": receipt_id,
            },
        }
    )
    receipt = {
        "schema_version": 2,
        "artifact_kind": "authority_use_receipt",
        "receipt_id": receipt_id,
        "reservation": reservation_binding,
        "execution_result": execution_binding,
        "owner_execution_result": owner_binding,
        "pre_commit_verification": proof["pre_commit_verification"],
        "consumed_at": parse_time(AT, "consumed_at").isoformat(),
        "grant_versions_after": grant_versions,
        "state_changes": changes,
        "idempotency_key": key,
    }
    path = root / ".task/authorization/use_receipts" / f"{receipt_id}.json"
    digest = write_immutable_json(path, receipt, "historical schema-v2 use receipt")
    apply_projection_changes(root, changes)
    return {"ref": path.relative_to(root).as_posix(), "sha256": digest}


def test_shared_grant_proofs_validate_before_and_after_consumed_replay(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(
        tmp_path, capsys, shared_grant_max_uses=3
    )
    authority = _prepare_authority(tmp_path, prepared, inputs)
    packet_binding, packet = load_packet(tmp_path, authority["authority_packet"])

    reserved = validate_historical_proof_chains(
        tmp_path, _proof_inputs(packet), skills_root=SKILLS_ROOT
    )
    assert [
        row["decision"]["selected_grants"][0]["state_version"] for row in reserved
    ] == [0, 1, 2]
    assert [row["current_state"]["status"] for row in reserved] == [
        "reserved",
        "reserved",
        "reserved",
    ]

    assert successor_cli(
        [
            "--root",
            str(tmp_path),
            "execute",
            "--authority-packet-ref",
            packet_binding["ref"],
            "--authority-packet-sha256",
            packet_binding["sha256"],
            "--at",
            AT,
            "--skills-root",
            str(SKILLS_ROOT),
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "complete"

    consumed = validate_historical_proof_chains(
        tmp_path, _proof_inputs(packet), skills_root=SKILLS_ROOT
    )
    assert [row["current_state"]["status"] for row in consumed] == [
        "consumed",
        "consumed",
        "consumed",
    ]
    assert [
        row["decision"]["selected_grants"][0]["state_version"] for row in consumed
    ] == [0, 1, 2]


def test_unrelated_settled_registered_schema_v2_receipt_is_inventory_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    authority = _prepare_authority(tmp_path, prepared, inputs)
    _packet_binding, packet = load_packet(tmp_path, authority["authority_packet"])
    proofs = list(packet["authority_proofs"].values())
    legacy_receipt = _settle_registered_schema_v2_use(
        tmp_path, proofs[0], key="unrelated-historical-use"
    )

    target = validate_historical_proof_chain(
        tmp_path,
        proofs[1]["reservation"],
        proofs[1]["pre_commit_verification"],
        expected_version=proofs[1]["expected_version"],
        skills_root=SKILLS_ROOT,
    )

    assert target["reservation_binding"] == proofs[1]["reservation"]
    assert target["current_state"]["status"] == "reserved"
    with pytest.raises(SystemExit):
        validate_historical_proof_chain(
            tmp_path,
            legacy_receipt,
            proofs[1]["pre_commit_verification"],
            expected_version=proofs[1]["expected_version"],
            skills_root=SKILLS_ROOT,
        )


@pytest.mark.parametrize("tamper", ("policy", "source", "evaluation"))
def test_historical_chain_reopens_exact_immutable_authority_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    tamper: str,
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    authority = _prepare_authority(tmp_path, prepared, inputs)
    _packet_binding, packet = load_packet(tmp_path, authority["authority_packet"])
    operation = packet["operations"][0]
    decision = json.loads(
        (tmp_path / operation["decision"]["ref"]).read_text(encoding="utf-8")
    )
    if tamper == "policy":
        ref = decision["selected_grants"][0]["policy_snapshot"]["ref"]
    elif tamper == "evaluation":
        ref = decision["evaluation_context"]["goal_autonomy_envelope"][
            "source_binding"
        ]["ref"]
    else:
        grant = json.loads(
            (tmp_path / operation["selected_grant"]["binding"]["ref"]).read_text(
                encoding="utf-8"
            )
        )
        ref = grant["source_approval"]["ref"]
    path = tmp_path / ref
    path.write_bytes(path.read_bytes() + b" ")
    proof = packet["authority_proofs"][operation["action"]]

    with pytest.raises(SystemExit):
        validate_historical_proof_chain(
            tmp_path,
            proof["reservation"],
            proof["pre_commit_verification"],
            expected_version=proof["expected_version"],
            skills_root=SKILLS_ROOT,
        )


def test_historical_chain_rejects_manifest_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    authority = _prepare_authority(tmp_path, prepared, inputs)
    _packet_binding, packet = load_packet(tmp_path, authority["authority_packet"])
    operation = packet["operations"][0]
    skill_id = "manage-task-state-index"
    custom = tmp_path / "custom-skills"
    target = custom / skill_id / "authority.operations.json"
    target.parent.mkdir(parents=True)
    shutil.copyfile(SKILLS_ROOT / skill_id / "authority.operations.json", target)
    target.write_bytes(target.read_bytes() + b" ")
    proof = packet["authority_proofs"][operation["action"]]

    with pytest.raises(SystemExit, match="manifest"):
        validate_historical_proof_chain(
            tmp_path,
            proof["reservation"],
            proof["pre_commit_verification"],
            expected_version=proof["expected_version"],
            skills_root=custom,
        )


def test_historical_chain_binds_precommit_version_to_reservation_intent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    authority = _prepare_authority(tmp_path, prepared, inputs)
    _packet_binding, packet = load_packet(tmp_path, authority["authority_packet"])
    operation = packet["operations"][0]
    proof = packet["authority_proofs"][operation["action"]]
    original = json.loads(
        (tmp_path / proof["pre_commit_verification"]["ref"]).read_text(
            encoding="utf-8"
        )
    )
    forged_version = 7
    core = {
        key: value for key, value in original.items() if key != "verification_id"
    }
    core["reservation_state"] = {
        **core["reservation_state"],
        "version": forged_version,
    }
    forged = {
        "verification_id": f"authv-{object_sha256(core)[:24]}",
        **core,
    }
    path = (
        tmp_path
        / ".task/authorization/verifications"
        / f"{forged['verification_id']}.json"
    )
    digest = write_immutable_json(path, forged, "forged historical precommit")

    with pytest.raises(SystemExit, match="reservation-state digest"):
        validate_historical_proof_chain(
            tmp_path,
            proof["reservation"],
            {"ref": path.relative_to(tmp_path).as_posix(), "sha256": digest},
            expected_version=forged_version,
            skills_root=SKILLS_ROOT,
        )
