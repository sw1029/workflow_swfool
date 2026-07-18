from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT
from .canonical import sha256_file
from .projection_io import safe_json, safe_owned_directory, validate_reservation_state
from .projection_recovery import validated_settled_intents
from .projection_reservations import validate_decision_artifact
from .workflow_candidates import grant_status_records
from .workflow_candidates import reservation_authority_blockers
from .workflow_candidates import validated_grants
from .workflow_evidence import artifact_summaries, artifact_summary


def _safe_artifacts(
    root: Path, directory: str, label: str
) -> list[tuple[Path, dict[str, Any], str]]:
    path = safe_owned_directory(
        root.resolve(), AUTHORIZATION_ROOT / directory, f"{label} directory"
    )
    if path is None:
        return []
    records: list[tuple[Path, dict[str, Any], str]] = []
    for candidate in sorted(path.iterdir()):
        if candidate.suffix != ".json":
            continue
        if candidate.is_symlink() or not candidate.is_file():
            raise SystemExit(f"{label} directory contains a non-regular artifact.")
        artifact, digest = safe_json(root, candidate, label)
        records.append((candidate, artifact, digest))
    return records


def _directory_summaries(root: Path, directory: str) -> list[dict[str, Any]]:
    return [
        artifact_summary(root, path, artifact, digest)
        for path, artifact, digest in _safe_artifacts(
            root, directory, f"authority {directory}"
        )
    ]


def _decision_summary(
    root: Path, path: Path, decision: dict[str, Any], digest: str
) -> dict[str, Any]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": digest,
        "decision_id": decision["decision_id"],
        "request_sha256": decision["request_sha256"],
        "decision": decision["decision"],
        "effective_authority_fingerprint": decision[
            "effective_authority_fingerprint"
        ],
        "selected_grants": decision["selected_grants"],
        "lineage_grants": decision["lineage_grants"],
    }


def _load_decisions(
    root: Path, request_sha256: str | None, skills_root: Path | None
) -> tuple[
    list[tuple[dict[str, Any], dict[str, Any]]], dict[str, dict[str, Any]]
]:
    decisions: list[tuple[dict[str, Any], dict[str, Any]]] = []
    decisions_by_ref: dict[str, dict[str, Any]] = {}
    for path, decision, digest in _safe_artifacts(
        root, "decisions", "authority decision"
    ):
        validate_decision_artifact(root, decision, path, skills_root=skills_root)
        summary = _decision_summary(root, path, decision, digest)
        decisions_by_ref[summary["ref"]] = decision
        if request_sha256 and decision["request_sha256"] != request_sha256:
            continue
        decisions.append((decision, summary))
    return decisions, decisions_by_ref


def _load_reservations(
    root: Path,
    settled: dict[str, list[tuple[Path, dict[str, Any]]]],
    decisions_by_ref: dict[str, dict[str, Any]],
    grant_records: dict[str, Any],
    request_sha256: str | None,
    at: Any,
) -> list[dict[str, Any]]:
    reservations: list[dict[str, Any]] = []
    for path, artifact in settled.get("reservations", []):
        if request_sha256 and artifact["request_sha256"] != request_sha256:
            continue
        state_path = (
            root
            / AUTHORIZATION_ROOT
            / "state"
            / "reservations"
            / f"{artifact['reservation_id']}.json"
        )
        state, state_digest = safe_json(root, state_path, "authority reservation state")
        state = validate_reservation_state(
            state, artifact["reservation_id"], "authority reservation state"
        )
        decision = decisions_by_ref.get(artifact["decision"]["ref"])
        if decision is None:
            raise SystemExit("Authority reservation decision is not status-visible.")
        blockers = (
            reservation_authority_blockers(artifact, decision, grant_records, at)
            if state["status"] == "reserved"
            else []
        )
        reservations.append(
            {
                "reservation": {
                    "ref": path.relative_to(root).as_posix(),
                    "sha256": sha256_file(path),
                    "reservation_id": artifact["reservation_id"],
                    "request_sha256": artifact["request_sha256"],
                },
                "state": state,
                "state_binding": {
                    "ref": state_path.relative_to(root).as_posix(),
                    "sha256": state_digest,
                },
                "authority_effective_usable": state["status"] == "reserved"
                and not blockers,
                "authority_blocker_codes": blockers,
            }
        )
    return reservations


def load_status_inventory(
    root: Path,
    *,
    grant_id: str | None,
    request_sha256: str | None,
    at: Any,
    skills_root: Path | None,
) -> dict[str, Any]:
    settled: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path, artifact in validated_settled_intents(root):
        settled.setdefault(path.parent.name, []).append((path, artifact))
    grant_records = validated_grants(root)
    decisions, decisions_by_ref = _load_decisions(
        root, request_sha256, skills_root
    )
    receipts = {
        name: artifact_summaries(root, settled.get(directory, []))
        for name, directory in (
            ("use_receipts", "use_receipts"),
            ("release_receipts", "release_receipts"),
            ("reconciliation_receipts", "reconciliation_receipts"),
        )
    }
    return {
        "grant_records": grant_records,
        "grants": grant_status_records(grant_records, grant_id, at),
        "decisions": decisions,
        "reservations": _load_reservations(
            root,
            settled,
            decisions_by_ref,
            grant_records,
            request_sha256,
            at,
        ),
        **receipts,
        "verifications": _directory_summaries(root, "verifications"),
        "execution_results": _directory_summaries(root, "execution_results"),
    }


__all__ = ["load_status_inventory"]
