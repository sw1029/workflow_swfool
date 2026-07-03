#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


TRACEBACK_FILE_RE = re.compile(r'File "([^"]+)", line ([0-9]+)(?:, in ([^\s]+))?')
EXCEPTION_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Interrupt|Warning))(?::|\b)")
HTTP_STATUS_RE = re.compile(r"\b(?:HTTP(?: status)?|status(?:_code)?)[=:\s]+([1-5][0-9]{2})\b", re.IGNORECASE)
PROVIDER_REQUEST_COUNT_RE = re.compile(r"\bprovider_request_count\s*[=:]\s*([0-9]+)\b", re.IGNORECASE)
PROVIDER_STATUS_RE = re.compile(r"\bprovider_status\s*[=:]\s*([A-Za-z0-9_.:-]+)\b", re.IGNORECASE)
MITIGATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("structured_output", re.compile(r"\b(structured[_ -]?output|json[_ -]?schema|response[_ -]?format)\b", re.IGNORECASE)),
    ("window_reduce", re.compile(r"\b(window[_ -]?(reduce|reduced|shrink|shrank)|smaller[_ -]?window)\b", re.IGNORECASE)),
    ("timeout_budget_increase", re.compile(r"\b(timeout[_ -]?(budget[_ -]?)?(increase|increased|extend|extended)|longer[_ -]?timeout)\b", re.IGNORECASE)),
    ("backoff_retry>=3", re.compile(r"\b(backoff|retry|retries).{0,40}\b([3-9]|[1-9][0-9]+)\b", re.IGNORECASE)),
    ("model_fallback", re.compile(r"\b(model[_ -]?fallback|fallback[_ -]?model|alternate[_ -]?model)\b", re.IGNORECASE)),
)
UNAVAILABLE_WORDS = r"(unavailable|unauthorized|forbidden|blocked|not allowed|금지|불가)"
MITIGATION_UNAVAILABLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("structured_output", re.compile(rf"\bstructured[_ -]?output\b[^.;\n]{{0,80}}\b{UNAVAILABLE_WORDS}\b", re.IGNORECASE)),
    ("window_reduce", re.compile(rf"\bwindow[_ -]?reduce\b[^.;\n]{{0,80}}\b{UNAVAILABLE_WORDS}\b", re.IGNORECASE)),
    ("timeout_budget_increase", re.compile(rf"\btimeout[_ -]?budget(?:[_ -]?increase)?\b[^.;\n]{{0,80}}\b{UNAVAILABLE_WORDS}\b", re.IGNORECASE)),
    ("backoff_retry>=3", re.compile(rf"\bbackoff[_ -]?retry\b[^.;\n]{{0,80}}\b{UNAVAILABLE_WORDS}\b", re.IGNORECASE)),
    ("model_fallback", re.compile(rf"\bmodel[_ -]?fallback\b[^.;\n]{{0,80}}\b{UNAVAILABLE_WORDS}\b", re.IGNORECASE)),
)
ENV_KEY_RE = re.compile(
    r"\b(?:missing|required|unset|not found|환경변수|env(?:ironment)?(?: variable)?)[^A-Z0-9_]{0,80}"
    r"([A-Z][A-Z0-9_]{2,})\b",
    re.IGNORECASE,
)
SECRETISH_KEY_RE = re.compile(r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|BEARER)", re.IGNORECASE)
SENSITIVE_FIELD_RE = re.compile(
    r"(?:secret|token|credential|password|body|prompt|source_text|raw_text|generated|response_text|private_key)",
    re.IGNORECASE,
)


def read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_json_value(raw: str | None) -> Any:
    if not raw:
        return None
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None
    path = Path(raw)
    try:
        is_file = path.is_file()
    except OSError:
        is_file = False
    if is_file:
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def load_python_module(path: Path, module_name: str) -> Any | None:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, resolved)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_adapter(adapter: Any | None, function_name: str, **kwargs: Any) -> tuple[Any, str | None]:
    if adapter is None or not hasattr(adapter, function_name):
        return None, None
    function = getattr(adapter, function_name)
    try:
        signature = inspect.signature(function)
        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        if accepts_kwargs:
            return function(**kwargs), None
        accepted = {key: value for key, value in kwargs.items() if key in signature.parameters}
        return function(**accepted), None
    except TypeError:
        try:
            return function(), None
        except Exception as exc:  # pragma: no cover - adapter-owned code
            return None, f"{function_name}_failed:{type(exc).__name__}"
    except Exception as exc:  # pragma: no cover - adapter-owned code
        return None, f"{function_name}_failed:{type(exc).__name__}"


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present"}
    return False


def compact_safe_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "<truncated>"
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) > 200:
            return text[:200] + "..."
        return text
    if isinstance(value, list):
        return [compact_safe_value(item, depth=depth + 1) for item in value[:8]]
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for key, child in value.items():
            text_key = str(key)
            if SENSITIVE_FIELD_RE.search(text_key):
                compact[text_key] = "<redacted>"
                continue
            compact[text_key] = compact_safe_value(child, depth=depth + 1)
            if len(compact) >= 24:
                break
        return compact
    return str(type(value).__name__)


def normalize_stage_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    return text or None


def normalize_execution_stage_ladder(value: Any) -> tuple[list[str], str]:
    if value is None:
        return [], "not_provided"
    source = value
    if isinstance(value, dict):
        for key in ("execution_stage_ladder", "stage_ladder", "stages", "ladder"):
            if key in value:
                source = value.get(key)
                break
    stages: list[str] = []
    if isinstance(source, list):
        for item in source:
            stage = item.get("name") if isinstance(item, dict) else item
            normalized = normalize_stage_name(stage)
            if normalized and normalized not in stages:
                stages.append(normalized)
    elif isinstance(source, dict):
        raw_stages = source.get("stages") or source.get("execution_stage_ladder") or source.get("stage_ladder")
        if isinstance(raw_stages, list):
            return normalize_execution_stage_ladder(raw_stages)
        for key in sorted(source, key=lambda item: str(source[item]) if isinstance(source.get(item), int) else str(item)):
            normalized = normalize_stage_name(key)
            if normalized and normalized not in stages:
                stages.append(normalized)
    elif isinstance(source, str):
        for item in re.split(r"[,>\s]+", source):
            normalized = normalize_stage_name(item)
            if normalized and normalized not in stages:
                stages.append(normalized)
    return stages, "provided" if stages else "malformed"


def safe_scalar_diagnostics(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        source = value.get("post_failure_diagnostics") if isinstance(value.get("post_failure_diagnostics"), dict) else value
    else:
        source = {}
    diagnostics: dict[str, Any] = {}
    if not isinstance(source, dict):
        return diagnostics
    for key, child in source.items():
        text_key = str(key)
        if SENSITIVE_FIELD_RE.search(text_key):
            continue
        if child is None or isinstance(child, (bool, int, float)):
            diagnostics[text_key] = child
        elif isinstance(child, str):
            text = child.strip()
            if text and len(text) <= 120:
                diagnostics[text_key] = text
        elif isinstance(child, (list, tuple, set)):
            diagnostics[f"{text_key}_count"] = len(child)
        elif isinstance(child, dict):
            diagnostics[f"{text_key}_field_count"] = len(child)
        if len(diagnostics) >= 24:
            break
    return diagnostics


def next_failure_stage(stages: list[str], last_successful_stage: str | None) -> str | None:
    if not stages or not last_successful_stage:
        return None
    if last_successful_stage not in stages:
        return None
    index = stages.index(last_successful_stage)
    if index + 1 >= len(stages):
        return None
    return stages[index + 1]


def normalize_gate_selfcheck(
    value: Any,
    *,
    gate_id: str | None,
    repo_owned_pre_exec_blocker: bool,
    adapter_error: str | None = None,
) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("gate_selfcheck"), dict):
        value = value["gate_selfcheck"]
    if not isinstance(value, dict):
        return {
            "gate_id": gate_id,
            "status": "not_provided" if adapter_error is None else "error",
            "adapter_error": adapter_error,
            "classification": None,
            "constrains_failure_classification": False,
        }
    blocked_pre_exec = bool_value(value.get("blocked_pre_exec") or value.get("pre_exec_blocked"))
    repo_owned_confirmed = repo_owned_pre_exec_blocker or bool_value(
        value.get("repo_owned_pre_exec_blocker")
        or value.get("repo_owned_source_blocker")
        or value.get("repo_owned_blocker")
    )
    contradicting_evidence = value.get("contradicting_evidence")
    if not isinstance(contradicting_evidence, list):
        contradicting_evidence = []
    trusted_evidence_source = value.get("trusted_evidence_source") or value.get("alternative_evidence_source")
    prior_pass_observed = bool_value(value.get("prior_pass_observed"))
    has_contradiction = bool(contradicting_evidence) or bool(trusted_evidence_source) or prior_pass_observed
    classification = (
        "self_inflicted_gate_defect"
        if blocked_pre_exec and repo_owned_confirmed and has_contradiction
        else None
    )
    status = "classify" if classification else ("warn" if blocked_pre_exec and has_contradiction else "pass")
    if blocked_pre_exec and has_contradiction and not repo_owned_confirmed:
        status = "warn_missing_repo_owned_confirmation"
    return {
        "gate_id": gate_id or value.get("gate_id"),
        "status": status,
        "blocked_pre_exec": blocked_pre_exec,
        "repo_owned_pre_exec_blocker": repo_owned_confirmed,
        "contradicting_evidence": compact_safe_value(contradicting_evidence),
        "trusted_evidence_source": compact_safe_value(trusted_evidence_source),
        "prior_pass_observed": prior_pass_observed,
        "classification": classification,
        "alternative_evidence_source": compact_safe_value(trusted_evidence_source) if classification else None,
        "constrains_failure_classification": bool(classification),
        "adapter_error": adapter_error,
    }


def scrub_path(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    try:
        home = str(Path.home())
        if text.startswith(home):
            text = "~" + text[len(home) :]
    except RuntimeError:
        pass
    return text


def traceback_last_frame(text: str) -> dict[str, Any] | None:
    matches = list(TRACEBACK_FILE_RE.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    return {
        "file": scrub_path(match.group(1)),
        "line": int(match.group(2)),
        "function": match.group(3) or None,
    }


def exception_class(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped:
            continue
        match = EXCEPTION_RE.match(stripped)
        if match:
            return match.group(1)
    return None


def http_statuses(text: str) -> list[int]:
    values: list[int] = []
    for match in HTTP_STATUS_RE.finditer(text):
        status = int(match.group(1))
        if status not in values:
            values.append(status)
    return values[:8]


def provider_request_count(text: str) -> int | None:
    matches = list(PROVIDER_REQUEST_COUNT_RE.finditer(text))
    if not matches:
        return None
    return int(matches[-1].group(1))


def provider_status(text: str) -> str | None:
    matches = list(PROVIDER_STATUS_RE.finditer(text))
    if not matches:
        return None
    return matches[-1].group(1).lower()


def provider_failure_class(text: str, statuses: list[int]) -> str | None:
    lowered = text.lower()
    status = provider_status(text)
    if status:
        if "empty" in status:
            return "empty"
        if "parse" in status or "malformed" in status:
            return "parse"
        if "timeout" in status:
            return "timeout"
        if "rate" in status:
            return "rate_limit"
        if "incomplete" in status:
            return "incomplete"
        if "auth" in status:
            return "auth"
    if any(code == 429 for code in statuses):
        return "rate_limit"
    if any(code in {408, 504} for code in statuses):
        return "timeout"
    if any(500 <= code <= 599 for code in statuses):
        return "transient"
    if any(code in {401, 403} for code in statuses):
        return "auth"
    if any(token in lowered for token in ("empty response", "empty provider", "blank response", "provider_response_empty=true")):
        return "empty"
    if any(token in lowered for token in ("parse error", "jsondecodeerror", "malformed response", "provider_response_parse_failed=true")):
        return "parse"
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout"
    if "rate limit" in lowered or "too many requests" in lowered:
        return "rate_limit"
    return None


def mitigations_attempted(text: str, request_count: int | None) -> list[str]:
    attempted: list[str] = []
    for name, pattern in MITIGATION_PATTERNS:
        if pattern.search(text) and name not in attempted:
            attempted.append(name)
    if request_count is not None and request_count >= 3 and "backoff_retry>=3" not in attempted:
        attempted.append("backoff_retry>=3")
    return attempted


def mitigations_unavailable(text: str) -> list[str]:
    names: list[str] = []
    for name, pattern in MITIGATION_UNAVAILABLE_PATTERNS:
        if pattern.search(text) and name not in names:
            names.append(name)
    return names


def missing_env_key_names(text: str, allow_secret_names: bool) -> list[str]:
    names: list[str] = []
    for match in ENV_KEY_RE.finditer(text):
        name = match.group(1).upper()
        if SECRETISH_KEY_RE.search(name) and not allow_secret_names:
            name = "<redacted_secret_env_key_name>"
        if name not in names:
            names.append(name)
    return names[:16]


def classify_error(exit_code: int | None, exc: str | None, text: str) -> str:
    if exc:
        return "runtime_exception"
    if exit_code is not None and exit_code != 0:
        return "nonzero_exit"
    if "traceback (most recent call last)" in text.lower():
        return "runtime_exception"
    return "unknown_failure"


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
