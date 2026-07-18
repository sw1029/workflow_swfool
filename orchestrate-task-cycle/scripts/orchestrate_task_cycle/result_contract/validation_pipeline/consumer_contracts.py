from __future__ import annotations

from typing import Any


CONTRACT_FIELDS = (
    "task_id",
    "adapter_revision_sha256",
    "consumer_revision_sha256",
    "hook_id",
    "required_hook_ids",
    "required_gate_ids",
)
SET_FIELDS = {"required_hook_ids", "required_gate_ids"}


def _declared(data: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _contract_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if not isinstance(value, dict):
        return []
    if value.get("consumer_id") or value.get("consumer_context_id"):
        return [value]
    return [
        {"consumer_id": consumer_id, **row}
        for consumer_id, row in value.items()
        if isinstance(row, dict)
    ]


def _same(field: str, left: Any, right: Any) -> bool:
    if field not in SET_FIELDS:
        return left == right
    if not isinstance(left, list) or not isinstance(right, list):
        return left == right
    return sorted(left) == sorted(right)


def _merge(expectation: dict[str, Any], field: str, value: Any) -> None:
    if expectation.get(field) is not None and not _same(
        field, expectation[field], value
    ):
        expectation["contract_conflicts"].append(field)
        return
    expectation[field] = value
    expectation["explicit"] = True


def _expectation(consumer_id: str, task_id: str | None) -> dict[str, Any]:
    return {
        "consumer_id": consumer_id,
        "task_id": task_id,
        "adapter_revision_sha256": None,
        "consumer_revision_sha256": None,
        "hook_id": None,
        "required_hook_ids": None,
        "required_gate_ids": None,
        "explicit": False,
        "contract_conflicts": [],
    }


def _adapter_revisions(result: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for path in (
        "adapter_revision_sha256",
        "domain_adapter.adapter_revision_sha256",
        "adapter_load_gate.adapter_revision_sha256",
        "result.adapter_revision_sha256",
        "result.domain_adapter.adapter_revision_sha256",
    ):
        declared, value = _declared(result, path)
        text = str(value or "").strip()
        if declared and text and text not in values:
            values.append(text)
    return values


def _apply_contract_rows(
    result: dict[str, Any], expectations: dict[str, dict[str, Any]]
) -> None:
    paths = (
        "consumer_contract",
        "consumer_contracts",
        "adapter_contract.consumer_contract",
        "adapter_contract.consumer_contracts",
        "consumer_context_conformance.consumer_contract",
        "consumer_context_conformance.consumer_contracts",
        "adapter_consumer_conformance.consumer_contract",
        "adapter_consumer_conformance.consumer_contracts",
        "result.consumer_contract",
        "result.consumer_contracts",
    )
    for path in paths:
        declared, value = _declared(result, path)
        if not declared:
            continue
        for row in _contract_rows(value):
            consumer_id = str(
                row.get("consumer_id") or row.get("consumer_context_id") or ""
            ).strip()
            if not consumer_id:
                continue
            expectation = expectations.setdefault(
                consumer_id,
                _expectation(consumer_id, str(result.get("task_id") or "") or None),
            )
            for field in CONTRACT_FIELDS:
                if field in row:
                    _merge(expectation, field, row[field])


def _adapter_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in (
        "repo_skill_adapter_packet.adapters",
        "adapter_scan.repo_skill_adapter_packet.adapters",
        "result.repo_skill_adapter_packet.adapters",
    ):
        declared, value = _declared(result, path)
        if declared and isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    return rows


def _apply_manifest_contracts(
    result: dict[str, Any], expectations: dict[str, dict[str, Any]]
) -> None:
    phase = str(result.get("phase") or result.get("step") or "").strip()
    if not phase:
        return
    for row in _adapter_rows(result):
        consumers = (row.get("phase_consumer_map") or {}).get(phase)
        hooks = (row.get("phase_hook_map") or {}).get(phase)
        if not isinstance(consumers, list) or not isinstance(hooks, list):
            continue
        for raw_consumer_id in consumers:
            consumer_id = str(raw_consumer_id).strip()
            if not consumer_id:
                continue
            expectation = expectations.setdefault(
                consumer_id,
                _expectation(consumer_id, str(result.get("task_id") or "") or None),
            )
            _merge(expectation, "required_hook_ids", hooks)
            if row.get("adapter_revision_sha256"):
                _merge(
                    expectation,
                    "adapter_revision_sha256",
                    row["adapter_revision_sha256"],
                )


def _apply_shared_sets(
    result: dict[str, Any], expectations: dict[str, dict[str, Any]]
) -> None:
    paths = {
        "required_hook_ids": (
            "required_hook_ids",
            "adapter_contract.required_hook_ids",
            "domain_adapter.required_hook_ids",
            "consumer_context_conformance.required_hook_ids",
        ),
        "required_gate_ids": (
            "required_gate_ids",
            "consumer_required_gate_ids",
            "consumer_context_conformance.required_gate_ids",
        ),
    }
    for field, field_paths in paths.items():
        declared_values = [
            value
            for path in field_paths
            for declared, value in [_declared(result, path)]
            if declared
        ]
        for expectation in expectations.values():
            for value in declared_values:
                _merge(expectation, field, value)


def consumer_expectations(
    result: dict[str, Any], consumer_ids: list[Any]
) -> dict[str, dict[str, Any]]:
    task_id = str(result.get("task_id") or "").strip() or None
    expectations = {
        str(consumer_id): _expectation(str(consumer_id), task_id)
        for consumer_id in consumer_ids
    }
    _apply_contract_rows(result, expectations)
    _apply_manifest_contracts(result, expectations)
    _apply_shared_sets(result, expectations)
    revisions = _adapter_revisions(result)
    for expectation in expectations.values():
        if expectation["explicit"]:
            for revision in revisions:
                _merge(expectation, "adapter_revision_sha256", revision)
            for field in SET_FIELDS:
                if expectation.get(field) is None:
                    expectation[field] = []
            expectation["contract_conflicts"] = sorted(
                set(expectation["contract_conflicts"])
            )
    return expectations


__all__ = ["consumer_expectations"]
