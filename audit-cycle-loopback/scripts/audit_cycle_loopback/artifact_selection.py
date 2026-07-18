"""Artifact discovery and identity selection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .decision_identity_dimensions import (
    DIMENSION_NAMES,
    SUBJECT_FIELDS,
    DecisionIdentityProjection,
    expected_dimension_echo,
    expected_subject_echo,
    parse_decision_identity,
)

from .decision_identity_binding import explicit_legacy_aliases
from .io_utils import read_json, rel_path


def _load_json_argument(root: Path, value: str | None) -> Any:
    if not value:
        return None
    text = str(value).strip()
    if text.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    source = Path(value)
    if not source.is_absolute():
        source = root / source
    try:
        if source.is_file():
            return read_json(source)
    except OSError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _paths_from_artifact_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [
            str(
                (item.get("artifact_path_or_store_ref") or item.get("path"))
                if isinstance(item, dict)
                else item
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return []
    paths: list[str] = []
    for key in ("artifact_paths", "artifacts", "reviewed_artifacts"):
        raw = value.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            candidate = (
                item.get("artifact_path_or_store_ref") or item.get("path")
                if isinstance(item, dict)
                else item
            )
            if candidate:
                paths.append(str(candidate))
    return paths


def _artifact_ref_from_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    for key in (
        "decision_artifact_ref",
        "decision_identity",
        "artifact_ref",
        "selected_artifact_ref",
    ):
        if isinstance(value.get(key), dict):
            return dict(value[key])
    if any(
        key in value
        for key in (
            "artifact_id",
            "artifact_sha256",
            "artifact_path_or_store_ref",
            "decision_subject_id",
            "subject_digest",
        )
    ):
        return dict(value)
    return {}


def _normalize_artifact_path(root: Path, value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text or "://" in text or text.lower().startswith("sha256:"):
        return None
    path = Path(text)
    return path if path.is_absolute() else root / path


def _sha256_path(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _select_paths(
    explicit_paths: list[Path],
    ref_path: Path | None,
    store_ref: str,
    discovered_paths: list[Path],
    supplied_ref: dict[str, Any],
) -> tuple[list[Path], str]:
    if explicit_paths:
        return explicit_paths, "explicit_caller_path"
    if ref_path is not None:
        return [ref_path], str(
            supplied_ref.get("discovery_basis") or "explicit_artifact_ref"
        )
    if store_ref:
        return [], str(
            supplied_ref.get("discovery_basis") or "content_addressed_store_ref"
        )
    return discovered_paths, "discovered_candidate"


@dataclass(frozen=True)
class _PathSelection:
    discovery_value: Any
    supplied_ref: dict[str, Any]
    explicit_paths: list[Path]
    discovered_paths: list[Path]
    paths: list[Path]
    discovery_basis: str
    selected_path: Path | None
    store_ref: str
    computed_sha: str | None
    store_sha: str
    ref_matches_explicit: bool


@dataclass(frozen=True)
class _IdentitySelection:
    projection: DecisionIdentityProjection
    explicit: bool
    aliases: dict[str, Any]
    declared_sha: str
    artifact_class: str
    lane_identity: Any
    artifact_id: str
    contract_valid: bool
    exact: bool
    store_exact: bool


def _prepare_path_selection(
    root: Path,
    artifact_paths_json: str | None,
    artifact_paths: list[str],
    artifact_ref_json: str | None,
) -> _PathSelection:
    discovery_value = _load_json_argument(root, artifact_paths_json)
    supplied_ref = _artifact_ref_from_value(
        _load_json_argument(root, artifact_ref_json)
    ) or _artifact_ref_from_value(discovery_value)
    explicit_paths = [
        path
        for raw in artifact_paths
        if (path := _normalize_artifact_path(root, raw)) is not None
    ]
    discovered_paths = [
        path
        for raw in _paths_from_artifact_value(discovery_value)
        if (path := _normalize_artifact_path(root, raw)) is not None
    ]
    raw_ref = str(
        supplied_ref.get("artifact_path_or_store_ref")
        or supplied_ref.get("path")
        or ""
    ).strip()
    ref_path = _normalize_artifact_path(root, raw_ref)
    store_ref = (
        raw_ref if "://" in raw_ref or raw_ref.lower().startswith("sha256:") else ""
    )
    paths, discovery_basis = _select_paths(
        explicit_paths, ref_path, store_ref, discovered_paths, supplied_ref
    )
    paths = list(dict.fromkeys(paths))
    selected_path = paths[0] if len(paths) == 1 else None
    store_hash_match = re.search(
        r"(?:sha256[:/])([a-f0-9]{64})(?:\b|$)", store_ref.lower()
    )
    return _PathSelection(
        discovery_value=discovery_value,
        supplied_ref=supplied_ref,
        explicit_paths=explicit_paths,
        discovered_paths=discovered_paths,
        paths=paths,
        discovery_basis=discovery_basis,
        selected_path=selected_path,
        store_ref=store_ref,
        computed_sha=_sha256_path(selected_path),
        store_sha=store_hash_match.group(1) if store_hash_match else "",
        ref_matches_explicit=not (
            explicit_paths
            and ref_path is not None
            and ref_path.resolve()
            not in {path.resolve() for path in explicit_paths}
        ),
    )


def _prepare_identity_selection(
    paths: _PathSelection,
    artifact_family: str | None,
) -> _IdentitySelection:
    supplied_ref = paths.supplied_ref
    projection = parse_decision_identity(supplied_ref)
    explicit = projection.explicit
    aliases = explicit_legacy_aliases(supplied_ref) if explicit else {}
    declared_sha = str(
        projection.subject_values.get("subject_digest")
        if explicit
        else supplied_ref.get("artifact_sha256") or supplied_ref.get("sha256") or ""
    ).strip().lower().removeprefix("sha256:")
    artifact_class = str(
        aliases.get("artifact_class")
        or supplied_ref.get("artifact_class")
        or supplied_ref.get("class")
        or artifact_family
        or ""
    ).strip()
    lane_identity = (
        aliases.get("production_lane_identity")
        if explicit
        else supplied_ref.get("production_lane_identity")
    )
    if lane_identity is None and isinstance(paths.discovery_value, dict):
        lane_identity = paths.discovery_value.get("production_lane_identity")
    artifact_id = str(
        aliases.get("artifact_id") or supplied_ref.get("artifact_id") or ""
    ).strip()
    if not artifact_id and paths.computed_sha:
        artifact_id = f"artifact-{paths.computed_sha[:16]}"
    contract_valid = bool(
        explicit
        and not projection.issues
        and projection.subject_values.get("freshness_status") == "current"
        and all(
            isinstance(supplied_ref.get(name), dict)
            and set(supplied_ref[name]) == {"applicability", "value"}
            for name in DIMENSION_NAMES
        )
        and all(field in supplied_ref for field in SUBJECT_FIELDS)
    )
    legacy_or_explicit_ready = contract_valid if explicit else bool(lane_identity)
    local_exact = bool(
        len(paths.paths) == 1
        and artifact_id
        and artifact_class
        and artifact_class.lower() != "unknown"
        and paths.computed_sha
        and (not declared_sha or declared_sha == paths.computed_sha)
        and legacy_or_explicit_ready
        and paths.ref_matches_explicit
    )
    store_exact = bool(
        not paths.paths
        and paths.store_ref
        and artifact_id
        and artifact_class
        and artifact_class.lower() != "unknown"
        and declared_sha
        and declared_sha == paths.store_sha
        and legacy_or_explicit_ready
    )
    return _IdentitySelection(
        projection=projection,
        explicit=explicit,
        aliases=aliases,
        declared_sha=declared_sha,
        artifact_class=artifact_class,
        lane_identity=lane_identity,
        artifact_id=artifact_id,
        contract_valid=contract_valid,
        exact=local_exact or store_exact,
        store_exact=store_exact,
    )


def _identity_status(paths: _PathSelection, identity: _IdentitySelection) -> str:
    if identity.exact:
        return "verified"
    if (
        identity.explicit
        and identity.projection.subject_values.get("freshness_status") != "current"
    ):
        return "explicit_identity_not_current"
    if identity.explicit and not identity.contract_valid:
        return "explicit_identity_invalid"
    if (
        identity.declared_sha
        and paths.computed_sha
        and identity.declared_sha != paths.computed_sha
    ):
        return "hash_mismatch"
    if not paths.ref_matches_explicit:
        return "explicit_ref_path_mismatch"
    if paths.store_ref and not identity.store_exact:
        return "store_ref_hash_unverified"
    return "not_evaluated"


def _selected_artifact_ref(
    root: Path,
    paths: _PathSelection,
    identity: _IdentitySelection,
) -> dict[str, Any]:
    supplied_ref = paths.supplied_ref
    explicit_fields = {}
    if identity.explicit:
        exact_identity = {
            **{field: supplied_ref.get(field) for field in SUBJECT_FIELDS},
            "freshness_status": identity.projection.subject_values.get(
                "freshness_status"
            ),
            **{name: supplied_ref.get(name) for name in DIMENSION_NAMES},
        }
        explicit_fields = {
            **exact_identity,
            "decision_identity": exact_identity,
            "decision_identity_kind": "explicit_v2",
            "decision_identity_echo": {
                **expected_subject_echo(supplied_ref),
                "dimension_values": expected_dimension_echo(supplied_ref),
            },
            **identity.aliases,
        }
    return {
        **explicit_fields,
        "artifact_id": identity.artifact_id or None,
        "artifact_class": identity.artifact_class or None,
        "artifact_path_or_store_ref": rel_path(root, paths.selected_path)
        if paths.selected_path is not None
        else (paths.store_ref or None),
        "artifact_sha256": (
            paths.computed_sha or identity.declared_sha or paths.store_sha or None
        ),
        "production_lane_identity": identity.lane_identity,
        "body_projection_fingerprint": (
            identity.aliases.get("body_projection_fingerprint")
            if identity.explicit
            else supplied_ref.get("body_projection_fingerprint")
        ),
        "cohort_identity": identity.aliases.get("cohort_identity")
        if identity.explicit
        else supplied_ref.get("cohort_identity"),
        "producer_run_id": identity.aliases.get("producer_run_id")
        if identity.explicit
        else supplied_ref.get("producer_run_id"),
        "verification_input_ids": supplied_ref.get("verification_input_ids")
        if not identity.explicit and "verification_input_ids" in supplied_ref
        else identity.aliases.get("verification_input_ids"),
        "input_fingerprints": supplied_ref.get("input_fingerprints")
        if not identity.explicit and "input_fingerprints" in supplied_ref
        else identity.aliases.get("input_fingerprints"),
        "created_or_observed_at": supplied_ref.get("created_or_observed_at"),
        "discovery_basis": paths.discovery_basis,
        "scope_verified": identity.exact,
        "advisory_discovery": not identity.exact,
        "identity_status": _identity_status(paths, identity),
        "conflicting_discovery_paths": sorted(
            {
                rel_path(root, path)
                for path in paths.discovered_paths
                if path not in paths.paths
            }
        ),
    }


def load_artifact_selection(
    root: Path,
    artifact_paths_json: str | None,
    artifact_paths: list[str],
    *,
    artifact_ref_json: str | None = None,
    artifact_family: str | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    paths = _prepare_path_selection(
        root,
        artifact_paths_json,
        artifact_paths,
        artifact_ref_json,
    )
    identity = _prepare_identity_selection(paths, artifact_family)
    return paths.paths, _selected_artifact_ref(root, paths, identity)
