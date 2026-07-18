"""Crash-safe apply and recovery for immutable external-advice intake plans."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import rel_path, sha256_text
from .intake_intent import (
    assert_no_pending_intake_intents,
    intake_intent_status,
    publish_intake_intent,
)
from .intake_no_effect import (
    load_no_effect_receipt,
    no_effect_receipt,
    no_effect_result,
    observe_prestate,
    publish_no_effect_receipt,
    stale_reason_codes,
)
from .intake_no_effect_proof import (
    duplicate_proof,
    duplicate_proof_current,
    historical_registry_proof,
)
from .intake_plan import (
    _build_event,
    _digest_or_none,
    _registry_snapshot_read_only,
    _source_text,
)
from .intake_plan_contract import (
    RESULT_SCHEMA_VERSION,
    canonical_bytes,
    canonical_destination_path,
    canonical_intake_artifact_path,
    load_intake_plan,
    receipt_for_plan,
    receipt_status,
    regular_payload,
    sha256_bytes,
)
from .normalization import normalize_text
from .storage import (
    atomic_replace,
    event_bytes,
    index_jsonl,
    index_md,
    merge_state,
    parse_events,
    publish_immutable,
    rebuild_index,
    registry_lock,
)


def _tagged_events(
    events: list[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    tagged = [row for row in events if row.get("intake_plan_id") == plan["plan_id"]]
    if len(tagged) > 1:
        raise SystemExit("External-advice intake plan has duplicate committed events")
    return tagged


def _committed_boundary_valid(
    registry: bytes,
    events: list[dict[str, Any]],
    plan: dict[str, Any],
    event: dict[str, Any],
) -> bool:
    indexes = [
        index
        for index, row in enumerate(events)
        if row.get("intake_plan_id") == plan["plan_id"]
    ]
    if len(indexes) != 1 or events[indexes[0]] != event:
        return False
    before_size = plan["registry"]["before_size"]
    prefix = registry[:before_size]
    if sha256_bytes(prefix) != plan["registry"]["before_sha256"]:
        return False
    separator = b"\n" if prefix and not prefix.endswith(b"\n") else b""
    planned_payload = separator + event_bytes(event)
    boundary = before_size + len(planned_payload)
    if registry[before_size:boundary] != planned_payload:
        return False
    suffix = events[indexes[0] + 1 :]
    return registry[boundary:] == b"".join(event_bytes(row) for row in suffix)


def _materialize_plan(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    text = _source_text(root, plan["raw"]["source_ref"], plan["raw"]["sha256"])
    metadata = plan["metadata"]
    normalized = normalize_text(
        plan["advice_id"],
        text,
        plan["raw"]["path"],
        metadata["title"],
        metadata["priority"],
        plan["raw"]["sha256"],
        source_id=metadata["source_id"],
        received_at=plan["created_at"],
        normalized_at=plan["created_at"],
    )
    if sha256_text(normalized) != plan["normalized"]["sha256"]:
        raise SystemExit("External-advice intake deterministic normalization mismatch")
    event = _build_event(
        advice_id=plan["advice_id"],
        plan_id=plan["plan_id"],
        title=metadata["title"],
        title_policy=metadata["title_policy"],
        priority=metadata["priority"],
        timestamp=plan["created_at"],
        raw_path=plan["raw"]["path"],
        active_path=plan["normalized"]["path"],
        raw_sha256=plan["raw"]["sha256"],
        normalized_sha256=plan["normalized"]["sha256"],
        source_id=metadata["source_id"],
        text=text,
    )
    if sha256_bytes(canonical_bytes(event)) != plan["event_sha256"]:
        raise SystemExit("External-advice intake recomputed event mismatch")
    return {
        "raw": text.encode("utf-8"),
        "normalized": normalized.encode("utf-8"),
        "event": event,
    }


def _preflight_destinations(
    root: Path,
    plan: dict[str, Any],
    content: dict[str, Any],
    *,
    require_present: bool,
) -> list[str]:
    missing: list[str] = []
    for key in ("raw", "normalized"):
        path = canonical_destination_path(root, plan[key]["path"], kind=key)
        if not path.exists() and not path.is_symlink():
            if require_present:
                raise SystemExit(
                    f"Committed external-advice intake artifact is missing: {path}"
                )
            missing.append(key)
            continue
        if regular_payload(root, path) != content[key]:
            raise SystemExit(f"External-advice intake destination conflict: {path}")
    return missing


def _publish_destinations(
    root: Path,
    plan: dict[str, Any],
    content: dict[str, Any],
    missing: list[str],
) -> bool:
    for key in missing:
        path = canonical_destination_path(
            root, plan[key]["path"], kind=key, ensure_parent=True
        )
        publish_immutable(root, path, content[key])
    return bool(missing)


def _prestate_current(plan: dict[str, Any], observation: dict[str, Any]) -> bool:
    destinations = observation["destination_observations"]
    return (
        not stale_reason_codes(plan, observation)
        and observation["source_observation"]["state"] == "exact"
        and all(
            destinations[key]["state"] in {"absent", "exact"}
            for key in ("raw", "normalized")
        )
    )


def _observation_is_safe(observation: dict[str, Any]) -> bool:
    return (
        observation["source_observation"]["state"] != "unsafe"
        and all(
            observation["destination_observations"][key]["state"] != "unsafe"
            for key in ("raw", "normalized")
        )
    )


def _no_effect_proof_current(
    root: Path,
    plan: dict[str, Any],
    registry: bytes,
    events: list[dict[str, Any]],
    receipt: dict[str, Any],
    intent_state: str,
) -> bool:
    current_observation = observe_prestate(
        root, plan, registry, regular_payload(root, index_md(root), missing=b"")
    )
    if (
        intent_state != "missing"
        or current_observation["plan_owned_publication_observed"]
        or not historical_registry_proof(
        registry, events, receipt, str(plan["plan_id"])
        )
    ):
        return False
    return receipt["settlement_kind"] != "exact_duplicate" or duplicate_proof_current(
        root, events, receipt["duplicate_proof"]
    )


def _try_settle_no_effect(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    registry: bytes,
    events: list[dict[str, Any]],
    intent_state: str,
) -> dict[str, Any] | None:
    if intent_state != "missing":
        return None
    assert_no_pending_intake_intents(root)
    markdown = regular_payload(root, index_md(root), missing=b"")
    observation = observe_prestate(root, plan, registry, markdown)
    if not _observation_is_safe(observation):
        return None
    if observation["plan_owned_publication_observed"]:
        return None
    proof = duplicate_proof(root, plan, events)
    reasons = (
        ["duplicate_exact_raw_source"]
        if proof is not None
        else stale_reason_codes(plan, observation)
    )
    if not reasons:
        return None
    receipt = no_effect_receipt(
        plan,
        plan_ref,
        plan_file_sha256,
        observation,
        reasons,
        proof,
    )
    receipt_ref, receipt_digest = publish_no_effect_receipt(
        root, plan, plan_ref, plan_file_sha256, receipt
    )
    return no_effect_result(
        plan,
        plan_ref,
        receipt,
        receipt_ref,
        receipt_digest,
        replay=False,
    )


def _effect_result(
    root: Path,
    plan: dict[str, Any],
    plan_ref: str,
    plan_file_sha256: str,
    receipt: dict[str, Any],
    receipt_path: Path,
    receipt_file_sha256: str,
    event: dict[str, Any],
    state: dict[str, dict[str, Any]],
    *,
    replay: bool,
    recovered: bool,
    mutation_performed: bool,
) -> dict[str, Any]:
    receipt_ref = rel_path(root, receipt_path)
    return {
        "result_kind": "external_advice_intake_apply_result",
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "ok",
        "apply_status": "already_applied" if replay else "applied",
        "event": event,
        "advice_id": plan["advice_id"],
        "plan_id": plan["plan_id"],
        "plan_ref": plan_ref,
        "plan_sha256": plan["plan_sha256"],
        "plan_file_sha256": plan_file_sha256,
        "receipt_ref": receipt_ref,
        "receipt_content_sha256": receipt["receipt_content_sha256"],
        "receipt_file_sha256": receipt_file_sha256,
        "execution_result_binding": {
            "ref": receipt_ref,
            "sha256": receipt_file_sha256,
        },
        "idempotent_replay": replay,
        "publication_recovered": recovered,
        "mutation_performed": mutation_performed,
        "index_md": rel_path(root, index_md(root)),
        "advice_count": len(state),
    }


def apply_intake_plan(root: Path, path_value: str | Path) -> dict[str, Any]:
    root = root.resolve()
    plan_path, plan, plan_file_sha256 = load_intake_plan(root, path_value)
    plan_ref = rel_path(root, plan_path)
    for key in ("raw", "normalized"):
        canonical_destination_path(root, plan[key]["path"], kind=key)
    receipt_path = canonical_intake_artifact_path(root, plan["plan_id"], "receipt")
    receipt = receipt_for_plan(plan, plan_ref, plan_file_sha256)
    replay = recovered = intent_created = False
    with registry_lock(root):
        assert_no_pending_intake_intents(root, allowed_plan_id=str(plan["plan_id"]))
        registry_before, events = _registry_snapshot_read_only(root)
        tagged = _tagged_events(events, plan)
        intent_state, _intent_digest = intake_intent_status(
            root, plan, plan_ref, plan_file_sha256
        )
        no_effect_state, settled_receipt, settled_digest = load_no_effect_receipt(
            root, plan, plan_ref, plan_file_sha256
        )
        if no_effect_state == "current" and settled_receipt is not None:
            if not _no_effect_proof_current(
                root, plan, registry_before, events, settled_receipt, intent_state
            ):
                raise SystemExit("External-advice no-effect receipt proof conflict")
            assert settled_digest is not None
            return no_effect_result(
                plan,
                plan_ref,
                settled_receipt,
                rel_path(root, receipt_path),
                settled_digest,
                replay=True,
            )
        if no_effect_state == "conflict":
            raise SystemExit("External-advice no-effect receipt conflict")
        receipt_state, receipt_file_sha256 = receipt_status(
            root, receipt_path, receipt
        )
        if receipt_state == "conflict":
            raise SystemExit("External-advice intake receipt conflict")
        if not tagged:
            if receipt_state == "current":
                raise SystemExit(
                    "External-advice intake receipt lacks its committed event"
                )
            settled = _try_settle_no_effect(
                root,
                plan,
                plan_ref,
                plan_file_sha256,
                registry_before,
                events,
                intent_state,
            )
            if settled is not None:
                return settled
            if intent_state == "conflict":
                raise SystemExit("External-advice intake intent conflict")
            if sha256_bytes(registry_before) != plan["registry"]["before_sha256"]:
                raise SystemExit("External-advice intake registry CAS mismatch")
            markdown_before = regular_payload(root, index_md(root), missing=b"")
            if _digest_or_none(markdown_before) != plan["markdown"]["before_sha256"]:
                raise SystemExit("External-advice intake Markdown CAS mismatch")
        content = _materialize_plan(root, plan)
        event = content["event"]
        replay = bool(tagged)
        if replay and tagged[0] != event:
            raise SystemExit("External-advice intake plan is conflictingly applied")
        if replay and not _committed_boundary_valid(
            registry_before, events, plan, event
        ):
            raise SystemExit("External-advice intake committed boundary is invalid")
        if not replay:
            payload = registry_before
            if payload and not payload.endswith(b"\n"):
                payload += b"\n"
            payload += event_bytes(event)
            if sha256_bytes(payload) != plan["registry"]["after_sha256"]:
                raise SystemExit("External-advice intake planned registry digest mismatch")
        missing = _preflight_destinations(root, plan, content, require_present=replay)
        if receipt_state == "missing":
            intent_created = publish_intake_intent(
                root, plan, plan_ref, plan_file_sha256
            )
        staged = _publish_destinations(root, plan, content, missing)
        if not replay:
            atomic_replace(root, index_jsonl(root), payload)
        at_boundary = (
            sha256_bytes(regular_payload(root, index_jsonl(root), missing=b""))
            == plan["registry"]["after_sha256"]
        )
        projection_current = (
            sha256_bytes(regular_payload(root, index_md(root), missing=b""))
            == plan["markdown"]["after_sha256"]
        )
        if replay and receipt_state == "missing" and not at_boundary:
            rebuild_index(root, generated_at=plan["created_at"])
            recovered = True
        elif at_boundary and (not projection_current or receipt_state == "missing"):
            rebuild_index(root, generated_at=plan["created_at"])
            if sha256_bytes(regular_payload(root, index_md(root))) != plan["markdown"]["after_sha256"]:
                raise SystemExit("External-advice intake render digest mismatch")
            recovered = replay
        if receipt_state == "missing":
            publish_immutable(
                root, receipt_path, canonical_bytes(receipt) + b"\n"
            )
            receipt_file_sha256 = sha256_bytes(regular_payload(root, receipt_path))
            recovered = replay
        assert receipt_file_sha256 is not None
        state = merge_state(
            parse_events(regular_payload(root, index_jsonl(root)), index_jsonl(root))
        )
    return _effect_result(
        root,
        plan,
        plan_ref,
        plan_file_sha256,
        receipt,
        receipt_path,
        receipt_file_sha256,
        event,
        state,
        replay=replay,
        recovered=recovered,
        mutation_performed=(not replay) or recovered or staged or intent_created,
    )
