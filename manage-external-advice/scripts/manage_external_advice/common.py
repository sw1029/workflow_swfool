"""Shared deterministic parsing, hashing, and trust-anchor helpers."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .contracts import (
    FINGERPRINT_CLAIM_RE,
    ROOT_CAUSE_CLAIM_RE,
    ROOT_CAUSE_LEDGER_REL_PATH,
)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def slugify(value: str, fallback: str = "advice") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return (slug or fallback)[:48]


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
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
    return rows


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present"}
    return False


def normalize_root_cause_slug(value: Any) -> str:
    raw = str(value or "").strip().lower()
    raw = re.sub(r"\bcycle-\d{8}-\d{6}\b", "cycle", raw)
    raw = re.sub(r"\b20\d{6}(?:[-_]\d{2,6})?\b", "date", raw)
    raw = re.sub(r"\b\d{8,14}\b", "date", raw)
    raw = re.sub(r"\b[0-9a-f]{7,40}\b", "hash", raw)
    raw = re.sub(r"\bv\d+\b|[-_]v\d+\b", "vnnn", raw)
    raw = re.sub(r"[^a-z0-9가-힣_.:/-]+", "-", raw)
    raw = re.sub(r"([_.:/-])v(?:nnn|\d+)$", "", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-_.:/|")
    return raw or "unknown_root_cause"


def extract_root_cause_claims(text: str) -> list[str]:
    claims = {
        normalize_root_cause_slug(match.group(1))
        for match in ROOT_CAUSE_CLAIM_RE.finditer(text)
    }
    for match in re.finditer(
        r"root_cause_claims\s*:\s*(\[[^\]\n]*\])", text, re.IGNORECASE
    ):
        try:
            loaded = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, list):
            claims.update(normalize_root_cause_slug(item) for item in loaded)
    return sorted(claim for claim in claims if claim != "unknown_root_cause")


def dead_root_cause_rows(
    root: Path, raw_path: str | None = None
) -> list[dict[str, Any]]:
    path = Path(raw_path or ROOT_CAUSE_LEDGER_REL_PATH)
    if not path.is_absolute():
        path = root / path
    dead: list[dict[str, Any]] = []
    for row in read_jsonl(path):
        if bool_value(row.get("repair_attempted")) and not bool_value(
            row.get("terminal_outcome_changed")
        ):
            dead.append(
                {
                    "hypothesized_root_cause": normalize_root_cause_slug(
                        row.get("hypothesized_root_cause")
                    ),
                    "family_key": row.get("family_key"),
                    "root_key": row.get("root_key"),
                    "root_family_key": row.get("root_family_key"),
                    "cycle_id": row.get("cycle_id"),
                    "path": rel_path(root, path),
                }
            )
    return dead


def load_json_value(root: Path, raw: str | None) -> Any:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root / path
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def first_fingerprint_value(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in (
            "current_output_fingerprint",
            "output_fingerprint",
            "artifact_fingerprint",
            "fingerprint",
        ):
            raw = value.get(key)
            if (
                raw is not None
                and str(raw).strip()
                and str(raw).strip().lower() != "unknown"
            ):
                return str(raw).strip()
        for child in value.values():
            found = first_fingerprint_value(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = first_fingerprint_value(child)
            if found:
                return found
    return None


def current_fingerprint_from_args(root: Path, args: argparse.Namespace) -> str | None:
    direct = str(getattr(args, "current_output_fingerprint", "") or "").strip()
    if direct and direct.lower() != "unknown":
        return direct
    return first_fingerprint_value(
        load_json_value(root, getattr(args, "current_output_fingerprint_json", None))
    )


def extract_fingerprint_claims(text: str) -> list[str]:
    claims = sorted(
        set(match.group(1).strip() for match in FINGERPRINT_CLAIM_RE.finditer(text))
    )
    for match in re.finditer(
        r"declared_output_fingerprints\s*:\s*(\[[^\]\n]*\])", text, re.IGNORECASE
    ):
        try:
            loaded = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, list):
            claims.extend(str(item).strip() for item in loaded if str(item).strip())
    return sorted(set(claims))


def read_title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()[:120] or fallback
        if stripped:
            return stripped[:120]
    return fallback
