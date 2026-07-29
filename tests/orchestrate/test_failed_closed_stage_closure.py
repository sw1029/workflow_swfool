from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from orchestrate_task_cycle.cycle_ledger import init_cycle, read_events
from orchestrate_task_cycle.ledger.compiled_events import (
    append_compiled_stage_observation,
    append_compiled_system_stage,
)
from orchestrate_task_cycle.ledger.constants import (
    COMPILED_STAGE_OBSERVATION_EVENT_KIND,
)
from orchestrate_task_cycle.ledger.semantic_seeds import (
    make_stage_observation_seed,
)
from orchestrate_task_cycle.stage.advance import _blocked
from orchestrate_task_cycle.stage.closure import (
    is_failed_closed_run_event,
    validate_failed_closed_projection,
)
from orchestrate_task_cycle.stage.service import _next_target
from orchestrate_task_cycle.stage.specs import (
    LEGACY_TARGET_COMPILE_SPECS,
    TARGET_COMPILE_SPECS,
)
from orchestrate_task_cycle.stage.v2_context import collect_selected_context
from orchestrate_task_cycle.stage import input_compilers
from orchestrate_task_cycle.transition.access import completed
from orchestrate_task_cycle.transition.constants import ORDER
from orchestrate_task_cycle.continuation.actions import build_action
from orchestrate_task_cycle.continuation.contracts import (
    ContinuationContractError,
)
from orchestrate_task_cycle.continuation.terminal import (
    run_terminal_owner_intake,
)
from orchestrate_task_cycle.continuation import stage_adapter
from run_task_code_and_log.terminal_projection import (
    build_run_terminal_projection,
    publish_run_terminal_projection,
)
from orchestrate_task_cycle.stage import run_terminal_publication


CYCLE_ID = "cycle-1"
RUN_ID = "run-1"


def _binding(
    root: Path | None, ref: str, marker: str
) -> dict[str, str]:
    if root is None:
        return {"ref": ref, "sha256": "a" * 64}
    path = root / ref
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = f"{marker}\n".encode()
    path.write_bytes(payload)
    return {"ref": ref, "sha256": hashlib.sha256(payload).hexdigest()}


def _artifact(
    identifier: str,
    safety_status: str = "safe",
    *,
    root: Path | None = None,
) -> dict[str, object]:
    return {
        "artifact_id": identifier,
        "binding": _binding(root, f"var/{identifier}.json", identifier),
        "safety_status": safety_status,
    }


def _failed_projection(
    root: Path | None = None,
    *,
    cycle_id: str = CYCLE_ID,
    run_id: str = RUN_ID,
    monitor_event_id: str = "event-run-terminal",
    variant: str = "primary",
) -> dict[str, object]:
    return build_run_terminal_projection(
        cycle_id=cycle_id,
        run_id=run_id,
        status="failed_closed",
        monitor={
            "status": "terminal",
            "monitor_command_id": monitor_event_id,
            "stop_command_id": None,
        },
        harvest={"status": "unavailable", "evidence_binding": None},
        safe_surviving_artifacts=[_artifact("log", root=root)],
        discarded_artifacts=[
            _artifact(f"candidate-{variant}", "unsafe", root=root)
        ],
        failure={
            "reason": "safety_gate",
            "evidence_binding": _binding(
                root, f"var/autopsy-{variant}.json", f"autopsy-{variant}"
            ),
        },
        next_action="review",
        retry_policy={"automatic_retry": False},
    )


def _succeeded_projection(
    root: Path | None = None,
    *,
    cycle_id: str = CYCLE_ID,
    run_id: str = RUN_ID,
    monitor_event_id: str = "event-run-terminal",
) -> dict[str, object]:
    return build_run_terminal_projection(
        cycle_id=cycle_id,
        run_id=run_id,
        status="succeeded",
        monitor={
            "status": "terminal",
            "monitor_command_id": monitor_event_id,
            "stop_command_id": None,
        },
        harvest={
            "status": "completed",
            "evidence_binding": _binding(
                root, "var/harvest.json", "harvest"
            ),
        },
        safe_surviving_artifacts=[],
        discarded_artifacts=[],
        failure=None,
        next_action="complete",
        retry_policy={"automatic_retry": False},
    )


def _terminal_event(
    root: Path,
    *,
    projection: dict[str, object] | list[dict[str, object]] | None = None,
) -> dict[str, object]:
    value = projection or _failed_projection(root)
    published = publish_run_terminal_projection(root, value)
    failed = value["status"] == "failed_closed"
    return {
        "event_id": (
            f"{value['cycle_id']}-run-terminal-{value['projection_id']}"
        ),
        "event_kind": COMPILED_STAGE_OBSERVATION_EVENT_KIND,
        "producer_kind": "stage_observer",
        "observation_kind": "run_terminal",
        "cycle_id": value["cycle_id"],
        "step": "run",
        "status": "failed" if failed else "complete",
        "execution_status": value["status"],
        "run_id": value["run_id"],
        "run_terminal_projection": value,
        "run_terminal_projection_binding": published["binding"],
    }


def _events_through_run(run_event: dict[str, object]) -> list[dict[str, object]]:
    run_index = ORDER.index("run")
    events = [
        {"event_id": f"event-{step}", "step": step, "status": "completed"}
        for step in ORDER[:run_index]
    ]
    events.append(run_event)
    return events


def _initialize_live_run(
    root: Path,
    *,
    cycle_id: str = CYCLE_ID,
    run_id: str = RUN_ID,
    execution_status: str = "failed",
    projection: dict[str, object] | None = None,
) -> dict[str, object]:
    (root / "task.md").write_text("# Task\n", encoding="utf-8")
    init_cycle(root, cycle_id, "task-1", "terminal projection test")
    append_compiled_system_stage(root, cycle_id, "context")
    artifacts: list[str] = []
    if projection is not None:
        projections = projection if isinstance(projection, list) else [projection]
        bindings = []
        for item in projections:
            bindings.extend(
                [
                    item["harvest"]["evidence_binding"],
                    *(
                        row["binding"]
                        for row in item["safe_surviving_artifacts"]
                    ),
                    *(
                        row["binding"]
                        for row in item["discarded_artifacts"]
                    ),
                    (
                        item["failure"]["evidence_binding"]
                        if item.get("failure") is not None
                        else None
                    ),
                ]
            )
        artifacts = [
            str(binding["ref"])
            for binding in bindings
            if isinstance(binding, dict)
        ]
    publication = append_compiled_stage_observation(
        root,
        cycle_id,
        make_stage_observation_seed(
            {
                "observation_kind": "long_run_status",
                "execution_status": execution_status,
                "task_id": "task-1",
                "run_id": run_id,
                "artifacts": artifacts,
                "reason": "run terminal source observed",
            }
        ),
    )
    return publication["event"]


def _publish_failed_terminal(
    root: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    draft = _failed_projection(root)
    source = _initialize_live_run(root, projection=draft)
    projection = _failed_projection(
        root, monitor_event_id=str(source["event_id"])
    )
    binding = publish_run_terminal_projection(root, projection)["binding"]
    publication = run_terminal_publication.publish_run_terminal_observation(
        root,
        CYCLE_ID,
        projection=projection,
        projection_binding=binding,
    )
    return projection, publication["event"]


def test_verified_failed_closed_run_is_a_terminal_ordering_state(
    tmp_path: Path,
) -> None:
    event = _terminal_event(tmp_path)

    assert validate_failed_closed_projection(
        event["run_terminal_projection"]
    ) == event["run_terminal_projection"]
    assert is_failed_closed_run_event(
        event, root=tmp_path, cycle_id=CYCLE_ID
    )
    assert _blocked([event], root=tmp_path, cycle_id=CYCLE_ID) == []
    assert completed(
        {"events": [event]},
        "run",
        root=tmp_path,
        cycle_id=CYCLE_ID,
    )
    assert _next_target(
        _events_through_run(event),
        "normal",
        3,
        root=tmp_path,
        cycle_id=CYCLE_ID,
    ) == "qualitative_review"


def test_failed_closed_owner_context_exposes_only_safe_run_bindings(
    tmp_path: Path,
) -> None:
    projection, _event = _publish_failed_terminal(tmp_path)
    intake = run_terminal_owner_intake(tmp_path, CYCLE_ID)
    assert intake is not None
    assert intake["safe_surviving_artifacts"] == [
        projection["safe_surviving_artifacts"][0]["binding"]
    ]
    assert intake["discarded_artifact_count"] == 1
    assert "discarded_artifacts" not in intake

    _full, model, _metrics = collect_selected_context(
        tmp_path,
        CYCLE_ID,
        TARGET_COMPILE_SPECS["qualitative_review"],
        max_files=12,
        max_paths=40,
    )
    serialized = json.dumps(model, sort_keys=True)
    assert projection["safe_surviving_artifacts"][0]["binding"]["ref"] in serialized
    assert projection["failure"]["evidence_binding"]["ref"] in serialized
    assert projection["discarded_artifacts"][0]["binding"]["ref"] not in serialized


def test_owner_acceptance_rejects_discarded_run_source_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projection, _event = _publish_failed_terminal(tmp_path)
    action = build_action(
        actor="agent",
        kind="run_owner",
        session_id="session-1",
        cycle_id=CYCLE_ID,
        task_id="task-1",
        target="qualitative_review",
        owner_skill="review-cycle-output-quality",
        preparation_binding={
            "ref": ".task/cycle/cycle-1/preparation.json",
            "sha256": "a" * 64,
        },
        work_order_binding={
            "ref": ".task/cycle/cycle-1/work-order.json",
            "sha256": "b" * 64,
        },
        routing={},
        continuation_token={
            "state_version": 1,
            "state_sha256": "c" * 64,
        },
        effect_class="observe_only",
        required_result_contract={},
    )
    monkeypatch.setattr(
        stage_adapter,
        "load_published_preparation",
        lambda *_args, **_kwargs: {"target": "qualitative_review"},
    )

    def unexpected_publish(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("discarded source was opened by the owner producer")

    monkeypatch.setattr(stage_adapter, "_publish_inputs", unexpected_publish)
    with pytest.raises(ContinuationContractError, match="discarded"):
        stage_adapter._accept(
            tmp_path,
            action,
            {
                "source_binding": projection["discarded_artifacts"][0][
                    "binding"
                ]
            },
            goal_id=None,
        )


def test_owner_result_producer_rejects_discarded_source_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projection, _event = _publish_failed_terminal(tmp_path)
    monkeypatch.setattr(
        input_compilers,
        "_preparation",
        lambda *_args, **_kwargs: (
            tmp_path,
            {"target": "index", "cycle_id": CYCLE_ID},
        ),
    )

    def unexpected_read(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("discarded source was opened")

    monkeypatch.setattr(input_compilers, "_read_exact_json", unexpected_read)
    discarded = projection["discarded_artifacts"][0]["binding"]
    with pytest.raises(ContinuationContractError, match="discarded"):
        input_compilers.publish_owner_result(
            tmp_path,
            ".task/cycle/cycle-1/preparation.json",
            "a" * 64,
            source_ref=discarded["ref"],
            source_sha256=discarded["sha256"],
        )


def test_non_producer_or_missing_cas_failure_remains_blocking(
    tmp_path: Path,
) -> None:
    projection = _failed_projection(tmp_path)
    event = _terminal_event(tmp_path, projection=projection)
    event["producer_kind"] = "stage_result_compiler"
    assert not is_failed_closed_run_event(
        event, root=tmp_path, cycle_id=CYCLE_ID
    )

    forged = deepcopy(event)
    forged["producer_kind"] = "stage_observer"
    forged["run_terminal_projection_binding"] = {
        "ref": "var/run-terminal.json",
        "sha256": "a" * 64,
    }
    assert not is_failed_closed_run_event(
        forged, root=tmp_path, cycle_id=CYCLE_ID
    )
    assert _blocked(
        [forged], root=tmp_path, cycle_id=CYCLE_ID
    ) == [forged]


@pytest.mark.parametrize(
    "tamper",
    [
        "binding_digest",
        "missing_binding",
        "run_id",
        "cycle_id",
        "automatic_retry",
        "unsafe_survivor",
        "event_id",
    ],
)
def test_tampered_or_retrying_failure_closure_remains_blocking(
    tmp_path: Path,
    tamper: str,
) -> None:
    event = _terminal_event(tmp_path)
    projection = event["run_terminal_projection"]
    assert isinstance(projection, dict)
    if tamper == "binding_digest":
        binding = event["run_terminal_projection_binding"]
        assert isinstance(binding, dict)
        binding["sha256"] = "f" * 64
    elif tamper == "missing_binding":
        event.pop("run_terminal_projection_binding")
    elif tamper == "run_id":
        event["run_id"] = "run-other"
    elif tamper == "cycle_id":
        event["cycle_id"] = "cycle-other"
    elif tamper == "automatic_retry":
        retry = projection["retry_policy"]
        assert isinstance(retry, dict)
        retry["automatic_retry"] = True
    elif tamper == "unsafe_survivor":
        surviving = projection["safe_surviving_artifacts"]
        assert isinstance(surviving, list)
        survivor = surviving[0]
        assert isinstance(survivor, dict)
        survivor["safety_status"] = "unknown"
    else:
        event["event_id"] = "forged-event"

    assert not is_failed_closed_run_event(
        event, root=tmp_path, cycle_id=CYCLE_ID
    )
    assert _blocked(
        [event], root=tmp_path, cycle_id=CYCLE_ID
    ) == [event]
    assert not completed(
        {"events": [event]},
        "run",
        root=tmp_path,
        cycle_id=CYCLE_ID,
    )
    assert _next_target(
        _events_through_run(event),
        "normal",
        3,
        root=tmp_path,
        cycle_id=CYCLE_ID,
    ) == "run"


def test_succeeded_projection_cannot_close_a_failed_run(tmp_path: Path) -> None:
    event = _terminal_event(
        tmp_path, projection=_succeeded_projection(tmp_path)
    )
    event["status"] = "failed"
    event["execution_status"] = "failed"

    assert not is_failed_closed_run_event(
        event, root=tmp_path, cycle_id=CYCLE_ID
    )
    assert _blocked(
        [event], root=tmp_path, cycle_id=CYCLE_ID
    ) == [event]


def test_succeeded_terminal_is_reopened_at_each_interpretation(
    tmp_path: Path,
) -> None:
    event = _terminal_event(
        tmp_path, projection=_succeeded_projection(tmp_path)
    )
    events = _events_through_run(event)

    assert _blocked([event], root=tmp_path, cycle_id=CYCLE_ID) == []
    assert completed(
        {"events": [event]},
        "run",
        root=tmp_path,
        cycle_id=CYCLE_ID,
    )
    assert _next_target(
        events,
        "normal",
        3,
        root=tmp_path,
        cycle_id=CYCLE_ID,
    ) == "qualitative_review"

    binding = event["run_terminal_projection_binding"]
    (tmp_path / binding["ref"]).unlink()

    assert _blocked(
        [event], root=tmp_path, cycle_id=CYCLE_ID
    ) == [event]
    assert not completed(
        {"events": [event]},
        "run",
        root=tmp_path,
        cycle_id=CYCLE_ID,
    )
    assert _next_target(
        events,
        "normal",
        3,
        root=tmp_path,
        cycle_id=CYCLE_ID,
    ) == "run"


def test_non_run_failure_behavior_is_unchanged() -> None:
    event = {
        "event_id": "review-event",
        "step": "qualitative_review",
        "status": "failed",
    }
    assert _blocked([event]) == [event]
    assert not completed({"events": [event]}, "qualitative_review")


def test_generic_run_results_cannot_author_terminal_projection_fields() -> None:
    forbidden = {"run_terminal_projection", "run_terminal_projection_binding"}
    assert forbidden.isdisjoint(
        TARGET_COMPILE_SPECS["run"].optional_owner_fields
    )
    assert forbidden.isdisjoint(
        LEGACY_TARGET_COMPILE_SPECS["run"].optional_owner_fields
    )


def test_terminal_publication_rejects_unjustified_success(
    tmp_path: Path,
) -> None:
    draft = _succeeded_projection(tmp_path)
    source = _initialize_live_run(
        tmp_path,
        execution_status="running",
        projection=draft,
    )
    projection = _succeeded_projection(
        tmp_path, monitor_event_id=str(source["event_id"])
    )
    published = publish_run_terminal_projection(tmp_path, projection)
    with pytest.raises(ValueError, match="does not support"):
        run_terminal_publication.publish_run_terminal_observation(
            tmp_path,
            CYCLE_ID,
            projection=projection,
            projection_binding=published["binding"],
        )


def test_terminal_publication_rejects_undeclared_evidence(
    tmp_path: Path,
) -> None:
    source = _initialize_live_run(
        tmp_path,
        execution_status="failed",
        projection=None,
    )
    projection = _failed_projection(
        tmp_path, monitor_event_id=str(source["event_id"])
    )
    published = publish_run_terminal_projection(tmp_path, projection)
    with pytest.raises(ValueError, match="not declared"):
        run_terminal_publication.publish_run_terminal_observation(
            tmp_path,
            CYCLE_ID,
            projection=projection,
            projection_binding=published["binding"],
        )


def test_terminal_projection_is_single_assignment_with_exact_replay(
    tmp_path: Path,
) -> None:
    draft = _failed_projection(tmp_path)
    conflict_draft = _failed_projection(tmp_path, variant="conflict")
    source = _initialize_live_run(
        tmp_path, projection=[draft, conflict_draft]
    )
    failed = _failed_projection(
        tmp_path, monitor_event_id=str(source["event_id"])
    )
    published = publish_run_terminal_projection(tmp_path, failed)
    first = run_terminal_publication.publish_run_terminal_observation(
        tmp_path,
        CYCLE_ID,
        projection=failed,
        projection_binding=published["binding"],
    )
    replay = run_terminal_publication.publish_run_terminal_observation(
        tmp_path,
        CYCLE_ID,
        projection=failed,
        projection_binding=published["binding"],
    )
    assert first["event"]["observation_kind"] == "run_terminal"
    assert replay["event_duplicate"] is True
    assert len(
        [
            event
            for event in read_events(tmp_path, CYCLE_ID)
            if event.get("observation_kind") == "run_terminal"
        ]
    ) == 1

    conflict = _failed_projection(
        tmp_path,
        monitor_event_id=str(source["event_id"]),
        variant="conflict",
    )
    conflicting = publish_run_terminal_projection(tmp_path, conflict)
    with pytest.raises(ValueError, match="different terminal projection"):
        run_terminal_publication.publish_run_terminal_observation(
            tmp_path,
            CYCLE_ID,
            projection=conflict,
            projection_binding=conflicting["binding"],
        )


def test_terminal_projection_cannot_cross_cycle_boundary(
    tmp_path: Path,
) -> None:
    draft = _failed_projection(tmp_path, cycle_id=CYCLE_ID)
    source = _initialize_live_run(
        tmp_path, cycle_id=CYCLE_ID, projection=draft
    )
    _initialize_live_run(
        tmp_path, cycle_id="cycle-2", projection=draft
    )
    projection = _failed_projection(
        tmp_path,
        cycle_id=CYCLE_ID,
        monitor_event_id=str(source["event_id"]),
    )
    published = publish_run_terminal_projection(tmp_path, projection)

    with pytest.raises(ValueError, match="another cycle"):
        run_terminal_publication.publish_run_terminal_observation(
            tmp_path,
            "cycle-2",
            projection=projection,
            projection_binding=published["binding"],
        )


def test_concurrent_terminal_decisions_keep_one_run_assignment(
    tmp_path: Path,
) -> None:
    first_draft = _failed_projection(tmp_path)
    second_draft = _failed_projection(tmp_path, variant="concurrent")
    source = _initialize_live_run(
        tmp_path,
        projection=[first_draft, second_draft],
    )
    projections = [
        _failed_projection(
            tmp_path, monitor_event_id=str(source["event_id"])
        ),
        _failed_projection(
            tmp_path,
            monitor_event_id=str(source["event_id"]),
            variant="concurrent",
        ),
    ]
    publications = [
        publish_run_terminal_projection(tmp_path, projection)
        for projection in projections
    ]

    def publish(index: int) -> str:
        try:
            run_terminal_publication.publish_run_terminal_observation(
                tmp_path,
                CYCLE_ID,
                projection=projections[index],
                projection_binding=publications[index]["binding"],
            )
        except ValueError as exc:
            assert "different terminal projection" in str(exc)
            return "conflict"
        return "published"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(publish, range(2)))
    assert outcomes == ["conflict", "published"]
    assert len(
        [
            event
            for event in read_events(tmp_path, CYCLE_ID)
            if event.get("observation_kind") == "run_terminal"
        ]
    ) == 1
