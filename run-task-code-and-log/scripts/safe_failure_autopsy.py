#!/usr/bin/env python3
from __future__ import annotations

import argparse
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


def read_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


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
) -> dict[str, Any]:
    combined = "\n".join(part for part in (stdout_text, stderr_text) if part)
    exc = exception_class(combined)
    frame = traceback_last_frame(combined)
    statuses = http_statuses(combined)
    failure_class = provider_failure_class(combined, statuses)
    request_count = provider_request_count(combined)
    unavailable = mitigations_unavailable(combined)
    attempted = [item for item in mitigations_attempted(combined, request_count) if item not in unavailable]
    return {
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract safe scalar diagnostics from failed command output.")
    parser.add_argument("--stdout-path")
    parser.add_argument("--stderr-path")
    parser.add_argument("--stdout-text")
    parser.add_argument("--stderr-text")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--command")
    parser.add_argument("--output")
    parser.add_argument(
        "--allow-secret-env-key-names",
        action="store_true",
        help="Allow exact secret-like env var names; values are never emitted.",
    )
    args = parser.parse_args(argv)

    stdout_text = args.stdout_text if args.stdout_text is not None else read_text(Path(args.stdout_path) if args.stdout_path else None)
    stderr_text = args.stderr_text if args.stderr_text is not None else read_text(Path(args.stderr_path) if args.stderr_path else None)
    result = autopsy(stdout_text, stderr_text, args.exit_code, args.command, args.allow_secret_env_key_names)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
