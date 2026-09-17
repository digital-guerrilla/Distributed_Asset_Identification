"""Authenticated encryption and content-addressed fragment envelopes.

This module deliberately does not implement quorum placement. It provides the
cryptographic primitive used by a future fragment network: storage nodes can
hold encrypted fragments and verify integrity without possessing the key.
"""

import base64
import hashlib
import os
from dataclasses import dataclass

import nacl.secret


@dataclass(frozen=True)
class EncryptedFragment:
    index: int
    nonce: bytes
    ciphertext: bytes
    sha256: str


@dataclass(frozen=True)
class EncryptedManifest:
    content_sha256: str
    encrypted_content_sha256: str
    chunk_size: int
    fragment_count: int
    fragments: tuple[dict[str, object], ...]


def _gf_mul(left: int, right: int) -> int:
    result = 0
    while right:
        if right & 1:
            result ^= left
        left = (left << 1) ^ (0x11B if left & 0x80 else 0)
        right >>= 1
    return result


def _gf_pow(value: int, exponent: int) -> int:
    result = 1
    while exponent:
        if exponent & 1:
            result = _gf_mul(result, value)
        value = _gf_mul(value, value)
        exponent >>= 1
    return result


def split_key(key: bytes, share_count: int, threshold: int) -> list[bytes]:
    if len(key) != nacl.secret.SecretBox.KEY_SIZE:
        raise ValueError("key must be a 32-byte SecretBox key")
    if not 2 <= threshold <= share_count <= 255:
        raise ValueError("require 2 <= threshold <= share_count <= 255")
    coefficients = [
        [key[index], *os.urandom(threshold - 1)]
        for index in range(len(key))
    ]
    shares = []
    for share_id in range(1, share_count + 1):
        values = bytearray([share_id])
        for polynomial in coefficients:
            value = 0
            for coefficient in reversed(polynomial):
                value = _gf_mul(value, share_id) ^ coefficient
            values.append(value)
        shares.append(bytes(values))
    return shares


def combine_key(shares: list[bytes], threshold: int) -> bytes:
    if len(shares) < threshold or not shares:
        raise ValueError("insufficient key shares")
    selected = shares[:threshold]
    if any(len(share) != len(selected[0]) for share in selected) or len(selected[0]) != 33:
        raise ValueError("invalid key share")
    if len({share[0] for share in selected}) != len(selected):
        raise ValueError("duplicate key share")
    secret = bytearray(32)
    for index in range(32):
        value = 0
        for position, share in enumerate(selected):
            x_position = share[0]
            numerator = 1
            denominator = 1
            for other_position, other in enumerate(selected):
                if position == other_position:
                    continue
                numerator = _gf_mul(numerator, other[0])
                denominator = _gf_mul(denominator, x_position ^ other[0])
            basis = _gf_mul(numerator, _gf_pow(denominator, 254))
            value ^= _gf_mul(share[index + 1], basis)
        secret[index] = value
    return bytes(secret)


def encrypt_fragments(content: bytes, chunk_size: int = 1024 * 1024) -> tuple[bytes, EncryptedManifest, list[EncryptedFragment]]:
    if not content:
        raise ValueError("content must not be empty")
    if chunk_size < 1024 or chunk_size > 16 * 1024 * 1024:
        raise ValueError("chunk_size must be between 1024 and 16777216 bytes")
    key = os.urandom(nacl.secret.SecretBox.KEY_SIZE)
    box = nacl.secret.SecretBox(key)
    fragments: list[EncryptedFragment] = []
    encrypted_parts: list[bytes] = []
    for index, start in enumerate(range(0, len(content), chunk_size)):
        encrypted = box.encrypt(content[start:start + chunk_size])
        nonce = bytes(encrypted.nonce)
        ciphertext = bytes(encrypted.ciphertext)
        fragments.append(EncryptedFragment(
            index=index,
            nonce=nonce,
            ciphertext=ciphertext,
            sha256=hashlib.sha256(ciphertext).hexdigest(),
        ))
        encrypted_parts.append(ciphertext)
    manifest = EncryptedManifest(
        content_sha256=hashlib.sha256(content).hexdigest(),
        encrypted_content_sha256=hashlib.sha256(b"".join(encrypted_parts)).hexdigest(),
        chunk_size=chunk_size,
        fragment_count=len(fragments),
        fragments=tuple({
            "index": fragment.index,
            "sha256": fragment.sha256,
            "size": len(fragment.ciphertext),
        } for fragment in fragments),
    )
    return key, manifest, fragments


def decrypt_fragments(key: bytes, manifest: EncryptedManifest, fragments: list[EncryptedFragment]) -> bytes:
    if len(key) != nacl.secret.SecretBox.KEY_SIZE:
        raise ValueError("key must be a 32-byte SecretBox key")
    expected = {int(item["index"]): str(item["sha256"]) for item in manifest.fragments}
    actual = {fragment.index: fragment for fragment in fragments}
    if set(expected) != set(actual) or len(actual) != manifest.fragment_count:
        raise ValueError("fragment set does not match manifest")
    box = nacl.secret.SecretBox(key)
    content = bytearray()
    encrypted_parts: list[bytes] = []
    for index in sorted(actual):
        fragment = actual[index]
        if hashlib.sha256(fragment.ciphertext).hexdigest() != expected[index]:
            raise ValueError(f"fragment {index} digest mismatch")
        encrypted_parts.append(fragment.ciphertext)
        content.extend(box.decrypt(fragment.nonce + fragment.ciphertext))
    if hashlib.sha256(b"".join(encrypted_parts)).hexdigest() != manifest.encrypted_content_sha256:
        raise ValueError("encrypted content digest mismatch")
    result = bytes(content)
    if hashlib.sha256(result).hexdigest() != manifest.content_sha256:
        raise ValueError("content digest mismatch")
    return result


def encode_key(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).decode().rstrip("=")


def decode_key(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError("invalid encoded document key") from error