from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .constants import TERMINAL_LATCH_KEY_VERSION, TERMINAL_OBSERVATION_FIELDS
from .event_model import now_iso
from .support import file_sha256


def content_bound_material_delta(value: Any) -> tuple[str | None, list[str]]:
    if value in (None, False, "", [], {}):
        return None, []
    if not isinstance(value, dict):
        return None, ["material_delta_content_identity"]
    identity_fields = (
        "artifact_sha256",
        "input_state_fingerprint",
        "authority_state_fingerprint",
        "external_state_fingerprint",
        "blocker_signature",
        "delta_sha256",
    )
    identity = {field: value.get(field) for field in identity_fields if value.get(field) not in (None, "")}
    if not identity:
        return None, ["material_delta_content_identity"]
    for field in ("artifact_sha256", "delta_sha256"):
        if field in identity and not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", str(identity[field]).lower()):
            return None, [field]
    canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), []


def terminal_reopen_contract(transition: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(transition, dict):
        return {}, ["lifecycle_transition_result"]
    transaction_id = str(transition.get("transaction_id") or "").strip()
    normalized: dict[str, Any] = {"transaction_id": transaction_id, "artifacts": {}}
    missing: list[str] = []
    if not transaction_id:
        missing.append("transaction_id")
    artifacts = transition.get("artifacts") if isinstance(transition.get("artifacts"), dict) else {}
    for name in ("seal", "registry", "pack", "index"):
        supplied = artifacts.get(name) if isinstance(artifacts.get(name), dict) else {}
        ref = str(supplied.get("ref") or transition.get(f"{name}_ref") or "").strip()
        sha256 = str(supplied.get("sha256") or transition.get(f"{name}_sha256") or "").strip().lower().removeprefix("sha256:")
        if not ref:
            missing.append(f"{name}_ref")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            missing.append(f"{name}_sha256")
        normalized["artifacts"][name] = {"ref": ref, "sha256": sha256}
    expected_transaction_sha = hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    supplied_transaction_sha = str(transition.get("transaction_sha256") or "").strip().lower().removeprefix("sha256:")
    if supplied_transaction_sha != expected_transaction_sha:
        missing.append("transaction_sha256")
    normalized["transaction_sha256"] = expected_transaction_sha
    return normalized, sorted(set(missing))


def verify_terminal_reopen_receipt(root: Path, transition: Any) -> tuple[bool, list[str]]:
    normalized, missing = terminal_reopen_contract(transition)
    if missing:
        return False, missing
    failures: list[str] = []
    root_resolved = root.resolve()
    for name, artifact in normalized["artifacts"].items():
        raw_ref = Path(str(artifact["ref"]))
        if raw_ref.is_absolute() or "#" in str(artifact["ref"]):
            failures.append(f"{name}_ref")
            continue
        path = (root_resolved / raw_ref).resolve(strict=False)
        try:
            path.relative_to(root_resolved)
        except ValueError:
            failures.append(f"{name}_ref")
            continue
        if file_sha256(path) != artifact["sha256"]:
            failures.append(f"{name}_sha256")
    return not failures, sorted(set(failures))


def terminal_latch_contract(event: dict[str, Any]) -> tuple[int, tuple[str, ...], tuple[str, ...], list[str]]:
    raw_version = event.get("terminal_latch_key_version")
    if raw_version is None:
        version = (
            TERMINAL_LATCH_KEY_VERSION
            if any(event.get(field) is not None for field in ("blocker_signature", "external_state_fingerprint"))
            else 1
        )
    elif (
        isinstance(raw_version, bool)
        or not isinstance(raw_version, int)
        or raw_version not in {1, TERMINAL_LATCH_KEY_VERSION}
    ):
        return 0, (), (), ["terminal_latch_key_version"]
    else:
        version = raw_version
    fields = (
        (
            "terminal_outcome_family_key",
            "blocker_signature",
            "input_state_fingerprint",
            "authority_state_fingerprint",
            "external_state_fingerprint",
        )
        if version == 2
        else ("terminal_outcome_family_key", "input_state_fingerprint", "authority_state_fingerprint")
    )
    key = tuple(str(event.get(field) or "").strip() for field in fields)
    missing = [field for field, value in zip(fields, key) if not value]
    return version, fields, key, missing


def terminal_event_reference(event: dict[str, Any]) -> tuple[str, str]:
    event_ref = ".task/cycle/{}/stage.jsonl#{}".format(
        str(event.get("cycle_id") or "unknown_cycle"),
        str(event.get("event_id") or "unknown_event"),
    )
    canonical = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return event_ref, hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _terminal_delta_state(
    previous_events: list[dict[str, Any]],
    latest_terminal: tuple[dict[str, Any], int, tuple[str, ...]] | None,
    event: dict[str, Any],
) -> tuple[str | None, bool, list[str]]:
    raw_material_delta = event.get("material_delta")
    if raw_material_delta in (None, False, "", [], {}):
        raw_material_delta = event.get("input_delta")
    fingerprint, errors = content_bound_material_delta(raw_material_delta)
    latest_fingerprint = None
    if latest_terminal is not None:
        latest_raw_delta = latest_terminal[0].get("material_delta")
        if latest_raw_delta in (None, False, "", [], {}):
            latest_raw_delta = latest_terminal[0].get("input_delta")
        latest_fingerprint, _latest_errors = content_bound_material_delta(latest_raw_delta)
    del previous_events
    return fingerprint, bool(fingerprint and fingerprint != latest_fingerprint), errors


def terminal_latch_state(previous_events: list[dict[str, Any]], event: dict[str, Any]) -> dict[str, Any]:
    if not event.get("terminal_justified"):
        return {}
    version, _tuple_fields, current_key, missing_fields = terminal_latch_contract(event)
    if missing_fields:
        return {
            "terminal_latch_status": "not_evaluated",
            "terminal_latch_key_version": version or None,
            "terminal_latch_missing_fields": missing_fields,
            "quiescent_terminal_latched": False,
        }
    residuals = event.get("residual_classification") or event.get("residuals") or []
    residual_classes = {
        str(item.get("classification") or item.get("residual_class") or item)
        for item in residuals
        if isinstance(item, (dict, str))
    }
    if residual_classes & {"self_resolvable_local", "offline_recompute", "existing_authority", "unverified"}:
        return {
            "terminal_latch_status": "prohibited",
            "quiescent_terminal_latched": False,
            "terminal_latch_residual_classes": sorted(residual_classes),
        }
    previous_terminal_rows: list[tuple[dict[str, Any], int, tuple[str, ...]]] = []
    for row in previous_events:
        if not row.get("terminal_justified"):
            continue
        row_version, _row_fields, row_key, row_missing = terminal_latch_contract(row)
        if not row_missing:
            previous_terminal_rows.append((row, row_version, row_key))
    latest_terminal = previous_terminal_rows[-1] if previous_terminal_rows else None
    previous = (
        latest_terminal[0]
        if latest_terminal is not None and latest_terminal[1] == version and latest_terminal[2] == current_key
        else None
    )
    material_delta_fingerprint, material_delta, material_delta_errors = _terminal_delta_state(
        previous_events, latest_terminal, event
    )
    if material_delta_errors:
        return {
            "terminal_latch_status": "not_evaluated",
            "terminal_latch_key_version": version,
            "terminal_latch_missing_fields": material_delta_errors,
            "quiescent_terminal_latched": False,
        }
    if previous is not None and not material_delta:
        prior_ref, prior_sha256 = terminal_event_reference(previous)
        unchanged_streak = int(previous.get("terminal_latch_streak") or 1) + 1
        return {
            "terminal_latch_status": "latched",
            "terminal_latch_key_version": version,
            "quiescent_terminal_latched": True,
            "suppress_full_cycle": True,
            "terminal_latch_streak": unchanged_streak,
            "unchanged_terminal_ref": previous.get("event_id"),
            "unchanged_ref": {
                "prior_packet_ref": prior_ref,
                "prior_packet_sha256": prior_sha256,
                "latch_key": list(current_key),
                "observed_at": str(event.get("created_at") or now_iso()),
                "unchanged_streak": unchanged_streak,
                "material_delta": False,
            },
            "unchanged_refs": [{"path": prior_ref, "sha256": prior_sha256}],
            "terminal_latch_source_cycle_id": previous.get("cycle_id"),
        }
    latest_latched = next((row for row in reversed(previous_events) if row.get("quiescent_terminal_latched")), None)
    reopen_source = latest_latched
    latest_latched_contract = terminal_latch_contract(reopen_source) if reopen_source is not None else None
    key_changed = bool(
        latest_latched_contract is not None
        and not latest_latched_contract[3]
        and (latest_latched_contract[0] != version or latest_latched_contract[2] != current_key)
    )
    if reopen_source is not None and (key_changed or material_delta):
        transition = event.get("lifecycle_transition_result") if isinstance(event.get("lifecycle_transition_result"), dict) else {}
        normalized_transition, transition_errors = terminal_reopen_contract(transition)
        atomic = not transition_errors
        return {
            "terminal_latch_status": "reopened" if atomic else "reopen_incomplete",
            "terminal_latch_key_version": version,
            "quiescent_terminal_latched": False,
            "terminal_latch_source_cycle_id": reopen_source.get("cycle_id"),
            "terminal_latch_key_changed": key_changed,
            "material_delta_fingerprint": material_delta_fingerprint,
            "lifecycle_transition_result": {
                **normalized_transition,
                "atomic": atomic,
                "validation_errors": transition_errors,
            },
        }
    return {
        "terminal_latch_status": "observed",
        "terminal_latch_key_version": version,
        "quiescent_terminal_latched": False,
        "terminal_latch_streak": 1,
    }


def compact_terminal_observation(event: dict[str, Any], latch: dict[str, Any]) -> dict[str, Any]:
    compact = {field: event[field] for field in TERMINAL_OBSERVATION_FIELDS if field in event}
    compact.update(latch)
    compact["event_kind"] = "terminal_latch_observation"
    compact["compact_observation"] = True
    compact["reason"] = str(event.get("reason") or "quiescent terminal observation")
    compact["artifacts"] = []
    compact["changed_files"] = []
    compact["blockers"] = []
    return compact
