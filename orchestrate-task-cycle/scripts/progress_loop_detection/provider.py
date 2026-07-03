from __future__ import annotations

import re
from typing import Any

from .constants import *
from .values import *

def provider_failure_class(value: dict[str, Any]) -> str | None:
    explicit = first_value(
        value,
        (
            "failure_class",
            "failure_autopsy.failure_class",
            "failure_autopsy_packet.failure_class",
            "provider_failure_class",
            "provider.failure_class",
            "run.failure_autopsy.failure_class",
            "result.failure_autopsy.failure_class",
        ),
    )
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()
    http_status = first_value(value, ("http_status", "failure_autopsy.http_status", "result.failure_autopsy.http_status"))
    statuses = http_status if isinstance(http_status, list) else [http_status]
    for status in statuses:
        code = number_value(status)
        if code == 429:
            return "rate_limit"
        if code in {408, 504}:
            return "timeout"
        if code is not None and 500 <= code <= 599:
            return "transient"
        if code in {401, 403}:
            return "auth"
    if boolish(first_value(value, ("provider_response_empty", "empty_provider_response", "result.provider_response_empty"))):
        return "empty"
    if boolish(first_value(value, ("provider_response_parse_failed", "provider_parse_failed", "result.provider_response_parse_failed"))):
        return "parse"
    status = first_value(value, ("provider_status", "provider.status", "runtime_status", "result.provider_status"))
    if isinstance(status, str):
        lowered = status.lower()
        if "empty" in lowered:
            return "empty"
        if "parse" in lowered or "malformed" in lowered:
            return "parse"
        if "timeout" in lowered:
            return "timeout"
        if "rate" in lowered:
            return "rate_limit"
        if "incomplete" in lowered:
            return "incomplete"
        if "auth" in lowered:
            return "auth"
    return None


def normalized_mitigation_name(value: str) -> str | None:
    lowered = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not lowered:
        return None
    if lowered in {"structured_output", "json_schema", "response_format"}:
        return "structured_output"
    if lowered in {"window_reduce", "window_reduced", "smaller_window"}:
        return "window_reduce"
    if lowered in {"timeout_budget_increase", "timeout_increase", "timeout_extended", "longer_timeout"}:
        return "timeout_budget_increase"
    if lowered in {"backoff_retry>=3", "backoff_retry_3", "retry>=3", "retries>=3"}:
        return "backoff_retry>=3"
    if lowered in {"model_fallback", "fallback_model", "alternate_model"}:
        return "model_fallback"
    if "structured" in lowered:
        return "structured_output"
    if "window" in lowered and ("reduce" in lowered or "smaller" in lowered):
        return "window_reduce"
    if "timeout" in lowered and any(token in lowered for token in ("increase", "extend", "budget", "longer")):
        return "timeout_budget_increase"
    if "backoff" in lowered or "retry" in lowered:
        return "backoff_retry>=3" if any(token in lowered for token in (">=3", "_3", "3")) else None
    if "model" in lowered and "fallback" in lowered:
        return "model_fallback"
    return None


def mitigation_list(value: Any) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, list):
        raw_items = [str(item) for item in value if item is not None]
    elif isinstance(value, str):
        raw_items = re.split(r"[,;\s]+", value)
    names = [name for item in raw_items if (name := normalized_mitigation_name(item))]
    return sorted(set(names))


def provider_mitigation_gate(value: dict[str, Any], failure_class: str | None, request_count: int | None) -> dict[str, Any]:
    attempted = mitigation_list(
        first_value(
            value,
            (
                "mitigations_attempted",
                "failure_autopsy.mitigations_attempted",
                "failure_autopsy_packet.mitigations_attempted",
                "run.failure_autopsy.mitigations_attempted",
                "result.failure_autopsy.mitigations_attempted",
            ),
        )
    )
    unavailable = mitigation_list(
        first_value(
            value,
            (
                "mitigations_unavailable",
                "failure_autopsy.mitigations_unavailable",
                "failure_autopsy_packet.mitigations_unavailable",
                "run.failure_autopsy.mitigations_unavailable",
                "result.failure_autopsy.mitigations_unavailable",
            ),
        )
    )
    if request_count is not None and request_count >= 3:
        attempted = sorted(set([*attempted, "backoff_retry>=3"]))
    required = sorted(MITIGATION_REQUIREMENTS.get(failure_class or "", set()))
    covered = set(attempted) | set(unavailable)
    missing = sorted(set(required) - covered)
    transient_failure = failure_class in TRANSIENT_PROVIDER_FAILURE_CLASSES
    return {
        "mitigations_attempted": attempted,
        "mitigations_unavailable": unavailable,
        "required_mitigations": required,
        "missing_mitigations": missing,
        "mitigation_required": transient_failure and bool(required),
        "mitigation_exhausted": transient_failure and bool(required) and not missing,
    }


def provider_reattempt_gate(value: dict[str, Any]) -> dict[str, Any]:
    request_count = number_value(
        first_value(
            value,
            (
                "provider_request_count",
                "provider.request_count",
                "failure_autopsy.provider_request_count",
                "failure_autopsy_packet.provider_request_count",
                "run.provider_request_count",
                "result.provider_request_count",
            ),
        )
    )
    failure_class = provider_failure_class(value)
    mitigation = provider_mitigation_gate(value, failure_class, request_count)
    authority_allows_retry = boolish(
        first_value(
            value,
            (
                "authority_allows_retry",
                "provider_retry_allowed",
                "retry_allowed",
                "authority.provider_retry_allowed",
                "authority_policy.provider_retry_allowed",
                "failure_autopsy_packet.authority_allows_retry",
                "loop_breaker_packet.authority_allows_retry",
            ),
        )
    )
    transient_failure = failure_class in TRANSIENT_PROVIDER_FAILURE_CLASSES
    permanent_failure = failure_class in PERMANENT_PROVIDER_FAILURE_CLASSES
    mitigation_missing = transient_failure and mitigation["mitigation_required"] and not mitigation["mitigation_exhausted"]
    reattempt_required = transient_failure and mitigation_missing and authority_allows_retry
    seal_allowed = permanent_failure or not mitigation_missing
    return {
        "provider_request_count": request_count,
        "failure_class": failure_class,
        "authority_allows_retry": authority_allows_retry,
        "transient_failure": transient_failure,
        "permanent_failure": permanent_failure,
        **mitigation,
        "provider_mitigation_required": mitigation_missing,
        "provider_reattempt_required": reattempt_required,
        "provider_retreat_allowed": permanent_failure or (transient_failure and not mitigation_missing),
        "provider_terminal_seal_allowed": seal_allowed,
        "provider_terminal_seal_denied_reason": "provider_failure_mitigation_unexhausted" if mitigation_missing else None,
    }
