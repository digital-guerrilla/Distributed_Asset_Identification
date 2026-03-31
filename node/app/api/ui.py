"""
Web UI endpoints.

  GET /ui/manufacturer  — Manufacturer dashboard (create/edit products, JSON-LD, gossip)
  GET /ui/client        — Client product lookup (resolve by DAID, browse, inspect)
  GET /ui               — Redirects to /ui/manufacturer
"""

import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter(tags=["ui"])

_STATIC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "static"))


def _f(name: str) -> str:
    return os.path.join(_STATIC, name)


@router.get("/ui", include_in_schema=False)
async def ui_root():
    return RedirectResponse("/ui/manufacturer")


@router.get("/ui/manufacturer", include_in_schema=False)
async def manufacturer_ui():
    return FileResponse(_f("manufacturer.html"), media_type="text/html")


@router.get("/ui/client", include_in_schema=False)
async def client_ui():
    return FileResponse(_f("client.html"), media_type="text/html")
