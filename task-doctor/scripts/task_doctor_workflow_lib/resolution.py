from __future__ import annotations

from pathlib import Path
from typing import Any

from .authority import (
    validate_completion,
    validate_reservation_binding,
    validate_reservation_evidence,
    verify_operation_plan,
)
from .common import SCHEMA_VERSION, expect_keys, read_json, require, workspace_file
from .journal import dependencies_complete, event, operation
from .mutation import mutate_workflow
from .dependency_cancellation import cancel_index_dependents
from .authority_basis import authority_bundle, verify_operation_source_approval
from .phase_validation import project_nonterminal_status


def _evidence(root: Path, ref: str, digest: str, label: str) -> dict[str, str]:
    workspace_file(root, ref, digest, label)
    return {"ref": ref, "sha256": digest}


def _read_bundle(
    root: Path, ref: str, digest: str, journal: dict[str, Any],
) -> dict[str, Any]:
    path = workspace_file(root, ref, digest, "resolution_bundle")
    body = read_json(path, "invalid_resolution_bundle")
    expect_keys(
        body,
        {"kind", "schema_version", "workflow_id", "plan_sha256",
         "from_classification", "user_interaction", "resolutions"},
        set(), "resolution_bundle", "invalid_resolution_bundle",
    )
    require(body["kind"] == "task_doctor_authority_resolution_bundle",
            "invalid_resolution_bundle", "resolution bundle kind mismatch")
    require(body["schema_version"] == SCHEMA_VERSION, "invalid_resolution_bundle",
            "resolution bundle schema version mismatch")
    require(body["workflow_id"] == journal["workflow_id"],
            "invalid_resolution_bundle", "resolution bundle workflow mismatch")
    require(body["plan_sha256"] == journal["plan_sha256"],
            "invalid_resolution_bundle", "resolution bundle plan mismatch")
    return body


def _validate_replay(
    root: Path, journal: dict[str, Any], body: dict[str, Any],
) -> None:
    resolutions = body["resolutions"]
    require(isinstance(resolutions, list) and bool(resolutions),
            "invalid_resolution_bundle", "resolutions must be a non-empty list")
    for item in resolutions:
        expect_keys(item, {"operation_id", "classification", "evidence_ref",
                           "evidence_sha256"}, set(), "resolution",
                    "invalid_resolution_bundle")
        plan_item, state = operation(journal, item["operation_id"])
        binding = {"ref": item["evidence_ref"], "sha256": item["evidence_sha256"]}
        if item["classification"] == "already_settled":
            validate_completion(root, journal, item["operation_id"],
                                binding["ref"], binding["sha256"])
        elif item["classification"] == "already_covered":
            verify_operation_source_approval(root, plan_item, binding)
        else:
            require(item["classification"] == "ready_to_resume",
                    "invalid_resolution_bundle", "replayed resolution class is invalid")
            _validate_replayed_reservation(root, journal, plan_item, state, binding)


def _validate_replayed_reservation(
    root: Path, journal: dict[str, Any], plan_item: dict[str, Any],
    state: dict[str, Any], binding: dict[str, str],
) -> None:
    if state["status"] == "complete":
        result = state.get("result_evidence") or {}
        validate_completion(root, journal, plan_item["operation_id"],
                            result.get("ref", ""), result.get("sha256", ""))
    elif state["status"] in {"pending", "in_progress", "effect_applied"}:
        validate_reservation_evidence(
            root, plan_item, binding,
            dependencies_ready=dependencies_complete(journal, plan_item),
        )
    else:
        validate_reservation_binding(root, plan_item, binding)


def _expected_ids(
    root: Path, journal: dict[str, Any], source: str, resolutions: list[Any], *,
    interaction: bool,
) -> set[str]:
    expected: set[str] = set()
    expected_classifications: dict[str, str] = {}
    source_expected: dict[str, str] | None = None
    if source == "needs_user_approval" and interaction:
        scopes = [
            item for item in journal["events"]
            if item["event"] == "semantic_approval_scope_bound"
        ]
        require(
            len(scopes) == 1,
            "stale_resolution_bundle",
            "workflow has no single durable semantic approval scope",
            retryable=True,
            next_action="prepare_new_plan",
        )
        scope = scopes[0]
        operation_ids = scope["operations"]
        projected = authority_bundle(
            journal, operation_ids, "consolidated_approval_bundle"
        )
        require(
            scope["bundle_id"] == projected["bundle_id"]
            and scope["bundle_fingerprint"] == projected["fingerprint"],
            "invalid_journal",
            "durable semantic approval scope differs from the immutable plan",
        )
        source_expected = {
            operation_id: "already_covered" for operation_id in operation_ids
        }
    elif source == "needs_user_approval":
        projection = project_nonterminal_status(root, journal)
        require(
            projection.get("should_prompt") is False
            and projection.get("authority_resolution_source") == source,
            "stale_resolution_bundle",
            "system authority bundle no longer matches live prompt-free progress",
            retryable=True,
            next_action="reload_status",
        )
        bundle = projection.get("authority_bundle")
        live = projection.get("live_authority_progress")
        bundle_items = bundle.get("items") if isinstance(bundle, dict) else None
        live_items = live.get("items") if isinstance(live, dict) else None
        require(
            isinstance(bundle_items, list) and bool(bundle_items)
            and isinstance(live_items, list),
            "invalid_workflow_projection",
            "prompt-free authority progression lacks its exact system bundle",
        )
        classifications = {
            "source_approval_ready_for_grant": "already_covered",
            "ready_to_reserve": "already_covered",
            "ready_to_resume": "ready_to_resume",
        }
        source_expected = {
            item["operation_id"]: classifications.get(item["resolution"], "")
            for item in live_items
        }
        bundle_ids = [item["operation_id"] for item in bundle_items]
        require(
            bundle_ids == list(source_expected)
            and all(source_expected.values()),
            "invalid_workflow_projection",
            "system authority bundle contains unsupported live progression",
        )
    for item in journal["plan"]["operations"]:
        state = journal["operation_state"][item["operation_id"]]
        if (state["status"] in {"complete", "skipped"}
                or state["resolution"] != source):
            continue
        if source == "needs_user_approval":
            if item["operation_id"] not in source_expected:
                continue
            classification = source_expected[item["operation_id"]]
            if classification == "ready_to_resume":
                require(dependencies_complete(journal, item), "dependency_incomplete",
                        "live reservation cannot advance before dependencies settle")
                lifecycle = verify_operation_plan(
                    root, item, phase="planning", dependencies_ready=True,
                )
                require(lifecycle.get("status") == "ready", "owner_not_dispatchable",
                        "live reservation owner is not ready for dispatch")
            else:
                verify_operation_plan(root, item, phase="structural")
            expected.add(item["operation_id"])
            expected_classifications[item["operation_id"]] = classification
            continue
        if not dependencies_complete(journal, item):
            continue
        lifecycle = verify_operation_plan(
            root, item, phase="planning", dependencies_ready=True,
        )
        status = lifecycle.get("status")
        if status in {"ready", "already_applied", "settled_no_effect"}:
            expected.add(item["operation_id"])
            expected_classifications[item["operation_id"]] = (
                "ready_to_resume" if status == "ready" else "already_settled"
            )
    observed = {item.get("operation_id") for item in resolutions
                if isinstance(item, dict)}
    require(bool(expected) and observed == expected, "incomplete_resolution_bundle",
            "bundle must resolve every currently matching operation exactly once",
            details={"expected": sorted(expected), "observed": sorted(observed)})
    require(len(resolutions) == len(observed), "invalid_resolution_bundle",
            "resolution bundle contains duplicate operation IDs")
    for value in resolutions:
        if isinstance(value, dict) and value.get("operation_id") in expected:
            require(
                value.get("classification")
                == expected_classifications[value["operation_id"]],
                "invalid_resolution_bundle",
                "resolution classification conflicts with public owner lifecycle",
            )
    return expected


def _prepare_resolutions(
    root: Path, journal: dict[str, Any], resolutions: list[dict[str, Any]],
) -> list[tuple[str, str, dict[str, Any], str | None]]:
    prepared = []
    for item in resolutions:
        expect_keys(item, {"operation_id", "classification", "evidence_ref",
                           "evidence_sha256"}, set(), "resolution",
                    "invalid_resolution_bundle")
        classification = item["classification"]
        require(classification in {
            "ready_to_resume", "already_settled", "already_covered",
        },
                "invalid_resolution_bundle",
                "bundle resolution classification is unsupported")
        plan_item, _ = operation(journal, item["operation_id"])
        if classification == "ready_to_resume":
            evidence = validate_reservation_evidence(
                root, plan_item,
                {"ref": item["evidence_ref"], "sha256": item["evidence_sha256"]},
                dependencies_ready=True,
            )
            effect = None
        elif classification == "already_covered":
            evidence = verify_operation_source_approval(
                root, plan_item,
                {"ref": item["evidence_ref"], "sha256": item["evidence_sha256"]},
            )
            effect = None
        else:
            _completion, effect = validate_completion(
                root, journal, item["operation_id"],
                item["evidence_ref"], item["evidence_sha256"],
            )
            evidence = _evidence(root, item["evidence_ref"], item["evidence_sha256"],
                                 "settled_completion")
        prepared.append((item["operation_id"], classification, evidence, effect))
    return prepared


def resolve_all(
    root: Path, workflow_id: str, bundle_ref: str, bundle_sha256: str,
    expected_revision: int,
) -> dict[str, Any]:
    def mutate(journal: dict[str, Any]) -> dict[str, Any]:
        body = _read_bundle(root, bundle_ref, bundle_sha256, journal)
        replayed = any(
            item.get("event") == "authority_bundle_resolved"
            and item.get("bundle_ref") == bundle_ref
            and item.get("bundle_sha256") == bundle_sha256
            for item in journal["events"]
        )
        if replayed:
            _validate_replay(root, journal, body)
            return {"command": "resolve-all", "bundle_ref": bundle_ref}
        source = body["from_classification"]
        require(source in {"needs_user_approval", "already_covered"},
                "invalid_resolution_bundle", "unsupported bundle source classification")
        resolutions = body["resolutions"]
        require(isinstance(resolutions, list) and bool(resolutions),
                "invalid_resolution_bundle", "resolutions must be a non-empty list")
        interaction = body["user_interaction"]
        require(isinstance(interaction, bool), "invalid_resolution_bundle",
                "user_interaction must be boolean")
        require(not interaction or source == "needs_user_approval",
                "invalid_resolution_bundle",
                "only semantic needs_user_approval resolution records user interaction")
        expected = _expected_ids(
            root, journal, source, resolutions, interaction=interaction,
        )
        if interaction:
            maximum = journal["plan"]["max_user_approval_interactions"]
            require(journal["approval_interactions_used"] < maximum,
                    "approval_interaction_budget_exhausted",
                    "workflow cannot request another user approval interaction",
                    next_action="reuse_existing_decision_or_prepare_changed_plan")
        prepared = _prepare_resolutions(root, journal, resolutions)
        for operation_id, classification, evidence, _effect in prepared:
            state = journal["operation_state"][operation_id]
            state["resolution"] = classification
            state["resolution_evidence"] = evidence
            state["status"] = "complete" if classification == "already_settled" else "pending"
            if classification == "already_settled":
                state["result_evidence"] = evidence
        if interaction:
            journal["approval_interactions_used"] += 1
        event(journal, "authority_bundle_resolved", from_classification=source,
              operations=sorted(expected), bundle_ref=bundle_ref,
              bundle_sha256=bundle_sha256, user_interaction=interaction)
        for operation_id, _classification, evidence, effect in prepared:
            if effect == "confirmed_no_effect":
                cancel_index_dependents(
                    root, journal, operation_id, evidence,
                )
        return {"command": "resolve-all", "bundle_ref": bundle_ref}

    return mutate_workflow(root, workflow_id, expected_revision, mutate)
