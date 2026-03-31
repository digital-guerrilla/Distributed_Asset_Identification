"""
Federation client — push asset records to peer nodes.

Used by authority nodes when they want to proactively propagate a record
to known peers (e.g. distributors, retailers, partner networks).
"""

import httpx

from ..core.models import AssetRecord
from .resolver import fetch_well_known


async def push_to_peer(
    target_authority: str,
    asset: AssetRecord,
    timeout: int = 10,
) -> bool:
    """
    Push a signed asset record to a peer node's federation sync endpoint.

    The peer will independently verify the signature before storing.

    Args:
        target_authority: Domain of the target peer node (e.g. "retail.example.com").
        asset:            The signed AssetRecord to push.
        timeout:          HTTP timeout in seconds.

    Returns:
        True if the peer accepted the record (202), False otherwise.
    """
    try:
        well_known = await fetch_well_known(target_authority, timeout=timeout)
        endpoint = well_known.endpoint.rstrip("/")
        url = f"{endpoint}/v1/federation/sync"

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(url, json=asset.model_dump(mode="json"))
            return resp.status_code == 202
    except Exception:
        return False


async def push_to_peers(
    peer_authorities: list[str],
    asset: AssetRecord,
    timeout: int = 10,
) -> dict[str, bool]:
    """
    Push an asset record to multiple peer nodes in sequence.

    Returns a dict mapping each peer authority to True (accepted) / False (failed).
    """
    results = {}
    for peer in peer_authorities:
        results[peer] = await push_to_peer(peer, asset, timeout=timeout)
    return results
