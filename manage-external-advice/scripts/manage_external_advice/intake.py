"""Registry initialization and raw-to-normalized advice intake."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .intake_plan import (
    apply_intake_plan,
    build_intake_plan,
    exact_duplicate_result,
    publish_intake_plan,
)
from .storage import (
    ensure_dirs,
    rebuild_index,
)


def load_source(source: str) -> tuple[str, str]:
    if source == "-":
        text = sys.stdin.read()
        return text, "stdin"
    path = Path(source)
    text = path.read_text(encoding="utf-8", errors="replace")
    return text, str(path)


def bounded_source_ref(
    root: Path,
    source: str,
    text: str,
    staging_ref: str | None,
) -> str:
    candidate_value = staging_ref or (None if source == "-" else source)
    if not candidate_value:
        raise SystemExit(
            "stdin intake planning requires --staging-ref to an existing workspace UTF-8 file"
        )
    candidate = Path(candidate_value)
    candidate = candidate if candidate.is_absolute() else Path.cwd() / candidate
    if candidate.is_symlink() or not candidate.is_file():
        raise SystemExit("Advice intake source_ref must be a regular non-symlink file")
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(
            "Advice intake planning source must be workspace-relative; use --staging-ref"
        ) from exc
    try:
        staged_text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit("Advice intake source_ref must contain valid UTF-8") from exc
    if staged_text != text:
        raise SystemExit("Advice intake --staging-ref does not match the supplied source")
    return relative.as_posix()


def cmd_init(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    ensure_dirs(root)
    result = rebuild_index(root)
    print(
        json.dumps(
            {"status": "ok", **result}, ensure_ascii=False, indent=2, sort_keys=True
        )
    )


def cmd_intake(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    apply_plan = getattr(args, "apply_plan", None)
    if apply_plan:
        result = apply_intake_plan(root, apply_plan)
    else:
        source = getattr(args, "source", None)
        if not source:
            raise SystemExit("intake requires --source unless --apply-plan is used")
        text, _transient_source_locator = load_source(source)
        duplicate = exact_duplicate_result(root, text)
        if duplicate:
            print(
                json.dumps(
                    duplicate,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return
        source_ref = bounded_source_ref(
            root, source, text, getattr(args, "staging_ref", None)
        )
        plan = build_intake_plan(
            root,
            text,
            getattr(args, "title", None),
            getattr(args, "priority", "normal"),
            at=getattr(args, "at", None),
            source_ref=source_ref,
        )
        if plan.get("plan_kind") is None:
            result = plan
        else:
            plan_output = getattr(args, "plan", None)
            planned = publish_intake_plan(root, plan, plan_output)
            result = planned if plan_output else apply_intake_plan(root, planned["plan_ref"])
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
