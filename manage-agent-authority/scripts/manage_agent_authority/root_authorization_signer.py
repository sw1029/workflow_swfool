"""Interactive exact-plan signer kept outside the ordinary authority CLI."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from .canonical import parse_time
from .root_authority_admin import (
    ROOT_AUTHORIZATION_HOME as ADMIN_ROOT_AUTHORIZATION_HOME,
)
from .root_authority_admin import (
    ROOT_AUTHORIZATION_ISSUER,
    assert_secure_file,
    key_paths,
)
from .root_authority_registry import (
    SIGNATURE_ALGORITHM,
    canonical_json,
    load_registry,
    sha256_bytes,
    spki_fingerprint,
)
from .root_authorization_evidence import (
    TRUST_ANCHOR_REGISTRY,
    validate_root_authorization_evidence,
)
from .root_grant_plan import load_root_approval_plan
from .root_tty import RootTTYError, confirm_exact, preflight
from .stable_store import read_regular


ROOT_AUTHORIZATION_HOME = ADMIN_ROOT_AUTHORIZATION_HOME
MAX_PRIVATE_KEY_BYTES = 32 * 1024
MAX_PASSPHRASE_BYTES = 4 * 1024


def _emit(value: dict[str, Any]) -> int:
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


def _digest(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if (
        len(normalized) != 64
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise SystemExit(f"{label} must be 64 lowercase hexadecimal characters.")
    return normalized


def _workspace(value: str) -> Path:
    raw = Path(str(value or ""))
    if not raw.is_absolute():
        raise SystemExit("Root authorization workspace must be absolute.")
    try:
        observed = raw.lstat()
    except OSError as exc:
        raise SystemExit("Root authorization workspace is unavailable.") from exc
    if raw.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        raise SystemExit("Root authorization workspace must be a real directory.")
    return raw.resolve()


def _summary(
    workspace: Path,
    binding: dict[str, str],
    plan: dict[str, Any],
) -> dict[str, Any]:
    grants = plan["approval_projection"]["grants"]
    return {
        "workspace": str(workspace),
        "approval_plan": binding,
        "plan_fingerprint": plan["plan_fingerprint"],
        "prepared_at": plan["prepared_at"],
        "expires_at": plan["approval_projection"]["validity"]["expires_at"],
        "grant_count": len(grants),
        "grants": [
            {
                "grant_id": grant["grant_id"],
                "holder_rank": grant["holder_rank"],
                "session_id": grant["session_id"],
                "task_id": grant["task_id"],
                "improvement_id": grant["improvement_id"],
                "capabilities": grant["capabilities"],
                "operations": grant["operations"],
                "subjects": grant["subjects"],
                "risk_ceiling": grant["risk_ceiling"],
                "cardinality": grant["cardinality"],
                "max_uses": grant["max_uses"],
            }
            for grant in grants
        ],
    }


def _tty_confirmation(summary: dict[str, Any], expected: str) -> str:
    try:
        confirm_exact(summary, expected)
    except RootTTYError as exc:
        raise SystemExit(exc.code) from exc
    return expected


def _cryptography() -> tuple[Any, Any, Any, Any]:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
    except ImportError as exc:
        raise SystemExit(
            "Root authorization signing requires cryptography>=44."
        ) from exc
    return hashes, serialization, padding, rsa


def _load_signing_key(key_id: str, anchor: dict[str, Any]) -> Any:
    hashes, serialization, padding, rsa = _cryptography()
    _ = hashes, padding
    paths = key_paths(key_id, root=ROOT_AUTHORIZATION_HOME)
    private_pem = assert_secure_file(
        paths["private"],
        label="root authorization private key",
        max_bytes=MAX_PRIVATE_KEY_BYTES,
    )
    passphrase = assert_secure_file(
        paths["passphrase"],
        label="root authorization passphrase",
        max_bytes=MAX_PASSPHRASE_BYTES,
    )
    public_pem = assert_secure_file(
        paths["public"],
        label="root authorization public key",
        max_bytes=MAX_PRIVATE_KEY_BYTES,
    )
    try:
        private_key = serialization.load_pem_private_key(
            private_pem,
            password=passphrase,
        )
        public_key = serialization.load_pem_public_key(public_pem)
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            "Root authorization signing key could not be unlocked."
        ) from exc
    if (
        not isinstance(private_key, rsa.RSAPrivateKey)
        or not isinstance(public_key, rsa.RSAPublicKey)
        or private_key.key_size != 3072
        or private_key.public_key().public_numbers() != public_key.public_numbers()
    ):
        raise SystemExit("Root authorization stored key pair does not match.")
    numbers = private_key.public_key().public_numbers()
    if (
        numbers.e != 65537
        or numbers.n.to_bytes(3072 // 8, "big").hex()
        != anchor["modulus_hex"]
        or numbers.e != anchor["public_exponent"]
    ):
        raise SystemExit(
            "Root authorization private key does not match the active registry."
        )
    return private_key


def _identifiers(
    workspace: Path,
    plan_binding: dict[str, str],
    key_id: str,
    decided_at: str,
) -> tuple[str, str]:
    seed = {
        "workspace_sha256": hashlib.sha256(
            str(workspace).encode("utf-8")
        ).hexdigest(),
        "approval_plan": plan_binding,
        "key_id": key_id,
        "decided_at": decided_at,
    }
    authorization = sha256_bytes(
        canonical_json({**seed, "id_kind": "authorization"})
    )
    evidence = sha256_bytes(
        canonical_json({**seed, "id_kind": "evidence"})
    )
    return (
        f"root-authorization-{authorization}",
        f"root-evidence-{evidence}",
    )


def _exclusive_outbox_write(path: Path, payload: bytes) -> None:
    parent = path.parent
    try:
        observed = parent.lstat()
    except OSError as exc:
        raise SystemExit("Root authorization outbox is unavailable.") from exc
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or stat.S_IMODE(observed.st_mode) != 0o700
    ):
        raise SystemExit("Root authorization outbox is unsafe.")
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        parent_descriptor = os.open(
            parent,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise SystemExit("Root authorization outbox is unsafe.") from exc
    try:
        descriptor = os.open(
            path.name,
            flags,
            0o600,
            dir_fd=parent_descriptor,
        )
    except FileExistsError as exc:
        os.close(parent_descriptor)
        raise SystemExit(
            "Root authorization outbox evidence already exists."
        ) from exc
    except OSError as exc:
        os.close(parent_descriptor)
        raise SystemExit(
            "Root authorization outbox evidence could not be created."
        ) from exc
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(parent_descriptor)
    except BaseException:
        try:
            os.unlink(path.name, dir_fd=parent_descriptor)
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)
        os.close(parent_descriptor)
    observed_payload = read_regular(
        path,
        label="root authorization outbox evidence",
        max_bytes=64 * 1024,
    )
    if observed_payload != payload:
        raise SystemExit("Root authorization outbox post-write bytes differ.")


def _ensure_outbox() -> Path:
    root = ROOT_AUTHORIZATION_HOME
    outbox = root / "outbox"
    for path in (root, outbox):
        if path.exists() or path.is_symlink():
            try:
                observed = path.lstat()
            except OSError as exc:
                raise SystemExit(
                    "Root authorization outbox path is unavailable."
                ) from exc
            if (
                path.is_symlink()
                or not stat.S_ISDIR(observed.st_mode)
                or observed.st_uid != os.geteuid()
                or stat.S_IMODE(observed.st_mode) != 0o700
            ):
                raise SystemExit("Root authorization outbox path is unsafe.")
            continue
        try:
            path.mkdir(mode=0o700)
        except OSError as exc:
            raise SystemExit(
                "Root authorization outbox path could not be created."
            ) from exc
    return outbox


def _active_anchor(
    loaded_registry: tuple[dict[str, Any], dict[str, dict[str, Any]], bytes, str],
    key_id: str,
) -> dict[str, Any]:
    anchor = loaded_registry[1].get(key_id)
    if (
        anchor is None
        or anchor["status"] != "active"
        or anchor["issuer"] != ROOT_AUTHORIZATION_ISSUER
        or key_id
        != (
            "root-rsa-sha256-"
            + spki_fingerprint(
                anchor["modulus_hex"],
                anchor["public_exponent"],
            )
        )
    ):
        raise SystemExit(
            "Root authorization key is not an active local signer key."
        )
    return anchor


def _assert_approval_window(plan: dict[str, Any], observed_at: str) -> None:
    observed = parse_time(observed_at, "root authorization decision time")
    prepared = parse_time(plan["prepared_at"], "root approval prepared_at")
    expires = parse_time(
        plan["approval_projection"]["validity"]["expires_at"],
        "root approval expires_at",
    )
    if observed < prepared or observed >= expires:
        raise SystemExit("Root approval plan is outside its approval window.")


def preflight_tty() -> dict[str, Any]:
    preflight()
    return {
        "authority_effects": False,
        "schema_version": 1,
        "status": "ready",
        "transport": "controlling_tty",
    }


def approve_root_plan(
    workspace: Path,
    *,
    approval_plan_ref: str,
    approval_plan_sha256: str,
    key_id: str,
) -> dict[str, Any]:
    root = _workspace(str(workspace))
    digest = _digest(approval_plan_sha256, "approval plan SHA-256")
    binding = {
        "ref": str(approval_plan_ref),
        "sha256": digest,
    }
    normalized_binding, plan = load_root_approval_plan(root, binding)
    if normalized_binding != binding:
        raise SystemExit("Root approval plan binding is not canonical.")
    loaded_registry = load_registry(TRUST_ANCHOR_REGISTRY)
    assert loaded_registry is not None
    anchor = _active_anchor(loaded_registry, key_id)
    registry_digest = loaded_registry[3]
    _assert_approval_window(plan, _utc_now())
    expected = f"APPROVE ROOT PLAN {digest}"
    if _tty_confirmation(_summary(root, binding, plan), expected) != expected:
        raise SystemExit("Root plan approval was not confirmed.")

    decided_at = _utc_now()
    normalized_binding_after, plan_after = load_root_approval_plan(root, binding)
    if normalized_binding_after != binding or plan_after != plan:
        raise SystemExit("Root approval plan changed during confirmation.")
    loaded_registry_after = load_registry(TRUST_ANCHOR_REGISTRY)
    assert loaded_registry_after is not None
    if loaded_registry_after[3] != registry_digest:
        raise SystemExit(
            "Root authorization registry changed during confirmation."
        )
    anchor_after = _active_anchor(loaded_registry_after, key_id)
    if anchor_after != anchor:
        raise SystemExit(
            "Root authorization registry changed during confirmation."
        )
    _assert_approval_window(plan_after, decided_at)

    private_key = _load_signing_key(key_id, anchor_after)
    loaded_registry_before_signing = load_registry(TRUST_ANCHOR_REGISTRY)
    assert loaded_registry_before_signing is not None
    if loaded_registry_before_signing[3] != registry_digest:
        raise SystemExit(
            "Root authorization registry changed during confirmation."
        )
    authorization_id, evidence_id = _identifiers(
        root,
        binding,
        key_id,
        decided_at,
    )
    unsigned = {
        "schema_version": 1,
        "artifact_kind": "authority_root_user_authorization_evidence",
        "audience": "manage-agent-authority/root-grant",
        "issuer": ROOT_AUTHORIZATION_ISSUER,
        "authorization_id": authorization_id,
        "approval_plan": binding,
        "approved": True,
        "decided_at": decided_at,
        "evidence_id": evidence_id,
    }
    hashes, _serialization, padding, _rsa = _cryptography()
    signature = private_key.sign(
        canonical_json(unsigned),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    evidence = {
        **unsigned,
        "signature": {
            "algorithm": SIGNATURE_ALGORITHM,
            "key_id": key_id,
            "value_base64": base64.b64encode(signature).decode("ascii"),
        },
    }
    normalized = validate_root_authorization_evidence(
        evidence,
        plan_binding=binding,
        plan=plan_after,
    )
    if normalized != evidence:
        raise SystemExit("Root authorization signer self-verification changed bytes.")
    payload = canonical_json(evidence)
    outbox = _ensure_outbox()
    path = outbox / f"{evidence_id}.json"
    _exclusive_outbox_write(path, payload)
    return {
        "approval_plan": binding,
        "evidence_path": str(path),
        "evidence_sha256": sha256_bytes(payload),
        "key_id": key_id,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="root_authorization_signer")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight-tty")
    approve = subparsers.add_parser("approve-root-plan")
    approve.add_argument("--workspace", required=True)
    approve.add_argument("--approval-plan-ref", required=True)
    approve.add_argument("--approval-plan-sha256", required=True)
    approve.add_argument("--key-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "preflight-tty":
        try:
            return _emit(preflight_tty())
        except RootTTYError as exc:
            sys.stderr.write(f"{exc.code}\n")
            return 2
    if args.command != "approve-root-plan":
        raise SystemExit("Unknown root authorization signer command.")
    return _emit(
        approve_root_plan(
            Path(args.workspace),
            approval_plan_ref=args.approval_plan_ref,
            approval_plan_sha256=args.approval_plan_sha256,
            key_id=args.key_id,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ROOT_AUTHORIZATION_HOME",
    "approve_root_plan",
    "build_parser",
    "main",
    "preflight_tty",
]
