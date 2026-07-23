from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .artifact_store import snapshot_file, transition_grants, update_current_policy
from .canonical import load_object
from .composition_intent_compiler import compile_grant_composition
from .decision_publication import evaluate_and_publish
from .lifecycle import consume
from .lifecycle import release
from .reconciliation import reconcile_quarantine
from .lifecycle import reserve
from .operation_compiler import compilation_inputs, compile_operation
from .operation_publication import load_published_compilation, publish_compilation
from .operation_batch import publish_operation_batch, publish_operation_set
from .root_grant import (
    materialize_plan_bound_root_grant,
    prepare_root_approval_plan,
)
from .root_decision_seed import compile_root_decision_seed
from .root_authorization_evidence import publish_root_authorization_evidence
from .grant_intent_compiler import (
    compile_delegated_grant,
    replay_registered_grant,
)
from .semantic_context import publish_shared_semantic_context
from .workflow_status import resolve_operation
from .workflow_status import status_snapshot
from .reconciliation_evidence import prepare_reconciliation_evidence
from .source_recovery import prepare_source_recovery
from .settlement import settle_owner_result
from .recovery_materialization import materialize_approved_recovery
from .verification_publication import verify_and_publish_precommit
from .verification_publication import verify_and_publish_predispatch
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


def _input_json(value: str) -> Any:
    if value == "-":
        try:
            loaded = json.load(sys.stdin)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"JSON input is invalid: {exc}") from exc
        return loaded
    try:
        candidate = Path(value)
        is_file = candidate.is_file()
    except OSError:
        is_file = False
    try:
        source = candidate.read_text(encoding="utf-8") if is_file else value
        return json.loads(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"JSON input is invalid: {exc}") from exc


def _input_object(value: str) -> dict[str, Any]:
    loaded = _input_json(value)
    if not isinstance(loaded, dict):
        raise SystemExit("JSON input must be an object.")
    return loaded


def _operation_inputs(
    args: argparse.Namespace, root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    compiled = getattr(args, "compiled_operation", None)
    if compiled is not None:
        if getattr(args, "context", None) is not None:
            raise SystemExit(
                "--context cannot be combined with --compiled-operation."
            )
        _, compilation = load_published_compilation(root, _input_object(compiled))
        return compilation_inputs(
            root,
            compilation,
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
    return _emit(
        replay_registered_grant(_root(args), load_object(args.grant))
    )


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


def command_compile_semantic_context(args: argparse.Namespace) -> int:
    return _emit(
        publish_shared_semantic_context(
            _root(args),
            _binding(args.initialization, "initialization"),
            _input_object(args.semantic),
        )
    )


def command_publish_operation_set(args: argparse.Namespace) -> int:
    return _emit(
        publish_operation_set(_root(args), _input_json(args.operations))
    )


def command_compile_operation_batch(args: argparse.Namespace) -> int:
    return _emit(
        publish_operation_batch(
            _root(args),
            _binding(args.semantic_context, "semantic_context"),
            _binding(args.operation_set, "operation_set"),
            compiled_at=args.at,
            skills_root=_skills_root(args),
        )
    )


def command_prepare_root_approval(args: argparse.Namespace) -> int:
    return _emit(
        prepare_root_approval_plan(
            _root(args),
            _binding(args.operation_batch, "operation_batch"),
            _binding(args.policy_snapshot, "policy_snapshot"),
            _input_object(args.grant_semantics),
            prepared_at=args.at,
            skills_root=_skills_root(args),
        )
    )


def command_compile_root_decision_seed(args: argparse.Namespace) -> int:
    return _emit(
        compile_root_decision_seed(
            _root(args),
            _binding(args.approval_plan, "approval_plan"),
            authorization_evidence=_binding(
                args.authorization_evidence, "authorization_evidence"
            ),
            skills_root=_skills_root(args),
        )
    )


def command_publish_root_authorization_evidence(
    args: argparse.Namespace,
) -> int:
    return _emit(
        publish_root_authorization_evidence(
            _root(args),
            _input_object(args.evidence),
            skills_root=_skills_root(args),
        )
    )


def command_materialize_plan_bound_root_grant(
    args: argparse.Namespace,
) -> int:
    return _emit(
        materialize_plan_bound_root_grant(
            _root(args),
            _binding(args.approval_plan, "approval_plan"),
            _binding(args.decision_seed, "decision_seed"),
            skills_root=_skills_root(args),
        )
    )


def command_delegate(args: argparse.Namespace) -> int:
    return _emit(
        compile_delegated_grant(
            _root(args),
            args.parent_grant_id,
            _input_object(args.semantics),
            delegated_at=args.at,
        )
    )


def command_evaluate(args: argparse.Namespace) -> int:
    root = _root(args)
    request, context = _operation_inputs(args, root)
    return _emit(
        evaluate_and_publish(
            root,
            request,
            context,
            evaluated_at=args.at,
            skills_root=_skills_root(args),
        )
    )


def command_compose(args: argparse.Namespace) -> int:
    return _emit(
        compile_grant_composition(
            _root(args),
            _binding(args.operation_batch, "operation_batch"),
            args.request_sha256,
            args.grant_ids,
            _binding(args.source_approval, "source_approval"),
            created_at=args.at,
            skills_root=_skills_root(args),
        )
    )


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
    publisher = (
        verify_and_publish_precommit
        if args.stage == "pre_commit"
        else verify_and_publish_predispatch
    )
    return _emit(
        publisher(
            _root(args),
            args.reservation_ref,
            args.reservation_sha256,
            verified_at=args.at,
            expected_version=args.expected_version,
            skills_root=_skills_root(args),
        )
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


def command_settle(args: argparse.Namespace) -> int:
    result = settle_owner_result(
        _root(args),
        args.reservation_ref,
        args.reservation_sha256,
        _binding(args.owner_result, "owner_result"),
        _binding(args.pre_commit_verification, "pre_commit_verification"),
        settled_at=args.at,
        expected_version=args.expected_version,
        idempotency_key=args.idempotency_key,
        skills_root=_skills_root(args),
    )
    return _emit(result)


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
        skills_root=_skills_root(args),
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


def command_materialize_approved_recovery(args: argparse.Namespace) -> int:
    return _emit(
        materialize_approved_recovery(
            _root(args),
            _binding(args.recovery_recipe, "recovery_recipe"),
            _binding(args.user_decision, "user_decision"),
            skills_root=_skills_root(args),
        )
    )


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
        "compile_semantic_context": command_compile_semantic_context,
        "publish_operation_set": command_publish_operation_set,
        "compile_operation": command_compile_operation,
        "compile_operation_batch": command_compile_operation_batch,
        "prepare_root_approval": command_prepare_root_approval,
        "publish_root_authorization_evidence":
            command_publish_root_authorization_evidence,
        "compile_root_decision_seed": command_compile_root_decision_seed,
        "snapshot_policy": command_snapshot_policy,
        "snapshot_source": command_snapshot_source,
        "register_grant": command_register_grant,
        "delegate": command_delegate,
        "evaluate": command_evaluate,
        "compose": command_compose,
        "reserve": command_reserve,
        "verify": command_verify,
        "consume": command_consume,
        "settle": command_settle,
        "release": command_release,
        "reconcile": command_reconcile,
        "prepare_reconciliation_evidence": command_prepare_reconciliation_evidence,
        "prepare_source_recovery": command_prepare_source_recovery,
        "materialize_approved_recovery": command_materialize_approved_recovery,
        "materialize_plan_bound_root_grant":
            command_materialize_plan_bound_root_grant,
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
