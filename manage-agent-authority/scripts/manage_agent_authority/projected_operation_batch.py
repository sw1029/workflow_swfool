"""Seal exact owner-projected compilations as one root-approval batch."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from .canonical import (
    canonical_bytes,
    object_sha256,
    write_immutable_json,
)
from .operation_batch_compilation import (
    MAX_OPERATION_BATCH_BYTES,
    OPERATION_BATCH_ROOT,
)


SOURCE_KIND = "selected_successor_authority_approval_projection"
SOURCE_KEYS = {"kind", "binding"}
PROJECTED_BATCH_KEYS = {
    "schema_version",
    "artifact_kind",
    "compiled_at",
    "projection_source",
    "operation_compilations",
    "operation_count",
    "field_provenance",
    "batch_fingerprint",
}
PROJECTED_BATCH_PROVENANCE = {
    "owner_projection": [
        "exact projection binding",
        "exact projected operation membership and order",
        "compilation timestamp",
    ],
    "compiler_derived": [
        "operation rows",
        "request digests",
        "batch fingerprint and CAS path",
    ],
    "authority_effect": "none",
    "replay_validation": (
        "fixed isolated current-owner validation on compilation, publication, "
        "load, and replay"
    ),
}
SOURCE_RECEIPT_KEYS = {
    "schema_version",
    "artifact_kind",
    "validation_status",
    "projection_source",
    "compiled_at",
    "operation_compilations",
    "operation_count",
    "receipt_sha256",
}
SOURCE_IMPORT_SKILLS = (
    "orchestrate-task-cycle",
    "manage-agent-authority",
    "manage-external-advice",
    "manage-task-state-index",
    "normalize-acceptance-and-demo",
    "record-agent-work-log",
    "audit-session-governance",
)


def _trusted_source_receipt(
    root: Path,
    projection_binding: dict[str, str],
    *,
    skills_root: Path | None,
) -> dict[str, Any]:
    from .owner_validator_process import (
        isolated_owner_validator_argv,
        run_bounded_owner_validator,
    )

    trusted_root = Path(__file__).resolve().parents[3]
    if skills_root is not None and skills_root.resolve() != trusted_root:
        raise SystemExit(
            "Projected operation batches require the co-located skills root."
        )
    import_roots = [
        (trusted_root / skill / "scripts").resolve(strict=True)
        for skill in SOURCE_IMPORT_SKILLS
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONSTARTUP", None)
    environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in import_roots)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONSAFEPATH"] = "1"
    argv = isolated_owner_validator_argv(
        "orchestrate_task_cycle",
        [
            "selected-successor",
            "--root",
            str(root.resolve()),
            "validate-approval-batch-source",
            "--approval-projection-ref",
            str(projection_binding.get("ref") or ""),
            "--approval-projection-sha256",
            str(projection_binding.get("sha256") or ""),
            "--skills-root",
            str(trusted_root),
        ],
        import_roots,
    )
    completed = run_bounded_owner_validator(
        argv, cwd=trusted_root, env=environment, timeout=30
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise SystemExit(
            (message or "selected-successor source validator failed")[:2000]
        )
    try:
        receipt = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            "Selected-successor source validator returned malformed JSON."
        ) from exc
    if (
        not isinstance(receipt, dict)
        or set(receipt) != SOURCE_RECEIPT_KEYS
        or receipt.get("schema_version") != 1
        or receipt.get("artifact_kind")
        != "selected_successor_approval_batch_source_validation"
        or receipt.get("validation_status") != "valid"
        or receipt.get("projection_source") != projection_binding
        or receipt.get("operation_count") != 3
        or not isinstance(receipt.get("operation_compilations"), list)
        or len(receipt["operation_compilations"]) != 3
    ):
        raise SystemExit("Selected-successor source validator receipt is not closed.")
    body = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt["receipt_sha256"] != object_sha256(body):
        raise SystemExit("Selected-successor source validator receipt digest differs.")
    return receipt


def _projection_rows(
    root: Path,
    projection_binding: dict[str, str],
    *,
    skills_root: Path | None,
) -> tuple[dict[str, str], str, list[dict[str, Any]]]:
    receipt = _trusted_source_receipt(root, projection_binding, skills_root=skills_root)
    return (
        receipt["projection_source"],
        receipt["compiled_at"],
        receipt["operation_compilations"],
    )


def compile_projected_operation_batch(
    root: Path,
    projection_binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Render a batch after fixed isolated current-owner validation."""

    root = root.resolve()
    binding, compiled_at, rows = _projection_rows(
        root, projection_binding, skills_root=skills_root
    )
    body = {
        "schema_version": 2,
        "artifact_kind": "authority_operation_batch",
        "compiled_at": compiled_at,
        "projection_source": {
            "kind": SOURCE_KIND,
            "binding": binding,
        },
        "operation_compilations": rows,
        "operation_count": len(rows),
        "field_provenance": copy.deepcopy(PROJECTED_BATCH_PROVENANCE),
    }
    batch = {**body, "batch_fingerprint": object_sha256(body)}
    if len(canonical_bytes(batch)) > MAX_OPERATION_BATCH_BYTES:
        raise SystemExit(
            f"operation batch exceeds the {MAX_OPERATION_BATCH_BYTES}-byte limit."
        )
    return batch


def validate_projected_operation_batch(
    root: Path,
    value: Any,
    *,
    skills_root: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Revalidate the owner source and re-render exact schema-v2 bytes."""

    if not isinstance(value, dict) or set(value) != PROJECTED_BATCH_KEYS:
        raise SystemExit("Projected operation batch is not a closed typed object.")
    source = value.get("projection_source")
    if (
        value.get("schema_version") != 2
        or value.get("artifact_kind") != "authority_operation_batch"
        or not isinstance(source, dict)
        or set(source) != SOURCE_KEYS
        or source.get("kind") != SOURCE_KIND
    ):
        raise SystemExit("Unsupported projected operation batch contract.")
    expected = compile_projected_operation_batch(
        root, source["binding"], skills_root=skills_root
    )
    if value != expected:
        raise SystemExit("Projected operation batch differs from its owner projection.")
    from .operation_publication import load_published_compilation

    compilations = [
        load_published_compilation(root, row["compilation"])[1]
        for row in expected["operation_compilations"]
    ]
    return expected, compilations


def publish_projected_operation_batch(
    root: Path,
    projection_binding: dict[str, str],
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Validate current owner state and publish or revalidate its batch."""

    root = root.resolve()
    batch = compile_projected_operation_batch(
        root, projection_binding, skills_root=skills_root
    )
    fingerprint = batch["batch_fingerprint"]
    target = root / OPERATION_BATCH_ROOT / f"{fingerprint}.json"
    if target.exists():
        from .stable_store import read_regular

        payload = read_regular(
            target,
            label="projected operation batch",
            max_bytes=MAX_OPERATION_BATCH_BYTES,
        )
        assert payload is not None
        try:
            current_value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SystemExit("Projected operation batch is unreadable.") from exc
        current, _compilations = validate_projected_operation_batch(
            root,
            current_value,
            skills_root=skills_root,
        )
        if current != batch:
            raise SystemExit("Projected operation batch replay differs.")
        from .canonical import sha256_file

        digest = sha256_file(target)
        replay = True
    else:
        digest = write_immutable_json(
            target, batch, "projected authority operation batch"
        )
        replay = False
    return {
        "status": "published",
        "operation_batch": {
            "ref": target.relative_to(root).as_posix(),
            "sha256": digest,
        },
        "projection_source": batch["projection_source"],
        "batch_fingerprint": fingerprint,
        "operation_count": batch["operation_count"],
        "idempotent_replay": replay,
        "authority_effects_applied": False,
        "model_authored_mechanical_bytes": 0,
    }


__all__ = (
    "PROJECTED_BATCH_KEYS",
    "PROJECTED_BATCH_PROVENANCE",
    "SOURCE_KIND",
    "compile_projected_operation_batch",
    "publish_projected_operation_batch",
    "validate_projected_operation_batch",
)
