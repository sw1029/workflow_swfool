#!/usr/bin/env python3
"""Build privacy-safe scalar diagnostics for failed task executions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .failure_diagnostics import (
    call_adapter,
    classify_error,
    exception_class,
    http_statuses,
    load_python_module,
    missing_env_key_names,
    mitigations_attempted,
    mitigations_unavailable,
    next_failure_stage,
    normalize_execution_stage_ladder,
    normalize_gate_selfcheck,
    normalize_stage_name,
    provider_failure_class,
    provider_request_count,
    provider_status,
    read_json_value,
    read_text,
    safe_scalar_diagnostics,
    traceback_last_frame,
)

def autopsy(
    stdout_text: str,
    stderr_text: str,
    exit_code: int | None,
    command: str | None,
    allow_secret_env_key_names: bool,
    gate_selfchecks: list[dict[str, Any]] | None = None,
    execution_stage_ladder: Any = None,
    last_successful_stage: str | None = None,
    post_failure_diagnostics: Any = None,
    execution_stage_ladder_error: str | None = None,
) -> dict[str, Any]:
    combined = "\n".join(part for part in (stdout_text, stderr_text) if part)
    exc = exception_class(combined)
    frame = traceback_last_frame(combined)
    statuses = http_statuses(combined)
    failure_class = provider_failure_class(combined, statuses)
    request_count = provider_request_count(combined)
    unavailable = mitigations_unavailable(combined)
    attempted = [item for item in mitigations_attempted(combined, request_count) if item not in unavailable]
    gate_selfchecks = gate_selfchecks or []
    classification = next(
        (
            item.get("classification")
            for item in gate_selfchecks
            if isinstance(item, dict) and item.get("classification")
        ),
        None,
    )
    alternative_evidence_source = next(
        (
            item.get("alternative_evidence_source")
            for item in gate_selfchecks
            if isinstance(item, dict) and item.get("alternative_evidence_source")
        ),
        None,
    )
    stages, stage_ladder_status = normalize_execution_stage_ladder(execution_stage_ladder)
    normalized_last_stage = normalize_stage_name(last_successful_stage)
    failure_surface_stage = next_failure_stage(stages, normalized_last_stage)
    scalar_diagnostics = safe_scalar_diagnostics(post_failure_diagnostics)
    stage_surface_declared = bool(stages or normalized_last_stage)
    diagnostics_unavailable = stage_surface_declared and not scalar_diagnostics
    result = {
        "schema_version": "safe-failure-autopsy-v1",
        "autopsy_status": "complete" if combined or exit_code is not None else "no_failure_text",
        "error_type": classify_error(exit_code, exc, combined),
        "exit_code": exit_code,
        "exception_class": exc,
        "traceback_last_frame": frame,
        "http_status": statuses,
        "missing_env_key_names": missing_env_key_names(combined, allow_secret_env_key_names),
        "provider_request_count": request_count,
        "provider_status": provider_status(combined),
        "failure_class": failure_class,
        "provider_response_empty": failure_class == "empty",
        "provider_response_parse_failed": failure_class == "parse",
        "classification": classification,
        "alternative_evidence_source": alternative_evidence_source,
        "gate_selfcheck": gate_selfchecks,
        "execution_stage_ladder_status": stage_ladder_status,
        "execution_stage_ladder": stages,
        "execution_stage_ladder_error": execution_stage_ladder_error,
        "last_successful_stage": normalized_last_stage,
        "failure_surface_stage": failure_surface_stage,
        "post_failure_scalar_diagnostics": scalar_diagnostics,
        "diagnostics_unavailable": diagnostics_unavailable,
        "diagnostics_unavailable_reason": (
            "no_post_failure_scalar_diagnostics"
            if diagnostics_unavailable
            else None
        ),
        "mitigations_attempted": attempted,
        "mitigations_unavailable": unavailable,
        "command_present": bool(command),
        "raw_stdout_persisted": False,
        "raw_stderr_persisted": False,
        "raw_body_persisted": False,
        "secret_values_persisted": False,
        "notes": [
            "Only scalar diagnostic fields are emitted.",
            "Do not treat this autopsy as remediation or validation success.",
        ],
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract safe scalar diagnostics from failed command output.")
    parser.add_argument("--stdout-path")
    parser.add_argument("--stderr-path")
    parser.add_argument("--stdout-text")
    parser.add_argument("--stderr-text")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--command")
    parser.add_argument("--output")
    parser.add_argument("--domain-adapter", help="Optional repository adapter exposing gate_selfcheck(...).")
    parser.add_argument("--gate-artifact-json", action="append", default=[], help="Path or JSON for a pre-execution gate artifact or self-check packet.")
    parser.add_argument("--gate-id", help="Stable gate id for gate_selfcheck classification.")
    parser.add_argument("--execution-stage-ladder-json", help="Path or JSON list/dict of adapter-owned execution stages.")
    parser.add_argument("--last-successful-stage", help="Adapter-owned stage name reached before failure.")
    parser.add_argument("--post-failure-diagnostics-json", help="Path or JSON object containing scalar/enum post-failure diagnostics.")
    parser.add_argument(
        "--repo-owned-pre-exec-blocker",
        action="store_true",
        help="Confirm that loopback/actionability provenance already established a repo-owned pre-execution blocker.",
    )
    parser.add_argument(
        "--allow-secret-env-key-names",
        action="store_true",
        help="Allow exact secret-like env var names; values are never emitted.",
    )
    args = parser.parse_args(argv)

    stdout_text = args.stdout_text if args.stdout_text is not None else read_text(Path(args.stdout_path) if args.stdout_path else None)
    stderr_text = args.stderr_text if args.stderr_text is not None else read_text(Path(args.stderr_path) if args.stderr_path else None)
    adapter = load_python_module(Path(args.domain_adapter), "safe_failure_autopsy_domain_adapter") if args.domain_adapter else None
    execution_stage_ladder = read_json_value(args.execution_stage_ladder_json)
    execution_stage_ladder_error = None
    if execution_stage_ladder is None:
        execution_stage_ladder, execution_stage_ladder_error = call_adapter(
            adapter,
            "execution_stage_ladder",
            command=args.command,
            exit_code=args.exit_code,
        )
    post_failure_diagnostics = read_json_value(args.post_failure_diagnostics_json)
    gate_selfchecks: list[dict[str, Any]] = []
    for raw_gate in args.gate_artifact_json or []:
        gate_artifact = read_json_value(raw_gate)
        adapter_value, adapter_error = call_adapter(
            adapter,
            "gate_selfcheck",
            gate_id=args.gate_id,
            gate_artifact=gate_artifact,
        )
        gate_value = adapter_value if adapter_value is not None else gate_artifact
        gate_selfchecks.append(
            normalize_gate_selfcheck(
                gate_value,
                gate_id=args.gate_id,
                repo_owned_pre_exec_blocker=args.repo_owned_pre_exec_blocker,
                adapter_error=adapter_error,
            )
        )
    result = autopsy(
        stdout_text,
        stderr_text,
        args.exit_code,
        args.command,
        args.allow_secret_env_key_names,
        gate_selfchecks,
        execution_stage_ladder,
        args.last_successful_stage,
        post_failure_diagnostics,
        execution_stage_ladder_error,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
