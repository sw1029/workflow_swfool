from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import sha256_file


def artifact_summary(
    root: Path, path: Path, artifact: dict[str, Any], digest: str
) -> dict[str, Any]:
    return {
        "ref": path.relative_to(root).as_posix(),
        "sha256": digest,
        "artifact_kind": artifact.get("artifact_kind"),
        "artifact_id": next(
            (
                artifact.get(key)
                for key in (
                    "verification_id",
                    "result_id",
                    "receipt_id",
                    "event_id",
                )
                if artifact.get(key)
            ),
            None,
        ),
        "reservation": artifact.get("reservation"),
        "effect_status": artifact.get("effect_status"),
        "outcome": artifact.get("outcome"),
    }


def artifact_summaries(
    root: Path, records: list[tuple[Path, dict[str, Any]]]
) -> list[dict[str, Any]]:
    return [
        artifact_summary(root, path, artifact, sha256_file(path))
        for path, artifact in records
    ]


def workflow_basis(
    kind: str,
    *,
    reservation: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
    source_approval: dict[str, Any] | None = None,
    recovery_recipe: dict[str, Any] | None = None,
    settlement_receipt: dict[str, Any] | None = None,
    blocker_codes: list[str] | None = None,
) -> dict[str, Any]:
    request_sha256 = None
    if reservation is not None:
        request_sha256 = reservation["reservation"]["request_sha256"]
    elif decision is not None:
        request_sha256 = decision["request_sha256"]
    return {
        "kind": kind,
        "request_sha256": request_sha256,
        "reservation": reservation["reservation"] if reservation else None,
        "reservation_state": reservation["state_binding"] if reservation else None,
        "decision": decision,
        "source_approval": source_approval,
        "recovery_recipe": recovery_recipe,
        "settlement_receipt": settlement_receipt,
        "blocker_codes": blocker_codes or [],
    }


def settlement_receipt(
    reservation: dict[str, Any],
    status: str,
    use_receipts: list[dict[str, Any]],
    release_receipts: list[dict[str, Any]],
    reconciliation_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    binding = {key: reservation["reservation"][key] for key in ("ref", "sha256")}
    if status == "consumed":
        candidates = [
            item
            for item in reconciliation_receipts
            if item["reservation"] == binding and item["outcome"] == "confirmed_effect"
        ] + [item for item in use_receipts if item["reservation"] == binding]
    else:
        candidates = [
            item
            for item in reconciliation_receipts
            if item["reservation"] == binding
            and item["outcome"] == "confirmed_no_effect"
        ] + [
            item
            for item in release_receipts
            if item["reservation"] == binding
            and item["effect_status"] in {"not_started", "verified_no_effect"}
        ]
    if not candidates:
        raise SystemExit("Terminal authority reservation lacks its settlement receipt.")
    return candidates[0]


__all__ = [
    "artifact_summaries",
    "artifact_summary",
    "settlement_receipt",
    "workflow_basis",
]
