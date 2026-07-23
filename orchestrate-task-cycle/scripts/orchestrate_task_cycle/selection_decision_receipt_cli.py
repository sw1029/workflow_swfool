"""Render or validate one persisted selection-decision receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence

from .selection_decision_receipt import (
    read_bound_json,
    read_selection_decision_receipt,
    render_preliminary_selection_decision,
    render_selection_decision_receipt,
)
from .selection_decision_receipt_values import (
    render_preliminary_selection_decision_from_values,
    render_selection_decision_receipt_from_values,
)
from .selection_synthesis import render_selection_synthesis
from .selection_decision_store import canonical_bytes
from .selection_publication_producer_capability import (
    _SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
)
from .selection_publication_reference_barrier import (
    registered_producer_barrier,
)
from .selection_publication_store import (
    _bounded_file_sha256,
    _write_once_with_status,
)
from .selection_trigger import (
    render_normal_cycle_trigger,
    render_publication_bootstrap,
)
from .selection_decision_receipt_v2 import (
    render_preliminary_selection_decision_v2_from_values,
    render_selection_decision_receipt_v2_from_values,
    validate_selection_decision_receipt_v2,
)


CYCLE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _binding(ref: str, digest: str) -> dict[str, str]:
    return {"ref": ref, "sha256": digest}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    commands = parser.add_subparsers(dest="action", required=True)
    synthesis = commands.add_parser("render-synthesis")
    synthesis.add_argument("--source-result-ref", required=True)
    synthesis.add_argument("--source-result-sha256", required=True)
    decision = commands.add_parser("render-decision")
    decision.add_argument("--trigger-tick-ref", required=True)
    decision.add_argument("--trigger-tick-sha256", required=True)
    decision.add_argument("--selection-synthesis-ref", required=True)
    decision.add_argument("--selection-synthesis-sha256", required=True)
    render = commands.add_parser("render")
    render.add_argument("--trigger-tick-ref", required=True)
    render.add_argument("--trigger-tick-sha256", required=True)
    render.add_argument("--selection-decision-ref", required=True)
    render.add_argument("--selection-decision-sha256", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--receipt-ref", required=True)
    validate.add_argument("--receipt-sha256", required=True)
    validate.add_argument("--trigger-tick-ref", required=True)
    validate.add_argument("--trigger-tick-sha256", required=True)
    pipeline = commands.add_parser("pipeline")
    pipeline.add_argument("--cycle-id", required=True)
    pipeline.add_argument("--source-result-ref", required=True)
    pipeline.add_argument("--source-result-sha256", required=True)
    pipeline.add_argument(
        "--trigger-kind",
        choices=("terminal_wait", "normal_cycle"),
        default="terminal_wait",
    )
    pipeline.add_argument("--trigger-tick-ref")
    pipeline.add_argument("--trigger-tick-sha256")
    for prefix in (
        "cycle-finalization",
        "schema-pre-derive",
        "current-task",
        "task-index",
        "publication-head",
    ):
        pipeline.add_argument(f"--{prefix}-ref")
        pipeline.add_argument(f"--{prefix}-sha256")
    return parser


def _pipeline_directory(
    root: Path, cycle_id: str, *, create: bool
) -> Path:
    if not CYCLE_ID.fullmatch(cycle_id):
        raise ValueError("selection decision pipeline cycle ID is invalid")
    directory = root / ".task" / "cycle" / cycle_id / "agent_receipts" / "selection"
    current = root
    for part in directory.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise ValueError("selection decision pipeline cannot traverse symlinks")
        if current.exists() and not current.is_dir():
            raise ValueError("selection decision pipeline output parent is not a directory")
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def _pipeline_artifact(
    root: Path, directory: Path, prefix: str, value: dict[str, Any]
) -> dict[str, Any]:
    payload = canonical_bytes(value)
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / f"{prefix}-{digest}.json"
    existing = path.exists() or path.is_symlink()
    if existing and _bounded_file_sha256(
        path, len(payload), f"selection decision {prefix}"
    ) != digest:
        raise ValueError(
            f"selection decision {prefix} conflicts with immutable evidence"
        )
    return {
        "prefix": prefix,
        "value": value,
        "binding": {
            "ref": path.relative_to(root).as_posix(),
            "sha256": digest,
        },
    }


def _persist_pipeline_artifact(
    root: Path, directory: Path, artifact: dict[str, Any]
) -> bool:
    prefix = artifact["prefix"]
    value = artifact["value"]
    payload = canonical_bytes(value)
    digest = hashlib.sha256(payload).hexdigest()
    path = directory / f"{prefix}-{digest}.json"
    persisted, created = _write_once_with_status(
        path,
        payload,
        f"selection decision {prefix}",
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    )
    binding = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": persisted,
    }
    if binding != artifact["binding"]:
        raise ValueError("selection decision artifact binding drifted")
    return created


def _required_normal_binding(
    args: argparse.Namespace, prefix: str
) -> dict[str, str]:
    ref = getattr(args, prefix + "_ref")
    digest = getattr(args, prefix + "_sha256")
    if not ref or not digest:
        option = prefix.replace("_", "-")
        raise ValueError(
            f"normal-cycle selection trigger requires --{option}-ref and SHA-256"
        )
    return _binding(ref, digest)


def _compile_pipeline(
    root: Path, args: argparse.Namespace
) -> dict[str, Any]:
    source_binding = _binding(args.source_result_ref, args.source_result_sha256)
    _, source_result = read_bound_json(
        root, source_binding, "derive synthesis source result"
    )
    synthesis = render_selection_synthesis(root, source_result)
    directory = _pipeline_directory(root, args.cycle_id, create=False)
    artifacts = [
        _pipeline_artifact(root, directory, "synthesis", synthesis)
    ]
    synthesis_binding = artifacts[0]["binding"]
    if args.trigger_kind == "normal_cycle":
        prospective_publication_head = None
        current_task = _required_normal_binding(args, "current_task")
        task_index = _required_normal_binding(args, "task_index")
        publication_ref = args.publication_head_ref
        publication_sha = args.publication_head_sha256
        if bool(publication_ref) != bool(publication_sha):
            raise ValueError(
                "normal-cycle publication head requires both ref and SHA-256"
            )
        if publication_ref:
            publication_head = _binding(publication_ref, publication_sha)
        else:
            bootstrap = render_publication_bootstrap(
                root,
                cycle_id=args.cycle_id,
                current_task=current_task,
                task_index=task_index,
            )
            bootstrap_artifact = _pipeline_artifact(
                root, directory, "publication-bootstrap", bootstrap
            )
            artifacts.append(bootstrap_artifact)
            publication_head = bootstrap_artifact["binding"]
            prospective_publication_head = bootstrap
        trigger = render_normal_cycle_trigger(
            root,
            cycle_id=args.cycle_id,
            cycle_finalization=_required_normal_binding(
                args, "cycle_finalization"
            ),
            schema_pre_derive=_required_normal_binding(
                args, "schema_pre_derive"
            ),
            derive_result=source_binding,
            current_task=current_task,
            task_index=task_index,
            publication_head=publication_head,
            input_evidence_manifest_sha256=synthesis[
                "input_evidence_manifest_sha256"
            ],
            _prospective_publication_head=prospective_publication_head,
        )
        trigger_artifact = _pipeline_artifact(
            root, directory, "trigger", trigger
        )
        artifacts.append(trigger_artifact)
        trigger_binding = trigger_artifact["binding"]
        decision = render_preliminary_selection_decision_v2_from_values(
            root,
            trigger_binding,
            trigger,
            synthesis_binding,
            synthesis,
            prospective_publication_head=prospective_publication_head,
        )
    else:
        trigger_binding, trigger = _trigger(root, args)
        decision = render_preliminary_selection_decision_from_values(
            root, trigger, synthesis_binding, synthesis
        )
    decision_artifact = _pipeline_artifact(
        root, directory, "decision", decision
    )
    artifacts.append(decision_artifact)
    decision_binding = decision_artifact["binding"]
    receipt = (
        render_selection_decision_receipt_v2_from_values(
            root,
            trigger_binding,
            trigger,
            decision_binding,
            decision,
            synthesis,
            prospective_publication_head=prospective_publication_head,
        )
        if args.trigger_kind == "normal_cycle"
        else render_selection_decision_receipt_from_values(
            root,
            trigger,
            trigger_binding,
            decision_binding,
            decision,
            synthesis,
        )
    )
    receipt_artifact = _pipeline_artifact(
        root, directory, "receipt", receipt
    )
    artifacts.append(receipt_artifact)
    return {
        "directory": directory,
        "artifacts": artifacts,
        "trigger": trigger,
        "trigger_binding": trigger_binding,
        "synthesis_binding": synthesis_binding,
        "decision_binding": decision_binding,
        "receipt_binding": receipt_artifact["binding"],
    }


def _publish_pipeline(
    root: Path, args: argparse.Namespace, plan: dict[str, Any]
) -> dict[str, Any]:
    directory = _pipeline_directory(root, args.cycle_id, create=True)
    created = [
        _persist_pipeline_artifact(root, directory, artifact)
        for artifact in plan["artifacts"]
    ]
    receipt_binding = plan["receipt_binding"]
    if args.trigger_kind == "normal_cycle":
        _, reopened_value = read_bound_json(
            root, receipt_binding, "selection decision receipt v2"
        )
        reopened = validate_selection_decision_receipt_v2(root, reopened_value)
    else:
        reopened = read_selection_decision_receipt(
            root,
            receipt_binding,
            expected_trigger_tick=plan["trigger"],
        )
    return {
        "status": "completed",
        "cycle_id": args.cycle_id,
        "outcome": reopened["outcome"],
        "selected_task_id": reopened["selected_task_id"],
        "trigger_kind": args.trigger_kind,
        "trigger": plan["trigger_binding"],
        "synthesis": plan["synthesis_binding"],
        "decision": plan["decision_binding"],
        "receipt": receipt_binding,
        "mutation_performed": any(created),
    }


def _pipeline(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    root = root.expanduser().resolve(strict=True)
    preflight = _compile_pipeline(root, args)
    with registered_producer_barrier(
        root,
        producer_capability=_SELECTION_PUBLICATION_PRODUCER_CAPABILITY,
    ):
        refreshed = _compile_pipeline(root, args)
        if refreshed != preflight:
            raise ValueError(
                "selection decision inputs changed during barrier acquisition"
            )
        return _publish_pipeline(root, args, refreshed)


def _trigger(
    root: Path, args: argparse.Namespace
) -> tuple[dict[str, str], dict[str, Any]]:
    if not args.trigger_tick_ref or not args.trigger_tick_sha256:
        raise ValueError("terminal-wait selection requires an exact trigger tick")
    binding = _binding(args.trigger_tick_ref, args.trigger_tick_sha256)
    _, trigger = read_bound_json(
        root,
        binding,
        "selection trigger tick",
    )
    return binding, trigger


def _run(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    if args.action == "pipeline":
        return _pipeline(root, args)
    if args.action == "render-synthesis":
        _, source_result = read_bound_json(
            root,
            _binding(args.source_result_ref, args.source_result_sha256),
            "derive synthesis source result",
        )
        return render_selection_synthesis(root, source_result)
    trigger_binding, trigger = _trigger(root, args)
    if args.action == "render-decision":
        return render_preliminary_selection_decision(
            root,
            trigger,
            _binding(
                args.selection_synthesis_ref,
                args.selection_synthesis_sha256,
            ),
        )
    if args.action == "render":
        return render_selection_decision_receipt(
            root,
            trigger,
            trigger_binding,
            _binding(
                args.selection_decision_ref,
                args.selection_decision_sha256,
            ),
        )
    return read_selection_decision_receipt(
        root,
        _binding(args.receipt_ref, args.receipt_sha256),
        expected_trigger_tick=trigger,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(Path(args.root), args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "block", "error": str(exc), "mutation_performed": False}
        code = 2
    else:
        code = 0
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
