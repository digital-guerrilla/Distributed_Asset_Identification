"""Owner-authorized lifecycle transitions for accepted relationships."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.crypto import NodeKeyManager
from ..core.models import RelationshipState, RelationshipTransitionRequest
from ..db.database import get_db
from ..db.orm_models import Asset, AssetHistory
from ..dependencies import get_key_manager, require_api_key
from .assets import _push_to_peers, _signed_record, _utc, record_to_storage, orm_to_record

router = APIRouter(prefix="/v3/relationships", tags=["lifecycle"])

_ALLOWED_TRANSITIONS = {
    RelationshipState.PROPOSED: {RelationshipState.ACCEPTED, RelationshipState.REVOKED},
    RelationshipState.ACCEPTED: {RelationshipState.SUPERSEDED, RelationshipState.DISPUTED, RelationshipState.REVOKED},
    RelationshipState.DISPUTED: {RelationshipState.ACCEPTED, RelationshipState.SUPERSEDED, RelationshipState.REVOKED},
}


@router.post("/{relationship_id}/transition")
async def transition_relationship(
    relationship_id: str,
    body: RelationshipTransitionRequest,
    db: AsyncSession = Depends(get_db),
    key_manager: NodeKeyManager = Depends(get_key_manager),
    _: None = Depends(require_api_key),
) -> dict:
    rows = (await db.execute(select(Asset))).scalars()
    root_row = None
    root = None
    relationship = None
    for row in rows:
        candidate = orm_to_record(row)
        if not row.is_authoritative or candidate.authority != key_manager.public_key_multibase:
            continue
        match = next((item for item in candidate.relationships if item.relationship_id == relationship_id), None)
        if match is not None:
            root_row, root, relationship = row, candidate, match
            break
    if root_row is None or root is None or relationship is None:
        raise HTTPException(status_code=404, detail="Authoritative relationship not found")
    if body.new_state not in _ALLOWED_TRANSITIONS.get(relationship.state, set()):
        raise HTTPException(status_code=422, detail=f"Cannot transition relationship from {relationship.state.value} to {body.new_state.value}")

    claims = dict(relationship.claims)
    events = list(claims.get("lifecycle_events", []))
    events.append({
        "from": relationship.state.value,
        "to": body.new_state.value,
        "reason": body.reason,
        "authority": key_manager.public_key_multibase,
        "at": datetime.now(timezone.utc).isoformat(),
        "evidence": [item.model_dump(mode="json") for item in body.evidence],
    })
    updated_relationship = relationship.model_copy(update={
        "state": body.new_state,
        "claims": {**claims, "lifecycle_events": events},
    })
    relationships = [updated_relationship if item.relationship_id == relationship_id else item for item in root.relationships]
    db.add(AssetHistory(
        asset_id=root_row.id,
        version=root_row.version,
        record_json=root_row.record_json,
        raw_payload=root_row.raw_payload,
        updated_at=root_row.updated_at,
    ))
    updated_at = datetime.now(timezone.utc)
    updated = _signed_record(
        record_id=root.id,
        record_kind=root.record_kind.value,
        subject=root.subject,
        relationships=relationships,
        availability=root.availability,
        controller=root.controller,
        created_at=_utc(root.created_at),
        updated_at=updated_at,
        version=root.version + 1,
        key_manager=key_manager,
    )
    root_row.record_json, root_row.raw_payload = record_to_storage(updated)
    root_row.updated_at = updated_at
    root_row.version = updated.version
    root_row.verified_at = updated_at
    await db.commit()
    asyncio.create_task(_push_to_peers(updated))
    return {"relationship": updated_relationship.model_dump(mode="json"), "root_version": updated.version}