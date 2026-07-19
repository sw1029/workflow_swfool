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
from .operation_compiler import compilation_inputs
from .operation_compiler import compile_operation
from .operation_publication import publish_compilation
from .workflow_status import resolve_operation
from .workflow_status import status_snapshot
from .reconciliation_evidence import prepare_reconciliation_evidence
from .source_recovery import prepare_source_recovery
from .cli_errors import emit_error
from .cli_parser import build_parser as _build_parser


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


def _input_object(value: str) -> dict[str, Any]:
    if value == "-":
        try:
            loaded = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"JSON input is invalid: {exc}") from exc
        if not isinstance(loaded, dict):
            raise SystemExit("JSON input must be an object.")
        return loaded
    return load_object(value)


def _operation_inputs(
    args: argparse.Namespace, root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    compiled = getattr(args, "compiled_operation", None)
    if compiled is not None:
        if getattr(args, "context", None) is not None:
            raise SystemExit(
                "--context cannot be combined with --compiled-operation."
            )
        return compilation_inputs(
            root,
            _input_object(compiled),
            skills_root=_skills_root(args),
        )
    if getattr(args, "context", None) is None:
        raise SystemExit("--request requires --context.")
    return load_object(args.request), load_object(args.context)


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


def command_compile_operation(args: argparse.Namespace) -> int:
    root = _root(args)
    compilation = compile_operation(
        root,
        _input_object(args.seed),
        compiled_at=args.at,
        skills_root=_skills_root(args),
    )
    if args.publish:
        return _emit(publish_compilation(root, compilation))
    return _emit(compilation)


def command_delegate(args: argparse.Namespace) -> int:
    result = register_grant(
        _root(args), load_object(args.grant), parent_id=args.parent_grant_id
    )
    return _emit({"status": "delegated", **result})


def command_evaluate(args: argparse.Namespace) -> int:
    root = _root(args)
    request, context = _operation_inputs(args, root)
    decision = evaluate(
        root,
        request,
        context,
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
    root = _root(args)
    request, context = _operation_inputs(args, root)
    return _emit(
        resolve_operation(
            root,
            request,
            context,
            evaluated_at=args.at,
            skills_root=_skills_root(args),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    handlers = {
        "compile_operation": command_compile_operation,
        "snapshot_policy": command_snapshot_policy,
        "snapshot_source": command_snapshot_source,
        "register_grant": command_register_grant,
        "delegate": command_delegate,
        "evaluate": command_evaluate,
        "compose": command_compose,
        "reserve": command_reserve,
        "verify": command_verify,
        "consume": command_consume,
        "release": command_release,
        "reconcile": command_reconcile,
        "prepare_reconciliation_evidence": command_prepare_reconciliation_evidence,
        "prepare_source_recovery": command_prepare_source_recovery,
        "transition": command_transition,
        "status": command_status,
        "resolve": command_resolve,
    }
    return _build_parser(handlers)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SystemExit as exc:
        return emit_error(args.command, exc, _emit)


if __name__ == "__main__":
    raise SystemExit(main())
