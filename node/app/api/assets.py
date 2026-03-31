"""
Asset CRUD endpoints — serves records held by this node.

Routes:
  GET  /v1/assets                        - List assets on this node (paginated)
  GET  /v1/assets/{authority}/{uuid}     - Get a specific asset (local store)
  POST /v1/assets                        - Register a new asset (write-protected)
  PUT  /v1/assets/{authority}/{uuid}     - Update asset metadata (write-protected)
  GET  /v1/assets/{authority}/{uuid}/history  - Version history
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.crypto import NodeKeyManager
from ..core.guid import generate_daid
from ..core.models import (
    AssetCreateRequest,
    AssetHistoryEntry,
    AssetListResponse,
    AssetMetadata,
    AssetRecord,
    AssetUpdateRequest,
    AuthorityData,
)
from ..db.database import get_db
from ..db.orm_models import Asset, AssetHistory
from ..dependencies import get_key_manager, require_api_key

router = APIRouter(prefix="/v1/assets", tags=["assets"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _orm_to_record(asset: Asset) -> AssetRecord:
    """Convert an ORM Asset row to a Pydantic AssetRecord."""
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


def _record_signing_dict(asset: Asset, now_iso: str | None = None) -> dict:
    """Build the dict that gets signed (excludes the 'signature' key)."""
    return {
        "id": asset.id,
        "authority": asset.authority,
        "authority_data": asset.authority_data_json or {},
        "metadata": asset.metadata_json or {},
        "created_at": _utc(asset.created_at).isoformat(),
        "updated_at": now_iso or _utc(asset.updated_at).isoformat(),
        "version": asset.version,
    }


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------------------
# GET /v1/assets  — list
# ---------------------------------------------------------------------------

@router.get("", response_model=AssetListResponse)
async def list_assets(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> AssetListResponse:
    count_result = await db.execute(select(func.count(Asset.id)))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Asset).order_by(Asset.created_at.desc()).limit(limit).offset(offset)
    )
    items = [_orm_to_record(a) for a in result.scalars()]
    return AssetListResponse(items=items, total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# GET /v1/assets/{authority}/{uuid}  — single asset
# ---------------------------------------------------------------------------

@router.get("/{authority}/{uuid}", response_model=AssetRecord)
async def get_asset(
    authority: str,
    uuid: str,
    db: AsyncSession = Depends(get_db),
) -> AssetRecord:
    daid = f"daid:{authority}:{uuid}"
    result = await db.execute(select(Asset).where(Asset.id == daid))
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {daid}")
    return _orm_to_record(asset)


# ---------------------------------------------------------------------------
# POST /v1/assets  — create
# ---------------------------------------------------------------------------

@router.post("", response_model=AssetRecord, status_code=201)
async def create_asset(
    body: AssetCreateRequest,
    db: AsyncSession = Depends(get_db),
    key_manager: NodeKeyManager = Depends(get_key_manager),
    _: None = Depends(require_api_key),
) -> AssetRecord:
    daid = generate_daid(settings.NODE_DOMAIN)
    now = datetime.now(timezone.utc)
    authority_data_dict = body.authority_data.model_dump()
    metadata_dict = body.metadata.model_dump()

    signing_dict = {
        "id": daid,
        "authority": settings.NODE_DOMAIN,
        "authority_data": authority_data_dict,
        "metadata": metadata_dict,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "version": 1,
    }
    signature = key_manager.sign_record(signing_dict)

    asset = Asset(
        id=daid,
        authority=settings.NODE_DOMAIN,
        authority_data_json=authority_data_dict,
        metadata_json=metadata_dict,
        created_at=now,
        updated_at=now,
        version=1,
        signature=signature,
        is_authoritative=True,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return _orm_to_record(asset)


# ---------------------------------------------------------------------------
# PUT /v1/assets/{authority}/{uuid}  — update
# ---------------------------------------------------------------------------

@router.put("/{authority}/{uuid}", response_model=AssetRecord)
async def update_asset(
    authority: str,
    uuid: str,
    body: AssetUpdateRequest,
    db: AsyncSession = Depends(get_db),
    key_manager: NodeKeyManager = Depends(get_key_manager),
    _: None = Depends(require_api_key),
) -> AssetRecord:
    daid = f"daid:{authority}:{uuid}"
    result = await db.execute(select(Asset).where(Asset.id == daid))
    asset = result.scalar_one_or_none()

    if asset is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {daid}")
    if not asset.is_authoritative:
        raise HTTPException(
            status_code=403,
            detail="This node is not authoritative for the requested asset",
        )

    # Snapshot the current version to history before mutating
    history = AssetHistory(
        asset_id=asset.id,
        version=asset.version,
        authority_data_json=asset.authority_data_json,
        metadata_json=asset.metadata_json,
        updated_at=_utc(asset.updated_at),
        signature=asset.signature,
    )
    db.add(history)

    # Apply update
    now = datetime.now(timezone.utc)
    new_version = asset.version + 1
    new_authority_data = body.authority_data.model_dump()
    new_metadata = body.metadata.model_dump()

    signing_dict = {
        "id": asset.id,
        "authority": asset.authority,
        "authority_data": new_authority_data,
        "metadata": new_metadata,
        "created_at": _utc(asset.created_at).isoformat(),
        "updated_at": now.isoformat(),
        "version": new_version,
    }
    new_signature = key_manager.sign_record(signing_dict)

    asset.authority_data_json = new_authority_data
    asset.metadata_json = new_metadata
    asset.updated_at = now
    asset.version = new_version
    asset.signature = new_signature

    await db.commit()
    await db.refresh(asset)
    record = _orm_to_record(asset)

    # Fan-out the updated record to all known peers so their caches update immediately
    import asyncio as _asyncio
    _asyncio.create_task(_push_to_peers(record))

    return record


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Peer push helper (fire-and-forget after update)
# ---------------------------------------------------------------------------

async def _push_to_peers(record: AssetRecord) -> None:
    """Push updated record to all alive gossip peers in the background."""
    try:
        import httpx as _httpx
        from ..federation.gossip import get_all_peers
        peers = await get_all_peers()
        alive = [p for p in peers if p.status == "alive"]
        payload = record.model_dump(mode="json")
        async with _httpx.AsyncClient(timeout=5) as client:
            for peer in alive:
                try:
                    await client.post(
                        f"{peer.endpoint.rstrip('/')}/v1/federation/sync",
                        json=payload,
                    )
                except Exception:
                    pass  # best-effort; peer may be temporarily unreachable
    except Exception:
        pass


# GET /v1/assets/{authority}/{uuid}/history  — version history
# ---------------------------------------------------------------------------

@router.get("/{authority}/{uuid}/history", response_model=list[AssetHistoryEntry])
async def get_asset_history(
    authority: str,
    uuid: str,
    db: AsyncSession = Depends(get_db),
) -> list[AssetHistoryEntry]:
    daid = f"daid:{authority}:{uuid}"

    # Verify the asset exists first
    result = await db.execute(select(Asset).where(Asset.id == daid))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {daid}")

    hist_result = await db.execute(
        select(AssetHistory)
        .where(AssetHistory.asset_id == daid)
        .order_by(AssetHistory.version.asc())
    )
    return [
        AssetHistoryEntry(
            asset_id=h.asset_id,
            version=h.version,
            authority_data=AuthorityData(**(h.authority_data_json or {})),
            metadata=AssetMetadata(**(h.metadata_json or {})),
            updated_at=_utc(h.updated_at),
            signature=h.signature,
        )
        for h in hist_result.scalars()
    ]
