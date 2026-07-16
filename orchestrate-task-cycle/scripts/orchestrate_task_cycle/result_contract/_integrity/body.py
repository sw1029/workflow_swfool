from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .core import (
    _report_root_name,
    canonical_encoded,
    collect_actual_roots,
    collect_report_roots,
    collect_terminal_key_values,
    identity_divergence_evidence,
    is_report_context_key,
    opaque_binding_evidence,
    projected_field_contract_supplied,
    projected_field_ids,
    projection_artifact_id,
    projection_fingerprint,
    report_integrity_required,
)
from .report import scalar_leaves


Root = tuple[str, dict[str, Any]]


@dataclass
class BodyComparisonContext:
    data: dict[str, Any]
    actual_roots: list[Root]
    report_roots: list[Root]
    field_ids: list[str]
    field_contract_supplied: bool
    canonical_fingerprint: str | None
    canonical_artifact_id: str | None
    divergences: list[dict[str, Any]] = field(default_factory=list)
    canonical_actual_conflicts: set[str] = field(default_factory=set)
    canonical_report_conflicts: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, data: dict[str, Any]) -> BodyComparisonContext:
        actual_roots = collect_actual_roots(data)
        report_roots = [
            (path, value)
            for path, value in collect_report_roots(data)
            if isinstance(value, dict)
            and is_report_context_key(_report_root_name(path))
        ]
        roots = [*actual_roots, *report_roots]
        return cls(
            data=data,
            actual_roots=actual_roots,
            report_roots=report_roots,
            field_ids=projected_field_ids(data, roots),
            field_contract_supplied=projected_field_contract_supplied(data, roots),
            canonical_fingerprint=projection_fingerprint(data),
            canonical_artifact_id=projection_artifact_id(data),
        )


def actual_report_body_divergences(data: dict[str, Any]) -> list[dict[str, Any]]:
    context = BodyComparisonContext.build(data)
    _validate_actual_identities(context)
    _validate_report_identities(context)
    _validate_actual_report_pairs(context)
    return context.divergences


def _validate_actual_identities(context: BodyComparisonContext) -> None:
    for actual_name, actual_value in context.actual_roots:
        artifact_id = projection_artifact_id(actual_value)
        fingerprint = projection_fingerprint(actual_value)
        if (
            context.canonical_artifact_id
            and artifact_id
            and artifact_id != context.canonical_artifact_id
        ):
            context.divergences.append(
                identity_divergence_evidence(
                    root_ref="$canonical_actual_projection",
                    source_ref=actual_name,
                    field_id="artifact_id",
                    canonical_value=context.canonical_artifact_id,
                    observed_value=artifact_id,
                )
            )
            context.canonical_actual_conflicts.add(actual_name)
        if (
            context.canonical_fingerprint
            and fingerprint
            and fingerprint != context.canonical_fingerprint
        ):
            context.divergences.append(
                identity_divergence_evidence(
                    root_ref="$canonical_actual_projection",
                    source_ref=actual_name,
                    field_id="body_projection_fingerprint",
                    canonical_value=context.canonical_fingerprint,
                    observed_value=fingerprint,
                )
            )
            context.canonical_actual_conflicts.add(actual_name)


def _validate_report_identities(context: BodyComparisonContext) -> None:
    for report_name, report_value in context.report_roots:
        artifact_id = projection_artifact_id(report_value)
        fingerprint = projection_fingerprint(report_value)
        comparable = bool(
            (context.canonical_artifact_id and artifact_id)
            or (context.canonical_fingerprint and fingerprint)
        )
        if (
            report_integrity_required(context.data)
            and (context.canonical_artifact_id or context.canonical_fingerprint)
            and not comparable
        ):
            context.divergences.append(
                opaque_binding_evidence(
                    root_ref="$required_report_identity",
                    field_id="projection_identity_binding",
                    entries=[
                        (
                            "$canonical_projection",
                            json.dumps("present"),
                            "projection_identity_present",
                        ),
                        (
                            report_name,
                            json.dumps("unbound"),
                            "projection_identity_not_comparable",
                        ),
                    ],
                )
            )
            context.canonical_report_conflicts.add(report_name)
            continue
        if _report_artifact_conflicts(context, report_name, artifact_id, fingerprint):
            continue
        if (
            context.canonical_fingerprint
            and fingerprint
            and fingerprint != context.canonical_fingerprint
        ):
            context.divergences.append(
                identity_divergence_evidence(
                    root_ref="$canonical_report_projection",
                    source_ref=report_name,
                    field_id="body_projection_fingerprint",
                    canonical_value=context.canonical_fingerprint,
                    observed_value=fingerprint,
                )
            )
            context.canonical_report_conflicts.add(report_name)


def _report_artifact_conflicts(
    context: BodyComparisonContext,
    report_name: str,
    artifact_id: str | None,
    fingerprint: str | None,
) -> bool:
    conflicts = bool(
        context.canonical_artifact_id
        and artifact_id
        and artifact_id != context.canonical_artifact_id
    )
    if not conflicts:
        return False
    if report_integrity_required(context.data) or (
        context.canonical_fingerprint and fingerprint == context.canonical_fingerprint
    ):
        context.divergences.append(
            identity_divergence_evidence(
                root_ref="$canonical_report_projection",
                source_ref=report_name,
                field_id="artifact_id",
                canonical_value=context.canonical_artifact_id,
                observed_value=artifact_id,
            )
        )
        context.canonical_report_conflicts.add(report_name)
    return True


def _validate_actual_report_pairs(context: BodyComparisonContext) -> None:
    for actual_name, actual_value in context.actual_roots:
        for report_name, report_value in context.report_roots:
            if (
                actual_name in context.canonical_actual_conflicts
                or report_name in context.canonical_report_conflicts
            ):
                continue
            if not _pair_identity_allows_comparison(
                context,
                actual_name,
                actual_value,
                report_name,
                report_value,
            ):
                continue
            _compare_pair_fields(
                context,
                actual_name,
                actual_value,
                report_name,
                report_value,
            )


def _pair_identity_allows_comparison(
    context: BodyComparisonContext,
    actual_name: str,
    actual_value: dict[str, Any],
    report_name: str,
    report_value: dict[str, Any],
) -> bool:
    actual_id = projection_artifact_id(actual_value)
    report_id = projection_artifact_id(report_value)
    actual_fp = projection_fingerprint(actual_value)
    report_fp = projection_fingerprint(report_value)
    artifact_conflicts = bool(
        (
            context.canonical_artifact_id
            and actual_id
            and actual_id != context.canonical_artifact_id
        )
        or (
            context.canonical_artifact_id
            and report_id
            and report_id != context.canonical_artifact_id
        )
        or (actual_id and report_id and actual_id != report_id)
    )
    pair_comparable = bool((actual_id and report_id) or (actual_fp and report_fp))
    if _required_pair_identity_missing(
        context, actual_name, report_name, actual_id, actual_fp, pair_comparable
    ):
        return False
    if artifact_conflicts:
        if report_integrity_required(context.data):
            context.divergences.append(
                identity_divergence_evidence(
                    root_ref=actual_name,
                    source_ref=report_name,
                    field_id="artifact_id",
                    canonical_value=actual_id
                    or context.canonical_artifact_id
                    or "present",
                    observed_value=report_id or "missing",
                )
            )
        return False
    if not _pair_is_scoped(context, actual_id, report_id, actual_fp, report_fp):
        return False
    effective_fp = actual_fp or context.canonical_fingerprint
    if effective_fp and report_fp and effective_fp != report_fp:
        context.divergences.append(
            opaque_binding_evidence(
                root_ref="$actual_report_projection",
                field_id="body_projection_fingerprint",
                entries=[
                    (actual_name, json.dumps(effective_fp), effective_fp),
                    (report_name, json.dumps(report_fp), report_fp),
                ],
            )
        )
        return False
    return True


def _required_pair_identity_missing(
    context: BodyComparisonContext,
    actual_name: str,
    report_name: str,
    actual_id: str | None,
    actual_fp: str | None,
    pair_comparable: bool,
) -> bool:
    missing = bool(
        report_integrity_required(context.data)
        and not context.canonical_artifact_id
        and not context.canonical_fingerprint
        and (actual_id or actual_fp)
        and not pair_comparable
    )
    if missing:
        context.divergences.append(
            opaque_binding_evidence(
                root_ref="$required_actual_report_identity",
                field_id="projection_identity_binding",
                entries=[
                    (
                        actual_name,
                        json.dumps("present"),
                        "actual_projection_identity_present",
                    ),
                    (
                        report_name,
                        json.dumps("unbound"),
                        "report_projection_identity_not_comparable",
                    ),
                ],
            )
        )
    return missing


def _pair_is_scoped(
    context: BodyComparisonContext,
    actual_id: str | None,
    report_id: str | None,
    actual_fp: str | None,
    report_fp: str | None,
) -> bool:
    shared_artifact = bool(actual_id and report_id and actual_id == report_id)
    top_artifact_scoped = bool(
        context.canonical_artifact_id
        and report_id == context.canonical_artifact_id
        and actual_id in {None, context.canonical_artifact_id}
    )
    shared_fingerprint = bool(actual_fp and report_fp and actual_fp == report_fp)
    top_fingerprint_scoped = bool(
        context.canonical_fingerprint
        and report_fp
        and actual_fp in {None, context.canonical_fingerprint}
    )
    return bool(
        shared_artifact
        or top_artifact_scoped
        or shared_fingerprint
        or top_fingerprint_scoped
    )


def _compare_pair_fields(
    context: BodyComparisonContext,
    actual_name: str,
    actual_value: dict[str, Any],
    report_name: str,
    report_value: dict[str, Any],
) -> None:
    actual_fields = scalar_leaves(actual_value)
    report_fields = scalar_leaves(report_value)
    if not context.field_contract_supplied:
        _compare_inferred_fields(
            context, actual_name, actual_fields, report_name, report_fields
        )
        return
    actual_terminal = collect_terminal_key_values(actual_value, actual_name)
    report_terminal = collect_terminal_key_values(report_value, report_name)
    for field_id in context.field_ids:
        actual_entries = actual_terminal.get(field_id, [])
        report_entries = report_terminal.get(field_id, [])
        _compare_declared_field(
            context,
            field_id,
            actual_name,
            actual_entries,
            report_name,
            report_entries,
        )


def _compare_inferred_fields(
    context: BodyComparisonContext,
    actual_name: str,
    actual_fields: dict[str, Any],
    report_name: str,
    report_fields: dict[str, Any],
) -> None:
    for field_id in sorted(set(actual_fields) & set(report_fields)):
        if "." not in field_id and any(
            key.endswith(f".{field_id}") for key in actual_fields
        ):
            continue
        if actual_fields[field_id] != report_fields[field_id]:
            context.divergences.append(
                opaque_binding_evidence(
                    root_ref="$actual_report_projection",
                    field_id=field_id,
                    entries=[
                        (
                            actual_name,
                            canonical_encoded(actual_fields[field_id]),
                            actual_fields[field_id],
                        ),
                        (
                            report_name,
                            canonical_encoded(report_fields[field_id]),
                            report_fields[field_id],
                        ),
                    ],
                )
            )


def _compare_declared_field(
    context: BodyComparisonContext,
    field_id: str,
    actual_name: str,
    actual_entries: list[tuple[str, str, Any]],
    report_name: str,
    report_entries: list[tuple[str, str, Any]],
) -> None:
    if not actual_entries and not report_entries:
        entries = [
            (actual_name, json.dumps("missing"), "actual_projection_field_missing"),
            (report_name, json.dumps("missing"), "report_projection_field_missing"),
        ]
    elif not actual_entries or not report_entries:
        entries = [
            (
                actual_name,
                json.dumps(bool(actual_entries)),
                "projection_field_present"
                if actual_entries
                else "projection_field_missing",
            ),
            (
                report_name,
                json.dumps(bool(report_entries)),
                "projection_field_present"
                if report_entries
                else "projection_field_missing",
            ),
        ]
    else:
        actual_values = {encoded for _, encoded, _ in actual_entries}
        report_values = {encoded for _, encoded, _ in report_entries}
        if actual_values == report_values:
            return
        entries = [*actual_entries, *report_entries]
    context.divergences.append(
        opaque_binding_evidence(
            root_ref="$actual_report_projection",
            field_id=field_id,
            entries=entries,
        )
    )
