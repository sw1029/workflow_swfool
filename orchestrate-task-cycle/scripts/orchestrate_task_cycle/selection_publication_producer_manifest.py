"""Closed, code-hashed manifest of built-in selection reference producers."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import stat
from typing import Any

from .selection_publication_producer_lint import lint_registered_producers


def _spec(
    producer_id: str,
    source_file: str,
    entrypoints: tuple[str, ...],
    role: str = "reference_writer",
) -> dict[str, Any]:
    module = source_file.removesuffix(".py")
    return {
        "producer_id": producer_id,
        "module": f"orchestrate_task_cycle.{module}",
        "entrypoints": sorted(set(entrypoints)),
        "role": role,
        "source_file": source_file,
    }


PRODUCER_SPECS = (
    _spec(
        "selection-publication-core",
        "selection_publication.py",
        ("prepare_publication_intent", "publish_prepared"),
    ),
    _spec(
        "selection-decision-receipt",
        "selection_decision_receipt_cli.py",
        ("main",),
    ),
    _spec(
        "selection-publication-intent",
        "selection_publication_intent_service.py",
        ("prepare_publication_intent",),
    ),
    _spec(
        "selection-publication-intent-index",
        "selection_publication_intent_index.py",
        ("write_prepare_index", "write_commit_index"),
    ),
    _spec(
        "selection-publication-state",
        "selection_publication_state.py",
        ("write_compiled_state",),
    ),
    _spec(
        "selection-publication-payload",
        "selection_publication_payload.py",
        ("persist_blob",),
    ),
    _spec(
        "selection-publication-migration",
        "selection_publication_migration.py",
        ("migrate_publication_state",),
    ),
    _spec(
        "selection-publication-gc-plan",
        "selection_publication_gc_scan.py",
        ("plan_gc",),
    ),
    _spec(
        "selection-publication-gc-apply",
        "selection_publication_gc_apply.py",
        ("apply_gc",),
    ),
    _spec(
        "selection-publication-gc-restore",
        "selection_publication_gc_restore.py",
        ("restore_gc",),
    ),
    _spec(
        "selected-successor-bundle",
        "selected_successor.py",
        ("prepare_selected_successor_bundle",),
    ),
    _spec(
        "selected-successor-index",
        "selected_successor_index.py",
        ("write_prepare_index",),
    ),
    _spec(
        "selected-successor-authority-artifacts",
        "selected_successor_authority_artifacts.py",
        ("publish_projection", "publish_packet", "publish_locator", "publish_index"),
    ),
    _spec(
        "selected-successor-authority-context",
        "selected_successor_authority_context_compiler.py",
        ("prepare_selected_successor_authority_contexts",),
    ),
    _spec(
        "selected-successor-execution",
        "selected_successor_execution.py",
        ("execute_selected_successor_bundle",),
    ),
    _spec(
        "selected-successor-execution-lease",
        "selected_successor_execution_lease.py",
        ("authority_gate", "publish_execution_lease"),
    ),
    _spec(
        "selection-publication-store-control",
        "selection_publication_store.py",
        (
            "_atomic_write",
            "_write_once",
            "_write_once_with_status",
            "_lock",
            "_publication_lock",
        ),
        "control",
    ),
    _spec(
        "selection-publication-store-immutable-control",
        "selection_publication_store_immutable.py",
        ("_write_once_unlocked_with_status",),
        "control",
    ),
    _spec(
        "selection-publication-gc-fs-control",
        "selection_publication_gc_fs.py",
        ("write_once_relative", "replace_relative", "write_payload"),
        "control",
    ),
    _spec(
        "selection-publication-gc-write-control",
        "selection_publication_gc_write.py",
        ("write_once_relative", "replace_relative", "write_payload"),
        "control",
    ),
    _spec(
        "selection-publication-barrier-control",
        "selection_publication_reference_barrier.py",
        (
            "reference_producer_barrier",
            "registered_producer_barrier",
            "reference_gc_barrier",
        ),
        "control",
    ),
    _spec(
        "selection-publication-capability-control",
        "selection_publication_producer_capability.py",
        (
            "_active_reference_barrier_mode",
            "_reference_barrier_proof",
            "_require_selection_publication_gc_exclusive",
            "_require_selection_publication_lock",
            "_require_selection_publication_producer",
        ),
        "control",
    ),
    _spec(
        "selection-publication-manifest-control",
        "selection_publication_producer_manifest.py",
        ("registered_producer_inventory", "valid_producer_inventory"),
        "control",
    ),
    _spec(
        "selection-publication-lint-control",
        "selection_publication_producer_lint.py",
        ("lint_registered_producers",),
        "control",
    ),
    _spec(
        "selection-publication-migration-journal",
        "selection_publication_migration_journal.py",
        ("archive_completed_generation",),
        "control",
    ),
)
PRODUCER_ROW_KEYS = {
    "producer_id",
    "module",
    "entrypoints",
    "role",
    "source_file",
    "source_sha256",
}
PRODUCER_INVENTORY_KEYS = {
    "schema_version",
    "scope",
    "producers",
    "contract_lint",
    "inventory_sha256",
}


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def registered_producer_inventory() -> dict[str, Any]:
    source_root = Path(__file__).resolve().parent
    rows: list[dict[str, Any]] = []
    for spec in PRODUCER_SPECS:
        path = source_root / str(spec["source_file"])
        try:
            observed = path.lstat()
            payload = path.read_bytes()
        except OSError as exc:
            raise ValueError(
                "selection-publication producer inventory is unavailable"
            ) from exc
        if (
            path.is_symlink()
            or not stat.S_ISREG(observed.st_mode)
            or observed.st_size != len(payload)
            or len(payload) > 512 * 1024
        ):
            raise ValueError(
                "selection-publication producer inventory source is unsafe"
            )
        try:
            tree = ast.parse(payload, filename=str(path))
        except (SyntaxError, ValueError) as exc:
            raise ValueError(
                "selection-publication producer inventory source is invalid"
            ) from exc
        definitions = {
            node.name
            for node in tree.body
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
        }
        missing = sorted(set(spec["entrypoints"]) - definitions)
        if missing:
            raise ValueError(
                "selection-publication producer manifest entrypoint is absent: "
                + ", ".join(missing)
            )
        rows.append(
            {**spec, "source_sha256": hashlib.sha256(payload).hexdigest()}
        )
    rows.sort(key=lambda row: row["producer_id"])
    lint = lint_registered_producers(
        source_root, {str(spec["source_file"]) for spec in PRODUCER_SPECS}
    )
    body = {
        "schema_version": 2,
        "scope": "closed_registered_selection_publication_modules",
        "producers": rows,
        "contract_lint": lint,
    }
    return {
        **body,
        "inventory_sha256": hashlib.sha256(_canonical_json(body)).hexdigest(),
    }


def valid_producer_inventory(value: Any) -> bool:
    if (
        not isinstance(value, dict)
        or set(value) != PRODUCER_INVENTORY_KEYS
        or value.get("schema_version") != 2
        or value.get("scope")
        != "closed_registered_selection_publication_modules"
        or not isinstance(value.get("producers"), list)
        or not value["producers"]
        or not isinstance(value.get("contract_lint"), dict)
    ):
        return False
    rows = value["producers"]
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != PRODUCER_ROW_KEYS
            or row.get("role") not in {"reference_writer", "control"}
            or not isinstance(row.get("entrypoints"), list)
            or not row["entrypoints"]
            or row["entrypoints"] != sorted(set(row["entrypoints"]))
            or any(not isinstance(item, str) or not item for item in row["entrypoints"])
            or any(
                not isinstance(row.get(key), str) or not row[key]
                for key in (
                    "producer_id",
                    "module",
                    "source_file",
                    "source_sha256",
                )
            )
            or len(row["source_sha256"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in row["source_sha256"]
            )
        ):
            return False
    if rows != sorted(rows, key=lambda row: row["producer_id"]):
        return False
    if len({row["producer_id"] for row in rows}) != len(rows):
        return False
    lint = value["contract_lint"]
    if (
        lint.get("schema_version") != 2
        or lint.get("policy")
        != "protected_mutation_imports_require_exact_symbol_allowlist"
        or lint.get("violations") != []
        or not isinstance(lint.get("lint_sha256"), str)
    ):
        return False
    lint_body = {key: child for key, child in lint.items() if key != "lint_sha256"}
    if lint["lint_sha256"] != hashlib.sha256(
        _canonical_json(lint_body)
    ).hexdigest():
        return False
    body = {
        key: value[key]
        for key in PRODUCER_INVENTORY_KEYS
        if key != "inventory_sha256"
    }
    return value["inventory_sha256"] == hashlib.sha256(
        _canonical_json(body)
    ).hexdigest()


__all__ = (
    "PRODUCER_SPECS",
    "registered_producer_inventory",
    "valid_producer_inventory",
)
