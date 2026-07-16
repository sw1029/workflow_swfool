#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


from .changed_surface import classify_files, git_changed_files, load_payload, values_from_payload


PROFILE_RANK = {"current_only": 0, "affected_chain": 1, "full_chain": 2}
PLACEHOLDER_TASK_IDS = {"", "unknown", "unknown-task", "none", "not_recorded"}


def strict_true(value: Any) -> bool:
    return value is True or (isinstance(value, int) and not isinstance(value, bool) and value == 1)


def list_field(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def choose_profile(surfaces: set[str], flags: dict[str, bool], known: bool) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if any(flags.values()):
        reasons.extend(sorted(key for key, value in flags.items() if value))
        return "full_chain", reasons
    if not known:
        return "affected_chain", ["changed_surface_unknown"]
    affected = surfaces & {"source", "tests", "runtime_config", "schema", "contract", "unknown"}
    if affected:
        reasons.append("affected_surfaces:" + ",".join(sorted(affected)))
        return "affected_chain", reasons
    return "current_only", ["local_state_or_documentation_only"]


def max_profile(left: str, right: str) -> str:
    if left not in PROFILE_RANK or right not in PROFILE_RANK:
        raise ValueError("Unknown validation profile.")
    return left if PROFILE_RANK[left] >= PROFILE_RANK[right] else right


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_value = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_value)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def workspace_output_path(root: Path, value: str) -> Path:
    raw = Path(value)
    path = (raw if raw.is_absolute() else root / raw).resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Validation-scope output path must stay inside the workspace root, including through symlinks.") from exc
    return path


def require_plan_identity(plan: dict[str, Any], task_id: str) -> None:
    normalized_task_id = str(task_id or "").strip()
    plan_task_id = str(plan.get("task_id") or "").strip()
    if normalized_task_id.lower() in PLACEHOLDER_TASK_IDS:
        raise ValueError("Finalize mode requires a non-placeholder task_id.")
    if str(plan.get("step") or "") != "validation_scope_plan":
        raise ValueError("Finalize mode requires a validation_scope_plan manifest.")
    if str(plan.get("mode") or "") != "plan":
        raise ValueError("Finalize mode requires a plan manifest with mode=plan.")
    if plan.get("finalized") is not False:
        raise ValueError("Finalize mode requires an unfinalized plan manifest.")
    if plan_task_id.lower() in PLACEHOLDER_TASK_IDS:
        raise ValueError("Plan manifest requires a non-placeholder task_id.")
    if plan_task_id != normalized_task_id:
        raise ValueError("Plan manifest task_id does not match the task being finalized.")


def build_manifest(
    *,
    root: Path,
    mode: str,
    task_id: str,
    values: list[str],
    files_known: bool,
    payload: dict[str, Any],
    plan: dict[str, Any] | None,
    required_commands: list[str],
    reused_prerequisites: list[str],
    escalation_reasons: list[str],
) -> dict[str, Any]:
    classified = classify_files(root, values)
    surfaces = set(classified["changed_surfaces"])
    flags = {
        "explicit_full_chain": strict_true(payload.get("explicit_full_chain")),
        "high_risk_contract_logic": strict_true(payload.get("high_risk_contract_logic")),
        "issue_closure": strict_true(payload.get("issue_closure")),
        "live_dispatch_or_readiness_promotion": strict_true(payload.get("live_dispatch_or_readiness_promotion")),
        "shared_runtime_change": strict_true(payload.get("shared_runtime_change")),
    }
    selected, rationale = choose_profile(surfaces, flags, files_known)
    profile_floor = selected
    profile_changed = False
    planned_files: list[str] = classified["changed_files"] if mode == "plan" else []
    actual_files: list[str] = classified["changed_files"] if mode == "finalize" else []
    if mode == "finalize":
        if not isinstance(plan, dict):
            raise ValueError("Finalize mode requires a plan manifest.")
        require_plan_identity(plan, task_id)
        plan_profile = str(plan.get("validation_profile") or "")
        if plan_profile not in PROFILE_RANK:
            raise ValueError("Plan manifest has an invalid validation_profile.")
        profile_floor = plan_profile
        final_profile = max_profile(plan_profile, selected)
        profile_changed = final_profile != plan_profile
        selected = final_profile
        planned_files = [str(item) for item in plan.get("planned_changed_files", []) if str(item).strip()]
        required_commands = list(dict.fromkeys(list_field(plan, "required_commands") + required_commands))
        reused_prerequisites = list(dict.fromkeys(list_field(plan, "reused_prerequisites") + reused_prerequisites))
        escalation_reasons = list(dict.fromkeys(list_field(plan, "escalation_reasons") + escalation_reasons))
        planned_set = set(planned_files)
        new_files = sorted(set(actual_files) - planned_set)
        if new_files:
            rationale.append("actual_surface_expanded:" + ",".join(new_files))

    status = "ok"
    findings: list[dict[str, str]] = []
    if not files_known:
        severity = "block" if mode == "finalize" else "warn"
        findings.append({"severity": severity, "code": "changed_surface_unknown", "message": "Changed-file input was not supplied."})
        status = severity
    if mode == "finalize" and not required_commands:
        findings.append(
            {
                "severity": "block",
                "code": "required_commands_missing",
                "message": "Finalized validation scope requires at least one repository-owned validation command.",
            }
        )
        status = "block"

    step = "validation_scope_plan" if mode == "plan" else "validation_scope_finalize"
    return {
        "format_version": 1,
        "step": step,
        "status": status,
        "task_id": task_id or "unknown-task",
        "mode": mode,
        "validation_profile": selected,
        "profile_floor": profile_floor,
        "profile_changed": profile_changed,
        "planned_changed_files": planned_files,
        "actual_changed_files": actual_files,
        "changed_surfaces": classified["changed_surfaces"],
        "surface_counts": classified["surface_counts"],
        "required_commands": list(dict.fromkeys(required_commands)),
        "reused_prerequisites": list(dict.fromkeys(reused_prerequisites)),
        "escalation_reasons": list(dict.fromkeys(escalation_reasons)),
        "rationale": rationale,
        "finalized": mode == "finalize" and status != "block",
        "findings": findings,
        "evidence_paths": ["stdout:validation_scope"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or finalize a fail-closed validation scope manifest.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--mode", choices=("plan", "finalize"), required=True)
    parser.add_argument("--task-id", default="unknown-task")
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--input-json")
    parser.add_argument("--plan-json")
    parser.add_argument("--from-git", action="store_true")
    parser.add_argument("--required-command", action="append", default=[])
    parser.add_argument("--reused-prerequisite", action="append", default=[])
    parser.add_argument("--escalation-reason", action="append", default=[])
    parser.add_argument("--explicit-full-chain", action="store_true")
    parser.add_argument("--high-risk-contract-logic", action="store_true")
    parser.add_argument("--issue-closure", action="store_true")
    parser.add_argument("--live-dispatch-or-readiness-promotion", action="store_true")
    parser.add_argument("--shared-runtime-change", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    payload = load_payload(args.input_json) if args.input_json else {}
    values = list(args.file) + values_from_payload(payload)
    files_known = bool(args.file) or any(key in payload for key in ("changed_files", "planned_changed_files", "actual_changed_files", "files"))
    if args.from_git:
        try:
            values.extend(git_changed_files(root))
            files_known = True
        except RuntimeError as exc:
            json.dump({"format_version": 1, "status": "block", "error": str(exc)}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 2
    for key in (
        "explicit_full_chain",
        "high_risk_contract_logic",
        "issue_closure",
        "live_dispatch_or_readiness_promotion",
        "shared_runtime_change",
    ):
        if getattr(args, key):
            payload[key] = True
    plan = load_payload(args.plan_json) if args.plan_json else None
    try:
        manifest = build_manifest(
            root=root,
            mode=args.mode,
            task_id=args.task_id,
            values=values,
            files_known=files_known,
            payload=payload,
            plan=plan,
            required_commands=list_field(payload, "required_commands") + list(args.required_command),
            reused_prerequisites=list_field(payload, "reused_prerequisites") + list(args.reused_prerequisite),
            escalation_reasons=list_field(payload, "escalation_reasons") + list(args.escalation_reason),
        )
    except ValueError as exc:
        manifest = {"format_version": 1, "status": "block", "error": str(exc)}
    if args.output:
        try:
            output_path = workspace_output_path(root, args.output)
        except ValueError as exc:
            manifest = {"format_version": 1, "status": "block", "error": str(exc)}
        else:
            atomic_write_json(output_path, manifest)
    json.dump(manifest, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 2 if manifest.get("status") == "block" else 0


if __name__ == "__main__":
    raise SystemExit(main())
