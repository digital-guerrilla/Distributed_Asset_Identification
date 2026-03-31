"""
Federation sync endpoint.

POST /v1/federation/sync

Used by authority nodes (or other peer nodes) to push signed asset records
to this node for caching/mirroring.

Security model:
  - The receiving node ALWAYS verifies the Ed25519 signature by fetching
    the authority's public key fresh from their .well-known endpoint.
  - Records with invalid signatures are rejected with 400.
  - Records with a lower or equal version than what we already hold are
    silently ignored (idempotent).
"""

from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.crypto import NodeKeyManager
from ..core.models import AssetRecord
from ..db.database import get_db
from ..db.orm_models import Asset
from ..dependencies import get_key_manager
from ..federation.resolver import fetch_well_known

router = APIRouter(prefix="/v1/federation", tags=["federation"])


@router.post("/sync", status_code=202)
async def receive_sync(
    asset: AssetRecord,
    db: AsyncSession = Depends(get_db),
    key_manager: NodeKeyManager = Depends(get_key_manager),
) -> dict:
    """
    Accept a pushed asset record from a peer node.

    Verification steps:
      1. Fetch the authority node's public key via .well-known
      2. Verify the Ed25519 signature
      3. Store (or update if newer version) as a cached record
    """
    # --- Verify we are not writing an authoritative record under our own domain
    #     (that would bypass the write-auth check on the assets endpoint)
    if asset.authority == settings.NODE_DOMAIN:
        raise HTTPException(
            status_code=400,
            detail="Cannot sync a record whose authority matches this node's domain. "
                   "Use the assets endpoint to create local records.",
        )

    # --- Step 1: Fetch authority's public key
    try:
        well_known = await fetch_well_known(asset.authority, timeout=settings.FEDERATION_TIMEOUT)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not fetch discovery document for authority '{asset.authority}': {exc}",
        )

    # --- Step 2: Verify signature
    signing_dict = {
        "id": asset.id,
        "authority": asset.authority,
        "authority_data": asset.authority_data.model_dump(),
        "metadata": asset.metadata.model_dump(),
        "created_at": _utc(asset.created_at).isoformat(),
        "updated_at": _utc(asset.updated_at).isoformat(),
        "version": asset.version,
    }
    if not asset.signature or not NodeKeyManager.verify(
        signing_dict, asset.signature, well_known.public_key
    ):
        raise HTTPException(status_code=400, detail="Signature verification failed")

    # --- Step 3: Store or update
    now = datetime.now(timezone.utc)
    result = await db.execute(select(Asset).where(Asset.id == asset.id))
    existing = result.scalar_one_or_none()

    if existing:
        if asset.version <= existing.version:
            return {"status": "ignored", "reason": "version not newer"}
        existing.authority_data_json = asset.authority_data.model_dump()
        existing.metadata_json = asset.metadata.model_dump()
        existing.updated_at = _utc(asset.updated_at)
        existing.version = asset.version
        existing.signature = asset.signature
        existing.cached_at = now
    else:
        db.add(Asset(
            id=asset.id,
            authority=asset.authority,
            authority_data_json=asset.authority_data.model_dump(),
            metadata_json=asset.metadata.model_dump(),
            created_at=_utc(asset.created_at),
            updated_at=_utc(asset.updated_at),
            version=asset.version,
            signature=asset.signature,
            is_authoritative=False,
            cached_at=now,
        ))

    await db.commit()
    return {"status": "accepted"}


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
