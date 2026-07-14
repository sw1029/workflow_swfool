#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_CONTRACT_PATHS = (
    ".task/contracts/output_delta_contract.json",
    ".agent_goal/output_delta_contract.json",
)
QUALITY_DELTA_KEYS: tuple[str, ...] = ()
METRIC_APPLICABILITY_STATUSES = {
    "applicable",
    "not_applicable",
    "insufficient_evidence",
    "invalid_contract",
}
METRIC_POLICY_CONTRACT_ERROR_CODES = {
    "declared_metric_id_malformed",
    "metric_alias_contract_malformed",
    "metric_policy_contract_malformed",
}
OPAQUE_ID_MAX_LENGTH = 256


def opaque_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > OPAQUE_ID_MAX_LENGTH:
        return None
    return normalized


def applicability_reason_code(value: Any, *, fallback: str | None) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return fallback
    normalized = opaque_id(value)
    if normalized is None or not normalized[0].isascii() or not normalized[0].isalnum() or any(
        not character.isascii() or not (character.isalnum() or character in "._-")
        for character in normalized
    ):
        return "applicability_reason_code_malformed"
    return normalized


def legacy_applicability_projection(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and all(
            isinstance(row, dict)
            and str(row.get("evaluation_status") or "").strip().lower() == "applicable"
            and row.get("reason_code") == "legacy_declared_metric"
            for row in value.values()
        )
    )


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def discover_contract(root: Path, explicit: str | None = None) -> tuple[Path | None, dict[str, Any] | None, str | None]:
    candidates = [explicit] if explicit else list(DEFAULT_CONTRACT_PATHS)
    for value in candidates:
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            continue
        loaded = read_json(path)
        if not isinstance(loaded, dict):
            return path, None, "malformed_contract_json"
        return path, loaded, None
    return None, None, "not_applicable_no_contract"


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present", "produced", "changed"}
    return False


def number_value(value: Any) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def policy_items(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [normalized for item in value if (normalized := opaque_id(item)) is not None]


def policy_items_contract(value: Any, *, absent_allowed: bool = False) -> tuple[list[str], bool]:
    """Return string contract items without stringifying malformed values."""
    if value is None:
        return ([], absent_allowed)
    if isinstance(value, str):
        normalized = opaque_id(value)
        return ([normalized], True) if normalized is not None else ([], False)
    if not isinstance(value, (list, tuple, set)):
        return ([], False)
    items: list[str] = []
    valid = True
    for item in value:
        normalized = opaque_id(item)
        if normalized is None:
            valid = False
            continue
        items.append(normalized)
    return (items, valid)


def opaque_id_list_valid(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return opaque_id(value) is not None
    return isinstance(value, (list, tuple, set)) and all(
        opaque_id(item) is not None for item in value
    )


def normalize_metric_applicability(value: Any, *, supplied: bool) -> dict[str, Any]:
    if not supplied:
        return {
            "evaluation_status": "applicable",
            "reason_code": "legacy_declared_metric",
            "required_body_class_ids": [],
            "missing_body_class_ids": [],
        }
    if isinstance(value, bool):
        value = {"evaluation_status": "applicable" if value else "not_applicable"}
    elif isinstance(value, str):
        value = {"evaluation_status": value}
    if not isinstance(value, dict):
        return {"evaluation_status": "invalid_contract", "reason_code": "applicability_row_malformed"}
    status = str(value.get("evaluation_status") or value.get("status") or "").strip().lower()
    boolean_status = value.get("applicable")
    if isinstance(boolean_status, bool):
        from_boolean = "applicable" if boolean_status else "not_applicable"
        if status and status != from_boolean:
            status = "invalid_contract"
        elif not status:
            status = from_boolean
    required_value = value.get("required_body_class_ids") if "required_body_class_ids" in value else value.get("required_body_classes")
    missing_value = value.get("missing_body_class_ids") if "missing_body_class_ids" in value else value.get("missing_body_classes")
    evidence_value = value.get("evidence_ids")
    required = policy_items(required_value)
    missing = policy_items(missing_value)
    opaque_ids_valid = all(
        opaque_id_list_valid(item) for item in (required_value, missing_value, evidence_value)
    )
    if not opaque_ids_valid:
        status = "invalid_contract"
    if status == "applicable" and missing:
        status = "insufficient_evidence"
    if status not in METRIC_APPLICABILITY_STATUSES:
        status = "invalid_contract"
    return {
        "evaluation_status": status,
        "reason_code": applicability_reason_code(
            value.get("reason_code"),
            fallback="applicability_opaque_id_malformed" if not opaque_ids_valid else None,
        ),
        "required_body_class_ids": required,
        "missing_body_class_ids": missing,
        "evidence_ids": policy_items(evidence_value),
    }


def normalize_quality_delta_policy(value: Any) -> dict[str, Any]:
    if isinstance(value, (list, tuple, set)):
        raw_keys = value
        raw_aliases: Any = {}
    elif isinstance(value, dict):
        raw_keys = next(
            (
                value[key]
                for key in ("declared_keys", "keys", "quality_delta_keys", "metric_keys", "axes")
                if key in value and value[key] is not None
            ),
            [],
        )
        raw_aliases = next(
            (
                value[key]
                for key in ("aliases", "quality_metric_aliases", "metric_aliases")
                if key in value and value[key] is not None
            ),
            {},
        )
        raw_applicability = value.get("applicability")
        alternate_applicability = value.get("metric_applicability")
        applicability_flag_conflict = bool(
            value.get("applicability_supplied") is False
            and any(
                mapping is not None and not legacy_applicability_projection(mapping)
                for mapping in (raw_applicability, alternate_applicability)
            )
        )
        if value.get("applicability_supplied") is False and not applicability_flag_conflict:
            raw_applicability = None
            alternate_applicability = None
    else:
        raw_keys = []
        raw_aliases = {}
        raw_applicability = None
        alternate_applicability = None
        applicability_flag_conflict = False
    if not isinstance(value, dict):
        raw_applicability = None
        alternate_applicability = None
        applicability_flag_conflict = False
    raw_key_items, declared_keys_valid = policy_items_contract(raw_keys)
    keys = list(dict.fromkeys(raw_key_items))
    aliases: dict[str, list[str]] = {}
    alias_invalid_keys: set[str] = set()
    alias_contract_valid = isinstance(raw_aliases, dict)
    if isinstance(raw_aliases, dict):
        for key in keys:
            supplied, supplied_valid = policy_items_contract(
                raw_aliases.get(key),
                absent_allowed=True,
            )
            if not supplied_valid:
                alias_invalid_keys.add(key)
            aliases[key] = list(dict.fromkeys([key, *supplied]))
        for alias_key, alias_value in raw_aliases.items():
            _, entry_valid = policy_items_contract(alias_value, absent_allowed=True)
            if opaque_id(alias_key) is None or not entry_valid:
                alias_contract_valid = False
                if isinstance(alias_key, str) and alias_key in keys:
                    alias_invalid_keys.add(alias_key)
    else:
        aliases = {key: [key] for key in keys}
    inherited_error_codes = [
        code
        for code in (policy_items(value.get("policy_contract_error_codes")) if isinstance(value, dict) else [])
        if code in METRIC_POLICY_CONTRACT_ERROR_CODES
    ]
    policy_contract_error_codes: list[str] = list(dict.fromkeys(inherited_error_codes))
    if isinstance(value, dict) and value.get("policy_contract_invalid") and not policy_contract_error_codes:
        policy_contract_error_codes.append("metric_policy_contract_malformed")
    if not declared_keys_valid:
        policy_contract_error_codes.append("declared_metric_id_malformed")
    if not alias_contract_valid or alias_invalid_keys:
        policy_contract_error_codes.append("metric_alias_contract_malformed")
    if applicability_flag_conflict:
        policy_contract_error_codes.append("metric_policy_contract_malformed")
    for applicability_value in (raw_applicability, alternate_applicability):
        if isinstance(applicability_value, dict) and any(
            opaque_id(metric_id) is None for metric_id in applicability_value
        ):
            policy_contract_error_codes.append("metric_policy_contract_malformed")
    policy_contract_error_codes = list(dict.fromkeys(policy_contract_error_codes))
    policy_contract_invalid = bool(policy_contract_error_codes)
    applicability_conflict = (
        raw_applicability is not None
        and alternate_applicability is not None
        and raw_applicability != alternate_applicability
    )
    applicability_source = raw_applicability if raw_applicability is not None else alternate_applicability
    applicability_supplied = applicability_source is not None
    mapping = applicability_source if isinstance(applicability_source, dict) else {}
    applicability = {
        key: normalize_metric_applicability(
            mapping.get(key),
            supplied=applicability_supplied,
        )
        for key in keys
    }
    if applicability_conflict or (applicability_supplied and not isinstance(applicability_source, dict)):
        for key in keys:
            applicability[key] = {
                **applicability[key],
                "evaluation_status": "invalid_contract",
                "reason_code": "applicability_mapping_conflict" if applicability_conflict else "applicability_mapping_malformed",
            }
    invalid = [key for key in keys if applicability[key]["evaluation_status"] == "invalid_contract"]
    if policy_contract_invalid:
        invalid = list(keys)
    insufficient = [key for key in keys if applicability[key]["evaluation_status"] == "insufficient_evidence"]
    not_applicable = [key for key in keys if applicability[key]["evaluation_status"] == "not_applicable"]
    return {
        "declared_keys": keys,
        "keys": [] if policy_contract_invalid or invalid else [key for key in keys if applicability[key]["evaluation_status"] == "applicable"],
        "aliases": aliases,
        "applicability": applicability,
        "applicability_supplied": applicability_supplied,
        "not_applicable_fields": not_applicable,
        "insufficient_evidence_fields": insufficient,
        "invalid_contract_fields": invalid,
        "policy_contract_invalid": policy_contract_invalid,
        "policy_contract_error_codes": policy_contract_error_codes,
        "supplied": bool(keys),
    }


def explicit_quality_delta_policy(
    contract: dict[str, Any] | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for source in (payload, contract):
        if not isinstance(source, dict):
            continue
        policy = source.get("quality_delta_policy")
        if policy is not None:
            candidates.append(normalize_quality_delta_policy(policy))
        elif source.get("quality_delta_keys") is not None:
            candidates.append(normalize_quality_delta_policy(
                {
                    "keys": source.get("quality_delta_keys"),
                    "aliases": source.get("quality_metric_aliases") or {},
                }
            ))
    if not candidates:
        return normalize_quality_delta_policy(None)
    comparable = [
        json.dumps(
            {
                "declared_keys": sorted(item["declared_keys"]),
                "policy_contract_invalid": item["policy_contract_invalid"],
                "policy_contract_error_codes": sorted(item["policy_contract_error_codes"]),
                "aliases": {
                    key: sorted(set(item["aliases"].get(key, [key])))
                    for key in sorted(item["declared_keys"])
                },
                "applicability": {
                    key: {
                        "evaluation_status": item["applicability"].get(key, {}).get("evaluation_status"),
                        "required_body_class_ids": sorted(set(item["applicability"].get(key, {}).get("required_body_class_ids") or [])),
                        "missing_body_class_ids": sorted(set(item["applicability"].get(key, {}).get("missing_body_class_ids") or [])),
                    }
                    for key in sorted(item["declared_keys"])
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        for item in candidates
    ]
    if len(set(comparable)) == 1:
        return candidates[0]
    declared = list(dict.fromkeys(key for item in candidates for key in item["declared_keys"]))
    aliases = {key: list(dict.fromkeys(alias for item in candidates for alias in item["aliases"].get(key, [key]))) for key in declared}
    return normalize_quality_delta_policy(
        {
            "keys": declared,
            "aliases": aliases,
            "applicability": {
                key: {
                    "evaluation_status": "invalid_contract",
                    "reason_code": "payload_contract_policy_conflict",
                }
                for key in declared
            },
        }
    )


def quality_metric_value(
    quality: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> float:
    candidates = policy_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate in quality:
            return number_value(quality.get(candidate))
    return 0.0


def numeric_metric_value(
    quality: dict[str, Any],
    key: str,
    aliases: dict[str, Any] | None = None,
) -> tuple[bool, float | None]:
    candidates = policy_items((aliases or {}).get(key)) or [key]
    for candidate in candidates:
        if candidate not in quality:
            continue
        value = quality.get(candidate)
        if isinstance(value, bool):
            return False, None
        if isinstance(value, (int, float)):
            try:
                numeric = float(value)
            except OverflowError:
                return False, None
            return (True, numeric) if math.isfinite(numeric) else (False, None)
        if isinstance(value, str):
            try:
                numeric = float(value.strip())
                return (True, numeric) if math.isfinite(numeric) else (False, None)
            except ValueError:
                return False, None
        return False, None
    return False, None


def quality_delta_gate(
    current_quality: dict[str, Any],
    previous_quality: dict[str, Any],
    epsilon: float = 1e-9,
    quality_delta_policy: Any = None,
) -> dict[str, Any]:
    policy = normalize_quality_delta_policy(quality_delta_policy)
    keys = policy["keys"]
    try:
        epsilon_value = float(epsilon) if not isinstance(epsilon, bool) else float("nan")
    except (OverflowError, TypeError, ValueError):
        epsilon_value = float("nan")
    epsilon_valid = math.isfinite(epsilon_value) and epsilon_value >= 0
    effective_epsilon = epsilon_value if epsilon_valid else 0.0
    current: dict[str, float] = {}
    previous: dict[str, float] = {}
    missing: list[str] = []
    previous_binding_count = sum(
        1
        for key in keys
        if any(candidate in previous_quality for candidate in policy["aliases"].get(key, [key]))
    )
    baseline_absent = bool(keys) and previous_binding_count == 0
    for key in keys:
        current_present, current_value = numeric_metric_value(current_quality, key, policy["aliases"])
        previous_present, previous_value = numeric_metric_value(previous_quality, key, policy["aliases"])
        if current_present and current_value is not None:
            current[key] = current_value
        if previous_present and previous_value is not None:
            previous[key] = previous_value
        elif baseline_absent:
            previous[key] = 0.0
        if not current_present or (not previous_present and not baseline_absent):
            missing.append(key)
    invalid = list(policy["invalid_contract_fields"])
    if not epsilon_valid:
        invalid = list(dict.fromkeys([*invalid, *policy["declared_keys"]]))
    insufficient = sorted(set([*policy["insufficient_evidence_fields"], *missing]))
    evaluated = bool(keys) and not invalid and not insufficient
    improved_fields = [
        key
        for key in keys
        if evaluated and current[key] > previous[key] + (effective_epsilon if key.endswith("_ratio") else 0.0)
    ]
    if policy.get("policy_contract_invalid") or invalid:
        evaluation_status = "invalid_contract"
    elif insufficient:
        evaluation_status = "insufficient_evidence"
    elif not policy["supplied"]:
        evaluation_status = "not_evaluated"
    elif not keys and policy["not_applicable_fields"]:
        evaluation_status = "not_applicable"
    else:
        evaluation_status = "evaluated"
    return {
        "gate": "G-COV",
        "quality_delta_pass": bool(improved_fields),
        "improved_fields": improved_fields,
        "current_quality_vector": current,
        "previous_quality_vector": previous,
        "quality_delta_policy": policy,
        "quality_delta_policy_supplied": policy["supplied"],
        "not_applicable_fields": policy["not_applicable_fields"],
        "insufficient_evidence_fields": insufficient,
        "invalid_contract_fields": invalid,
        "evaluation_status": evaluation_status,
        "status": "pass" if improved_fields else ("block" if evaluation_status == "evaluated" else evaluation_status),
    }


def rel_path(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def provider_entry(contract: dict[str, Any]) -> str | None:
    provider = contract.get("output_delta_provider")
    if isinstance(provider, dict):
        entry = provider.get("entry")
        if entry:
            return str(entry)
    return None


def normalize_provider_result(
    root: Path,
    contract_path: Path | None,
    contract: dict[str, Any] | None,
    provider_payload: dict[str, Any] | None,
    status: str,
    reason: str | None = None,
    provider_stderr: str | None = None,
) -> dict[str, Any]:
    payload = provider_payload if isinstance(provider_payload, dict) else {}
    produced = boolish(payload.get("produced_domain_delta"))
    changed_vs_previous = boolish(payload.get("changed_vs_previous"))
    semantic_progress = boolish(payload.get("semantic_progress"))
    strict_produced = produced and changed_vs_previous and semantic_progress
    metadata_only = boolish(payload.get("metadata_only")) or (status != "complete") or not strict_produced
    output_layer_paths = as_list(payload.get("output_layer_paths") or (contract or {}).get("output_layer_paths"))
    evidence_paths = as_list(payload.get("evidence_paths"))
    quality_vector = payload.get("quality_vector") if isinstance(payload.get("quality_vector"), dict) else {}
    previous_quality_vector = payload.get("previous_quality_vector") if isinstance(payload.get("previous_quality_vector"), dict) else {}
    substance_metrics = payload.get("substance_metrics") if isinstance(payload.get("substance_metrics"), dict) else {}
    previous_substance_metrics = payload.get("previous_substance_metrics") if isinstance(payload.get("previous_substance_metrics"), dict) else {}
    corrective_resolution = payload.get("corrective_resolution") if isinstance(payload.get("corrective_resolution"), (list, dict)) else []
    quality_delta_policy = explicit_quality_delta_policy(contract, payload)
    return {
        "schema_version": "output-delta-gate-v1",
        "output_delta_status": status,
        "output_delta_reason": reason,
        "output_delta_contract_path": rel_path(root, contract_path),
        "produced_domain_delta": strict_produced,
        "declared_produced_domain_delta": produced,
        "changed_vs_previous": changed_vs_previous,
        "semantic_progress": semantic_progress,
        "metadata_only": metadata_only,
        "effective_progress_kind": "goal_productive" if strict_produced else "governance_only",
        "output_layer_paths": output_layer_paths,
        "previous_output_fingerprint": payload.get("previous_output_fingerprint"),
        "current_output_fingerprint": payload.get("current_output_fingerprint"),
        "output_delta_summary": payload.get("output_delta_summary") or payload.get("summary") or {},
        "quality_vector": quality_vector,
        "previous_quality_vector": previous_quality_vector,
        "quality_delta_policy": quality_delta_policy,
        "coverage_quality_delta_gate": quality_delta_gate(
            quality_vector,
            previous_quality_vector,
            quality_delta_policy=quality_delta_policy,
        ),
        "substance_metrics": substance_metrics,
        "previous_substance_metrics": previous_substance_metrics,
        "corrective_resolution": corrective_resolution,
        "output_fingerprint": payload.get("output_fingerprint") or payload.get("current_output_fingerprint"),
        "counts": payload.get("counts") if isinstance(payload.get("counts"), dict) else {},
        "evidence_paths": evidence_paths,
        "raw_body_persisted": False,
        "secret_values_persisted": False,
        "provider_stderr_summary": provider_stderr[:500] if provider_stderr else None,
    }


def run_provider(
    root: Path,
    contract_path: Path,
    contract: dict[str, Any],
    artifact_paths_json: str | None,
    artifact_paths: list[str],
) -> dict[str, Any]:
    entry = provider_entry(contract)
    if not entry:
        return normalize_provider_result(root, contract_path, contract, None, "not_applicable_no_provider", "missing_output_delta_provider")
    entry_path = Path(entry)
    if not entry_path.is_absolute():
        entry_path = root / entry_path
    if not entry_path.is_file():
        return normalize_provider_result(root, contract_path, contract, None, "blocked_provider_missing", "provider_entry_not_found")

    command = [sys.executable, str(entry_path), "--root", str(root), "--contract", str(contract_path)]
    if artifact_paths_json:
        command.extend(["--artifact-paths-json", artifact_paths_json])
    for artifact_path in artifact_paths:
        command.extend(["--artifact-path", artifact_path])
    proc = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return normalize_provider_result(
            root,
            contract_path,
            contract,
            None,
            "blocked_provider_failed",
            f"provider_exit_{proc.returncode}",
            proc.stderr,
        )
    try:
        provider_payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return normalize_provider_result(root, contract_path, contract, None, "blocked_provider_malformed", "provider_stdout_not_json", proc.stderr)
    if not isinstance(provider_payload, dict):
        return normalize_provider_result(root, contract_path, contract, None, "blocked_provider_malformed", "provider_stdout_not_object", proc.stderr)
    return normalize_provider_result(root, contract_path, contract, provider_payload, "complete")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a repository output-delta contract through its provider hook.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--contract")
    parser.add_argument("--artifact-paths-json")
    parser.add_argument("--artifact-path", action="append", default=[])
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    contract_path, contract, reason = discover_contract(root, args.contract)
    if contract_path is None or contract is None:
        result = normalize_provider_result(root, contract_path, contract, None, reason or "not_applicable_no_contract", reason)
    else:
        result = run_provider(root, contract_path, contract, args.artifact_paths_json, args.artifact_path)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if result["output_delta_status"] in {"complete", "not_applicable_no_contract", "not_applicable_no_provider"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
