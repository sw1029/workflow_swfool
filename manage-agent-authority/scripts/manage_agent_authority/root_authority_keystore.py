"""Secure local key-store and RSA primitives for root authorization."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any

from .root_authority_registry import (
    SIGNATURE_ALGORITHM,
    sha256_bytes,
    spki_fingerprint,
)
from .root_grant_plan import _identifier
from .stable_store import read_regular


ROOT_AUTHORIZATION_ISSUER = "local-agent-managed-root-authorizer"
KEY_SIZE = 3072
PUBLIC_EXPONENT = 65537
KEY_ID = re.compile(r"^root-rsa-sha256-[0-9a-f]{64}$")
STORE_DIRECTORIES = ("private", "public", "passphrases", "receipts", "outbox")


def key_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not KEY_ID.fullmatch(normalized):
        raise SystemExit("Root authorization key ID is invalid.")
    return normalized


def mode(path: Path) -> str | None:
    try:
        return f"{stat.S_IMODE(path.lstat().st_mode):04o}"
    except FileNotFoundError:
        return None


def assert_directory(
    path: Path,
    *,
    exact_mode: int | None = None,
    reject_writable: bool = True,
) -> None:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise SystemExit(f"Secure directory is unavailable: {path}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or (reject_writable and stat.S_IMODE(observed.st_mode) & 0o022)
        or (
            exact_mode is not None
            and stat.S_IMODE(observed.st_mode) != exact_mode
        )
    ):
        raise SystemExit(f"Secure directory ownership or mode is invalid: {path}")


def _ensure_secure_directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        assert_directory(path, exact_mode=0o700)
        return
    assert_directory(path.parent, reject_writable=False)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    except OSError as exc:
        raise SystemExit(f"Could not create secure directory: {path}") from exc
    assert_directory(path, exact_mode=0o700)


def ensure_store_layout(root: Path, *directories: str) -> None:
    _ensure_secure_directory(root)
    for name in directories:
        if name not in STORE_DIRECTORIES:
            raise SystemExit("Unknown root-authorization store directory.")
        _ensure_secure_directory(root / name)


def paths(key_id_value: str, *, root: Path) -> dict[str, Path]:
    normalized = _identifier(key_id_value, "root authorization key ID")
    return {
        "private": (
            root
            / "private"
            / f"{normalized}.root-authorization-private.pem"
        ),
        "public": (
            root
            / "public"
            / f"{normalized}.root-authorization-public.pem"
        ),
        "passphrase": (
            root
            / "passphrases"
            / f"{normalized}.root-authorization-passphrase"
        ),
        "receipt": root / "receipts" / f"{normalized}.json",
    }


def assert_secure_file(
    path: Path,
    *,
    label: str,
    max_bytes: int,
) -> bytes:
    try:
        observed = path.lstat()
    except OSError as exc:
        raise SystemExit(f"Required {label} is unavailable.") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or stat.S_IMODE(observed.st_mode) != 0o600
    ):
        raise SystemExit(f"{label} ownership or mode is invalid.")
    payload = read_regular(path, label=label, max_bytes=max_bytes)
    assert payload is not None
    return payload


def assert_target_absent(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SystemExit(f"{label} target could not be inspected.") from exc
    raise SystemExit(f"{label} target already exists; refusing overwrite.")


def _cryptography() -> tuple[Any, Any, Any, Any]:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
    except ImportError as exc:
        raise SystemExit(
            "Root authorization administration requires cryptography>=44."
        ) from exc
    return hashes, serialization, padding, (rsa, InvalidSignature)


def public_record(
    public_key: Any,
    issuer: str,
) -> tuple[dict[str, Any], bytes, str]:
    _hashes, serialization, _padding, crypto_types = _cryptography()
    rsa, _invalid_signature = crypto_types
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise SystemExit("Root authorization public key must be RSA.")
    numbers = public_key.public_numbers()
    if public_key.key_size != KEY_SIZE or numbers.e != PUBLIC_EXPONENT:
        raise SystemExit(
            "Root authorization public key must be RSA-3072 with exponent 65537."
        )
    spki = public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    fingerprint = sha256_bytes(spki)
    record = {
        "key_id": f"root-rsa-sha256-{fingerprint}",
        "issuer": _identifier(issuer, "root authorization issuer"),
        "algorithm": SIGNATURE_ALGORITHM,
        "modulus_hex": numbers.n.to_bytes(KEY_SIZE // 8, "big").hex(),
        "public_exponent": numbers.e,
        "status": "active",
    }
    if spki_fingerprint(record["modulus_hex"], numbers.e) != fingerprint:
        raise SystemExit("Root authorization public-key identity self-check failed.")
    return record, spki, fingerprint


def load_public_key(payload: bytes) -> Any:
    _hashes, serialization, _padding, _crypto_types = _cryptography()
    try:
        return serialization.load_pem_public_key(payload)
    except (TypeError, ValueError) as exc:
        raise SystemExit("Root authorization public PEM is invalid.") from exc


def generate_key_material() -> tuple[Any, bytes, bytes, bytes, dict[str, Any], str]:
    hashes, serialization, padding, crypto_types = _cryptography()
    rsa, invalid_signature = crypto_types
    passphrase = secrets.token_urlsafe(64).encode("ascii")
    try:
        private_key = rsa.generate_private_key(
            public_exponent=PUBLIC_EXPONENT,
            key_size=KEY_SIZE,
        )
        private_pem = private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(passphrase),
        )
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        record, _spki, fingerprint = public_record(
            private_key.public_key(),
            ROOT_AUTHORIZATION_ISSUER,
        )
        reloaded = serialization.load_pem_private_key(
            private_pem,
            password=passphrase,
        )
        if (
            not isinstance(reloaded, rsa.RSAPrivateKey)
            or reloaded.public_key().public_numbers()
            != private_key.public_key().public_numbers()
        ):
            raise SystemExit("Generated root authorization key pair does not match.")
        message = b"root-authorization-key-self-test-v1\n"
        signature = reloaded.sign(message, padding.PKCS1v15(), hashes.SHA256())
        private_key.public_key().verify(
            signature,
            message,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except invalid_signature as exc:
        raise SystemExit("Generated root authorization key self-test failed.") from exc
    except (TypeError, ValueError) as exc:
        raise SystemExit("Generated root authorization key validation failed.") from exc
    return private_key, private_pem, public_pem, passphrase, record, fingerprint


def cleanup_created(created: list[Path]) -> None:
    for path in reversed(created):
        try:
            path.unlink()
        except (FileNotFoundError, OSError):
            pass


def render_receipt(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


__all__ = [
    "ROOT_AUTHORIZATION_ISSUER",
    "STORE_DIRECTORIES",
    "assert_directory",
    "assert_secure_file",
    "assert_target_absent",
    "cleanup_created",
    "ensure_store_layout",
    "generate_key_material",
    "key_id",
    "load_public_key",
    "mode",
    "paths",
    "public_record",
    "render_receipt",
]
