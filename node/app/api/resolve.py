"""
Network-aware resolve endpoint.

GET /v1/resolve/{authority}/{uuid}

Resolves any DAID from the entire DAID network, not just records held locally:

  1. If this node is the authority → serve directly (fast path)
  2. Else, check local cache.  If found and not stale → return cached record.
  3. Else, resolve from the authoritative node via federation, verify sig,
     cache the result, and return it.

Response:
  {
    "asset":               {AssetRecord},
    "verified":            true | false,
    "source":              "local_authoritative" | "local_cache" | "remote_authoritative",
    "authority_endpoint":  "https://..."
  }
"""

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.crypto import NodeKeyManager
from ..core.models import AssetMetadata, AssetRecord, AuthorityData, ResolveResponse
from ..db.database import get_db
from ..db.orm_models import Asset
from ..dependencies import get_key_manager
from ..federation.resolver import resolve_daid

router = APIRouter(prefix="/v1/resolve", tags=["resolve"])


# ---------------------------------------------------------------------------
# Browse — proxy a remote node's asset list (avoids browser CORS)
# MUST be defined before /{authority}/{uuid} to avoid route shadowing.
# ---------------------------------------------------------------------------

@router.get("/browse/{authority:path}")
async def browse_authority(
    authority: str,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    Fetch the asset list from any authority node and return it,
    so the client UI can browse remote nodes without CORS issues.
    Falls back to the local /v1/assets when authority == this node.
    """
    if authority.lower() == settings.NODE_DOMAIN.lower():
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{settings.NODE_API_BASE}/v1/assets",
                params={"limit": limit, "offset": offset},
            )
    else:
        base = f"http://{authority}"
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                r = await client.get(
                    f"{base}/v1/assets",
                    params={"limit": limit, "offset": offset},
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not reach {authority}: {exc}",
                )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=f"Remote node returned {r.status_code}")
    return r.json()


@router.get("/{authority}/{uuid}", response_model=ResolveResponse)
async def resolve(
    authority: str,
    uuid: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    key_manager: NodeKeyManager = Depends(get_key_manager),
) -> ResolveResponse:
    daid = f"daid:{authority}:{uuid}"

    # ------------------------------------------------------------------
    # Fast path: this node is the authority
    # ------------------------------------------------------------------
    if authority.lower() == settings.NODE_DOMAIN.lower():
        result = await db.execute(select(Asset).where(Asset.id == daid))
        asset = result.scalar_one_or_none()
        if asset is None:
            raise HTTPException(status_code=404, detail=f"Asset not found: {daid}")
        return ResolveResponse(
            asset=_orm_to_record(asset),
            verified=True,
            source="local_authoritative",
            authority_endpoint=settings.NODE_API_BASE,
        )

    # ------------------------------------------------------------------
    # Check local cache (respect CACHE_TTL)
    # ------------------------------------------------------------------
    result = await db.execute(select(Asset).where(Asset.id == daid))
    cached = result.scalar_one_or_none()

    if not refresh and cached and cached.cached_at and settings.CACHE_TTL > 0:
        age = datetime.now(timezone.utc) - _utc(cached.cached_at)
        if age < timedelta(seconds=settings.CACHE_TTL):
            return ResolveResponse(
                asset=_orm_to_record(cached),
                verified=False,  # Not re-verified this request; trust the stored sig
                source="local_cache",
            )

    # ------------------------------------------------------------------
    # Resolve from the authoritative node
    # ------------------------------------------------------------------
    try:
        asset_record, verified, endpoint = await resolve_daid(daid, key_manager)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to resolve {daid} from authority node: {exc}",
        )

    # Cache the verified result locally
    now = datetime.now(timezone.utc)
    if cached:
        if asset_record.version >= cached.version:
            cached.authority_data_json = asset_record.authority_data.model_dump()
            cached.metadata_json = asset_record.metadata.model_dump()
            cached.updated_at = _utc(asset_record.updated_at)
            cached.version = asset_record.version
            cached.signature = asset_record.signature
            cached.cached_at = now
    else:
        db.add(Asset(
            id=asset_record.id,
            authority=asset_record.authority,
            authority_data_json=asset_record.authority_data.model_dump(),
            metadata_json=asset_record.metadata.model_dump(),
            created_at=_utc(asset_record.created_at),
            updated_at=_utc(asset_record.updated_at),
            version=asset_record.version,
            signature=asset_record.signature,
            is_authoritative=False,
            cached_at=now,
        ))
    await db.commit()

    return ResolveResponse(
        asset=asset_record,
        verified=verified,
        source="remote_authoritative",
        authority_endpoint=endpoint,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _orm_to_record(asset: Asset) -> AssetRecord:
    return AssetRecord(
        id=asset.id,
        authority=asset.authority,
        authority_data=AuthorityData(**(asset.authority_data_json or {})),
        metadata=AssetMetadata(**(asset.metadata_json or {})),
        created_at=_utc(asset.created_at),
        updated_at=_utc(asset.updated_at),
        version=asset.version,
        signature=asset.signature,
    )


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
