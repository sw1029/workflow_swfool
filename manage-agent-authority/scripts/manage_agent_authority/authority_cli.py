from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .artifact_store import AUTHORIZATION_ROOT
from .artifact_store import register_grant
from .artifact_store import snapshot_file
from .artifact_store import transition_grants
from .artifact_store import update_current_policy
from .canonical import load_object
from .canonical import object_sha256
from .canonical import parse_time
from .canonical import write_immutable_json
from .composition import create_composition
from .evaluator import evaluate
from .lifecycle import consume
from .lifecycle import release
from .reconciliation import reconcile_quarantine
from .lifecycle import reserve
from .lifecycle import verify_reservation_with_recovery
from .workflow_status import resolve_operation
from .workflow_status import status_snapshot
from .reconciliation_evidence import prepare_reconciliation_evidence
from .source_recovery import prepare_source_recovery
from .cli_errors import emit_error


def _emit(value: Any) -> int:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


def _root(args: argparse.Namespace) -> Path:
    return Path(args.root).resolve()


def _skills_root(args: argparse.Namespace) -> Path | None:
    value = getattr(args, "skills_root", None)
    return Path(value).resolve() if value else None


def _binding(value: str, label: str) -> dict[str, str]:
    loaded = load_object(value)
    if set(loaded) != {"ref", "sha256"}:
        raise SystemExit(f"{label} must contain exactly ref and sha256.")
    return {"ref": str(loaded["ref"]), "sha256": str(loaded["sha256"])}


def command_snapshot_policy(args: argparse.Namespace) -> int:
    binding = snapshot_file(_root(args), args.policy_ref, "policy")
    pointer = update_current_policy(
        _root(args), binding, expected_version=args.expected_version
    )
    return _emit(
        {"status": "snapshotted", "policy_snapshot": binding, "current_policy": pointer}
    )


def command_snapshot_source(args: argparse.Namespace) -> int:
    binding = snapshot_file(_root(args), args.source_ref, "source_approval")
    return _emit({"status": "snapshotted", "source_approval": binding})


def command_register_grant(args: argparse.Namespace) -> int:
    result = register_grant(_root(args), load_object(args.grant), parent_id=None)
    return _emit({"status": "registered", **result})


def command_delegate(args: argparse.Namespace) -> int:
    result = register_grant(
        _root(args), load_object(args.grant), parent_id=args.parent_grant_id
    )
    return _emit({"status": "delegated", **result})


def command_evaluate(args: argparse.Namespace) -> int:
    root = _root(args)
    decision = evaluate(
        root,
        load_object(args.request),
        load_object(args.context),
        evaluated_at=args.at,
        skills_root=_skills_root(args),
    )
    path = root / AUTHORIZATION_ROOT / "decisions" / f"{decision['decision_id']}.json"
    digest = write_immutable_json(path, decision, "authority decision")
    return _emit(
        {
            **decision,
            "decision_ref": path.relative_to(root).as_posix(),
            "decision_sha256": digest,
        }
    )


def command_compose(args: argparse.Namespace) -> int:
    result = create_composition(_root(args), load_object(args.composition))
    return _emit({"status": "created", **result})


def command_reserve(args: argparse.Namespace) -> int:
    result = reserve(
        _root(args),
        args.decision_ref,
        args.decision_sha256,
        reserved_at=args.at,
        idempotency_key=args.idempotency_key,
        skills_root=_skills_root(args),
    )
    return _emit({"status": "reserved", **result})


def command_verify(args: argparse.Namespace) -> int:
    root = _root(args)
    reservation, state, verification, state_sha256 = verify_reservation_with_recovery(
        root,
        args.reservation_ref,
        args.reservation_sha256,
        verified_at=args.at,
        expected_version=args.expected_version,
        skills_root=_skills_root(args),
    )
    decision = verification["decision"]
    state_path = (
        root
        / AUTHORIZATION_ROOT
        / "state"
        / "reservations"
        / f"{reservation['reservation_id']}.json"
    )
    core = {
        "schema_version": 2,
        "artifact_kind": "authority_verification",
        "stage": args.stage,
        "reservation": {
            "ref": args.reservation_ref,
            "sha256": args.reservation_sha256,
        },
        "reservation_state": {
            "ref": state_path.relative_to(root).as_posix(),
            "sha256": state_sha256,
            "version": state["version"],
            "status": state["status"],
        },
        "grant_states": verification["grant_states"],
        "request_id": decision["request"]["request_id"],
        "effective_authority_fingerprint": reservation[
            "effective_authority_fingerprint"
        ],
        "verified_at": parse_time(args.at, "at").isoformat(),
    }
    result = {
        "verification_id": f"authv-{object_sha256(core)[:24]}",
        **core,
    }
    path = (
        root
        / AUTHORIZATION_ROOT
        / "verifications"
        / f"{result['verification_id']}.json"
    )
    digest = write_immutable_json(path, result, "authority verification")
    return _emit(
        {
            "status": "verified",
            **result,
            "verification_ref": path.relative_to(root).as_posix(),
            "verification_sha256": digest,
        }
    )


def command_consume(args: argparse.Namespace) -> int:
    pre_commit_value = getattr(args, "pre_commit_verification", None)
    result = consume(
        _root(args),
        args.reservation_ref,
        args.reservation_sha256,
        _binding(args.execution_result, "execution_result"),
        pre_commit_verification=(
            _binding(pre_commit_value, "pre_commit_verification")
            if pre_commit_value
            else None
        ),
        expected_subject_after_sha256=getattr(
            args, "expected_subject_after_sha256", None
        ),
        consumed_at=args.at,
        expected_version=args.expected_version,
        idempotency_key=args.idempotency_key,
        skills_root=_skills_root(args),
    )
    return _emit({"status": "consumed", **result})


def command_release(args: argparse.Namespace) -> int:
    result = release(
        _root(args),
        args.reservation_ref,
        args.reservation_sha256,
        _binding(args.no_effect_evidence, "no_effect_evidence"),
        released_at=args.at,
        expected_version=args.expected_version,
        idempotency_key=args.idempotency_key,
        effect_status=args.effect_status,
    )
    return _emit(
        {
            "status": "released"
            if result["release_receipt"]["release_applied"]
            else "quarantined",
            **result,
        }
    )


def command_reconcile(args: argparse.Namespace) -> int:
    pre_commit_value = getattr(args, "pre_commit_verification", None)
    result = reconcile_quarantine(
        _root(args),
        args.reservation_ref,
        args.reservation_sha256,
        _binding(args.effect_evidence, "effect_evidence"),
        outcome=args.outcome,
        pre_commit_verification=(
            _binding(pre_commit_value, "pre_commit_verification")
            if pre_commit_value
            else None
        ),
        reconciled_at=args.at,
        expected_version=args.expected_version,
        idempotency_key=args.idempotency_key,
    )
    return _emit(
        {
            "status": result["reconciliation_receipt"]["outcome"],
            **result,
        }
    )


def command_prepare_reconciliation_evidence(args: argparse.Namespace) -> int:
    owner_value = getattr(args, "owner_result", None)
    return _emit(
        prepare_reconciliation_evidence(
            _root(args),
            args.reservation_ref,
            args.reservation_sha256,
            outcome=args.outcome,
            owner_result=(
                _binding(owner_value, "owner_result") if owner_value else None
            ),
            observed_at=args.at,
            expected_version=args.expected_version,
        )
    )


def command_prepare_source_recovery(args: argparse.Namespace) -> int:
    result = prepare_source_recovery(
        _root(args), args.decision_ref, args.decision_sha256,
        prepared_at=args.at, skills_root=_skills_root(args),
    )
    return _emit(result)


def command_transition(args: argparse.Namespace) -> int:
    root = _root(args)
    result = transition_grants(
        root,
        args.grant_id,
        args.transition,
        event_id=args.event_id,
        expected_version=args.expected_version,
        source_approval=_binding(args.source_approval, "source_approval"),
        transitioned_at=args.at,
    )
    return _emit({"status": args.transition, **result})


def command_status(args: argparse.Namespace) -> int:
    return _emit(
        status_snapshot(
            _root(args),
            grant_id=args.grant_id,
            request_sha256=getattr(args, "request_sha256", None),
            evaluated_at=args.at,
            skills_root=_skills_root(args),
        )
    )


def command_resolve(args: argparse.Namespace) -> int:
    return _emit(
        resolve_operation(
            _root(args),
            load_object(args.request),
            load_object(args.context),
            evaluated_at=args.at,
            skills_root=_skills_root(args),
        )
    )


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", default=".")


def _add_at(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--at", required=True, help="RFC3339 time with timezone")


def _add_skills_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skills-root")


def _add_reconciliation_parsers(subparsers: Any) -> None:
    reconcile_parser = subparsers.add_parser("reconcile")
    _add_root(reconcile_parser)
    _add_at(reconcile_parser)
    reconcile_parser.add_argument("--reservation-ref", required=True)
    reconcile_parser.add_argument("--reservation-sha256", required=True)
    reconcile_parser.add_argument("--effect-evidence", required=True)
    reconcile_parser.add_argument("--pre-commit-verification")
    reconcile_parser.add_argument("--expected-version", type=int, required=True)
    reconcile_parser.add_argument("--idempotency-key", required=True)
    reconcile_parser.add_argument(
        "--outcome",
        choices=("confirmed_effect", "confirmed_no_effect", "still_unknown"),
        required=True,
    )
    reconcile_parser.set_defaults(func=command_reconcile)

    evidence_parser = subparsers.add_parser("prepare-reconciliation-evidence")
    _add_root(evidence_parser)
    _add_at(evidence_parser)
    evidence_parser.add_argument("--reservation-ref", required=True)
    evidence_parser.add_argument("--reservation-sha256", required=True)
    evidence_parser.add_argument("--owner-result")
    evidence_parser.add_argument("--expected-version", type=int, required=True)
    evidence_parser.add_argument(
        "--outcome",
        choices=("confirmed_effect", "confirmed_no_effect", "still_unknown"),
        required=True,
    )
    evidence_parser.set_defaults(func=command_prepare_reconciliation_evidence)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage deterministic authority v2 grants and leases."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_policy = subparsers.add_parser("snapshot-policy")
    _add_root(snapshot_policy)
    snapshot_policy.add_argument(
        "--policy-ref", default=".agent_goal/agent_authority.md"
    )
    snapshot_policy.add_argument("--expected-version", type=int, required=True)
    snapshot_policy.set_defaults(func=command_snapshot_policy)

    snapshot_source = subparsers.add_parser("snapshot-source")
    _add_root(snapshot_source)
    snapshot_source.add_argument("--source-ref", required=True)
    snapshot_source.set_defaults(func=command_snapshot_source)

    register = subparsers.add_parser("register-grant")
    _add_root(register)
    register.add_argument("--grant", required=True)
    register.set_defaults(func=command_register_grant)

    delegate = subparsers.add_parser("delegate")
    _add_root(delegate)
    delegate.add_argument("--parent-grant-id", required=True)
    delegate.add_argument("--grant", required=True)
    delegate.set_defaults(func=command_delegate)

    evaluate_parser = subparsers.add_parser("evaluate")
    _add_root(evaluate_parser)
    _add_at(evaluate_parser)
    _add_skills_root(evaluate_parser)
    evaluate_parser.add_argument("--request", required=True)
    evaluate_parser.add_argument("--context", required=True)
    evaluate_parser.set_defaults(func=command_evaluate)

    compose = subparsers.add_parser("compose")
    _add_root(compose)
    compose.add_argument("--composition", required=True)
    compose.set_defaults(func=command_compose)

    reserve_parser = subparsers.add_parser("reserve")
    _add_root(reserve_parser)
    _add_at(reserve_parser)
    _add_skills_root(reserve_parser)
    reserve_parser.add_argument("--decision-ref", required=True)
    reserve_parser.add_argument("--decision-sha256", required=True)
    reserve_parser.add_argument("--idempotency-key", required=True)
    reserve_parser.set_defaults(func=command_reserve)

    verify_parser = subparsers.add_parser("verify")
    _add_root(verify_parser)
    _add_at(verify_parser)
    _add_skills_root(verify_parser)
    verify_parser.add_argument("--reservation-ref", required=True)
    verify_parser.add_argument("--reservation-sha256", required=True)
    verify_parser.add_argument("--expected-version", type=int, required=True)
    verify_parser.add_argument(
        "--stage", choices=("pre_dispatch", "pre_commit"), required=True
    )
    verify_parser.set_defaults(func=command_verify)

    consume_parser = subparsers.add_parser("consume")
    _add_root(consume_parser)
    _add_at(consume_parser)
    _add_skills_root(consume_parser)
    consume_parser.add_argument("--reservation-ref", required=True)
    consume_parser.add_argument("--reservation-sha256", required=True)
    consume_parser.add_argument("--execution-result", required=True)
    consume_parser.add_argument("--pre-commit-verification", required=True)
    consume_parser.add_argument("--expected-subject-after-sha256", required=True)
    consume_parser.add_argument("--expected-version", type=int, required=True)
    consume_parser.add_argument("--idempotency-key", required=True)
    consume_parser.set_defaults(func=command_consume)

    release_parser = subparsers.add_parser("release")
    _add_root(release_parser)
    _add_at(release_parser)
    release_parser.add_argument("--reservation-ref", required=True)
    release_parser.add_argument("--reservation-sha256", required=True)
    release_parser.add_argument("--no-effect-evidence", required=True)
    release_parser.add_argument("--expected-version", type=int, required=True)
    release_parser.add_argument("--idempotency-key", required=True)
    release_parser.add_argument(
        "--effect-status",
        choices=("not_started", "verified_no_effect", "unknown_effect"),
        required=True,
    )
    release_parser.set_defaults(func=command_release)

    _add_reconciliation_parsers(subparsers)

    recovery_parser = subparsers.add_parser("prepare-source-recovery")
    _add_root(recovery_parser)
    _add_at(recovery_parser)
    _add_skills_root(recovery_parser)
    recovery_parser.add_argument("--decision-ref", required=True)
    recovery_parser.add_argument("--decision-sha256", required=True)
    recovery_parser.set_defaults(func=command_prepare_source_recovery)

    transition = subparsers.add_parser("transition")
    _add_root(transition)
    _add_at(transition)
    transition.add_argument("--grant-id", required=True)
    transition.add_argument(
        "--transition",
        choices=("revoked", "suspended", "expired", "reactivated"),
        required=True,
    )
    transition.add_argument("--event-id", required=True)
    transition.add_argument("--expected-version", type=int, required=True)
    transition.add_argument("--source-approval", required=True)
    transition.set_defaults(func=command_transition)

    status = subparsers.add_parser("status")
    _add_root(status)
    _add_skills_root(status)
    status.add_argument(
        "--at",
        help="RFC3339 evaluation time with timezone; defaults to the current UTC time",
    )
    status.add_argument("--grant-id")
    status.add_argument("--request-sha256")
    status.set_defaults(func=command_status)

    resolve_parser = subparsers.add_parser("resolve")
    _add_root(resolve_parser)
    _add_at(resolve_parser)
    _add_skills_root(resolve_parser)
    resolve_parser.add_argument("--request", required=True)
    resolve_parser.add_argument("--context", required=True)
    resolve_parser.set_defaults(func=command_resolve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SystemExit as exc:
        return emit_error(args.command, exc, _emit)


if __name__ == "__main__":
    raise SystemExit(main())
