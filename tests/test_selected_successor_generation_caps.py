from __future__ import annotations

from pathlib import Path

import pytest

import orchestrate_task_cycle.selection_publication_store as publication_store
from orchestrate_task_cycle.selected_successor import (
    MAX_BUNDLE_BYTES,
    _publish_bundle,
)
from orchestrate_task_cycle.selected_successor_authority_artifacts import (
    MAX_INDEX_BYTES,
    MAX_OUTCOME_BYTES,
    packet_candidate,
    publish_index,
    publish_locator,
    publish_packet,
    publish_projection,
)
from orchestrate_task_cycle.selection_publication_store import (
    _canonical_json,
    _sha256_bytes,
    _write_once,
)


def _binding(ref: str, character: str) -> dict[str, str]:
    return {"ref": ref, "sha256": character * 64}


@pytest.mark.parametrize("kind", ("packet", "projection"))
def test_oversized_outcome_generation_has_zero_store_writes(
    tmp_path: Path, kind: str
) -> None:
    body = {"padding": "x" * (MAX_OUTCOME_BYTES - 64)}
    publisher = publish_packet if kind == "packet" else publish_projection
    field = (
        "packet_content_sha256"
        if kind == "packet"
        else "projection_content_sha256"
    )
    sealed = {**body, field: _sha256_bytes(_canonical_json(body))}
    assert len(_canonical_json(body)) <= MAX_OUTCOME_BYTES
    assert len(_canonical_json(sealed)) > MAX_OUTCOME_BYTES

    with pytest.raises(ValueError, match="exceeds 256 KiB"):
        publisher(tmp_path, body)

    assert not (tmp_path / ".task").exists()


def test_oversized_packet_candidate_cannot_publish_a_locator(
    tmp_path: Path,
) -> None:
    body = {"padding": "x" * (MAX_OUTCOME_BYTES + 1)}

    with pytest.raises(ValueError, match="exceeds 256 KiB"):
        packet_candidate(tmp_path, body)

    assert not (tmp_path / ".task").exists()


@pytest.mark.parametrize("kind", ("locator", "index"))
def test_oversized_lookup_generation_has_zero_store_writes(
    tmp_path: Path, kind: str
) -> None:
    input_sha = "a" * 64
    padding = {"oversized": "x" * (MAX_INDEX_BYTES + 1)}
    packet = _binding(".task/packet.json", "b")

    with pytest.raises(ValueError, match="exceeds 64 KiB"):
        if kind == "locator":
            publish_locator(tmp_path, input_sha, packet, padding)
        else:
            identity = {
                "prepared_at": "2026-07-23T00:00:00+00:00",
                "bundle": _binding("bundle.json", "c"),
                "request_context": _binding("request.json", "d"),
                "evaluation_context": _binding("evaluation.json", "e"),
                "grants": padding,
                "operation_manifests": {},
            }
            publish_index(
                tmp_path,
                identity,
                input_sha,
                outcome_kind="packet",
                outcome=packet,
            )

    assert not (tmp_path / ".task").exists()


def test_oversized_bundle_generation_has_zero_store_writes(tmp_path: Path) -> None:
    body = {"padding": "x" * (MAX_BUNDLE_BYTES - 64)}
    sealed = {
        **body,
        "bundle_content_sha256": _sha256_bytes(_canonical_json(body)),
    }
    assert len(_canonical_json(body)) <= MAX_BUNDLE_BYTES
    assert len(_canonical_json(sealed)) > MAX_BUNDLE_BYTES

    with pytest.raises(ValueError, match="exceeds 256 KiB"):
        _publish_bundle(tmp_path, body)

    assert not (tmp_path / ".task").exists()


def test_write_once_rejects_size_mismatch_before_opening_existing_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "existing.json"
    path.write_bytes(b"x" * (1024 * 1024))

    def unexpected_open(*_args: object, **_kwargs: object) -> int:
        raise AssertionError("size-mismatched immutable leaf must not be opened")

    monkeypatch.setattr(publication_store.os, "open", unexpected_open)
    with pytest.raises(ValueError, match="conflicts with immutable"):
        _write_once(path, b"{}\n", "bounded immutable test")
