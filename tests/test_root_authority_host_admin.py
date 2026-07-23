from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
import stat

import pytest
from cryptography.hazmat.primitives import serialization

from manage_agent_authority import root_authority_admin as admin
from manage_agent_authority import root_authority_registry as registry
from manage_agent_authority import root_authorization_signer as signer
from root_tty_test_support import run_with_tty


def _register_worker(
    trust: str,
    store: str,
    public_pem: bytes,
    expected: str,
    queue: multiprocessing.Queue,
) -> None:
    admin.TRUST_ANCHOR_REGISTRY = Path(trust)
    admin.ROOT_AUTHORIZATION_HOME = Path(store)
    try:
        result = admin.register_public_key(
            public_pem,
            issuer=admin.ROOT_AUTHORIZATION_ISSUER,
            expected_registry_sha256=expected,
            rotation_overlap=True,
        )
    except SystemExit as exc:
        queue.put(("error", str(exc)))
    else:
        queue.put(("ok", result["registry_sha256_after"]))


@pytest.fixture
def host_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, str]:
    host = tmp_path / "host"
    host.mkdir(mode=0o700)
    trust = host / "root-authorization.trust.json"
    payload = registry.canonical_json(registry.empty_registry())
    trust.write_bytes(payload)
    trust.chmod(0o600)
    store = host / "root-authorization"
    monkeypatch.setattr(admin, "TRUST_ANCHOR_REGISTRY", trust)
    monkeypatch.setattr(admin, "ROOT_AUTHORIZATION_HOME", store)
    return trust, store, registry.sha256_bytes(payload)


def test_provision_encrypts_pair_and_records_only_public_receipt(
    host_registry: tuple[Path, Path, str],
) -> None:
    trust, store, initial_digest = host_registry

    result = admin.provision(expected_registry_sha256=initial_digest)
    paths = admin.key_paths(result["key_id"], root=store)
    private_pem = paths["private"].read_bytes()
    passphrase = paths["passphrase"].read_bytes()
    public_pem = paths["public"].read_bytes()

    assert b"ENCRYPTED PRIVATE KEY" in private_pem
    with pytest.raises((TypeError, ValueError)):
        serialization.load_pem_private_key(
            private_pem,
            password=b"wrong-passphrase",
        )
    private_key = serialization.load_pem_private_key(
        private_pem,
        password=passphrase,
    )
    public_key = serialization.load_pem_public_key(public_pem)
    assert private_key.public_key().public_numbers() == public_key.public_numbers()
    assert private_key.key_size == 3072
    assert public_key.public_numbers().e == 65537

    for path in (store, *(store / name for name in admin.STORE_DIRECTORIES[:4])):
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
    for path in paths.values():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    receipt = json.loads(paths["receipt"].read_text(encoding="utf-8"))
    rendered = json.dumps(receipt, sort_keys=True)
    assert passphrase.decode("ascii") not in rendered
    assert "PRIVATE KEY" not in rendered
    assert receipt["custody_mode"] == "agent_managed_local_bootstrap"
    assert receipt["security_boundary"] == (
        "same_os_user_not_independent_isolation"
    )
    assert registry.sha256_bytes(trust.read_bytes()) == result[
        "registry_sha256_after"
    ]


def test_register_replay_rotation_cas_and_revocation_are_fail_closed(
    host_registry: tuple[Path, Path, str],
) -> None:
    _trust, store, initial_digest = host_registry
    first = admin.provision(expected_registry_sha256=initial_digest)
    first_public = admin.key_paths(first["key_id"], root=store)[
        "public"
    ].read_bytes()

    replay = admin.register_public_key(
        first_public,
        issuer=admin.ROOT_AUTHORIZATION_ISSUER,
        expected_registry_sha256=first["registry_sha256_after"],
    )
    assert replay["status"] == "already_registered"
    assert replay["registry_sha256_after"] == first["registry_sha256_after"]
    with pytest.raises(SystemExit, match="CAS mismatch"):
        admin.register_public_key(
            first_public,
            issuer=admin.ROOT_AUTHORIZATION_ISSUER,
            expected_registry_sha256=initial_digest,
        )
    with pytest.raises(SystemExit, match="issuer cannot change"):
        admin.register_public_key(
            first_public,
            issuer="different-root-issuer",
            expected_registry_sha256=first["registry_sha256_after"],
        )

    generated = admin._generate_key_material()  # noqa: SLF001
    second_public = generated[2]
    with pytest.raises(SystemExit, match="rotation overlap"):
        admin.register_public_key(
            second_public,
            issuer=admin.ROOT_AUTHORIZATION_ISSUER,
            expected_registry_sha256=first["registry_sha256_after"],
        )
    second = admin.register_public_key(
        second_public,
        issuer=admin.ROOT_AUTHORIZATION_ISSUER,
        expected_registry_sha256=first["registry_sha256_after"],
        rotation_overlap=True,
    )
    confirmation = (
        f"REVOKE {first['key_id']} AND INVALIDATE EXISTING EVIDENCE"
    )
    revocation = run_with_tty(
        lambda: admin.revoke_public_key(
            first["key_id"],
            reason="rotation-complete",
            expected_registry_sha256=second["registry_sha256_after"],
        ),
        input_bytes=(confirmation + "\n").encode("utf-8"),
    )
    assert revocation.status == "ok"
    revoked = revocation.value
    assert revoked["status"] == "revoked"
    assert revoked["existing_evidence_valid_on_future_verification"] is False
    with pytest.raises(SystemExit, match="cannot be reactivated"):
        admin.register_public_key(
            first_public,
            issuer=admin.ROOT_AUTHORIZATION_ISSUER,
            expected_registry_sha256=revoked["registry_sha256_after"],
            rotation_overlap=True,
        )


def test_provision_rejects_symlink_store_and_cleans_partial_files(
    host_registry: tuple[Path, Path, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _trust, store, initial_digest = host_registry
    unsafe_target = tmp_path / "unsafe"
    unsafe_target.mkdir()
    store.symlink_to(unsafe_target, target_is_directory=True)
    with pytest.raises(SystemExit, match="ownership or mode"):
        admin.provision(expected_registry_sha256=initial_digest)

    store.unlink()
    material = admin._generate_key_material()  # noqa: SLF001
    monkeypatch.setattr(admin, "_generate_key_material", lambda: material)

    def fail_registry(_keys: list[dict[str, object]]) -> str:
        raise SystemExit("injected registry failure")

    monkeypatch.setattr(admin, "_replace_registry", fail_registry)
    with pytest.raises(SystemExit, match="injected registry failure"):
        admin.provision(expected_registry_sha256=initial_digest)
    paths = admin.key_paths(material[4]["key_id"], root=store)
    assert all(not path.exists() for path in paths.values())


def test_registry_rejects_noncanonical_and_group_writable_files(
    host_registry: tuple[Path, Path, str],
) -> None:
    trust, _store, _initial_digest = host_registry
    trust.write_text(json.dumps(registry.empty_registry()), encoding="utf-8")
    with pytest.raises(SystemExit, match="not canonical"):
        admin.status()

    trust.write_bytes(registry.canonical_json(registry.empty_registry()))
    trust.chmod(0o622)
    with pytest.raises(SystemExit, match="unsafe"):
        admin.status()


def test_registry_concurrent_writers_allow_one_cas_winner(
    host_registry: tuple[Path, Path, str],
) -> None:
    trust, store, initial_digest = host_registry
    first_public = admin._generate_key_material()[2]  # noqa: SLF001
    second_public = admin._generate_key_material()[2]  # noqa: SLF001
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    processes = [
        context.Process(
            target=_register_worker,
            args=(
                str(trust),
                str(store),
                public_pem,
                initial_digest,
                queue,
            ),
        )
        for public_pem in (first_public, second_public)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0
    results = [queue.get(timeout=2) for _process in processes]
    assert sorted(kind for kind, _detail in results) == ["error", "ok"]
    assert any("CAS mismatch" in detail for kind, detail in results if kind == "error")
    loaded = registry.load_registry(trust)
    assert loaded is not None
    assert len(loaded[0]["keys"]) == 1


def test_admin_parser_has_no_secret_input_options() -> None:
    parser = admin.build_parser()
    option_strings = {
        option
        for action in parser._actions  # noqa: SLF001
        for option in action.option_strings
    }
    assert "--private-key" not in option_strings
    assert "--passphrase" not in option_strings

    signer_parser = signer.build_parser()
    base = [
        "approve-root-plan",
        "--workspace",
        "/tmp/workspace",
        "--approval-plan-ref",
        ".task/plan.json",
        "--approval-plan-sha256",
        "0" * 64,
        "--key-id",
        "root-rsa-sha256-" + ("1" * 64),
    ]
    for forbidden in (
        "--yes",
        "--stdin",
        "--confirmation",
        "--approval-text",
        "--tty-path",
        "--private-key",
        "--passphrase",
        "--registry",
        "--issuer",
        "--audience",
        "--approved",
        "--signature",
        "--decided-at",
    ):
        with pytest.raises(SystemExit):
            signer_parser.parse_args([*base, forbidden])
