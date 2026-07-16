from __future__ import annotations

from typing import Any

from .constants import FIELD_ORDER


def render_markdown(report: dict[str, Any]) -> str:
    fields = report["fields"]
    lines: list[str] = []
    for field in FIELD_ORDER:
        lines.append(f"{field}:")
        for item in fields.get(field, ["not_run"]):
            lines.append(f"- {item}")
        lines.append("")
    extra = report.get("extra") or {}
    if extra:
        lines.append("추가 참고:")
        for key, value in extra.items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
