"""Provision and administer host-local root-authorization keys.

This module is intentionally separate from the ordinary authority workflow CLI.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

from .root_authority_keystore import (
    ROOT_AUTHORIZATION_ISSUER,
    STORE_DIRECTORIES,
    assert_directory as _assert_directory,
    assert_secure_file,
    assert_target_absent as _assert_target_absent,
    cleanup_created as _cleanup_created,
    ensure_store_layout as _ensure_store_layout,
    generate_key_material as _generate_key_material,
    key_id as _key_id,
    load_public_key as _load_public_key,
    mode as _mode,
    paths as _key_paths,
    public_record as _public_record,
    render_receipt as render_registry_receipt,
)
from .root_authority_registry import (
    load_registry,
    render_registry,
    sha256_bytes,
    spki_fingerprint,
)
from .root_grant_plan import _identifier
from .root_tty import RootTTYError, confirm_exact
from .stable_store import atomic_replace, locked_file, publish_immutable, read_regular


SKILL_ROOT = Path(__file__).resolve().parents[2]
CODEX_HOME = SKILL_ROOT.parent.parent
ROOT_AUTHORIZATION_HOME = CODEX_HOME / "root-authorization"
TRUST_ANCHOR_REGISTRY = SKILL_ROOT / "root-authorization.trust.json"
CUSTODY_MODE = "agent_managed_local_bootstrap"
EXPECTED_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _emit(value: Any) -> int:
    json.dump(
        value,
        sys.stdout,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    sys.stdout.write("\n")
    return 0


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _expected_digest(value: str, *, allow_absent: bool = True) -> str:
    normalized = str(value or "").strip()
    if allow_absent and normalized == "absent":
        return normalized
    if not EXPECTED_DIGEST.fullmatch(normalized):
        expected = "<64 lowercase hex>"
        if allow_absent:
            expected += " or absent"
        raise SystemExit(
            f"Expected registry SHA-256 must be {expected}."
        )
    return normalized


def ensure_store_layout(*directories: str) -> None:
    _ensure_store_layout(ROOT_AUTHORIZATION_HOME, *directories)


def key_paths(
    key_id: str,
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    store = ROOT_AUTHORIZATION_HOME if root is None else root
    return _key_paths(key_id, root=store)


def _lock_path() -> Path:
    return TRUST_ANCHOR_REGISTRY.with_name("root-authorization.trust.lock")


def _assert_registry_parent() -> None:
    _assert_directory(TRUST_ANCHOR_REGISTRY.parent)


def _assert_lock_file() -> None:
    path = _lock_path()
    try:
        observed = path.lstat()
    except OSError as exc:
        raise SystemExit("Root authorization registry lock is unavailable.") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or stat.S_IMODE(observed.st_mode) != 0o600
    ):
        raise SystemExit("Root authorization registry lock is unsafe.")


def _registry_state() -> tuple[list[dict[str, Any]], str]:
    loaded = load_registry(TRUST_ANCHOR_REGISTRY, required=False)
    if loaded is None:
        return [], "absent"
    value, _entries, _payload, digest = loaded
    return list(value["keys"]), digest


def _check_cas(expected: str, observed: str) -> None:
    if expected != observed:
        raise SystemExit(
            "Root authorization registry CAS mismatch; reload status and retry."
        )


def _replace_registry(keys: list[dict[str, Any]]) -> str:
    payload = render_registry(keys)
    atomic_replace(TRUST_ANCHOR_REGISTRY, payload, mode=0o600)
    loaded = load_registry(TRUST_ANCHOR_REGISTRY)
    assert loaded is not None
    if loaded[2] != payload:
        raise SystemExit("Root authorization registry post-write bytes differ.")
    return loaded[3]


def _registration_result(
    current: list[dict[str, Any]],
    record: dict[str, Any],
    *,
    rotation_overlap: bool,
) -> tuple[list[dict[str, Any]], bool]:
    for existing in current:
        same_material = (
            existing["modulus_hex"] == record["modulus_hex"]
            and existing["public_exponent"] == record["public_exponent"]
        )
        if existing["key_id"] == record["key_id"]:
            if not same_material:
                raise SystemExit("Root authorization key-ID collision detected.")
            if existing["issuer"] != record["issuer"]:
                raise SystemExit(
                    "Root authorization key issuer cannot change on replay."
                )
            if existing["status"] == "revoked":
                raise SystemExit(
                    "A revoked root authorization key cannot be reactivated."
                )
            return current, False
        if same_material:
            raise SystemExit(
                "Duplicate root authorization public key has a different key ID."
            )
    if (
        any(item["status"] == "active" for item in current)
        and not rotation_overlap
    ):
        raise SystemExit(
            "A second active root key requires explicit rotation overlap mode."
        )
    return sorted([*current, record], key=lambda item: item["key_id"]), True


def _file_status(path: Path) -> dict[str, Any]:
    try:
        observed = path.lstat()
    except FileNotFoundError:
        return {"exists": False, "mode": None}
    except OSError:
        return {"exists": True, "mode": "unreadable"}
    return {
        "exists": True,
        "mode": f"{stat.S_IMODE(observed.st_mode):04o}",
    }


def status() -> dict[str, Any]:
    loaded = load_registry(TRUST_ANCHOR_REGISTRY, required=False)
    if loaded is None:
        digest = "absent"
        keys: list[dict[str, Any]] = []
    else:
        value, _entries, _payload, digest = loaded
        keys = list(value["keys"])
    rendered = []
    for key in keys:
        paths = key_paths(key["key_id"])
        rendered.append(
            {
                "key_id": key["key_id"],
                "issuer": key["issuer"],
                "status": key["status"],
                "fingerprint_sha256": spki_fingerprint(
                    key["modulus_hex"],
                    key["public_exponent"],
                ),
                "files": {
                    name: _file_status(path)
                    for name, path in paths.items()
                },
            }
        )
    return {
        "registry_sha256": digest,
        "custody_mode": CUSTODY_MODE,
        "security_boundary": "same_os_user_not_independent_isolation",
        "keys": rendered,
    }


def register_public_key(
    public_pem: bytes,
    *,
    issuer: str,
    expected_registry_sha256: str,
    rotation_overlap: bool = False,
) -> dict[str, Any]:
    expected = _expected_digest(expected_registry_sha256)
    record, _spki, fingerprint = _public_record(
        _load_public_key(public_pem),
        issuer,
    )
    _assert_registry_parent()
    with locked_file(_lock_path()):
        _assert_lock_file()
        current, before = _registry_state()
        _check_cas(expected, before)
        updated, changed = _registration_result(
            current,
            record,
            rotation_overlap=rotation_overlap,
        )
        after = _replace_registry(updated) if changed else before
    return {
        "status": "registered" if changed else "already_registered",
        "key_id": record["key_id"],
        "issuer": record["issuer"],
        "fingerprint_sha256": fingerprint,
        "registry_sha256_before": before,
        "registry_sha256_after": after,
        "rotation_overlap": rotation_overlap,
    }


def provision(
    *,
    expected_registry_sha256: str,
    rotation_overlap: bool = False,
) -> dict[str, Any]:
    expected = _expected_digest(expected_registry_sha256)
    _assert_registry_parent()
    ensure_store_layout("private", "public", "passphrases", "receipts")
    created: list[Path] = []
    registry_committed = False
    with locked_file(_lock_path()):
        _assert_lock_file()
        current, before = _registry_state()
        _check_cas(expected, before)
        (
            _private_key,
            private_pem,
            public_pem,
            passphrase,
            record,
            fingerprint,
        ) = _generate_key_material()
        updated, changed = _registration_result(
            current,
            record,
            rotation_overlap=rotation_overlap,
        )
        if not changed:
            raise SystemExit("Generated root authorization key unexpectedly replays.")
        after_payload = render_registry(updated)
        after = sha256_bytes(after_payload)
        paths = key_paths(record["key_id"])
        for label, path in paths.items():
            _assert_target_absent(path, f"root authorization {label}")
        receipt = {
            "schema_version": 1,
            "artifact_kind": "root_authorization_provisioning_receipt",
            "key_id": record["key_id"],
            "issuer": record["issuer"],
            "algorithm": record["algorithm"],
            "fingerprint_sha256": fingerprint,
            "custody_mode": CUSTODY_MODE,
            "security_boundary": "same_os_user_not_independent_isolation",
            "provisioned_at": _utc_now(),
            "registry_sha256_before": before,
            "registry_sha256_after": after,
            "files": {
                name: str(path)
                for name, path in paths.items()
                if name != "receipt"
            },
        }
        payloads = (
            (paths["private"], private_pem),
            (paths["public"], public_pem),
            (paths["passphrase"], passphrase),
            (paths["receipt"], render_registry_receipt(receipt)),
        )
        try:
            for path, payload in payloads:
                if not publish_immutable(path, payload, mode=0o600):
                    raise SystemExit(
                        "Root authorization key target appeared during provisioning."
                    )
                created.append(path)
            observed_after = _replace_registry(updated)
            if observed_after != after:
                raise SystemExit(
                    "Root authorization registry digest differs from prepared receipt."
                )
            registry_committed = True
        finally:
            if not registry_committed:
                _cleanup_created(created)
    return {
        "status": "provisioned",
        "key_id": record["key_id"],
        "issuer": record["issuer"],
        "fingerprint_sha256": fingerprint,
        "custody_mode": CUSTODY_MODE,
        "security_boundary": "same_os_user_not_independent_isolation",
        "registry_sha256_before": before,
        "registry_sha256_after": after,
        "files": {
            name: {
                "path": str(path),
                "mode": _mode(path),
            }
            for name, path in paths.items()
        },
    }


def _tty_confirmation(expected: str) -> str:
    try:
        confirm_exact(None, expected)
    except RootTTYError as exc:
        raise SystemExit(exc.code) from exc
    return expected


def revoke_public_key(
    key_id: str,
    *,
    reason: str,
    expected_registry_sha256: str,
) -> dict[str, Any]:
    normalized_key_id = _key_id(key_id)
    normalized_reason = _identifier(reason, "root authorization revocation reason")
    expected = _expected_digest(
        expected_registry_sha256,
        allow_absent=False,
    )
    _assert_registry_parent()
    current, observed = _registry_state()
    _check_cas(expected, observed)
    by_id = {item["key_id"]: item for item in current}
    target = by_id.get(normalized_key_id)
    if target is None:
        raise SystemExit("Root authorization key is not registered.")
    if target["status"] == "revoked":
        return {
            "status": "already_revoked",
            "key_id": normalized_key_id,
            "reason": normalized_reason,
            "registry_sha256_before": observed,
            "registry_sha256_after": observed,
        }
    confirmation = (
        f"REVOKE {normalized_key_id} AND INVALIDATE EXISTING EVIDENCE"
    )
    if _tty_confirmation(confirmation) != confirmation:
        raise SystemExit("Root authorization key revocation was not confirmed.")
    with locked_file(_lock_path()):
        _assert_lock_file()
        current, before = _registry_state()
        _check_cas(expected, before)
        updated = [
            {**item, "status": "revoked"}
            if item["key_id"] == normalized_key_id
            else item
            for item in current
        ]
        after = _replace_registry(updated)
    return {
        "status": "revoked",
        "key_id": normalized_key_id,
        "reason": normalized_reason,
        "registry_sha256_before": before,
        "registry_sha256_after": after,
        "existing_evidence_valid_on_future_verification": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="root_authority_admin")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")

    provision_parser = subparsers.add_parser("provision")
    provision_parser.add_argument("--expected-registry-sha256", required=True)
    provision_parser.add_argument("--rotation-overlap", action="store_true")

    register_parser = subparsers.add_parser("register-public-key")
    register_parser.add_argument("--public-key", required=True)
    register_parser.add_argument("--issuer", required=True)
    register_parser.add_argument("--expected-registry-sha256", required=True)
    register_parser.add_argument("--rotation-overlap", action="store_true")

    revoke_parser = subparsers.add_parser("revoke-public-key")
    revoke_parser.add_argument("--key-id", required=True)
    revoke_parser.add_argument("--reason", required=True)
    revoke_parser.add_argument("--expected-registry-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        return _emit(status())
    if args.command == "provision":
        return _emit(
            provision(
                expected_registry_sha256=args.expected_registry_sha256,
                rotation_overlap=args.rotation_overlap,
            )
        )
    if args.command == "register-public-key":
        path = Path(args.public_key).absolute()
        payload = read_regular(
            path,
            label="root authorization public PEM",
            max_bytes=64 * 1024,
        )
        assert payload is not None
        return _emit(
            register_public_key(
                payload,
                issuer=args.issuer,
                expected_registry_sha256=args.expected_registry_sha256,
                rotation_overlap=args.rotation_overlap,
            )
        )
    if args.command == "revoke-public-key":
        return _emit(
            revoke_public_key(
                args.key_id,
                reason=args.reason,
                expected_registry_sha256=args.expected_registry_sha256,
            )
        )
    raise SystemExit("Unknown root authority administration command.")


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CUSTODY_MODE",
    "ROOT_AUTHORIZATION_HOME",
    "ROOT_AUTHORIZATION_ISSUER",
    "STORE_DIRECTORIES",
    "TRUST_ANCHOR_REGISTRY",
    "assert_secure_file",
    "build_parser",
    "ensure_store_layout",
    "key_paths",
    "main",
    "provision",
    "register_public_key",
    "revoke_public_key",
    "status",
]
