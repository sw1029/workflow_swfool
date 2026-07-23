"""Fixed operation-to-owner-validator registry."""

from __future__ import annotations

from dataclasses import dataclass


OperationIdentity = tuple[str, str, str, str]


@dataclass(frozen=True)
class OwnerValidatorSpec:
    identity: OperationIdentity
    owner_skill: str
    module: str
    argv_prefix: tuple[str, ...]
    import_skills: tuple[str, ...]


TASK_INDEX_IDENTITY: OperationIdentity = (
    "manage-task-state-index",
    "2.0.0",
    "mutate_task_state_index",
    "1",
)
PUBLISH_SELECTED_SUCCESSOR_IDENTITY: OperationIdentity = (
    "orchestrate-task-cycle",
    "2.0.0",
    "publish_selected_successor_topology",
    "1",
)
SETTLE_SELECTED_SUCCESSOR_IDENTITY: OperationIdentity = (
    "orchestrate-task-cycle",
    "2.0.0",
    "settle_selected_successor_task_state",
    "1",
)
APPLY_SELECTION_GC_IDENTITY: OperationIdentity = (
    "orchestrate-task-cycle",
    "2.0.0",
    "apply_selection_publication_retention",
    "1",
)
RESTORE_SELECTION_GC_IDENTITY: OperationIdentity = (
    "orchestrate-task-cycle",
    "2.0.0",
    "restore_selection_publication_retention",
    "1",
)


def _selected_successor(
    identity: OperationIdentity,
) -> OwnerValidatorSpec:
    return OwnerValidatorSpec(
        identity=identity,
        owner_skill="orchestrate-task-cycle",
        module="orchestrate_task_cycle",
        argv_prefix=(
            "selected-successor",
            "validate-owner-result",
            "--operation",
            identity[2],
        ),
        import_skills=(
            "orchestrate-task-cycle",
            "manage-task-state-index",
            "record-agent-work-log",
        ),
    )


def _selection_gc(identity: OperationIdentity) -> OwnerValidatorSpec:
    return OwnerValidatorSpec(
        identity=identity,
        owner_skill="orchestrate-task-cycle",
        module="orchestrate_task_cycle",
        argv_prefix=(
            "selection-publication",
            "gc-validate-owner-result",
            "--operation",
            identity[2],
        ),
        import_skills=(
            "orchestrate-task-cycle",
            "manage-agent-authority",
        ),
    )


OWNER_VALIDATORS = {
    TASK_INDEX_IDENTITY: OwnerValidatorSpec(
        identity=TASK_INDEX_IDENTITY,
        owner_skill="manage-task-state-index",
        module="manage_task_state_index",
        argv_prefix=("index", "validate-owner-result"),
        import_skills=("manage-task-state-index", "record-agent-work-log"),
    ),
    PUBLISH_SELECTED_SUCCESSOR_IDENTITY: _selected_successor(
        PUBLISH_SELECTED_SUCCESSOR_IDENTITY
    ),
    SETTLE_SELECTED_SUCCESSOR_IDENTITY: _selected_successor(
        SETTLE_SELECTED_SUCCESSOR_IDENTITY
    ),
    APPLY_SELECTION_GC_IDENTITY: _selection_gc(APPLY_SELECTION_GC_IDENTITY),
    RESTORE_SELECTION_GC_IDENTITY: _selection_gc(
        RESTORE_SELECTION_GC_IDENTITY
    ),
}


__all__ = (
    "OWNER_VALIDATORS",
    "OperationIdentity",
    "OwnerValidatorSpec",
)
