#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


SOURCE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
}
DOC_SUFFIXES = {".md", ".mdx", ".rst", ".txt"}
RUNTIME_NAMES = {
    "cargo.lock",
    "cargo.toml",
    "compose.yaml",
    "compose.yml",
    "dockerfile",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pyproject.toml",
    "requirements.txt",
    "tox.ini",
    "uv.lock",
    "yarn.lock",
}


def normalize_path(root: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()
    normalized = path.as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def classify_path(value: str) -> str:
    path = Path(value)
    parts = tuple(part.lower() for part in path.parts)
    name = path.name.lower()
    suffix = path.suffix.lower()

    if ".issue" in parts:
        return "issue"
    if ".task" in parts:
        return "task_state"
    if ".schema" in parts or name.endswith(".schema.json") or name.endswith(".schema.yaml"):
        return "schema"
    if ".contract" in parts or name == "skill.md" or name.endswith(".contract.json"):
        return "contract"
    if (
        "tests" in parts
        or "test" in parts
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
    ):
        return "tests"
    if name in RUNTIME_NAMES or (".github" in parts and "workflows" in parts) or name.startswith("dockerfile."):
        return "runtime_config"
    if suffix in SOURCE_SUFFIXES:
        return "source"
    if suffix in DOC_SUFFIXES or "docs" in parts or "references" in parts:
        return "docs"
    return "unknown"


def values_from_payload(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("changed_files", "planned_changed_files", "actual_changed_files", "files"):
        raw = payload.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if isinstance(item, str) and item.strip():
                values.append(item)
            elif isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"].strip():
                values.append(item["path"])
    return values


def git_changed_files(root: Path) -> list[str]:
    process = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace").strip() or "git status failed")
    fields = process.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        row = fields[index]
        index += 1
        if not row:
            continue
        status = row[:2]
        path = row[3:]
        if "R" in status or "C" in status:
            if path:
                paths.append(path)
            if index < len(fields) and fields[index]:
                path = fields[index]
                index += 1
        if path:
            paths.append(path)
    return paths


def classify_files(root: Path, values: Iterable[str]) -> dict[str, Any]:
    normalized = sorted({normalize_path(root, value) for value in values if str(value).strip()})
    files = [{"path": value, "surface": classify_path(value)} for value in normalized]
    counts = Counter(item["surface"] for item in files)
    return {
        "format_version": 1,
        "status": "ok",
        "files": files,
        "changed_files": normalized,
        "changed_surfaces": sorted(counts),
        "surface_counts": dict(sorted(counts.items())),
    }


def load_payload(value: str) -> dict[str, Any]:
    if value == "-":
        raw = sys.stdin.read()
    else:
        stripped = value.strip()
        if stripped.startswith("{"):
            raw = stripped
        else:
            candidate = Path(value)
            raw = candidate.read_text(encoding="utf-8") if candidate.is_file() else value
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise SystemExit("Input JSON must be an object.")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify changed files into validation surfaces.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--input-json")
    parser.add_argument("--from-git", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    values = list(args.file)
    if args.input_json:
        values.extend(values_from_payload(load_payload(args.input_json)))
    if args.from_git:
        try:
            values.extend(git_changed_files(root))
        except RuntimeError as exc:
            json.dump({"format_version": 1, "status": "block", "error": str(exc)}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 2
    json.dump(classify_files(root, values), sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
