"""
Pydantic data models for the DAID protocol.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .guid import is_valid_daid


# ---------------------------------------------------------------------------
# Document Reference  (content-addressed pointer to an external document)
# ---------------------------------------------------------------------------

class DocumentRef(BaseModel):
    """
    A pointer to an external document associated with this asset.

    The sha256 hash allows any node or client to verify document integrity
    independently of where the URL points. The authority can change CDN
    providers without the hash changing.
    """

    type: str = Field(
        ...,
        description=(
            "Document type — e.g. 'installation_manual', 'datasheet', "
            "'ce_declaration', 'safety_data_sheet', 'drawing', 'firmware_image'"
        ),
    )
    url: str = Field(..., description="Public URL to fetch the document from")
    sha256: Optional[str] = Field(
        None,
        description="Hex-encoded SHA-256 of the document bytes for integrity verification",
    )
    mime_type: Optional[str] = Field(None, description="MIME type, e.g. 'application/pdf'")
    language: Optional[str] = Field(None, description="BCP-47 language tag, e.g. 'en'")
    version: Optional[str] = Field(None, description="Document revision, e.g. '3.0'")


# ---------------------------------------------------------------------------
# IFC Property Sets  (ISO 16739 / buildingSMART)
# ---------------------------------------------------------------------------

class IFCPsets(BaseModel):
    """
    IFC 4.x property sets for BIM and facility management interoperability.

    Keys are standard Pset names (e.g. 'Pset_ManufacturerTypeInformation').
    Values are dicts of property name → value, matching IFC schema naming.

    Common Psets:
      Pset_ManufacturerTypeInformation — Manufacturer, ModelLabel, ProductionYear, GTIN
      Pset_ServiceLife                 — ServiceLifeType, ServiceLifeDuration (ISO 8601 duration)
      Pset_Warranty                    — WarrantyPeriod, WarrantyContent
      Pset_MaintenanceStrategy         — MaintenanceStrategy
    """

    Pset_ManufacturerTypeInformation: Optional[dict[str, Any]] = None
    Pset_ServiceLife: Optional[dict[str, Any]] = None
    Pset_Warranty: Optional[dict[str, Any]] = None
    Pset_MaintenanceStrategy: Optional[dict[str, Any]] = None
    custom: Optional[dict[str, dict[str, Any]]] = Field(
        None,
        description="Custom Psets — key is the Pset name, value is a dict of properties",
    )


# ---------------------------------------------------------------------------
# Authority Data  (core product identity — issued and owned by authority node)
# ---------------------------------------------------------------------------

class AuthorityData(BaseModel):
    """
    The canonical product identity issued exclusively by the authority node.

    This is the trust root of an asset record — only the authority node that
    holds the signing key can create or modify these fields. Any peer node
    may cache and serve this data, but the Ed25519 signature must always
    verify against the authority's public key before the data is trusted.

    Three optional extension layers:
      ifc_psets  — ISO 16739 IFC property sets (BIM / facility management)
      documents  — Content-addressed document pointers (manuals, certs, drawings)
      schema_org — Supplemental schema.org fields not already mapped automatically
    """

    name: str = Field(..., description="Product or asset name")
    manufacturer: str = Field(..., description="Manufacturer or brand name")
    model_number: str = Field(..., description="Manufacturer's model or part number")
    serial_number: Optional[str] = Field(
        None, description="Individual unit serial number (leave null for product-level records)"
    )
    hardware_revision: Optional[str] = Field(
        None, description="Hardware revision, e.g. 'Rev B'"
    )
    firmware_version: Optional[str] = Field(
        None, description="Firmware or software version if applicable"
    )

    # IFC / BIM layer
    ifc_psets: Optional[IFCPsets] = Field(
        None, description="IFC 4.x property sets for BIM/CAFM interoperability"
    )

    # Document map
    documents: list[DocumentRef] = Field(
        default_factory=list,
        description="Content-addressed pointers to manuals, certs, drawings, etc.",
    )

    # schema.org supplemental fields (auto-mapped fields like name/manufacturer
    # are handled by the JSON-LD serialiser; add extras here)
    schema_org: Optional[dict[str, Any]] = Field(
        None,
        description="Additional schema.org properties not automatically mapped",
    )


# ---------------------------------------------------------------------------
# Asset Metadata  (extended optional fields — hosted on authority, cached by peers)
# ---------------------------------------------------------------------------

class AssetMetadata(BaseModel):
    """
    Extended, optional metadata for an asset.

    These fields supplement the core AuthorityData and are also part of the
    signed record, meaning they can only be modified by the authority node.
    Peer nodes cache this alongside the authority_data transparently.
    """

    description: Optional[str] = None
    category: Optional[str] = None
    sku: Optional[str] = Field(None, description="Stock Keeping Unit")
    gtin: Optional[str] = Field(
        None,
        description="Global Trade Item Number (EAN-13, UPC-A, GTIN-14)",
    )
    origin_country: Optional[str] = Field(
        None, description="ISO 3166-1 alpha-2 country code"
    )
    tags: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Open-ended key-value extensions. Prefix keys with a namespace, "
                    "e.g. 'pharma:lot_number'.",
    )


# ---------------------------------------------------------------------------
# Asset Record (the canonical signed document)
# ---------------------------------------------------------------------------

class AssetRecord(BaseModel):
    """
    A complete, signed asset record as stored and exchanged between nodes.

    `authority_data` holds the core product identity and is the primary field
    peers cache when a record is resolved across the network.
    `metadata` holds extended optional fields.
    Both sections are covered by the Ed25519 `signature`.
    """

    id: str = Field(..., description="Full DAID URI, e.g. daid:acme.com:uuid4")
    authority: str = Field(..., description="Authority domain of the issuing node")
    authority_data: AuthorityData
    metadata: AssetMetadata = Field(default_factory=AssetMetadata)
    created_at: datetime
    updated_at: datetime
    version: int = Field(1, ge=1)
    signature: Optional[str] = Field(
        None, description="Base64-encoded Ed25519 signature by the authority node"
    )

    @field_validator("id")
    @classmethod
    def validate_daid(cls, v: str) -> str:
        if not is_valid_daid(v):
            raise ValueError(f"Invalid DAID URI: {v!r}")
        return v


# ---------------------------------------------------------------------------
# Asset History Entry (previous version snapshot)
# ---------------------------------------------------------------------------

class AssetHistoryEntry(BaseModel):
    asset_id: str
    version: int
    authority_data: AuthorityData
    metadata: AssetMetadata = Field(default_factory=AssetMetadata)
    updated_at: datetime
    signature: Optional[str] = None


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class AssetCreateRequest(BaseModel):
    authority_data: AuthorityData
    metadata: AssetMetadata = Field(default_factory=AssetMetadata)


class AssetUpdateRequest(BaseModel):
    authority_data: AuthorityData
    metadata: AssetMetadata = Field(default_factory=AssetMetadata)


# ---------------------------------------------------------------------------
# Node Discovery / Info
# ---------------------------------------------------------------------------

class WellKnownResponse(BaseModel):
    endpoint: str = Field(..., description="Base URL of this node's API")
    node_id: str = Field(..., description="Authority domain of this node")
    public_key: str = Field(..., description="Base64-encoded Ed25519 public key")
    api_version: str = "1.0"


class NodeInfo(BaseModel):
    node_id: str
    public_key: str
    api_version: str = "1.0"
    supported_features: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Resolution response
# ---------------------------------------------------------------------------

class ResolveResponse(BaseModel):
    asset: AssetRecord
    verified: bool
    source: str = Field(
        ...,
        description="One of: local_authoritative, local_cache, remote_authoritative",
    )
    authority_endpoint: Optional[str] = None


# ---------------------------------------------------------------------------
# Paginated list response
# ---------------------------------------------------------------------------

class AssetListResponse(BaseModel):
    items: list[AssetRecord]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Gossip protocol models
# ---------------------------------------------------------------------------

class GossipPeerState(BaseModel):
    """The view one node has of a peer's health and identity."""

    node_id: str = Field(..., description="Authority domain of the peer node")
    endpoint: str = Field(..., description="Base HTTP URL of the peer node")
    public_key: Optional[str] = Field(None, description="Base64 Ed25519 public key")
    status: Literal["alive", "suspect", "dead"] = "alive"
    last_seen: Optional[datetime] = None
    generation: int = Field(0, description="Monotonically increasing heartbeat counter")


class GossipDigest(BaseModel):
    """
    A compact summary of what one node knows about the network.
    Sent during gossip exchange so peers can identify stale/missing entries.
    """

    from_node: str
    peers: list[GossipPeerState] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=__import__('datetime').timezone.utc))


class GossipSyncRequest(BaseModel):
    """Payload for POST /v1/gossip/sync"""

    digest: GossipDigest


class GossipSyncResponse(BaseModel):
    """Response — the receiver's own digest so the caller can update their state."""

    digest: GossipDigest
