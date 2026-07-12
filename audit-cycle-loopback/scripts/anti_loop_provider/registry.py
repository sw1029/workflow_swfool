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
    basis = {
        "cycle_id": str(cycle_id),
        "canonical_artifact_family": str(canonical_artifact_family),
        "blocker_signature": str(blocker_signature),
        "input_state_fingerprint": str(input_state_fingerprint),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "attempt-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

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
        identity = str(row.get("attempt_identity") or "")
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
                corrected["correction_of_attempt_identity"] = identity
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
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")

def normalize_hook_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)[:128]

def hook_demand_threshold_from_value(value: Any, default: int = HOOK_DEMAND_THRESHOLD_DEFAULT) -> int:
    if isinstance(value, dict):
        for key in ("hook_demand_threshold", "threshold", "value", "default"):
            parsed = int(float_value(value.get(key)) or 0)
            if parsed > 0:
                return parsed
        return max(1, int(default or HOOK_DEMAND_THRESHOLD_DEFAULT))
    parsed = int(float_value(value) or 0)
    return max(1, parsed or int(default or HOOK_DEMAND_THRESHOLD_DEFAULT))

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
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
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
    rows = read_jsonl(path)
    seen = {
        (
            str(row.get("cycle_id") or ""),
            str(row.get("family_key") or ""),
            str(row.get("root_key") or ""),
            str(row.get("hypothesized_root_cause") or ""),
        )
        for row in rows
    }
    changed = False
    for entry in entries:
        attempt_identity = str(entry.get("attempt_identity") or "")
        correction = next(
            (
                row
                for row in rows
                if attempt_identity
                and str(row.get("attempt_identity") or "") == attempt_identity
                and equivalent_root_cause(entry, row)
            ),
            None,
        )
        if correction is not None:
            label_fields = (
                "family_key",
                "root_key",
                "root_family_key",
                "hypothesized_root_cause",
            )
            if not any(
                str(correction.get(field) or "") != str(entry.get(field) or "")
                for field in label_fields
            ):
                continue
            corrected = dict(entry)
            corrected["label_correction"] = True
            corrected["correction_of_attempt_identity"] = attempt_identity
            corrected["repair_attempted"] = False
            corrected["attempt_count"] = 0
            corrected["vacuous_attempt_count"] = 0
            rows.append(corrected)
            changed = True
            continue
        key = (
            str(entry.get("cycle_id") or ""),
            str(entry.get("family_key") or ""),
            str(entry.get("root_key") or ""),
            str(entry.get("hypothesized_root_cause") or ""),
        )
        if key in seen:
            continue
        rows.append(entry)
        seen.add(key)
        changed = True
    if changed:
        rows = compact_root_cause_ledger(rows, max_rows_per_family)
        write_registry(path, rows)
    return rows, changed

def feed_exhausted_family_seal(root: Path, packet: dict[str, Any]) -> str | None:
    path = root / ".task" / "sealed_blocker_families.json"
    existing = read_json(path)
    if isinstance(existing, dict) and isinstance(existing.get("families"), list):
        data = existing
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
    record = {
        "semantic_signature": semantic or None,
        "blocker_signature": blocker or None,
        "root_key": root_key or None,
        "root_family_key": root_family or None,
        "hypothesis_exhausted": True,
        "vacuous_untried_attempt_count": packet.get("vacuous_untried_attempt_count"),
        "untried_promotion_budget": packet.get("untried_promotion_budget"),
        "reason": "root-cause hypothesis budget exhausted without terminal_outcome_changed",
        "updated_at": now_iso(),
        "source": "audit-cycle-loopback",
    }
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return rel_path(root, path)
