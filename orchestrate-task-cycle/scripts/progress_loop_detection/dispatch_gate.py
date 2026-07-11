from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import *
from .values import *
from .io_utils import *
from .provider import *

def provider_scale_dispatch_gate(value: dict[str, Any], coverage_gate: dict[str, Any]) -> dict[str, Any]:
    gate = first_mapping(
        value,
        (
            "provider_scale_dispatch_gate",
            "dispatch_gate",
            "anti_loop_progress_gate.provider_scale_dispatch_gate",
            "loop_breaker_packet.provider_scale_dispatch_gate",
            "result.provider_scale_dispatch_gate",
        ),
    )
    if gate:
        return gate
    provider_count = number_value(
        first_value(
            value,
            (
                "provider_request_count",
                "failure_autopsy.provider_request_count",
                "failure_autopsy_packet.provider_request_count",
                "run.provider_request_count",
                "result.provider_request_count",
            ),
        )
    )
    provider_count = provider_count or 0
    current = coverage_gate.get("current_quality_vector") if isinstance(coverage_gate.get("current_quality_vector"), dict) else {}
    current_all_zero = bool(current) and all((number_value(metric_value) or 0) <= 0 for metric_value in current.values())
    previous_all_zero = boolish(coverage_gate.get("previous_high_water_all_zero") or coverage_gate.get("high_water_all_zero"))
    dispatch_required = provider_count == 0 and previous_all_zero and current_all_zero
    return {
        "gate": "G-DISPATCH",
        "provider_request_count": provider_count,
        "high_water_all_zero": previous_all_zero and current_all_zero,
        "dispatch_required": dispatch_required,
        "hard_stop_required": dispatch_required,
        "constrains_disposition": dispatch_required,
        "allowed_dispositions": ["goal_productive", "terminal_blocked", "user_escalation"],
        "status": "block" if dispatch_required else "ok",
    }
