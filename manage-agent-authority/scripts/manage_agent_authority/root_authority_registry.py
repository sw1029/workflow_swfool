"""Closed host-local trust-registry parsing shared by verifier and admin."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from .stable_store import read_regular


MAX_TRUST_REGISTRY_BYTES = 64 * 1024
SIGNATURE_ALGORITHM = "rsassa-pkcs1-v1_5-sha256"
TRUST_REGISTRY_KEYS = {"schema_version", "artifact_kind", "keys"}
TRUST_KEY_KEYS = {
    "key_id",
    "issuer",
    "algorithm",
    "modulus_hex",
    "public_exponent",
    "status",
}


def canonical_json(value: Any) -> bytes:
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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identifier(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > 128
        or "*" in normalized
        or "/" in normalized
    ):
        raise SystemExit(f"{label} must be a bounded exact identifier.")
    return normalized


def _der_length(length: int) -> bytes:
    if length < 0:
        raise ValueError("DER length must not be negative")
    if length < 128:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def _der_value(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _der_length(len(value)) + value


def _der_integer(value: int) -> bytes:
    if value < 0:
        raise ValueError("DER integer must not be negative")
    encoded = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    if encoded[0] & 0x80:
        encoded = b"\x00" + encoded
    return _der_value(0x02, encoded)


def spki_der(modulus_hex: str, exponent: int) -> bytes:
    """Render the RSA SubjectPublicKeyInfo DER used for stable key identity."""

    rsa_public_key = _der_value(
        0x30,
        _der_integer(int(modulus_hex, 16)) + _der_integer(exponent),
    )
    rsa_encryption = bytes.fromhex("300d06092a864886f70d0101010500")
    return _der_value(
        0x30,
        rsa_encryption + _der_value(0x03, b"\x00" + rsa_public_key),
    )


def spki_fingerprint(modulus_hex: str, exponent: int) -> str:
    return sha256_bytes(spki_der(modulus_hex, exponent))


def empty_registry() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_kind": "authority_root_authorization_trust_anchors",
        "keys": [],
    }


def render_registry(keys: list[dict[str, Any]]) -> bytes:
    ordered = sorted(keys, key=lambda item: str(item["key_id"]))
    return canonical_json(
        {
            "schema_version": 1,
            "artifact_kind": "authority_root_authorization_trust_anchors",
            "keys": ordered,
        }
    )


def parse_registry(payload: bytes) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "Root authorization trust-anchor registry is unreadable."
        ) from exc
    try:
        canonical_payload = canonical_json(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            "Root authorization trust-anchor registry is not canonical."
        ) from exc
    if (
        not isinstance(value, dict)
        or set(value) != TRUST_REGISTRY_KEYS
        or value.get("schema_version") != 1
        or value.get("artifact_kind")
        != "authority_root_authorization_trust_anchors"
        or payload != canonical_payload
        or not isinstance(value.get("keys"), list)
    ):
        raise SystemExit(
            "Root authorization trust-anchor registry is not canonical."
        )
    if value["keys"] != sorted(
        value["keys"],
        key=lambda item: str(item.get("key_id", ""))
        if isinstance(item, dict)
        else "",
    ):
        raise SystemExit("Root authorization trust-anchor keys are not sorted.")

    result: dict[str, dict[str, Any]] = {}
    public_material: set[tuple[str, int]] = set()
    for index, key in enumerate(value["keys"]):
        if (
            not isinstance(key, dict)
            or set(key) != TRUST_KEY_KEYS
            or key.get("algorithm") != SIGNATURE_ALGORITHM
            or key.get("status") not in {"active", "revoked"}
            or not isinstance(key.get("public_exponent"), int)
            or isinstance(key.get("public_exponent"), bool)
        ):
            raise SystemExit(
                f"Root authorization trust anchor {index} is invalid."
            )
        key_id = _identifier(
            key.get("key_id"),
            f"root authorization trust anchor {index} key_id",
        )
        issuer = _identifier(
            key.get("issuer"),
            f"root authorization trust anchor {index} issuer",
        )
        modulus_hex = str(key.get("modulus_hex") or "")
        exponent = key["public_exponent"]
        if (
            len(modulus_hex) < 512
            or len(modulus_hex) % 2
            or any(character not in "0123456789abcdef" for character in modulus_hex)
            or exponent < 3
            or exponent % 2 == 0
        ):
            raise SystemExit(
                f"Root authorization trust anchor {index} key material is invalid."
            )
        material = (modulus_hex, exponent)
        if key_id in result:
            raise SystemExit("Root authorization trust-anchor IDs are not unique.")
        if material in public_material:
            raise SystemExit(
                "Root authorization trust-anchor public keys are not unique."
            )
        normalized = {
            **key,
            "key_id": key_id,
            "issuer": issuer,
            "modulus_hex": modulus_hex,
        }
        result[key_id] = normalized
        public_material.add(material)
    return value, result


def _secure_path(path: Path) -> None:
    parent = path.parent
    try:
        parent_stat = parent.lstat()
    except OSError as exc:
        raise SystemExit(
            "Root authorization trust-anchor registry parent is unavailable."
        ) from exc
    if (
        parent.is_symlink()
        or not stat.S_ISDIR(parent_stat.st_mode)
        or parent_stat.st_uid != os.geteuid()
        or stat.S_IMODE(parent_stat.st_mode) & 0o022
    ):
        raise SystemExit(
            "Root authorization trust-anchor registry parent is unsafe."
        )
    try:
        file_stat = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SystemExit(
            "Root authorization trust-anchor registry is unavailable."
        ) from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(file_stat.st_mode)
        or file_stat.st_uid != os.geteuid()
        or stat.S_IMODE(file_stat.st_mode) & 0o022
    ):
        raise SystemExit("Root authorization trust-anchor registry is unsafe.")


def load_registry(
    path: Path,
    *,
    required: bool = True,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], bytes, str] | None:
    _secure_path(path)
    payload = read_regular(
        path,
        required=required,
        label="root authorization trust-anchor registry",
        max_bytes=MAX_TRUST_REGISTRY_BYTES,
    )
    if payload is None:
        return None
    value, entries = parse_registry(payload)
    _secure_path(path)
    return value, entries, payload, sha256_bytes(payload)


__all__ = [
    "MAX_TRUST_REGISTRY_BYTES",
    "SIGNATURE_ALGORITHM",
    "TRUST_KEY_KEYS",
    "TRUST_REGISTRY_KEYS",
    "canonical_json",
    "empty_registry",
    "load_registry",
    "parse_registry",
    "render_registry",
    "sha256_bytes",
    "spki_der",
    "spki_fingerprint",
]
