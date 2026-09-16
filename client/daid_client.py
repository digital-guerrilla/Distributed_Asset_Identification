"""Async client for DAID v3 nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx


@dataclass
class RecordResult:
    id: str
    authority: str
    controller: str
    record_kind: str
    subject: dict[str, Any]
    relationships: list[dict[str, Any]]
    availability: dict[str, Any]
    version: int
    created_at: str
    updated_at: str
    proof: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.subject.get("name", ""))


@dataclass
class NodeInfo:
    routing_host: str
    authority: str
    protocol_version: str
    supported_record_kinds: list[str] = field(default_factory=list)
    role: str = "resolver"


class DAIDClient:
    def __init__(self, node_url: str, api_key: str | None = None, timeout: int = 15):
        self._base = node_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "DAIDClient":
        self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self

    async def __aexit__(self, *_) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self._client

    def _headers(self, write: bool = False) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if write:
            if not self._api_key:
                raise ValueError("api_key is required for write operations")
            headers["x-api-key"] = self._api_key
        return headers

    async def get_node_info(self) -> NodeInfo:
        response = await self._http().get(f"{self._base}/v3/node/info")
        response.raise_for_status()
        return NodeInfo(**response.json())

    async def get_well_known(self) -> dict[str, Any]:
        response = await self._http().get(f"{self._base}/.well-known/daid/server")
        response.raise_for_status()
        return response.json()

    async def get_record(self, daid: str) -> RecordResult:
        authority, record_uuid = _split_daid(daid)
        response = await self._http().get(
            f"{self._base}/v3/records/{authority}/{record_uuid}"
        )
        response.raise_for_status()
        return _parse_record(response.json())

    async def list_records(self, limit: int = 50, offset: int = 0) -> list[RecordResult]:
        response = await self._http().get(
            f"{self._base}/v3/records",
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        return [_parse_record(item) for item in response.json()["items"]]

    async def create_record(
        self,
        record_kind: str,
        subject: dict[str, Any],
        *,
        controller: str | None = None,
        availability: dict[str, Any] | None = None,
    ) -> RecordResult:
        payload: dict[str, Any] = {"record_kind": record_kind, "subject": subject}
        if controller:
            payload["controller"] = controller
        if availability:
            payload["availability"] = availability
        response = await self._http().post(
            f"{self._base}/v3/records",
            json=payload,
            headers=self._headers(write=True),
        )
        response.raise_for_status()
        return _parse_record(response.json())

    async def update_record(
        self,
        record: RecordResult,
        subject: dict[str, Any],
    ) -> RecordResult:
        authority, record_uuid = _split_daid(record.id)
        response = await self._http().put(
            f"{self._base}/v3/records/{authority}/{record_uuid}",
            json={
                "subject": subject,
                "controller": record.controller,
                "relationships": record.relationships,
                "availability": record.availability,
            },
            headers=self._headers(write=True),
        )
        response.raise_for_status()
        return _parse_record(response.json())

    async def get_history(self, daid: str) -> list[dict[str, Any]]:
        authority, record_uuid = _split_daid(daid)
        response = await self._http().get(
            f"{self._base}/v3/records/{authority}/{record_uuid}/history"
        )
        response.raise_for_status()
        return response.json()

    async def resolve_graph(
        self,
        root: str,
        *,
        depth: int = 2,
        max_nodes: int = 50,
        view: str = "public",
    ) -> dict[str, Any]:
        response = await self._http().post(
            f"{self._base}/v3/resolve-graph",
            json={"root": root, "depth": depth, "max_nodes": max_nodes, "view": view},
        )
        response.raise_for_status()
        return response.json()

    async def propose_relationship(self, proposal: dict[str, Any]) -> dict[str, Any]:
        response = await self._http().post(
            f"{self._base}/v3/relationships/proposals",
            json=proposal,
            headers=self._headers(write=True),
        )
        response.raise_for_status()
        return response.json()

    async def accept_relationship(self, proposal: dict[str, Any]) -> dict[str, Any]:
        response = await self._http().post(
            f"{self._base}/v3/relationships/accept",
            json=proposal,
            headers=self._headers(write=True),
        )
        response.raise_for_status()
        return response.json()

    async def get_gossip_peers(self) -> list[dict[str, Any]]:
        response = await self._http().get(f"{self._base}/v3/gossip/peers")
        response.raise_for_status()
        return response.json()


def _split_daid(daid: str) -> tuple[str, str]:
    parsed = urlsplit(daid)
    parts = parsed.path.strip("/").split("/")
    if parsed.scheme != "daid" or not parsed.netloc or len(parts) != 2:
        raise ValueError(f"Invalid DAID URI: {daid!r}")
    return parts[0], parts[1]


def _parse_record(document: dict[str, Any]) -> RecordResult:
    return RecordResult(
        id=document["id"],
        authority=document["authority"],
        controller=document["controller"],
        record_kind=document["record_kind"],
        subject=document["subject"],
        relationships=document.get("relationships", []),
        availability=document["availability"],
        version=document["version"],
        created_at=document["created_at"],
        updated_at=document["updated_at"],
        proof=document["proof"],
    )