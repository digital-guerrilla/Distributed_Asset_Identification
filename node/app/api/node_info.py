"""DAID v3 node information endpoint."""

from fastapi import APIRouter, Depends

from ..config import settings
from ..core.crypto import NodeKeyManager
from ..core.models import NodeInfo
from ..dependencies import get_key_manager, require_api_key

router = APIRouter(prefix="/v3/node", tags=["node"])


@router.get("/info", response_model=NodeInfo)
async def get_node_info(
    key_manager: NodeKeyManager = Depends(get_key_manager),
) -> NodeInfo:
    return NodeInfo(
        routing_host=settings.NODE_DOMAIN,
        authority=key_manager.public_key_multibase,
        role=settings.NODE_ROLE,
    )


@router.get("/access")
async def check_node_access(_: None = Depends(require_api_key)) -> dict:
    return {"authorized": True, "routing_host": settings.NODE_DOMAIN, "role": settings.NODE_ROLE}
