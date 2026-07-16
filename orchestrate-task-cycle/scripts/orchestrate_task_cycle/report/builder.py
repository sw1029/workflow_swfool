from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..result_contract.finalization import VERDICT_AXES, projection_conclusions
from .completion import (
    completion_evidence_findings,
    next_task_line,
    report_closure_records,
    report_closure_steps,
    report_input_findings,
    task_line,
)
from .constants import FIELD_ORDER
from .evidence import (
    advice_docs,
    blockers,
    changed_files,
    command_results,
    goal_truth,
    long_run_status_lines,
    model_effort_routing_lines,
    progress_axes,
    progress_verdict,
    report_evidence_paths,
    validation_verdict,
)
from .events import event_value
from .finalization import finalization_consumption, finalization_projection
from .io import deep_get


@dataclass(frozen=True)
class ReportInputs:
    context: dict[str, Any]
    stage: dict[str, Any]
    validation: dict[str, Any]
    progress: dict[str, Any]
    commit: dict[str, Any]
    closeout_commit: dict[str, Any]


@dataclass
class ReportState:
    inputs: ReportInputs
    observed_validation: str = "not_run"
    observed_progress: str = "not_run"
    validation_verdict: str = "not_run"
    progress_verdict: str = "not_run"
    blockers: list[str] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    authoritative_projection: dict[str, Any] | None = None
    finalization_receipt: dict[str, Any] | None = None
    completion_candidate: bool = False
    used_goal_truth: list[str] = field(default_factory=list)
    used_advice: list[str] = field(default_factory=list)
    routing_summary: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    axes: list[str] = field(default_factory=list)
    verdict_axes: dict[str, Any] = field(default_factory=dict)
    evidence_paths: list[str] = field(default_factory=list)
    task_id: Any = "unknown-task"
    next_task_id: Any = "unknown-task"
    selected_task_source: str = ""
    closure_records: list[dict[str, Any]] = field(default_factory=list)
    closure_steps: list[str] = field(default_factory=list)
    completion_status: str = "not_complete"
    fields: dict[str, list[str]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class ReportStage(Protocol):
    def apply(self, state: ReportState) -> None: ...


class FinalizedTruthStage:
    def apply(self, state: ReportState) -> None:
        data = state.inputs
        state.observed_validation = validation_verdict(data.validation, data.stage)
        state.observed_progress = progress_verdict(
            data.validation, data.stage, data.progress
        )
        state.blockers = blockers(
            data.context, data.stage, data.validation, data.progress
        )
        state.findings = report_input_findings(data.stage, data.validation)
        projection, receipt, finalization_findings = finalization_projection(
            data.context,
            data.stage,
            data.validation,
        )
        state.authoritative_projection = projection
        state.finalization_receipt = receipt
        state.findings.extend(finalization_findings)
        if projection is not None:
            state.validation_verdict, state.progress_verdict = projection_conclusions(
                projection
            )
            if state.observed_validation not in {
                "not_run",
                state.validation_verdict,
            } or state.observed_progress not in {
                "not_run",
                state.progress_verdict,
            }:
                state.findings.append(
                    {
                        "severity": "block",
                        "code": "authoritative_projection_report_divergence",
                        "message": (
                            "Report inputs disagree with the receipt-bound authoritative "
                            "finalization projection."
                        ),
                        "evidence": {
                            "observed_validation_verdict": state.observed_validation,
                            "observed_progress_verdict": state.observed_progress,
                            "projected_validation_verdict": state.validation_verdict,
                            "projected_progress_verdict": state.progress_verdict,
                        },
                    }
                )
        else:
            state.validation_verdict = (
                "passed"
                if state.observed_validation == "complete"
                else state.observed_validation
            )
            state.progress_verdict = state.observed_progress
            if (
                state.validation_verdict in {"passed", "pass", "success"}
                or state.progress_verdict == "advanced"
            ):
                state.findings.append(
                    {
                        "severity": "block",
                        "code": "finalization_receipt_missing",
                        "message": (
                            "A positive report conclusion requires the current verified "
                            "finalization receipt and projection."
                        ),
                    }
                )


class EvidenceProjectionStage:
    def apply(self, state: ReportState) -> None:
        data = state.inputs
        projection = state.authoritative_projection
        state.completion_candidate = (
            state.validation_verdict in {"complete", "passed", "pass", "success"}
            and state.progress_verdict == "advanced"
            and not state.blockers
            and not state.findings
            and projection is not None
            and state.finalization_receipt is not None
            and projection.get("authoritative_final") == "success"
        )
        state.used_goal_truth = goal_truth(data.context, data.stage, data.validation)
        state.used_advice = advice_docs(data.context, data.stage, data.validation)
        state.routing_summary = model_effort_routing_lines(
            data.context, data.stage
        ) or ["not_recorded"]
        state.changed_files = changed_files(
            data.context, data.stage, data.validation, data.commit
        )
        state.commands = command_results(data.validation, data.stage)
        state.axes = progress_axes(data.validation, data.stage)
        state.verdict_axes = (
            {axis: projection[axis] for axis in VERDICT_AXES}
            if projection is not None
            else {}
        )
        if projection is not None and state.axes == ["not_recorded"]:
            state.axes = [
                f"{axis}: {str(projection[axis].get('status') or 'unknown')}"
                for axis in VERDICT_AXES
            ]
        state.evidence_paths = report_evidence_paths(
            data.context,
            data.stage,
            data.validation,
            data.progress,
            data.commit,
            data.closeout_commit,
        )
        state.task_id = (
            data.validation.get("completed_task_id")
            or data.stage.get("completed_task_id")
            or data.validation.get("task_id")
            or data.stage.get("task_id")
            or "unknown-task"
        )
        state.next_task_id = (
            data.stage.get("next_task_id")
            or deep_get(data.stage, "derive", "next_task_id")
            or event_value(
                data.stage, "next_task_id", ("report", "derive", "validate", "commit")
            )
            or "unknown-task"
        )
        state.selected_task_source = str(
            data.stage.get("selected_task_source")
            or event_value(data.stage, "selected_task_source", ("derive", "report"))
            or ""
        )
        state.closure_records = report_closure_records(data.stage, data.commit)
        state.closure_steps = sorted(report_closure_steps(data.stage, data.commit))


class CompletionStage:
    def apply(self, state: ReportState) -> None:
        data = state.inputs
        if state.completion_candidate:
            state.findings.extend(
                completion_evidence_findings(
                    stage=data.stage,
                    validation=data.validation,
                    commit=data.commit,
                    task_id=state.task_id,
                    next_task_id=state.next_task_id,
                    commands=state.commands,
                    axes=state.axes,
                    evidence_paths=state.evidence_paths,
                )
            )
        complete = state.completion_candidate and not state.findings
        state.completion_status = "complete_verified" if complete else "not_complete"
        state.fields = {
            "기준 GT": state.used_goal_truth or ["없음"],
            "비-GT 방향성 문서": state.used_advice or ["없음"],
            "주 진행 skill": ["$orchestrate-task-cycle"],
            "모델/effort 라우팅": state.routing_summary,
            "수행한 task": [task_line(data.context, data.validation, data.stage)],
            "변경한 파일": state.changed_files or ["없음"],
            "실행한 검증": state.commands,
            "validation verdict": [state.validation_verdict],
            "progress verdict": [state.progress_verdict],
            "progress axes": state.axes,
            "남은 blocker": state.blockers or ["없음"],
            "다음 task/방향성": [next_task_line(data.context, data.stage)],
            "완료 여부": [state.completion_status],
        }
        if data.validation.get("report_path"):
            state.extra["validation_report_path"] = data.validation["report_path"]
        long_run_lines = long_run_status_lines(data.context, data.stage)
        if long_run_lines:
            state.extra["long_running_execution"] = long_run_lines
        if data.commit:
            state.extra["implementation_commit"] = data.commit
        if data.closeout_commit:
            state.extra["closeout_commit"] = data.closeout_commit


DEFAULT_REPORT_PIPELINE: tuple[ReportStage, ...] = (
    FinalizedTruthStage(),
    EvidenceProjectionStage(),
    CompletionStage(),
)


@dataclass(frozen=True)
class ReportBuilder:
    stages: tuple[ReportStage, ...] = DEFAULT_REPORT_PIPELINE

    def build(self, inputs: ReportInputs) -> dict[str, Any]:
        state = ReportState(inputs=inputs)
        for stage in self.stages:
            stage.apply(state)
        return self._result(state)

    @staticmethod
    def _result(state: ReportState) -> dict[str, Any]:
        projection = state.authoritative_projection
        receipt = state.finalization_receipt
        return {
            "format_version": 1,
            "step": "report",
            "used_goal_truth": state.used_goal_truth,
            "used_advice": state.used_advice,
            "model_effort_routing": state.routing_summary,
            "task_id": state.task_id,
            "changed_files": state.changed_files,
            "commands": state.commands,
            "validation_verdict": state.validation_verdict,
            "progress_verdict": state.progress_verdict,
            "blockers": state.blockers,
            "progress_axes": state.axes,
            "verdict_contract_version": projection.get("verdict_contract_version")
            if projection
            else None,
            "verdict_axes": state.verdict_axes,
            "authoritative_final": projection.get("authoritative_final")
            if projection
            else None,
            "authoritative_projection": projection,
            "finalization_receipt": receipt,
            "finalization_consumption": finalization_consumption(receipt)
            if receipt
            else None,
            "next_task_id": state.next_task_id,
            "selected_task_source": state.selected_task_source,
            "closure_steps": state.closure_steps,
            "closure_records": state.closure_records,
            "completion_status": state.completion_status,
            "report_findings": state.findings,
            "evidence_paths": state.evidence_paths,
            "fields": state.fields,
            "extra": state.extra,
            "field_order": FIELD_ORDER,
        }
