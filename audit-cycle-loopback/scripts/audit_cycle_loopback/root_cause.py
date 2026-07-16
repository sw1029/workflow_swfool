from __future__ import annotations

from typing import Any
from pathlib import Path
import fnmatch
import re
from . import families as _families
from . import outcome as _outcome
from . import values as _values
from . import vectors as _vectors


def normalize_root_cause_equivalence_slug(value: Any) -> str:
    slug = _outcome.normalize_root_cause_slug(value)
    slug = re.sub(r"([_.:/-])v(?:nnn|\d+)$", "", slug)
    slug = re.sub(r"([_.:/-])(?:variant|facet|phase|stage|case|mode|fix|repair)$", "", slug)
    return slug.strip("-_.:/|") or "unknown_root_cause"

def normalize_root_cause_hypotheses(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("root_cause_hypotheses", "hypotheses", "items", "root_causes"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
        else:
            value = [value]
    if isinstance(value, str):
        value = [{"hypothesized_root_cause": value}]
    if not isinstance(value, list):
        return []
    hypotheses: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            item = {"hypothesized_root_cause": item}
        if not isinstance(item, dict):
            continue
        raw = item.get("hypothesized_root_cause") or item.get("root_cause") or item.get("root_key") or item.get("root")
        slug = _outcome.normalize_root_cause_slug(raw)
        if slug == "unknown_root_cause":
            continue
        normalized = dict(item)
        normalized["hypothesized_root_cause"] = slug
        hypotheses.append(normalized)
    return hypotheses


ROOT_CAUSE_PROVENANCE_KEYS = (
    "provenance_refs",
    "provenance",
    "advice_id",
    "advice_path",
    "issue_id",
    "issue_path",
    "run_id",
    "run_path",
    "run_evidence_path",
    "evidence_path",
    "evidence_paths",
    "source_evidence_path",
    "source_evidence_paths",
)


def normalize_repo_owned_source_roots(value: Any) -> list[str]:
    if isinstance(value, dict):
        for key in ("repo_owned_source_roots", "source_roots", "roots", "patterns"):
            if key in value:
                value = value.get(key)
                break
        else:
            return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    roots: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        normalized = text.replace("\\", "/").strip()
        if normalized not in roots:
            roots.append(normalized)
    return roots[:50]

def root_cause_provenance_refs(entry: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ROOT_CAUSE_PROVENANCE_KEYS:
        value = entry.get(key)
        if isinstance(value, list):
            refs.extend(str(item).strip() for item in value if item is not None and str(item).strip())
        elif isinstance(value, dict):
            refs.extend(str(item).strip() for item in value.values() if item is not None and str(item).strip())
        elif value is not None and str(value).strip():
            refs.append(str(value).strip())
    return sorted(set(refs))[:12]

def clean_provenance_path_ref(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("file://"):
        text = text[len("file://") :]
    match = re.match(r"^(.*?):[0-9]+(?::[0-9]+)?$", text)
    if match:
        text = match.group(1)
    return text.replace("\\", "/").strip()

def repo_owned_provenance_refs(root: Path | None, refs: list[str], source_roots: list[str]) -> list[str]:
    if root is None or not source_roots:
        return []
    root_resolved = root.resolve()
    owned: list[str] = []
    for ref in refs:
        cleaned = clean_provenance_path_ref(ref)
        if not cleaned:
            continue
        ref_path = Path(cleaned)
        if not ref_path.is_absolute():
            ref_path = root_resolved / ref_path
        try:
            rel = ref_path.resolve().relative_to(root_resolved).as_posix()
        except (OSError, ValueError):
            rel = cleaned.lstrip("./")
        for raw_pattern in source_roots:
            pattern = raw_pattern.strip().replace("\\", "/").strip("/")
            if not pattern:
                continue
            zero_depth_pattern = pattern.replace("/**/", "/")
            if (
                rel == pattern
                or rel.startswith(pattern + "/")
                or fnmatch.fnmatch(rel, pattern)
                or (zero_depth_pattern != pattern and fnmatch.fnmatch(rel, zero_depth_pattern))
                or fnmatch.fnmatch(rel, pattern.rstrip("/") + "/**")
            ):
                owned.append(ref)
                break
    return sorted(set(owned))[:12]

def root_cause_actionability(
    entry: dict[str, Any],
    *,
    root: Path | None = None,
    repo_owned_source_roots: list[str] | None = None,
) -> dict[str, Any]:
    structural_fields = ("local", "bounded", "provider_free", "in_scope", "authority_allowed")
    structural = all(_values.bool_value(entry.get(field)) for field in structural_fields)
    asserted = _values.bool_value(entry.get("actionable")) or _values.bool_value(entry.get("root_cause_actionable"))
    provenance = root_cause_provenance_refs(entry)
    explicit_owned_refs = _vectors.string_list(entry.get("repo_owned_source_refs"))
    computed_owned_refs = repo_owned_provenance_refs(root, provenance, repo_owned_source_roots or [])
    owned_refs = sorted(set(explicit_owned_refs + computed_owned_refs))[:12]
    provenance_derived = bool(owned_refs)
    actionable = structural or provenance_derived or (asserted and bool(provenance))
    if actionable:
        status = "verified"
    elif asserted:
        status = "unverified"
    else:
        status = "not_actionable"
    basis = {
        "asserted_actionable": asserted,
        "structural_actionable": structural,
        "provenance_derived_actionable": provenance_derived,
        "repo_owned_source_ref_count": len(owned_refs),
        "repo_owned_source_refs": owned_refs,
        "provenance_ref_count": len(provenance),
        "required_structural_fields": list(structural_fields),
    }
    return {"actionable": actionable, "status": status, "basis": basis, "provenance_refs": provenance}

def harden_repo_owned_actionability(
    entry: dict[str, Any],
    *,
    root: Path,
    repo_owned_source_roots: list[str],
) -> dict[str, Any]:
    actionability = root_cause_actionability(entry, root=root, repo_owned_source_roots=repo_owned_source_roots)
    owned_refs = _vectors.string_list(actionability.get("basis", {}).get("repo_owned_source_refs"))
    if not owned_refs:
        return actionability
    rejected: dict[str, Any] = {}
    for field in ("local", "in_scope", "actionable"):
        if not _values.bool_value(entry.get(field)):
            rejected[field] = entry.get(field)
        entry[field] = True
    entry["repo_owned_source_refs"] = owned_refs
    if rejected:
        entry["self_report_rejected_fields"] = rejected
    return root_cause_actionability(entry, root=root, repo_owned_source_roots=repo_owned_source_roots)

def root_cause_actionable(entry: dict[str, Any]) -> bool:
    return bool(root_cause_actionability(entry)["actionable"])

def same_root_cause_scope(row: dict[str, Any], family_key: str, root_key: str, root_family_key: str) -> bool:
    if str(row.get("family_key") or "") == family_key:
        return True
    if root_key and str(row.get("root_key") or "") == root_key:
        return True
    if root_family_key and str(row.get("root_family_key") or row.get("blocker_root_family") or "") == root_family_key:
        return True
    return False

def root_cause_target_surface(row: dict[str, Any]) -> str:
    return _families.normalize_root_family_key(
        row.get("target_surface")
        or row.get("blocker_signature")
        or row.get("root_key")
        or row.get("root_family_key")
        or row.get("family_key")
        or "unknown_surface"
    )

def root_cause_delta_class(row: dict[str, Any]) -> str:
    return _families.normalize_root_family_key(row.get("observed_delta_class") or "unknown_delta")

def root_cause_distinct_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_root_cause_equivalence_slug(row.get("hypothesized_root_cause")),
        root_cause_target_surface(row),
        root_cause_delta_class(row),
    )

def equivalent_root_cause(row: dict[str, Any], attempted_row: dict[str, Any]) -> bool:
    row_key = root_cause_distinct_key(row)
    attempted_key = root_cause_distinct_key(attempted_row)
    if row_key == attempted_key:
        return True
    return False

def root_cause_attempt_weight(row: dict[str, Any], field: str, default: int = 0) -> int:
    value = row.get(field)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str) and value.strip().isdigit():
        return max(0, int(value.strip()))
    return default

def root_cause_exhaustion_state(
    rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
    budget: int | None,
) -> dict[str, Any]:
    scoped = [row for row in rows if same_root_cause_scope(row, family_key, root_key, root_family_key)]
    attempted_rows = [row for row in scoped if _values.bool_value(row.get("repair_attempted"))]
    positive_attempts = [
        row for row in attempted_rows if _values.bool_value(row.get("terminal_outcome_changed"))
    ]
    vacuous_rows = [
        row for row in attempted_rows if not _values.bool_value(row.get("terminal_outcome_changed"))
    ]
    vacuous_attempt_count = sum(root_cause_attempt_weight(row, "vacuous_attempt_count", 1) for row in vacuous_rows)
    streak = 0
    for row in reversed(scoped):
        if not _values.bool_value(row.get("repair_attempted")):
            continue
        if _values.bool_value(row.get("terminal_outcome_changed")):
            break
        streak += root_cause_attempt_weight(row, "vacuous_attempt_count", 1)
    budget_contract = _values.budget_evaluation(
        "root_cause_repair_attempts",
        budget,
        source="caller_or_repository_config",
    )
    budget_limit = _values.budget_value(budget_contract)
    exhausted = (
        budget_limit is not None
        and vacuous_attempt_count >= budget_limit
        and not positive_attempts
    )
    return {
        "hypothesis_exhausted": exhausted,
        "untried_promotion_budget": budget_limit,
        "budget_evaluation": budget_contract,
        "budget_evaluation_status": budget_contract["budget_evaluation_status"],
        "vacuous_untried_attempt_count": vacuous_attempt_count,
        "vacuous_untried_streak": streak,
        "successful_untried_attempt_count": len(positive_attempts),
        "attempted_hypothesis_count": len(attempted_rows),
    }

def root_cause_hypothesis_gate(
    rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
    budget: int | None,
    *,
    root: Path | None = None,
    repo_owned_source_roots: list[str] | None = None,
) -> dict[str, Any]:
    latest_by_root: dict[str, dict[str, Any]] = {}
    attempted_rows: list[dict[str, Any]] = []
    for row in rows:
        if not same_root_cause_scope(row, family_key, root_key, root_family_key):
            continue
        hypothesis_root = _outcome.normalize_root_cause_slug(row.get("hypothesized_root_cause"))
        latest_by_root[hypothesis_root] = row
        if _values.bool_value(row.get("repair_attempted")):
            attempted_rows.append(row)
    untried = []
    unverified = []
    duplicates = []
    for hypothesis_root, row in sorted(latest_by_root.items()):
        actionability = root_cause_actionability(
            row,
            root=root,
            repo_owned_source_roots=repo_owned_source_roots,
        )
        if not actionability["actionable"]:
            if actionability["status"] == "unverified":
                unverified.append(
                    {
                        "family_key": row.get("family_key"),
                        "root_key": row.get("root_key"),
                        "root_family_key": row.get("root_family_key"),
                        "hypothesized_root_cause": hypothesis_root,
                        "actionability_status": "unverified",
                        "actionability_basis": actionability["basis"],
                    }
                )
            continue
        duplicate = next((attempted for attempted in attempted_rows if equivalent_root_cause(row, attempted)), None)
        if duplicate is not None:
            duplicates.append(
                {
                    "family_key": row.get("family_key"),
                    "root_key": row.get("root_key"),
                    "root_family_key": row.get("root_family_key"),
                    "hypothesized_root_cause": hypothesis_root,
                    "attempted_equivalent": _outcome.normalize_root_cause_slug(duplicate.get("hypothesized_root_cause")),
                    "target_surface": root_cause_target_surface(row),
                    "observed_delta_class": row.get("observed_delta_class"),
                }
            )
            continue
        untried.append(
            {
                "family_key": row.get("family_key"),
                "root_key": row.get("root_key"),
                "root_family_key": row.get("root_family_key"),
                "hypothesized_root_cause": hypothesis_root,
                "repair_attempted": False,
                "repair_task_id": row.get("repair_task_id"),
                "terminal_outcome_changed": _values.bool_value(row.get("terminal_outcome_changed")),
                "observed_delta_class": row.get("observed_delta_class"),
                "target_surface": root_cause_target_surface(row),
                "cycle_id": row.get("cycle_id"),
                "actionable": True,
                "actionability_status": "verified",
                "actionability_basis": actionability["basis"],
                "provenance_refs": actionability["provenance_refs"],
            }
        )
    exhaustion = root_cause_exhaustion_state(rows, family_key, root_key, root_family_key, budget)
    if exhaustion["hypothesis_exhausted"]:
        untried = []
    return {
        **exhaustion,
        "untried_root_cause_hypotheses": untried,
        "root_cause_unverified_hypotheses": unverified,
        "root_cause_duplicate_hypotheses": duplicates,
    }

def untried_root_cause_hypotheses(
    rows: list[dict[str, Any]],
    family_key: str,
    root_key: str,
    root_family_key: str,
    *,
    root: Path | None = None,
    repo_owned_source_roots: list[str] | None = None,
) -> list[dict[str, Any]]:
    return root_cause_hypothesis_gate(
        rows,
        family_key,
        root_key,
        root_family_key,
        None,
        root=root,
        repo_owned_source_roots=repo_owned_source_roots,
    )["untried_root_cause_hypotheses"]
