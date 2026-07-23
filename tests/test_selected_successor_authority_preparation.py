from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

import pytest

from orchestrate_task_cycle.selected_successor import (
    load_selected_successor_bundle,
    prepare_selected_successor_bundle,
)
from orchestrate_task_cycle.selected_successor_authority import (
    prepare_selected_successor_authority,
)
from orchestrate_task_cycle.selected_successor_authority_publication import (
    _argv as authority_argv,
)
from orchestrate_task_cycle.selected_successor_authority_artifacts import (
    load_index,
    load_packet,
    load_projection,
)
from orchestrate_task_cycle.selected_successor_cli import main as successor_cli
from selected_successor_authority_support import (
    AT,
    SKILLS_ROOT,
    prepare_authority_inputs,
)
from test_selection_publication_external_transaction import (
    _binding,
    _initialize_active_task,
    _selected_receipt,
)


def _prepared(
    root: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    grants: bool = True,
    shared_grant_max_uses: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _initialize_active_task(root)
    decision = _selected_receipt(root, capsys)
    candidate = root / ".task/candidates/task-next.md"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("# Task\n\n- Task ID: `task-next`\n", encoding="utf-8")
    prepared = prepare_selected_successor_bundle(
        root,
        source_decision=decision,
        task_source=_binding(root, candidate),
        at=AT,
    )
    bundle = load_selected_successor_bundle(root, prepared["bundle"])
    inputs = prepare_authority_inputs(
        root,
        bundle,
        prepared["bundle"],
        register_existing_grants=grants,
        shared_grant_max_uses=shared_grant_max_uses,
    )
    return prepared, bundle, inputs


def _prepare_authority(
    root: Path, prepared: dict[str, Any], inputs: dict[str, Any]
) -> dict[str, Any]:
    return prepare_selected_successor_authority(
        root,
        bundle_binding=prepared["bundle"],
        request_context_binding=inputs["request_context"],
        evaluation_context_binding=inputs["evaluation_context"],
        grants=inputs["grants"],
        at=AT,
        skills_root=SKILLS_ROOT,
    )


def _authority_counts(root: Path) -> tuple[int, int, int]:
    authorization = root / ".task/authorization"
    return tuple(
        len(list((authorization / directory).glob("*.json")))
        for directory in ("decisions", "reservations", "verifications")
    )


def _damage_predecessor_snapshot(
    root: Path, bundle: dict[str, Any], damage: str
) -> None:
    plan = json.loads(
        (root / bundle["task_state_plan"]["ref"]).read_text(encoding="utf-8")
    )
    predecessor = next(
        event for event in plan["events"] if event["status"] == "superseded"
    )
    snapshot = root / predecessor["fields"]["snapshot_path"]
    if damage == "missing":
        snapshot.unlink()
    elif damage == "tampered":
        snapshot.write_bytes(snapshot.read_bytes() + b"\n# tampered\n")
    else:
        target = root / "predecessor-snapshot-symlink-target.md"
        target.write_bytes(snapshot.read_bytes())
        snapshot.unlink()
        snapshot.symlink_to(target)


def test_prepare_authority_builds_body_free_packet_and_packet_cli_executes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)

    result = _prepare_authority(tmp_path, prepared, inputs)
    packet_binding, packet = load_packet(tmp_path, result["authority_packet"])

    assert result["status"] == "prepared"
    assert result["model_authored_mechanical_bytes"] == 0
    assert result["execute_argv"][0] == sys.executable
    assert result["execute_argv"][1:4] == ["-B", "-I", "-c"]
    assert "--skills-root" in result["execute_argv"]
    assert str(SKILLS_ROOT.resolve()) in result["execute_argv"]
    assert packet_binding == result["authority_packet"]
    assert set(packet["authority_proofs"]) == {
        "apply_task_state_plan_pending",
        "publish_selected_successor_topology",
        "settle_selected_successor_task_state",
    }
    assert all(
        set(row)
        == {
            "action",
            "compilation",
            "request_sha256",
            "decision",
            "selected_grant",
        }
        for row in packet["operations"]
    )
    assert _authority_counts(tmp_path) == (3, 3, 3)

    shadow = tmp_path / "orchestrate_task_cycle"
    shadow.mkdir()
    marker = tmp_path / "workspace-shadow-ran"
    payload = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('shadowed', encoding='utf-8')\n"
        "raise SystemExit(97)\n"
    )
    (shadow / "__init__.py").write_text(payload, encoding="utf-8")
    (shadow / "__main__.py").write_text(payload, encoding="utf-8")
    fake_bin = tmp_path / "hostile-path"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 98\n", encoding="utf-8")
    fake_python.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]

    completed = subprocess.run(
        result["execute_argv"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    executed = json.loads(completed.stdout)
    assert executed["status"] == "complete"
    assert not marker.exists()

    recovered_process = subprocess.run(
        result["recover_argv"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert recovered_process.returncode == 0, (
        recovered_process.stderr or recovered_process.stdout
    )
    recovered = json.loads(recovered_process.stdout)
    assert recovered["status"] == "complete"
    assert not marker.exists()

    replay = _prepare_authority(tmp_path, prepared, inputs)
    assert replay["idempotent_replay"] is True
    assert replay["mutation_performed"] is False


def test_generated_authority_argv_never_imports_code_from_skills_root_argument(
    tmp_path: Path,
) -> None:
    alternate = tmp_path / "workspace-supplied-skills"
    packet = {
        "ref": ".task/authorization/packets/packet.json",
        "sha256": "a" * 64,
    }

    argv = authority_argv(tmp_path, "execute", packet, AT, alternate)

    import_root_count = int(argv[5])
    import_roots = argv[6 : 6 + import_root_count]
    assert import_roots
    assert all(not root.startswith(str(alternate)) for root in import_roots)
    assert argv[argv.index("--skills-root") + 1] == str(alternate.resolve())


def test_truly_absent_grants_publish_projection_but_no_authority_lifecycle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, grants=False)

    result = _prepare_authority(tmp_path, prepared, inputs)
    _binding_value, projection = load_projection(
        tmp_path, result["approval_projection"]
    )

    assert result["status"] == "approval_required"
    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert (
        len(
            list(
                (tmp_path / ".task/authorization/operation_compilations").glob("*.json")
            )
        )
        == 3
    )
    assert projection["authority_effects"]["decisions_published"] is False
    assert all("compilation" in row for row in projection["operations"])
    assert all(
        row["decision"] == "approval_required" for row in projection["operations"]
    )

    replay = _prepare_authority(tmp_path, prepared, inputs)
    assert replay["idempotent_replay"] is True
    assert _authority_counts(tmp_path) == (0, 0, 0)


def test_declared_absent_existing_grant_is_input_conflict_with_zero_writes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    action = "apply_task_state_plan_pending"
    inputs["grants"] = {**inputs["grants"], action: {"status": "absent"}}

    with pytest.raises(ValueError, match="conflicts with the exact input"):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert not (tmp_path / ".task/authorization/operation_compilations").exists()


def test_shared_grant_budget_is_preflighted_before_any_reservation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=2)

    result = _prepare_authority(tmp_path, prepared, inputs)
    _projection_binding, projection = load_projection(
        tmp_path, result["approval_projection"]
    )

    assert result["status"] == "approval_required"
    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert (
        len(
            list(
                (tmp_path / ".task/authorization/operation_compilations").glob("*.json")
            )
        )
        == 3
    )
    assert all(row["decision"] == "allowed" for row in projection["operations"])
    assert all(
        row["reason_codes"] == ["aggregate_grant_budget_insufficient"]
        and row["approval_projection"] is not None
        for row in projection["operations"]
    )

    replay = _prepare_authority(tmp_path, prepared, inputs)
    assert replay["idempotent_replay"] is True
    assert replay["mutation_performed"] is False
    assert _authority_counts(tmp_path) == (0, 0, 0)


@pytest.mark.parametrize(
    "closure_result",
    [
        {"status": "invalid", "route": "selected_successor_topology"},
        {"status": "ready", "route": "current_cycle"},
        {
            "status": "blocked_prerequisite",
            "route": "selected_successor_topology",
        },
    ],
    ids=("invalid", "route-mismatch", "incomplete"),
)
def test_non_ready_topology_closure_aborts_before_first_authority_reservation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    closure_result: dict[str, str],
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=3)
    grant_state_root = tmp_path / ".task/authorization/state/grants"
    grant_states_before = {
        path.name: path.read_bytes() for path in grant_state_root.glob("*.json")
    }
    import orchestrate_task_cycle.executable_closure_topology as topology

    monkeypatch.setattr(
        topology,
        "preflight_selected_successor_closure",
        lambda *_args, **_kwargs: dict(closure_result),
    )

    with pytest.raises(
        ValueError,
        match="executable closure is not ready before reservation",
    ):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert {
        path.name: path.read_bytes() for path in grant_state_root.glob("*.json")
    } == grant_states_before
    assert not list(
        (tmp_path / ".task/authorization/state/reservations").glob("*.json")
    )
    assert (
        len(
            list(
                (tmp_path / ".task/authorization/operation_compilations").glob("*.json")
            )
        )
        == 3
    )


def test_task_swap_after_ready_closure_aborts_before_first_reservation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=3)
    grant_state_root = tmp_path / ".task/authorization/state/grants"
    grant_states_before = {
        path.name: path.read_bytes() for path in grant_state_root.glob("*.json")
    }
    import orchestrate_task_cycle.selected_successor_authority_publication as publication

    swapped = False

    def swap_task_after_closure(
        stage: str, root: Path, closure: dict[str, Any]
    ) -> None:
        nonlocal swapped
        assert stage == "after_pure_preflight"
        assert closure["status"] == "ready"
        if swapped:
            return
        swapped = True
        (root / "task.md").write_text(
            "# Task\n\n- Task ID: `task-swapped-after-closure`\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(
        publication, "_reservation_closure_hook", swap_task_after_closure
    )

    with pytest.raises(
        ValueError,
        match="closure epoch changed before authority reservation",
    ):
        _prepare_authority(tmp_path, prepared, inputs)

    assert swapped is True
    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert {
        path.name: path.read_bytes() for path in grant_state_root.glob("*.json")
    } == grant_states_before
    assert not list(
        (tmp_path / ".task/authorization/state/reservations").glob("*.json")
    )


@pytest.mark.parametrize("damage", ("missing", "tampered", "symlink"))
def test_snapshot_drift_after_ready_closure_has_zero_reservations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    prepared, bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=3)
    import orchestrate_task_cycle.selected_successor_authority_publication as publication

    drifted = False

    def damage_after_closure(stage: str, root: Path, closure: dict[str, Any]) -> None:
        nonlocal drifted
        assert stage == "after_pure_preflight"
        assert closure["status"] == "ready"
        assert closure["closure_epoch"]["selected_successor_predecessor"]["snapshot"]
        if not drifted:
            _damage_predecessor_snapshot(root, bundle, damage)
            drifted = True

    monkeypatch.setattr(publication, "_reservation_closure_hook", damage_after_closure)

    with pytest.raises(
        ValueError,
        match="closure epoch changed before authority reservation",
    ):
        _prepare_authority(tmp_path, prepared, inputs)

    assert drifted is True
    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert not list(
        (tmp_path / ".task/authorization/state/reservations").glob("*.json")
    )


@pytest.mark.parametrize("damage", ("missing", "tampered", "symlink"))
def test_predecessor_snapshot_drift_before_authority_has_zero_reservations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    damage: str,
) -> None:
    prepared, bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=3)
    _damage_predecessor_snapshot(tmp_path, bundle, damage)
    grant_state_root = tmp_path / ".task/authorization/state/grants"
    grant_states_before = {
        path.name: path.read_bytes() for path in grant_state_root.glob("*.json")
    }

    with pytest.raises(ValueError, match="predecessor snapshot"):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert {
        path.name: path.read_bytes() for path in grant_state_root.glob("*.json")
    } == grant_states_before
    assert not list(
        (tmp_path / ".task/authorization/state/reservations").glob("*.json")
    )


def test_unrelated_unique_active_alias_rejects_topology_without_authority_writes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=3)
    from test_executable_closure import _task
    import orchestrate_task_cycle.selected_successor_authority as authority

    monkeypatch.setattr(
        authority,
        "validate_pristine_source",
        lambda *_args, **_kwargs: None,
    )

    _task(tmp_path, task_id="task-unrelated", status="active")
    grant_state_root = tmp_path / ".task/authorization/state/grants"
    grant_states_before = {
        path.name: path.read_bytes() for path in grant_state_root.glob("*.json")
    }

    with pytest.raises(
        ValueError,
        match="executable closure is not ready before reservation",
    ):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert {
        path.name: path.read_bytes() for path in grant_state_root.glob("*.json")
    } == grant_states_before


def test_legitimate_task_index_writer_waits_for_reservation_scope(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=3)
    import orchestrate_task_cycle.selected_successor_authority_publication as publication
    from manage_task_state_index import index as task_index

    started = threading.Event()
    finished = threading.Event()
    failures: list[BaseException] = []
    writer: threading.Thread | None = None

    def write_index() -> None:
        try:
            started.set()
            task_index.append_event(
                tmp_path,
                {
                    "event": "upsert",
                    "id": "audit-concurrent-closure-writer",
                    "type": "audit",
                    "status": "logged",
                    "path": ".task/concurrent-closure-audit.md",
                    "title": "Concurrent closure audit",
                    "updated_at": "2026-07-17T10:00:01+09:00",
                },
            )
        except BaseException as exc:  # pragma: no cover - asserted below.
            failures.append(exc)
        finally:
            finished.set()

    def start_writer(stage: str, _root: Path, closure: dict[str, Any]) -> None:
        nonlocal writer
        assert stage == "after_pure_preflight"
        assert closure["status"] == "ready"
        writer = threading.Thread(target=write_index, daemon=True)
        writer.start()
        assert started.wait(timeout=1)
        assert not finished.wait(timeout=0.05)

    monkeypatch.setattr(publication, "_reservation_closure_hook", start_writer)

    result = _prepare_authority(tmp_path, prepared, inputs)
    assert result["status"] == "prepared"
    assert writer is not None
    writer.join(timeout=2)
    assert finished.is_set()
    assert failures == []
    assert _authority_counts(tmp_path) == (3, 3, 3)


def test_sufficient_shared_grant_tracks_current_version_per_chain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=3)

    result = _prepare_authority(tmp_path, prepared, inputs)
    _packet_binding, packet = load_packet(tmp_path, result["authority_packet"])

    assert result["status"] == "prepared"
    assert _authority_counts(tmp_path) == (3, 3, 3)
    assert len(packet["operations"]) == 3
    assert len(packet["authority_proofs"]) == 3
    assert len({row["decision"]["ref"] for row in packet["operations"]}) == 3
    assert (
        len(
            {
                proof["reservation"]["ref"]
                for proof in packet["authority_proofs"].values()
            }
        )
        == 3
    )
    assert (
        len(
            {
                proof["pre_commit_verification"]["ref"]
                for proof in packet["authority_proofs"].values()
            }
        )
        == 3
    )
    grant_ids = []
    state_versions = []
    for operation in packet["operations"]:
        decision = json.loads(
            (tmp_path / operation["decision"]["ref"]).read_text(encoding="utf-8")
        )
        grant_ids.append(decision["selected_grants"][0]["grant_id"])
        state_versions.append(decision["selected_grants"][0]["state_version"])
    assert len(set(grant_ids)) == 1
    assert state_versions == [0, 1, 2]
    shared_state = json.loads(
        (
            tmp_path
            / ".task/authorization/state/grants/selected-compiler-shared-grant.json"
        ).read_text(encoding="utf-8")
    )
    assert shared_state["reserved_uses"] == 3
    assert shared_state["version"] == 3

    replay = _prepare_authority(tmp_path, prepared, inputs)
    assert replay["idempotent_replay"] is True


def test_sufficient_shared_grant_resumes_after_first_reservation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys, shared_grant_max_uses=3)
    import manage_agent_authority.lifecycle as lifecycle

    real_reserve = lifecycle.reserve
    calls = 0

    def crash_on_second(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second reservation crash")
        return real_reserve(*args, **kwargs)

    with monkeypatch.context() as crash:
        crash.setattr(lifecycle, "reserve", crash_on_second)
        with pytest.raises(RuntimeError, match="second reservation crash"):
            _prepare_authority(tmp_path, prepared, inputs)

    result = _prepare_authority(tmp_path, prepared, inputs)
    assert result["status"] == "prepared"
    assert _authority_counts(tmp_path) == (3, 3, 3)


@pytest.mark.parametrize("input_name", ("request_context", "evaluation_context"))
def test_oversized_context_fails_before_compilation_or_authority_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    input_name: str,
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    path = tmp_path / inputs[input_name]["ref"]
    path.write_bytes(b"{" + b" " * (64 * 1024 + 1) + b"}")
    inputs[input_name] = {
        "ref": path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }

    with pytest.raises(ValueError, match="artifact size limit"):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _authority_counts(tmp_path) == (0, 0, 0)
    assert not (tmp_path / ".task/authorization/operation_compilations").exists()


def test_packet_locator_repairs_missing_index_after_consumed_execution(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    import orchestrate_task_cycle.selected_successor_authority_publication as publication

    with monkeypatch.context() as crash:
        crash.setattr(
            publication,
            "publish_index",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("index crash")
            ),
        )
        with pytest.raises(RuntimeError, match="index crash"):
            _prepare_authority(tmp_path, prepared, inputs)

    locator_path = next(
        (
            tmp_path / ".task/selection_publication/successor_authority_locators/sha256"
        ).glob("*.json")
    )
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    packet_binding = locator["packet"]
    code = successor_cli(
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
    )
    assert code == 0
    capsys.readouterr()

    replay = _prepare_authority(tmp_path, prepared, inputs)
    assert replay["index_repaired"] is True
    assert replay["authority_packet"] == packet_binding


def test_invalid_located_packet_is_not_swallowed_or_reauthorized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _bundle, inputs = _prepared(tmp_path, capsys)
    import orchestrate_task_cycle.selected_successor_authority_publication as publication

    with monkeypatch.context() as crash:
        crash.setattr(
            publication,
            "publish_index",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("index crash")
            ),
        )
        with pytest.raises(RuntimeError):
            _prepare_authority(tmp_path, prepared, inputs)
    locator_path = next(
        (
            tmp_path / ".task/selection_publication/successor_authority_locators/sha256"
        ).glob("*.json")
    )
    locator = json.loads(locator_path.read_text(encoding="utf-8"))
    packet_path = tmp_path / locator["packet"]["ref"]
    packet_path.write_bytes(packet_path.read_bytes() + b" ")
    before = _authority_counts(tmp_path)

    with pytest.raises(ValueError, match="raw SHA-256"):
        _prepare_authority(tmp_path, prepared, inputs)

    assert _authority_counts(tmp_path) == before
    assert not list(
        (
            tmp_path / ".task/selection_publication/successor_authority_indexes/sha256"
        ).glob("*.json")
    )


@pytest.mark.parametrize("kind", ("packet", "projection"))
def test_compact_outcome_loaders_reject_over_256_kib_before_json_parse(
    tmp_path: Path, kind: str
) -> None:
    suffix = "packets" if kind == "packet" else "projections"
    path = (
        tmp_path
        / f".task/selection_publication/successor_authority_{suffix}/sha256"
        / f"{'0' * 64}.json"
    )
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{" + b" " * (256 * 1024 + 1) + b"}")
    binding = {
        "ref": path.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }

    loader = load_packet if kind == "packet" else load_projection
    with pytest.raises(ValueError, match="artifact size limit"):
        loader(tmp_path, binding)


@pytest.mark.parametrize("mode", ("oversized", "symlink"))
def test_authority_index_reader_is_bounded_and_no_follow(
    tmp_path: Path, mode: str
) -> None:
    input_sha = "1" * 64
    identity = {
        "prepared_at": AT,
        "bundle": {"ref": "x", "sha256": "2" * 64},
        "request_context": {"ref": "y", "sha256": "3" * 64},
        "evaluation_context": {"ref": "z", "sha256": "4" * 64},
        "grants": {},
        "operation_manifests": {},
    }
    path = (
        tmp_path
        / ".task/selection_publication/successor_authority_indexes/sha256"
        / f"{input_sha}.json"
    )
    path.parent.mkdir(parents=True)
    if mode == "oversized":
        path.write_bytes(b"{" + b" " * (64 * 1024 + 1) + b"}")
        match = "at most 64 KiB"
    else:
        target = tmp_path / "outside-index.json"
        target.write_text("{}", encoding="utf-8")
        path.symlink_to(target)
        match = "cannot be a symlink"

    with pytest.raises(ValueError, match=match):
        load_index(tmp_path, identity, input_sha)
