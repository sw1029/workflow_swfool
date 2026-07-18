"""Construct the closed orchestrator projection from authority-owner artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .authority_artifacts import (
    owner_axis_projection,
    owner_scope_projection,
    read_bound_authority_json,
    validate_authority_artifacts,
)
from .authority_boundary import (
    canonical_sha256,
    effective_authority_fingerprint,
    project_authority_packet,
)


def _binding(ref: str, sha256: str) -> dict[str, str]:
    return {"ref": ref, "sha256": sha256}


def _not_applicable_reservation() -> dict[str, Any]:
    return {
        "applicability": "not_applicable",
        "reservation_id": None,
        "artifact_ref": None,
        "artifact_sha256": None,
        "state_ref": None,
        "state_sha256": None,
        "state_version": None,
        "status": None,
        "effective_authority_fingerprint": None,
        "grant_uses": [],
    }


def _not_applicable_preflight() -> dict[str, Any]:
    return {
        "status": "not_applicable",
        "artifact_ref": None,
        "artifact_sha256": None,
        "verification_id": None,
        "stage": None,
        "reservation": None,
        "reservation_state": None,
        "grant_states": [],
        "request_id": None,
        "effective_authority_fingerprint": None,
        "verified_at": None,
    }


def _dispatch_bindings(
    root: Path,
    reservation_binding: dict[str, str] | None,
    verification_binding: dict[str, str] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if reservation_binding is None or verification_binding is None:
        raise ValueError(
            "allowed mutation requires reservation and pre-dispatch verification bindings"
        )
    reservation = read_bound_authority_json(root, reservation_binding, "reservation")
    verification = read_bound_authority_json(
        root, verification_binding, "pre_dispatch_verification"
    )
    state_binding = verification.get("reservation_state")
    if not isinstance(state_binding, dict):
        raise ValueError("pre-dispatch verification has no reservation_state binding")
    state = read_bound_authority_json(
        root,
        _binding(
            str(state_binding.get("ref") or ""), str(state_binding.get("sha256") or "")
        ),
        "reservation_state",
    )
    reservation_projection = {
        "applicability": "required",
        "reservation_id": reservation.get("reservation_id"),
        "artifact_ref": reservation_binding["ref"],
        "artifact_sha256": reservation_binding["sha256"],
        "state_ref": state_binding.get("ref"),
        "state_sha256": state_binding.get("sha256"),
        "state_version": state.get("version"),
        "status": state.get("status"),
        "effective_authority_fingerprint": reservation.get(
            "effective_authority_fingerprint"
        ),
        "grant_uses": reservation.get("grant_uses"),
    }
    verification_projection = {
        "status": "verified",
        "artifact_ref": verification_binding["ref"],
        "artifact_sha256": verification_binding["sha256"],
        **{
            key: verification.get(key)
            for key in (
                "verification_id",
                "stage",
                "reservation",
                "reservation_state",
                "grant_states",
                "request_id",
                "effective_authority_fingerprint",
                "verified_at",
            )
        },
    }
    return reservation_projection, verification_projection


def build_authority_packet(
    root: str | Path,
    decision_binding: dict[str, str],
    *,
    reservation_binding: dict[str, str] | None = None,
    verification_binding: dict[str, str] | None = None,
    local_resolution: str | None = None,
    local_evidence_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Build, then artifact-verify, one exact authority-phase packet."""

    workspace = Path(root).expanduser().resolve(strict=True)
    decision = read_bound_authority_json(workspace, decision_binding, "decision")
    request = (
        decision.get("request") if isinstance(decision.get("request"), dict) else {}
    )
    manifest = decision.get("operation_manifest")
    axes = owner_axis_projection(decision)
    if local_resolution is not None:
        if local_resolution != "available" or not local_evidence_ids:
            raise ValueError("local override may only assert evidence-backed available")
        axes["local_resolution"] = {
            "status": "available",
            "evidence_ids": list(local_evidence_ids),
        }
    allowed_mutation = (
        decision.get("decision") == "allowed"
        and request.get("mutation_class") != "observe"
    )
    if allowed_mutation:
        reservation, preflight = _dispatch_bindings(
            workspace, reservation_binding, verification_binding
        )
    else:
        if reservation_binding is not None or verification_binding is not None:
            raise ValueError(
                "non-dispatch decision cannot carry lease or verification bindings"
            )
        reservation, preflight = (
            _not_applicable_reservation(),
            _not_applicable_preflight(),
        )
    operation = {
        "skill_id": request.get("skill_id"),
        "skill_version": request.get("skill_version"),
        "operation_id": request.get("operation_id"),
        "operation_version": request.get("operation_version"),
        "manifest_ref": manifest.get("ref") if isinstance(manifest, dict) else None,
        "manifest_sha256": manifest.get("sha256")
        if isinstance(manifest, dict)
        else None,
        "manifest_status": "verified" if isinstance(manifest, dict) else "missing",
        "mutation_class": request.get("mutation_class"),
    }
    decision_projection = {
        "decision_id": decision.get("decision_id"),
        "artifact_ref": decision_binding["ref"],
        "artifact_sha256": decision_binding["sha256"],
        "request_id": request.get("request_id"),
        "request_sha256": decision.get("request_sha256"),
        "decision": decision.get("decision"),
        "effective_authority_fingerprint": decision.get(
            "effective_authority_fingerprint"
        ),
    }
    identity = {
        "decision_id": decision.get("decision_id"),
        "reservation_sha256": reservation.get("artifact_sha256"),
        "verification_sha256": preflight.get("artifact_sha256"),
    }
    packet: dict[str, Any] = {
        "step": "authority",
        "schema_version": 2,
        "artifact_kind": "orchestrator_authority_packet",
        "packet_id": "authop-" + canonical_sha256(identity)[:24],
        "decision_binding": decision_projection,
        "operation_binding": operation,
        "subject": request.get("subject"),
        "scope": owner_scope_projection(decision),
        "axes": axes,
        "selected_grants": decision.get("selected_grants"),
        "lineage_grants": decision.get("lineage_grants"),
        "approval_projection": decision.get("approval_projection"),
        "composition_receipt": request.get("composition_receipt"),
        "reservation_binding": reservation,
        "dispatch_preflight": preflight,
        "effective_authority_fingerprint": "",
        "evidence_ids": [str(decision.get("decision_id"))],
        "packet_sha256": "",
    }
    packet["effective_authority_fingerprint"] = effective_authority_fingerprint(packet)
    packet["packet_sha256"] = canonical_sha256(
        {key: value for key, value in packet.items() if key != "packet_sha256"}
    )
    projection = project_authority_packet(packet)
    findings = list(projection.findings)
    findings.extend(validate_authority_artifacts(packet, workspace))
    if findings:
        codes = ", ".join(str(row["code"]) for row in findings)
        raise ValueError(f"constructed authority packet did not verify: {codes}")
    return packet


def _load_binding(value: str) -> dict[str, str]:
    try:
        path = Path(value)
        raw = json.loads(path.read_text(encoding="utf-8") if path.is_file() else value)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("binding must be JSON or a JSON file") from exc
    if not isinstance(raw, dict) or set(raw) != {"ref", "sha256"}:
        raise ValueError("binding must contain exactly ref and sha256")
    return {"ref": str(raw["ref"]), "sha256": str(raw["sha256"])}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--decision-binding", required=True)
    parser.add_argument("--reservation-binding")
    parser.add_argument("--verification-binding")
    parser.add_argument("--local-resolution", choices=("available",))
    parser.add_argument("--local-evidence-id", action="append", default=[])
    parser.add_argument("--output")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        packet = build_authority_packet(
            args.root,
            _load_binding(args.decision_binding),
            reservation_binding=_load_binding(args.reservation_binding)
            if args.reservation_binding
            else None,
            verification_binding=_load_binding(args.verification_binding)
            if args.verification_binding
            else None,
            local_resolution=args.local_resolution,
            local_evidence_ids=args.local_evidence_id,
        )
    except ValueError as exc:
        parser.error(str(exc))
    body = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(body, encoding="utf-8")
    else:
        print(body, end="")
    return 0


__all__ = ("build_authority_packet", "main")


if __name__ == "__main__":
    raise SystemExit(main())
