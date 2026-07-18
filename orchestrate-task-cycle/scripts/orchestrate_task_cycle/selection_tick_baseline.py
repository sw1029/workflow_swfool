"""Validated selection-tick baselines and sticky exact-input observations."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .selection_decision_receipt import (
    acknowledgement_binding,
    normalize_binding,
    read_receipt_trigger_tick,
    read_selection_decision_receipt,
)
from .selection_tick_contract import (
    ACKNOWLEDGEMENT_KEYS,
    validate_selection_tick_v2,
)
from .selection_tick_limits import MAX_AUTHORITY_PACKETS, MAX_WATCH_ENTRIES
from .selection_tick_premise import (
    VERIFIED_PREMISE_CONTRACT,
    validate_embedded_verified_premise_row,
)


SAFE_BASELINE_STATUSES = frozenset({"baseline_recorded", "no_op"})
STICKY_WATCH_KINDS = frozenset({"exact_premise", "effective_authority"})
_PACKET_ID = re.compile(r"selection-tick-[0-9a-f]{32}")
_WATCH_ID = re.compile(r"watch-[0-9a-f]{24}")
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_SELECTION_JSON_BYTES = 256 * 1024


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _expected_packet_id(packet: dict[str, Any]) -> str:
    body = {key: child for key, child in packet.items() if key != "packet_id"}
    return "selection-tick-" + hashlib.sha256(_canonical(body)).hexdigest()[:32]


def _packet_candidates(value: dict[str, Any]) -> list[object]:
    candidates: list[object] = [value]
    nested_result = value.get("result")
    if isinstance(nested_result, dict):
        candidates.append(nested_result)
    for candidate in list(candidates):
        if not isinstance(candidate, dict):
            continue
        terminal_wait = candidate.get("terminal_wait")
        if isinstance(terminal_wait, dict):
            candidates.append(terminal_wait.get("selection_tick_baseline"))
    return candidates


def load_json_object(root: Path, raw: str, label: str) -> dict[str, Any]:
    """Load one bounded root-local regular JSON object without following symlinks."""

    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository root must be a directory")
    candidate = Path(raw).expanduser()
    if not raw or ".." in candidate.parts:
        raise ValueError(f"{label} path is invalid")
    lexical = candidate if candidate.is_absolute() else root / candidate
    try:
        relative = lexical.absolute().relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} path is outside repository root") from exc
    current = root
    try:
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise OSError
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
        if not stat.S_ISREG(resolved.lstat().st_mode):
            raise OSError
        with resolved.open("rb") as handle:
            body = handle.read(MAX_SELECTION_JSON_BYTES + 1)
        if len(body) > MAX_SELECTION_JSON_BYTES:
            raise ValueError(f"{label} exceeds {MAX_SELECTION_JSON_BYTES} bytes")
        value = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def load_json_objects(root: Path, paths: list[str], label: str) -> list[dict[str, Any]]:
    """Load bounded caller-supplied root-local JSON objects."""

    if len(paths) > MAX_AUTHORITY_PACKETS:
        raise ValueError(f"{label} count exceeds {MAX_AUTHORITY_PACKETS}")
    return [load_json_object(root, raw, label) for raw in paths]


@dataclass(frozen=True, slots=True)
class PreviousSelectionTick:
    """One authenticated prior tick and its explicit acknowledgement mode."""

    packet: dict[str, Any]
    acknowledging_selection: bool
    selection_acknowledgement_binding: dict[str, Any] | None = None


def _common_packet_valid(root: Path, packet: dict[str, Any]) -> bool:
    if packet.get("format_version") == 2:
        try:
            validate_selection_tick_v2(packet)
        except (TypeError, ValueError):
            return False
        common = True
    else:
        packet_id = packet.get("packet_id")
        common = bool(
            isinstance(packet_id, str)
            and _PACKET_ID.fullmatch(packet_id)
            and packet_id == _expected_packet_id(packet)
            and packet.get("format_version") == 1
            and packet.get("artifact_kind") == "selection_tick"
            and packet.get("full_cycle_allowed") is False
            and packet.get("mutation_performed") is False
            and packet.get("not_goal_truth") is True
            and packet.get("not_authority") is True
            and isinstance(packet.get("watch_entries"), list)
        )
    if not common or packet.get("baseline_rebased") is not True:
        return common
    binding = packet.get("selection_acknowledgement_binding")
    if not isinstance(binding, dict) or set(binding) != ACKNOWLEDGEMENT_KEYS:
        return False
    try:
        receipt_binding = normalize_binding(
            {
                "ref": binding.get("selection_receipt_ref"),
                "sha256": binding.get("selection_receipt_sha256"),
            },
            "selection decision receipt",
        )
        receipt = read_selection_decision_receipt(
            root,
            receipt_binding,
            expected_trigger_binding={
                "trigger_selection_tick_id": binding.get("trigger_tick_id"),
                "trigger_selection_tick_sha256": binding.get("trigger_tick_sha256"),
            },
        )
        expected = acknowledgement_binding(receipt_binding, receipt)
        trigger = read_receipt_trigger_tick(root, receipt)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return bool(
        binding == expected
        and packet.get("acknowledged_selection_tick_id")
        == binding.get("trigger_tick_id")
        and packet.get("selection_acknowledgement_status") == "accepted"
        and _rebased_descends_from_trigger(packet, trigger)
    )


def _rebased_descends_from_trigger(
    packet: dict[str, Any], trigger: dict[str, Any]
) -> bool:
    return bool(
        packet.get("previous_input_manifest_sha256")
        == trigger.get("observed_input_manifest_sha256")
        and packet.get("observed_input_manifest_sha256")
        == trigger.get("observed_input_manifest_sha256")
        and packet.get("watch_entries") == trigger.get("watch_entries")
        and packet.get("changed_watch_entries") == []
        and packet.get("material_changed_watch_entries") == []
        and packet.get("changed_evidence_classes") == []
        and all(
            packet.get(field) == trigger.get(field)
            for field in (
                "wake_predicates",
                "watched_evidence_classes",
                "minimum_material_delta",
                "premise_input_contract",
            )
        )
    )


def validated_previous_tick(
    root: Path,
    value: dict[str, Any] | None,
    acknowledge_selection_tick_id: str | None,
    selection_receipt_ref: str | None,
    selection_receipt_sha256: str | None,
) -> PreviousSelectionTick | None:
    """Authenticate a safe baseline or an exactly acknowledged selection tick."""

    inputs = (
        (acknowledge_selection_tick_id, "acknowledgement packet ID"),
        (selection_receipt_ref, "selection receipt ref"),
        (selection_receipt_sha256, "selection receipt SHA-256"),
    )
    if any(value is not None and not isinstance(value, str) for value, _ in inputs):
        raise ValueError("selection acknowledgement inputs must be strings or null")
    acknowledgement = (acknowledge_selection_tick_id or "").strip()
    receipt_ref = (selection_receipt_ref or "").strip()
    receipt_sha256 = (selection_receipt_sha256 or "").strip()
    if value is None:
        if acknowledgement or receipt_ref or receipt_sha256:
            raise ValueError("selection acknowledgement requires a previous tick")
        return None
    packet = next(
        (
            candidate
            for candidate in _packet_candidates(value)
            if isinstance(candidate, dict)
            and candidate.get("artifact_kind") == "selection_tick"
        ),
        None,
    )
    if not isinstance(packet, dict):
        raise ValueError("previous input does not contain a selection-tick packet")
    if not _common_packet_valid(root, packet):
        raise ValueError(
            "previous selection-tick packet is not a valid terminal-wait baseline"
        )
    safe = bool(
        packet.get("status") in SAFE_BASELINE_STATUSES
        and packet.get("selection_required") is False
        and packet.get("agent_fanout_allowed") is False
    )
    selected = bool(
        packet.get("format_version") == 2
        and packet.get("status") == "selection_required"
        and packet.get("selection_required") is True
        and packet.get("agent_fanout_allowed") is True
        and packet.get("next_action") == "run_derive_selection"
    )
    if safe:
        if acknowledgement or receipt_ref or receipt_sha256:
            raise ValueError(
                "selection acknowledgement is valid only for a selection-required tick"
            )
        return PreviousSelectionTick(packet, False)
    if selected:
        if acknowledgement != packet["packet_id"]:
            raise ValueError(
                "selection-required previous tick requires its exact packet ID acknowledgement"
            )
        try:
            receipt_binding = normalize_binding(
                {"ref": receipt_ref, "sha256": receipt_sha256},
                "selection decision receipt",
            )
            receipt = read_selection_decision_receipt(
                root, receipt_binding, expected_trigger_tick=packet
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                "selection acknowledgement requires an exact persisted decision receipt"
            ) from exc
        return PreviousSelectionTick(
            packet, True, acknowledgement_binding(receipt_binding, receipt)
        )
    raise ValueError(
        "previous selection-tick packet is not a valid terminal-wait baseline"
    )


def _watch_map(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    if len(rows) > MAX_WATCH_ENTRIES:
        raise ValueError(f"{label} watch entry count exceeds {MAX_WATCH_ENTRIES}")
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label} watch entries must be objects")
        watch_id = row.get("watch_id")
        if not isinstance(watch_id, str) or not _WATCH_ID.fullmatch(watch_id):
            raise ValueError(f"{label} watch entry has an invalid watch_id")
        if watch_id in mapped:
            raise ValueError(f"{label} watch entries contain duplicate watch_id values")
        mapped[watch_id] = row
    return mapped


def _validate_sticky_row(row: dict[str, Any]) -> None:
    kind = row.get("kind")
    if kind == "exact_premise":
        if row.get("premise_input_contract") == VERIFIED_PREMISE_CONTRACT:
            validate_embedded_verified_premise_row(row)
            return
        premise_id = row.get("premise_id")
        digest = row.get("sha256")
        valid = bool(
            row.get("evidence_class") == "exact_subject"
            and isinstance(premise_id, str)
            and _OPAQUE_ID.fullmatch(premise_id)
            and row.get("watch_id")
            == "watch-"
            + hashlib.sha256(f"exact_subject:{premise_id}".encode()).hexdigest()[:24]
            and row.get("path_redacted") is True
            and "path" not in row
            and row.get("exists") is True
            and isinstance(digest, str)
            and _SHA256.fullmatch(digest)
            and isinstance(row.get("size_bytes"), int)
            and not isinstance(row.get("size_bytes"), bool)
            and row["size_bytes"] >= 0
            and "premise_receipt" not in row
            and "premise_receipt_id" not in row
        )
    elif kind == "effective_authority":
        scope_id = row.get("authority_scope_id")
        fingerprint = row.get("effective_authority_fingerprint")
        decision = row.get("decision")
        valid = bool(
            row.get("evidence_class") == "authority"
            and isinstance(scope_id, str)
            and _OPAQUE_ID.fullmatch(scope_id)
            and row.get("watch_id")
            == "watch-" + hashlib.sha256(scope_id.encode()).hexdigest()[:24]
            and isinstance(fingerprint, str)
            and _SHA256.fullmatch(fingerprint)
            and isinstance(decision, str)
            and _OPAQUE_ID.fullmatch(decision)
            and isinstance(row.get("axis_statuses"), dict)
        )
    else:
        return
    if not valid:
        raise ValueError("previous selection-tick contains an invalid sticky watch row")


def carry_forward_sticky_rows(
    previous: dict[str, Any] | None,
    current_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Preserve prior exact premise/authority observations when callers omit them."""

    current = _watch_map(current_rows, "current")
    if previous is None:
        return current_rows, []
    previous_rows = previous.get("watch_entries")
    if not isinstance(previous_rows, list):
        raise ValueError("previous selection-tick packet lacks watch entries")
    prior = _watch_map(previous_rows, "previous")
    carried: list[str] = []
    for watch_id, row in prior.items():
        if row.get("kind") not in STICKY_WATCH_KINDS:
            continue
        _validate_sticky_row(row)
        existing = current.get(watch_id)
        if existing is not None:
            if existing.get("kind") != row.get("kind"):
                raise ValueError("sticky watch_id collides with a different watch kind")
            continue
        current[watch_id] = copy.deepcopy(row)
        carried.append(watch_id)
        if len(current) > MAX_WATCH_ENTRIES:
            raise ValueError(f"selection watch entry count exceeds {MAX_WATCH_ENTRIES}")
    rows = sorted(
        current.values(), key=lambda row: (str(row["kind"]), str(row["watch_id"]))
    )
    return rows, sorted(carried)


def changed_watch_entries(
    previous: dict[str, Any], current_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return stable scalar deltas between two authenticated watch manifests."""

    previous_rows = previous.get("watch_entries")
    if not isinstance(previous_rows, list):
        raise ValueError("previous selection-tick packet lacks watch entries")
    before = _watch_map(previous_rows, "previous")
    after = _watch_map(current_rows, "current")
    changed: list[dict[str, Any]] = []
    for watch_id in sorted(set(before) | set(after)):
        old = before.get(watch_id)
        new = after.get(watch_id)
        if old == new:
            continue
        row = new or old or {}
        changed.append(
            {
                "watch_id": watch_id,
                "evidence_class": row.get("evidence_class", "custom_watch"),
                "change_kind": (
                    "added"
                    if old is None
                    else "removed"
                    if new is None
                    else "content_changed"
                ),
            }
        )
    return changed


__all__ = (
    "MAX_SELECTION_JSON_BYTES",
    "PreviousSelectionTick",
    "SAFE_BASELINE_STATUSES",
    "carry_forward_sticky_rows",
    "changed_watch_entries",
    "load_json_object",
    "load_json_objects",
    "validated_previous_tick",
)
