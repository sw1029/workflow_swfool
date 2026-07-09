#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import result_contract  # noqa: E402
from result_contract_lib.base import RuleContext, RuleRegistry, TargetContractRule  # noqa: E402
from result_contract_lib.registry import default_rule_registry  # noqa: E402


def empty_context(target: str) -> RuleContext:
    return RuleContext(
        target=target,
        result={},
        mode="block",
        findings=[],
        missing=[],
        require_context_field=lambda _field, _code, _message: None,
    )


def test_default_registry_has_one_owner_per_target() -> None:
    owners: dict[str, list[str]] = {}
    for rule in default_rule_registry().rules:
        assert isinstance(rule, TargetContractRule)
        for target in rule.targets:
            owners.setdefault(target, []).append(type(rule).__name__)

    assert owners
    assert all(len(rule_names) == 1 for rule_names in owners.values())
    assert owners["derive"] == ["DeriveRule"]
    assert owners["loopback_audit"] == ["LoopbackAuditRule"]
    assert owners["validate"] == ["CompletionValidationRule"]


def test_rule_registry_supports_focused_extension() -> None:
    visited: list[str] = []

    class FocusedRule(TargetContractRule):
        targets = frozenset({"focused"})

        def check(self, context: RuleContext) -> None:
            visited.append(context.target)

    registry = RuleRegistry([FocusedRule()])
    registry.validate(empty_context("other"))
    registry.validate(empty_context("focused"))

    assert visited == ["focused"]


def test_validator_accepts_an_injected_registry() -> None:
    class EmptyRule(TargetContractRule):
        targets = frozenset({"run"})

        def check(self, context: RuleContext) -> None:
            context.findings.append({"severity": "warn", "code": "injected", "message": "injected"})

    validator = result_contract.ResultContractValidator(RuleRegistry([EmptyRule()]))
    output = validator.validate(
        "run",
        {"step": "run", "task_id": "task-1", "execution_status": "success", "evidence_paths": ["run.json"]},
    )

    assert any(item.get("code") == "injected" for item in output["findings"])


def test_report_rule_preserves_optional_task_pack_contract() -> None:
    packet = {
        "step": "report",
        "used_goal_truth": [],
        "used_advice": [],
        "model_effort_routing": {},
        "task_id": "task-1",
        "changed_files": [],
        "commands": [],
        "validation_verdict": "partial",
        "progress_verdict": "no_progress",
        "blockers": [],
        "progress_axes": {},
        "next_task_id": None,
        "completion_status": "partial",
    }

    result = result_contract.validate("report", packet, "block")
    codes = {finding.get("code") for finding in result["findings"]}

    assert "report_task_pack_status_missing" not in codes
    assert "report_task_pack_path_missing" not in codes
    assert "report_task_pack_item_id_missing" not in codes


def main() -> int:
    test_default_registry_has_one_owner_per_target()
    test_rule_registry_supports_focused_extension()
    test_validator_accepts_an_injected_registry()
    test_report_rule_preserves_optional_task_pack_contract()
    print("result contract architecture tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
