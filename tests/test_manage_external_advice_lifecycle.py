from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
for package_root in (
    ROOT / "manage-external-advice" / "scripts",
    ROOT / "record-agent-work-log" / "scripts",
):
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from manage_external_advice.common import sha256_file, sha256_text  # noqa: E402
import manage_external_advice.application_publication as application_publication  # noqa: E402
import manage_external_advice.intake_apply as intake_apply_module  # noqa: E402
import manage_external_advice.intake_intent as intake_intent_module  # noqa: E402
import manage_external_advice.stable_store as stable_store  # noqa: E402
from manage_external_advice.intake_intent import publish_intake_intent  # noqa: E402
from manage_external_advice.intake import cmd_intake  # noqa: E402
from manage_external_advice.intake_plan import (  # noqa: E402
    apply_intake_plan,
    build_intake_plan,
    publish_intake_plan,
    verify_intake_plan,
)
from manage_external_advice.intake_plan_contract import (  # noqa: E402
    canonical_bytes as canonical_intake_bytes,
    sha256_bytes as intake_sha256_bytes,
)
from manage_external_advice.lifecycle import cmd_mark_applied  # noqa: E402
from manage_external_advice.packet_contract import (  # noqa: E402
    clause_id_sets,
    digest_binding,
)
from manage_external_advice.rendering import cmd_render_packet  # noqa: E402
from manage_external_advice.registry import main as registry_main  # noqa: E402
from manage_external_advice.storage import append_event, load_events, merge_state  # noqa: E402


FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "advice"
EXPECTED_SKILL_ADVICE_IDS = {
    *(
        f"SA-GEN-0{index}-{suffix}"
        for index, suffix in (
            (1, "INPLACE-FIRST"),
            (2, "ADDITIVE-ONLY-WITH-GAP"),
            (3, "NO-NEW-SKILL-BY-DEFAULT"),
            (4, "OPAQUE-SOURCE-METADATA"),
            (5, "NO-OVERCLAIM"),
        )
    ),
    "SA-GEN-06-FINAL-OUTCOME-CLASSIFICATION",
    "SA-001",
    "SA-002",
    "SA-003",
    "SA-004",
    "SA-005",
    "SA-006",
    "SA-007",
    "SA-008",
    "SA-009",
    "SA-009A",
    "SA-010",
    "SA-011",
    "SA-012A",
    "SA-012B",
    "SA-013",
    "SA-014",
    "SA-014A",
    "SA-014B",
    "SA-014C",
    *(f"A-S0{index}" for index in range(1, 7)),
}
EXPECTED_TASK_ADVICE_IDS = {
    *(
        f"TA-C0{index}-{suffix}"
        for index, suffix in (
            (1, "EVIDENCE-FIRST"),
            (2, "ONE-OWNER"),
            (3, "SATISFIABILITY"),
            (4, "SCOPED-PROGRESS"),
            (5, "SOURCE-OPAQUE"),
            (6, "NO-OVERCLAIM"),
            (7, "RECONSTRUCTION-READINESS"),
            (8, "SCOPED-CLOSEOUT"),
            (9, "CURRENT-DEBT-ROUTING"),
        )
    ),
    *(f"TA-{index:02d}" for index in range(14)),
    "TA-09A",
    "TA-09B",
    "TA-09C",
}


def _intake(root: Path, source: Path) -> None:
    cmd_intake(
        argparse.Namespace(
            root=str(root),
            source=str(source),
            title="workflow correction",
            priority="normal",
        )
    )


def _snapshot(root: Path) -> dict[str, bytes]:
    advice_root = root / ".agent_advice"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(advice_root.rglob("*"))
        if path.is_file()
    }


def _rehash_intake_plan(plan: dict[str, object]) -> dict[str, object]:
    body = {key: value for key, value in plan.items() if key != "plan_sha256"}
    return {**body, "plan_sha256": intake_sha256_bytes(canonical_intake_bytes(body))}


def test_intake_deduplicates_exact_raw_digest_before_any_registry_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "# Advice\n\nSA-013: Must wire the consumer decision gate.\n\n"
        "The workflow should preserve a separate happy path.\n",
        encoding="utf-8",
    )
    _intake(tmp_path, source)
    first_output = json.loads(capsys.readouterr().out)
    before = _snapshot(tmp_path)

    _intake(tmp_path, source)
    duplicate_output = json.loads(capsys.readouterr().out)
    after = _snapshot(tmp_path)

    assert first_output["status"] == "ok"
    assert duplicate_output["status"] == "duplicate_exact_raw_source"
    assert duplicate_output["deduplicated"] is True
    assert after == before
    assert len(load_events(tmp_path)) == 1


def test_intake_preserves_explicit_directive_id_and_scopes_implicit_id_to_digest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "# Advice\n\nSA-013: Must wire the consumer decision gate.\n\n"
        "The workflow should preserve a separate happy path.\n",
        encoding="utf-8",
    )
    _intake(tmp_path, source)
    capsys.readouterr()
    item = next(iter(merge_state(load_events(tmp_path)).values()))
    directives = item["fields"]["directives"]

    assert directives[0]["directive_id"] == "SA-013"
    assert directives[0]["id_origin"] == "explicit"
    assert directives[0]["directive_state"] == "pending"
    assert directives[0]["semantic_equivalence_claimed"] == "false"
    assert directives[1]["directive_id"] == f"dir-{item['raw_sha256']}-0002"
    assert directives[1]["id_origin"] == "source_digest_ordinal"
    assert item["fields"]["semantic_dedup_policy"] == "explicit_directive_id_only"


def test_intake_persists_opaque_source_metadata_and_keeps_raw_body_out_of_packets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    locator_token = "private-user-locator-7f93"
    raw_only_token = "RAW_BODY_ONLY_8db4519f"
    source_dir = tmp_path / locator_token
    source_dir.mkdir()
    source = source_dir / "identifying-source-name.md"
    raw_text = (
        f"{raw_only_token}\n\nSA-006: Must publish a recoverable lifecycle event.\n"
    )
    source.write_text(raw_text, encoding="utf-8")

    cmd_intake(
        argparse.Namespace(
            root=str(tmp_path),
            source=str(source.resolve()),
            title=None,
            priority="normal",
        )
    )
    intake = json.loads(capsys.readouterr().out)
    event = intake["event"]
    event_payload = json.dumps(event, ensure_ascii=False, sort_keys=True)

    assert event["source_label"] == event["source_id"]
    assert event["source_label"].startswith("src-sha256-")
    assert event["source_label_policy"] == "opaque_content_id"
    assert event["title_policy"] == "opaque_fallback"
    assert event["title"].startswith("external-advice-")
    assert str(source.resolve()) not in event_payload
    assert locator_token not in event_payload
    assert raw_only_token not in event_payload
    assert (tmp_path / event["raw_source_path"]).read_text(encoding="utf-8") == raw_text
    normalized = (tmp_path / event["path"]).read_text(encoding="utf-8")
    assert str(source.resolve()) not in normalized
    assert locator_token not in normalized

    cmd_render_packet(argparse.Namespace(root=str(tmp_path), format="json"))
    packet_payload = capsys.readouterr().out
    assert str(source.resolve()) not in packet_payload
    assert locator_token not in packet_payload
    assert raw_only_token not in packet_payload

    evidence = tmp_path / "validation.json"
    evidence.write_text('{"status":"pass"}\n', encoding="utf-8")
    digest = sha256_file(evidence)
    assert digest is not None
    item = merge_state(load_events(tmp_path))[event["advice_id"]]
    dispositions = [
        {
            "directive_id": row["directive_id"],
            "disposition": "incorporated",
            "evidence_ref": "validation.json",
            "evidence_sha256": digest,
        }
        for row in item["fields"]["directives"]
    ]
    cmd_mark_applied(
        argparse.Namespace(
            root=str(tmp_path),
            advice_id=event["advice_id"],
            evidence="validation run",
            directive_dispositions_json=json.dumps(dispositions),
            note="",
        )
    )
    capsys.readouterr()
    receipt_payload = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / ".agent_log").rglob("*.md")
    )
    assert str(source.resolve()) not in receipt_payload
    assert locator_token not in receipt_payload
    assert raw_only_token not in receipt_payload


def test_intake_replaces_path_like_caller_title_with_opaque_fallback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.md"
    source.write_text("SA-006: Must retain bounded metadata.\n", encoding="utf-8")
    unsafe_title = "../../private/customer-identifier"

    cmd_intake(
        argparse.Namespace(
            root=str(tmp_path),
            source=str(source),
            title=unsafe_title,
            priority="normal",
        )
    )
    event = json.loads(capsys.readouterr().out)["event"]

    assert event["title_policy"] == "opaque_fallback"
    assert event["title"].startswith("external-advice-")
    assert "private" not in event["title"]
    assert "customer-identifier" not in event["title"]


def test_implicit_duplicate_wording_keeps_distinct_source_ordinals(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "The workflow should preserve the decision path.\n"
        "The workflow should preserve the decision path.\n",
        encoding="utf-8",
    )
    _intake(tmp_path, source)
    capsys.readouterr()
    item = next(iter(merge_state(load_events(tmp_path)).values()))
    directives = item["fields"]["directives"]

    assert [row["directive_id"] for row in directives] == [
        f"dir-{item['raw_sha256']}-0001",
        f"dir-{item['raw_sha256']}-0002",
    ]
    assert all(row["semantic_equivalence_claimed"] == "false" for row in directives)


def test_conflicting_explicit_directive_id_fails_before_intake_write(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "SA-013: Must wire the decision gate.\n"
        "SA-013: Must remove the decision gate.\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="Duplicate explicit directive_id"):
        _intake(tmp_path, source)

    assert not (tmp_path / ".agent_advice").exists()


def test_duplicate_canonical_heading_declaration_fails_before_intake_write(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "### SA-001 — First owner\n"
        "- change_class: `in_place_revision`\n"
        "- consumption_state: `pending`\n\n"
        "### SA-001 — First owner\n"
        "- change_class: `in_place_revision`\n"
        "- consumption_state: `pending`\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Duplicate explicit directive_id"):
        _intake(tmp_path, source)

    assert not (tmp_path / ".agent_advice").exists()


@pytest.mark.parametrize(
    ("fixture_name", "expected_ids"),
    (
        ("skill_advice_structure.md", EXPECTED_SKILL_ADVICE_IDS),
        ("task_advice_structure.md", EXPECTED_TASK_ADVICE_IDS),
    ),
)
def test_root_advice_structures_intake_with_exact_canonical_clause_coverage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fixture_name: str,
    expected_ids: set[str],
) -> None:
    source = tmp_path / fixture_name
    source.write_text(
        (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    _intake(tmp_path, source)
    output = json.loads(capsys.readouterr().out)
    item = output["event"]
    records = item["fields"]["directives"]

    assert {row["directive_id"] for row in records} == expected_ids
    assert len(records) == len(expected_ids)
    assert all(row["id_origin"] == "explicit" for row in records)
    assert item["fields"]["fidelity_status"] == "ok"
    assert item["fields"]["normalization_complete"] == "true"
    assert item["fields"]["raw_direct_reference_required"] == "false"
    assert item["fields"]["execution_plan_eligible"] == "false"
    assert item["fields"]["reference_echo_count"] > 0


def test_structural_metadata_preserves_change_selection_and_grouping_contracts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "skill_advice_structure.md"
    source.write_text(
        (FIXTURE_ROOT / source.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    _intake(tmp_path, source)
    output = json.loads(capsys.readouterr().out)
    rows = {row["directive_id"]: row for row in output["event"]["fields"]["directives"]}

    assert rows["SA-001"]["change_class"] == "in_place_revision"
    assert rows["SA-012B"]["selection_disposition_when_capability_absent"] == "deferred"
    assert rows["SA-013"]["grouping_only"] == "true"
    assert rows["SA-013"]["actionable_child"] == "SA-013A-DOWNSTREAM-CONSUMER-WIRING"
    assert rows["SA-014C"]["selection_disposition"] == "deferred_by_default"
    assert rows["A-S01"]["selection_disposition"] == "deferred_by_default"
    assert rows["A-S01"]["conditional_grouping"] == "true"
    assert rows["A-S01"]["directive_state"] == "deferred"
    assert rows["SA-001"]["reference_classification"] == ("owning_clause_reference")
    assert "table_reference" in rows["SA-001"]["reference_kinds"]


def test_workflow_directive_uses_one_generic_owner_record_without_parallel_section(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "workflow-advice.md"
    directive_text = "Route owner semantics without global taxonomy"
    source.write_text(
        "# Advice\n\nCurrent workflow evidence is incomplete.\n\n"
        f"### WF-001 — {directive_text}\n"
        "- classification: `in_place_revision`\n"
        "- consumption_state: `pending`\n"
        "- target_owner: `derive-improvement-task`\n",
        encoding="utf-8",
    )

    _intake(tmp_path, source)
    event = json.loads(capsys.readouterr().out)["event"]
    record = event["fields"]["directives"][0]
    normalized = (tmp_path / event["path"]).read_text(encoding="utf-8")

    assert record["directive_id"] == "WF-001"
    assert record["directive_text"] == directive_text
    assert record["classification"] == "in_place_revision"
    assert record["change_class"] == "in_place_revision"
    assert record["consumption_state"] == "pending"
    assert record["target_owner"] == "derive-improvement-task"
    assert normalized.count(directive_text) == 1
    assert "## Workflow Contract Revisions" not in normalized


def test_document_local_contract_key_stays_raw_and_is_not_globalized(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "adapter-advice.md"
    directive_text = "Keep local contract detail adapter-owned"
    local_key = "gating_axis_producer_contract"
    source.write_text(
        "# Advice\n\nCurrent workflow evidence is incomplete.\n\n"
        f"### WF-002 — {directive_text}\n"
        "- change_class: `in_place_revision`\n"
        "- consumption_state: `pending`\n"
        "- target_owner: `task-doctor`\n"
        f"- {local_key}: `adapter-private-value`\n",
        encoding="utf-8",
    )

    _intake(tmp_path, source)
    event = json.loads(capsys.readouterr().out)["event"]
    record = event["fields"]["directives"][0]
    normalized = (tmp_path / event["path"]).read_text(encoding="utf-8")
    raw = (tmp_path / event["raw_source_path"]).read_text(encoding="utf-8")

    assert record["directive_text"] == directive_text
    assert local_key not in record
    assert f"{local_key}:" not in normalized
    assert f"{local_key}:" in raw
    assert normalized.count(directive_text) == 1


def test_documented_workflow_contract_matches_generic_normalizer_surface() -> None:
    skill_text = (ROOT / "manage-external-advice" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    contract_text = (
        ROOT
        / "manage-external-advice"
        / "references"
        / "advice-contract.md"
    ).read_text(encoding="utf-8")

    for field in (
        "change_class|classification",
        "consumption_state|default_state",
        "target_owner",
        "directive_text",
    ):
        assert field in skill_text
        assert field in contract_text
    assert "## Workflow Contract Revisions" not in contract_text
    assert "## Measurable Targets" not in contract_text
    assert "Part K-style" not in skill_text + contract_text
    assert "gating_axis_producer_contract" not in skill_text + contract_text
    assert "measurable target fields:" not in contract_text
    template = contract_text.split("```markdown", 1)[1].split("```", 1)[0]
    assert "re_advised_dead_hypothesis" not in template
    assert "dead_hypothesis_claims" not in template


def test_active_packet_exposes_exact_actionable_clause_and_source_binding(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "skill_advice_structure.md"
    source.write_text(
        (FIXTURE_ROOT / source.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    _intake(tmp_path, source)
    intake = json.loads(capsys.readouterr().out)
    cmd_render_packet(argparse.Namespace(root=str(tmp_path), format="json"))
    packet = json.loads(capsys.readouterr().out)

    non_actionable = {
        "SA-013",
        "SA-014",
        "SA-014C",
        *(f"A-S0{index}" for index in range(1, 7)),
    }
    expected_actionable = (EXPECTED_SKILL_ADVICE_IDS - non_actionable) | {
        "SA-013A-DOWNSTREAM-CONSUMER-WIRING"
    }
    assert packet["applicability"] == "applicable"
    assert set(packet["canonical_clause_ids"]) == EXPECTED_SKILL_ADVICE_IDS
    assert set(packet["canonical_actionable_clause_ids"]) == expected_actionable
    assert packet["actionable_clause_ids"] == packet["canonical_actionable_clause_ids"]
    assert packet["duplicate_actionable_clause_ids"] == []
    assert packet["advice_packet_digest"] == digest_binding(
        packet["advice_packet_digest_basis"]
    )
    advice_id = intake["event"]["advice_id"]
    source_digest = intake["event"]["raw_sha256"]
    assert packet["source_digests"] == {advice_id: source_digest}
    assert set(packet["clause_source_digests"]) == expected_actionable
    assert set(packet["clause_source_digests"].values()) == {source_digest}


def test_mark_applied_uses_structural_actionable_children_not_grouping_or_deferred(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "skill_advice_structure.md"
    source.write_text(
        (FIXTURE_ROOT / source.name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    evidence = tmp_path / "validation.json"
    evidence.write_text('{"status":"pass"}\n', encoding="utf-8")
    _intake(tmp_path, source)
    capsys.readouterr()
    item = next(iter(merge_state(load_events(tmp_path)).values()))
    _, actionable_ids = clause_id_sets(item)
    digest = sha256_file(evidence)
    assert digest is not None
    dispositions = [
        {
            "directive_id": directive_id,
            "disposition": "incorporated",
            "evidence_ref": "validation.json",
            "evidence_sha256": digest,
        }
        for directive_id in actionable_ids
    ]

    cmd_mark_applied(
        argparse.Namespace(
            root=str(tmp_path),
            advice_id=item["advice_id"],
            evidence="structural consumption",
            directive_dispositions_json=json.dumps(dispositions),
            note="",
        )
    )
    capsys.readouterr()
    updated = merge_state(load_events(tmp_path))[item["advice_id"]]

    assert set(updated["fields"]["directive_states"]) == set(actionable_ids)
    assert "SA-013A-DOWNSTREAM-CONSUMER-WIRING" in actionable_ids
    assert "SA-013" not in actionable_ids
    assert "SA-014C" not in actionable_ids
    assert not ({f"A-S0{index}" for index in range(1, 7)} & set(actionable_ids))


def test_raw_direct_fallback_is_needs_review_and_packet_is_not_an_execution_plan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "unstructured.md"
    source.write_text(
        "현재 observation에는 판단 근거가 부족하다.\n"
        "The workflow should preserve the unresolved evidence boundary.\n",
        encoding="utf-8",
    )

    _intake(tmp_path, source)
    output = json.loads(capsys.readouterr().out)
    fields = output["event"]["fields"]
    assert fields["fidelity_status"] == "needs_review"
    assert fields["fidelity_reason"] == "raw_direct_fallback_only"
    assert fields["raw_direct_reference_required"] == "true"
    assert fields["normalization_complete"] == "false"
    assert fields["normalized_packet_use"] == "warning_only_raw_review"

    cmd_render_packet(argparse.Namespace(root=str(tmp_path), format="json"))
    packet = json.loads(capsys.readouterr().out)

    assert packet["execution_plan_eligible"] is False
    assert packet["normalized_packet_use"] == "warning_only_raw_review"
    assert packet["incomplete_normalization_advice_ids"] == [
        output["event"]["advice_id"]
    ]


def test_mark_applied_requires_evidence_bound_disposition_for_every_directive(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.md"
    source.write_text(
        "# Advice\n\nSA-013: Must wire the consumer decision gate.\n\n"
        "The workflow should preserve a separate happy path.\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "validation.json"
    evidence.write_text('{"status":"pass"}\n', encoding="utf-8")
    _intake(tmp_path, source)
    capsys.readouterr()
    item = next(iter(merge_state(load_events(tmp_path)).values()))
    directive_ids = [row["directive_id"] for row in item["fields"]["directives"]]
    digest = sha256_file(evidence)
    assert digest is not None

    incomplete = [
        {
            "directive_id": directive_ids[0],
            "disposition": "incorporated",
            "evidence_ref": "validation.json",
            "evidence_sha256": digest,
        }
    ]
    with pytest.raises(SystemExit, match="cover every actionable directive"):
        cmd_mark_applied(
            argparse.Namespace(
                root=str(tmp_path),
                advice_id=item["advice_id"],
                evidence="validation run",
                directive_dispositions_json=json.dumps(incomplete),
                note="",
            )
        )
    assert (tmp_path / item["path"]).is_file()

    complete = [
        {
            "directive_id": directive_id,
            "disposition": "incorporated" if index == 0 else "residual",
            "evidence_ref": "validation.json",
            "evidence_sha256": digest,
        }
        for index, directive_id in enumerate(directive_ids)
    ]
    cmd_mark_applied(
        argparse.Namespace(
            root=str(tmp_path),
            advice_id=item["advice_id"],
            evidence="validation run",
            directive_dispositions_json=json.dumps(complete),
            note="residual remains explicitly open",
        )
    )
    capsys.readouterr()
    updated = merge_state(load_events(tmp_path))[item["advice_id"]]

    assert updated["status"] == "applied"
    assert updated["fields"]["container_lifecycle_separate_from_clause_state"] is True
    assert updated["fields"]["directive_states"] == {
        directive_ids[0]: "incorporated",
        directive_ids[1]: "residual",
    }
    assert all(
        row["evidence_sha256"] == digest for row in updated["directive_dispositions"]
    )


def _mark_applied_fixture(
    root: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[dict[str, object], list[dict[str, str]], argparse.Namespace]:
    source = root / "source.md"
    source.write_text(
        "# Advice\n\nSA-006: Must publish lifecycle state atomically.\n",
        encoding="utf-8",
    )
    evidence = root / "validation.json"
    evidence.write_text('{"status":"pass"}\n', encoding="utf-8")
    _intake(root, source)
    capsys.readouterr()
    item = next(iter(merge_state(load_events(root)).values()))
    digest = sha256_file(evidence)
    assert digest is not None
    dispositions = [
        {
            "directive_id": str(row["directive_id"]),
            "disposition": "incorporated",
            "evidence_ref": "validation.json",
            "evidence_sha256": digest,
        }
        for row in item["fields"]["directives"]  # type: ignore[index]
    ]
    args = argparse.Namespace(
        root=str(root),
        advice_id=item["advice_id"],
        evidence="validation run",
        directive_dispositions_json=json.dumps(dispositions),
        note="atomic lifecycle verification",
    )
    return item, dispositions, args


def _one_shot_crash(point: str):
    crashed = False

    def inject(name: str) -> None:
        nonlocal crashed
        if name == point and not crashed:
            crashed = True
            raise RuntimeError(f"injected {point}")

    return inject


@pytest.mark.parametrize(
    "crash_point",
    ("after_prepare", "after_applied_copy", "after_log"),
)
def test_mark_applied_precommit_crash_keeps_active_state_and_retry_converges(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    crash_point: str,
) -> None:
    item, _dispositions, args = _mark_applied_fixture(tmp_path, capsys)
    monkeypatch.setattr(
        application_publication, "_crash_point", _one_shot_crash(crash_point)
    )

    with pytest.raises(RuntimeError, match=crash_point):
        cmd_mark_applied(args)

    precommit_events = load_events(tmp_path)
    current = merge_state(precommit_events)[str(item["advice_id"])]
    assert current["status"] == "active"
    assert (tmp_path / str(item["path"])).is_file()
    assert not any(row.get("event") == "mark_applied" for row in precommit_events)
    if crash_point == "after_log":
        log_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (tmp_path / ".agent_log").rglob("*.md")
        )
        assert "becomes authoritative only when" in log_text

    monkeypatch.setattr(application_publication, "_crash_point", lambda _name: None)
    cmd_mark_applied(args)
    first = json.loads(capsys.readouterr().out)
    first_events = load_events(tmp_path)
    first_logs = (
        (tmp_path / ".agent_log" / "index.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )

    assert merge_state(first_events)[str(item["advice_id"])]["status"] == "applied"
    assert not (tmp_path / str(item["path"])).exists()
    assert (tmp_path / first["event"]["path"]).is_file()
    assert len([row for row in first_events if row.get("event") == "mark_applied"]) == 1
    assert len(first_logs) == 1
    assert first["event"]["operation_digest"] == first["operation_digest"]

    cmd_mark_applied(args)
    second = json.loads(capsys.readouterr().out)
    assert second["event"] == first["event"]
    assert load_events(tmp_path) == first_events
    assert (tmp_path / ".agent_log" / "index.jsonl").read_text(
        encoding="utf-8"
    ).splitlines() == first_logs


def test_mark_applied_postcommit_crash_recovers_cleanup_without_duplicate_event(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item, _dispositions, args = _mark_applied_fixture(tmp_path, capsys)
    monkeypatch.setattr(
        application_publication, "_crash_point", _one_shot_crash("after_event")
    )

    with pytest.raises(RuntimeError, match="after_event"):
        cmd_mark_applied(args)

    committed_events = load_events(tmp_path)
    current = merge_state(committed_events)[str(item["advice_id"])]
    assert current["status"] == "applied"
    assert (tmp_path / str(item["path"])).is_file()
    assert (
        len([row for row in committed_events if row.get("event") == "mark_applied"])
        == 1
    )

    monkeypatch.setattr(application_publication, "_crash_point", lambda _name: None)
    cmd_mark_applied(args)
    recovered = json.loads(capsys.readouterr().out)

    assert recovered["publication_recovered"] is True
    assert not (tmp_path / str(item["path"])).exists()
    assert load_events(tmp_path) == committed_events
    assert Path(tmp_path / recovered["journal"]["commit_receipt"]).is_file()


def test_mark_applied_prepare_cas_rejects_source_and_event_revision_changes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item, _dispositions, args = _mark_applied_fixture(tmp_path, capsys)
    monkeypatch.setattr(
        application_publication, "_crash_point", _one_shot_crash("after_prepare")
    )
    with pytest.raises(RuntimeError, match="after_prepare"):
        cmd_mark_applied(args)

    active = tmp_path / str(item["path"])
    original = active.read_text(encoding="utf-8")
    active.write_text(original + "\nchanged\n", encoding="utf-8")
    monkeypatch.setattr(application_publication, "_crash_point", lambda _name: None)
    with pytest.raises(SystemExit, match="CAS content digest mismatch"):
        cmd_mark_applied(args)
    assert not any(row.get("event") == "mark_applied" for row in load_events(tmp_path))

    active.write_text(original, encoding="utf-8")
    from manage_external_advice.storage import append_event

    append_event(
        tmp_path,
        {
            "event": "active_metadata_refresh",
            "advice_id": item["advice_id"],
            "status": "active",
            "path": item["path"],
            "content_sha256": item["content_sha256"],
        },
    )
    with pytest.raises(SystemExit, match="event revision/digest mismatch"):
        cmd_mark_applied(args)
    assert not any(row.get("event") == "mark_applied" for row in load_events(tmp_path))


def test_mark_applied_staged_artifact_tamper_is_not_promoted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item, _dispositions, args = _mark_applied_fixture(tmp_path, capsys)
    monkeypatch.setattr(
        application_publication,
        "_crash_point",
        _one_shot_crash("after_applied_copy"),
    )
    with pytest.raises(RuntimeError, match="after_applied_copy"):
        cmd_mark_applied(args)

    staged = next((tmp_path / ".agent_advice" / "applied").glob("*.md"))
    staged.write_text("tampered\n", encoding="utf-8")
    monkeypatch.setattr(application_publication, "_crash_point", lambda _name: None)
    with pytest.raises(SystemExit, match="Immutable advice publication conflict"):
        cmd_mark_applied(args)

    current = merge_state(load_events(tmp_path))[str(item["advice_id"])]
    assert current["status"] == "active"
    assert (tmp_path / str(item["path"])).is_file()


def test_mark_applied_prepared_request_cannot_be_silently_replaced(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item, _dispositions, args = _mark_applied_fixture(tmp_path, capsys)
    monkeypatch.setattr(
        application_publication, "_crash_point", _one_shot_crash("after_prepare")
    )
    with pytest.raises(RuntimeError, match="after_prepare"):
        cmd_mark_applied(args)

    changed = argparse.Namespace(**vars(args))
    changed.evidence = "different validation claim"
    monkeypatch.setattr(application_publication, "_crash_point", lambda _name: None)
    with pytest.raises(SystemExit, match="different request"):
        cmd_mark_applied(changed)

    current = merge_state(load_events(tmp_path))[str(item["advice_id"])]
    assert current["status"] == "active"
    assert (
        len(list((tmp_path / ".agent_advice" / "journal").rglob("*.prepare.json"))) == 1
    )


def test_mark_applied_tampered_prepare_journal_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item, _dispositions, args = _mark_applied_fixture(tmp_path, capsys)
    monkeypatch.setattr(
        application_publication, "_crash_point", _one_shot_crash("after_prepare")
    )
    with pytest.raises(RuntimeError, match="after_prepare"):
        cmd_mark_applied(args)

    prepare = next((tmp_path / ".agent_advice" / "journal").rglob("*.prepare.json"))
    record = json.loads(prepare.read_text(encoding="utf-8"))
    record["prepared_at"] = "tampered"
    prepare.write_text(json.dumps(record), encoding="utf-8")
    monkeypatch.setattr(application_publication, "_crash_point", lambda _name: None)
    with pytest.raises(SystemExit, match="journal digest mismatch"):
        cmd_mark_applied(args)

    current = merge_state(load_events(tmp_path))[str(item["advice_id"])]
    assert current["status"] == "active"


def test_intake_plan_freezes_identity_paths_timestamps_and_digests_then_replays(
    tmp_path: Path,
) -> None:
    raw_text = "# Advice\n\nSA-006: Must preserve one immutable intake operation.\n"
    source = tmp_path / "frozen-source.md"
    source.write_text(raw_text, encoding="utf-8")
    fixed_at = "2026-07-18T14:05:06+09:00"
    plan = build_intake_plan(
        tmp_path,
        raw_text,
        "frozen intake",
        "high",
        at=fixed_at,
        source_ref="frozen-source.md",
    )

    assert plan["created_at"] == fixed_at
    assert plan["raw"]["path"].endswith("20260718-140506-frozen-intake.md")
    assert plan["raw"]["source_ref"] == (
        ".agent_advice/journal/intake/source_snapshots/"
        f"src-sha256-{plan['raw']['sha256']}.md"
    )
    # Pure planning must not mutate the workspace. Publication materializes the
    # content-addressed, opaque source snapshot together with the immutable plan.
    assert not (tmp_path / plan["raw"]["source_ref"]).exists()
    assert "content" not in plan["raw"]
    assert "content" not in plan["normalized"]
    assert "event" not in plan
    assert raw_text not in json.dumps(plan, ensure_ascii=False, sort_keys=True)
    assert sha256_text(raw_text) == plan["raw"]["sha256"]

    planned = publish_intake_plan(
        tmp_path, plan, ".agent_advice/journal/intake/frozen.plan.json"
    )
    assert (tmp_path / plan["raw"]["source_ref"]).read_text(
        encoding="utf-8"
    ) == raw_text
    assert not (tmp_path / plan["raw"]["path"]).exists()
    assert not (tmp_path / plan["normalized"]["path"]).exists()
    applied = apply_intake_plan(tmp_path, planned["plan_ref"])
    before_replay = _snapshot(tmp_path)
    replay = apply_intake_plan(tmp_path, planned["plan_ref"])

    assert applied["result_kind"] == "external_advice_intake_apply_result"
    assert applied["apply_status"] == "applied"
    assert replay["apply_status"] == "already_applied"
    assert replay["idempotent_replay"] is True
    assert replay["mutation_performed"] is False
    assert _snapshot(tmp_path) == before_replay
    assert len(load_events(tmp_path)) == 1
    assert (tmp_path / plan["raw"]["path"]).read_text(encoding="utf-8") == raw_text
    assert sha256_file(tmp_path / planned["plan_ref"]) == planned["plan_file_sha256"]
    assert sha256_file(tmp_path / applied["receipt_ref"]) == applied[
        "receipt_file_sha256"
    ]
    assert applied["execution_result_binding"] == {
        "ref": applied["receipt_ref"],
        "sha256": applied["receipt_file_sha256"],
    }


def test_intake_plan_public_verifier_is_read_only_and_reopens_owner_effect(
    tmp_path: Path,
) -> None:
    text = "SA-006: Expose a closed read-only intake verification contract.\n"
    source = tmp_path / "verify-source.md"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "verify intake",
        "normal",
        at="2026-07-18T14:06:00+09:00",
        source_ref="verify-source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)

    before_ready = _snapshot(tmp_path)
    ready = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert ready["status"] == "ready"
    assert ready["mutation_performed"] is False
    assert _snapshot(tmp_path) == before_ready

    applied = apply_intake_plan(tmp_path, planned["plan_ref"])
    before_verify = _snapshot(tmp_path)
    verified = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert verified["status"] == "already_applied"
    assert verified["receipt_ref"] == applied["receipt_ref"]
    assert verified["receipt_file_sha256"] == applied["receipt_file_sha256"]
    assert verified["mutation_performed"] is False
    assert _snapshot(tmp_path) == before_verify

    (tmp_path / plan["raw"]["path"]).write_text("tampered", encoding="utf-8")
    conflicted = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert conflicted["status"] == "conflict"
    assert "raw_artifact_digest_mismatch" in conflicted["defects"]


def test_intake_plan_duplicate_settles_no_effect_and_reopens_after_suffix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    text = "SA-006: Preserve one exact source without a duplicate plan effect.\n"
    source = tmp_path / "source.md"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "planned duplicate",
        "normal",
        at="2026-07-18T14:06:10+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    competing = build_intake_plan(
        tmp_path,
        text,
        "canonical duplicate",
        "normal",
        at="2026-07-18T14:06:11+09:00",
        source_ref="source.md",
    )
    competing_plan = publish_intake_plan(tmp_path, competing)
    apply_intake_plan(tmp_path, competing_plan["plan_ref"])

    settled = apply_intake_plan(tmp_path, planned["plan_ref"])
    assert settled["status"] == "settled_no_effect"
    assert settled["settlement_kind"] == "exact_duplicate"
    assert settled["reason_codes"] == ["duplicate_exact_raw_source"]
    receipt_path = tmp_path / settled["receipt_ref"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["receipt_kind"] == "external_advice_intake_no_effect_receipt"
    assert receipt["plan_id"] == plan["plan_id"]
    assert receipt["plan_file_sha256"] == planned["plan_file_sha256"]
    assert receipt["duplicate_proof"]["raw_sha256"] == plan["raw"]["sha256"]
    assert text not in receipt_path.read_text(encoding="utf-8")

    suffix = tmp_path / "suffix.md"
    suffix.write_text("SA-007: Append an unrelated valid suffix.\n", encoding="utf-8")
    _intake(tmp_path, suffix)
    capsys.readouterr()
    reopened = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert reopened["status"] == "settled_no_effect"
    assert reopened["plan_effect_observed"] is False
    assert reopened["plan_intent_observed"] is False
    assert reopened["prestate_current"] is False
    assert reopened["no_effect_verified"] is True
    assert reopened["receipt_file_sha256"] == settled["receipt_file_sha256"]

    before_replay = _snapshot(tmp_path)
    replay = apply_intake_plan(tmp_path, planned["plan_ref"])
    assert replay["idempotent_replay"] is True
    assert replay["mutation_performed"] is False
    assert _snapshot(tmp_path) == before_replay


def test_intake_plan_source_staleness_gets_closed_no_effect_receipt(
    tmp_path: Path,
) -> None:
    text = "SA-006: Bind source staleness before canonical publication.\n"
    source = tmp_path / "source.md"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "source stale",
        "normal",
        at="2026-07-18T14:06:20+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    (tmp_path / plan["raw"]["source_ref"]).write_text(
        "changed source\n", encoding="utf-8"
    )

    stale = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert stale["status"] == "stale"
    assert stale["plan_effect_observed"] is False
    assert stale["plan_intent_observed"] is False
    assert stale["prestate_current"] is False
    assert stale["no_effect_verified"] is False
    settled = apply_intake_plan(tmp_path, planned["plan_ref"])
    assert settled["reason_codes"] == ["source_changed"]
    assert not (tmp_path / plan["raw"]["path"]).exists()
    assert not (tmp_path / plan["normalized"]["path"]).exists()
    assert verify_intake_plan(tmp_path, planned["plan_ref"])["no_effect_verified"]


@pytest.mark.parametrize(
    ("published_keys", "stale_kind"),
    (
        (("raw",), "registry"),
        (("normalized",), "source"),
        (("raw", "normalized"), "registry_and_source"),
    ),
)
def test_intake_plan_owned_destination_bytes_never_settle_as_no_effect(
    tmp_path: Path,
    published_keys: tuple[str, ...],
    stale_kind: str,
) -> None:
    text = "SA-006: Treat deterministic destination bytes as partial publication.\n"
    source = tmp_path / "source.md"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "partial destination",
        "normal",
        at="2026-07-18T14:06:21+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    content = intake_apply_module._materialize_plan(tmp_path, plan)
    for key in published_keys:
        destination = tmp_path / plan[key]["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content[key])
    if "registry" in stale_kind:
        append_event(
            tmp_path,
            {
                "event": "defer",
                "advice_id": "adv-unrelated-partial",
                "status": "deferred",
                "updated_at": "2026-07-18T14:06:22+09:00",
            },
        )
    if "source" in stale_kind:
        (tmp_path / plan["raw"]["source_ref"]).unlink()

    observed = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert observed["status"] == "recovery_required"
    assert observed["plan_effect_observed"] is True
    assert observed["plan_owned_publication_observed"] is True
    assert observed["no_effect_verified"] is False
    with pytest.raises(SystemExit):
        apply_intake_plan(tmp_path, planned["plan_ref"])
    assert not (
        tmp_path
        / ".agent_advice"
        / "journal"
        / "intake"
        / f"{plan['plan_id']}.receipt.json"
    ).exists()


def test_intake_plan_opaque_snapshot_hides_caller_locator_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    private = tmp_path / "private-author-work-title" / "identifying-name.md"
    private.parent.mkdir()
    private.write_text(
        "SA-006: Preserve only an opaque source locator.\n", encoding="utf-8"
    )

    cmd_intake(
        argparse.Namespace(
            root=str(tmp_path),
            source=str(private),
            title=None,
            priority="normal",
        )
    )
    capsys.readouterr()

    durable_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in (tmp_path / ".agent_advice").rglob("*")
        if path.is_file()
    )
    assert "private-author-work-title" not in durable_text
    assert "identifying-name.md" not in durable_text


def test_intake_plan_file_requires_exact_canonical_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Seal exact plan bytes.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "plan bytes",
        "normal",
        at="2026-07-18T14:06:23+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    plan_path = tmp_path / planned["plan_ref"]
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="bytes are not canonical"):
        verify_intake_plan(tmp_path, planned["plan_ref"])


def test_intake_intent_file_requires_exact_canonical_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Seal exact intent bytes.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "intent bytes",
        "normal",
        at="2026-07-18T14:06:24+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    publish_intake_intent(
        tmp_path, plan, planned["plan_ref"], planned["plan_file_sha256"]
    )
    intent_path = intake_intent_module.intent_path(tmp_path, plan["plan_id"])
    intent = json.loads(intent_path.read_text(encoding="utf-8"))
    intent_path.write_bytes(canonical_intake_bytes(intent))

    with pytest.raises(SystemExit, match="bytes are not canonical"):
        intake_intent_module._load_intent(tmp_path, intent_path)
    assert verify_intake_plan(tmp_path, planned["plan_ref"])["status"] == "conflict"


def test_intake_no_effect_receipt_requires_exact_canonical_bytes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Seal exact no-effect receipt bytes.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "receipt bytes",
        "normal",
        at="2026-07-18T14:06:25+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    (tmp_path / plan["raw"]["source_ref"]).unlink()
    settled = apply_intake_plan(tmp_path, planned["plan_ref"])
    receipt_path = tmp_path / settled["receipt_ref"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_path.write_bytes(canonical_intake_bytes(receipt) + b"\n ")

    observed = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert observed["status"] == "conflict"
    assert observed["no_effect_verified"] is False


def test_intake_plan_concurrent_cas_has_one_effect_and_one_no_effect(
    tmp_path: Path,
) -> None:
    planned: list[dict[str, object]] = []
    for ordinal in (1, 2):
        source = tmp_path / f"source-{ordinal}.md"
        text = f"SA-00{ordinal}: Serialize one competing intake plan.\n"
        source.write_text(text, encoding="utf-8")
        plan = build_intake_plan(
            tmp_path,
            text,
            f"concurrent {ordinal}",
            "normal",
            at=f"2026-07-18T14:06:2{ordinal}+09:00",
            source_ref=source.name,
        )
        planned.append(publish_intake_plan(tmp_path, plan))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda item: apply_intake_plan(tmp_path, str(item["plan_ref"])),
                planned,
            )
        )
    assert {result["status"] for result in results} == {"ok", "settled_no_effect"}
    assert len(load_events(tmp_path)) == 1
    no_effect = next(result for result in results if result["status"] == "settled_no_effect")
    verified = verify_intake_plan(tmp_path, no_effect["plan_ref"])
    assert verified["status"] == "settled_no_effect"
    assert verified["plan_effect_observed"] is False
    assert verified["no_effect_verified"] is True


def test_intake_plan_pending_exact_intent_is_recovery_not_no_effect(
    tmp_path: Path,
) -> None:
    text = "SA-006: Never classify a pending own intent as no effect.\n"
    source = tmp_path / "source.md"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "pending intent",
        "normal",
        at="2026-07-18T14:06:30+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    assert publish_intake_intent(
        tmp_path, plan, planned["plan_ref"], planned["plan_file_sha256"]
    )

    pending = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert pending["status"] == "recovery_required"
    assert pending["plan_intent_observed"] is True
    assert pending["no_effect_verified"] is False
    applied = apply_intake_plan(tmp_path, planned["plan_ref"])
    assert applied["apply_status"] == "applied"
    assert verify_intake_plan(tmp_path, planned["plan_ref"])["status"] == "already_applied"


def test_intake_plan_pending_intent_with_changed_source_is_conflict(
    tmp_path: Path,
) -> None:
    text = "SA-006: Do not settle an ambiguous pending intent.\n"
    source = tmp_path / "source.md"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "ambiguous intent",
        "normal",
        at="2026-07-18T14:06:35+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    publish_intake_intent(
        tmp_path, plan, planned["plan_ref"], planned["plan_file_sha256"]
    )
    (tmp_path / plan["raw"]["source_ref"]).write_text(
        "changed after intent\n", encoding="utf-8"
    )
    classified = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert classified["status"] == "conflict"
    assert classified["plan_intent_observed"] is True
    assert classified["no_effect_verified"] is False
    with pytest.raises(SystemExit, match="source digest mismatch"):
        apply_intake_plan(tmp_path, planned["plan_ref"])


def test_intake_no_effect_prefix_accepts_canonical_separator_before_suffix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = tmp_path / "baseline.md"
    baseline.write_text("SA-001: Establish a prefix without final newline.\n", encoding="utf-8")
    _intake(tmp_path, baseline)
    capsys.readouterr()
    registry = tmp_path / ".agent_advice" / "index.jsonl"
    registry.write_bytes(registry.read_bytes().rstrip(b"\n"))
    source = tmp_path / "source.md"
    text = "SA-006: Reopen no-effect proof after a canonical separator.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "separator proof",
        "normal",
        at="2026-07-18T14:06:36+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    (tmp_path / plan["raw"]["source_ref"]).unlink()
    settled = apply_intake_plan(tmp_path, planned["plan_ref"])
    append_event(
        tmp_path,
        {
            "event": "defer",
            "advice_id": "adv-unrelated",
            "status": "deferred",
            "updated_at": "2026-07-18T14:06:37+09:00",
        },
    )
    verified = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert verified["status"] == "settled_no_effect"
    assert verified["receipt_file_sha256"] == settled["receipt_file_sha256"]


def test_intake_plan_tampered_no_effect_receipt_and_symlink_fail_closed(
    tmp_path: Path,
) -> None:
    text = "SA-006: Seal no-effect evidence without raw content.\n"
    source = tmp_path / "source.md"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "sealed no effect",
        "normal",
        at="2026-07-18T14:06:40+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    source.unlink()
    settled = apply_intake_plan(tmp_path, planned["plan_ref"])
    receipt_path = tmp_path / settled["receipt_ref"]
    tampered = json.loads(receipt_path.read_text(encoding="utf-8"))
    tampered["unexpected"] = "field"
    body = {key: value for key, value in tampered.items() if key != "receipt_content_sha256"}
    tampered["receipt_content_sha256"] = intake_sha256_bytes(
        canonical_intake_bytes(body)
    )
    receipt_path.write_text(json.dumps(tampered), encoding="utf-8")
    conflicted = verify_intake_plan(tmp_path, planned["plan_ref"])
    assert conflicted["status"] == "conflict"
    assert conflicted["no_effect_verified"] is False

    other = tmp_path / "other.md"
    other.write_text("SA-007: Reject a symlinked receipt leaf.\n", encoding="utf-8")
    other_plan = build_intake_plan(
        tmp_path,
        other.read_text(encoding="utf-8"),
        "receipt symlink",
        "normal",
        at="2026-07-18T14:06:41+09:00",
        source_ref="other.md",
    )
    other_planned = publish_intake_plan(tmp_path, other_plan)
    receipt_leaf = (
        tmp_path
        / ".agent_advice"
        / "journal"
        / "intake"
        / f"{other_plan['plan_id']}.receipt.json"
    )
    outside = tmp_path / "outside-receipt.json"
    outside.write_text("{}", encoding="utf-8")
    receipt_leaf.symlink_to(outside)
    with pytest.raises(SystemExit, match="journal artifact must be a regular file"):
        apply_intake_plan(tmp_path, other_planned["plan_ref"])


def test_intake_plan_rejects_noncanonical_or_symlinked_source_refs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Keep source bindings canonical and non-symlinked.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "source binding",
        "normal",
        at="2026-07-18T14:07:00+09:00",
        source_ref="source.md",
    )
    malicious = json.loads(json.dumps(plan))
    malicious["raw"]["source_ref"] = "./source.md"
    malicious = _rehash_intake_plan(malicious)
    with pytest.raises(SystemExit, match="exact canonical workspace-relative"):
        publish_intake_plan(tmp_path, malicious)

    real = tmp_path / "real"
    real.mkdir()
    (real / "source.md").write_text(text, encoding="utf-8")
    (tmp_path / "alias").symlink_to(real, target_is_directory=True)
    with pytest.raises(SystemExit, match="must not traverse symlinks"):
        build_intake_plan(
            tmp_path,
            text,
            "symlinked source",
            "normal",
            at="2026-07-18T14:08:00+09:00",
            source_ref="alias/source.md",
        )


@pytest.mark.parametrize(
    "destination",
    (
        "outside.md",
        ".agent_advice/raw/../outside.md",
        "/tmp/external-advice-outside.md",
    ),
)
def test_intake_plan_rejects_self_hashed_noncanonical_destination(
    tmp_path: Path,
    destination: str,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Keep intake destinations canonical.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "canonical",
        "normal",
        at="2026-07-18T14:10:00+09:00",
        source_ref="source.md",
    )
    plan["raw"]["path"] = destination
    malicious = _rehash_intake_plan(plan)
    plan_path = tmp_path / "malicious-plan.json"
    plan_path.write_bytes(canonical_intake_bytes(malicious) + b"\n")

    with pytest.raises(SystemExit, match="exact canonical"):
        apply_intake_plan(tmp_path, "malicious-plan.json")

    assert not (tmp_path / "outside.md").exists()


def test_intake_plan_prepare_rejects_noncanonical_metadata_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Keep prepare metadata in its owned subtree.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "prepare boundary",
        "normal",
        at="2026-07-18T14:10:01+09:00",
        source_ref="source.md",
    )

    with pytest.raises(SystemExit, match="plan output must be an exact canonical"):
        publish_intake_plan(tmp_path, plan, "outside.plan.json")

    assert not (tmp_path / "outside.plan.json").exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("advice_id", "adv-unbound", "advice_id"),
        ("source_id", "src-sha256-" + "0" * 64, "source identity"),
        ("registry_path", ".agent_advice/other.jsonl", "registry binding"),
        ("markdown_path", ".agent_advice/other.md", "Markdown binding"),
        ("raw_sha256", "A" * 64, "content digests"),
    ),
)
def test_intake_plan_rejects_rehashed_internal_identity_or_path_mismatch(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Bind every intake identity.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "bound",
        "normal",
        at="2026-07-18T14:11:00+09:00",
        source_ref="source.md",
    )
    if field == "source_id":
        plan["metadata"]["source_id"] = value
    elif field == "registry_path":
        plan["registry"]["path"] = value
    elif field == "markdown_path":
        plan["markdown"]["path"] = value
    elif field == "raw_sha256":
        plan["raw"]["sha256"] = value
    else:
        plan[field] = value
    malicious = _rehash_intake_plan(plan)
    plan_path = tmp_path / f"malicious-{field}.json"
    plan_path.write_bytes(canonical_intake_bytes(malicious) + b"\n")

    with pytest.raises(SystemExit, match=message):
        apply_intake_plan(tmp_path, plan_path.relative_to(tmp_path))


@pytest.mark.parametrize("directory", ("raw", "active"))
def test_intake_plan_rejects_symlinked_destination_ancestor(
    tmp_path: Path,
    directory: str,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Reject symlinked intake ancestors.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "symlink ancestor",
        "normal",
        at="2026-07-18T14:12:00+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    outside = tmp_path / f"outside-{directory}"
    outside.mkdir()
    (tmp_path / ".agent_advice" / directory).symlink_to(
        outside, target_is_directory=True
    )

    with pytest.raises(SystemExit, match="ancestor must be a regular directory"):
        apply_intake_plan(tmp_path, planned["plan_ref"])

    assert list(outside.iterdir()) == []


def test_intake_plan_source_snapshot_ancestor_swap_cannot_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Bind source snapshots to a stable parent identity.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "snapshot parent identity",
        "normal",
        at="2026-07-18T14:12:10+09:00",
        source_ref="source.md",
    )
    snapshots = tmp_path / ".agent_advice" / "journal" / "intake" / "source_snapshots"
    detached = snapshots.with_name("source_snapshots-detached")
    outside = tmp_path / "outside-snapshots"
    outside.mkdir()
    original_write = stable_store._write_payload
    swapped = False

    def write_then_swap(descriptor: int, payload: bytes, mode: int) -> None:
        nonlocal swapped
        original_write(descriptor, payload, mode)
        if payload == text.encode() and not swapped:
            snapshots.rename(detached)
            snapshots.symlink_to(outside, target_is_directory=True)
            swapped = True

    monkeypatch.setattr(stable_store, "_write_payload", write_then_swap)

    with pytest.raises(SystemExit, match="ancestors must be stable|identity changed"):
        publish_intake_plan(tmp_path, plan)

    assert swapped is True
    assert list(outside.iterdir()) == []
    assert list(detached.iterdir()) == []
    assert not (
        tmp_path
        / ".agent_advice"
        / "journal"
        / "intake"
        / f"{plan['plan_id']}.plan.json"
    ).exists()


def test_registry_replace_ancestor_swap_cannot_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert load_events(tmp_path) == []
    advice = tmp_path / ".agent_advice"
    detached = tmp_path / ".agent_advice-detached"
    outside = tmp_path / "outside-registry"
    outside.mkdir()
    original_write = stable_store._write_payload
    swapped = False

    def write_then_swap(descriptor: int, payload: bytes, mode: int) -> None:
        nonlocal swapped
        original_write(descriptor, payload, mode)
        if payload and not swapped:
            advice.rename(detached)
            advice.symlink_to(outside, target_is_directory=True)
            swapped = True

    monkeypatch.setattr(stable_store, "_write_payload", write_then_swap)

    with pytest.raises(SystemExit, match="ancestors must be stable|identity changed"):
        append_event(
            tmp_path,
            {
                "event": "defer",
                "advice_id": "adv-ancestor-swap",
                "status": "deferred",
                "updated_at": "2026-07-18T14:12:11+09:00",
            },
        )

    assert swapped is True
    assert list(outside.iterdir()) == []
    assert (detached / "index.jsonl").read_bytes() == b""
    assert not list(detached.glob(".index.jsonl.*.tmp"))


def test_intake_plan_rejects_symlink_or_conflicting_destination_leaf(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Reject conflicting intake leaves.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "leaf conflict",
        "normal",
        at="2026-07-18T14:13:00+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    raw_path = tmp_path / plan["raw"]["path"]
    raw_path.parent.mkdir()
    outside = tmp_path / "outside-leaf.md"
    outside.write_text("outside\n", encoding="utf-8")
    raw_path.symlink_to(outside)
    with pytest.raises(SystemExit, match="destination must be a regular file"):
        apply_intake_plan(tmp_path, planned["plan_ref"])
    raw_path.unlink()
    raw_path.write_text("conflict\n", encoding="utf-8")
    settled = apply_intake_plan(tmp_path, planned["plan_ref"])
    assert settled["status"] == "settled_no_effect"
    assert settled["reason_codes"] == ["raw_destination_conflict"]
    assert settled["plan_effect_observed"] is False


def test_intake_plan_stale_registry_and_tampered_plan_fail_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first_source = tmp_path / "first-source.md"
    first_source.write_text(
        "SA-001: Must preserve the planned source.\n", encoding="utf-8"
    )
    first = build_intake_plan(
        tmp_path,
        "SA-001: Must preserve the planned source.\n",
        "first",
        "normal",
        at="2026-07-18T15:00:00+09:00",
        source_ref="first-source.md",
    )
    first_plan = publish_intake_plan(tmp_path, first)

    source = tmp_path / "second.md"
    source.write_text("SA-002: Must publish a separate source.\n", encoding="utf-8")
    _intake(tmp_path, source)
    capsys.readouterr()
    settled = apply_intake_plan(tmp_path, first_plan["plan_ref"])
    assert settled["status"] == "settled_no_effect"
    assert "registry_cas_stale" in settled["reason_codes"]
    assert settled["execution_result_binding"] == {
        "ref": settled["receipt_ref"],
        "sha256": settled["receipt_file_sha256"],
    }
    assert not (tmp_path / first["raw"]["path"]).exists()

    third_source = tmp_path / "third-source.md"
    third_source.write_text(
        "SA-003: Must reject a changed plan body.\n", encoding="utf-8"
    )
    third = build_intake_plan(
        tmp_path,
        "SA-003: Must reject a changed plan body.\n",
        "third",
        "normal",
        at="2026-07-18T15:00:01+09:00",
        source_ref="third-source.md",
    )
    third_plan = publish_intake_plan(tmp_path, third)
    plan_path = tmp_path / third_plan["plan_ref"]
    tampered = json.loads(plan_path.read_text(encoding="utf-8"))
    tampered["created_at"] = "2026-07-18T15:00:02+09:00"
    plan_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(SystemExit, match="plan digest mismatch"):
        apply_intake_plan(tmp_path, third_plan["plan_ref"])


def test_intake_plan_recovers_post_event_projection_and_duplicate_is_zero_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_text = "SA-006: Must recover the intake projection after event commit.\n"
    source = tmp_path / "recoverable-source.md"
    source.write_text(raw_text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        raw_text,
        "recoverable",
        "normal",
        at="2026-07-18T16:00:00+09:00",
        source_ref="recoverable-source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    original_rebuild = intake_apply_module.rebuild_index

    def crash_projection(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected advice projection failure")

    monkeypatch.setattr(intake_apply_module, "rebuild_index", crash_projection)
    with pytest.raises(RuntimeError, match="projection failure"):
        apply_intake_plan(tmp_path, planned["plan_ref"])
    assert len(load_events(tmp_path)) == 1
    with pytest.raises(SystemExit, match="Pending external-advice intake intent"):
        append_event(
            tmp_path,
            {
                "event": "defer",
                "advice_id": plan["advice_id"],
                "status": "deferred",
                "updated_at": "2026-07-18T16:00:01+09:00",
            },
        )

    competing_source = tmp_path / "competing-source.md"
    competing_text = "SA-007: A competing intake must wait for recovery.\n"
    competing_source.write_text(competing_text, encoding="utf-8")
    competing = build_intake_plan(
        tmp_path,
        competing_text,
        "competing",
        "normal",
        at="2026-07-18T16:00:02+09:00",
        source_ref="competing-source.md",
    )
    competing_plan = publish_intake_plan(tmp_path, competing)
    with pytest.raises(SystemExit, match="Pending external-advice intake intent"):
        apply_intake_plan(tmp_path, competing_plan["plan_ref"])

    monkeypatch.setattr(intake_apply_module, "rebuild_index", original_rebuild)
    recovered = apply_intake_plan(tmp_path, planned["plan_ref"])
    assert recovered["apply_status"] == "already_applied"
    assert recovered["publication_recovered"] is True
    before_duplicate = _snapshot(tmp_path)
    duplicate = build_intake_plan(
        tmp_path,
        raw_text,
        "ignored duplicate title",
        "low",
        at="2026-07-18T17:00:00+09:00",
        source_ref="recoverable-source.md",
    )
    assert duplicate["status"] == "duplicate_exact_raw_source"
    assert duplicate["mutation_performed"] is False
    assert _snapshot(tmp_path) == before_duplicate


def test_intake_plan_recovers_unique_committed_event_with_unrelated_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Recover an exact intake event without discarding a suffix.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "suffix recovery",
        "normal",
        at="2026-07-18T16:10:00+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)
    original_rebuild = intake_apply_module.rebuild_index

    def crash_projection(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected suffix recovery crash")

    monkeypatch.setattr(intake_apply_module, "rebuild_index", crash_projection)
    with pytest.raises(RuntimeError, match="suffix recovery crash"):
        apply_intake_plan(tmp_path, planned["plan_ref"])
    registry = tmp_path / ".agent_advice" / "index.jsonl"
    unrelated = {
        "event": "intake",
        "advice_id": "adv-unrelated-suffix",
        "type": "external_advice",
        "status": "active",
        "path": ".agent_advice/active/unrelated.md",
        "updated_at": "2026-07-18T16:10:01+09:00",
    }
    with registry.open("ab") as handle:
        handle.write((json.dumps(unrelated, sort_keys=True) + "\n").encode("utf-8"))
    suffix_bytes = registry.read_bytes()

    monkeypatch.setattr(intake_apply_module, "rebuild_index", original_rebuild)
    recovered = apply_intake_plan(tmp_path, planned["plan_ref"])

    assert recovered["apply_status"] == "already_applied"
    assert recovered["publication_recovered"] is True
    assert registry.read_bytes() == suffix_bytes
    assert len(load_events(tmp_path)) == 2
    assert (tmp_path / recovered["receipt_ref"]).is_file()


def test_intake_plan_recovery_rejects_duplicate_plan_tagged_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.md"
    text = "SA-006: Reject ambiguous plan-tagged recovery.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "ambiguous recovery",
        "normal",
        at="2026-07-18T16:11:00+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)

    def crash_projection(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected ambiguous recovery crash")

    monkeypatch.setattr(intake_apply_module, "rebuild_index", crash_projection)
    with pytest.raises(RuntimeError, match="ambiguous recovery crash"):
        apply_intake_plan(tmp_path, planned["plan_ref"])
    registry = tmp_path / ".agent_advice" / "index.jsonl"
    duplicate = dict(load_events(tmp_path)[0])
    with registry.open("ab") as handle:
        handle.write((json.dumps(duplicate, sort_keys=True) + "\n").encode("utf-8"))

    with pytest.raises(SystemExit, match="duplicate committed events"):
        apply_intake_plan(tmp_path, planned["plan_ref"])


@pytest.mark.parametrize("tamper", ("wrong_prefix", "noncontiguous", "invalid_suffix"))
def test_intake_plan_recovery_rejects_unproven_historical_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tamper: str,
) -> None:
    baseline = tmp_path / "baseline.md"
    baseline.write_text("SA-001: Establish a bound prefix.\n", encoding="utf-8")
    _intake(tmp_path, baseline)
    capsys.readouterr()
    source = tmp_path / "source.md"
    text = "SA-006: Require a proven historical intake boundary.\n"
    source.write_text(text, encoding="utf-8")
    plan = build_intake_plan(
        tmp_path,
        text,
        "boundary proof",
        "normal",
        at="2026-07-18T16:12:00+09:00",
        source_ref="source.md",
    )
    planned = publish_intake_plan(tmp_path, plan)

    def crash_projection(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("injected intake boundary failure")

    monkeypatch.setattr(intake_apply_module, "rebuild_index", crash_projection)
    with pytest.raises(RuntimeError, match="intake boundary failure"):
        apply_intake_plan(tmp_path, planned["plan_ref"])
    registry = tmp_path / ".agent_advice" / "index.jsonl"
    rows = load_events(tmp_path)
    tagged_index = next(
        offset
        for offset, row in enumerate(rows)
        if row.get("intake_plan_id") == plan["plan_id"]
    )
    if tamper == "wrong_prefix":
        rows[0] = {**rows[0], "title": "mutated historical prefix"}
        registry.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    elif tamper == "noncontiguous":
        rows.insert(
            tagged_index,
            {
                "event": "intake",
                "advice_id": "adv-interposed",
                "type": "external_advice",
                "status": "active",
                "path": ".agent_advice/active/interposed.md",
                "updated_at": "2026-07-18T16:12:01+09:00",
            },
        )
        registry.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    else:
        with registry.open("ab") as handle:
            handle.write(b"[]\n")

    message = "committed boundary" if tamper != "invalid_suffix" else "Invalid JSON object"
    with pytest.raises(SystemExit, match=message):
        apply_intake_plan(tmp_path, planned["plan_ref"])


def test_intake_cli_plan_then_apply_plan_round_trip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "cli-source.md"
    source.write_text("SA-006: Must support explicit plan/apply CLI.\n", encoding="utf-8")
    plan_ref = ".agent_advice/journal/intake/cli.plan.json"

    assert registry_main(
        [
            "--root",
            str(tmp_path),
            "intake",
            "--source",
            str(source),
            "--title",
            "cli plan",
            "--at",
            "2026-07-18T18:00:00+09:00",
            "--plan",
            plan_ref,
        ]
    ) == 0
    planned = json.loads(capsys.readouterr().out)
    assert planned["status"] == "planned"
    assert not (tmp_path / ".agent_advice" / "index.jsonl").exists()

    assert registry_main(
        ["--root", str(tmp_path), "intake", "--apply-plan", plan_ref]
    ) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied["apply_status"] == "applied"
    assert applied["execution_result_binding"]["sha256"] == applied[
        "receipt_file_sha256"
    ]
