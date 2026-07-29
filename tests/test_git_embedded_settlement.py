from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from repo_change_commit import git_observation
from repo_change_commit.git_embedded_settlement import (
    GitEmbeddedSettlementError,
    build_git_embedded_settlement,
    build_payload_projection,
    canonical_file_bytes,
    validate_git_embedded_settlement,
    verify_final_commit,
)
from repo_change_commit.git_observation import (
    message_sha256,
    prepare_anchor,
    recover_verified_closeout,
    verify_head,
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def binding(name: str) -> dict[str, str]:
    return {"ref": f".task/authorization/{name}.json", "sha256": "a" * 64}


def intent() -> dict:
    return {
        "commit_role": "closeout",
        "goal_id": "goal-1",
        "task_id": "task-1",
        "cycle_id": "cycle-1",
        "session_id": "session-1",
        "authority_request": binding("request"),
        "authority_reservation": binding("reservation"),
        "precommit_evidence": binding("precommit"),
    }


def init_repo(root: Path) -> None:
    git(root, "init")
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "config", "user.name", "Workflow Tests")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "tracked.txt")
    git(root, "commit", "-m", "Base")


def test_embedded_settlement_closes_in_one_commit_without_tracked_followup(
    tmp_path: Path, monkeypatch
) -> None:
    init_repo(tmp_path)
    monkeypatch.setattr(
        git_observation,
        "validate_authority_provenance",
        lambda root, value, **_kwargs: value,
    )
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (tmp_path / "report.json").write_text('{"status":"complete"}\n', encoding="utf-8")
    git(tmp_path, "add", "tracked.txt", "report.json")
    message = b"Close workflow cycle\n\nCycle: cycle-1\n"
    anchor_path = ".task/authorization/settlements/cycle-1.json"
    settlement = prepare_anchor(
        tmp_path,
        anchor_path=anchor_path,
        commit_message=message,
        intent=intent(),
    )
    assert prepare_anchor(
        tmp_path,
        anchor_path=anchor_path,
        commit_message=message,
        intent=intent(),
    ) == settlement
    assert settlement["contract_id"] == "git_embedded_settlement@v1"
    assert settlement["payload_changed_path_count"] == 2
    message_path = tmp_path / "message.txt"
    message_path.write_bytes(message)
    git(tmp_path, "commit", "-F", str(message_path))
    verification = verify_head(tmp_path, anchor_path=anchor_path)
    assert verification["terminal"] is True
    assert verification["tracked_post_commit_receipt_required"] is False
    recovered = recover_verified_closeout(
        tmp_path,
        anchor_path=anchor_path,
        expected={
            "commit_role": "closeout",
            "goal_id": "goal-1",
            "task_id": "task-1",
            "cycle_id": "cycle-1",
            "session_id": "session-1",
        },
    )
    assert recovered["commit_hash"] == verification["commit_oid"]
    assert recovered["settlement_verification"] == verification
    assert git(tmp_path, "status", "--short") == "?? message.txt"
    # The only remaining path is the intentionally untracked message input;
    # verification itself created no tracked settlement receipt.
    assert not any(
        path.name != "cycle-1.json"
        for path in (tmp_path / ".task/authorization/settlements").iterdir()
    )


def test_prepare_rejects_missing_authority_producer_artifacts(
    tmp_path: Path,
) -> None:
    init_repo(tmp_path)
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    git(tmp_path, "add", "tracked.txt")
    with pytest.raises(
        GitEmbeddedSettlementError, match="authority provenance"
    ):
        prepare_anchor(
            tmp_path,
            anchor_path=".task/authorization/settlements/cycle-1.json",
            commit_message=b"Close workflow cycle\n",
            intent=intent(),
        )
    assert not (
        tmp_path / ".task/authorization/settlements/cycle-1.json"
    ).exists()


def test_payload_projection_excludes_anchor_and_is_order_stable() -> None:
    tree = [
        {
            "path": "b.txt",
            "mode": "100644",
            "object_id": "1" * 40,
            "object_type": "blob",
        },
        {
            "path": "a.txt",
            "mode": "100644",
            "object_id": "2" * 40,
            "object_type": "blob",
        },
    ]
    diff = [
        {
            "path": "b.txt",
            "status": "M",
            "before_mode": "100644",
            "before_object_id": "3" * 40,
            "after_mode": "100644",
            "after_object_id": "1" * 40,
        }
    ]
    first = build_payload_projection(
        anchor_path=".task/anchor.json",
        payload_tree_oid="4" * 40,
        tree_entries=tree,
        diff_entries=diff,
    )
    second = build_payload_projection(
        anchor_path=".task/anchor.json",
        payload_tree_oid="4" * 40,
        tree_entries=list(reversed(tree)),
        diff_entries=diff,
    )
    assert first == second
    with pytest.raises(GitEmbeddedSettlementError, match="exclude"):
        build_payload_projection(
            anchor_path=".task/anchor.json",
            payload_tree_oid="4" * 40,
            tree_entries=[
                {
                    "path": ".task/anchor.json",
                    "mode": "100644",
                    "object_id": "2" * 40,
                    "object_type": "blob",
                }
            ],
            diff_entries=[],
        )


def test_settlement_and_final_observation_tampering_fail_closed() -> None:
    anchor_path = ".task/authorization/settlements/cycle-1.json"
    projection = build_payload_projection(
        anchor_path=anchor_path,
        payload_tree_oid="4" * 40,
        tree_entries=[],
        diff_entries=[],
    )
    settlement = build_git_embedded_settlement(
        anchor_path=anchor_path,
        parent_head="5" * 40,
        commit_message_sha256=message_sha256(b"message\n"),
        commit_role="closeout",
        goal_id="goal-1",
        task_id="task-1",
        cycle_id="cycle-1",
        session_id="session-1",
        authority_request=binding("request"),
        authority_reservation=binding("reservation"),
        precommit_evidence=binding("precommit"),
        payload_projection=projection,
    )
    tampered = deepcopy(settlement)
    tampered["task_id"] = "task-2"
    with pytest.raises(GitEmbeddedSettlementError, match="identity"):
        validate_git_embedded_settlement(tampered)
    observation = {
        "commit_oid": "6" * 40,
        "parent_heads": ["5" * 40],
        "commit_message_sha256": settlement["commit_message_sha256"],
        "anchor_path": settlement["anchor_path"],
        "anchor_blob_sha256": __import__("hashlib").sha256(
            canonical_file_bytes(settlement)
        ).hexdigest(),
        "payload_tree_oid": projection["payload_tree_oid"],
        "tree_entries": [],
        "diff_entries": [],
    }
    assert verify_final_commit(settlement, observation)["terminal"] is True
    observation["parent_heads"] = ["7" * 40]
    with pytest.raises(GitEmbeddedSettlementError, match="parent"):
        verify_final_commit(settlement, observation)


def test_prepare_rejects_non_reserved_or_preexisting_anchor_without_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    init_repo(tmp_path)
    monkeypatch.setattr(
        git_observation,
        "validate_authority_provenance",
        lambda root, value, **_kwargs: value,
    )
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    git(tmp_path, "add", "tracked.txt")
    with pytest.raises(GitEmbeddedSettlementError, match="reserved cycle"):
        prepare_anchor(
            tmp_path,
            anchor_path="tracked.txt",
            commit_message=b"Close workflow cycle\n",
            intent=intent(),
        )
    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "changed\n"

    reserved = (
        tmp_path / ".task/authorization/settlements/cycle-1.json"
    )
    reserved.parent.mkdir(parents=True)
    reserved.write_text("preexisting user bytes\n", encoding="utf-8")
    with pytest.raises(GitEmbeddedSettlementError, match="different bytes"):
        prepare_anchor(
            tmp_path,
            anchor_path=reserved.relative_to(tmp_path).as_posix(),
            commit_message=b"Close workflow cycle\n",
            intent=intent(),
        )
    assert reserved.read_text(encoding="utf-8") == "preexisting user bytes\n"
