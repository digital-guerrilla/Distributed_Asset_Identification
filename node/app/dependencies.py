"""
FastAPI dependency providers.

- Key manager: singleton Ed25519 keypair for this node.
- API key guard: protects write endpoints.
"""

from fastapi import Header, HTTPException

from .config import settings
from .core.crypto import NodeKeyManager

_key_manager: NodeKeyManager | None = None


def get_key_manager() -> NodeKeyManager:
    """
    FastAPI dependency — returns the node's singleton key manager.
    Loaded/created once on first call; subsequent calls return the same instance.
    """
    global _key_manager
    if _key_manager is None:
        _key_manager = NodeKeyManager.load_or_create(settings.PRIVATE_KEY_FILE)
    return _key_manager


def require_api_key(x_api_key: str = Header(default=None)) -> None:
    """
    FastAPI dependency — raises 401 if the x-api-key header is missing or wrong.
    Use as: `_: None = Depends(require_api_key)`
    """
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
