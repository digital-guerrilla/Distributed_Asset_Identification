"""
Ed25519 cryptographic operations for DAID nodes.

Each node holds a single Ed25519 keypair:
  - Private key: used to sign every record issued by this node
  - Public key:  published via /.well-known/daid/server; used by anyone to verify

Signing input is canonical JSON — dict serialized with sorted keys, no
whitespace, and with the "signature" field excluded.
"""

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import nacl.encoding
import nacl.exceptions
import nacl.signing


class NodeKeyManager:
    """
    Manages an Ed25519 signing keypair for a DAID node.

    Usage:
        km = NodeKeyManager.load_or_create("./node_key.bin")
        sig = km.sign_record(record_dict)
        ok  = NodeKeyManager.verify(record_dict, sig, other_node_pubkey_b64)
    """

    def __init__(self, private_key_bytes: bytes | None = None):
        if private_key_bytes is not None:
            self._signing_key = nacl.signing.SigningKey(private_key_bytes)
        else:
            self._signing_key = nacl.signing.SigningKey.generate()
        self._verify_key = self._signing_key.verify_key

    # ------------------------------------------------------------------
    # Key Properties
    # ------------------------------------------------------------------

    @property
    def public_key_b64(self) -> str:
        """Base64-encoded (standard) 32-byte Ed25519 public key."""
        return base64.b64encode(bytes(self._verify_key)).decode()

    @property
    def private_key_bytes(self) -> bytes:
        """Raw 32-byte private key (seed). Keep this secret."""
        return bytes(self._signing_key)

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def sign_record(self, record: dict[str, Any]) -> str:
        """
        Sign a record dict and return a base64-encoded Ed25519 signature.

        The "signature" key is excluded from the signing payload so that
        the signature can be stored alongside the signed data.
        """
        payload = _canonical_json(record)
        signed = self._signing_key.sign(payload.encode())
        return base64.b64encode(signed.signature).decode()

    # ------------------------------------------------------------------
    # Verification (static — doesn't need the private key)
    # ------------------------------------------------------------------

    @staticmethod
    def verify(record: dict[str, Any], signature_b64: str, public_key_b64: str) -> bool:
        """
        Verify an Ed25519 signature over a record dict.

        Args:
            record:         The asset record dict (may include "signature" key).
            signature_b64:  Base64-encoded 64-byte signature.
            public_key_b64: Base64-encoded 32-byte Ed25519 public key.

        Returns:
            True if the signature is valid, False otherwise.
        """
        try:
            pub_key_bytes = base64.b64decode(public_key_b64)
            verify_key = nacl.signing.VerifyKey(pub_key_bytes)
            payload = _canonical_json(record)
            sig_bytes = base64.b64decode(signature_b64)
            verify_key.verify(payload.encode(), sig_bytes)
            return True
        except (nacl.exceptions.BadSignatureError, Exception):
            return False

    # ------------------------------------------------------------------
    # Key Persistence
    # ------------------------------------------------------------------

    @classmethod
    def load_or_create(cls, key_file: str) -> "NodeKeyManager":
        """
        Load a node keypair from a file, or generate a new one if the
        file does not exist. The generated key is saved to the file.
        """
        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                return cls(f.read())

        km = cls()
        os.makedirs(os.path.dirname(os.path.abspath(key_file)), exist_ok=True)
        with open(key_file, "wb") as f:
            f.write(km.private_key_bytes)
        print(f"[daid] Generated new Ed25519 keypair → {key_file}")
        print(f"[daid] Public key: {km.public_key_b64}")
        return km


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _canonical_json(record: dict[str, Any]) -> str:
    """
    Produce the deterministic, canonical JSON payload for signing.

    Rules:
      - Exclude the top-level "signature" key
      - Sort all dict keys recursively
      - No extra whitespace
      - datetime objects serialized as UTC ISO 8601
    """
    record_copy = {k: v for k, v in record.items() if k != "signature"}
    return json.dumps(record_copy, sort_keys=True, separators=(",", ":"), default=_json_default)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.astimezone(timezone.utc).isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def sha256_hex(data: str) -> str:
    """SHA-256 hash of a UTF-8 string, returned as hex string."""
    return hashlib.sha256(data.encode()).hexdigest()
