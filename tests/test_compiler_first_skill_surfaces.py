from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
TARGET_SKILLS = (
    "manage-agent-authority",
    "task-doctor",
    "manage-task-state-index",
    "manage-external-advice",
    "orchestrate-task-cycle",
)
REQUIRED_COMPILER_TOKENS = {
    "manage-agent-authority": ("compile-operation", "non-authoritative"),
    "task-doctor": ("compile-intent", "accept-review", "schema-v2"),
    "manage-task-state-index": ("compile-transition", "--intent"),
    "manage-external-advice": ("compile-dispositions", "--decision-map"),
    "orchestrate-task-cycle": ("stage prepare", "stage submit", "stage advance"),
}
FORBIDDEN_AUXILIARY_DOCS = {
    "README.md",
    "INSTALLATION_GUIDE.md",
    "QUICK_REFERENCE.md",
    "CHANGELOG.md",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]*)?)\)")


def test_target_skills_keep_progressive_disclosure_bounds() -> None:
    for skill_name in TARGET_SKILLS:
        skill_root = ROOT / skill_name
        body = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        assert len(body.splitlines()) < 500, skill_name
        assert len(body.split()) < 5_000, skill_name
        assert not (FORBIDDEN_AUXILIARY_DOCS & {path.name for path in skill_root.iterdir()})


def test_target_skill_markdown_links_and_long_reference_contents() -> None:
    for skill_name in TARGET_SKILLS:
        skill_root = ROOT / skill_name
        skill_file = skill_root / "SKILL.md"
        for raw_target in MARKDOWN_LINK.findall(skill_file.read_text(encoding="utf-8")):
            relative = raw_target.split("#", 1)[0]
            assert (skill_root / relative).is_file(), (skill_name, relative)
        for reference in (skill_root / "references").glob("*.md"):
            text = reference.read_text(encoding="utf-8")
            if len(text.splitlines()) > 100:
                assert "## Contents" in text, reference


def test_target_openai_metadata_is_compact_and_skill_bound() -> None:
    for skill_name in TARGET_SKILLS:
        payload = yaml.safe_load(
            (ROOT / skill_name / "agents" / "openai.yaml").read_text(encoding="utf-8")
        )
        assert set(payload) == {"interface"}
        interface = payload["interface"]
        assert set(interface) == {"display_name", "short_description", "default_prompt"}
        assert 25 <= len(interface["short_description"]) <= 64
        prompt = interface["default_prompt"]
        assert f"${skill_name}" in prompt
        assert prompt.count(".") == 1 and prompt.endswith(".")
        assert len(prompt) <= 240


def test_target_skill_docs_prefer_the_public_compiler_surfaces() -> None:
    for skill_name, tokens in REQUIRED_COMPILER_TOKENS.items():
        body = (ROOT / skill_name / "SKILL.md").read_text(encoding="utf-8")
        for token in tokens:
            assert token in body, (skill_name, token)
