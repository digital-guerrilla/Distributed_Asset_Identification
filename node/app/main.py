"""
DAID Node — FastAPI application entry point.

Start with:
  uvicorn app.main:app --reload --port 8000
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import assets, discovery, federation, gossip as gossip_api, jsonld, node_info, resolve, ui as ui_router
from .config import settings
from .db.database import init_db
from .dependencies import get_key_manager
from .federation import gossip as gossip_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise database (creates tables if they don't exist)
    await init_db(settings.DATABASE_URL)

    # Pre-load / create the node keypair so any errors surface at startup
    km = get_key_manager()
    print(f"[daid] Node ID:    {settings.NODE_DOMAIN}")
    print(f"[daid] API base:   {settings.NODE_API_BASE}")
    print(f"[daid] Public key: {km.public_key_b64}")
    print(f"[daid] Role:       {settings.NODE_ROLE}")

    # Bootstrap gossip membership from seed peers
    await gossip_engine.bootstrap_peers()

    # Start background gossip loop (no-op for producer-role nodes)
    gossip_task = asyncio.create_task(gossip_engine.gossip_loop())

    yield

    # Graceful shutdown
    gossip_task.cancel()
    try:
        await gossip_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="DAID Node",
    description=(
        "Distributed Asset Identification Node — "
        "federated, cryptographically-signed product/asset tracking."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)

# /.well-known/daid/server  (no prefix)
app.include_router(discovery.router)

# /v1/assets  (CRUD + JSON-LD)
app.include_router(assets.router)
app.include_router(jsonld.router)

# /v1/resolve
app.include_router(resolve.router)

# /v1/federation
app.include_router(federation.router)

# /v1/gossip
app.include_router(gossip_api.router)

# /v1/node
app.include_router(node_info.router)


# /ui  (web dashboard)
app.include_router(ui_router.router)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": "DAID Node",
        "node_id": settings.NODE_DOMAIN,
        "api_version": "1.0",
        "docs": "/docs",
        "well_known": "/.well-known/daid/server",
        "ui_manufacturer": "/ui/manufacturer",
        "ui_client": "/ui/client",
    }
