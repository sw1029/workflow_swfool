"""Artifact discovery and identity selection."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

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
    for key in ("decision_artifact_ref", "artifact_ref", "selected_artifact_ref"):
        if isinstance(value.get(key), dict):
            return dict(value[key])
    if any(
        key in value
        for key in ("artifact_id", "artifact_sha256", "artifact_path_or_store_ref")
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


def load_artifact_selection(
    root: Path,
    artifact_paths_json: str | None,
    artifact_paths: list[str],
    *,
    artifact_ref_json: str | None = None,
    artifact_family: str | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    discovery_value = _load_json_argument(root, artifact_paths_json)
    explicit_ref_value = _load_json_argument(root, artifact_ref_json)
    supplied_ref = _artifact_ref_from_value(
        explicit_ref_value
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
    computed_sha = _sha256_path(selected_path)
    declared_sha = (
        str(supplied_ref.get("artifact_sha256") or supplied_ref.get("sha256") or "")
        .strip()
        .lower()
    )
    store_hash_match = re.search(
        r"(?:sha256[:/])([a-f0-9]{64})(?:\b|$)", store_ref.lower()
    )
    store_sha = store_hash_match.group(1) if store_hash_match else ""
    artifact_class = str(
        supplied_ref.get("artifact_class")
        or supplied_ref.get("class")
        or artifact_family
        or ""
    ).strip()
    lane_identity = supplied_ref.get("production_lane_identity")
    if lane_identity is None and isinstance(discovery_value, dict):
        lane_identity = discovery_value.get("production_lane_identity")
    artifact_id = str(supplied_ref.get("artifact_id") or "").strip()
    if not artifact_id and computed_sha:
        artifact_id = f"artifact-{computed_sha[:16]}"
    ref_matches_explicit = not (
        explicit_paths
        and ref_path is not None
        and ref_path.resolve() not in {path.resolve() for path in explicit_paths}
    )
    local_exact_identity = bool(
        len(paths) == 1
        and artifact_id
        and artifact_class
        and artifact_class.lower() != "unknown"
        and computed_sha
        and (not declared_sha or declared_sha == computed_sha)
        and lane_identity
        and ref_matches_explicit
    )
    store_exact_identity = bool(
        not paths
        and store_ref
        and artifact_id
        and artifact_class
        and artifact_class.lower() != "unknown"
        and declared_sha
        and declared_sha == store_sha
        and lane_identity
    )
    exact_identity = local_exact_identity or store_exact_identity
    selected_ref = {
        "artifact_id": artifact_id or None,
        "artifact_class": artifact_class or None,
        "artifact_path_or_store_ref": rel_path(root, selected_path)
        if selected_path is not None
        else (store_ref or None),
        "artifact_sha256": computed_sha or declared_sha or store_sha or None,
        "production_lane_identity": lane_identity,
        "body_projection_fingerprint": supplied_ref.get("body_projection_fingerprint"),
        "verification_input_ids": supplied_ref.get("verification_input_ids")
        if "verification_input_ids" in supplied_ref
        else None,
        "input_fingerprints": supplied_ref.get("input_fingerprints")
        if "input_fingerprints" in supplied_ref
        else None,
        "created_or_observed_at": supplied_ref.get("created_or_observed_at"),
        "discovery_basis": discovery_basis,
        "scope_verified": exact_identity,
        "advisory_discovery": not exact_identity,
        "identity_status": (
            "verified"
            if exact_identity
            else "hash_mismatch"
            if declared_sha and computed_sha and declared_sha != computed_sha
            else "explicit_ref_path_mismatch"
            if not ref_matches_explicit
            else "store_ref_hash_unverified"
            if store_ref and not store_exact_identity
            else "not_evaluated"
        ),
        "conflicting_discovery_paths": sorted(
            {
                rel_path(root, path)
                for path in discovered_paths
                if path not in paths
            }
        ),
    }
    return paths, selected_ref
