"""Adapter from continuation actions to the existing stage compiler/CAS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..stage.executor_registry import executor_spec
from ..stage.input_compilers import (
    compile_routing,
    publish_owner_result,
    publish_semantic,
)
from ..stage.preparation_store import (
    load_published_preparation,
)
from ..stage.service import submit_stage
from ..stage.specs import TARGET_COMPILE_SPECS
from ..cycle_ledger import read_events
from .actions import validate_action
from .contracts import ContinuationContractError
from .stage_advancement import advance as _advance
from .successor_initialization import ensure_selected_successor_cycle
from .terminal import reject_discarded_terminal_inputs


def _split_result(
    preparation: dict[str, Any], result: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    specification = TARGET_COMPILE_SPECS[str(preparation["target"])]
    owner_fields = set(specification.owner_receipt_fields) | set(
        specification.optional_owner_fields
    )
    semantic_fields = set(specification.semantic_fields) | set(
        specification.optional_semantic_fields
    )
    reasoned_fields = set(specification.reasoned_not_applicable_fields)
    owner = {key: value for key, value in result.items() if key in owner_fields}
    semantic = {key: value for key, value in result.items() if key in semantic_fields}
    reasoned = {key: value for key, value in result.items() if key in reasoned_fields}
    return owner, semantic, reasoned


def _publish_inputs(
    root: Path,
    action: dict[str, Any],
    preparation: dict[str, Any],
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    prep_binding = action["preparation_binding"]
    owner, semantic, reasoned = _split_result(preparation, result)
    source = result.get("source_binding")
    owner_publication = (
        publish_owner_result(
            root,
            prep_binding["ref"],
            prep_binding["sha256"],
            None,
            source_ref=source.get("ref"),
            source_sha256=source.get("sha256"),
        )
        if isinstance(source, dict)
        else publish_owner_result(
            root, prep_binding["ref"], prep_binding["sha256"], owner
        )
    )
    semantic_publication = (
        publish_semantic(
            root,
            prep_binding["ref"],
            prep_binding["sha256"],
            semantic,
            reasoned_not_applicable=reasoned,
        )
        if preparation.get("executor_kind") == "hybrid"
        else None
    )
    registered = executor_spec(str(preparation["target"]))
    routing_publication = None
    if registered.routing_required:
        profile_id = action["routing"].get("profile_id")
        if not profile_id:
            raise ContinuationContractError(
                "routed owner action lacks a controller-selected profile"
            )
        routing_publication = compile_routing(
            root,
            prep_binding["ref"],
            prep_binding["sha256"],
            str(profile_id),
        )
    return owner_publication, semantic_publication, routing_publication


def _binding(publication: dict[str, Any] | None, name: str) -> tuple[str | None, str | None]:
    if publication is None:
        return None, None
    value = publication[f"{name}_binding"]
    return value["ref"], value["sha256"]


def _accept(
    root: Path,
    action: dict[str, Any],
    result: dict[str, Any],
    *,
    goal_id: str | None,
) -> dict[str, Any]:
    validated = validate_action(action)
    prep_binding = validated["preparation_binding"]
    if prep_binding is None:
        raise ContinuationContractError(
            "owner acceptance requires a preparation binding"
        )
    preparation = load_published_preparation(
        root, prep_binding["ref"], prep_binding["sha256"]
    )
    if preparation["target"] != validated["target"]:
        raise ContinuationContractError("action target changed before acceptance")
    reject_discarded_terminal_inputs(
        root, validated["cycle_id"], result
    )
    if validated["target"] == "closeout_commit":
        status = str(
            result.get("commit_status") or result.get("status") or ""
        ).lower()
        if status in {"created", "committed", "success", "passed"}:
            anchor_path = result.get("settlement_anchor_path")
            if not isinstance(anchor_path, str) or not anchor_path:
                raise ContinuationContractError(
                    "session closeout requires an embedded settlement anchor"
                )
            try:
                from repo_change_commit.git_observation import verify_head

                verification = verify_head(
                    root,
                    anchor_path=anchor_path,
                    expected={
                        "commit_role": "closeout",
                        "goal_id": goal_id,
                        "task_id": validated["task_id"],
                        "cycle_id": validated["cycle_id"],
                        "session_id": validated["session_id"],
                    },
                )
            except (OSError, ValueError) as exc:
                raise ContinuationContractError(
                    f"session closeout settlement is invalid: {exc}"
                ) from exc
            if result.get("commit_hash") != verification["commit_oid"]:
                raise ContinuationContractError(
                    "session closeout commit hash differs from verified HEAD"
                )
            supplied = result.get("settlement_verification")
            if supplied is not None and supplied != verification:
                raise ContinuationContractError(
                    "caller settlement verification differs from verified HEAD"
                )
            result = {
                **result,
                "settlement_verification": verification,
            }
    owner, semantic, routing = _publish_inputs(
        root, validated, preparation, result
    )
    semantic_ref, semantic_sha = _binding(semantic, "semantic")
    routing_ref, routing_sha = _binding(routing, "routing")
    output = submit_stage(
        root,
        preparation,
        apply=True,
        owner_result_ref=owner["owner_result_binding"]["ref"],
        owner_result_sha256=owner["owner_result_binding"]["sha256"],
        semantic_ref=semantic_ref,
        semantic_sha256=semantic_sha,
        routing_ref=routing_ref,
        routing_sha256=routing_sha,
    )
    return {
        "status": (
            "accepted"
            if output.get("status") not in {"block", "failed"}
            else "rejected"
        ),
        "stage_result": output,
        "effect_status": (
            "unknown"
            if output.get("stop_reason") == "unknown_effect"
            else "settled"
        ),
    }


def _accept_monitor(
    root: Path, action: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Accept only a monitor result already sealed by the ledger producer."""

    projection = result.get("projection") or result.get(
        "run_terminal_projection"
    )
    projection_binding = result.get("binding") or result.get(
        "run_terminal_projection_binding"
    )
    if isinstance(projection, dict):
        from ..stage.closure import reopen_run_terminal_event
        from ..stage.run_terminal_publication import (
            publish_run_terminal_observation,
        )

        publication = publish_run_terminal_observation(
            root,
            action["cycle_id"],
            projection=projection,
            projection_binding=projection_binding,
        )
        verified = reopen_run_terminal_event(
            root, action["cycle_id"], publication["event"]
        )
        return {
            "status": "accepted",
            "effect_status": "settled",
            "stage_result": publication,
            "run_terminal_status": verified["status"],
            "run_terminal_run_id": verified["run_id"],
        }
    publication = result.get("ledger_append")
    event = publication.get("event") if isinstance(publication, dict) else None
    if not isinstance(event, dict) or event.get("step") != "run":
        raise ContinuationContractError(
            "monitor acceptance requires a sealed run ledger observation"
        )
    event_id = event.get("event_id")
    current = [
        row
        for row in read_events(root, action["cycle_id"])
        if row.get("event_id") == event_id
    ]
    if len(current) != 1 or current[0] != event:
        raise ContinuationContractError(
            "monitor ledger observation is missing or changed"
        )
    result_run_id = result.get("run_id")
    event_run_id = event.get("run_id")
    if result_run_id and event_run_id and result_run_id != event_run_id:
        raise ContinuationContractError("monitor run_id changed at acceptance")
    accepted = {
        "status": "accepted",
        "effect_status": "settled",
        "stage_result": {"event": event},
    }
    if event.get("observation_kind") == "run_terminal":
        from ..stage.closure import reopen_run_terminal_event

        verified = reopen_run_terminal_event(
            root, action["cycle_id"], event
        )
        accepted["run_terminal_status"] = verified["status"]
        accepted["run_terminal_run_id"] = verified["run_id"]
    return accepted


class StageContinuationAdapter:
    """Use existing compiler-first stage services without model calls."""

    def __init__(
        self,
        root: str | Path,
        *,
        workflow_mode: str = "normal",
        session_id: str | None = None,
        goal_id: str | None = None,
        task_family: str | None = None,
    ) -> None:
        self.root = Path(root).resolve(strict=True)
        self.workflow_mode = workflow_mode
        self.session_id = session_id
        self.goal_id = goal_id
        self.task_family = task_family

    def advance(self, cycle_id: str, *, closure_only: bool) -> dict[str, Any]:
        return _advance(
            self.root, self.workflow_mode, cycle_id, closure_only=closure_only
        )

    def accept(
        self, action: dict[str, Any], result: dict[str, Any]
    ) -> dict[str, Any]:
        validated = validate_action(action)
        if validated["kind"] == "monitor_run":
            return _accept_monitor(self.root, validated, result)
        return _accept(
            self.root,
            validated,
            result,
            goal_id=self.goal_id,
        )

    def classify_effect(
        self,
        state: dict[str, Any],
        preparation: dict[str, Any],
        *,
        at: str,
    ) -> str:
        from .local_run_dispatch import local_long_run_authorized

        return (
            "local_long_run"
            if local_long_run_authorized(
                self.root, state, preparation, at=at
            )
            else "unknown"
        )

    def recover(self, action: dict[str, Any]) -> dict[str, Any]:
        validated = validate_action(action)
        from ..stage.executor_registry import owner_recovery_strategy

        strategy = owner_recovery_strategy(
            validated["target"], validated["effect_class"]
        )
        if strategy == "verify_closeout_anchor":
            anchor_path = (
                ".task/authorization/settlements/"
                f"{validated['cycle_id']}.json"
            )
            try:
                from repo_change_commit.git_observation import (
                    recover_verified_closeout,
                )

                result = recover_verified_closeout(
                    self.root,
                    anchor_path=anchor_path,
                    expected={
                        "commit_role": "closeout",
                        "goal_id": self.goal_id,
                        "task_id": validated["task_id"],
                        "cycle_id": validated["cycle_id"],
                        "session_id": validated["session_id"],
                    },
                )
            except (OSError, ValueError):
                return {"status": "unknown_effect"}
            return {"status": "result_found", "result": result}
        if strategy == "safe_reissue":
            return {"status": "not_dispatched"}
        return {"status": "unknown_effect"}

    def selected_successor(self, cycle_id: str) -> dict[str, Any] | None:
        return ensure_selected_successor_cycle(
            self.root,
            cycle_id,
            session_id=self.session_id,
            goal_id=self.goal_id,
            task_family=self.task_family,
        )


__all__ = ("StageContinuationAdapter",)
