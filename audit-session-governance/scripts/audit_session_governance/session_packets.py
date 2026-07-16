"""Build and independently validate session-governance packets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .session_common import (
    AUDIT_ID,
    AuditError,
    COUNT_KEYS,
    FINDINGS,
    KIND,
    MAX_ALLOWED_BYTES,
    MAX_BYTES,
    PARSER_VERSION,
    SAFE_ID,
    SHA,
    TOOLS,
    TOP_KEYS,
    VERSION,
    derived_id,
    digest,
    read_snapshot,
    safe_file,
)
from .session_parsing import (
    dedupe_findings,
    make_finding,
    normalize_timestamp,
    parse,
)

def make_binding(
    cycle_id: str | None, task_id: str | None
) -> tuple[dict[str, str], bool]:
    for name, value in (("cycle_id", cycle_id), ("task_id", task_id)):
        if value is not None and not SAFE_ID.fullmatch(value):
            raise AuditError(f"{name} must be a path-safe identifier")
    if cycle_id and task_id:
        return {
            "status": "bound", "cycle_id": cycle_id, "task_id": task_id
        }, False
    if cycle_id or task_id:
        return {"status": "ambiguous"}, True
    return {"status": "unbound"}, False


def build_packet(
    source: Path,
    relative: Path,
    *,
    tool: str,
    session_id: str | None,
    cycle_id: str | None,
    task_id: str | None,
    max_bytes: int,
) -> dict[str, Any]:
    if tool not in TOOLS:
        raise AuditError("tool must be codex or claude-code")
    if max_bytes != MAX_BYTES:
        raise AuditError(f"max-bytes must equal the contract limit {MAX_BYTES}")
    if session_id is not None and not SAFE_ID.fullmatch(session_id):
        raise AuditError("session-id must be a path-safe identifier")
    data, source_hash, size = read_snapshot(source, max_bytes)
    parsed = parse(data, size, tool)
    bound, ambiguous = make_binding(cycle_id, task_id)
    findings = list(parsed["findings"])
    if ambiguous:
        findings.append(make_finding("ambiguous_binding"))
    findings = dedupe_findings(findings)
    status = parsed["status"]
    consumable = status == "complete" and bound["status"] == "bound"
    repair = "none" if status == "complete" else "proposal_only"
    source_path = relative.as_posix()
    evidence = [source_path] + [
        f"sha256:{value}" for value in parsed["hashes"]
    ]
    packet: dict[str, Any] = {
        "format_version": VERSION,
        "artifact_kind": KIND,
        "parser_version": PARSER_VERSION,
        "tool": tool,
        "session_id": session_id or (
            "session-" + digest(source_path.encode("utf-8"))[:24]
        ),
        "source": {
            "path": source_path, "sha256": source_hash, "size_bytes": size,
        },
        "capture_mode": parsed["mode"],
        "capture_status": status,
        "integrity_status": "source_hash_only",
        "binding": bound,
        "consumable": consumable,
        "not_goal_truth": True,
        "not_validation_evidence": True,
        "repair_class": repair,
        "auto_repair_allowed": False,
        "findings": findings,
        "event_counts": parsed["counts"],
        "timestamp_bounds": {
            "first": parsed["times"][0], "last": parsed["times"][1],
        },
        "evidence_paths": evidence,
    }
    packet["audit_id"] = derived_id("audit", packet)
    return packet



def _validate_packet_header(
    packet: dict[str, Any],
    errors: list[str],
) -> Path | None:
    if packet["format_version"] != VERSION or packet["artifact_kind"] != KIND:
        errors.append("packet version or kind is invalid")
    if packet["parser_version"] != PARSER_VERSION:
        errors.append("parser version is invalid")
    if packet["tool"] not in TOOLS:
        errors.append("tool is invalid")
    if (
        not isinstance(packet["audit_id"], str)
        or not AUDIT_ID.fullmatch(packet["audit_id"])
    ):
        errors.append("audit-id is invalid")
    if (
        not isinstance(packet["session_id"], str)
        or not SAFE_ID.fullmatch(packet["session_id"])
    ):
        errors.append("session-id is invalid")
    if packet["not_goal_truth"] is not True:
        errors.append("packet must remain non-goal-truth")
    if packet["not_validation_evidence"] is not True:
        errors.append("packet must remain non-validation-evidence")
    if packet["capture_mode"] not in {
        "conversation_projection", "structured_telemetry", "unknown"
    }:
        errors.append("capture mode is invalid")
    if packet["capture_status"] not in {
        "complete", "partial", "quarantined", "failed"
    }:
        errors.append("capture status is invalid")
    if packet["integrity_status"] != "source_hash_only":
        errors.append("inspector packets require source-hash-only integrity")
    source = packet["source"]
    if (
        not isinstance(source, dict)
        or set(source) != {"path", "sha256", "size_bytes"}
        or not isinstance(source.get("path"), str)
        or not isinstance(source.get("sha256"), str)
        or not SHA.fullmatch(source["sha256"])
        or not isinstance(source.get("size_bytes"), int)
        or isinstance(source.get("size_bytes"), bool)
        or source["size_bytes"] < 0
    ):
        errors.append("source schema is invalid")
        source_relative = None
    else:
        source_relative = Path(source["path"])
        if (
            source_relative.is_absolute()
            or ".." in source_relative.parts
            or source_relative.as_posix() != source["path"]
        ):
            errors.append("source path is not canonical repository-relative")
    return source_relative


def _validate_binding(
    packet: dict[str, Any],
    errors: list[str],
) -> tuple[Any, Any]:
    binding = packet["binding"]
    if not isinstance(binding, dict) or "status" not in binding:
        errors.append("binding schema is invalid")
        binding_status = None
    else:
        binding_status = binding.get("status")
        if binding_status == "bound":
            if set(binding) != {"status", "cycle_id", "task_id"}:
                errors.append("bound packet requires cycle and task identifiers")
            elif any(
                not isinstance(binding.get(key), str)
                or not SAFE_ID.fullmatch(binding[key])
                for key in ("cycle_id", "task_id")
            ):
                errors.append("bound identifiers are invalid")
        elif binding_status in {"ambiguous", "unbound"}:
            if set(binding) != {"status"}:
                errors.append("non-bound packet cannot claim identifiers")
        else:
            errors.append("binding status is invalid")
    expected_consumable = (
        packet["capture_status"] == "complete" and binding_status == "bound"
    )
    if packet["consumable"] is not expected_consumable:
        errors.append("consumable state is inconsistent")
    expected_repair = (
        "none" if packet["capture_status"] == "complete" else "proposal_only"
    )
    if packet["repair_class"] != expected_repair:
        errors.append("repair class is inconsistent")
    if packet["auto_repair_allowed"] is not False:
        errors.append("auto repair exceeds derived metadata")
    return binding, binding_status


def _validate_observations(
    packet: dict[str, Any],
    source_relative: Path | None,
    errors: list[str],
) -> None:
    counts = packet["event_counts"]
    if (
        not isinstance(counts, dict)
        or set(counts) != COUNT_KEYS
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts.values()
        )
    ):
        errors.append("event counts are invalid")
    bounds = packet["timestamp_bounds"]
    if (
        not isinstance(bounds, dict)
        or set(bounds) != {"first", "last"}
        or any(
            value is not None
            and (
                not isinstance(value, str)
                or normalize_timestamp(value) != value
            )
            for value in bounds.values()
        )
        or ((bounds.get("first") is None) != (bounds.get("last") is None))
    ):
        errors.append("timestamp bounds are invalid")
    findings = packet["findings"]
    if not isinstance(findings, list):
        errors.append("findings are invalid")
    else:
        for item in findings:
            if (
                not isinstance(item, dict)
                or set(item)
                != {"code", "severity", "message", "evidence_class", "resolved"}
                or item.get("code") not in FINDINGS
            ):
                errors.append("finding schema is invalid")
                continue
            spec = FINDINGS[item["code"]]
            if (
                (item["severity"], item["evidence_class"], item["message"]) != spec
                or not isinstance(item["resolved"], bool)
                or item["evidence_class"]
                not in {"transcript_observation", "absence_unknown"}
            ):
                errors.append("finding content is invalid")
    evidence = packet["evidence_paths"]
    if (
        not isinstance(evidence, list)
        or not evidence
        or not all(isinstance(value, str) and value for value in evidence)
        or source_relative is not None
        and evidence[0] != source_relative.as_posix()
        or any(
            not value.startswith("sha256:")
            or not SHA.fullmatch(value.removeprefix("sha256:"))
            for value in evidence[1:]
        )
    ):
        errors.append("evidence paths or event hashes are invalid")
    if isinstance(counts, dict):
        expected_hashes = (
            0
            if packet["capture_status"] == "failed"
            and any(
                item.get("code") in {"source_too_large", "source_too_many_lines"}
                for item in packet["findings"]
            )
            else counts.get("total_lines")
        )
        if isinstance(expected_hashes, int) and len(evidence) - 1 != expected_hashes:
            errors.append("event-hash count is inconsistent")
    body = dict(packet)
    claimed = body.pop("audit_id")
    if claimed != derived_id("audit", body):
        errors.append("audit-id does not match packet content")


def _verify_source_projection(
    packet: dict[str, Any],
    root: Path,
    source_relative: Path | None,
    binding: Any,
    binding_status: Any,
    errors: list[str],
    verify_source: bool,
) -> None:
    source = packet["source"]
    if verify_source and source_relative is not None and isinstance(source, dict):
        try:
            path, relative = safe_file(root, source_relative)
            _, actual_hash, actual_size = read_snapshot(path, MAX_ALLOWED_BYTES)
            if (
                relative != source_relative
                or actual_hash != source["sha256"]
                or actual_size != source["size_bytes"]
            ):
                errors.append("source snapshot does not match packet")
            elif (
                packet["tool"] in TOOLS
                and isinstance(packet["session_id"], str)
                and SAFE_ID.fullmatch(packet["session_id"])
                and isinstance(binding, dict)
                and binding_status in {"bound", "ambiguous", "unbound"}
            ):
                expected = build_packet(
                    path,
                    relative,
                    tool=packet["tool"],
                    session_id=packet["session_id"],
                    cycle_id=(
                        binding.get("cycle_id")
                        if binding_status == "bound"
                        else "ambiguous-binding"
                        if binding_status == "ambiguous"
                        else None
                    ),
                    task_id=(binding.get("task_id") if binding_status == "bound" else None),
                    max_bytes=MAX_BYTES,
                )
                if expected != packet:
                    errors.append("packet does not match deterministic source projection")
        except AuditError as exc:
            errors.append(f"source verification failed: {exc}")


def validate_packet(
    packet: Any, root: Path, *, verify_source: bool = True
) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be an object"]
    if set(packet) != TOP_KEYS:
        return ["packet top-level schema is not closed"]
    source_relative = _validate_packet_header(packet, errors)
    binding, binding_status = _validate_binding(packet, errors)
    _validate_observations(packet, source_relative, errors)
    _verify_source_projection(
        packet,
        root,
        source_relative,
        binding,
        binding_status,
        errors,
        verify_source,
    )
    return errors
