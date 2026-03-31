"""
DAID resolution — converts a DAID URI into a verified AssetRecord by
contacting the authoritative node.

Flow:
  1. Parse authority from DAID URI
  2. Fetch /.well-known/daid/server from that authority to get endpoint + public key
  3. Call GET {endpoint}/v1/assets/{authority}/{uuid}
  4. Verify Ed25519 signature
  5. Return (AssetRecord, verified: bool, authority_endpoint: str)
"""

from datetime import datetime, timezone

import httpx

from ..core.crypto import NodeKeyManager
from ..core.guid import parse_daid
from ..core.models import AssetRecord, WellKnownResponse


async def fetch_well_known(authority: str, timeout: int = 10) -> WellKnownResponse:
    """
    Fetch the DAID discovery document from an authority domain.

    For proper domain names: tries HTTPS first, falls back to HTTP.
    For IP addresses and localhost: uses HTTP only (no TLS handshake sent to
    a plain-HTTP server, which would cause uvicorn to log spurious warnings).

    Raises:
        ValueError: If the document cannot be fetched or parsed.
    """
    host = authority.split(":")[0].lower()
    is_ip_or_local = (
        host == "localhost"
        or host.replace(".", "").isdigit()  # IPv4
        or host.startswith("[")              # IPv6 literal
    )
    if is_ip_or_local:
        candidates = [f"http://{authority}/.well-known/daid/server"]
    else:
        candidates = [
            f"https://{authority}/.well-known/daid/server",
            f"http://{authority}/.well-known/daid/server",
        ]

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for url in candidates:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return WellKnownResponse(**resp.json())
            except httpx.RequestError:
                continue

    raise ValueError(f"Could not discover DAID node for authority: {authority!r}")


async def resolve_daid(
    daid: str,
    key_manager: NodeKeyManager,
    timeout: int = 10,
) -> tuple[AssetRecord, bool, str]:
    """
    Resolve a DAID URI to a signed asset record from the authoritative node.

    Returns:
        (asset_record, verified, authority_endpoint)

    Raises:
        ValueError: On invalid DAID, unreachable authority, or HTTP error.
    """
    parsed = parse_daid(daid)

    # Step 1 — discover the authority node
    well_known = await fetch_well_known(parsed.authority, timeout=timeout)
    endpoint = well_known.endpoint.rstrip("/")

    # Step 2 — fetch the asset record
    url = f"{endpoint}/v1/assets/{parsed.authority}/{parsed.asset_uuid}"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
        except httpx.RequestError as exc:
            raise ValueError(f"HTTP error fetching {url}: {exc}") from exc

        if resp.status_code == 404:
            raise ValueError(f"Asset not found on authority node: {daid}")
        if resp.status_code != 200:
            raise ValueError(
                f"Authority node returned HTTP {resp.status_code} for {daid}"
            )

        asset_data = resp.json()

    asset = AssetRecord(**asset_data)

    # Step 3 — verify signature
    signing_dict = {
        "id": asset.id,
        "authority": asset.authority,
        "authority_data": asset.authority_data.model_dump(),
        "metadata": asset.metadata.model_dump(),
        "created_at": _utc(asset.created_at).isoformat(),
        "updated_at": _utc(asset.updated_at).isoformat(),
        "version": asset.version,
    }
    verified = bool(asset.signature) and NodeKeyManager.verify(
        signing_dict, asset.signature, well_known.public_key
    )

    return asset, verified, endpoint


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
