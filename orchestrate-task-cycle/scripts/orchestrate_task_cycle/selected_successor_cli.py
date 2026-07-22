"""Prepare, authority-gate, execute, or recover a selected successor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .selected_successor import prepare_selected_successor_bundle
from .selected_successor_authority import prepare_selected_successor_authority
from .selected_successor_authority_context_compiler import (
    prepare_selected_successor_authority_contexts,
)
from .selected_successor_authority_validation import validate_authority_packet
from .selected_successor_execution import ACTIONS, execute_selected_successor_bundle
from .selected_successor_owner_validation import (
    OPERATIONS,
    validate_selected_successor_owner_result,
)


PREFIXES = {
    ACTIONS[0]: "index",
    ACTIONS[1]: "publication",
    ACTIONS[2]: "settlement",
}
SOURCE_RANKS = ("S0", "S1", "S2", "S3", "S4")
RISK_TIERS = ("R0", "R1", "R2", "R3")
MUTATION_CLASSES = (
    "observe",
    "local_mutation",
    "external_mutation",
    "destructive",
)
DECISION_CLASSES = ("D0", "D1", "D2", "D3")


def _binding(ref: str, digest: str) -> dict[str, str]:
    return {"ref": ref, "sha256": digest}


def _optional_binding(args: argparse.Namespace, prefix: str) -> dict[str, str] | None:
    ref = getattr(args, f"{prefix}_ref")
    digest = getattr(args, f"{prefix}_sha256")
    if ref is None and digest is None:
        return None
    if ref is None or digest is None:
        raise ValueError(f"{prefix.replace('_', '-')} requires ref and sha256 together")
    return _binding(ref, digest)


def _add_context_arguments(parser: argparse.ArgumentParser) -> None:
    from .selected_successor_authority_context import (
        DECISION_STATUS,
        EXTERNAL_INPUT,
        GOAL_TRUTH,
    )

    parser.add_argument("--bundle-ref", required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--actor-rank", choices=SOURCE_RANKS, required=True)
    parser.add_argument(
        "--external-input-status", choices=sorted(EXTERNAL_INPUT), required=True
    )
    parser.add_argument(
        "--goal-truth-status", choices=sorted(GOAL_TRUTH), required=True
    )
    parser.add_argument(
        "--risk-acceptance-status", choices=sorted(DECISION_STATUS), required=True
    )
    parser.add_argument(
        "--design-selection-status", choices=sorted(DECISION_STATUS), required=True
    )
    for prefix in (
        "external-input-evidence",
        "risk-acceptance-evidence",
        "design-selection-evidence",
    ):
        parser.add_argument(f"--{prefix}-ref")
        parser.add_argument(f"--{prefix}-sha256")
    parser.add_argument("--session-capability", action="append", required=True)
    parser.add_argument(
        "--session-risk-ceiling", choices=RISK_TIERS, required=True
    )
    parser.add_argument(
        "--session-mutation-class",
        action="append",
        choices=MUTATION_CLASSES,
        required=True,
    )
    parser.add_argument("--session-evidence-id", required=True)
    parser.add_argument("--goal-envelope-id", required=True)
    parser.add_argument("--goal-capability", action="append", required=True)
    parser.add_argument("--goal-risk-ceiling", choices=RISK_TIERS, required=True)
    parser.add_argument(
        "--goal-decision-class",
        action="append",
        choices=DECISION_CLASSES,
        required=True,
    )
    parser.add_argument("--goal-subject-digest", action="append", required=True)
    parser.add_argument("--goal-operation", action="append", required=True)
    parser.add_argument("--goal-source-ref", required=True)
    parser.add_argument("--goal-source-sha256", required=True)
    parser.add_argument("--skills-root")


def _add_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--authority-packet-ref")
    parser.add_argument("--authority-packet-sha256")
    parser.add_argument("--bundle-ref")
    parser.add_argument("--bundle-sha256")
    parser.add_argument("--at", required=True)
    parser.add_argument("--skills-root")
    for prefix in PREFIXES.values():
        parser.add_argument(f"--{prefix}-reservation-ref")
        parser.add_argument(f"--{prefix}-reservation-sha256")
        parser.add_argument(f"--{prefix}-pre-commit-ref")
        parser.add_argument(f"--{prefix}-pre-commit-sha256")
        parser.add_argument(
            f"--{prefix}-expected-version", type=int
        )


def _authority_proofs(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    proofs: dict[str, dict[str, Any]] = {}
    for action, prefix in PREFIXES.items():
        proofs[action] = {
            "reservation": _binding(
                getattr(args, f"{prefix}_reservation_ref"),
                getattr(args, f"{prefix}_reservation_sha256"),
            ),
            "pre_commit_verification": _binding(
                getattr(args, f"{prefix}_pre_commit_ref"),
                getattr(args, f"{prefix}_pre_commit_sha256"),
            ),
            "expected_version": (
                getattr(args, f"{prefix}_expected_version")
                if getattr(args, f"{prefix}_expected_version") is not None
                else 0
            ),
        }
    return proofs


def _prepared_grants(args: argparse.Namespace) -> dict[str, Any]:
    grants: dict[str, Any] = {}
    for action, prefix in PREFIXES.items():
        absent = bool(getattr(args, f"{prefix}_grant_absent"))
        ref = getattr(args, f"{prefix}_grant_ref")
        digest = getattr(args, f"{prefix}_grant_sha256")
        if absent and ref is None and digest is None:
            grants[action] = {"status": "absent"}
        elif not absent and ref is not None and digest is not None:
            grants[action] = _binding(ref, digest)
        else:
            raise ValueError(
                f"{prefix} grant requires ref+sha256 or the explicit absent flag"
            )
    return grants


def _execution_inputs(
    root: Path, args: argparse.Namespace, skills_root: Path | None
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    packet_ref = args.authority_packet_ref
    packet_sha = args.authority_packet_sha256
    legacy_bindings = [args.bundle_ref, args.bundle_sha256]
    legacy_versions = []
    for prefix in PREFIXES.values():
        legacy_bindings.extend(
            (
                getattr(args, f"{prefix}_reservation_ref"),
                getattr(args, f"{prefix}_reservation_sha256"),
                getattr(args, f"{prefix}_pre_commit_ref"),
                getattr(args, f"{prefix}_pre_commit_sha256"),
            )
        )
        legacy_versions.append(getattr(args, f"{prefix}_expected_version"))
    if packet_ref is not None or packet_sha is not None:
        if (
            packet_ref is None
            or packet_sha is None
            or any(value is not None for value in legacy_bindings + legacy_versions)
        ):
            raise ValueError(
                "authority packet mode requires one exact packet pair and no legacy proofs"
            )
        packet = validate_authority_packet(
            root,
            _binding(packet_ref, packet_sha),
            skills_root=skills_root,
        )
        return packet["bundle"], packet["authority_proofs"]
    if not all(value is not None for value in legacy_bindings):
        raise ValueError(
            "legacy execution requires bundle and all three explicit proof bindings"
        )
    return _binding(args.bundle_ref, args.bundle_sha256), _authority_proofs(args)


def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root)
    if args.command == "prepare":
        return prepare_selected_successor_bundle(
            root,
            source_decision=_binding(
                args.source_decision_ref, args.source_decision_sha256
            ),
            task_source=_binding(args.task_source_ref, args.task_source_sha256),
            at=args.at,
        )
    if args.command == "prepare-authority":
        return prepare_selected_successor_authority(
            root,
            bundle_binding=_binding(args.bundle_ref, args.bundle_sha256),
            request_context_binding=_binding(
                args.request_context_ref, args.request_context_sha256
            ),
            evaluation_context_binding=_binding(
                args.evaluation_context_ref, args.evaluation_context_sha256
            ),
            grants=_prepared_grants(args),
            at=args.at,
            skills_root=Path(args.skills_root) if args.skills_root else None,
        )
    if args.command == "prepare-authority-context":
        request_context = {
            "external_input_status": args.external_input_status,
            "goal_truth_status": args.goal_truth_status,
            "risk_acceptance_status": args.risk_acceptance_status,
            "design_selection_status": args.design_selection_status,
            "external_input_evidence": _optional_binding(
                args, "external_input_evidence"
            ),
            "risk_acceptance_evidence": _optional_binding(
                args, "risk_acceptance_evidence"
            ),
            "design_selection_evidence": _optional_binding(
                args, "design_selection_evidence"
            ),
        }
        session = {
            "capabilities": args.session_capability,
            "risk_ceiling": args.session_risk_ceiling,
            "mutation_classes": args.session_mutation_class,
            "evidence_id": args.session_evidence_id,
        }
        envelope = {
            "envelope_id": args.goal_envelope_id,
            "capabilities": args.goal_capability,
            "risk_ceiling": args.goal_risk_ceiling,
            "decision_classes": args.goal_decision_class,
            "subjects": args.goal_subject_digest,
            "operations": args.goal_operation,
            "source_binding": _binding(
                args.goal_source_ref, args.goal_source_sha256
            ),
        }
        return prepare_selected_successor_authority_contexts(
            root,
            bundle_binding=_binding(args.bundle_ref, args.bundle_sha256),
            actor_rank=args.actor_rank,
            request_context=request_context,
            session_ceiling=session,
            goal_autonomy_envelope=envelope,
            skills_root=Path(args.skills_root) if args.skills_root else None,
        )
    if args.command in {"execute", "recover"}:
        skills_root = Path(args.skills_root) if args.skills_root else None
        bundle, proofs = _execution_inputs(root, args, skills_root)
        return execute_selected_successor_bundle(
            root,
            bundle_binding=bundle,
            authority_proofs=proofs,
            settled_at=args.at,
            skills_root=skills_root,
        )
    return validate_selected_successor_owner_result(
        root,
        operation=args.operation,
        owner_result=_binding(args.owner_result_ref, args.owner_result_sha256),
        reservation=_binding(args.reservation_ref, args.reservation_sha256),
        pre_commit_verification=_binding(
            args.pre_commit_ref, args.pre_commit_sha256
        ),
        phase=args.phase,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--source-decision-ref", required=True)
    prepare.add_argument("--source-decision-sha256", required=True)
    prepare.add_argument("--task-source-ref", required=True)
    prepare.add_argument("--task-source-sha256", required=True)
    prepare.add_argument("--at", required=True)
    authority = commands.add_parser("prepare-authority")
    authority.add_argument("--bundle-ref", required=True)
    authority.add_argument("--bundle-sha256", required=True)
    authority.add_argument("--request-context-ref", required=True)
    authority.add_argument("--request-context-sha256", required=True)
    authority.add_argument("--evaluation-context-ref", required=True)
    authority.add_argument("--evaluation-context-sha256", required=True)
    authority.add_argument("--at", required=True)
    authority.add_argument("--skills-root")
    for prefix in PREFIXES.values():
        authority.add_argument(f"--{prefix}-grant-ref")
        authority.add_argument(f"--{prefix}-grant-sha256")
        authority.add_argument(
            f"--{prefix}-grant-absent", action="store_true"
        )
    _add_context_arguments(commands.add_parser("prepare-authority-context"))
    for name in ("execute", "recover"):
        _add_execution_arguments(commands.add_parser(name))
    validate = commands.add_parser("validate-owner-result")
    validate.add_argument("--operation", choices=sorted(OPERATIONS), required=True)
    for name in (
        "owner-result-ref",
        "owner-result-sha256",
        "reservation-ref",
        "reservation-sha256",
        "pre-commit-ref",
        "pre-commit-sha256",
    ):
        validate.add_argument(f"--{name}", required=True)
    validate.add_argument(
        "--phase", choices=("current", "historical"), default="current"
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (OSError, ValueError, json.JSONDecodeError, SystemExit) as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error": str(exc),
                    "mutation_performed": None,
                    "mutation_status": "unknown_after_failure",
                }
            )
        )
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


__all__ = ("main",)
