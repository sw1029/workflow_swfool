"""Typed state shared by the ordered progress-analysis stage pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class AnalysisContext:
    root: Path
    recent: int | None
    strict: bool
    policy: dict[str, Any]
    recurrence_threshold: int | None
    goal_productive_threshold: int | None
    root_axis_threshold: int | None
    feature_symbol_threshold: int | None
    terminal_quiescence_threshold: int | None
    terminal_escalation_threshold: int | None
    detection_only_streak_cap: int | None
    consolidation_streak_cap: int | None
    command_surface_threshold: int | None
    metadata_only_window: int | None
    write_registry: bool
    finalized_cycle_id: str | None
    state: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None


class AnalysisStage(Protocol):
    """One ordered, side-effect-bounded analysis strategy."""

    name: str

    def run(self, context: AnalysisContext) -> None: ...


class ContextBoundStage:
    """Expose explicit context fields to converted stage logic."""

    context: AnalysisContext

    def bind(self, context: AnalysisContext) -> None:
        self.context = context

    @property
    def root(self) -> Path:
        return self.context.root

    @property
    def recent(self) -> int | None:
        return self.context.recent

    @property
    def strict(self) -> bool:
        return self.context.strict

    @property
    def policy(self) -> dict[str, Any]:
        return self.context.policy

    @property
    def recurrence_threshold(self) -> int | None:
        return self.context.recurrence_threshold

    @property
    def goal_productive_threshold(self) -> int | None:
        return self.context.goal_productive_threshold

    @property
    def root_axis_threshold(self) -> int | None:
        return self.context.root_axis_threshold

    @property
    def feature_symbol_threshold(self) -> int | None:
        return self.context.feature_symbol_threshold

    @property
    def terminal_quiescence_threshold(self) -> int | None:
        return self.context.terminal_quiescence_threshold

    @property
    def terminal_escalation_threshold(self) -> int | None:
        return self.context.terminal_escalation_threshold

    @property
    def detection_only_streak_cap(self) -> int | None:
        return self.context.detection_only_streak_cap

    @property
    def consolidation_streak_cap(self) -> int | None:
        return self.context.consolidation_streak_cap

    @property
    def command_surface_threshold(self) -> int | None:
        return self.context.command_surface_threshold

    @property
    def metadata_only_window(self) -> int | None:
        return self.context.metadata_only_window

    @property
    def write_registry(self) -> bool:
        return self.context.write_registry

    @property
    def finalized_cycle_id(self) -> str | None:
        return self.context.finalized_cycle_id

    @property
    def state(self) -> dict[str, Any]:
        return self.context.state
