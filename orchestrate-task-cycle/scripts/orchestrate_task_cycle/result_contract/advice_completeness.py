"""Exact active-advice packet and clause-consumption completeness checks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from .common import add, advice_handling_rationale_present, first_present
from .receipts import _full_sha256, _opaque_scalar, _positive_decision_claim


PACKET_PATHS = (
    "active_advice_packet",
    "expected_advice_packet",
    "external_advice_packet",
    "advice_packet",
    "result.active_advice_packet",
)
EXPECTED_ID_KEYS = (
    "canonical_actionable_clause_ids",
    "actionable_clause_ids",
    "expected_actionable_clause_ids",
    "expected_advice_clause_ids",
)


@dataclass(frozen=True)
class AdviceExpectation:
    packet: dict[str, Any]
    clause_ids: frozenset[str]
    packet_digest: str
    source_by_clause: dict[str, Any]
    severity: str


@dataclass(frozen=True)
class BasisProjection:
    clause_ids: frozenset[str]
    source_by_clause: dict[str, str]
    source_by_advice: dict[str, str]
    duplicate_clause_ids: frozenset[str]
    valid: bool


def _at_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _packet(
    result: dict[str, Any], context: dict[str, Any] | None
) -> dict[str, Any] | None:
    for container in (result, context):
        if not isinstance(container, dict):
            continue
        for path in PACKET_PATHS:
            candidate = _at_path(container, path)
            if isinstance(candidate, dict):
                return candidate
        if any(key in container for key in EXPECTED_ID_KEYS):
            return container
    return None


def _declared(packet: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in packet:
            return packet[key]
    return None


def _normalized_digest(value: Any) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def _binding_digest(binding: dict[str, Any]) -> str:
    encoded = json.dumps(
        binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _basis_projection(binding: Any) -> BasisProjection:
    if not isinstance(binding, dict):
        return BasisProjection(frozenset(), {}, {}, frozenset(), True)
    items = binding.get("active_items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        return BasisProjection(frozenset(), {}, {}, frozenset(), False)
    clause_ids: set[str] = set()
    duplicate_clause_ids: set[str] = set()
    source_by_clause: dict[str, str] = {}
    source_by_advice: dict[str, str] = {}
    valid = True
    for item in items:
        raw = item.get("actionable_clause_ids")
        advice_id = item.get("advice_id")
        source_digest = _normalized_digest(item.get("source_digest"))
        if (
            not _opaque_scalar(advice_id)
            or not _full_sha256(source_digest)
            or not isinstance(raw, list)
            or not all(_opaque_scalar(value) for value in raw)
        ):
            valid = False
            continue
        source_by_advice[str(advice_id).strip()] = source_digest
        for value in raw:
            clause_id = str(value).strip()
            if clause_id in clause_ids:
                duplicate_clause_ids.add(clause_id)
            clause_ids.add(clause_id)
            source_by_clause.setdefault(clause_id, source_digest)
            if source_by_clause[clause_id] != source_digest:
                valid = False
    return BasisProjection(
        frozenset(clause_ids),
        source_by_clause,
        source_by_advice,
        frozenset(duplicate_clause_ids),
        valid,
    )


def _digest_map(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, str] = {}
    for key, digest in value.items():
        if not _opaque_scalar(key) or not _full_sha256(digest):
            return None
        normalized[str(key).strip()] = _normalized_digest(digest)
    return normalized


def _positive_advice_use(
    target: str, result: dict[str, Any], rows: list[dict[str, Any]]
) -> bool:
    positive_state = any(
        str(row.get("state") or "").strip().lower() in {"wired", "verified"}
        for row in rows
    )
    explicit_use = first_present(
        result,
        [
            "used_advice",
            "advice_applied",
            "advice_consumed",
            "result.used_advice",
        ],
    )
    return bool(
        positive_state
        or _positive_decision_claim(target, result)
        or (explicit_use and not advice_handling_rationale_present(result))
    )


def _expectation(
    target: str,
    result: dict[str, Any],
    context: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    base_severity: str,
    findings: list[dict[str, Any]],
) -> AdviceExpectation | None:
    packet = _packet(result, context)
    if packet is None:
        return None
    severity = (
        "block"
        if base_severity == "block" or _positive_advice_use(target, result, rows)
        else "warn"
    )
    applicability = (
        str(packet.get("applicability") or packet.get("advice_applicability") or "")
        .strip()
        .lower()
    )
    if applicability in {"not_applicable", "n/a", "na"}:
        binding = packet.get("advice_packet_digest_basis")
        projection = _basis_projection(binding)
        basis_applicability = (
            str(binding.get("applicability") or "").strip().lower()
            if isinstance(binding, dict)
            else ""
        )
        if binding is not None and (
            not projection.valid
            or projection.clause_ids
            or basis_applicability not in {"not_applicable", "n/a", "na"}
        ):
            add(
                findings,
                severity,
                "active_advice_packet_applicability_mismatch",
                "A not-applicable packet cannot contradict an applicable or actionable digest basis.",
            )
        return None
    raw_expected = _declared(packet, EXPECTED_ID_KEYS)
    if raw_expected is None:
        return None
    raw_is_valid = isinstance(raw_expected, list) and all(
        _opaque_scalar(value) for value in raw_expected
    )
    expected_values = (
        [str(value).strip() for value in raw_expected if _opaque_scalar(value)]
        if isinstance(raw_expected, list)
        else []
    )
    expected_counts = Counter(expected_values)
    expected_ids = frozenset(expected_values)
    if (
        not raw_is_valid
        or not expected_ids
        or any(count > 1 for count in expected_counts.values())
    ):
        add(
            findings,
            severity,
            "active_advice_expected_clause_set_invalid",
            "Applicable active advice must expose one non-empty, unique opaque actionable clause ID set.",
            {
                "expected_clause_count": len(expected_ids),
                "duplicate_expected_clause_ids": sorted(
                    clause_id
                    for clause_id, count in expected_counts.items()
                    if count > 1
                ),
            },
        )
        if not expected_ids:
            return None
    alias_conflict = False
    for key in EXPECTED_ID_KEYS:
        if key not in packet:
            continue
        alias = packet[key]
        alias_conflict = alias_conflict or not (
            isinstance(alias, list)
            and all(_opaque_scalar(value) for value in alias)
            and {str(value).strip() for value in alias} == expected_ids
            and len(alias) == len(expected_ids)
        )
    if alias_conflict:
        add(
            findings,
            severity,
            "active_advice_packet_clause_set_alias_conflict",
            "All declared actionable clause-set aliases must expose the same exact set.",
        )
    source_digests = packet.get("clause_source_digests")
    return AdviceExpectation(
        packet=packet,
        clause_ids=expected_ids,
        packet_digest=_normalized_digest(
            packet.get("advice_packet_digest") or packet.get("packet_digest")
        ),
        source_by_clause=(source_digests if isinstance(source_digests, dict) else {}),
        severity=severity,
    )


def _validate_packet_contract(
    expectation: AdviceExpectation, findings: list[dict[str, Any]]
) -> None:
    packet = expectation.packet
    if not _full_sha256(expectation.packet_digest):
        add(
            findings,
            expectation.severity,
            "active_advice_packet_digest_invalid",
            "An applicable expected advice packet requires a full content digest.",
        )
    binding = packet.get("advice_packet_digest_basis")
    projection = _basis_projection(binding)
    basis_applicability = (
        str(binding.get("applicability") or "").strip().lower()
        if isinstance(binding, dict)
        else ""
    )
    packet_applicability = (
        str(packet.get("applicability") or packet.get("advice_applicability") or "")
        .strip()
        .lower()
    )
    if binding is not None and (
        basis_applicability != packet_applicability
        or basis_applicability != "applicable"
    ):
        add(
            findings,
            expectation.severity,
            "active_advice_packet_applicability_mismatch",
            "The packet applicability must equal its digest-basis applicability and actionable content.",
        )
    if binding is not None and (
        not projection.valid or projection.clause_ids != expectation.clause_ids
    ):
        add(
            findings,
            expectation.severity,
            "active_advice_packet_clause_set_mismatch",
            "The exposed actionable clause set must equal the digest-basis clause set.",
            {
                "missing_from_exposed_set": sorted(
                    projection.clause_ids - expectation.clause_ids
                ),
                "external_to_digest_basis": sorted(
                    expectation.clause_ids - projection.clause_ids
                ),
            },
        )
    if binding is not None and (
        not isinstance(binding, dict)
        or expectation.packet_digest != _binding_digest(binding)
    ):
        add(
            findings,
            expectation.severity,
            "active_advice_packet_digest_mismatch",
            "The expected advice packet digest does not bind its supplied digest basis.",
        )
    exposed_clause_sources = _digest_map(packet.get("clause_source_digests"))
    exposed_advice_sources = _digest_map(packet.get("source_digests"))
    if binding is not None and (
        exposed_clause_sources != projection.source_by_clause
        or exposed_advice_sources != projection.source_by_advice
    ):
        add(
            findings,
            expectation.severity,
            "active_advice_packet_source_digest_mismatch",
            "The exposed clause/advice source digests must equal the digest-basis source projection.",
        )
    duplicate_packet_ids = packet.get("duplicate_actionable_clause_ids")
    declared_duplicates = (
        {str(value).strip() for value in duplicate_packet_ids if _opaque_scalar(value)}
        if isinstance(duplicate_packet_ids, list)
        else set()
    )
    duplicate_ids = declared_duplicates | set(projection.duplicate_clause_ids)
    if duplicate_ids:
        add(
            findings,
            expectation.severity,
            "active_advice_packet_clause_identity_conflict",
            "One actionable clause ID is owned by multiple active advice items.",
            {"clause_ids": sorted(duplicate_ids)},
        )


def _observed_clause_ids(rows: list[dict[str, Any]]) -> list[str]:
    return [
        str(row.get("clause_id") or row.get("advice_clause_id") or "").strip()
        for row in rows
        if _opaque_scalar(row.get("clause_id") or row.get("advice_clause_id"))
    ]


def _validate_row_set(
    expectation: AdviceExpectation,
    rows: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    observed_values = _observed_clause_ids(rows)
    observed_counts = Counter(observed_values)
    observed_ids = set(observed_values)
    if not rows:
        add(
            findings,
            expectation.severity,
            "advice_consumption_rows_missing",
            "The active expected advice clause set has no consumption rows.",
            {"expected_clause_ids": sorted(expectation.clause_ids)},
        )
    defects = (
        (
            "advice_consumption_clause_missing",
            "Advice consumption rows do not cover every expected actionable clause.",
            sorted(expectation.clause_ids - observed_ids),
        ),
        (
            "advice_consumption_clause_duplicate",
            "Advice consumption must contain exactly one row per expected clause.",
            sorted(
                clause_id for clause_id, count in observed_counts.items() if count > 1
            ),
        ),
        (
            "advice_consumption_external_clause",
            "Advice consumption contains clause IDs outside the active expected packet.",
            sorted(observed_ids - expectation.clause_ids),
        ),
    )
    for code, message, clause_ids in defects:
        if clause_ids:
            add(
                findings,
                expectation.severity,
                code,
                message,
                {"clause_ids": clause_ids},
            )


def _validate_row_digest_bindings(
    expectation: AdviceExpectation,
    rows: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> None:
    for row in rows:
        clause_id = str(
            row.get("clause_id") or row.get("advice_clause_id") or ""
        ).strip()
        if clause_id not in expectation.clause_ids:
            continue
        observed_packet_digest = _normalized_digest(
            row.get("advice_packet_digest") or row.get("packet_digest")
        )
        if (
            not _full_sha256(expectation.packet_digest)
            or observed_packet_digest != expectation.packet_digest
        ):
            add(
                findings,
                expectation.severity,
                "advice_consumption_packet_digest_mismatch",
                "Every expected clause-consumption row must echo the active packet digest.",
                {"clause_id": clause_id},
            )
        expected_source_digest = _normalized_digest(
            expectation.source_by_clause.get(clause_id)
        )
        if not expected_source_digest:
            continue
        observed_source_digest = _normalized_digest(
            row.get("advice_source_digest") or row.get("source_digest")
        )
        if (
            not _full_sha256(expected_source_digest)
            or observed_source_digest != expected_source_digest
        ):
            add(
                findings,
                expectation.severity,
                "advice_consumption_source_digest_mismatch",
                "Clause consumption must echo the source digest assigned by the active packet.",
                {"clause_id": clause_id},
            )


def validate_expected_advice_completeness(
    target: str,
    result: dict[str, Any],
    context: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    base_severity: str,
    findings: list[dict[str, Any]],
) -> None:
    """Require an exact packet-bound row set only when expectations are supplied."""

    expectation = _expectation(target, result, context, rows, base_severity, findings)
    if expectation is None:
        return
    _validate_packet_contract(expectation, findings)
    _validate_row_set(expectation, rows, findings)
    _validate_row_digest_bindings(expectation, rows, findings)


__all__ = ("validate_expected_advice_completeness",)
