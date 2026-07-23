"""Compile or publish one exact user-escalation authority re-entry chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .selection_authority_reentry import (
    compile_authority_reentry,
    publish_authority_reentry,
)


def _add_binding(
    parser: argparse.ArgumentParser,
    name: str,
    *,
    required: bool = True,
) -> None:
    option = name.replace("_", "-")
    parser.add_argument(f"--{option}-ref", required=required)
    parser.add_argument(f"--{option}-sha256", required=required)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    command = parser.add_subparsers(dest="action", required=True)
    publish = command.add_parser("publish")
    publish.add_argument("--cycle-id", required=True)
    publish.add_argument("--at", required=True)
    _add_binding(publish, "source_result")
    _add_binding(publish, "cycle_finalization")
    _add_binding(publish, "schema_pre_derive")
    _add_binding(publish, "current_task")
    _add_binding(publish, "task_index")
    _add_binding(publish, "publication_head", required=False)
    publish.add_argument("--authority-decision-ref", action="append", default=[])
    publish.add_argument(
        "--authority-decision-sha256",
        action="append",
        default=[],
    )
    publish.add_argument("--skills-root")
    publish.add_argument("--dry-run", action="store_true")
    return parser


def _binding(args: argparse.Namespace, name: str) -> dict[str, str] | None:
    ref = getattr(args, f"{name}_ref")
    digest = getattr(args, f"{name}_sha256")
    if bool(ref) != bool(digest):
        option = name.replace("_", "-")
        raise ValueError(f"{option} requires both ref and SHA-256")
    return {"ref": ref, "sha256": digest} if ref else None


def _required_binding(args: argparse.Namespace, name: str) -> dict[str, str]:
    binding = _binding(args, name)
    if binding is None:
        raise ValueError(f"{name.replace('_', '-')} binding is required")
    return binding


def _skills_root(args: argparse.Namespace) -> Path:
    if args.skills_root:
        return Path(args.skills_root)
    return Path(__file__).resolve().parents[3]


def _compile(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    refs = args.authority_decision_ref
    digests = args.authority_decision_sha256
    if not refs or len(refs) != len(digests):
        raise ValueError(
            "authority decisions require matching non-empty ref and SHA-256 lists"
        )
    publication_head = _binding(args, "publication_head")
    return compile_authority_reentry(
        root,
        cycle_id=args.cycle_id,
        source_result=_required_binding(args, "source_result"),
        cycle_finalization=_required_binding(args, "cycle_finalization"),
        schema_pre_derive=_required_binding(args, "schema_pre_derive"),
        current_task=_required_binding(args, "current_task"),
        task_index=_required_binding(args, "task_index"),
        publication_head=publication_head,
        authority_decisions=[
            {"ref": ref, "sha256": digest}
            for ref, digest in zip(refs, digests, strict=True)
        ],
        skills_root=_skills_root(args),
        at=args.at,
    )


def _preflight_projection(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "authority_reentry_publication_preflight",
        "status": "ready",
        "selected_task_id": plan["selected_task_id"],
        "trigger": plan["trigger"],
        "synthesis": plan["synthesis"],
        "task_source": plan["task_source"],
        "resolution": plan["resolution"],
        "decision": plan["decision"],
        "receipt": plan["receipt"],
        "effect_boundary": "preparation_only",
        "not_authority": True,
        "mutation_performed": False,
    }


def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).expanduser().resolve(strict=True)
    plan = _compile(root, args)
    if args.dry_run:
        return _preflight_projection(plan)
    return publish_authority_reentry(root, plan)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (
        KeyError,
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        SystemExit,
    ) as exc:
        result = {
            "schema_version": 1,
            "artifact_kind": "authority_reentry_publication_result",
            "status": "block",
            "error": str(exc),
            "effect_boundary": "preparation_only",
            "not_authority": True,
            "mutation_performed": False,
        }
        code = 2
    else:
        code = 0
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
