from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .collections import (
    collect_fields,
    event_malformed_reasons,
    evidence_paths,
    latest_value,
    long_run_events,
    values,
)
from .constants import AXIS_FIELDS, PART_L_M_FIELDS, VERDICT_AXIS_FIELDS
from .finalization import (
    FinalizationInputs,
    FinalizationResult,
    resolve_finalization,
)


@dataclass(frozen=True)
class DashboardInputs:
    events: list[dict[str, Any]]
    current: dict[str, Any]
    current_load_status: str
    cycle_id: str
    workspace_root: Path | None = None


@dataclass
class DashboardState:
    inputs: DashboardInputs
    latest_by_step: dict[str, dict[str, Any]] = field(default_factory=dict)
    valid_events: list[dict[str, Any]] = field(default_factory=list)
    malformed_events: list[dict[str, Any]] = field(default_factory=list)
    current_count: int | None = None
    ledger_latest_event_id: str = ""
    current_latest_event_id: str = ""
    snapshot_status: str = "missing"
    task_ids: list[str] = field(default_factory=list)
    issue_ids: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    observed_validation: str = "not_run"
    normalized_observed_validation: str = "not_run"
    observed_progress: str = "not_run"
    task_id: str = "unknown-task"
    progress_axes: list[dict[str, Any]] = field(default_factory=list)
    verdict_axis_history: list[dict[str, Any]] = field(default_factory=list)
    finalization: FinalizationResult | None = None
    summary: dict[str, Any] = field(default_factory=dict)


class DashboardStage(Protocol):
    def apply(self, state: DashboardState) -> None: ...


class EventClassificationStage:
    def apply(self, state: DashboardState) -> None:
        seen_event_ids: set[str] = set()
        for event in state.inputs.events:
            reasons = event_malformed_reasons(event, state.inputs.cycle_id)
            event_id = str(event.get("event_id") or "").strip()
            if event_id and event_id in seen_event_ids:
                reasons.append("duplicate_event_id")
            if event_id:
                seen_event_ids.add(event_id)
            if reasons:
                state.malformed_events.append(
                    {**event, "_dashboard_malformed_reasons": reasons}
                )
                continue
            state.valid_events.append(event)
            state.latest_by_step[str(event["step"])] = event


class SnapshotStatusStage:
    def apply(self, state: DashboardState) -> None:
        current = state.inputs.current
        value = current.get("event_count")
        state.current_count = (
            value if isinstance(value, int) and not isinstance(value, bool) else None
        )
        events = state.inputs.events
        state.ledger_latest_event_id = (
            str(events[-1].get("event_id") or "").strip() if events else ""
        )
        current_latest = (
            current.get("latest_event")
            if isinstance(current.get("latest_event"), dict)
            else {}
        )
        state.current_latest_event_id = str(
            current_latest.get("event_id") or ""
        ).strip()
        if state.inputs.current_load_status != "loaded":
            state.snapshot_status = state.inputs.current_load_status
        elif state.current_count != len(events):
            state.snapshot_status = "stale"
        elif (
            state.ledger_latest_event_id or state.current_latest_event_id
        ) and state.ledger_latest_event_id != state.current_latest_event_id:
            state.snapshot_status = "stale"
        else:
            state.snapshot_status = "current"


class EvidenceCollectionStage:
    def apply(self, state: DashboardState) -> None:
        events = state.valid_events
        state.task_ids = collect_fields(
            events, ("task_id", "completed_task_id", "next_task_id")
        )
        state.issue_ids = collect_fields(
            events,
            (
                "issue_id",
                "issue_ids",
                "issue_path",
                "issue_paths",
                "issue_url",
                "issue_urls",
            ),
        )
        state.changed_files = collect_fields(events, ("changed_files",))
        state.blockers = collect_fields(events, ("blockers",))
        state.artifacts = evidence_paths(events)
        state.observed_validation = (
            str(latest_value(events, "validation_verdict", default="not_run"))
            .strip()
            .lower()
        )
        state.normalized_observed_validation = {
            "complete": "passed",
            "pass": "passed",
            "success": "passed",
            "ok": "passed",
        }.get(state.observed_validation, state.observed_validation)
        state.observed_progress = str(
            latest_value(events, "progress_verdict", default="not_run")
        )
        state.task_id = str(
            latest_value(events, "task_id", "completed_task_id", default="unknown-task")
        )
        state.progress_axes = [
            {"step": event.get("step"), field: event[field]}
            for event in events
            for field in AXIS_FIELDS
            if field in event and event[field] not in (None, "", [], {})
        ]
        state.verdict_axis_history = [
            {"step": event.get("step"), "axis": field, "verdict": event[field]}
            for event in events
            for field in VERDICT_AXIS_FIELDS
            if field in event and event[field] not in (None, "", [], {})
        ]


class FinalizationProjectionStage:
    def apply(self, state: DashboardState) -> None:
        state.finalization = resolve_finalization(
            FinalizationInputs(
                valid_events=state.valid_events,
                cycle_id=state.inputs.cycle_id,
                workspace_root=state.inputs.workspace_root,
                observed_validation=state.observed_validation,
                normalized_observed_validation=state.normalized_observed_validation,
                observed_progress=state.observed_progress,
            ),
            state.verdict_axis_history,
        )


def _unchanged_refs(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs: dict[tuple[str, str], dict[str, str]] = {}
    for event in events:
        for ref in event.get("unchanged_refs") or []:
            if not isinstance(ref, dict):
                continue
            path = str(ref.get("path") or "").strip()
            sha256 = str(ref.get("sha256") or "").strip()
            if path and sha256:
                refs[(path, sha256)] = {"path": path, "sha256": sha256}
    return list(refs.values())


def _dashboard_findings(state: DashboardState) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if state.snapshot_status != "current":
        findings.append(
            {
                "severity": "warn",
                "code": "current_stage_snapshot_not_current",
                "status": state.snapshot_status,
            }
        )
    if state.malformed_events:
        findings.append(
            {
                "severity": "warn",
                "code": "malformed_or_noncanonical_events",
                "count": len(state.malformed_events),
            }
        )
    if not state.inputs.events:
        findings.append({"severity": "warn", "code": "empty_cycle_ledger"})
    elif not state.valid_events:
        findings.append({"severity": "warn", "code": "no_valid_cycle_events"})
    finalization = state.finalization
    assert finalization is not None
    findings.extend(
        {
            "severity": "block",
            "code": str(item["code"]),
            "message": str(item["message"]),
            **(
                {"evidence": item["evidence"]}
                if item.get("evidence") is not None
                else {}
            ),
        }
        for item in finalization.errors
    )
    return findings


class DashboardResultStage:
    def apply(self, state: DashboardState) -> None:
        finalization = state.finalization
        assert finalization is not None
        events = state.valid_events
        unchanged_refs = _unchanged_refs(events)
        lineage_findings = [
            {"step": event.get("step"), field: event[field]}
            for event in events
            for field in PART_L_M_FIELDS
            if field in event and event[field] not in (None, False, "", [], {})
        ]
        commit_results = [
            {
                "step": event.get("step"),
                "commit_role": event.get("commit_role"),
                "commit_status": event.get("commit_status") or event.get("status"),
                "commit_hash": event.get("commit_hash"),
                "commit_subject": event.get("commit_subject"),
            }
            for event in events
            if event.get("step") in {"commit", "closeout_commit"}
        ]
        issue_results = [
            {
                "issue_packet_id": event.get("issue_packet_id"),
                "issue_status": event.get("issue_status") or event.get("status"),
                "issue_ids": event.get("issue_ids") or values(event.get("issue_id")),
            }
            for event in events
            if event.get("step") == "issue"
        ]
        findings = _dashboard_findings(state)
        projection = finalization.authoritative_projection
        receipt = finalization.receipt
        dashboard_status = (
            "block" if finalization.errors else "rendered" if not findings else "warn"
        )
        state.summary = {
            "format_version": 1,
            "step": "dashboard",
            "cycle_id": state.inputs.cycle_id,
            "task_id": state.task_id,
            "dashboard_status": dashboard_status,
            "event_count": len(state.inputs.events),
            "valid_event_count": len(events),
            "current_stage_event_count": state.current_count,
            "ledger_latest_event_id": state.ledger_latest_event_id or None,
            "current_stage_latest_event_id": state.current_latest_event_id or None,
            "snapshot_status": state.snapshot_status,
            "latest_event": events[-1] if events else {},
            "latest_by_step": state.latest_by_step,
            "malformed_events": state.malformed_events,
            "task_ids": state.task_ids,
            "changed_files": state.changed_files,
            "artifacts": state.artifacts,
            "issue_ids": state.issue_ids,
            "issue_results": issue_results,
            "commit_results": commit_results,
            "long_runs": long_run_events(events),
            "validation_verdict": finalization.validation_verdict,
            "progress_verdict": finalization.progress_verdict,
            "progress_axes": state.progress_axes,
            "verdict_axes": finalization.verdict_axes,
            "verdict_axis_history": state.verdict_axis_history,
            "authoritative_final": projection.get("authoritative_final")
            if projection
            else None,
            "authoritative_projection": projection,
            "finalization_receipt": receipt,
            "finalization_consumption": (
                {
                    field: receipt[field]
                    for field in (
                        "finalization_token",
                        "attempt_id",
                        "attempt_revision",
                        "authoritative_projection_id",
                        "authoritative_projection_digest",
                        "receipt_hash",
                    )
                }
                if receipt
                else None
            ),
            "unchanged_ref_count": len(unchanged_refs),
            "unchanged_refs": unchanged_refs[-50:],
            "lineage_findings": lineage_findings,
            "blockers": state.blockers,
            "findings": findings,
        }


DEFAULT_DASHBOARD_PIPELINE: tuple[DashboardStage, ...] = (
    EventClassificationStage(),
    SnapshotStatusStage(),
    EvidenceCollectionStage(),
    FinalizationProjectionStage(),
    DashboardResultStage(),
)


@dataclass(frozen=True)
class DashboardBuilder:
    stages: tuple[DashboardStage, ...] = DEFAULT_DASHBOARD_PIPELINE

    def build(self, inputs: DashboardInputs) -> dict[str, Any]:
        state = DashboardState(inputs=inputs)
        for stage in self.stages:
            stage.apply(state)
        return state.summary
