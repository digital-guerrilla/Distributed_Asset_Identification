"""
DAID URI parsing and generation.

Format: daid:{authority}:{uuid4}
  authority = hostname or hostname:port
  uuid4     = standard UUID v4 string

Examples:
  daid:products.acme.com:550e8400-e29b-41d4-a716-446655440000
  daid:localhost:8001:a8098c1a-f86e-11da-bd1a-00112444be1e
"""

import re
import uuid
from dataclasses import dataclass

DAID_SCHEME = "daid"

# Matches: daid:{authority}:{uuid4}
# authority = hostname optionally with :port
# uuid4     = 8-4-4-4-12 hex groups where third group starts with '4'
#             and fourth group starts with 8/9/a/b
_DAID_RE = re.compile(
    r'^daid:'
    r'([a-zA-Z0-9._-]+(?::\d+)?)'   # authority (group 1)
    r':'
    r'([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})'  # uuid4 (group 2)
    r'$',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedDAID:
    authority: str
    asset_uuid: str

    @property
    def full_id(self) -> str:
        return f"daid:{self.authority}:{self.asset_uuid}"

    def __str__(self) -> str:
        return self.full_id


def generate_daid(authority: str) -> str:
    """
    Generate a new DAID URI for the given authority.

    Args:
        authority: The authority domain (e.g. "products.acme.com" or "localhost:8000")

    Returns:
        A new DAID URI string, e.g. "daid:products.acme.com:550e8400-..."
    """
    return f"daid:{authority}:{uuid.uuid4()}"


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
            f"Expected format: daid:{{authority}}:{{uuid4}}"
        )
    return ParsedDAID(authority=match.group(1).lower(), asset_uuid=match.group(2).lower())


def is_valid_daid(daid: str) -> bool:
    """Return True if the string is a syntactically valid DAID URI."""
    return bool(_DAID_RE.match(daid.strip()))
