"""Discover and hand off repository-owned workflow adapters without loading them."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Sequence


SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REQUIRED_PATH_FIELDS = (("implementation_path", "implementation_sha256"),)
OPTIONAL_PATH_FIELDS = (
    ("legacy_compatibility_path", "legacy_compatibility_sha256"),
    ("renderer_path", "renderer_sha256"),
    ("decision_identity_validator_path", "decision_identity_validator_sha256"),
    ("authority_projection_path", "authority_projection_sha256"),
)
COMPONENT_PATH_FIELDS = REQUIRED_PATH_FIELDS + OPTIONAL_PATH_FIELDS


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _object_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_regular_file(root: Path, raw: str) -> tuple[Path, str]:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    lexical = candidate.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError as exc:
        raise ValueError("adapter component escapes repository root") from exc
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("adapter component crosses a symlink")
    resolved = lexical.resolve(strict=True)
    if not stat.S_ISREG(resolved.lstat().st_mode):
        raise ValueError("adapter component is not a regular file")
    return resolved, resolved.relative_to(root).as_posix()


def _component(root: Path, raw: Any) -> tuple[str | None, str | None, str | None]:
    if not isinstance(raw, str) or not raw.strip():
        return None, None, "path_missing"
    try:
        path, relative = _safe_regular_file(root, raw)
    except (OSError, ValueError) as exc:
        return raw, None, type(exc).__name__
    return relative, _file_sha256(path), None


def _adapter_row(root: Path, manifest_path: Path) -> dict[str, Any]:
    relative_manifest = manifest_path.relative_to(root).as_posix()
    base: dict[str, Any] = {
        "manifest_path": relative_manifest,
        "manifest_sha256": _file_sha256(manifest_path),
        "static_validation": {"status": "block", "errors": []},
    }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        base["static_validation"]["errors"].append(
            f"manifest_load_failed:{type(exc).__name__}"
        )
        return base
    if not isinstance(manifest, dict):
        base["static_validation"]["errors"].append("manifest_not_object")
        return base
    adapter_id = str(manifest.get("adapter_id") or "").strip()
    hooks = manifest.get("hooks")
    phase_consumers = manifest.get("phase_consumers")
    phase_hooks = manifest.get("phase_hooks")
    required_consumers = manifest.get("required_consumer_ids")
    base.update(
        {
            "adapter_id": adapter_id,
            "status": str(manifest.get("status") or "unknown"),
            "not_goal_truth": manifest.get("not_goal_truth") is True,
            "not_validation_evidence": manifest.get("not_validation_evidence") is True,
            "required_consumer_ids": required_consumers
            if isinstance(required_consumers, list)
            else [],
            "phase_consumer_map": phase_consumers
            if isinstance(phase_consumers, dict)
            else {},
            "phase_hook_map": phase_hooks if isinstance(phase_hooks, dict) else {},
            "hooks": hooks if isinstance(hooks, list) else [],
        }
    )
    errors = base["static_validation"]["errors"]
    if not adapter_id:
        errors.append("adapter_id_missing")
    if manifest.get("format_version") != 2:
        errors.append("unsupported_manifest_format")
    if (
        not isinstance(hooks, list)
        or any(not isinstance(item, str) for item in hooks)
        or len(set(hooks)) != len(hooks)
    ):
        errors.append("hook_registry_invalid")
    if (
        not isinstance(required_consumers, list)
        or any(
            not isinstance(item, str) or not item.strip() for item in required_consumers
        )
        or len(set(required_consumers)) != len(required_consumers)
    ):
        errors.append("required_consumer_registry_invalid")
    if not isinstance(phase_consumers, dict) or not isinstance(phase_hooks, dict):
        errors.append("phase_registry_invalid")
    elif set(phase_consumers) != set(phase_hooks):
        errors.append("phase_registry_divergence")
    else:
        if any(
            not isinstance(names, list)
            or any(not isinstance(name, str) or not name.strip() for name in names)
            or len(set(names)) != len(names)
            for names in phase_consumers.values()
        ):
            errors.append("phase_consumer_registry_invalid")
        elif isinstance(required_consumers, list) and any(
            name not in required_consumers
            for names in phase_consumers.values()
            for name in names
        ):
            errors.append("phase_consumer_undeclared")
        if any(
            not isinstance(names, list)
            or any(not isinstance(name, str) or not name.strip() for name in names)
            or len(set(names)) != len(names)
            for names in phase_hooks.values()
        ):
            errors.append("phase_hook_registry_invalid")
        elif isinstance(hooks, list) and any(
            name not in hooks for names in phase_hooks.values() for name in names
        ):
            errors.append("phase_hook_undeclared")
    for path_field, hash_field in REQUIRED_PATH_FIELDS:
        relative, digest, error = _component(root, manifest.get(path_field))
        base[path_field] = relative
        base[hash_field] = digest
        if error:
            errors.append(f"{path_field}:{error}")
    for path_field, hash_field in OPTIONAL_PATH_FIELDS:
        raw = manifest.get(path_field)
        if raw in (None, ""):
            base[path_field] = None
            base[hash_field] = None
            continue
        relative, digest, error = _component(root, raw)
        base[path_field] = relative
        base[hash_field] = digest
        if error:
            errors.append(f"{path_field}:{error}")
    basis = {
        "adapter_id": adapter_id,
        "manifest_sha256": base["manifest_sha256"],
        "implementation_sha256": base.get("implementation_sha256"),
        "legacy_compatibility_sha256": base.get("legacy_compatibility_sha256"),
        "renderer_sha256": base.get("renderer_sha256"),
        "decision_identity_validator_sha256": base.get(
            "decision_identity_validator_sha256"
        ),
        "phase_consumer_map": base["phase_consumer_map"],
        "phase_hook_map": base["phase_hook_map"],
    }
    if "authority_projection_path" in manifest:
        basis["authority_projection_sha256"] = base.get("authority_projection_sha256")
    base["adapter_revision_sha256"] = _object_sha256(basis)
    base["static_validation"]["status"] = "pass" if not errors else "block"
    return base


def scan_repo_skill_adapters(
    root: str | Path, *, cycle_id: str = "unknown"
) -> dict[str, Any]:
    repo_root = Path(root).expanduser().resolve(strict=True)
    skill_root = repo_root / ".codex" / "skills"
    manifests: list[Path] = []
    if skill_root.is_dir() and not skill_root.is_symlink():
        manifests = sorted(
            path
            for path in skill_root.glob("*/adapter.manifest.json")
            if path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        )
    rows = [_adapter_row(repo_root, path) for path in manifests]
    blockers = [
        {
            "code": "repo_skill_adapter_static_validation_failed",
            "adapter_id": row.get("adapter_id"),
            "errors": row["static_validation"]["errors"],
        }
        for row in rows
        if row["static_validation"]["status"] != "pass"
    ]
    packet = {
        "schema_version": 2,
        "artifact_kind": "repo_skill_adapter_scan_packet",
        "step": "repo_skill_adapter_scan",
        "cycle_id": cycle_id,
        "adapter_scan_status": "pass" if not blockers else "block",
        "adapter_count": len(rows),
        "repo_skill_adapter_packet": {
            "schema_version": 2,
            "adapters": rows,
            "not_goal_truth": True,
            "not_validation_evidence": True,
        },
        "blockers": blockers,
        "evidence_paths": [row["manifest_path"] for row in rows],
    }
    packet["scan_packet_sha256"] = _object_sha256(packet)
    return packet


def _load_scan(root: Path, raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        path, _ = _safe_regular_file(root, raw)
        value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("adapter scan packet is not an object")
    return value


def registered_adapter_handoff(
    root: str | Path,
    scan_packet: dict[str, Any],
    *,
    phase: str,
    consumer_id: str,
) -> dict[str, Any]:
    repo_root = Path(root).expanduser().resolve(strict=True)
    container = scan_packet.get("repo_skill_adapter_packet")
    rows = container.get("adapters") if isinstance(container, dict) else None
    if not isinstance(rows, list):
        return {
            "status": "invalid_scan",
            "adapter_registered": False,
            "adapter_loaded": False,
            "classification": "adapter_scan_contract_defect",
        }
    active_rows = [
        row for row in rows if isinstance(row, dict) and row.get("status") == "active"
    ]
    malformed = [
        row
        for row in active_rows
        if not isinstance(row.get("phase_consumer_map"), dict)
        or any(
            not isinstance(value, list) for value in row["phase_consumer_map"].values()
        )
    ]
    if malformed:
        return {
            "status": "invalid_scan",
            "adapter_registered": True,
            "adapter_loaded": False,
            "classification": "adapter_scan_contract_defect",
        }
    matches = [
        row
        for row in active_rows
        if consumer_id in (row.get("phase_consumer_map") or {}).get(phase, [])
    ]
    if not matches:
        return {
            "status": "not_registered",
            "adapter_registered": False,
            "adapter_loaded": False,
            "classification": "adapter_absent",
        }
    if len(matches) != 1:
        return {
            "status": "ambiguous",
            "adapter_registered": True,
            "adapter_loaded": False,
            "classification": "adapter_wiring_defect",
        }
    row = matches[0]
    stale: list[str] = []
    for path_field, hash_field in COMPONENT_PATH_FIELDS:
        if row.get(path_field) is None and row.get(hash_field) is None:
            continue
        try:
            path, relative = _safe_regular_file(
                repo_root, str(row.get(path_field) or "")
            )
        except (OSError, ValueError):
            stale.append(path_field)
            continue
        if relative != row.get(path_field) or _file_sha256(path) != row.get(hash_field):
            stale.append(path_field)
    try:
        manifest, relative_manifest = _safe_regular_file(
            repo_root, str(row.get("manifest_path") or "")
        )
        if relative_manifest != row.get("manifest_path") or _file_sha256(
            manifest
        ) != row.get("manifest_sha256"):
            stale.append("manifest_path")
        current_row = _adapter_row(repo_root, manifest)
        for field in (
            "adapter_id",
            "status",
            "implementation_path",
            "implementation_sha256",
            "legacy_compatibility_path",
            "legacy_compatibility_sha256",
            "renderer_path",
            "renderer_sha256",
            "decision_identity_validator_path",
            "decision_identity_validator_sha256",
            "authority_projection_path",
            "authority_projection_sha256",
            "phase_consumer_map",
            "phase_hook_map",
            "adapter_revision_sha256",
        ):
            if current_row.get(field) != row.get(field):
                stale.append(field)
    except (OSError, ValueError):
        stale.append("manifest_path")
    ready = bool(row.get("static_validation", {}).get("status") == "pass" and not stale)
    return {
        "status": "ready" if ready else "registered_unavailable",
        "adapter_id": row.get("adapter_id"),
        "adapter_registered": True,
        "adapter_loaded": False,
        "classification": "registered_adapter_ready"
        if ready
        else "adapter_wiring_defect",
        "implementation_path": row.get("implementation_path"),
        "implementation_sha256": row.get("implementation_sha256"),
        "legacy_compatibility_path": row.get("legacy_compatibility_path"),
        "legacy_compatibility_sha256": row.get("legacy_compatibility_sha256"),
        "renderer_path": row.get("renderer_path"),
        "renderer_sha256": row.get("renderer_sha256"),
        "decision_identity_validator_path": row.get("decision_identity_validator_path"),
        "decision_identity_validator_sha256": row.get(
            "decision_identity_validator_sha256"
        ),
        "authority_projection_path": row.get("authority_projection_path"),
        "authority_projection_sha256": row.get("authority_projection_sha256"),
        "manifest_path": row.get("manifest_path"),
        "manifest_sha256": row.get("manifest_sha256"),
        "adapter_revision_sha256": row.get("adapter_revision_sha256"),
        "phase": phase,
        "consumer_id": consumer_id,
        "stale_components": sorted(set(stale)),
        "authority_granted": False,
    }


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--root", default=".")
    scan.add_argument("--cycle-id", default="unknown")
    scan.add_argument("--output")
    handoff = commands.add_parser("handoff")
    handoff.add_argument("--root", default=".")
    handoff.add_argument("--scan-json", required=True)
    handoff.add_argument("--phase", required=True)
    handoff.add_argument("--consumer-id", required=True)
    handoff.add_argument("--output")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.root).expanduser().resolve(strict=True)
    if args.command == "scan":
        result = scan_repo_skill_adapters(root, cycle_id=args.cycle_id)
    else:
        result = registered_adapter_handoff(
            root,
            _load_scan(root, args.scan_json),
            phase=args.phase,
            consumer_id=args.consumer_id,
        )
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = root / output
        _write(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return (
        0
        if result.get("status")
        not in {"invalid_scan", "ambiguous", "registered_unavailable"}
        else 2
    )


__all__ = (
    "main",
    "registered_adapter_handoff",
    "scan_repo_skill_adapters",
)
