#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cc", ".cpp", ".h", ".hpp", ".sh"}
CONFIG_NAMES = {"pyproject.toml", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "requirements.txt", "environment.yml", "Dockerfile", "docker-compose.yml", ".github"}


def git_files(root: Path) -> list[str]:
    try:
        result = subprocess.run(["git", "status", "--short"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        value = line[3:].strip()
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        if value:
            files.append(value)
    return files


def classify(path: str) -> list[str]:
    p = Path(path)
    parts = set(p.parts)
    name = p.name
    suffix = p.suffix.lower()
    surfaces: list[str] = []
    if path == "task.md" or ".task" in parts or ".agent_log" in parts:
        surfaces.append("task_state")
    if ".issue" in parts:
        surfaces.append("issue")
    if ".schema" in parts:
        surfaces.append("schema")
    if ".contract" in parts:
        surfaces.append("contract")
    if ".agent_goal" in parts or ".agent_advice" in parts:
        surfaces.append("goal_or_advice")
    if ".validation" in parts:
        surfaces.append("validation_set")
    if "test" in name.lower() or "tests" in parts:
        surfaces.append("tests")
    if suffix in SOURCE_SUFFIXES:
        surfaces.append("source")
    if name in CONFIG_NAMES or ".github" in parts or "ci" in parts:
        surfaces.append("runtime_config")
    if suffix in {".md", ".rst", ".txt"} and not surfaces:
        surfaces.append("docs")
    if not surfaces:
        surfaces.append("unknown")
    return sorted(set(surfaces))


def analyze(files: list[str]) -> dict[str, Any]:
    by_file = {path: classify(path) for path in files}
    surfaces = sorted({surface for values in by_file.values() for surface in values})
    high_risk = any(surface in surfaces for surface in ("runtime_config", "schema", "contract")) or (
        "source" in surfaces and "tests" in surfaces
    )
    return {"changed_files": files, "surfaces": surfaces, "by_file": by_file, "high_risk": high_risk}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify changed surfaces for validation-scope planning.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--from-git", action="store_true")
    parser.add_argument("--file", action="append", default=[])
    parser.add_argument("--input-json", help="JSON containing `changed_files`.")
    args = parser.parse_args(argv)

    files = list(args.file)
    if args.input_json:
        data = json.loads(Path(args.input_json).read_text(encoding="utf-8")) if args.input_json != "-" else json.loads(sys.stdin.read())
        value = data.get("changed_files") if isinstance(data, dict) else None
        if isinstance(value, list):
            files.extend(str(item) for item in value)
    if args.from_git:
        files.extend(git_files(Path(args.root).resolve()))
    output = analyze(sorted(dict.fromkeys(files)))
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
