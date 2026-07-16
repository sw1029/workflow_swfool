from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FindingCollector:
    findings: list[dict[str, Any]] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str, evidence: Any | None = None) -> None:
        finding: dict[str, Any] = {
            "severity": severity,
            "code": code,
            "message": message,
        }
        if evidence is not None:
            finding["evidence"] = evidence
        self.findings.append(finding)

    def extend(self, findings: list[dict[str, Any]]) -> None:
        self.findings.extend(finding for finding in findings if isinstance(finding, dict))


@dataclass
class PacketBuilder:
    packet: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> "PacketBuilder":
        self.packet[key] = value
        return self

    def update(self, values: dict[str, Any]) -> "PacketBuilder":
        self.packet.update(values)
        return self

    def attach_findings(self, findings: list[dict[str, Any]]) -> "PacketBuilder":
        if findings:
            self.packet["findings"] = findings
        return self

    def build(self) -> dict[str, Any]:
        return dict(self.packet)
