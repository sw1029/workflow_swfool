from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import resolve_workspace_path
from .canonical import sha256_file
from .contracts import CAPABILITY_RE
from .contracts import DECISION_CLASSES
from .contracts import MUTATION_CLASSES
from .contracts import REVERSIBILITY
from .contracts import RISK_TIERS
from .contracts import SOURCE_RANKS


MANIFEST_KEYS = {
    "schema_version",
    "manifest_kind",
    "skill_id",
    "skill_version",
    "operations",
}
OPERATION_KEYS = {
    "operation_id",
    "operation_version",
    "mutation_class",
    "required_capabilities",
    "source_rank_floor",
    "risk_floor",
    "decision_class",
    "effect_classes",
    "data_classes",
    "reversibility",
    "subject_kinds",
    "authority_applicability",
    "authorization_mechanism",
}
APPLICABILITY = {"required", "conditional", "none"}
AUTHORIZATION_MECHANISMS = {
    "none",
    "grant",
    "typed_source_approval",
    "bound_lifecycle_artifact",
}


def default_skills_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _strings(value: Any, label: str, *, capability: bool = False) -> list[str]:
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{label} must be a non-empty list.")
    normalized = sorted(set(str(item) for item in value))
    if len(normalized) != len(value) or any(
        not item or "*" in item for item in normalized
    ):
        raise SystemExit(f"{label} must contain unique exact values without wildcards.")
    if capability and any(not CAPABILITY_RE.fullmatch(item) for item in normalized):
        raise SystemExit(f"{label} contains an invalid capability namespace.")
    return normalized


def validate_manifest(value: dict[str, Any], source: Path) -> dict[str, Any]:
    extra = sorted(set(value) - MANIFEST_KEYS)
    missing = sorted(MANIFEST_KEYS - set(value))
    if extra or missing:
        raise SystemExit(
            f"Operation manifest {source} has unknown={extra} missing={missing}."
        )
    if value["schema_version"] != 2 or value["manifest_kind"] != "authority_operations":
        raise SystemExit(
            f"Operation manifest {source} requires schema_version=2 and manifest_kind=authority_operations."
        )
    skill_id = str(value["skill_id"] or "")
    skill_version = str(value["skill_version"] or "")
    if not skill_id or not skill_version:
        raise SystemExit(
            f"Operation manifest {source} requires skill_id and skill_version."
        )
    operations = value["operations"]
    if not isinstance(operations, list) or not operations:
        raise SystemExit(f"Operation manifest {source} requires operations.")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, operation in enumerate(operations):
        label = f"{source}:operations[{index}]"
        if not isinstance(operation, dict):
            raise SystemExit(f"{label} must be an object.")
        extra = sorted(set(operation) - OPERATION_KEYS)
        missing = sorted(OPERATION_KEYS - set(operation))
        if extra or missing:
            raise SystemExit(f"{label} has unknown={extra} missing={missing}.")
        operation_id = str(operation["operation_id"] or "")
        operation_version = str(operation["operation_version"] or "")
        key = (operation_id, operation_version)
        if not all(key) or key in seen:
            raise SystemExit(f"{label} has a missing or duplicate operation identity.")
        seen.add(key)
        mutation = str(operation["mutation_class"])
        rank = str(operation["source_rank_floor"])
        risk = str(operation["risk_floor"])
        decision_class = str(operation["decision_class"])
        reversibility = str(operation["reversibility"])
        applicability = str(operation["authority_applicability"])
        mechanism = str(operation["authorization_mechanism"])
        if (
            mutation not in MUTATION_CLASSES
            or rank not in SOURCE_RANKS
            or risk not in RISK_TIERS
        ):
            raise SystemExit(f"{label} contains an invalid mutation/rank/risk enum.")
        if decision_class not in DECISION_CLASSES or reversibility not in REVERSIBILITY:
            raise SystemExit(
                f"{label} contains an invalid decision/reversibility enum."
            )
        if applicability not in APPLICABILITY:
            raise SystemExit(f"{label} contains an invalid authority_applicability.")
        if mechanism not in AUTHORIZATION_MECHANISMS:
            raise SystemExit(f"{label} contains an invalid authorization_mechanism.")
        if (applicability == "none") != (mechanism == "none"):
            raise SystemExit(
                f"{label} applicability and authorization mechanism conflict."
            )
        normalized.append(
            {
                "operation_id": operation_id,
                "operation_version": operation_version,
                "mutation_class": mutation,
                "required_capabilities": _strings(
                    operation["required_capabilities"],
                    f"{label}.required_capabilities",
                    capability=True,
                ),
                "source_rank_floor": rank,
                "risk_floor": risk,
                "decision_class": decision_class,
                "effect_classes": _strings(
                    operation["effect_classes"], f"{label}.effect_classes"
                ),
                "data_classes": _strings(
                    operation["data_classes"], f"{label}.data_classes"
                ),
                "reversibility": reversibility,
                "subject_kinds": _strings(
                    operation["subject_kinds"], f"{label}.subject_kinds"
                ),
                "authority_applicability": applicability,
                "authorization_mechanism": mechanism,
            }
        )
    return {
        "schema_version": 2,
        "manifest_kind": "authority_operations",
        "skill_id": skill_id,
        "skill_version": skill_version,
        "operations": sorted(
            normalized,
            key=lambda item: (item["operation_id"], item["operation_version"]),
        ),
    }


def load_operation(
    skill_id: str,
    skill_version: str,
    operation_id: str,
    operation_version: str,
    *,
    skills_root: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    root = (skills_root or default_skills_root()).resolve()
    path = resolve_workspace_path(
        root,
        f"{skill_id}/authority.operations.json",
        "operation manifest",
        must_exist=False,
    )
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"Operation manifest {path} is unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"Operation manifest {path} must be an object.")
    manifest = validate_manifest(raw, path)
    if manifest["skill_id"] != skill_id or manifest["skill_version"] != skill_version:
        return None, {
            "ref": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
        }
    binding = {
        "ref": path.relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }
    for operation in manifest["operations"]:
        if (
            operation["operation_id"] == operation_id
            and operation["operation_version"] == operation_version
        ):
            return operation, binding
    return None, binding
