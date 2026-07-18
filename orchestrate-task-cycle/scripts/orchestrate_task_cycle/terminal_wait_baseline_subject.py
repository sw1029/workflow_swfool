"""Non-circular exact-subject materialization for terminal-wait baselines."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .terminal_wait_baseline_contract import (
    authority_subject_revision,
    normalize_authority_subject,
    validate_authority_subject_sources,
)
from .terminal_wait_baseline_store import (
    artifact_ref,
    display_bytes,
    mutation_lock,
    sha256_bytes,
    write_once,
)


def _subject_projection(subject: dict[str, Any]) -> dict[str, Any]:
    body = display_bytes(subject)
    digest = sha256_bytes(body)
    binding = {
        "ref": artifact_ref("subjects", digest),
        "sha256": digest,
    }
    return {
        "binding": binding,
        "body": body,
        "subject": {
            "kind": "terminal_wait_baseline_binding",
            "ref": binding["ref"],
            "digest": digest,
            "revision": authority_subject_revision(subject),
        },
    }


def materialize_terminal_wait_authority_subject(
    root: Path, raw_subject: dict[str, Any], *, dry_run: bool = False
) -> dict[str, Any]:
    """Materialize the exact regular file used by authority preflight."""

    root = root.expanduser().resolve(strict=True)
    subject = normalize_authority_subject(raw_subject)
    validate_authority_subject_sources(root, subject)
    predicted = _subject_projection(subject)
    if dry_run:
        return {
            "status": "dry_run",
            "mutation_performed": False,
            "authority_subject_binding": predicted["binding"],
            "authority_subject": predicted["subject"],
            "prepare_only": True,
            "current_pointer_exposed": False,
        }
    with mutation_lock(root):
        validate_authority_subject_sources(root, subject)
        existed = (root / predicted["binding"]["ref"]).exists()
        binding = write_once(
            root,
            "subjects",
            predicted["binding"]["sha256"],
            predicted["body"],
        )
        if binding != predicted["binding"]:
            raise ValueError("terminal-wait authority subject binding drifted")
        validate_authority_subject_sources(root, subject)
        return {
            "status": "already_materialized" if existed else "materialized",
            "mutation_performed": not existed,
            "authority_subject_binding": binding,
            "authority_subject": predicted["subject"],
            "prepare_only": True,
            "current_pointer_exposed": False,
        }


__all__ = ("materialize_terminal_wait_authority_subject",)
