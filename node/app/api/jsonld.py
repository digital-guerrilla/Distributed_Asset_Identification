"""
schema.org JSON-LD serialisation endpoint.

  GET /v1/assets/{authority}/{uuid}/jsonld

Returns the asset record as a schema.org JSON-LD document, with the
following type mapping:

  - Individual unit (serial_number set)  → schema:IndividualProduct
  - Product type (no serial_number)      → schema:Product

The full signed AssetRecord is embedded as a custom 'daid:record'
property so that consumers who understand the protocol can extract
and verify it. The IFC Psets and document list are also embedded
under their own namespaced properties.

JSON-LD context references:
  https://schema.org/
  https://standards.buildingsmart.org/IFC/ (informal namespace)
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..core.models import AssetRecord, AssetMetadata, AuthorityData
from ..db.database import get_db
from ..db.orm_models import Asset
from ..dependencies import get_key_manager

from fastapi import Depends

router = APIRouter(prefix="/v1/assets", tags=["assets"])


@router.get("/{authority}/{uuid}/jsonld")
async def get_asset_jsonld(
    authority: str,
    uuid: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Return the asset as a schema.org JSON-LD document.

    Compatible with Shopify, Google Merchant Centre, and any JSON-LD consumer.
    IFC property sets are embedded under the 'ifc:' namespace for BIM tooling.
    """
    daid = f"daid:{authority}:{uuid}"
    result = await db.execute(select(Asset).where(Asset.id == daid))
    asset_row = result.scalar_one_or_none()
    if asset_row is None:
        raise HTTPException(status_code=404, detail=f"Asset not found: {daid}")

    ad_raw = asset_row.authority_data_json or {}
    meta_raw = asset_row.metadata_json or {}

    ad = AuthorityData(**ad_raw)
    meta = AssetMetadata(**meta_raw)

    # Base URL for this record
    self_url = f"{settings.NODE_API_BASE.rstrip('/')}/v1/assets/{authority}/{uuid}"

    # schema.org type selection
    schema_type = "IndividualProduct" if ad.serial_number else "Product"

    jsonld: dict = {
        "@context": {
            "@vocab": "https://schema.org/",
            "ifc": "https://standards.buildingsmart.org/IFC/DEV/IFC4_3/OWL#",
            "daid": "https://daid.protocol/v1/",
        },
        "@type": schema_type,
        "@id": self_url,

        # Core identity — schema.org
        "name": ad.name,
        "brand": {
            "@type": "Brand",
            "name": ad.manufacturer,
        },
        "model": ad.model_number,

        # Optional core fields
        **({"serialNumber": ad.serial_number} if ad.serial_number else {}),
        **({"description": meta.description} if meta.description else {}),
        **({"sku": meta.sku} if meta.sku else {}),
        **({"gtin": meta.gtin} if meta.gtin else {}),
        **({"countryOfOrigin": {"@type": "Country", "identifier": meta.origin_country}} if meta.origin_country else {}),
        **({"category": meta.category} if meta.category else {}),

        # Offers placeholder (Shopify/Google merchant friendly)
        # Populate via schema_org supplemental dict if needed
    }

    # Merge any supplemental schema.org fields the authority explicitly set
    if ad.schema_org:
        jsonld.update(ad.schema_org)

    # Document map → schema.org subjectOf + daid:documents
    if ad.documents:
        jsonld["subjectOf"] = []
        for doc in ad.documents:
            entry: dict = {
                "@type": "CreativeWork",
                "encodingFormat": doc.mime_type or "application/octet-stream",
                "url": doc.url,
            }
            if doc.version:
                entry["version"] = doc.version
            if doc.language:
                entry["inLanguage"] = doc.language
            if doc.sha256:
                entry["daid:sha256"] = doc.sha256
            entry["daid:documentType"] = doc.type
            jsonld["subjectOf"].append(entry)

    # IFC Psets → ifc: namespace
    if ad.ifc_psets:
        psets_dict = ad.ifc_psets.model_dump(exclude_none=True)
        # Merge custom psets up into the same dict
        custom = psets_dict.pop("custom", None) or {}
        psets_dict.update(custom)
        if psets_dict:
            jsonld["ifc:hasPropertySet"] = [
                {"@type": f"ifc:{pset_name}", **props}
                for pset_name, props in psets_dict.items()
            ]

    # Embed the canonical DAID URI and signature for protocol-aware consumers
    jsonld["daid:id"] = daid
    jsonld["daid:authority"] = authority
    jsonld["daid:version"] = asset_row.version
    if asset_row.signature:
        jsonld["daid:signature"] = asset_row.signature

    return JSONResponse(
        content=jsonld,
        media_type="application/ld+json",
    )
