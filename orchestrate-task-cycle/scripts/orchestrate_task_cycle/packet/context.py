from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


RouteSelector = Callable[[str, dict[str, Any] | None], dict[str, Any]]


@dataclass(frozen=True)
class PacketBuildContext:
    context: dict[str, Any]
    stage: dict[str, Any]
    model_effort_policy: dict[str, Any]
    model_effort_profile_path: Path
    routing_reference_path: Path
    route_selector: RouteSelector
    output_delta_contract_candidates: tuple[str, ...]

    def route(self, profile_id: str) -> dict[str, Any]:
        request = routing_request_for(profile_id, self.context, self.stage)
        return self.route_selector(profile_id, request)


def load_json(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    if path_value == "-":
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    stripped = path_value.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    path = Path(path_value)
    try:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            return json.loads(raw) if raw.strip() else {}
    except OSError:
        pass
    return json.loads(stripped)


def deep_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def routing_request_for(
    profile_id: str,
    context: dict[str, Any],
    stage: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {"signals": {}}
    for source in (context, stage):
        routing = (
            source.get("model_effort_routing")
            if isinstance(source.get("model_effort_routing"), dict)
            else {}
        )
        model_bindings = (
            routing.get("model_bindings")
            if isinstance(routing.get("model_bindings"), dict)
            else {}
        )
        if model_bindings:
            merged.setdefault("model_bindings", {}).update(model_bindings)
        profiles = (
            routing.get("profiles") if isinstance(routing.get("profiles"), dict) else {}
        )
        profile_request = (
            profiles.get(profile_id)
            if isinstance(profiles.get(profile_id), dict)
            else {}
        )
        profile_signals = (
            profile_request.get("signals")
            if isinstance(profile_request.get("signals"), dict)
            else {}
        )
        merged["signals"].update(profile_signals)
        profile_evidence = (
            profile_request.get("signal_evidence")
            if isinstance(profile_request.get("signal_evidence"), dict)
            else {}
        )
        if profile_evidence:
            merged.setdefault("signal_evidence", {}).update(profile_evidence)
        for field in (
            "final_direction_ownership",
            "request_max",
            "max_escalation_reason",
            "prior_tier5_evidence",
            "agent_count",
        ):
            if field in profile_request:
                merged[field] = profile_request[field]
    return merged


def goal_truth(context: dict[str, Any]) -> list[str]:
    used = deep_get(context, "agent_goal", "used_goal_truth")
    if isinstance(used, list):
        return [str(item) for item in used]
    return []


def available_goal_truth(context: dict[str, Any]) -> list[str]:
    available = deep_get(context, "agent_goal", "available_goal_truth")
    if isinstance(available, list):
        return [str(item) for item in available]
    files = deep_get(context, "agent_goal", "goal_truth_files")
    if isinstance(files, dict):
        return [
            str(item.get("path"))
            for item in files.values()
            if isinstance(item, dict) and item.get("exists")
        ]
    return []


def active_advice(context: dict[str, Any]) -> list[dict[str, Any]]:
    value = deep_get(context, "external_advice", "active_files")
    if isinstance(value, list):
        workspace = context.get("workspace")
        root = Path(str(workspace)) if workspace else None
        return [enrich_advice(item, root) for item in value if isinstance(item, dict)]
    return []


def output_delta_contract_packet(
    context: dict[str, Any],
    candidates: tuple[str, ...] = (
        ".task/contracts/output_delta_contract.json",
        ".agent_goal/output_delta_contract.json",
    ),
) -> dict[str, Any] | None:
    workspace = context.get("workspace")
    if not workspace:
        return None
    root = Path(str(workspace))
    for relative in candidates:
        path = root / relative
        if not path.is_file():
            continue
        try:
            contract = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"status": "malformed", "path": relative}
        if not isinstance(contract, dict):
            return {"status": "malformed", "path": relative}
        provider = (
            contract.get("output_delta_provider")
            if isinstance(contract.get("output_delta_provider"), dict)
            else {}
        )
        return {
            "status": "available",
            "path": relative,
            "output_layer_paths": contract.get("output_layer_paths") or [],
            "positive_evidence_predicate": contract.get("positive_evidence_predicate"),
            "provider_kind": provider.get("kind"),
            "provider_entry": provider.get("entry"),
            "gate_contract": "Call scripts/output_delta_contract.py before qualitative_review/derive when artifact paths are available.",
        }
    return {"status": "not_applicable_no_contract"}


def section_lines(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return sections


def section_text(lines: list[str], limit: int = 700) -> str:
    value = " ".join(line.strip() for line in lines if line.strip())
    if len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def section_bullets(lines: list[str], limit: int = 8) -> list[str]:
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            values.append(stripped[2:].strip())
        elif values and not stripped.startswith("#"):
            values[-1] = f"{values[-1]} {stripped}"
    return values[:limit]


def parse_advice_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            break
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        metadata[key.strip()] = value.strip()
    sections = section_lines(text)
    return {
        "advice_id": metadata.get("advice_id"),
        "status": metadata.get("status"),
        "not_goal_truth": metadata.get("not_goal_truth"),
        "raw_source_path": metadata.get("raw_source_path"),
        "scope": metadata.get("scope"),
        "priority": metadata.get("priority"),
        "source_label": metadata.get("source_label"),
        "summary": section_text(sections.get("Summary", [])),
        "actionable_directives": section_bullets(
            sections.get("Actionable Directives", [])
        ),
        "application_gates": section_bullets(sections.get("Application Gates", [])),
        "evidence_to_mark_applied": section_bullets(
            sections.get("Evidence To Mark Applied", []), limit=5
        ),
        "exclusions": section_bullets(sections.get("Exclusions", []), limit=5),
    }


def enrich_advice(item: dict[str, Any], root: Path | None) -> dict[str, Any]:
    enriched = dict(item)
    path_value = item.get("path")
    if not path_value or root is None:
        return enriched
    path = root / str(path_value)
    if not path.is_file():
        return enriched
    parsed = parse_advice_document(path)
    for key, value in parsed.items():
        if value:
            enriched[key] = value
    if parsed.get("source_label"):
        enriched["title"] = parsed["source_label"]
    return enriched


def authority_policy(stage: dict[str, Any]) -> str:
    value = (
        stage.get("authority_policy")
        or deep_get(stage, "packet", "authority_policy")
        or deep_get(stage, "routing", "authority_policy")
    )
    return str(value) if value else "default_current_agent_permissions"


def task_summary(context: dict[str, Any]) -> str:
    task = context.get("task_md") if isinstance(context.get("task_md"), dict) else {}
    if not task or not task.get("exists"):
        return "task.md absent"
    title = task.get("title") or "task.md"
    return f"{task.get('path', 'task.md')} ({title})"


def counts(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_miss_active": deep_get(context, "task_state", "task_miss", "active_count")
        or 0,
        "candidate_count": deep_get(context, "task_state", "candidate_task", "count")
        or 0,
        "task_pack_count": deep_get(context, "task_state", "task_pack", "count") or 0,
        "task_pack_active": deep_get(context, "task_state", "task_pack", "active_count")
        or 0,
        "issue_active": deep_get(context, "issue", "active_count") or 0,
        "schema_count": deep_get(context, "schema", "count") or 0,
        "contract_count": deep_get(context, "contract", "count") or 0,
        "agent_log_count": deep_get(context, "agent_log", "markdown_count") or 0,
        "external_advice_active": deep_get(context, "external_advice", "active_count")
        or 0,
        "validation_set_count": deep_get(context, "validation_assets", "sets", "count")
        or 0,
        "cycle_validation_set_count": deep_get(
            context, "task_state", "validation_set", "count"
        )
        or 0,
        "session_audit_count": deep_get(context, "session_audit", "valid_count") or 0,
    }
