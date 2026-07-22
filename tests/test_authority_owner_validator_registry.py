from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from manage_agent_authority.canonical import object_sha256
from manage_agent_authority.owner_validators import (
    invoke_registered_owner_validator,
    load_owner_validation_receipt,
    publish_owner_validation_receipt,
    registered_owner_validator,
    validate_owner_validation_receipt,
)
from manage_agent_authority.canonical import sha256_file
from manage_agent_authority import owner_validation_io
from manage_agent_authority.owner_validation_io import (
    MAX_OWNER_VALIDATION_RECEIPT_BYTES,
)
from manage_agent_authority.owner_validator_process import (
    MAX_OWNER_VALIDATOR_STDOUT_BYTES,
    run_bounded_owner_validator,
)


ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def request() -> dict[str, object]:
    return {
        "skill_id": "manage-task-state-index",
        "skill_version": "2.0.0",
        "operation_id": "mutate_task_state_index",
        "operation_version": "1",
        "subject": {
            "kind": "task_index",
            "ref": ".task/index.jsonl",
            "digest": SHA_A,
            "revision": "revision-1",
        },
    }


def binding(ref: str, digest: str) -> dict[str, str]:
    return {"ref": ref, "sha256": digest}


def receipt() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "artifact_kind": "owner_validation_receipt",
        "validation_status": "valid",
        "outcome": "confirmed_effect",
        "operation": "mutate_task_state_index",
        "owner_result": binding(".task/results/owner.json", SHA_B),
        "reservation": binding(".task/authorization/reservations/r.json", SHA_C),
        "pre_commit_verification": binding(
            ".task/authorization/verifications/v.json", SHA_D
        ),
        "phase": "current",
        "subject": {
            "kind": "task_index",
            "ref": ".task/index.jsonl",
            "before_sha256": SHA_A,
            "after_sha256": SHA_B,
        },
        "event_batch": {
            "plan_id": "plan-1",
            "before_event_count": 10,
            "event_count": 2,
            "event_payload_sha256": SHA_C,
        },
        "descendant_event_count": 3,
        "validated_at": "2026-07-23T10:00:00+09:00",
    }
    value["receipt_sha256"] = object_sha256(value)
    return value


def test_registry_is_exact_and_does_not_accept_manifest_named_callables() -> None:
    spec = registered_owner_validator(request())
    assert spec.module == "manage_task_state_index"
    forged = {**request(), "operation_id": "workspace_supplied_callable"}
    with pytest.raises(SystemExit, match="No trusted owner-result validator"):
        registered_owner_validator(forged)


def test_common_owner_validation_receipt_binds_authority_inputs() -> None:
    value = receipt()
    validated = validate_owner_validation_receipt(
        value,
        request=request(),
        owner_result=value["owner_result"],  # type: ignore[arg-type]
        reservation=value["reservation"],  # type: ignore[arg-type]
        pre_commit_verification=value["pre_commit_verification"],  # type: ignore[arg-type]
        phase="current",
    )
    assert validated["outcome"] == "confirmed_effect"
    value["descendant_event_count"] = 4
    with pytest.raises(SystemExit, match="receipt_sha256"):
        validate_owner_validation_receipt(
            value,
            request=request(),
            owner_result=value["owner_result"],  # type: ignore[arg-type]
            reservation=value["reservation"],  # type: ignore[arg-type]
            pre_commit_verification=value["pre_commit_verification"],  # type: ignore[arg-type]
            phase="current",
        )


def test_registered_invocation_uses_fixed_module_and_command(tmp_path: Path) -> None:
    value = receipt()
    captured: dict[str, object] = {}

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(argv, 0, json.dumps(value), "")

    result = invoke_registered_owner_validator(
        tmp_path,
        request(),
        value["owner_result"],  # type: ignore[arg-type]
        value["reservation"],  # type: ignore[arg-type]
        value["pre_commit_verification"],  # type: ignore[arg-type]
        phase="current",
        skills_root=ROOT,
        runner=runner,
    )
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert argv[1:6] == ["-P", "-m", "manage_task_state_index", "index", "--root"]
    assert "validate-owner-result" in argv
    assert captured["cwd"] == ROOT
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONSAFEPATH"] == "1"
    assert result == value


def test_registered_invocation_cannot_import_workspace_shadow_package(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "workspace-shadow-ran"
    package = tmp_path / "manage_task_state_index"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('shadowed')\n",
        encoding="utf-8",
    )
    value = receipt()

    with pytest.raises(SystemExit):
        invoke_registered_owner_validator(
            tmp_path,
            request(),
            value["owner_result"],  # type: ignore[arg-type]
            value["reservation"],  # type: ignore[arg-type]
            value["pre_commit_verification"],  # type: ignore[arg-type]
            phase="current",
            skills_root=ROOT,
        )

    assert not marker.exists()


def test_registered_invocation_rejects_an_alternate_skills_root(
    tmp_path: Path,
) -> None:
    value = receipt()
    alternate = tmp_path / "alternate-skills"
    alternate.mkdir()

    with pytest.raises(SystemExit, match="co-located checked-in skills root"):
        invoke_registered_owner_validator(
            tmp_path,
            request(),
            value["owner_result"],  # type: ignore[arg-type]
            value["reservation"],  # type: ignore[arg-type]
            value["pre_commit_verification"],  # type: ignore[arg-type]
            phase="current",
            skills_root=alternate,
        )


def test_registered_invocation_rejects_oversized_custom_runner_output(
    tmp_path: Path,
) -> None:
    value = receipt()

    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            argv, 0, "x" * (MAX_OWNER_VALIDATOR_STDOUT_BYTES + 1), ""
        )

    with pytest.raises(SystemExit, match="output exceeds its safety limit"):
        invoke_registered_owner_validator(
            tmp_path,
            request(),
            value["owner_result"],  # type: ignore[arg-type]
            value["reservation"],  # type: ignore[arg-type]
            value["pre_commit_verification"],  # type: ignore[arg-type]
            phase="current",
            skills_root=ROOT,
            runner=runner,
        )


def test_default_validator_process_stops_at_stdout_limit(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.write('x' * "
        f"{MAX_OWNER_VALIDATOR_STDOUT_BYTES + 1})",
    ]

    with pytest.raises(SystemExit, match="stdout.*safety limit"):
        run_bounded_owner_validator(
            command,
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout=5,
        )


def test_owner_validation_loader_rejects_a_relocated_self_sealed_receipt(
    tmp_path: Path,
) -> None:
    value = receipt()
    canonical = publish_owner_validation_receipt(tmp_path, value)
    copied = tmp_path / ".task/authorization/copied-owner-validation.json"
    copied.parent.mkdir(parents=True, exist_ok=True)
    copied.write_bytes((tmp_path / canonical["ref"]).read_bytes())
    relocated = {
        "ref": copied.relative_to(tmp_path).as_posix(),
        "sha256": sha256_file(copied),
    }

    with pytest.raises(SystemExit, match="canonical receipt path"):
        load_owner_validation_receipt(
            tmp_path,
            relocated,
            request=request(),
            owner_result=value["owner_result"],  # type: ignore[arg-type]
            reservation=value["reservation"],  # type: ignore[arg-type]
            pre_commit_verification=value["pre_commit_verification"],  # type: ignore[arg-type]
        )


def test_owner_validation_loader_rejects_oversize_before_json_or_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seal = "e" * 64
    path = (
        tmp_path
        / ".task/authorization/owner_validations"
        / f"owner-validation-{seal}.json"
    )
    path.parent.mkdir(parents=True)
    payload = b"{" + b" " * MAX_OWNER_VALIDATION_RECEIPT_BYTES
    path.write_bytes(payload)
    artifact_before = path.read_bytes()
    json_called = False

    def forbidden_json_loads(_payload: object) -> object:
        nonlocal json_called
        json_called = True
        raise AssertionError("oversized receipt must fail before JSON parsing")

    monkeypatch.setattr(owner_validation_io.json, "loads", forbidden_json_loads)
    with pytest.raises(SystemExit, match="safety limit"):
        load_owner_validation_receipt(
            tmp_path,
            {
                "ref": path.relative_to(tmp_path).as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
            request=request(),
            owner_result=receipt()["owner_result"],  # type: ignore[arg-type]
            reservation=receipt()["reservation"],  # type: ignore[arg-type]
            pre_commit_verification=receipt()["pre_commit_verification"],  # type: ignore[arg-type]
        )

    assert json_called is False
    assert path.read_bytes() == artifact_before
