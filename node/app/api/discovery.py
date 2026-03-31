"""
/.well-known/daid/server  — Node discovery document.

This endpoint is the trust anchor for the DAID protocol.
Any resolver fetches this before contacting the node API.

Response format:
  {
    "endpoint":    "https://api.acme.com",
    "node_id":     "products.acme.com",
    "public_key":  "base64 Ed25519 pubkey",
    "api_version": "1.0"
  }
"""

from fastapi import APIRouter, Depends

from ..config import settings
from ..core.crypto import NodeKeyManager
from ..core.models import WellKnownResponse
from ..dependencies import get_key_manager

router = APIRouter(tags=["discovery"])


@router.get("/.well-known/daid/server", response_model=WellKnownResponse)
async def well_known_server(
    key_manager: NodeKeyManager = Depends(get_key_manager),
) -> WellKnownResponse:
    """
    Return the discovery document for this node.

    Clients parse the authority from a DAID URI, then fetch this endpoint
    on that authority's domain to learn the API base URL and public key.
    """
    return WellKnownResponse(
        endpoint=settings.NODE_API_BASE,
        node_id=settings.NODE_DOMAIN,
        public_key=key_manager.public_key_b64,
        api_version="1.0",
    )
