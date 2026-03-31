"""
DAID Python Client SDK

Simple async client for interacting with any DAID node.

Usage:
    import asyncio
    from client.daid_client import DAIDClient

    async def main():
        async with DAIDClient("http://localhost:8000", api_key="my-key") as client:
            asset = await client.create_asset({"name": "Widget"})
            print(asset.id)
            result = await client.resolve(asset.id)
            print(result.verified)

    asyncio.run(main())
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Data classes returned by the SDK
# ---------------------------------------------------------------------------

@dataclass
class AssetResult:
    id: str
    authority: str
    authority_data: dict          # core identity: name, manufacturer, model_number, ...
    metadata: dict                # extended optional fields
    version: int
    created_at: str
    updated_at: str
    signature: str | None

    @property
    def name(self) -> str:
        return self.authority_data.get("name", "")

    @property
    def manufacturer(self) -> str:
        return self.authority_data.get("manufacturer", "")

    @property
    def model_number(self) -> str:
        return self.authority_data.get("model_number", "")

    @property
    def authority_from_id(self) -> str:
        """Extract authority from the DAID URI."""
        parts = self.id.split(":")
        return parts[1] if len(parts) >= 3 else ""

    @property
    def uuid(self) -> str:
        """Extract UUID from the DAID URI."""
        parts = self.id.split(":")
        return parts[2] if len(parts) >= 3 else ""


@dataclass
class ResolveResult:
    asset: AssetResult
    verified: bool
    source: str
    authority_endpoint: Optional[str] = None


@dataclass
class NodeInfo:
    node_id: str
    public_key: str
    api_version: str
    supported_features: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class DAIDClient:
    """
    Async HTTP client for a DAID node.

    Can be used as an async context manager or with explicit open/close.

    Args:
        node_url:  Base URL of the DAID node, e.g. "http://localhost:8000"
        api_key:   API key for write operations (POST /v1/assets, PUT /v1/assets/...)
        timeout:   Default request timeout in seconds
    """

    def __init__(
        self,
        node_url: str,
        api_key: Optional[str] = None,
        timeout: int = 15,
    ):
        self._base = node_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "DAIDClient":
        self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # Allow one-shot use without context manager
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self._client

    def _headers(self, write: bool = False) -> dict:
        h: dict = {"Content-Type": "application/json"}
        if write:
            if not self._api_key:
                raise ValueError("api_key is required for write operations")
            h["x-api-key"] = self._api_key
        return h

    # ------------------------------------------------------------------
    # Node info
    # ------------------------------------------------------------------

    async def get_node_info(self) -> NodeInfo:
        """Fetch node identity and capabilities."""
        resp = await self._get_client().get(
            f"{self._base}/v1/node/info", headers=self._headers()
        )
        resp.raise_for_status()
        d = resp.json()
        return NodeInfo(
            node_id=d["node_id"],
            public_key=d["public_key"],
            api_version=d["api_version"],
            supported_features=d.get("supported_features", []),
        )

    async def get_well_known(self) -> dict:
        """Fetch the /.well-known/daid/server discovery document."""
        resp = await self._get_client().get(f"{self._base}/.well-known/daid/server")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Asset reads
    # ------------------------------------------------------------------

    async def get_asset(self, daid: str) -> AssetResult:
        """
        Fetch an asset directly from this node's local store.
        Returns 404 if not held by this node.
        """
        authority, uuid = _split_daid(daid)
        resp = await self._get_client().get(
            f"{self._base}/v1/assets/{authority}/{uuid}", headers=self._headers()
        )
        resp.raise_for_status()
        return _parse_asset(resp.json())

    async def list_assets(self, limit: int = 50, offset: int = 0) -> list[AssetResult]:
        """List assets held by this node."""
        resp = await self._get_client().get(
            f"{self._base}/v1/assets",
            params={"limit": limit, "offset": offset},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return [_parse_asset(a) for a in resp.json()["items"]]

    async def get_history(self, daid: str) -> list[dict]:
        """Fetch version history for an asset."""
        authority, uuid = _split_daid(daid)
        resp = await self._get_client().get(
            f"{self._base}/v1/assets/{authority}/{uuid}/history",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Resolve (network-aware)
    # ------------------------------------------------------------------

    async def resolve(self, daid: str) -> ResolveResult:
        """
        Resolve any DAID from the network.

        This node will route to the authoritative node automatically,
        verify the signature, and return the result.
        """
        authority, uuid = _split_daid(daid)
        resp = await self._get_client().get(
            f"{self._base}/v1/resolve/{authority}/{uuid}", headers=self._headers()
        )
        resp.raise_for_status()
        d = resp.json()
        return ResolveResult(
            asset=_parse_asset(d["asset"]),
            verified=d["verified"],
            source=d["source"],
            authority_endpoint=d.get("authority_endpoint"),
        )

    async def get_jsonld(self, daid: str) -> dict:
        """Fetch the asset as a schema.org JSON-LD document."""
        authority, uuid = _split_daid(daid)
        resp = await self._get_client().get(
            f"{self._base}/v1/assets/{authority}/{uuid}/jsonld",
            headers={"Accept": "application/ld+json"},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_gossip_peers(self) -> list[dict]:
        """Return this node's current gossip membership view."""
        resp = await self._get_client().get(f"{self._base}/v1/gossip/peers")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Asset writes (require api_key)
    # ------------------------------------------------------------------

    async def create_asset(
        self,
        authority_data: dict,
        metadata: dict | None = None,
    ) -> AssetResult:
        """
        Register a new asset on this node.
        authority_data must include: name, manufacturer, model_number
        metadata is optional extended fields.
        """
        resp = await self._get_client().post(
            f"{self._base}/v1/assets",
            json={"authority_data": authority_data, "metadata": metadata or {}},
            headers=self._headers(write=True),
        )
        resp.raise_for_status()
        return _parse_asset(resp.json())

    async def update_asset(
        self,
        daid: str,
        authority_data: dict,
        metadata: dict | None = None,
    ) -> AssetResult:
        """
        Update an asset's authority data and/or metadata.
        Requires api_key. This node must be authoritative for the asset.
        """
        authority, uuid = _split_daid(daid)
        resp = await self._get_client().put(
            f"{self._base}/v1/assets/{authority}/{uuid}",
            json={"authority_data": authority_data, "metadata": metadata or {}},
            headers=self._headers(write=True),
        )
        resp.raise_for_status()
        return _parse_asset(resp.json())

    # ------------------------------------------------------------------
    # Federation helpers
    # ------------------------------------------------------------------

    async def push_to_peer(self, peer_url: str, daid: str) -> bool:
        """
        Read a local asset and push it to a peer node's federation endpoint.
        The peer will verify the signature independently.
        """
        asset_resp = await self.get_asset(daid)
        peer_base = peer_url.rstrip("/")
        resp = await self._get_client().post(
            f"{peer_base}/v1/federation/sync",
            json={
                "id": asset_resp.id,
                "authority": asset_resp.authority,
                "authority_data": asset_resp.authority_data,
                "metadata": asset_resp.metadata,
                "version": asset_resp.version,
                "created_at": asset_resp.created_at,
                "updated_at": asset_resp.updated_at,
                "signature": asset_resp.signature,
            },
        )
        return resp.status_code == 202


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DAID_RE = re.compile(
    r'^daid:([a-zA-Z0-9._:-]+):([0-9a-f-]{36})$', re.IGNORECASE
)


def _split_daid(daid: str) -> tuple[str, str]:
    m = _DAID_RE.match(daid.strip())
    if not m:
        raise ValueError(f"Invalid DAID URI: {daid!r}")
    return m.group(1), m.group(2)


def _parse_asset(d: dict) -> AssetResult:
    return AssetResult(
        id=d["id"],
        authority=d["authority"],
        authority_data=d["authority_data"],
        metadata=d.get("metadata") or {},
        version=d["version"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        signature=d.get("signature"),
    )
