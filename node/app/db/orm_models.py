"""
SQLAlchemy ORM models for DAID node storage.

Two tables:
  assets         — Current state of each asset record (authoritative + cached)
  asset_history  — Previous versions, written on every update
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Asset(Base):
    """
    Stores one asset record per DAID URI.

    `is_authoritative` distinguishes records this node owns (and can update)
    from records cached from remote authority nodes.
    """

    __tablename__ = "assets"

    # Primary key is the full DAID URI, e.g. "daid:acme.com:uuid4"
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # Authority domain extracted from the DAID (indexed for fast listing)
    authority: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Core product identity — issued by the authority node, cached by peers
    authority_data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Extended optional metadata
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Base64-encoded Ed25519 signature from the authority node
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    # True  → this node issued this record (has the signing key)
    # False → obtained from a remote node; signature must be verified to trust
    is_authoritative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # When the record was last fetched/synced from the remote authority (cached records only)
    cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetHistory(Base):
    """
    Immutable snapshots of previous asset versions.
    Written automatically whenever an authoritative record is updated.
    """

    __tablename__ = "asset_history"

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    authority_data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)


class GossipPeer(Base):
    """
    Persisted gossip membership table.

    Each row represents what this node currently believes about one peer:
    its endpoint, Ed25519 public key, health status, and heartbeat generation.
    Rows are upserted on every gossip exchange and on .well-known discovery.
    """

    __tablename__ = "gossip_peers"

    # Authority domain is the stable identifier (e.g. "127.0.0.1:8092")
    node_id: Mapped[str] = mapped_column(String, primary_key=True)

    # Base URL of the peer's API — may change if the node migrates
    endpoint: Mapped[str] = mapped_column(String, nullable=False)

    # Ed25519 public key (base64) — used to verify records from this peer
    public_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SWIM-style status: alive | suspect | dead
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="alive")

    # Monotonically increasing counter the peer increments on each heartbeat
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Wall-clock time this node last received a heartbeat from the peer
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
