from __future__ import annotations

from pathlib import Path
from typing import Any

from .canonical import canonical_bytes
from .canonical import resolve_workspace_path
from .canonical import write_json_atomic
from .projection_contracts import AUTHORIZATION_ROOT
from .projection_contracts import CHANGE_KEYS
from .projection_contracts import INTENT_DIRECTORIES
from .projection_contracts import MAX_INTENT_BYTES
from .projection_contracts import STATE_ROOT
from .projection_contracts import closed
from .projection_io import safe_json
from .projection_receipts import validate_release_receipt
from .projection_receipts import validate_use_receipt
from .projection_reservations import validate_reservation
from .projection_transitions import validate_transition
from .projection_reconciliation import validate_reconciliation_receipt


Intent = tuple[Path, dict[str, Any], list[dict[str, Any]]]
StateGraph = dict[str, dict[bytes, bytes]]


def _validate_intent(
    root: Path,
    directory: str,
    artifact: dict[str, Any],
    path: Path,
    *,
    skills_root: Path | None,
    allow_settled_registered_legacy: bool,
) -> list[dict[str, Any]]:
    expected_kind = INTENT_DIRECTORIES[directory]
    if artifact.get("artifact_kind") != expected_kind:
        raise SystemExit(
            f"Unknown or misplaced authority recovery intent in {directory}: {path.name}"
        )
    if directory == "reservations":
        return validate_reservation(root, artifact, path)[2]
    if directory == "use_receipts":
        return validate_use_receipt(
            root,
            artifact,
            path,
            skills_root=skills_root,
            allow_settled_registered_legacy=allow_settled_registered_legacy,
        )
    if directory == "release_receipts":
        return validate_release_receipt(
            root,
            artifact,
            path,
            skills_root=skills_root,
            allow_settled_registered_legacy=allow_settled_registered_legacy,
        )
    if directory == "reconciliation_receipts":
        return validate_reconciliation_receipt(root, artifact, path)
    return validate_transition(root, artifact, path)


def projection_change(
    root: Path,
    path: Path,
    before: dict[str, Any] | None,
    after: dict[str, Any],
) -> dict[str, Any]:
    root = root.resolve()
    boundary = (root / STATE_ROOT).resolve()
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(boundary)
    except ValueError as exc:
        raise SystemExit(
            "Authority projection change escapes the state boundary."
        ) from exc
    return {
        "ref": resolved.relative_to(root).as_posix(),
        "before": before,
        "after": after,
    }


def apply_projection_changes(root: Path, changes: Any) -> None:
    if not isinstance(changes, list) or not changes:
        raise SystemExit("Recoverable authority intent requires projection changes.")
    root = root.resolve()
    boundary = (root / STATE_ROOT).resolve()
    for index, raw in enumerate(changes):
        change = closed(raw, CHANGE_KEYS, f"projection change {index}")
        if change["before"] is not None and not isinstance(change["before"], dict):
            raise SystemExit(f"Projection change {index} before state is invalid.")
        if not isinstance(change["after"], dict):
            raise SystemExit(f"Projection change {index} after state is invalid.")
        path = resolve_workspace_path(
            root,
            change["ref"],
            f"projection change {index}",
            must_exist=False,
        )
        try:
            path.relative_to(boundary)
        except ValueError as exc:
            raise SystemExit("Projection recovery escapes the state boundary.") from exc
        current = (
            safe_json(root, path, "authority projection")[0] if path.exists() else None
        )
        if current == change["after"]:
            continue
        if current != change["before"]:
            raise SystemExit(
                f"Projection recovery conflict at {change['ref']}; quarantine manual recovery."
            )
        write_json_atomic(path, change["after"])


def _intent_directory(root: Path, directory: str) -> Path | None:
    relative = AUTHORIZATION_ROOT / directory
    path = root.resolve() / relative
    if not path.exists() and not path.is_symlink():
        return None
    resolved = resolve_workspace_path(
        root,
        relative.as_posix(),
        f"authority intent directory {directory}",
        regular_file=False,
    )
    if not resolved.is_dir():
        raise SystemExit(f"Authority intent directory {directory} is not a directory.")
    return resolved


def _load_intents(
    root: Path,
    *,
    skills_root: Path | None,
    allow_settled_registered_legacy: bool = False,
) -> list[Intent]:
    root = root.resolve()
    intents: list[Intent] = []
    for directory in INTENT_DIRECTORIES:
        path = _intent_directory(root, directory)
        if path is None:
            continue
        for artifact_path in sorted(path.iterdir()):
            if artifact_path.suffix != ".json":
                continue
            artifact, _ = safe_json(
                root, artifact_path, f"authority recovery intent {artifact_path.name}"
            )
            changes = _validate_intent(
                root,
                directory,
                artifact,
                artifact_path,
                skills_root=skills_root,
                allow_settled_registered_legacy=allow_settled_registered_legacy,
            )
            intents.append((artifact_path, artifact, changes))
    return intents


def _state_graph(intents: list[Intent]) -> StateGraph:
    graph: StateGraph = {}
    incoming: dict[str, dict[bytes, tuple[bytes, Path]]] = {}
    provenance: dict[str, dict[bytes, Path]] = {}
    for path, _, changes in intents:
        for change in changes:
            before = canonical_bytes(change["before"])
            after = canonical_bytes(change["after"])
            edges = graph.setdefault(change["ref"], {})
            sources = provenance.setdefault(change["ref"], {})
            if before in edges:
                conflict = "competing" if edges[before] != after else "duplicate"
                raise SystemExit(
                    f"{conflict.capitalize()} authority recovery intents at {change['ref']}: "
                    f"{sources[before]} and {path}"
                )
            reverse = incoming.setdefault(change["ref"], {})
            if after in reverse and reverse[after][0] != before:
                raise SystemExit(
                    f"Converging authority recovery intents at {change['ref']}: "
                    f"{reverse[after][1]} and {path}"
                )
            edges[before] = after
            sources[before] = path
            reverse[after] = (before, path)
    return graph


def _reachable(edges: dict[bytes, bytes], start: bytes, target: bytes) -> bool:
    seen: set[bytes] = set()
    current = start
    while current not in seen and current in edges:
        seen.add(current)
        current = edges[current]
        if current == target:
            return True
    return False


def _current(root: Path, ref: str) -> Any:
    path = resolve_workspace_path(
        root, ref, "authority recovery projection", must_exist=False
    )
    return (
        safe_json(root, path, "authority recovery projection")[0]
        if path.exists()
        else None
    )


def _changes_settled(
    root: Path,
    changes: list[dict[str, Any]],
    graph: StateGraph,
) -> bool:
    for change in changes:
        current_key = canonical_bytes(_current(root, change["ref"]))
        after_key = canonical_bytes(change["after"])
        if current_key != after_key and not _reachable(
            graph.get(change["ref"], {}), after_key, current_key
        ):
            return False
    return True


def validated_settled_intent(
    root: Path,
    artifact_path: Path,
    *,
    skills_root: Path | None = None,
) -> dict[str, Any]:
    """Return a validated intent after each projection reached it or a descendant."""
    root = root.resolve()
    target = artifact_path.resolve(strict=False)
    for path, artifact in _validated_settled_intents(
        root,
        skills_root=skills_root,
        allow_settled_registered_legacy=True,
    ):
        if path.resolve(strict=False) == target:
            _validate_intent(
                root,
                path.parent.name,
                artifact,
                path,
                skills_root=skills_root,
                allow_settled_registered_legacy=False,
            )
            return artifact
    raise SystemExit(
        "Authority intent replay artifact is not a validated owner intent."
    )


def validated_settled_intents(
    root: Path, *, skills_root: Path | None = None
) -> list[tuple[Path, dict[str, Any]]]:
    """Return all closed intents after proving their projections are settled."""
    return _validated_settled_intents(
        root,
        skills_root=skills_root,
        allow_settled_registered_legacy=False,
    )


def validated_inventory_intents(
    root: Path, *, skills_root: Path | None = None
) -> list[tuple[Path, dict[str, Any]]]:
    """Read exact-settled historical registered schema-v2 receipts for status only."""

    return _validated_settled_intents(
        root,
        skills_root=skills_root,
        allow_settled_registered_legacy=True,
    )


def _validated_settled_intents(
    root: Path,
    *,
    skills_root: Path | None,
    allow_settled_registered_legacy: bool,
) -> list[tuple[Path, dict[str, Any]]]:
    root = root.resolve()
    intents = _load_intents(
        root,
        skills_root=skills_root,
        allow_settled_registered_legacy=allow_settled_registered_legacy,
    )
    graph = _state_graph(intents)
    settled: list[tuple[Path, dict[str, Any]]] = []
    for path, artifact, changes in intents:
        if not _changes_settled(root, changes, graph):
            raise SystemExit(
                "Authority intent replay is not settled at its exact after-state or a proven descendant."
            )
        settled.append((path, artifact))
    return settled


def recover_projection_intents(
    root: Path, *, skills_root: Path | None = None
) -> list[str]:
    """Validate, then finish every immutable authority intent before a new action."""
    root = root.resolve()
    intents = _load_intents(
        root,
        skills_root=skills_root,
        # Historical registered schema-v2 receipts may be observed only when
        # their projections already equal every exact after-state. The receipt
        # validator rejects a before-state here, so recovery can never apply it.
        allow_settled_registered_legacy=True,
    )
    graph = _state_graph(intents)
    pending = list(intents)
    recovered: list[str] = []
    while pending:
        deferred: list[Intent] = []
        progressed = False
        for artifact_path, artifact, changes in pending:
            applicable: list[dict[str, Any]] = []
            blocked = False
            for change in changes:
                current_key = canonical_bytes(_current(root, change["ref"]))
                before_key = canonical_bytes(change["before"])
                after_key = canonical_bytes(change["after"])
                if current_key == before_key:
                    applicable.append(change)
                elif current_key != after_key and not _reachable(
                    graph.get(change["ref"], {}), after_key, current_key
                ):
                    blocked = True
                    break
            if blocked:
                deferred.append((artifact_path, artifact, changes))
                continue
            if applicable:
                apply_projection_changes(root, applicable)
                recovered.append(artifact_path.relative_to(root).as_posix())
            progressed = True
        if not deferred:
            return recovered
        if not progressed:
            refs = sorted(
                {change["ref"] for _, _, changes in deferred for change in changes}
            )
            raise SystemExit(
                "Authority recovery conflict; quarantine manual recovery for "
                + ", ".join(refs)
            )
        pending = deferred
    return recovered


__all__ = [
    "MAX_INTENT_BYTES",
    "apply_projection_changes",
    "projection_change",
    "recover_projection_intents",
    "validated_inventory_intents",
    "validated_settled_intent",
    "validated_settled_intents",
]
