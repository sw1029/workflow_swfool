"""Validate one exact-subject premise against locally bound evidence artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .exact_subject_premise import (
    validate_exact_subject_premise,
    validate_exact_subject_premise_receipt,
)
from .exact_subject_premise_v2 import (
    seal_artifact_verified_receipt,
    validate_artifact_verified_exact_subject_premise_receipt,
)


MAX_SERIALIZED_INPUT_BYTES = 256 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


class _CliBlock(ValueError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--context", required=True)
    parser.add_argument("--submission", required=True)
    parser.add_argument("--prior-receipt", action="append", default=[])
    parser.add_argument(
        "--binding-artifact",
        help="current task or selection-baseline artifact; required if consumed",
    )
    parser.add_argument(
        "--subject-artifact",
        help="current subject body artifact; required if consumed",
    )
    parser.add_argument(
        "--source-subject-artifact",
        help="source-side body artifact; required for source-separated evidence",
    )
    parser.add_argument(
        "--baseline-subject-artifact",
        help="prior subject body artifact; required for a nonempty freshness baseline",
    )
    parser.add_argument(
        "--evidence-artifact",
        action="append",
        default=[],
        metavar="EVIDENCE_ID=PATH",
        help=(
            "repeat for the invariant and every producer/verifier/replay or "
            "source/current/comparison receipt"
        ),
    )
    return parser


def _workspace_root(path_value: str) -> Path:
    try:
        root = Path(path_value).expanduser().resolve(strict=True)
    except OSError as exc:
        raise _CliBlock("workspace_root_invalid") from exc
    if not root.is_dir():
        raise _CliBlock("workspace_root_invalid")
    return root


def _workspace_file(root: Path, path_value: str, reason_code: str) -> Path:
    candidate = Path(path_value)
    if not path_value or ".." in candidate.parts:
        raise _CliBlock("workspace_path_invalid")
    lexical = candidate if candidate.is_absolute() else root / candidate
    try:
        relative = lexical.absolute().relative_to(root)
    except ValueError as exc:
        raise _CliBlock("workspace_path_invalid") from exc
    current = root
    try:
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise OSError
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
        if not stat.S_ISREG(resolved.lstat().st_mode):
            raise OSError
    except (OSError, ValueError) as exc:
        raise _CliBlock(reason_code) from exc
    return resolved


def _read_object(root: Path, path_value: str, reason_code: str) -> dict[str, Any]:
    path = _workspace_file(root, path_value, reason_code)
    try:
        with path.open("rb") as handle:
            body = handle.read(MAX_SERIALIZED_INPUT_BYTES + 1)
        if len(body) > MAX_SERIALIZED_INPUT_BYTES:
            raise OSError
        value = json.loads(body.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _CliBlock(reason_code) from exc
    if not isinstance(value, dict):
        raise _CliBlock(reason_code)
    return value


def _artifact_sha256(root: Path, path_value: str | None, reason_code: str) -> str:
    if not path_value:
        raise _CliBlock(reason_code)
    path = _workspace_file(root, path_value, reason_code)
    try:
        if path.stat().st_size > MAX_ARTIFACT_BYTES:
            raise OSError
        digest = hashlib.sha256()
        size_bytes = 0
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                size_bytes += len(chunk)
                if size_bytes > MAX_ARTIFACT_BYTES:
                    raise OSError
                digest.update(chunk)
    except OSError as exc:
        raise _CliBlock(reason_code) from exc
    return digest.hexdigest()


def _canonical_sha256(value: object) -> str:
    try:
        body = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _CliBlock("binding_artifact_invalid") from exc
    return hashlib.sha256(body).hexdigest()


def _verify_current_binding(
    root: Path, binding: Mapping[str, Any], artifact_path: str | None
) -> dict[str, str]:
    kind = binding.get("binding_kind")
    if kind == "terminal_task":
        raw_sha256 = _artifact_sha256(
            root, artifact_path, "binding_artifact_unreadable"
        )
        binding_sha256 = raw_sha256
        expected = binding.get("terminal_task_sha256")
        artifact_id = "terminal-task"
        digest_mode = "raw_sha256"
    elif kind == "selection_baseline":
        if not artifact_path:
            raise _CliBlock("binding_artifact_unreadable")
        artifact = _read_object(root, artifact_path, "binding_artifact_unreadable")
        binding_sha256 = _canonical_sha256(artifact)
        raw_sha256 = _artifact_sha256(
            root, artifact_path, "binding_artifact_unreadable"
        )
        expected = binding.get("selection_baseline_sha256")
        artifact_id = str(binding.get("selection_baseline_id"))
        digest_mode = "canonical_json_sha256"
    else:
        raise _CliBlock("binding_artifact_invalid")
    if binding_sha256 != expected:
        raise _CliBlock("binding_artifact_digest_mismatch")
    return {
        "artifact_kind": str(kind),
        "artifact_id": artifact_id,
        "digest_mode": digest_mode,
        "binding_sha256": binding_sha256,
        "raw_sha256": raw_sha256,
    }


def _evidence_paths(values: Sequence[str]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for value in values:
        evidence_id, separator, path = value.partition("=")
        if not separator or not evidence_id or not path or evidence_id in paths:
            raise _CliBlock("evidence_artifact_binding_invalid")
        paths[evidence_id] = path
    return paths


def _evidence_receipt_rows(accepted: Mapping[str, Any]) -> list[dict[str, str]]:
    evidence = accepted["evidence"]
    if evidence["mode"] == "producer_verifier_replay":
        roles = ("producer", "verifier", "replay")
    elif evidence["mode"] == "source_separated_current_body" and all(
        field in evidence
        for field in ("source_receipt_sha256", "current_body_receipt_sha256")
    ):
        roles = ("source", "current_body", "comparison")
    else:
        raise _CliBlock("evidence_mode_not_artifact_verifiable")
    return [
        {
            "role": role,
            "receipt_id": str(evidence[f"{role}_receipt_id"]),
            "raw_sha256": str(evidence[f"{role}_receipt_sha256"]),
        }
        for role in roles
    ]


def _required_evidence_digests(
    accepted: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, str]]
) -> dict[str, str]:
    invariant = accepted["first_failing_invariant"]
    required = {str(invariant["evidence_id"]): str(invariant["evidence_sha256"])}
    for row in evidence_rows:
        evidence_id = row["receipt_id"]
        if evidence_id in required:
            raise _CliBlock("evidence_artifact_binding_ambiguous")
        required[evidence_id] = row["raw_sha256"]
    return required


def _verify_bound_artifacts(
    root: Path, receipt: Mapping[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    accepted = receipt["accepted_premise"]
    binding_artifact = _verify_current_binding(
        root, accepted["binding"], args.binding_artifact
    )
    subject_sha256 = _artifact_sha256(
        root, args.subject_artifact, "subject_artifact_unreadable"
    )
    if subject_sha256 != accepted["subject"]["content_sha256"]:
        raise _CliBlock("subject_artifact_digest_mismatch")
    baseline_subject = accepted["freshness"]["baseline_subject"]
    baseline_attestation = None
    if baseline_subject is None:
        if args.baseline_subject_artifact:
            raise _CliBlock("unexpected_baseline_subject_artifact")
    else:
        baseline_sha256 = _artifact_sha256(
            root,
            args.baseline_subject_artifact,
            "baseline_subject_artifact_unreadable",
        )
        if baseline_sha256 != baseline_subject["content_sha256"]:
            raise _CliBlock("baseline_subject_artifact_digest_mismatch")
        baseline_attestation = {
            "subject_id": str(baseline_subject["subject_id"]),
            "revision_id": str(baseline_subject["revision_id"]),
            "raw_sha256": baseline_sha256,
        }
    evidence = accepted["evidence"]
    evidence_rows = _evidence_receipt_rows(accepted)
    required = _required_evidence_digests(accepted, evidence_rows)
    source_attestation = None
    if evidence["mode"] == "source_separated_current_body":
        source_sha256 = _artifact_sha256(
            root,
            args.source_subject_artifact,
            "source_subject_artifact_unreadable",
        )
        if source_sha256 != evidence["source_content_sha256"]:
            raise _CliBlock("source_subject_artifact_digest_mismatch")
        source_attestation = {
            "source_identity": str(evidence["source_channel_id"]),
            "revision_id": str(evidence["source_revision_id"]),
            "raw_sha256": source_sha256,
        }
    elif args.source_subject_artifact:
        raise _CliBlock("unexpected_source_subject_artifact")
    paths = _evidence_paths(args.evidence_artifact)
    if set(paths) != set(required):
        raise _CliBlock("evidence_artifact_set_mismatch")
    for evidence_id, expected_sha256 in required.items():
        actual = _artifact_sha256(
            root, paths[evidence_id], "evidence_artifact_unreadable"
        )
        if actual != expected_sha256:
            raise _CliBlock("evidence_artifact_digest_mismatch")
    invariant = accepted["first_failing_invariant"]
    return {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_artifact_verification",
        "validator_policy": {
            "policy_id": "exact-subject-artifact-verifier",
            "policy_version": "1",
        },
        "workspace_file_validation": {
            "status": "verified",
            "workspace_local": True,
            "regular_non_symlink": True,
        },
        "current_binding_artifact": binding_artifact,
        "current_subject": {
            "subject_id": str(accepted["subject"]["subject_id"]),
            "revision_id": str(accepted["subject"]["revision_id"]),
            "raw_sha256": subject_sha256,
        },
        "freshness_baseline_subject": baseline_attestation,
        "source_subject": source_attestation,
        "invariant_evidence": {
            "evidence_id": str(invariant["evidence_id"]),
            "raw_sha256": str(invariant["evidence_sha256"]),
        },
        "evidence_receipts": evidence_rows,
        "source_body_persisted": False,
        "source_path_persisted": False,
    }


def _blocked(reason_code: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_kind": "exact_subject_premise_cli_failure",
        "status": "blocked",
        "reason_code": reason_code,
        "mutation_performed": False,
        "source_body_persisted": False,
        "source_path_persisted": False,
    }


def _validated_prior_receipts(
    values: Sequence[object],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[str]]:
    legacy_receipts: list[dict[str, Any]] = []
    verified_receipts: list[dict[str, Any]] = []
    legacy_consumed_replays: set[str] = set()
    try:
        for value in values:
            if (
                isinstance(value, Mapping)
                and value.get("artifact_kind")
                == "artifact_verified_exact_subject_premise_receipt"
            ):
                verified = validate_artifact_verified_exact_subject_premise_receipt(
                    value
                )
                verified_receipts.append(verified)
                legacy_receipts.append(verified["legacy_receipt"])
            else:
                legacy = validate_exact_subject_premise_receipt(value)
                legacy_receipts.append(legacy)
                if legacy["status"] == "consumed":
                    legacy_consumed_replays.add(legacy["replay_identity_sha256"])
    except ValueError as exc:
        raise _CliBlock("prior_receipt_contract_invalid") from exc
    return legacy_receipts, verified_receipts, legacy_consumed_replays


def _run(args: argparse.Namespace) -> dict[str, Any]:
    root = _workspace_root(args.root)
    context = _read_object(root, args.context, "context_input_unreadable")
    submission = _read_object(root, args.submission, "submission_input_unreadable")
    prior_values = [
        _read_object(root, path, "prior_receipt_input_unreadable")
        for path in args.prior_receipt
    ]
    prior_receipts, verified_priors, legacy_consumed_replays = (
        _validated_prior_receipts(prior_values)
    )
    try:
        result = validate_exact_subject_premise(
            submission,
            context=context,
            prior_receipts=prior_receipts,
        )
    except ValueError as exc:
        raise _CliBlock("premise_contract_invalid") from exc
    receipt = result["receipt"]
    if receipt["status"] == "consumed":
        replay_identity = str(receipt["replay_identity_sha256"])
        if replay_identity in legacy_consumed_replays:
            raise _CliBlock("consumed_prior_requires_artifact_verified_v2")
        attestation = _verify_bound_artifacts(root, receipt, args)
        sealed = seal_artifact_verified_receipt(receipt, attestation)
        matching_verified = [
            value
            for value in verified_priors
            if value["legacy_receipt"]["replay_identity_sha256"] == replay_identity
        ]
        if any(value != sealed for value in matching_verified):
            raise _CliBlock("artifact_verified_replay_conflict")
        receipt = sealed
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        output = _run(args)
    except _CliBlock as exc:
        output = _blocked(exc.reason_code)
        code = 2
    else:
        code = 0
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
