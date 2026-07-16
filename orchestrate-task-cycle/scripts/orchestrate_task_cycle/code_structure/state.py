from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuditState:
    records: list[dict[str, Any]]
    scanned: list[dict[str, Any]]
    exempt: list[dict[str, Any]]
    oversize: list[dict[str, Any]]
    hard_items: list[dict[str, Any]]
    soft_items: list[dict[str, Any]]
    metrics: dict[str, Any]
    findings: list[dict[str, Any]]
    refactor_required: bool
    primary: dict[str, Any] | None
