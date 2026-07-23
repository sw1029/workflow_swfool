from __future__ import annotations

import json
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
    "orchestrate-task-cycle": (
        "stage prepare",
        "stage submit",
        "stage advance",
        "prepare-intent",
        "prepare-authority",
        "semantic_field_count",
        "compiler-first-efficiency.md",
    ),
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


def test_authority_packet_publication_has_a_bounded_compiler_operation() -> None:
    manifest = json.loads(
        (
            ROOT / "orchestrate-task-cycle/authority.operations.json"
        ).read_text(encoding="utf-8")
    )
    operation = next(
        row
        for row in manifest["operations"]
        if row["operation_id"] == "publish_authority_packet_binding"
    )
    assert operation["authority_applicability"] == "none"
    assert operation["authorization_mechanism"] == "none"
    assert operation["mutation_class"] == "local_mutation"
    assert operation["source_rank_floor"] == "S0"
    assert operation["risk_floor"] == "R1"
    assert operation["effect_classes"] == [
        "publish_validated_authority_owner_result_binding"
    ]

    skill = (ROOT / "orchestrate-task-cycle/SKILL.md").read_text(encoding="utf-8")
    for token in (
        "publish_authority_packet_binding",
        "authority-packet --cycle-id <cycle> --publish",
        "effect_boundary: preparation_only",
    ):
        assert token in skill


def test_selected_successor_docs_sanction_guarded_route_without_api_overclaim() -> None:
    skill = (ROOT / "orchestrate-task-cycle/SKILL.md").read_text(encoding="utf-8")
    reference = (
        ROOT
        / "orchestrate-task-cycle/references/selection-reentry-and-publication.md"
    ).read_text(encoding="utf-8")

    assert "Use only `selected-successor execute|recover`" in skill
    assert "Do not invoke the lower owner commands directly" in skill
    assert "they do not themselves establish the all-three gate" in skill
    assert "the only supported first-effect entrypoints" in reference
    assert "must not be invoked directly for this route" in reference
    assert "do not themselves establish or retroactively create" in reference


def test_selected_successor_docs_define_compiled_authority_packet_boundary() -> None:
    skill = (ROOT / "orchestrate-task-cycle/SKILL.md").read_text(encoding="utf-8")
    reference = (
        ROOT
        / "orchestrate-task-cycle/references/selection-reentry-and-publication.md"
    ).read_text(encoding="utf-8")
    efficiency = (
        ROOT / "orchestrate-task-cycle/references/compiler-first-efficiency.md"
    ).read_text(encoding="utf-8")
    authority_skill = (ROOT / "manage-agent-authority/SKILL.md").read_text(
        encoding="utf-8"
    )
    authority_contract = (
        ROOT / "manage-agent-authority/references/authority-v2-contract.md"
    ).read_text(encoding="utf-8")

    for text in (skill, reference, efficiency, authority_skill, authority_contract):
        assert "prepare-authority" in text
        assert "canonical evaluator" in text
        assert "source approval or grant" in text

    for token in (
        "selected_successor_authority_request_context",
        "selected_successor_authority_packet",
        "selected_successor_authority_approval_projection",
        "--index-grant-absent",
        "--publication-grant-absent",
        "--settlement-grant-absent",
        "--authority-packet-ref",
        "legacy-compatible",
    ):
        assert token in reference, token

    assert "zero decisions, reservations, or pre-commit verifications" in reference
    assert "The packet is a compact transport and" in reference
    assert "not new authority" in reference
    assert "trusted_request_idempotency_key" in authority_skill
    assert "trusted_request_idempotency_key" in authority_contract
    assert "evaluate_and_publish" in authority_contract
    assert "verify_and_publish_precommit" in authority_contract
