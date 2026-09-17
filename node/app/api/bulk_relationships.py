"""Batch relationship proposals for contractor and supplier integrations."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.crypto import NodeKeyManager
from ..core.models import (
    BulkRelationshipProposalRequest,
    BulkRelationshipProposalResponse,
    BulkRelationshipProposalResult,
)
from ..db.database import get_db
from ..dependencies import get_key_manager, require_api_key
from .relationships import propose_relationship

router = APIRouter(prefix="/v3/relationships", tags=["relationships"])


@router.post("/bulk-proposals", response_model=BulkRelationshipProposalResponse, status_code=201)
async def bulk_propose_relationships(
    body: BulkRelationshipProposalRequest,
    db: AsyncSession = Depends(get_db),
    key_manager: NodeKeyManager = Depends(get_key_manager),
    _: None = Depends(require_api_key),
) -> BulkRelationshipProposalResponse:
    results: list[BulkRelationshipProposalResult] = []
    for index, proposal in enumerate(body.proposals):
        try:
            relationship = await propose_relationship(proposal, db, key_manager, None)
            results.append(BulkRelationshipProposalResult(
                index=index,
                status="proposed",
                relationship=relationship,
            ))
        except Exception as error:
            results.append(BulkRelationshipProposalResult(
                index=index,
                status="failed",
                error=str(error),
            ))
    return BulkRelationshipProposalResponse(
        batch_id=str(uuid.uuid4()),
        total=len(results),
        proposed=sum(item.status == "proposed" for item in results),
        failed=sum(item.status == "failed" for item in results),
        results=results,
    )