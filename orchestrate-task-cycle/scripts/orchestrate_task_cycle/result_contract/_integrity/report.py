from __future__ import annotations

import json
from typing import Any

from .core import (
    _report_root_name,
    collect_report_roots,
    collect_terminal_key_values,
    identity_divergence_evidence,
    is_report_context_key,
    opaque_binding_evidence,
    projected_field_ids,
    projection_artifact_id,
    projection_fingerprint,
    report_integrity_required,
    scoped_report_roots,
)


RootIdentity = tuple[str, Any, str | None, str | None]


def cross_report_projection_values(
    data: dict[str, Any],
    roots: list[tuple[str, Any]],
) -> tuple[
    str | None, list[str], dict[str, list[tuple[str, str, Any]]], list[dict[str, Any]]
]:
    top_level_fingerprint = projection_fingerprint(data)
    top_level_artifact_id = projection_artifact_id(data)
    root_identities = [
        (path, root, projection_artifact_id(root), projection_fingerprint(root))
        for path, root in roots
    ]
    artifact_groups: dict[str, list[RootIdentity]] = {}
    for identity in root_identities:
        if identity[2]:
            artifact_groups.setdefault(identity[2], []).append(identity)

    canonical_artifact_id, canonical_fingerprint = _canonical_projection_identity(
        top_level_artifact_id,
        top_level_fingerprint,
        root_identities,
        artifact_groups,
    )
    identity_divergences = _identity_divergences(
        data,
        top_level_artifact_id,
        top_level_fingerprint,
        root_identities,
        artifact_groups,
    )

    if not canonical_fingerprint and not canonical_artifact_id:
        return None, [], {}, identity_divergences

    scoped_roots = _scoped_projection_roots(
        root_identities, canonical_artifact_id, canonical_fingerprint
    )
    field_ids = projected_field_ids(data, scoped_roots)
    if not field_ids:
        return canonical_fingerprint, [], {}, identity_divergences
    aggregated: dict[str, list[tuple[str, str, Any]]] = {}
    for root_path, root in scoped_roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for field_id in field_ids:
            aggregated.setdefault(field_id, []).extend(
                terminal_values.get(field_id, [])
            )
    return canonical_fingerprint, field_ids, aggregated, identity_divergences


def _canonical_projection_identity(
    top_artifact_id: str | None,
    top_fingerprint: str | None,
    identities: list[RootIdentity],
    artifact_groups: dict[str, list[RootIdentity]],
) -> tuple[str | None, str | None]:
    canonical_artifact_id = top_artifact_id
    canonical_fingerprint = top_fingerprint
    if not top_artifact_id and not top_fingerprint:
        shared_ids = [
            artifact_id
            for artifact_id, grouped in artifact_groups.items()
            if len(grouped) >= 2
        ]
        if len(shared_ids) == 1:
            canonical_artifact_id = shared_ids[0]
    top_artifact_matched = bool(
        top_artifact_id
        and any(root_id == top_artifact_id for _, _, root_id, _ in identities)
    )
    if not top_fingerprint and not top_artifact_matched:
        fingerprints = [value for _, _, _, value in identities if value]
        if len(fingerprints) >= 2 and len(set(fingerprints)) == 1:
            canonical_fingerprint = fingerprints[0]
    return canonical_artifact_id, canonical_fingerprint


def _identity_divergences(
    data: dict[str, Any],
    top_artifact_id: str | None,
    top_fingerprint: str | None,
    identities: list[RootIdentity],
    artifact_groups: dict[str, list[RootIdentity]],
) -> list[dict[str, Any]]:
    divergences: list[dict[str, Any]] = []
    if top_artifact_id or top_fingerprint:
        for path, _, root_id, fingerprint in identities:
            artifact_conflicts = bool(
                top_artifact_id and root_id and root_id != top_artifact_id
            )
            fingerprint_conflicts = bool(
                top_fingerprint and fingerprint and fingerprint != top_fingerprint
            )
            if artifact_conflicts:
                if report_integrity_required(data) or (
                    top_fingerprint and fingerprint == top_fingerprint
                ):
                    divergences.append(
                        identity_divergence_evidence(
                            root_ref="$canonical_projection",
                            source_ref=path,
                            field_id="artifact_id",
                            canonical_value=top_artifact_id,
                            observed_value=root_id,
                        )
                    )
                continue
            if fingerprint_conflicts:
                divergences.append(
                    identity_divergence_evidence(
                        root_ref="$canonical_projection",
                        source_ref=path,
                        field_id="body_projection_fingerprint",
                        canonical_value=top_fingerprint,
                        observed_value=fingerprint,
                    )
                )
    if not top_fingerprint:
        _append_shared_artifact_divergences(
            divergences, top_artifact_id, artifact_groups
        )
    return divergences


def _append_shared_artifact_divergences(
    divergences: list[dict[str, Any]],
    top_artifact_id: str | None,
    artifact_groups: dict[str, list[RootIdentity]],
) -> None:
    artifact_ids = (
        [top_artifact_id]
        if top_artifact_id
        else [key for key, grouped in artifact_groups.items() if len(grouped) >= 2]
    )
    for artifact_id in artifact_ids:
        entries = [
            (path, json.dumps(fingerprint), fingerprint)
            for path, _, _, fingerprint in artifact_groups.get(artifact_id, [])
            if fingerprint
        ]
        if len({encoded for _, encoded, _ in entries}) <= 1:
            continue
        divergences.append(
            opaque_binding_evidence(
                root_ref="$shared_artifact_projection",
                field_id="body_projection_fingerprint",
                entries=entries,
            )
        )


def _scoped_projection_roots(
    identities: list[RootIdentity],
    canonical_artifact_id: str | None,
    canonical_fingerprint: str | None,
) -> list[tuple[str, Any]]:
    scoped: list[tuple[str, Any]] = []
    for path, root, artifact_id, fingerprint in identities:
        if not artifact_id and not fingerprint:
            continue
        artifact_matches = bool(
            canonical_artifact_id and artifact_id == canonical_artifact_id
        )
        fingerprint_matches = bool(
            canonical_fingerprint and fingerprint == canonical_fingerprint
        )
        artifact_conflicts = bool(
            canonical_artifact_id
            and artifact_id
            and artifact_id != canonical_artifact_id
        )
        fingerprint_conflicts = bool(
            canonical_fingerprint
            and fingerprint
            and fingerprint != canonical_fingerprint
        )
        if not (artifact_conflicts or fingerprint_conflicts) and (
            artifact_matches or fingerprint_matches
        ):
            scoped.append((path, root))
    return scoped


def report_key_divergences(data: dict[str, Any]) -> list[dict[str, Any]]:
    roots = collect_report_roots(data)
    if report_integrity_required(data) and not roots:
        roots = [("$", data)]
    local_roots = scoped_report_roots(data, roots)
    divergences: list[dict[str, Any]] = []
    if report_integrity_required(data) and (
        projection_artifact_id(data) or projection_fingerprint(data)
    ):
        canonical_artifact_id = projection_artifact_id(data)
        canonical_fingerprint = projection_fingerprint(data)
        for root_path, root in roots:
            root_artifact_id = projection_artifact_id(root)
            root_fingerprint = projection_fingerprint(root)
            comparable_identity = bool(
                (canonical_artifact_id and root_artifact_id)
                or (canonical_fingerprint and root_fingerprint)
            )
            if comparable_identity:
                continue
            divergences.append(
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
                            root_path,
                            json.dumps("unbound"),
                            "projection_identity_not_comparable",
                        ),
                    ],
                )
            )
    for root_path, root in local_roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for key, entries in terminal_values.items():
            unique_values = {encoded for _, encoded, _ in entries}
            if len(entries) < 2 or len(unique_values) <= 1:
                continue
            divergences.append(
                opaque_binding_evidence(
                    root_ref=root_path, field_id=key, entries=entries
                )
            )
    projection_roots = [
        (path, root)
        for path, root in roots
        if is_report_context_key(_report_root_name(path))
    ]
    _, _, cross_root_values, identity_divergences = cross_report_projection_values(
        data, projection_roots
    )
    divergences.extend(identity_divergences)
    for key, entries in cross_root_values.items():
        unique_values = {encoded for _, encoded, _ in entries}
        root_paths = {
            root_path
            for root_path, _ in projection_roots
            if any(
                path == root_path
                or path.startswith(f"{root_path}.")
                or path.startswith(f"{root_path}[")
                for path, _, _ in entries
            )
        }
        if len(root_paths) < 2 or len(unique_values) <= 1:
            continue
        divergences.append(
            opaque_binding_evidence(
                root_ref="$canonical_projection", field_id=key, entries=entries
            )
        )
    return divergences


def report_key_duplicate_matches(data: dict[str, Any]) -> list[dict[str, Any]]:
    roots = collect_report_roots(data)
    if report_integrity_required(data) and not roots:
        roots = [("$", data)]
    local_roots = scoped_report_roots(data, roots)
    duplicates: list[dict[str, Any]] = []
    for root_path, root in local_roots:
        terminal_values = collect_terminal_key_values(root, root_path)
        for key, entries in terminal_values.items():
            unique_values = {encoded for _, encoded, _ in entries}
            if len(entries) < 2 or len(unique_values) != 1:
                continue
            evidence = opaque_binding_evidence(
                root_ref=root_path, field_id=key, entries=entries
            )
            evidence["duplicate_count"] = len(entries)
            duplicates.append(evidence)
    projection_roots = [
        (path, root)
        for path, root in roots
        if is_report_context_key(_report_root_name(path))
    ]
    _, _, cross_root_values, _ = cross_report_projection_values(data, projection_roots)
    for key, entries in cross_root_values.items():
        unique_values = {encoded for _, encoded, _ in entries}
        root_paths = {
            root_path
            for root_path, _ in projection_roots
            if any(
                path == root_path
                or path.startswith(f"{root_path}.")
                or path.startswith(f"{root_path}[")
                for path, _, _ in entries
            )
        }
        if len(root_paths) < 2 or len(unique_values) != 1:
            continue
        evidence = opaque_binding_evidence(
            root_ref="$canonical_projection", field_id=key, entries=entries
        )
        evidence["duplicate_count"] = len(entries)
        duplicates.append(evidence)
    return duplicates


def scalar_leaves(value: Any, prefix: str = "") -> dict[str, Any]:
    leaves: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            leaves.update(scalar_leaves(child, child_prefix))
    elif not isinstance(value, list) and prefix:
        leaves[prefix] = value
        leaves.setdefault(prefix.rsplit(".", 1)[-1], value)
    return leaves
