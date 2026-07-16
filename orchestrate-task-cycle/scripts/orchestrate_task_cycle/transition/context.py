from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


Finding = dict[str, Any]


@dataclass
class ValidationContext:
    context: dict[str, Any]
    stage: dict[str, Any]
    transition: str
    routing: dict[str, Any] | None = None
    workflow_mode: str = "normal"
    findings: list[Finding] = field(default_factory=list)

    @property
    def routing_source(self) -> dict[str, Any]:
        return self.routing if isinstance(self.routing, dict) else {}

    @property
    def target_step(self) -> str:
        return self.transition.removeprefix("pre_")

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        evidence: Any = None,
    ) -> None:
        item: Finding = {
            "severity": severity,
            "code": code,
            "message": message,
        }
        if evidence is not None:
            item["evidence"] = evidence
        self.findings.append(item)

    def result(self) -> dict[str, Any]:
        status = "ok"
        if any(item["severity"] == "block" for item in self.findings):
            status = "block"
        elif self.findings:
            status = "warn"
        return {
            "status": status,
            "transition": self.transition,
            "workflow_mode": self.workflow_mode,
            "findings": self.findings,
        }


class ValidationStage(Protocol):
    def __call__(self, state: ValidationContext) -> None: ...
