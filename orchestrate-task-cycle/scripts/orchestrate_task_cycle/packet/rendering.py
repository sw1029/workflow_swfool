from __future__ import annotations

from typing import Any


def render_markdown(packet: dict[str, Any]) -> str:
    lines = [f"# Subskill Packet: {packet['target']}", ""]
    for key in (
        "skill",
        "mode",
        "workspace",
        "task",
        "authority_policy",
        "routing_reference",
    ):
        if key in packet:
            lines.append(f"- {key}: {packet[key]}")
    lines.append("")
    lines.append("## Available Goal Truth")
    available = packet.get("available_goal_truth") or []
    if available:
        lines.extend(f"- {item}" for item in available)
    else:
        lines.append("- 없음")
    lines.append("")
    lines.append("## Used Goal Truth")
    gt = packet.get("used_goal_truth") or []
    if gt:
        lines.extend(f"- {item}" for item in gt)
    else:
        lines.append("- 없음")
    lines.append("")
    lines.append("## Non-GT Direction Advice")
    advice = packet.get("used_advice") or []
    if advice:
        for item in advice:
            if isinstance(item, dict):
                lines.append(f"### {item.get('advice_id') or item.get('path')}")
                lines.append(f"- path: {item.get('path')}")
                lines.append(
                    f"- title: {item.get('title') or item.get('source_label') or 'external advice'}"
                )
                for key in (
                    "status",
                    "priority",
                    "scope",
                    "not_goal_truth",
                    "raw_source_path",
                ):
                    if item.get(key):
                        lines.append(f"- {key}: {item.get(key)}")
                if item.get("summary"):
                    lines.append(f"- summary: {item.get('summary')}")
                for key in (
                    "actionable_directives",
                    "application_gates",
                    "evidence_to_mark_applied",
                    "exclusions",
                ):
                    values = item.get(key)
                    if isinstance(values, list) and values:
                        lines.append(f"- {key}:")
                        lines.extend(f"  - {value}" for value in values)
            else:
                lines.append(f"- {item}")
    else:
        lines.append("- 없음")
    for section_key in (
        "routing",
        "task_pack_packet",
        "required_inputs",
        "required_outputs",
        "selection_rules",
        "commit_gates",
        "forbidden_bypasses",
        "required_fields_order",
        "context_counts",
    ):
        value = packet.get(section_key)
        if not value:
            continue
        title = section_key.replace("_", " ").title()
        lines.extend(["", f"## {title}"])
        if isinstance(value, dict):
            lines.extend(f"- {key}: {item}" for key, item in value.items())
        elif isinstance(value, list):
            lines.extend(f"- {item}" for item in value)
        else:
            lines.append(f"- {value}")
    return "\n".join(lines).rstrip() + "\n"
