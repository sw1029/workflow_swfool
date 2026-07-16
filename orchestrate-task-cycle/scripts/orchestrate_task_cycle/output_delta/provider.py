from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .common import as_list, boolish
from .gate import quality_delta_gate
from .policy import explicit_quality_delta_policy


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
    metadata_only = (
        boolish(payload.get("metadata_only"))
        or (status != "complete")
        or not strict_produced
    )
    output_layer_paths = as_list(
        payload.get("output_layer_paths") or (contract or {}).get("output_layer_paths")
    )
    evidence_paths = as_list(payload.get("evidence_paths"))
    quality_vector = (
        payload.get("quality_vector")
        if isinstance(payload.get("quality_vector"), dict)
        else {}
    )
    previous_quality_vector = (
        payload.get("previous_quality_vector")
        if isinstance(payload.get("previous_quality_vector"), dict)
        else {}
    )
    substance_metrics = (
        payload.get("substance_metrics")
        if isinstance(payload.get("substance_metrics"), dict)
        else {}
    )
    previous_substance_metrics = (
        payload.get("previous_substance_metrics")
        if isinstance(payload.get("previous_substance_metrics"), dict)
        else {}
    )
    corrective_resolution = (
        payload.get("corrective_resolution")
        if isinstance(payload.get("corrective_resolution"), (list, dict))
        else []
    )
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
        "effective_progress_kind": "goal_productive"
        if strict_produced
        else "governance_only",
        "output_layer_paths": output_layer_paths,
        "previous_output_fingerprint": payload.get("previous_output_fingerprint"),
        "current_output_fingerprint": payload.get("current_output_fingerprint"),
        "output_delta_summary": payload.get("output_delta_summary")
        or payload.get("summary")
        or {},
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
        "output_fingerprint": payload.get("output_fingerprint")
        or payload.get("current_output_fingerprint"),
        "counts": payload.get("counts")
        if isinstance(payload.get("counts"), dict)
        else {},
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
        return normalize_provider_result(
            root,
            contract_path,
            contract,
            None,
            "not_applicable_no_provider",
            "missing_output_delta_provider",
        )
    entry_path = Path(entry)
    if not entry_path.is_absolute():
        entry_path = root / entry_path
    if not entry_path.is_file():
        return normalize_provider_result(
            root,
            contract_path,
            contract,
            None,
            "blocked_provider_missing",
            "provider_entry_not_found",
        )
    command = [
        sys.executable,
        str(entry_path),
        "--root",
        str(root),
        "--contract",
        str(contract_path),
    ]
    if artifact_paths_json:
        command.extend(["--artifact-paths-json", artifact_paths_json])
    for artifact_path in artifact_paths:
        command.extend(["--artifact-path", artifact_path])
    proc = subprocess.run(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
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
        return normalize_provider_result(
            root,
            contract_path,
            contract,
            None,
            "blocked_provider_malformed",
            "provider_stdout_not_json",
            proc.stderr,
        )
    if not isinstance(provider_payload, dict):
        return normalize_provider_result(
            root,
            contract_path,
            contract,
            None,
            "blocked_provider_malformed",
            "provider_stdout_not_object",
            proc.stderr,
        )
    return normalize_provider_result(
        root, contract_path, contract, provider_payload, "complete"
    )
