#!/usr/bin/env python3
"""Validate and resolve bounded internal workflow mode profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any


FORMAT_VERSION = 1
PROFILE_KIND = "workflow_mode_profile"
REGISTRY_KIND = "workflow_mode_profile_registry"
RESOLUTION_KIND = "workflow_mode_resolution"
PROFILE_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

CAPTURE_MODES = {"off", "conversation_projection", "structured_telemetry"}
CONSUME_MODES = {"shadow", "advisory", "required"}
REACTION_MODES = {"observe", "proposal_only", "derived_metadata_only"}
ACTIVATION_SOURCES = {"default", "user_instruction", "caller_policy", "authority_record"}

CONSUME_RANK = {"shadow": 0, "advisory": 1, "required": 2}
REACTION_RANK = {"observe": 0, "proposal_only": 1, "derived_metadata_only": 2}

AUTO_REPAIR_ALLOWLIST = {
    ("rebuild_index", ".task/session_audit/index.json"),
}

PROFILE_FIELDS = {
    "format_version",
    "artifact_kind",
    "profile_id",
    "profile_version",
    "capture",
    "consume",
    "reaction",
    "allowed_repairs",
    "required_hook_signatures",
    "required_consumer_ids",
    "local_override",
    "not_goal_truth",
    "not_validation_evidence",
}
RESOLUTION_FIELDS = {
    "format_version",
    "artifact_kind",
    "status",
    "activation_source",
    "base_profile_id",
    "base_profile_hash",
    "override_profile_id",
    "override_profile_hash",
    "effective_profile",
    "effective_profile_hash",
    "allowed_effects",
    "repair_receipt_required",
    "not_goal_truth",
    "not_validation_evidence",
    "resolution_id",
}
DEFAULT_REGISTRY = Path(__file__).resolve().parents[2] / "references" / "mode-profiles.json"


class ModeProfileError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ModeProfileError(f"{field} must be a list of non-empty strings")
    normalized = [item.strip() for item in value]
    if len(normalized) != len(set(normalized)):
        raise ModeProfileError(f"{field} must not contain duplicates")
    return normalized


def _repair_pairs(value: Any) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        raise ModeProfileError("allowed_repairs must be a list")
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"operation", "target"}:
            raise ModeProfileError(f"allowed_repairs[{index}] must contain only operation and target")
        operation = item.get("operation")
        target = item.get("target")
        if not isinstance(operation, str) or not isinstance(target, str):
            raise ModeProfileError(f"allowed_repairs[{index}] values must be strings")
        pair = (operation, target)
        if pair not in AUTO_REPAIR_ALLOWLIST:
            raise ModeProfileError(f"repair is outside the exact allowlist: {operation} -> {target}")
        pairs.append(pair)
    if len(pairs) != len(set(pairs)):
        raise ModeProfileError("allowed_repairs must not contain duplicates")
    return pairs


def validate_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PROFILE_FIELDS:
        raise ModeProfileError("profile must use the closed workflow_mode_profile schema")
    if value.get("format_version") != FORMAT_VERSION or value.get("artifact_kind") != PROFILE_KIND:
        raise ModeProfileError("profile version or artifact kind is invalid")
    profile_id = value.get("profile_id")
    if not isinstance(profile_id, str) or not PROFILE_ID_RE.fullmatch(profile_id):
        raise ModeProfileError("profile_id must be lowercase hyphen-case")
    profile_version = value.get("profile_version")
    if not isinstance(profile_version, int) or isinstance(profile_version, bool) or profile_version < 1:
        raise ModeProfileError("profile_version must be a positive integer")
    if value.get("capture") not in CAPTURE_MODES:
        raise ModeProfileError("capture mode is invalid")
    if value.get("consume") not in CONSUME_MODES:
        raise ModeProfileError("consume mode is invalid")
    if value.get("reaction") not in REACTION_MODES:
        raise ModeProfileError("reaction mode is invalid")
    if not isinstance(value.get("local_override"), bool):
        raise ModeProfileError("local_override must be boolean")
    if value.get("not_goal_truth") is not True or value.get("not_validation_evidence") is not True:
        raise ModeProfileError("mode profiles must remain non-GT and non-validation-evidence")

    repairs = _repair_pairs(value.get("allowed_repairs"))
    hooks = _string_list(value.get("required_hook_signatures"), "required_hook_signatures")
    consumers = _string_list(value.get("required_consumer_ids"), "required_consumer_ids")
    if value["reaction"] == "derived_metadata_only" and not repairs:
        raise ModeProfileError("derived_metadata_only requires an allowlisted repair")
    if value["reaction"] != "derived_metadata_only" and repairs:
        raise ModeProfileError("only derived_metadata_only may name repairs")
    if value["capture"] == "off" and value["consume"] == "required":
        raise ModeProfileError("capture=off cannot require session consumption")

    normalized = dict(value)
    normalized["allowed_repairs"] = [
        {"operation": operation, "target": target} for operation, target in repairs
    ]
    normalized["required_hook_signatures"] = hooks
    normalized["required_consumer_ids"] = consumers
    return normalized


def load_profile(path: str | Path, profile_id: str | None = None) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(value, dict) and value.get("artifact_kind") == REGISTRY_KIND:
        if value.get("format_version") != FORMAT_VERSION or set(value) != {"format_version", "artifact_kind", "profiles"}:
            raise ModeProfileError("mode profile registry is malformed")
        profiles = value.get("profiles")
        if not isinstance(profiles, list):
            raise ModeProfileError("mode profile registry profiles must be a list")
        if not profile_id:
            raise ModeProfileError("profile_id is required when loading a registry")
        matches = [item for item in profiles if isinstance(item, dict) and item.get("profile_id") == profile_id]
        if len(matches) != 1:
            raise ModeProfileError("profile_id must resolve to exactly one registry profile")
        return validate_profile(matches[0])
    if profile_id and isinstance(value, dict) and value.get("profile_id") != profile_id:
        raise ModeProfileError("requested profile_id does not match the standalone profile")
    return validate_profile(value)


def _capture_reduction(base: str, override: str) -> bool:
    return override == base or override == "off"


def _validate_reducing_override(base: dict[str, Any], override: dict[str, Any]) -> None:
    if override["local_override"] is not True:
        raise ModeProfileError("override profile must set local_override=true")
    if not _capture_reduction(base["capture"], override["capture"]):
        raise ModeProfileError("local override cannot replace capture with another active capture capability")
    if CONSUME_RANK[override["consume"]] > CONSUME_RANK[base["consume"]]:
        raise ModeProfileError("local override cannot increase consumption authority")
    if REACTION_RANK[override["reaction"]] > REACTION_RANK[base["reaction"]]:
        raise ModeProfileError("local override cannot increase reaction authority")
    base_repairs = {(item["operation"], item["target"]) for item in base["allowed_repairs"]}
    override_repairs = {(item["operation"], item["target"]) for item in override["allowed_repairs"]}
    if not override_repairs <= base_repairs:
        raise ModeProfileError("local override cannot add repair capabilities")
    if not set(override["required_hook_signatures"]) >= set(base["required_hook_signatures"]):
        raise ModeProfileError("local override cannot remove required hook signatures")
    if not set(override["required_consumer_ids"]) >= set(base["required_consumer_ids"]):
        raise ModeProfileError("local override cannot remove required consumer probes")


def resolve_profile(
    base_value: Any,
    *,
    override_value: Any | None = None,
    activation_source: str = "default",
) -> dict[str, Any]:
    base = validate_profile(base_value)
    if base["local_override"] is True:
        raise ModeProfileError("base profile must be tracked and set local_override=false")
    if activation_source not in ACTIVATION_SOURCES:
        raise ModeProfileError("activation source is invalid; observations cannot self-activate a profile")
    effective = base
    override = None
    if override_value is not None:
        override = validate_profile(override_value)
        _validate_reducing_override(base, override)
        effective = override

    privileged = effective["consume"] == "required" or effective["reaction"] == "derived_metadata_only"
    if privileged and activation_source == "default":
        raise ModeProfileError("required consumption or repair needs user, caller, or authority activation")

    effects = {
        "capture_enabled": effective["capture"] != "off",
        "capture_mode": effective["capture"],
        "consumption_mode": effective["consume"],
        "reaction_mode": effective["reaction"],
        "proposal_generation_allowed": effective["reaction"] in {"proposal_only", "derived_metadata_only"},
        "derived_metadata_repair_allowed": effective["reaction"] == "derived_metadata_only",
        "semantic_mutation_allowed": False,
        "authority_expansion_allowed": False,
        "verdict_upgrade_allowed": False,
        "canonical_phase_change_allowed": False,
    }
    packet: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "artifact_kind": RESOLUTION_KIND,
        "status": "pass",
        "activation_source": activation_source,
        "base_profile_id": base["profile_id"],
        "base_profile_hash": content_hash(base),
        "override_profile_id": override["profile_id"] if override else None,
        "override_profile_hash": content_hash(override) if override else None,
        "effective_profile": effective,
        "effective_profile_hash": content_hash(effective),
        "allowed_effects": effects,
        "repair_receipt_required": effects["derived_metadata_repair_allowed"],
        "not_goal_truth": True,
        "not_validation_evidence": True,
    }
    packet["resolution_id"] = "mode-resolution-" + content_hash(packet)[:32]
    return packet


def validate_resolution(
    value: Any,
    *,
    registry_path: str | Path = DEFAULT_REGISTRY,
) -> dict[str, Any]:
    """Recompute a resolution from its tracked base and embedded reducing override."""

    if not isinstance(value, dict) or set(value) != RESOLUTION_FIELDS:
        raise ModeProfileError("resolution must use the closed workflow_mode_resolution schema")
    if (
        value.get("format_version") != FORMAT_VERSION
        or value.get("artifact_kind") != RESOLUTION_KIND
        or value.get("status") != "pass"
    ):
        raise ModeProfileError("resolution version, kind, or status is invalid")
    base_id = value.get("base_profile_id")
    if not isinstance(base_id, str) or not base_id:
        raise ModeProfileError("resolution base_profile_id is invalid")
    base = load_profile(registry_path, base_id)
    override_id = value.get("override_profile_id")
    effective = validate_profile(value.get("effective_profile"))
    override: dict[str, Any] | None = None
    if override_id is None:
        if value.get("override_profile_hash") is not None or effective != base:
            raise ModeProfileError("resolution without an override must equal its tracked base")
    else:
        if not isinstance(override_id, str) or effective.get("profile_id") != override_id:
            raise ModeProfileError("resolution override identity is invalid")
        override = effective
    expected = resolve_profile(
        base,
        override_value=override,
        activation_source=value.get("activation_source"),
    )
    if value != expected:
        raise ModeProfileError("resolution does not match deterministic profile resolution")
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate_cmd = commands.add_parser("validate")
    validate_cmd.add_argument("--profile", required=True)
    validate_cmd.add_argument("--profile-id")
    resolve_cmd = commands.add_parser("resolve")
    resolve_cmd.add_argument("--base", required=True)
    resolve_cmd.add_argument("--base-profile-id")
    resolve_cmd.add_argument("--override")
    resolve_cmd.add_argument("--override-profile-id")
    resolve_cmd.add_argument("--activation-source", choices=sorted(ACTIVATION_SOURCES), default="default")
    verify_cmd = commands.add_parser("verify-resolution")
    verify_cmd.add_argument("--resolution", required=True)
    verify_cmd.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            profile = load_profile(args.profile, args.profile_id)
            output = {"status": "pass", "profile": profile, "profile_hash": content_hash(profile)}
        elif args.command == "resolve":
            base = load_profile(args.base, args.base_profile_id)
            override = load_profile(args.override, args.override_profile_id) if args.override else None
            output = resolve_profile(base, override_value=override, activation_source=args.activation_source)
        else:
            resolution = json.loads(Path(args.resolution).read_text(encoding="utf-8"))
            output = {
                "status": "pass",
                "resolution": validate_resolution(
                    resolution,
                    registry_path=args.registry,
                ),
            }
    except (OSError, json.JSONDecodeError, ModeProfileError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
