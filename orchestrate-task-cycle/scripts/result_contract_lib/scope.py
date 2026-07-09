from __future__ import annotations

from typing import Any

from .accessors import deep_get, has_value, positive_count, value_for


def active_advice_present(data: dict[str, Any]) -> bool:
    candidates = [
        "active_advice_count",
        "external_advice_active",
        "context_counts.external_advice_active",
        "external_advice.active_count",
        "context.external_advice.active_count",
        "packet.context_counts.external_advice_active",
    ]
    if has_value(data, "used_advice"):
        return True
    for candidate in candidates:
        value = deep_get(data, candidate) if "." in candidate else data.get(candidate)
        if positive_count(value):
            return True
    for candidate in ("active_advice", "external_advice.active_files", "context.external_advice.active_files"):
        value = deep_get(data, candidate) if "." in candidate else data.get(candidate)
        if isinstance(value, list) and value:
            return True
    return False


def active_task_pack_present(data: dict[str, Any]) -> bool:
    candidates = [
        "task_pack_active",
        "context_counts.task_pack_active",
        "packet.context_counts.task_pack_active",
        "task_pack_packet",
        "packet.task_pack_packet",
    ]
    for candidate in candidates:
        value = deep_get(data, candidate) if "." in candidate else data.get(candidate)
        if positive_count(value) or (isinstance(value, dict) and value):
            return True
    return False


def task_pack_path_present(data: dict[str, Any]) -> bool:
    fields = ["changed_files", "artifacts", "artifact_paths", "evidence_paths", "report_paths", "tracked_artifacts"]
    for field in fields:
        value = deep_get(data, field) if "." in field else data.get(field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str) and ".task/task_pack/" in item:
                return True
    return False


def task_pack_in_scope(data: dict[str, Any]) -> bool:
    selected_source = str(value_for(data, "selected_task_source") or "").lower()
    return selected_source == "task_pack" or active_task_pack_present(data) or task_pack_path_present(data) or has_value(data, "task_pack_status")


def advice_handling_rationale_present(data: dict[str, Any]) -> bool:
    fields = [
        "advice_deferred_reason",
        "advice_rejected_reason",
        "advice_not_applicable_reason",
        "advice_handling_rationale",
        "external_advice_rationale",
        "used_advice_rationale",
        "advice_usage_deferred_reason",
    ]
    for field in fields:
        if has_value(data, field):
            return True
    return False


def add(findings: list[dict[str, Any]], severity: str, code: str, message: str, evidence: Any = None) -> None:
    item: dict[str, Any] = {"severity": severity, "code": code, "message": message}
    if evidence is not None:
        item["evidence"] = evidence
    findings.append(item)

