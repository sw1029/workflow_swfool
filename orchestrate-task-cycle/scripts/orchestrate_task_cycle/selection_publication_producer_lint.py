"""Static contract lint for selection-publication mutation primitives."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any


MAX_LINT_FILES = 768
MAX_LINT_BYTES = 8 * 1024 * 1024
MAX_LINT_DEPTH = 8
ALLOWED_IMPORTERS = {
    "selection_publication_gc_fs.replace_relative": {
        "selection_publication_migration.py",
        "selection_publication_reference_barrier.py",
    },
    "selection_publication_gc_fs.write_once_relative": {
        "selection_publication_gc_apply.py",
        "selection_publication_gc_restore.py",
        "selection_publication_gc_scan.py",
        "selection_publication_migration_journal.py",
    },
    "selection_publication_gc_fs.write_payload": {
        "selection_publication_gc_restore.py",
    },
    "selection_publication_gc_write.replace_relative": {
        "selection_publication_gc_fs.py",
    },
    "selection_publication_gc_write.write_once_relative": {
        "selection_publication_gc_fs.py",
    },
    "selection_publication_gc_write.write_payload": {
        "selection_publication_gc_fs.py",
    },
    "selection_publication_payload.persist_blob": {
        "selection_publication_intent_service.py",
    },
    "selection_publication_producer_capability."
    "_SELECTION_PUBLICATION_GC_EXCLUSIVE_CAPABILITY": {
        "selection_publication_gc_apply.py",
        "selection_publication_gc_restore.py",
        "selection_publication_gc_write.py",
        "selection_publication_reference_barrier.py",
    },
    "selection_publication_producer_capability."
    "_SELECTION_PUBLICATION_PRODUCER_CAPABILITY": {
        "selected_successor.py",
        "selected_successor_authority_artifacts.py",
        "selected_successor_authority_context_compiler.py",
        "selected_successor_execution_lease.py",
        "selected_successor_index.py",
        "selection_decision_receipt_cli.py",
        "selection_publication.py",
        "selection_publication_gc_scan.py",
        "selection_publication_intent_index.py",
        "selection_publication_intent_service.py",
        "selection_publication_migration.py",
        "selection_publication_migration_journal.py",
        "selection_publication_reference_barrier.py",
        "selection_publication_state.py",
    },
    "selection_publication_producer_capability."
    "_active_reference_barrier_mode": {
        "selection_publication_gc_write.py",
    },
    "selection_publication_producer_capability._reference_barrier_proof": {
        "selection_publication_reference_barrier.py",
    },
    "selection_publication_producer_capability."
    "_require_selection_publication_gc_exclusive": {
        "selection_publication_gc_write.py",
    },
    "selection_publication_producer_capability."
    "_require_selection_publication_producer": {
        "selection_publication_gc_write.py",
        "selection_publication_reference_barrier.py",
        "selection_publication_store.py",
    },
    "selection_publication_producer_capability."
    "_require_selection_publication_lock": {
        "selection_publication_store.py",
    },
    "selection_publication_store._atomic_write": {
        "selection_publication.py",
        "selection_publication_state.py",
    },
    "selection_publication_store._blob_path": {
        "selection_publication_payload.py",
    },
    "selection_publication_store._lock": {
        "selection_publication.py",
        "selection_publication_gc_scan.py",
        "selection_publication_intent_service.py",
        "selection_publication_migration.py",
    },
    "selection_publication_store._publication_lock": {
        "selection_publication_gc_apply.py",
        "selection_publication_gc_restore.py",
        "selection_publication_reference_barrier.py",
    },
    "selection_publication_store._write_once": {
        "selection_publication.py",
        "selection_publication_intent_index.py",
        "selection_publication_intent_service.py",
        "selection_publication_migration.py",
    },
    "selection_publication_store._write_once_with_status": {
        "selected_successor.py",
        "selected_successor_authority_artifacts.py",
        "selected_successor_authority_context_compiler.py",
        "selected_successor_execution_lease.py",
        "selected_successor_index.py",
        "selection_decision_receipt_cli.py",
        "selection_publication_payload.py",
    },
    "selection_publication_store._atomic_write_unlocked": set(),
    "selection_publication_store_immutable._write_once_unlocked_with_status": {
        "selection_publication_store.py",
    },
    "selection_publication_gc_write._write_payload_unlocked": set(),
    "selection_publication_gc_write._link_immutable": set(),
    "selection_publication_reference_barrier.reference_gc_barrier": {
        "selection_publication_gc_apply.py",
        "selection_publication_gc_restore.py",
    },
    "selection_publication_reference_barrier."
    "reference_producer_barrier": {
        "selection_publication_gc_write.py",
    },
    "selection_publication_reference_barrier."
    "registered_producer_barrier": {
        "selected_successor_execution_lease.py",
        "selection_decision_receipt_cli.py",
        "selection_publication_store.py",
    },
}
PROTECTED_IMPORTS: dict[str, set[str]] = {}
for _qualified_symbol in ALLOWED_IMPORTERS:
    _family, _symbol = _qualified_symbol.split(".", 1)
    PROTECTED_IMPORTS.setdefault(_family, set()).add(_symbol)


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _source_family(module: str | None) -> str | None:
    if not module:
        return None
    leaf = module.rsplit(".", 1)[-1]
    return leaf if leaf in PROTECTED_IMPORTS else None


def _allowed(source_file: str, family: str, symbol: str) -> bool:
    return source_file in ALLOWED_IMPORTERS.get(
        f"{family}.{symbol}", set()
    )


def _violation(
    source_file: str, line: int, symbol: str
) -> dict[str, Any]:
    return {"source_file": source_file, "line": line, "symbol": symbol}


def _violations(
    source_file: str, tree: ast.AST
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    module_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            family = _source_family(node.module)
            if family is not None:
                for alias in node.names:
                    if alias.name == "*":
                        violations.append(
                            _violation(
                                source_file, node.lineno, f"{family}.*"
                            )
                        )
                    elif (
                        alias.name in PROTECTED_IMPORTS[family]
                        and not _allowed(source_file, family, alias.name)
                    ):
                        violations.append(
                            _violation(
                                source_file,
                                node.lineno,
                                f"{family}.{alias.name}",
                            )
                        )
            else:
                for alias in node.names:
                    imported_family = _source_family(alias.name)
                    if imported_family is not None:
                        module_aliases[
                            alias.asname or imported_family
                        ] = imported_family
        elif isinstance(node, ast.Import):
            for alias in node.names:
                family = _source_family(alias.name)
                if family is not None:
                    module_aliases[alias.asname or family] = family
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and (family := module_aliases.get(node.value.id))
            and node.attr in PROTECTED_IMPORTS[family]
            and not _allowed(source_file, family, node.attr)
        ):
            violations.append(
                _violation(
                    source_file, node.lineno, f"{family}.{node.attr}"
                )
            )
    return violations


def lint_registered_producers(
    source_root: Path, registered_source_files: set[str]
) -> dict[str, Any]:
    """Reject a package module that reaches mutation primitives off-manifest."""

    allowed_sources = {
        source
        for sources in ALLOWED_IMPORTERS.values()
        for source in sources
    }
    missing_registrations = sorted(
        allowed_sources - registered_source_files
    )
    if missing_registrations:
        raise ValueError(
            "selection-publication producer manifest omits an allowed "
            f"importer: {missing_registrations[0]}"
        )
    paths = sorted(source_root.rglob("*.py"))
    if len(paths) > MAX_LINT_FILES:
        raise ValueError("selection-publication producer lint exceeds file bound")
    scanned_bytes = 0
    source_tree = hashlib.sha256()
    violations: list[dict[str, Any]] = []
    for path in paths:
        relative = path.relative_to(source_root)
        source_file = relative.as_posix()
        if len(relative.parts) > MAX_LINT_DEPTH:
            raise ValueError(
                "selection-publication producer lint exceeds depth bound"
            )
        current = source_root
        for part in relative.parts[:-1]:
            current /= part
            if current.is_symlink():
                raise ValueError(
                    "selection-publication producer lint ancestor is unsafe"
                )
        try:
            payload = path.read_bytes()
            observed = path.lstat()
        except OSError as exc:
            raise ValueError(
                "selection-publication producer lint source is unavailable"
            ) from exc
        scanned_bytes += len(payload)
        source_tree.update(source_file.encode("utf-8"))
        source_tree.update(b"\0")
        source_tree.update(hashlib.sha256(payload).digest())
        if (
            path.is_symlink()
            or observed.st_size != len(payload)
            or scanned_bytes > MAX_LINT_BYTES
        ):
            raise ValueError(
                "selection-publication producer lint source is unsafe or too large"
            )
        try:
            tree = ast.parse(payload, filename=str(path))
        except (SyntaxError, ValueError) as exc:
            raise ValueError(
                "selection-publication producer lint source is invalid"
            ) from exc
        violations.extend(_violations(source_file, tree))
    body = {
        "schema_version": 2,
        "policy": "protected_mutation_imports_require_exact_symbol_allowlist",
        "allowed_importers": {
            symbol: sorted(sources)
            for symbol, sources in sorted(ALLOWED_IMPORTERS.items())
        },
        "protected_symbols": sorted(ALLOWED_IMPORTERS),
        "registered_source_files": sorted(registered_source_files),
        "scanned_file_count": len(paths),
        "scanned_bytes": scanned_bytes,
        "source_tree_sha256": source_tree.hexdigest(),
        "violations": violations,
    }
    result = {
        **body,
        "lint_sha256": hashlib.sha256(_canonical_json(body)).hexdigest(),
    }
    if violations:
        first = violations[0]
        raise ValueError(
            "selection-publication producer contract lint rejected "
            f"{first['source_file']}:{first['line']} {first['symbol']}"
        )
    return result


__all__ = ("lint_registered_producers",)
