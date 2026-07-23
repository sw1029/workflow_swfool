#!/usr/bin/env python3
"""Compile a bounded semantic draft into one immutable acceptance owner result."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .acceptance_cas import immutable_write
from .acceptance_contract_registry import (
    RICH_ACCEPTANCE_CONTRACT_FIELDS,
    VERIFIER_CONTRACT_FIELDS,
)
from .acceptance_identity import (
    AcceptanceIdentityError,
    bind,
)


COMPILER_ID = "normalize_acceptance.owner.v2"
MAX_DRAFT_BYTES = 64 * 1024
MAX_COMPILED_BYTES = 128 * 1024
SEMANTIC_FIELDS = frozenset(
    {
        "acceptance_status",
        "acceptance_criteria",
        "blockers",
        "evidence_paths",
        "acceptance_scenarios",
        "validation_predicate_contract",
        "producer_directives",
        "acceptance_contract",
    }
)
REQUIRED_SEMANTIC_FIELDS = frozenset(
    {"acceptance_status", "acceptance_criteria", "blockers", "evidence_paths"}
)
DERIVED_FIELDS = frozenset(
    {
        "format_version",
        "schema_version",
        "artifact_kind",
        "step",
        "task_id",
        "acceptance_id",
        "acceptance_provenance",
        "satisfiability_rows",
        "mutually_unsatisfiable_contract",
        "unverifiable_acceptance_contract",
    }
)


def _publication_race_hook(stage: str, path: Path) -> None:
    """Private deterministic race-injection seam used by storage tests."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except ValueError as exc:
        raise AcceptanceIdentityError(
            "semantic draft contains a non-finite JSON number"
        ) from exc


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _workspace_file(root: Path, ref: str, label: str) -> Path:
    raw = Path(ref)
    if raw.is_absolute() or not raw.parts or ".." in raw.parts:
        raise AcceptanceIdentityError(
            f"{label} ref must be a workspace-relative path"
        )
    candidate = root
    for part in raw.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise AcceptanceIdentityError(f"{label} ref must not traverse a symlink")
    try:
        path = candidate.resolve(strict=True)
        path.relative_to(root)
    except (FileNotFoundError, ValueError) as exc:
        raise AcceptanceIdentityError(
            f"{label} path does not resolve to a workspace file"
        ) from exc
    if not path.is_file():
        raise AcceptanceIdentityError(f"{label} must identify one regular file")
    return path


def _read_draft(
    root: Path, binding: dict[str, str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if set(binding) != {"ref", "sha256"}:
        raise AcceptanceIdentityError("draft binding must contain exact ref and sha256")
    ref, expected = binding["ref"], binding["sha256"]
    if (
        not isinstance(ref, str)
        or not ref
        or not isinstance(expected, str)
        or len(expected) != 64
        or any(character not in "0123456789abcdef" for character in expected)
    ):
        raise AcceptanceIdentityError("draft binding values are invalid")
    path = _workspace_file(root, ref, "semantic draft")
    size = path.stat().st_size
    if size > MAX_DRAFT_BYTES:
        raise AcceptanceIdentityError(
            f"semantic draft exceeds the {MAX_DRAFT_BYTES}-byte limit"
        )
    payload = path.read_bytes()
    if len(payload) > MAX_DRAFT_BYTES:
        raise AcceptanceIdentityError(
            f"semantic draft exceeds the {MAX_DRAFT_BYTES}-byte limit"
        )
    if sha256_bytes(payload) != expected:
        raise AcceptanceIdentityError("semantic draft sha256 does not match exact bytes")
    try:
        draft = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceIdentityError("semantic draft is not valid UTF-8 JSON") from exc
    if not isinstance(draft, dict):
        raise AcceptanceIdentityError("semantic draft must be a JSON object")
    return draft, {
        "ref": path.relative_to(root).as_posix(),
        "sha256": expected,
        "size_bytes": len(payload),
    }


def _validate_semantic_draft(draft: dict[str, Any]) -> None:
    derived = set(draft) & DERIVED_FIELDS
    if derived:
        raise AcceptanceIdentityError(
            "semantic draft contains compiler-derived fields: "
            + ", ".join(sorted(derived))
        )
    unknown = set(draft) - SEMANTIC_FIELDS
    if unknown:
        raise AcceptanceIdentityError(
            "semantic draft contains unsupported fields: "
            + ", ".join(sorted(unknown))
        )
    missing = REQUIRED_SEMANTIC_FIELDS - set(draft)
    if missing:
        raise AcceptanceIdentityError(
            "semantic draft is missing required fields: "
            + ", ".join(sorted(missing))
        )
    predicate_contract = draft.get("validation_predicate_contract")
    if (
        isinstance(predicate_contract, dict)
        and "satisfiability_rows" in predicate_contract
    ):
        raise AcceptanceIdentityError(
            "semantic draft must not author compiler-derived satisfiability_rows"
        )
    acceptance_contract = draft.get("acceptance_contract")
    if acceptance_contract is not None:
        if not isinstance(acceptance_contract, dict):
            raise AcceptanceIdentityError(
                "semantic draft acceptance_contract must be a JSON object"
            )
        unknown_contract = (
            set(acceptance_contract) - RICH_ACCEPTANCE_CONTRACT_FIELDS
        )
        if unknown_contract:
            raise AcceptanceIdentityError(
                "semantic draft acceptance_contract contains unsupported fields: "
                + ", ".join(sorted(unknown_contract))
            )
        verifier = acceptance_contract.get("acceptance_verifier_contract")
        if verifier is not None:
            if not isinstance(verifier, dict):
                raise AcceptanceIdentityError(
                    "acceptance_verifier_contract must be a JSON object"
                )
            unknown_verifier = set(verifier) - VERIFIER_CONTRACT_FIELDS
            if unknown_verifier:
                raise AcceptanceIdentityError(
                    "acceptance_verifier_contract contains unsupported fields: "
                    + ", ".join(sorted(unknown_verifier))
                )
            required_hooks = verifier.get("required_gate_hooks")
            if required_hooks is not None and (
                not isinstance(required_hooks, list)
                or any(
                    not isinstance(hook, str) or not hook.strip()
                    for hook in required_hooks
                )
            ):
                raise AcceptanceIdentityError(
                    "required_gate_hooks must be a list of non-empty hook IDs"
                )


def _immutable_write(root: Path, path: Path, payload: bytes) -> bool:
    return immutable_write(
        root,
        path,
        payload,
        race_hook=_publication_race_hook,
    )


def compile_acceptance(
    root: Path,
    *,
    task_id: str,
    task_path: str,
    draft_binding: dict[str, str],
    publish: bool = True,
) -> dict[str, Any]:
    """Return a compact binding summary; never return the compiled packet body."""

    root = root.resolve()
    draft, exact_draft_binding = _read_draft(root, draft_binding)
    _validate_semantic_draft(draft)
    result = bind(root, task_id, task_path, draft, True)
    result.pop("format_version", None)
    result = {
        "format_version": 2,
        "schema_version": 1,
        "artifact_kind": "acceptance_packet",
        **result,
    }
    result["acceptance_provenance"] = {
        **result["acceptance_provenance"],
        "source_semantic_draft_ref": exact_draft_binding["ref"],
        "source_semantic_draft_sha256": exact_draft_binding["sha256"],
    }
    body = {
        "schema_version": 2,
        "artifact_kind": "compiled_acceptance_owner_result",
        "compiler_id": COMPILER_ID,
        "source_draft_binding": exact_draft_binding,
        "result": result,
        "result_sha256": sha256_bytes(canonical_bytes(result)),
    }
    payload = canonical_bytes(body) + b"\n"
    if len(payload) > MAX_COMPILED_BYTES:
        raise AcceptanceIdentityError(
            f"compiled acceptance exceeds the {MAX_COMPILED_BYTES}-byte limit"
        )
    digest = sha256_bytes(payload)
    ref = f".task/acceptance/sha256/{digest}.json"
    path = root / ref
    mutation_performed = (
        _immutable_write(root, path, payload) if publish else False
    )
    return {
        "schema_version": 1,
        "artifact_kind": "acceptance_compile_result",
        "compiler_id": COMPILER_ID,
        "status": "published" if publish else "dry_run",
        "acceptance_id": result["acceptance_id"],
        "task_id": result["task_id"],
        "source_draft_binding": exact_draft_binding,
        "owner_result_binding": {
            "ref": ref,
            "sha256": digest,
            "size_bytes": len(payload),
        },
        "mutation_performed": mutation_performed,
        "duplicate": publish and not mutation_performed,
        "model_authored_mechanical_bytes": 0,
    }


def validate_compiled_acceptance(
    root: Path,
    value: Any,
    *,
    source_ref: str,
    expected_task_id: str,
) -> dict[str, Any]:
    """Recompile a producer artifact from its exact draft and current task bytes."""

    root = root.resolve(strict=True)
    expected_fields = {
        "schema_version",
        "artifact_kind",
        "compiler_id",
        "source_draft_binding",
        "result",
        "result_sha256",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected_fields
        or value.get("schema_version") != 2
        or value.get("artifact_kind") != "compiled_acceptance_owner_result"
        or value.get("compiler_id") != COMPILER_ID
    ):
        raise AcceptanceIdentityError(
            "compiled acceptance envelope is not a closed supported contract"
        )
    payload = canonical_bytes(value) + b"\n"
    digest = sha256_bytes(payload)
    expected_ref = f".task/acceptance/sha256/{digest}.json"
    if source_ref != expected_ref:
        raise AcceptanceIdentityError(
            "compiled acceptance ref is not its exact producer CAS path"
        )
    draft_binding = value.get("source_draft_binding")
    if not isinstance(draft_binding, dict) or set(draft_binding) != {
        "ref",
        "sha256",
        "size_bytes",
    }:
        raise AcceptanceIdentityError(
            "compiled acceptance draft binding is not closed"
        )
    draft, normalized_draft = _read_draft(
        root,
        {
            "ref": draft_binding.get("ref"),
            "sha256": draft_binding.get("sha256"),
        },
    )
    if draft_binding != normalized_draft:
        raise AcceptanceIdentityError(
            "compiled acceptance draft binding differs from exact source bytes"
        )
    _validate_semantic_draft(draft)
    result = value.get("result")
    provenance = (
        result.get("acceptance_provenance")
        if isinstance(result, dict)
        and isinstance(result.get("acceptance_provenance"), dict)
        else {}
    )
    if (
        not isinstance(expected_task_id, str)
        or not expected_task_id
        or not isinstance(result, dict)
        or result.get("task_id") != expected_task_id
        or provenance.get("source_task_id") != expected_task_id
        or not isinstance(provenance.get("source_task_path"), str)
    ):
        raise AcceptanceIdentityError(
            "compiled acceptance task does not match the consuming cycle"
        )
    expected_result = bind(
        root,
        expected_task_id,
        provenance["source_task_path"],
        draft,
        True,
    )
    expected_result.pop("format_version", None)
    expected_result = {
        "format_version": 2,
        "schema_version": 1,
        "artifact_kind": "acceptance_packet",
        **expected_result,
    }
    expected_result["acceptance_provenance"] = {
        **expected_result["acceptance_provenance"],
        "source_semantic_draft_ref": normalized_draft["ref"],
        "source_semantic_draft_sha256": normalized_draft["sha256"],
    }
    expected = {
        "schema_version": 2,
        "artifact_kind": "compiled_acceptance_owner_result",
        "compiler_id": COMPILER_ID,
        "source_draft_binding": normalized_draft,
        "result": expected_result,
        "result_sha256": sha256_bytes(canonical_bytes(expected_result)),
    }
    if value != expected:
        raise AcceptanceIdentityError(
            "compiled acceptance differs from deterministic recompilation"
        )
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compile one semantic acceptance draft into a deterministic CAS owner result."
        )
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-path", default="task.md")
    parser.add_argument("--draft-ref", required=True)
    parser.add_argument("--draft-sha256", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = compile_acceptance(
            Path(args.root),
            task_id=args.task_id,
            task_path=args.task_path,
            draft_binding={
                "ref": args.draft_ref,
                "sha256": args.draft_sha256,
            },
            publish=not args.dry_run,
        )
    except (AcceptanceIdentityError, OSError, UnicodeError) as exc:
        output = {
            "schema_version": 1,
            "artifact_kind": "acceptance_compile_result",
            "status": "block",
            "error": str(exc),
        }
        json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
