from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .common import canonical_bytes
from .journal import atomic_write, check_revision, load, locked, workflow_paths
from .journal_contract import validate_journal
from .terminal_validation import validate_terminal_operations
from .phase_validation import (
    project_nonterminal_status,
    validate_nonterminal_operations,
)


Mutator = Callable[[dict[str, Any]], dict[str, Any]]


def mutate_workflow(
    root: Path, workflow_id: str, expected_revision: int, mutator: Mutator,
) -> dict[str, Any]:
    journal_path, lock_path = workflow_paths(root, workflow_id)
    with locked(root, lock_path):
        _, _, journal = load(root, workflow_id)
        check_revision(journal, expected_revision)
        validate_terminal_operations(root, journal)
        validate_nonterminal_operations(root, journal)
        before = canonical_bytes(journal)
        payload = mutator(journal)
        validate_journal(journal, workflow_id)
        changed = canonical_bytes(journal) != before
        if changed:
            atomic_write(root, journal_path, journal)
    result = project_nonterminal_status(root, journal)
    result.update(ok=True, journal_ref=str(journal_path.relative_to(root)),
                  replayed=not changed)
    result.update(payload)
    return result
