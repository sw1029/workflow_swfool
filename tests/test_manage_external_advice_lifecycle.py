from __future__ import annotations

import argparse
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

from manage_external_advice.common import sha256_file  # noqa: E402
import manage_external_advice.application_publication as application_publication  # noqa: E402
from manage_external_advice.intake import cmd_intake  # noqa: E402
from manage_external_advice.lifecycle import cmd_mark_applied  # noqa: E402
from manage_external_advice.packet_contract import (  # noqa: E402
    clause_id_sets,
    digest_binding,
)
from manage_external_advice.rendering import cmd_render_packet  # noqa: E402
from manage_external_advice.storage import load_events, merge_state  # noqa: E402


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
