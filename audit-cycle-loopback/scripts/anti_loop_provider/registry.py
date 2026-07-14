from __future__ import annotations

from .common import *

def default_high_water() -> dict[str, Any]:
    return {"ever_provider_dispatch": False}

def decision_input_state_fingerprint(values: list[Any], artifact_ref: dict[str, Any]) -> str:
    supplied = first_field_value(values, {"input_state_fingerprint", "decision_input_fingerprint"})
    input_fingerprints = first_field_value(values, {"input_fingerprints"})
    basis = {
        "artifact_sha256": artifact_ref.get("artifact_sha256"),
        "production_lane_identity": artifact_ref.get("production_lane_identity"),
        "supplied_input_state_fingerprint": str(supplied) if supplied else None,
        "input_fingerprints": input_fingerprints if isinstance(input_fingerprints, dict) else {},
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def content_bound_attempt_identity(
    cycle_id: str,
    canonical_artifact_family: str,
    blocker_signature: str,
    input_state_fingerprint: str,
) -> str:
    # Keep the legacy label parameters in the callable contract, but exclude
    # them from the logical identity.  Family and blocker labels are trace
    # metadata and may be corrected without creating another attempt.
    basis = {
        "cycle_id": str(cycle_id),
        "input_state_fingerprint": str(input_state_fingerprint),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "attempt-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def legacy_content_bound_attempt_identity(
    cycle_id: str,
    canonical_artifact_family: str,
    blocker_signature: str,
    input_state_fingerprint: str,
) -> str:
    """Return the pre-v2 label-bound identity for compatibility tracing."""
    basis = {
        "cycle_id": str(cycle_id),
        "canonical_artifact_family": str(canonical_artifact_family),
        "blocker_signature": str(blocker_signature),
        "input_state_fingerprint": str(input_state_fingerprint),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "attempt-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def logical_attempt_key(row: dict[str, Any]) -> str:
    cycle_id = str(row.get("cycle_id") or "")
    input_fingerprint = str(row.get("input_state_fingerprint") or "")
    if cycle_id and input_fingerprint:
        return f"logical:{cycle_id}:{input_fingerprint}"
    identity = str(row.get("attempt_identity") or "")
    return f"identity:{identity}" if identity else ""


def attempt_revision_value(row: dict[str, Any] | None) -> int:
    if not isinstance(row, dict):
        return 0
    for field in ("attempt_revision", "attempt_revision_candidate"):
        value = int(float_value(row.get(field)) or 0)
        if value > 0:
            return value
    return 1 if row.get("attempt_identity") else 0


def canonical_json_sha256(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_DURABLE_SENSITIVE_KEYS = {
    "anti_loop_handoff",
    "artifact_path_or_store_ref",
    "changed_files",
    "changed_verifier_source_paths",
    "duplicate_key_paths",
    "error",
    "evidence_paths",
    "legacy_attempt_identity",
    "legacy_family_key",
    "message",
    "original_title",
    "path",
    "raw_source_path",
    "reason",
    "repair_task_id",
    "root_cause_ledger_projection",
    "sealed_blocker_families_projection",
    "source_paths",
    "task_family_label",
    "task_id",
    "task_label",
    "task_name",
    "task_pack_name",
    "title",
    "verifier_source_paths",
}
_DURABLE_VOLATILE_KEYS = {
    "checked_at",
    "created_at",
    "created_or_observed_at",
    "timestamp",
    "updated_at",
}
_DURABLE_SENSITIVE_KEY_PARTS = (
    "character_count",
    "char_count",
    "direct_quote",
    "interval",
    "line_number",
    "line_start",
    "line_end",
    "locator",
    "offset",
    "original_title",
    "quoted_text",
    "raw_text",
    "source_text",
    "text_span",
)


def _durable_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().lower()
    return bool(
        normalized in _DURABLE_SENSITIVE_KEYS
        or normalized in _DURABLE_VOLATILE_KEYS
        or normalized.endswith("_at")
        or normalized.endswith("_error")
        or normalized.endswith("_path")
        or normalized.endswith("_paths")
        or normalized.startswith("path_")
        or normalized == "raw"
        or normalized.startswith("raw_")
        or normalized.endswith("_raw")
        or normalized == "text"
        or normalized.startswith("text_")
        or normalized.endswith("_text")
        or normalized == "quote"
        or normalized.startswith("quote_")
        or normalized.endswith("_quote")
        or normalized == "title"
        or normalized.startswith("title_")
        or normalized.endswith("_title")
        or any(part in normalized for part in _DURABLE_SENSITIVE_KEY_PARTS)
    )


def _reference_looks_like_path(value: str) -> bool:
    text = value.strip()
    return bool(
        text.startswith(("/", "./", "../", "~"))
        or "/" in text
        or "\\" in text
        or re.search(r"(?:^|[._-])(?:md|jsonl?|ya?ml|txt|csv|parquet|py)$", text, re.IGNORECASE)
    )


def bounded_durable_projection(value: Any, *, parent_key: str = "") -> Any:
    """Remove source-locating metadata while retaining replayable scalar state."""
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            if _durable_key_is_sensitive(key):
                continue
            if key == "findings" and isinstance(child, list):
                projected[key] = [
                    {
                        field: finding.get(field)
                        for field in ("severity", "code")
                        if finding.get(field) is not None
                    }
                    for finding in child
                    if isinstance(finding, dict)
                ]
                continue
            sanitized = bounded_durable_projection(child, parent_key=key)
            if sanitized is not None or child is None:
                projected[key] = sanitized
        return projected
    if isinstance(value, list):
        projected_items = []
        for child in value:
            sanitized = bounded_durable_projection(child, parent_key=parent_key)
            if sanitized is not None:
                projected_items.append(sanitized)
        return projected_items
    if isinstance(value, str) and _reference_looks_like_path(value):
        if (
            parent_key.endswith("_ref")
            or parent_key.endswith("_refs")
            or parent_key.endswith("_error")
            or parent_key in {"action", "error", "message", "orphans", "provenance_refs"}
        ):
            return None
    return value


def load_verified_finalized_loopback_state(
    root: Path,
    cycle_id: str,
) -> tuple[dict[str, Any], str, str | None]:
    """Load replayable loopback projections through the finalizer's verifier."""
    pointer = root / ".task" / "cycle" / str(cycle_id) / "current_finalization.json"
    if not pointer.is_file():
        return {}, "not_available", None
    ledger_path = (
        Path(__file__).resolve().parents[3]
        / "orchestrate-task-cycle"
        / "scripts"
        / "cycle_ledger.py"
    )
    if not ledger_path.is_file():
        return {}, "invalid", "cycle_ledger_loader_missing"
    spec = importlib.util.spec_from_file_location("cycle_ledger_loopback_consumer", ledger_path)
    if spec is None or spec.loader is None:
        return {}, "invalid", "cycle_ledger_loader_unavailable"
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        verified = module.load_current_finalized_state(root, str(cycle_id))
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return {}, "invalid", f"{type(exc).__name__}:{exc}"
    if not isinstance(verified, dict) or verified.get("valid") is not True:
        return {}, "invalid", "finalized_state_not_verified"
    durable_state = verified.get("durable_state_candidate")
    projections: dict[str, Any] = {}
    if isinstance(durable_state, dict) and durable_state.get("mode") == "complete_projection":
        raw = durable_state.get("projections")
        if isinstance(raw, dict):
            projections = dict(raw)
    elif isinstance(durable_state, dict) and durable_state.get("mode") == "typed_operations":
        for operation in durable_state.get("operations") or []:
            if not isinstance(operation, dict):
                continue
            target_id = str(operation.get("target_id") or "")
            payload = operation.get("payload")
            if target_id and isinstance(payload, dict):
                projections[target_id] = payload
    else:
        return {}, "invalid", "finalized_durable_state_mode_invalid"
    return {
        "verified_state": verified,
        "projections": projections,
    }, "verified", None


def finalized_projection_rows(projections: dict[str, Any], target_id: str) -> tuple[list[dict[str, Any]], bool]:
    aliases = {
        "family_progress_registry": ("family_progress_registry", "registry_projection"),
        "root_cause_ledger": ("root_cause_ledger", "ledger_projection"),
    }
    for key in aliases.get(target_id, (target_id,)):
        value = projections.get(key)
        if isinstance(value, dict) and isinstance(value.get("rows"), list):
            value = value["rows"]
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)], True
        if isinstance(value, dict):
            return [value], True
    return [], False


def finalized_seal_projection(projections: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    value = projections.get("sealed_blocker_families")
    if isinstance(value, dict) and isinstance(value.get("state"), dict):
        value = value["state"]
    return (dict(value), True) if isinstance(value, dict) else ({}, False)

def load_registry(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        return []
    return rows

def compact_registry(rows: list[dict[str, Any]], max_rows_per_family: int) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    identity_index: dict[str, int] = {}
    for row in rows:
        identity = logical_attempt_key(row)
        if identity and identity in identity_index:
            index = identity_index[identity]
            previous = deduplicated[index]
            corrected = dict(previous)
            corrected.update(row)
            if any(
                str(previous.get(field) or "") != str(row.get(field) or "")
                for field in ("family_key", "root_key", "root_family_key", "blocker_signature")
            ):
                corrected["registry_label_correction"] = True
                corrected["correction_of_attempt_identity"] = str(
                    previous.get("attempt_identity") or row.get("attempt_identity") or ""
                )
                previous_revision = attempt_revision_value(previous)
                corrected.setdefault("attempt_revision_candidate", previous_revision + 1)
                corrected.setdefault("supersedes_attempt_revision_candidate", previous_revision)
                corrected.setdefault(
                    "supersedes_attempt_identity_candidate",
                    previous.get("attempt_identity"),
                )
            deduplicated[index] = corrected
            continue
        if identity:
            identity_index[identity] = len(deduplicated)
        deduplicated.append(row)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in deduplicated:
        buckets.setdefault(str(row.get("family_key") or "unknown"), []).append(row)
    compacted: list[dict[str, Any]] = []
    for family_rows in buckets.values():
        compacted.extend(family_rows[-max_rows_per_family:])
    return compacted

def write_registry(path: Path, rows: list[dict[str, Any]]) -> None:
    """Reject the retired direct-write path; finalization owns durable publication."""
    raise RuntimeError(
        "direct anti-loop registry writes are prohibited; publish a typed mutation candidate through cycle finalization"
    )

def normalize_hook_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)[:128]

def hook_demand_threshold_from_value(value: Any, default: Any = None) -> int | None:
    """Read an explicit hook-demand budget without supplying a global default."""
    parsed = positive_int_or_none(value)
    if parsed is not None:
        return parsed
    return positive_int_or_none(default)

def latest_adapter_hook_demand(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    for row in reversed(rows):
        raw = row.get("adapter_hook_demand")
        if not isinstance(raw, list):
            continue
        ledger: dict[str, dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            hook_id = normalize_hook_id(item.get("hook_id"))
            if not hook_id:
                continue
            affected_gate_ids = sorted(
                {
                    normalize_hook_id(gate_id)
                    for gate_id in list_values(item.get("affected_gate_ids"))
                    if normalize_hook_id(gate_id)
                }
            )
            ledger[hook_id] = {
                "hook_id": hook_id,
                "skip_count": max(0, int(float_value(item.get("skip_count")) or 0)),
                "decision_relevant_skip_count": max(
                    0,
                    int(float_value(item.get("decision_relevant_skip_count")) or 0),
                ),
                "affected_gate_ids": affected_gate_ids,
                "first_skip_cycle_id": item.get("first_skip_cycle_id"),
                "last_skip_cycle_id": item.get("last_skip_cycle_id"),
            }
        return ledger
    return {}

def merge_adapter_hook_demand(
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    cycle_id: str,
) -> list[dict[str, Any]]:
    ledger = latest_adapter_hook_demand(rows)
    for event in events:
        if not isinstance(event, dict):
            continue
        hook_id = normalize_hook_id(event.get("hook_id"))
        if not hook_id:
            continue
        record = ledger.setdefault(
            hook_id,
            {
                "hook_id": hook_id,
                "skip_count": 0,
                "decision_relevant_skip_count": 0,
                "affected_gate_ids": [],
                "first_skip_cycle_id": cycle_id,
                "last_skip_cycle_id": cycle_id,
            },
        )
        record["skip_count"] = max(0, int(float_value(record.get("skip_count")) or 0)) + 1
        if bool_value(event.get("decision_relevant_skip")):
            record["decision_relevant_skip_count"] = (
                max(0, int(float_value(record.get("decision_relevant_skip_count")) or 0)) + 1
            )
        affected = set(list_values(record.get("affected_gate_ids")))
        gate_id = normalize_hook_id(event.get("affected_gate_id"))
        if gate_id:
            affected.add(gate_id)
        record["affected_gate_ids"] = sorted(affected)
        record["first_skip_cycle_id"] = record.get("first_skip_cycle_id") or cycle_id
        record["last_skip_cycle_id"] = cycle_id
    return [ledger[key] for key in sorted(ledger)]

def compact_root_cause_ledger(rows: list[dict[str, Any]], max_rows_per_family: int) -> list[dict[str, Any]]:
    lineage_rows: list[dict[str, Any]] = []
    prior_by_attempt: dict[str, list[dict[str, Any]]] = {}
    label_fields = (
        "family_key",
        "root_key",
        "root_family_key",
        "hypothesized_root_cause",
    )
    for supplied in rows:
        row = dict(supplied)
        attempt_identity = str(row.get("attempt_identity") or "")
        prior = next(
            (
                candidate
                for candidate in reversed(prior_by_attempt.get(attempt_identity, []))
                if attempt_identity and equivalent_root_cause(row, candidate)
            ),
            None,
        )
        if prior is not None:
            labels_changed = any(
                str(prior.get(field) or "") != str(row.get(field) or "")
                for field in label_fields
            )
            if not labels_changed:
                continue
            row["label_correction"] = True
            row["correction_of_attempt_identity"] = attempt_identity
            row["repair_attempted"] = False
            row["attempt_count"] = 0
            row["vacuous_attempt_count"] = 0
        lineage_rows.append(row)
        if attempt_identity:
            prior_by_attempt.setdefault(attempt_identity, []).append(row)

    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in lineage_rows:
        family = str(row.get("family_key") or "unknown")
        buckets.setdefault(family, []).append(row)
    compacted: list[dict[str, Any]] = []
    for family_rows in buckets.values():
        latest_by_equivalence: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in family_rows:
            key = root_cause_distinct_key(row)
            existing = latest_by_equivalence.get(key)
            merged = dict(row)
            label_correction = bool_value(row.get("label_correction"))
            attempted_increment = 1 if bool_value(row.get("repair_attempted")) and not label_correction else 0
            vacuous_increment = attempted_increment if not bool_value(row.get("terminal_outcome_changed")) else 0
            if existing:
                merged["attempt_count"] = root_cause_attempt_weight(existing, "attempt_count") + attempted_increment
                merged["vacuous_attempt_count"] = root_cause_attempt_weight(existing, "vacuous_attempt_count") + vacuous_increment
                merged["terminal_outcome_changed"] = bool_value(existing.get("terminal_outcome_changed")) or bool_value(row.get("terminal_outcome_changed"))
                merged["first_cycle_id"] = existing.get("first_cycle_id") or existing.get("cycle_id")
                merged["previous_cycle_id"] = existing.get("cycle_id")
                if label_correction:
                    merged["repair_attempted"] = bool_value(existing.get("repair_attempted"))
                aliases = set(list_values(existing.get("hypothesis_aliases")))
                aliases.add(str(existing.get("hypothesized_root_cause") or ""))
                aliases.add(str(row.get("hypothesized_root_cause") or ""))
                merged["hypothesis_aliases"] = sorted(alias for alias in aliases if alias)[:20]
            else:
                merged["attempt_count"] = root_cause_attempt_weight(row, "attempt_count", attempted_increment)
                merged["vacuous_attempt_count"] = root_cause_attempt_weight(row, "vacuous_attempt_count", vacuous_increment)
            latest_by_equivalence[key] = merged
        compacted.extend(list(latest_by_equivalence.values())[-max_rows_per_family:])
    return compacted

def append_root_cause_ledger(path: Path, entries: list[dict[str, Any]], max_rows_per_family: int = ROOT_CAUSE_LEDGER_MAX_ROWS_PER_FAMILY_DEFAULT) -> tuple[list[dict[str, Any]], bool]:
    """Reject the retired append-and-write helper rather than publish partial truth."""
    raise RuntimeError(
        "direct root-cause ledger writes are prohibited; prepare the root_cause_ledger typed operation instead"
    )

def feed_exhausted_family_seal(root: Path, packet: dict[str, Any]) -> str | None:
    """Reject the retired seal writer; the finalizer publishes its projection atomically."""
    raise RuntimeError(
        "direct family-seal writes are prohibited; prepare the sealed_blocker_families typed operation instead"
    )


def project_exhausted_family_seal(existing: Any, packet: dict[str, Any]) -> dict[str, Any]:
    """Project a complete seal state without publishing it."""
    if isinstance(existing, dict) and isinstance(existing.get("families"), list):
        data = dict(existing)
        records = [item for item in existing["families"] if isinstance(item, dict)]
    elif isinstance(existing, list):
        data = {"schema_version": "sealed-blocker-families-v1", "families": [item for item in existing if isinstance(item, dict)]}
        records = data["families"]
    elif isinstance(existing, dict):
        records = [existing]
        data = {"schema_version": "sealed-blocker-families-v1", "families": records}
    else:
        data = {"schema_version": "sealed-blocker-families-v1", "families": []}
        records = data["families"]
    semantic = str(packet.get("semantic_signature") or "").lower()
    blocker = str(packet.get("blocker_signature") or "").lower()
    root_family = str(packet.get("root_family_key") or packet.get("blocker_root_family") or "").lower()
    root_key = str(packet.get("root_key") or "").lower()
    record = exhausted_family_seal_record(packet)
    replaced = False
    for index, item in enumerate(records):
        if (
            str(item.get("semantic_signature") or "").lower() == semantic
            and str(item.get("blocker_signature") or "").lower() == blocker
            and str(item.get("root_family_key") or "").lower() == root_family
        ):
            records[index] = {**item, **record}
            replaced = True
            break
    if not replaced:
        records.append(record)
    data["families"] = records[-200:]
    return data


def exhausted_family_seal_record(packet: dict[str, Any]) -> dict[str, Any]:
    """Build a seal mutation payload without writing workflow state."""
    semantic = str(packet.get("semantic_signature") or "").lower()
    blocker = str(packet.get("blocker_signature") or "").lower()
    root_family = str(packet.get("root_family_key") or packet.get("blocker_root_family") or "").lower()
    root_key = str(packet.get("root_key") or "").lower()
    return {
        "semantic_signature": semantic or None,
        "blocker_signature": blocker or None,
        "root_key": root_key or None,
        "root_family_key": root_family or None,
        "hypothesis_exhausted": True,
        "vacuous_untried_attempt_count": packet.get("vacuous_untried_attempt_count"),
        "untried_promotion_budget": packet.get("untried_promotion_budget"),
        "reason": "root-cause hypothesis budget exhausted without terminal_outcome_changed",
        "source": "audit-cycle-loopback",
    }
