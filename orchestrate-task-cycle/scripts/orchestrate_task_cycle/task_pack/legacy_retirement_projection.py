"""Operational projection of settled legacy retirement artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .legacy_retirement_store import binding_for, scan_category
from .legacy_retirement_validation import (
    validate_activation_binding,
    validate_completion_binding,
)
from .storage import rel_path


@dataclass(slots=True)
class _ProjectionState:
    active: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    linked: dict[str, set[str]] = field(
        default_factory=lambda: {
            "prepares": set(),
            "overlays": set(),
            "snapshots": set(),
            "completions": set(),
            "activations": set(),
        }
    )


def _finding(code: str, message: str, **evidence: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "severity": "block",
        "code": code,
        "message": message,
    }
    if evidence:
        result["evidence"] = evidence
    return result


def _activation_candidates(
    root: Path, state: _ProjectionState
) -> dict[str, list[Path]]:
    by_completion: dict[str, list[Path]] = {}
    for path in scan_category(root, "activations"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            completion = raw.get("completion") if isinstance(raw, dict) else None
            completion_ref = str(
                completion.get("ref") if isinstance(completion, dict) else ""
            )
            if not completion_ref:
                raise ValueError("activation has no completion ref")
            by_completion.setdefault(completion_ref, []).append(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            state.findings.append(
                _finding(
                    "legacy_retirement_activation_invalid",
                    str(exc),
                    artifact_ref=rel_path(root, path),
                )
            )
    return by_completion


def _record_pending(
    state: _ProjectionState,
    source_ref: str,
    completion_binding: dict[str, str],
    candidates: list[Path],
) -> None:
    state.pending[source_ref] = completion_binding
    state.findings.append(
        _finding(
            "authority_settlement_pending"
            if not candidates
            else "multiple_legacy_retirement_activations",
            "Committed legacy retirement requires exactly one settled activation.",
            source_pack_ref=source_ref,
            completion_ref=completion_binding["ref"],
            activation_count=len(candidates),
        )
    )


def _process_completion(
    root: Path,
    path: Path,
    candidates_by_completion: dict[str, list[Path]],
    state: _ProjectionState,
) -> None:
    completion_binding = binding_for(root, path)
    state.linked["completions"].add(path.name)
    try:
        completion, overlay, _plan = validate_completion_binding(
            root, completion_binding
        )
        source_ref = str((overlay.get("source_pack") or {}).get("ref") or "")
        state.linked["prepares"].add(Path(completion["prepare"]["ref"]).name)
        state.linked["overlays"].add(Path(completion["overlay"]["ref"]).name)
        state.linked["snapshots"].add(Path(completion["source_snapshot"]["ref"]).name)
        candidates = candidates_by_completion.get(completion_binding["ref"], [])
        if len(candidates) != 1:
            _record_pending(state, source_ref, completion_binding, candidates)
            return
        activation_path = candidates[0]
        activation_binding = binding_for(root, activation_path)
        activation, checked_overlay, _ = validate_activation_binding(
            root, activation_binding, phase="historical"
        )
        if checked_overlay != overlay:
            raise ValueError("activation overlay differs from completion overlay")
        if source_ref in state.active:
            raise ValueError("source pack has multiple active retirement overlays")
        state.linked["activations"].add(activation_path.name)
        state.active[source_ref] = {
            "activation": activation_binding,
            "retirement": completion["overlay"],
            "completion": completion_binding,
            "authority_use_receipt": activation["authority_use_receipt"],
            "raw_finding_codes": (overlay.get("eligibility") or {}).get(
                "blocking_finding_codes"
            ),
        }
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        state.findings.append(
            _finding(
                "legacy_retirement_artifact_invalid",
                str(exc),
                completion_ref=completion_binding["ref"],
            )
        )


def _append_unlinked_findings(root: Path, state: _ProjectionState) -> None:
    for prepare_path in scan_category(root, "prepares"):
        if prepare_path.name not in state.linked["prepares"]:
            state.findings.append(
                _finding(
                    "legacy_retirement_transaction_pending",
                    "Prepared legacy retirement requires forward completion.",
                    prepare_ref=rel_path(root, prepare_path),
                )
            )
    for category in ("overlays", "snapshots", "activations"):
        for path in scan_category(root, category):
            if path.name not in state.linked[category]:
                state.findings.append(
                    _finding(
                        "legacy_retirement_orphan_artifact",
                        "Artifact is not bound by one valid completion and activation chain.",
                        artifact_ref=rel_path(root, path),
                    )
                )


def retirement_store_projection(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    state = _ProjectionState()
    try:
        candidates = _activation_candidates(root, state)
        for path in scan_category(root, "completions"):
            _process_completion(root, path, candidates, state)
        _append_unlinked_findings(root, state)
    except (OSError, ValueError) as exc:
        state.findings.append(_finding("legacy_retirement_store_invalid", str(exc)))
    return {
        "status": "block" if state.findings else "ok",
        "active_by_pack_ref": state.active,
        "pending_by_pack_ref": state.pending,
        "active_count": len(state.active),
        "pending_count": len(state.pending),
        "findings": state.findings,
    }


def active_retirement_for_pack(
    root: Path,
    pack_path: Path,
    projection: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    state = projection or retirement_store_projection(root)
    return (state.get("active_by_pack_ref") or {}).get(rel_path(root, pack_path))


def require_pack_not_retired(root: Path, pack_path: Path) -> None:
    state = retirement_store_projection(root)
    if state.get("findings"):
        raise SystemExit(str(state["findings"][0]["message"]))
    if active_retirement_for_pack(root, pack_path, state) is not None:
        raise SystemExit(
            "Task pack is an immutable retired legacy artifact and cannot be mutated."
        )


__all__ = (
    "active_retirement_for_pack",
    "require_pack_not_retired",
    "retirement_store_projection",
)
