from __future__ import annotations

from .common import *

def normalize_family_key(artifact_family: str, semantic_signature: str) -> str:
    raw = f"{artifact_family or 'unknown'}|{semantic_signature or 'unknown'}".lower()
    raw = re.sub(r"\bcycle-\d{8}-\d{6}\b", "cycle", raw)
    raw = re.sub(r"\b20\d{6}(?:[-_]\d{2,6})?\b", "date", raw)
    raw = re.sub(r"[-_]v\d+\b", "-vNNN", raw)
    raw = re.sub(r"\bv\d+\b", "vNNN", raw)
    raw = re.sub(r"after[-_][a-z0-9_.-]+", "after-X", raw)
    raw = re.sub(r"run[-_][a-z0-9_.-]+", "run-X", raw)
    raw = re.sub(r"w_[a-f0-9]{8,}", "w_HASH", raw)
    raw = re.sub(r"[^a-z0-9|._-]+", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-")
    return raw or "unknown|unknown"

def normalize_root_family_key(*values: Any) -> str:
    raw = "|".join(str(value or "") for value in values if value is not None and str(value).strip()).lower()
    if not raw:
        return "unknown"
    raw = re.sub(r"\bcycle-\d{8}-\d{6}\b", "cycle", raw)
    raw = re.sub(r"\b20\d{6}(?:[-_]\d{2,6})?\b", "date", raw)
    raw = re.sub(r"\b\d{8,14}\b", "date", raw)
    raw = re.sub(r"\b[0-9a-f]{7,40}\b", "hash", raw)
    raw = re.sub(r"after[-_][a-z0-9_.-]+", "after-x", raw)
    raw = re.sub(r"run[-_][a-z0-9_.-]+", "run-x", raw)
    raw = re.sub(r"\bv\d+\b|[-_]v\d+\b", "vnnn", raw)
    raw = re.sub(r"[^a-z0-9가-힣|._:/-]+", "-", raw)
    raw = re.sub(r"-{2,}", "-", raw).strip("-_.:/|")
    for _ in range(6):
        updated = FACET_SUFFIX_RE.sub("", raw).strip("-_.:/|")
        if updated == raw:
            break
        raw = updated
    tokens = [token for token in re.split(r"[|._:/-]+", raw) if token and token not in {"date", "run", "cycle"}]
    return "_".join(dict.fromkeys(tokens[:16]))[:200] or "unknown"
