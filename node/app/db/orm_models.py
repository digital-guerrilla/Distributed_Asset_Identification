"""SQLAlchemy persistence for DAID v3 records and peer state."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Asset(Base):
    __tablename__ = "records"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    routing_host: Mapped[str] = mapped_column(String, nullable=False, index=True)
    authority: Mapped[str] = mapped_column(String, nullable=False, index=True)
    controller: Mapped[str] = mapped_column(String, nullable=False)
    record_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    record_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_authoritative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssetHistory(Base):
    __tablename__ = "record_history"

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    record_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GossipPeer(Base):
    __tablename__ = "gossip_peers"

    node_id: Mapped[str] = mapped_column(String, primary_key=True)
    endpoint: Mapped[str] = mapped_column(String, nullable=False)
    public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="alive")
    generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)