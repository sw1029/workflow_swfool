#!/usr/bin/env python3
"""Inventory local Python environments and check dependency availability.

This script is intentionally read-only. It discovers common conda/venv/system
interpreters, probes package metadata and import specs, and emits JSON or text.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


COMMON_VENV_NAMES = {".venv", "venv", "env", ".env", "virtualenv"}
SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".tox",
    "_tmp",
    "tmp",
    "logs",
    "processed",
    "catalog",
    "normalized",
    "index",
}
COMMON_IMPORT_NAMES = {
    "beautifulsoup4": "bs4",
    "opencv-python": "cv2",
    "opencv-contrib-python": "cv2",
    "pillow": "PIL",
    "pyyaml": "yaml",
    "scikit-learn": "sklearn",
    "python-dateutil": "dateutil",
    "sentence-transformers": "sentence_transformers",
    "huggingface-hub": "huggingface_hub",
    "faiss-cpu": "faiss",
    "faiss-gpu": "faiss",
    "pytorch-lightning": "pytorch_lightning",
}


def run_json(cmd: List[str], timeout: int = 8) -> Optional[Any]:
    try:
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=timeout)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except Exception:
        return None


def executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def python_in_prefix(prefix: Path) -> Optional[Path]:
    candidates = [
        prefix / "bin" / "python",
        prefix / "Scripts" / "python.exe",
        prefix / "python.exe",
    ]
    for candidate in candidates:
        if executable(candidate):
            return candidate
    return None


def add_candidate(candidates: Dict[str, Dict[str, Any]], python: Path, kind: str, name: str, prefix: Optional[Path] = None) -> None:
    try:
        resolved = python.resolve()
    except Exception:
        resolved = python
    key = str(resolved)
    if key in candidates:
        existing = candidates[key]
        existing["sources"] = sorted(set(existing.get("sources", []) + [kind]))
        if name and name not in existing.get("names", []):
            existing.setdefault("names", []).append(name)
        return
    candidates[key] = {
        "python": key,
        "kind": kind,
        "names": [name] if name else [],
        "prefix": str(prefix or python.parent.parent),
        "sources": [kind],
    }


def discover_conda(candidates: Dict[str, Dict[str, Any]]) -> None:
    data = run_json(["conda", "env", "list", "--json"], timeout=12)
    if isinstance(data, dict):
        for prefix_text in data.get("envs", []) or []:
            prefix = Path(prefix_text)
            python = python_in_prefix(prefix)
            if python:
                add_candidate(candidates, python, "conda", prefix.name, prefix)
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        prefix = Path(conda_prefix)
        python = python_in_prefix(prefix)
        if python:
            add_candidate(candidates, python, "conda-active", prefix.name, prefix)


def discover_virtualenvs(candidates: Dict[str, Dict[str, Any]], root: Path, max_depth: int) -> None:
    roots: List[Path] = [root]
    for env_var in ("VIRTUAL_ENV",):
        value = os.environ.get(env_var)
        if value:
            roots.append(Path(value))
    home = Path.home()
    roots.extend(
        [
            home / ".virtualenvs",
            home / ".venvs",
            home / ".cache" / "pypoetry" / "virtualenvs",
            home / ".local" / "share" / "virtualenvs",
            home / ".conda" / "envs",
            home / "miniconda3" / "envs",
            home / "anaconda3" / "envs",
        ]
    )
    for base in roots:
        if not base.exists():
            continue
        if python_in_prefix(base):
            add_candidate(candidates, python_in_prefix(base), "venv", base.name, base)  # type: ignore[arg-type]
        if base == root:
            stack = [(base, 0)]
            while stack:
                current, depth = stack.pop()
                if depth > max_depth:
                    continue
                if current.name in COMMON_VENV_NAMES:
                    python = python_in_prefix(current)
                    if python:
                        add_candidate(candidates, python, "venv", current.name, current)
                    continue
                try:
                    children = [p for p in current.iterdir() if p.is_dir() and p.name not in SKIP_DIR_NAMES]
                except Exception:
                    continue
                stack.extend((child, depth + 1) for child in children)
        else:
            try:
                for child in base.iterdir():
                    if child.is_dir():
                        python = python_in_prefix(child)
                        if python:
                            add_candidate(candidates, python, "venv", child.name, child)
            except Exception:
                continue


def discover_path_pythons(candidates: Dict[str, Dict[str, Any]]) -> None:
    seen: set[str] = set()
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found and found not in seen:
            seen.add(found)
            add_candidate(candidates, Path(found), "path", name, None)


def parse_dep(text: str) -> Tuple[str, str]:
    if "=" in text:
        dist, import_name = text.split("=", 1)
    elif ":" in text:
        dist, import_name = text.split(":", 1)
    else:
        dist = text
        import_name = COMMON_IMPORT_NAMES.get(text.lower(), text.replace("-", "_"))
    return dist.strip(), import_name.strip()


PROBE = r"""
import importlib.metadata as md
import importlib.util
import json
import platform
import sys

deps = json.loads(sys.argv[1])
result = {
    "executable": sys.executable,
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "version": sys.version.split()[0],
    "implementation": platform.python_implementation(),
    "deps": [],
}
for item in deps:
    dist = item["dist"]
    import_name = item["import"]
    dep = {"dist": dist, "import": import_name, "dist_version": None, "import_found": False, "error": None}
    try:
        dep["dist_version"] = md.version(dist)
    except Exception as exc:
        dep["error"] = type(exc).__name__
    try:
        dep["import_found"] = importlib.util.find_spec(import_name) is not None
    except Exception as exc:
        dep["import_error"] = type(exc).__name__
    result["deps"].append(dep)
print(json.dumps(result, ensure_ascii=True))
"""


def probe_python(python: str, deps: List[Tuple[str, str]], timeout: int) -> Dict[str, Any]:
    payload = [{"dist": dist, "import": import_name} for dist, import_name in deps]
    try:
        proc = subprocess.run(
            [python, "-c", PROBE, json.dumps(payload)],
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except Exception as exc:
        return {"ok": False, "probe_error": repr(exc)}
    if proc.returncode != 0:
        return {"ok": False, "probe_error": proc.stderr.strip()[:1000]}
    try:
        data = json.loads(proc.stdout)
    except Exception as exc:
        return {"ok": False, "probe_error": f"json parse failed: {exc}"}
    data["ok"] = True
    return data


def score_candidate(probe: Dict[str, Any]) -> Tuple[int, List[str], List[str]]:
    deps = probe.get("deps") or []
    present: List[str] = []
    missing: List[str] = []
    score = 0
    for dep in deps:
        name = dep.get("dist") or dep.get("import")
        if dep.get("import_found"):
            present.append(str(name))
            score += 2
        elif dep.get("dist_version"):
            present.append(str(name))
            score += 1
        else:
            missing.append(str(name))
            score -= 3
    return score, present, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory local Python envs and dependency availability.")
    parser.add_argument("--root", default=".", help="Project root to scan for local venvs.")
    parser.add_argument("--dep", action="append", default=[], help="Dependency name, or distribution=import_name. Repeatable.")
    parser.add_argument("--max-depth", type=int, default=3, help="Depth for project-local venv discovery.")
    parser.add_argument("--timeout", type=int, default=8, help="Per-interpreter probe timeout seconds.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    deps = [parse_dep(dep) for dep in args.dep]
    candidates: Dict[str, Dict[str, Any]] = {}
    discover_conda(candidates)
    discover_virtualenvs(candidates, root, args.max_depth)
    discover_path_pythons(candidates)
    add_candidate(candidates, Path(sys.executable), "current", "current", Path(sys.prefix))

    results: List[Dict[str, Any]] = []
    for candidate in candidates.values():
        probe = probe_python(candidate["python"], deps, args.timeout)
        score, present, missing = score_candidate(probe) if probe.get("ok") else (-999, [], [dist for dist, _ in deps])
        row = {**candidate, "probe": probe, "score": score, "present": present, "missing": missing}
        results.append(row)
    results.sort(key=lambda item: (item["score"], not item["missing"], item["python"]), reverse=True)

    output = {"root": str(root), "dependencies": [{"dist": d, "import": i} for d, i in deps], "environments": results}
    if args.json:
        print(json.dumps(output, ensure_ascii=True, indent=2))
    else:
        for idx, env in enumerate(results, 1):
            probe = env.get("probe", {})
            version = probe.get("version", "unknown")
            status = "ok" if not env["missing"] and probe.get("ok") else "missing"
            print(f"{idx}. {status} score={env['score']} python={env['python']} version={version}")
            print(f"   kind={env['kind']} names={','.join(env.get('names') or [])} prefix={env.get('prefix')}")
            if env["present"]:
                print(f"   present={', '.join(env['present'])}")
            if env["missing"]:
                print(f"   missing={', '.join(env['missing'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
