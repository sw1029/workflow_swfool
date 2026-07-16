from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .support import artifact_path, file_sha256, normalize_list
from .terminal import terminal_event_reference


def prior_artifact_refs(root: Path, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    del root
    refs: list[dict[str, Any]] = []
    for event in events:
        for ref in event.get("artifact_refs") or []:
            if isinstance(ref, dict) and ref.get("path") and ref.get("sha256"):
                refs.append({"path": str(ref["path"]), "sha256": str(ref["sha256"])})
    return refs


def annotate_artifact_refs(root: Path, event: dict[str, Any], previous_events: list[dict[str, Any]]) -> None:
    previous = prior_artifact_refs(root, previous_events)
    authoritative_unchanged = {(str(ref["path"]), str(ref["sha256"]).lower()) for ref in previous}
    authoritative_unchanged.update(
        terminal_event_reference(previous_event)
        for previous_event in previous_events
        if previous_event.get("terminal_justified") and previous_event.get("event_id")
    )
    artifact_refs: list[dict[str, Any]] = []
    unchanged_refs: list[dict[str, str]] = []
    for supplied in event.get("unchanged_refs") or []:
        if not isinstance(supplied, dict):
            continue
        supplied_path = str(supplied.get("path") or "").strip()
        supplied_hash = str(supplied.get("sha256") or "").strip()
        if supplied_path and supplied_hash:
            if not re.fullmatch(r"[0-9a-f]{64}", supplied_hash.lower()):
                raise ValueError("supplied unchanged_ref requires a full lowercase SHA-256 digest")
            if (supplied_path, supplied_hash.lower()) not in authoritative_unchanged:
                raise ValueError("supplied unchanged_ref does not match prior authoritative path+hash evidence")
            unchanged_refs.append({"path": supplied_path, "sha256": supplied_hash.lower()})
    artifacts = normalize_list(event.get("artifacts"))
    supplied_refs = event.get("artifact_refs") if isinstance(event.get("artifact_refs"), list) else []
    if not artifacts:
        for supplied in supplied_refs:
            if not isinstance(supplied, dict) or not supplied.get("path") or not supplied.get("sha256"):
                raise ValueError("supplied artifact_refs require non-empty path and sha256")
            supplied_path = str(supplied["path"])
            supplied_hash = str(supplied["sha256"])
            current_hash = file_sha256(artifact_path(root, supplied_path))
            if current_hash != supplied_hash:
                raise ValueError(f"supplied artifact_ref hash does not match current artifact: {supplied_path}")
            ref: dict[str, Any] = {"path": supplied_path, "sha256": current_hash, "exists": True}
            prior = next(
                (
                    item
                    for item in reversed(previous)
                    if item.get("sha256") == current_hash and item.get("path") == supplied_path
                ),
                None,
            )
            if prior:
                ref["unchanged_ref"] = {"path": supplied_path, "sha256": current_hash}
                unchanged_refs.append(ref["unchanged_ref"])
            artifact_refs.append(ref)
    for artifact in artifacts:
        digest = file_sha256(artifact_path(root, artifact))
        if not digest:
            artifact_refs.append({"path": artifact, "sha256": None, "exists": False})
            continue
        ref = {"path": artifact, "sha256": digest, "exists": True}
        prior = next(
            (
                item
                for item in reversed(previous)
                if item.get("sha256") == digest and item.get("path") == artifact
            ),
            None,
        )
        if prior and prior.get("path") and prior.get("sha256"):
            ref["unchanged_ref"] = {"path": str(prior["path"]), "sha256": str(prior["sha256"])}
            unchanged_refs.append(ref["unchanged_ref"])
        artifact_refs.append(ref)
    event["artifact_refs"] = artifact_refs
    event["unchanged_refs"] = list(
        {
            (ref["path"], ref["sha256"]): ref
            for ref in unchanged_refs
            if ref.get("path") and ref.get("sha256")
        }.values()
    )
