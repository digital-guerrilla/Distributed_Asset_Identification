"""Content-addressed document upload, retrieval, and peer replication."""

import asyncio
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.crypto import NodeKeyManager
from ..core.models import DocumentRef
from ..db.database import get_db
from ..db.orm_models import Asset
from ..dependencies import get_key_manager, require_api_key, valid_api_key
from .assets import orm_to_record, replace_asset_subject, replication_endpoints

router = APIRouter(prefix="/v3/documents", tags=["documents"])


def _paths(sha256: str) -> tuple[Path, Path]:
    root = Path(settings.DOCUMENT_STORAGE_DIR)
    return root / sha256, root / f"{sha256}.json"


def _store(content: bytes, sha256: str, name: str, media_type: str) -> None:
    content_path, metadata_path = _paths(sha256)
    content_path.parent.mkdir(parents=True, exist_ok=True)
    content_path.write_bytes(content)
    metadata_path.write_text(
        json.dumps({"name": name, "media_type": media_type}, ensure_ascii=True),
        encoding="utf-8",
    )


async def _read_upload(request: Request) -> bytes:
    declared_size = int(request.headers.get("content-length", "0") or 0)
    if declared_size > settings.MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the configured size limit")
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="Document is empty")
    if len(content) > settings.MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds the configured size limit")
    return content


@router.post("/upload/{authority}/{record_uuid}", response_model=DocumentRef, status_code=201)
async def upload_document(
    authority: str,
    record_uuid: str,
    request: Request,
    file_name: str = Header(..., alias="x-file-name"),
    db: AsyncSession = Depends(get_db),
    key_manager: NodeKeyManager = Depends(get_key_manager),
    _: None = Depends(require_api_key),
) -> DocumentRef:
    record_id = f"daid://{settings.NODE_DOMAIN}/{authority}/{record_uuid}"
    row = (await db.execute(select(Asset).where(Asset.id == record_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Record not found: {record_id}")
    if not row.is_authoritative or authority != key_manager.public_key_multibase:
        raise HTTPException(status_code=403, detail="This node is not authoritative for the record")

    content = await _read_upload(request)
    sha256 = hashlib.sha256(content).hexdigest()
    media_type = request.headers.get("content-type") or "application/octet-stream"
    name = Path(file_name).name or "document"
    _store(content, sha256, name, media_type)

    document = DocumentRef(
        url=f"{settings.NODE_API_BASE.rstrip('/')}/v3/documents/{sha256}",
        media_type=media_type,
        sha256=sha256,
        name=name,
    )
    record = orm_to_record(row)
    if not any(item.sha256 == sha256 for item in record.subject.documents):
        subject = record.subject.model_copy(
            update={"documents": [*record.subject.documents, document]}
        )
        await replace_asset_subject(
            row=row,
            subject=subject,
            controller=record.controller,
            db=db,
            key_manager=key_manager,
        )
    asyncio.create_task(_push_document_to_peers(content, document, record.availability))
    return document


@router.post("/replica/{sha256}", status_code=202)
async def receive_document_replica(
    sha256: str,
    request: Request,
    file_name: str = Header("document", alias="x-file-name"),
) -> dict:
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256):
        raise HTTPException(status_code=422, detail="Invalid SHA-256 digest")
    content = await _read_upload(request)
    if hashlib.sha256(content).hexdigest() != sha256:
        raise HTTPException(status_code=400, detail="Document digest does not match content")
    media_type = request.headers.get("content-type") or "application/octet-stream"
    _store(content, sha256, Path(file_name).name or "document", media_type)
    return {"status": "accepted", "sha256": sha256}


@router.get("/{sha256}")
async def get_document(
    sha256: str,
    x_api_key: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    content_path, metadata_path = _paths(sha256)
    if not content_path.is_file():
        raise HTTPException(status_code=404, detail="Document is not stored on this node")
    rows = (await db.execute(select(Asset))).scalars()
    linked_records = [
        orm_to_record(row)
        for row in rows
        if any(item.sha256 == sha256 for item in orm_to_record(row).subject.documents)
    ]
    if linked_records and all(
        record.availability.visibility == "restricted" for record in linked_records
    ) and not valid_api_key(x_api_key):
        raise HTTPException(status_code=403, detail="Document access is restricted")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    return FileResponse(
        content_path,
        media_type=metadata.get("media_type", "application/octet-stream"),
        filename=metadata.get("name", "document"),
        content_disposition_type="inline",
    )


async def _push_document_to_peers(content: bytes, document: DocumentRef, availability) -> None:
    try:
        import httpx
        from ..federation.gossip import get_all_peers

        peers = [peer for peer in await get_all_peers() if peer.status == "alive"]
        endpoints = replication_endpoints(availability, peers)
        headers = {
            "content-type": document.media_type,
            "x-file-name": document.name or "document",
        }
        async with httpx.AsyncClient(timeout=settings.FEDERATION_TIMEOUT) as client:
            for endpoint in endpoints:
                try:
                    await client.post(
                        f"{endpoint}/v3/documents/replica/{document.sha256}",
                        content=content,
                        headers=headers,
                    )
                except Exception:
                    continue
    except Exception:
        return
