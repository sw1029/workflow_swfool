from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SKILL_FILES = sorted(
    path
    for path in ROOT.glob("*/SKILL.md")
    if not path.parent.name.startswith(".")
)


def scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        parsed = ast.literal_eval(value)
        return str(parsed)
    return value


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "---", f"{path}: missing opening frontmatter delimiter"
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise AssertionError(f"{path}: missing closing frontmatter delimiter") from exc
    result: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        assert ":" in line, f"{path}: malformed frontmatter line: {line!r}"
        key, value = line.split(":", 1)
        result[key.strip()] = scalar(value)
    return result


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda path: path.parent.name)
def test_skill_frontmatter_matches_directory_and_is_discoverable(skill_path: Path) -> None:
    metadata = frontmatter(skill_path)

    assert set(metadata) == {"name", "description"}
    assert metadata["name"] == skill_path.parent.name
    assert NAME_PATTERN.fullmatch(metadata["name"])
    assert len(metadata["name"]) <= 64
    assert metadata["description"].strip()
    assert len(metadata["description"]) <= 1024
    assert "<" not in metadata["description"] and ">" not in metadata["description"]

