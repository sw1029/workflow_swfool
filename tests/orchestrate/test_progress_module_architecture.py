from __future__ import annotations

import ast
from pathlib import Path
import sys


sys.dont_write_bytecode = True
SKILLS_ROOT = Path(__file__).resolve().parents[2]
for package_root in (
    SKILLS_ROOT / "orchestrate-task-cycle" / "scripts",
    SKILLS_ROOT / "record-agent-work-log" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from orchestrate_task_cycle.progress import api, compat  # noqa: E402
from orchestrate_task_cycle.progress.analysis import (  # noqa: E402
    BaseProgressLoopAnalyzer,
    ProgressLoopAnalyzer,
    analyze,
)
from orchestrate_task_cycle.progress.analysis_pipeline import (  # noqa: E402
    default_stages,
)
from orchestrate_task_cycle.progress.constant_registry import (  # noqa: E402
    CONSTANTS_BY_NAME,
    public_constant_names,
    validate_constant_registry,
)


PROGRESS_ROOT = (
    SKILLS_ROOT
    / "orchestrate-task-cycle"
    / "scripts"
    / "orchestrate_task_cycle"
    / "progress"
)
LEGACY_API_SYMBOLS = {
    "BaseProgressLoopAnalyzer",
    "EvidenceCollectionMixin",
    "FindingBuilderMixin",
    "GateEvaluationMixin",
    "ProgressAggregationMixin",
    "ProgressLoopAnalyzer",
    "ResultBuilderMixin",
    "RootMetricMixin",
    "QUALITY_DELTA_KEYS",
    "analyze",
    "candidate_files",
    "coverage_quality_delta_gate",
    "gate_allowed_dispositions",
    "gate_constrains_disposition",
    "prepare_feature_symbol_registry_update",
    "terminal_escalation_gate",
    "validate_constant_registry",
}


def test_progress_modules_are_explicit_and_structurally_bounded() -> None:
    for path in PROGRESS_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert len(source.splitlines()) <= 500, path
        assert "import_module" not in source, path
        assert "spec_from_file_location" not in source, path
        assert "sys.path" not in source, path
        tree = ast.parse(source)
        assert not any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "*" for alias in node.names)
            for node in ast.walk(tree)
        ), path
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert node.end_lineno is not None
                assert node.end_lineno - node.lineno + 1 <= 140, (path, node.name)


def test_analyzer_uses_the_declared_strategy_order_without_mixin_mro() -> None:
    assert ProgressLoopAnalyzer.__bases__ == (BaseProgressLoopAnalyzer,)
    assert [stage.name for stage in default_stages()] == [
        "evidence",
        "aggregation",
        "root_metrics",
        "gates",
        "findings",
        "result",
    ]


def test_explicit_api_and_compatibility_surface_retain_legacy_symbols() -> None:
    assert LEGACY_API_SYMBOLS <= set(api.__all__)
    assert api.__all__ == compat.__all__
    assert all(hasattr(api, name) and hasattr(compat, name) for name in api.__all__)


def test_constant_registry_uses_the_static_runtime_map() -> None:
    result = validate_constant_registry()
    assert result["status"] == "ok"
    assert public_constant_names() == sorted(CONSTANTS_BY_NAME)
    assert result["runtime_constant_count"] == len(CONSTANTS_BY_NAME) == 35


def test_analyze_wrapper_and_composed_analyzer_are_behavior_equivalent(
    tmp_path: Path,
) -> None:
    wrapper = analyze(tmp_path, None, False)
    composed = ProgressLoopAnalyzer(tmp_path, None, False).run()
    wrapper.pop("checked_at")
    composed.pop("checked_at")
    assert wrapper == composed
    assert not list(tmp_path.iterdir())
