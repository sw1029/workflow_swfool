#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_CONTRACT_PATHS = (
    ".task/contracts/output_delta_contract.json",
    ".agent_goal/output_delta_contract.json",
)
QUALITY_DELTA_KEYS: tuple[str, ...] = ()


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
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_quality_delta_policy(value: Any) -> dict[str, Any]:
    if isinstance(value, (list, tuple, set)):
        raw_keys = value
        raw_aliases: Any = {}
    elif isinstance(value, dict):
        raw_keys = (
            value.get("keys")
            or value.get("quality_delta_keys")
            or value.get("metric_keys")
            or value.get("axes")
            or []
        )
        raw_aliases = (
            value.get("aliases")
            or value.get("quality_metric_aliases")
            or value.get("metric_aliases")
            or {}
        )
    else:
        raw_keys = []
        raw_aliases = {}
    keys = list(dict.fromkeys(policy_items(raw_keys)))
    aliases: dict[str, list[str]] = {}
    for key in keys:
        supplied = policy_items(raw_aliases.get(key)) if isinstance(raw_aliases, dict) else []
        aliases[key] = list(dict.fromkeys([key, *supplied]))
    return {"keys": keys, "aliases": aliases, "supplied": bool(keys)}


def explicit_quality_delta_policy(
    contract: dict[str, Any] | None,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    for source in (payload, contract):
        if not isinstance(source, dict):
            continue
        policy = source.get("quality_delta_policy")
        if policy is not None:
            return normalize_quality_delta_policy(policy)
        if source.get("quality_delta_keys") is not None:
            return normalize_quality_delta_policy(
                {
                    "keys": source.get("quality_delta_keys"),
                    "aliases": source.get("quality_metric_aliases") or {},
                }
            )
    return normalize_quality_delta_policy(None)


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


def quality_delta_gate(
    current_quality: dict[str, Any],
    previous_quality: dict[str, Any],
    epsilon: float = 1e-9,
    quality_delta_policy: Any = None,
) -> dict[str, Any]:
    policy = normalize_quality_delta_policy(quality_delta_policy)
    keys = policy["keys"]
    current = {key: quality_metric_value(current_quality, key, policy["aliases"]) for key in keys}
    previous = {key: quality_metric_value(previous_quality, key, policy["aliases"]) for key in keys}
    improved_fields = [
        key
        for key in keys
        if current[key] > previous[key] + (epsilon if key.endswith("_ratio") else 0.0)
    ]
    return {
        "gate": "G-COV",
        "quality_delta_pass": bool(improved_fields),
        "improved_fields": improved_fields,
        "current_quality_vector": current,
        "previous_quality_vector": previous,
        "quality_delta_policy": policy,
        "quality_delta_policy_supplied": policy["supplied"],
        "evaluation_status": "evaluated" if keys else "not_evaluated",
        "status": "pass" if improved_fields else ("block" if keys else "not_evaluated"),
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
