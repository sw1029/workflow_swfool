from __future__ import annotations

import re
from typing import Any

from .values import boolish, first_mapping, first_value, number_value

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
    normalized = value.strip()
    return normalized if normalized else None


def mitigation_list(value: Any) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, list):
        raw_items = [str(item) for item in value if item is not None]
    elif isinstance(value, str):
        raw_items = re.split(r"[,;\s]+", value)
    names = [name for item in raw_items if (name := normalized_mitigation_name(item))]
    return sorted(set(names))


def provider_mitigation_gate(
    value: dict[str, Any],
    failure_class: str | None,
    request_count: int | None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    retry_policy = (policy or {}).get("provider_retry_policy") or {}
    policy_active = bool(retry_policy.get("supplied"))
    requirements = retry_policy.get("mitigation_requirements") or {}
    required = sorted(requirements.get(failure_class or "", set()))
    covered = set(attempted) | set(unavailable)
    missing = sorted(set(required) - covered)
    transient_failure = failure_class in set(retry_policy.get("transient_failure_classes") or [])
    return {
        "mitigations_attempted": attempted,
        "mitigations_unavailable": unavailable,
        "required_mitigations": required,
        "missing_mitigations": missing,
        "mitigation_required": transient_failure and bool(required),
        "mitigation_exhausted": transient_failure and bool(required) and not missing,
        "evaluation_status": "evaluated" if policy_active else "not_evaluated",
    }


def provider_reattempt_gate(
    value: dict[str, Any],
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit_gate = first_mapping(
        value,
        (
            "provider_reattempt_gate",
            "anti_loop_progress_gate.provider_reattempt_gate",
            "result.provider_reattempt_gate",
        ),
    )
    if explicit_gate:
        return {
            **explicit_gate,
            "evaluation_status": explicit_gate.get("evaluation_status") or "evaluated",
        }
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
    retry_policy = (policy or {}).get("provider_retry_policy") or {}
    policy_active = bool(retry_policy.get("supplied"))
    mitigation = provider_mitigation_gate(value, failure_class, request_count, policy)
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
    transient_failure = failure_class in set(retry_policy.get("transient_failure_classes") or [])
    permanent_failure = failure_class in set(retry_policy.get("permanent_failure_classes") or [])
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
        "provider_terminal_seal_allowed": policy_active and seal_allowed,
        "provider_terminal_seal_denied_reason": (
            "provider_retry_policy_not_supplied"
            if not policy_active
            else ("provider_failure_mitigation_unexhausted" if mitigation_missing else None)
        ),
        "evaluation_status": "evaluated" if policy_active else "not_evaluated",
    }
