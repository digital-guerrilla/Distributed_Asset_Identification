"""DAID v3 URI parsing and generation."""

import re
import uuid
from dataclasses import dataclass

DAID_SCHEME = "daid"

_DAID_RE = re.compile(
    r"^daid://"
    r"([a-zA-Z0-9.-]+(?::\d+)?)"
    r"/(z[1-9A-HJ-NP-Za-km-z]+)"
    r"/([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedDAID:
    routing_host: str
    authority_key_fingerprint: str
    record_uuid: str

    @property
    def full_id(self) -> str:
        return (
            f"daid://{self.routing_host}/{self.authority_key_fingerprint}/"
            f"{self.record_uuid}"
        )

    def __str__(self) -> str:
        return self.full_id


def generate_daid(routing_host: str, authority_key_fingerprint: str) -> str:
    """Generate a self-certifying DAID v3 URI."""
    candidate = f"daid://{routing_host}/{authority_key_fingerprint}/{uuid.uuid4()}"
    return parse_daid(candidate).full_id


def parse_daid(daid: str) -> ParsedDAID:
    """
    Parse a DAID URI string into its components.

    Raises:
        ValueError: If the string is not a valid DAID URI.
    """
    match = _DAID_RE.match(daid.strip())
    if not match:
        raise ValueError(
            f"Invalid DAID URI: {daid!r}. "
            "Expected format: daid://{routing-host}/{authority-key-fingerprint}/{uuid4}"
        )
    return ParsedDAID(
        routing_host=match.group(1).lower(),
        authority_key_fingerprint=match.group(2),
        record_uuid=match.group(3).lower(),
    )


def is_valid_daid(daid: str) -> bool:
    """Return True if the string is a syntactically valid DAID URI."""
    return bool(_DAID_RE.match(daid.strip()))
