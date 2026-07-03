from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RuntimeCache:
    domain_adapter_module: Any | None = None
    quality_metrics_module: Any | None = None


@dataclass
class EvaluationContext:
    root: Path
    args: Any
    registry_path: Path
    artifact_paths: list[Path] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    domain_adapter: Any | None = None
    domain_adapter_path: str | None = None
    domain_adapter_error: str | None = None


@dataclass
class EvaluationState:
    registry_rows: list[dict[str, Any]] = field(default_factory=list)
    gate_inputs: list[dict[str, Any]] = field(default_factory=list)
    quality_vector: dict[str, Any] = field(default_factory=dict)
    evidence_paths: list[str] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)

    def add_gate(self, name: str, gate: dict[str, Any]) -> None:
        self.gate_inputs.append({"name": name, **gate})

    def add_finding(self, finding: dict[str, Any]) -> None:
        self.findings.append(finding)
