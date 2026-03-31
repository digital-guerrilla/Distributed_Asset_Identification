"""
Node information endpoint.

GET /v1/node/info  — returns node identity, public key, and capabilities.
"""

from fastapi import APIRouter, Depends

from ..config import settings
from ..core.crypto import NodeKeyManager
from ..core.models import NodeInfo
from ..dependencies import get_key_manager

router = APIRouter(prefix="/v1/node", tags=["node"])


@router.get("/info", response_model=NodeInfo)
async def get_node_info(
    key_manager: NodeKeyManager = Depends(get_key_manager),
) -> NodeInfo:
    features = ["assets", "federation", "history", "resolve", "jsonld", "schema.org", "ifc-psets"]
    if settings.NODE_ROLE in ("resolver", "full"):
        features.append("gossip")
    return NodeInfo(
        node_id=settings.NODE_DOMAIN,
        public_key=key_manager.public_key_b64,
        supported_features=features,
    )
