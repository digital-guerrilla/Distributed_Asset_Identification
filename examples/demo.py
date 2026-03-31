from __future__ import annotations

"""
DAID 5-Node Mesh Demo
=====================
Self-contained: starts five DAID nodes automatically as subprocesses,
demonstrates the full mesh — each node is both an authority for its own
products and a caching peer for every other node's products.

Network topology:
  Alpha   (8091)  — IronForge Tools Co.       (industrial tools)
  Beta    (8092)  — AeroTech Components        (aerospace parts)
  Gamma   (8093)  — NovaTech Electronics       (sensors & modules)
  Delta   (8094)  — CoreDyne Systems           (compute hardware)
  Epsilon (8095)  — VaultSec Industries        (security hardware)

Mesh resolution flow demonstrated:
  1. Each node registers its own authoritative product(s)
  2. Beta  resolves Alpha's wrench  → remote_authoritative → caches it
  3. Gamma resolves Beta's fan      → remote_authoritative → caches it
  4. Delta resolves Gamma's sensor  → remote_authoritative → caches it
  5. Epsilon resolves Delta's chip  → remote_authoritative → caches it
  6. Alpha resolves Epsilon's vault → remote_authoritative → caches it
  7. Beta  resolves Alpha's wrench AGAIN → local_cache  (no network hop)
  8. Delta resolves Alpha's wrench  → remote_authoritative (different path)
  9. Show all cached records on Gamma (products from multiple authorities)

Run with:
    python examples/demo.py
"""

import asyncio
import json
import multiprocessing
import os
import shutil
import sys
import tempfile
import time

import httpx

# ---------------------------------------------------------------------------
# Subprocess entry point — must be at module level for Windows (spawn)
# ---------------------------------------------------------------------------

def _node_worker(node_dir: str, port: int, env: dict) -> None:
    for k, v in env.items():
        os.environ[k] = v
    sys.path.insert(0, node_dir)
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Paths & imports
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_DIR  = os.path.join(REPO_ROOT, "node")
sys.path.insert(0, REPO_ROOT)

from client.daid_client import DAIDClient  # noqa: E402

# ---------------------------------------------------------------------------
# Node registry
# ---------------------------------------------------------------------------

NODES = {
    "Alpha":   {"port": 8091, "key": "alpha-key",   "manufacturer": "IronForge Tools Co."},
    "Beta":    {"port": 8092, "key": "beta-key",    "manufacturer": "AeroTech Components"},
    "Gamma":   {"port": 8093, "key": "gamma-key",   "manufacturer": "NovaTech Electronics"},
    "Delta":   {"port": 8094, "key": "delta-key",   "manufacturer": "CoreDyne Systems"},
    "Epsilon": {"port": 8095, "key": "epsilon-key", "manufacturer": "VaultSec Industries"},
}

PRODUCTS = {
    "Alpha": [
        {
            "authority_data": {
                "name": "QuantumGrip Industrial Wrench",
                "manufacturer": "IronForge Tools Co.",
                "model_number": "QG-5500-PRO",
                "hardware_revision": "Rev C",
                # IFC 4.x property sets — BIM / facility management
                "ifc_psets": {
                    "Pset_ManufacturerTypeInformation": {
                        "Manufacturer": "IronForge Tools Co.",
                        "ModelLabel": "QG-5500-PRO",
                        "ProductionYear": "2025",
                        "GlobalTradeItemNumber": "00614141453245",
                    },
                    "Pset_ServiceLife": {
                        "ServiceLifeType": "MeanServiceLife",
                        "ServiceLifeDuration": "P10Y",
                    },
                    "Pset_Warranty": {
                        "WarrantyPeriod": "P3Y",
                        "WarrantyContent": "Full parts and labour",
                    },
                },
                # Content-addressed document map
                "documents": [
                    {
                        "type": "installation_manual",
                        "url": "https://cdn.ironforge.example/manuals/qg5500-v3.pdf",
                        "sha256": "a3f1c2d4e5b6789012345678901234567890abcdef1234567890abcdef123456",
                        "mime_type": "application/pdf",
                        "language": "en",
                        "version": "3.0",
                    },
                    {
                        "type": "ce_declaration",
                        "url": "https://certs.ironforge.example/ce/qg5500-2025.pdf",
                        "sha256": "b8d4e1f2a3c4567890abcdef1234567890abcdef1234567890abcdef12345678",
                        "mime_type": "application/pdf",
                    },
                ],
                # Supplemental schema.org fields
                "schema_org": {
                    "offers": {"@type": "Offer", "availability": "https://schema.org/InStock"},
                },
            },
            "metadata": {
                "category": "industrial-tools",
                "sku": "IFT-QG5500",
                "gtin": "00614141453245",
                "origin_country": "DE",
                "tags": ["certified-iso9001", "hand-tool"],
                "attributes": {"torque_nm": 550, "weight_kg": 2.4},
            },
        },
        {
            "authority_data": {
                "name": "NanoTorque Precision Driver",
                "manufacturer": "IronForge Tools Co.",
                "model_number": "NT-PD-200",
                "hardware_revision": "Rev A",
            },
            "metadata": {
                "category": "precision-tools",
                "sku": "IFT-NTPD200",
                "attributes": {"torque_nm": 2.5, "bit_count": 26},
            },
        },
    ],
    "Beta": [
        {
            "authority_data": {
                "name": "TurboFan Thrust Module",
                "manufacturer": "AeroTech Components",
                "model_number": "TF-X200-EC",
                "serial_number": None,
                "firmware_version": "4.2.1",
            },
            "metadata": {
                "category": "aerospace",
                "sku": "ATC-TFX200",
                "origin_country": "US",
                "tags": ["FAA-approved", "turbine"],
                "attributes": {"thrust_kg": 200, "rpm_max": 45000},
            },
        },
    ],
    "Gamma": [
        {
            "authority_data": {
                "name": "ProSensor Environmental Array",
                "manufacturer": "NovaTech Electronics",
                "model_number": "PS-ENV-X9",
                "hardware_revision": "Rev B",
                "firmware_version": "2.0.0",
            },
            "metadata": {
                "category": "sensors",
                "sku": "NTE-PSENVX9",
                "tags": ["IoT", "multi-sensor"],
                "attributes": {
                    "sensors": ["temperature", "humidity", "pressure", "VOC"],
                    "interface": "I2C/SPI",
                },
            },
        },
    ],
    "Delta": [
        {
            "authority_data": {
                "name": "MegaCore AI Processor",
                "manufacturer": "CoreDyne Systems",
                "model_number": "MC-AI-3000",
                "hardware_revision": "Rev D",
            },
            "metadata": {
                "category": "compute",
                "sku": "CDS-MCAI3000",
                "origin_country": "TW",
                "tags": ["edge-AI", "RISC-V"],
                "attributes": {"cores": 128, "tops": 300, "tdp_w": 15},
            },
        },
    ],
    "Epsilon": [
        {
            "authority_data": {
                "name": "SecureVault HSM Module",
                "manufacturer": "VaultSec Industries",
                "model_number": "SV-HSM-100",
                "hardware_revision": "Rev A",
                "firmware_version": "1.5.3",
            },
            "metadata": {
                "category": "security-hardware",
                "sku": "VSI-SVHSM100",
                "tags": ["FIPS-140-3", "HSM", "cryptography"],
                "attributes": {"key_store_capacity": 10000, "interface": "USB/PCIe"},
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_url(name: str) -> str:
    return f"http://127.0.0.1:{NODES[name]['port']}"


def _wait_for_node(url: str, timeout: int = 25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with httpx.Client(timeout=2) as c:
                if c.get(url).status_code < 500:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def _sep(title: str) -> None:
    print(f"\n{'═' * 66}")
    print(f"  {title}")
    print("═" * 66)


def _sub(title: str) -> None:
    print(f"\n  ── {title}")


def _asset_summary(asset, source: str = "", verified: bool | None = None) -> None:
    ad = asset.authority_data if isinstance(asset.authority_data, dict) else {}
    print(f"     DAID:         {asset.id}")
    print(f"     Name:         {ad.get('name', asset.authority_data)}")
    print(f"     Manufacturer: {ad.get('manufacturer', '—')}")
    print(f"     Model No.:    {ad.get('model_number', '—')}")
    print(f"     Version:      {asset.version}")
    if source:
        verified_str = f"  verified={verified}" if verified is not None else ""
        print(f"     Source:       {source}{verified_str}")


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

async def main() -> None:
    tmpdir = tempfile.mkdtemp(prefix="daid_mesh_demo_")
    processes = []

    try:
        # ------------------------------------------------------------------
        # Start all 5 nodes
        # ------------------------------------------------------------------
        print("\n[daid] Spinning up 5-node mesh…\n")
        all_ports = [cfg["port"] for cfg in NODES.values()]
        for name, cfg in NODES.items():
            port = cfg["port"]
            # Gossip seeds: all other nodes (self will be filtered out by gossip engine)
            seeds = ",".join(
                f"http://127.0.0.1:{p}" for p in all_ports if p != port
            )
            env = {
                "NODE_DOMAIN":              f"127.0.0.1:{port}",
                "NODE_API_BASE":            f"http://127.0.0.1:{port}",
                "API_KEY":                  cfg["key"],
                "DATABASE_URL":             f"sqlite+aiosqlite:///{tmpdir}/{name.lower()}.db",
                "PRIVATE_KEY_FILE":         f"{tmpdir}/{name.lower()}.bin",
                "GOSSIP_SEEDS":             seeds,
                "GOSSIP_INTERVAL":          "5",
                "GOSSIP_SUSPECT_TIMEOUT":   "120",
                "GOSSIP_DEAD_TIMEOUT":      "300",
                "NODE_ROLE":                "resolver",
            }
            p = multiprocessing.Process(
                target=_node_worker, args=(NODE_DIR, port, env), daemon=True
            )
            p.start()
            processes.append(p)

        # Wait for all nodes
        all_ready = all(_wait_for_node(_node_url(n)) for n in NODES)
        if not all_ready:
            print("[daid] ERROR: One or more nodes failed to start.")
            sys.exit(1)

        print("[daid] All 5 nodes ready.")
        for name, cfg in NODES.items():
            print(f"         {name:8s} → {_node_url(name)}  ({cfg['manufacturer']})")

        # ------------------------------------------------------------------
        # Phase 1 — Each node registers its authoritative products
        # ------------------------------------------------------------------
        _sep("PHASE 1 — Authority nodes register their products")

        registered: dict[str, list] = {}
        for name, products in PRODUCTS.items():
            registered[name] = []
            async with DAIDClient(_node_url(name), api_key=NODES[name]["key"]) as client:
                for product in products:
                    asset = await client.create_asset(
                        authority_data=product["authority_data"],
                        metadata=product.get("metadata", {}),
                    )
                    registered[name].append(asset)
                    mfr = product["authority_data"]["manufacturer"]
                    mdl = product["authority_data"]["model_number"]
                    print(f"  [{name}] Registered {mdl} ({mfr})")
                    print(f"          → {asset.id}")

        # ------------------------------------------------------------------
        # Phase 2 — Mesh ring resolution (each node resolves its neighbour's asset)
        # ------------------------------------------------------------------
        _sep("PHASE 2 — Mesh ring: each node resolves its neighbour's product")
        print("  (HTTPS .well-known lookup → fetch from authority → verify Ed25519 sig → cache)")

        ring = [
            ("Beta",    "Alpha"),   # Beta  resolves Alpha's wrench
            ("Gamma",   "Beta"),    # Gamma resolves Beta's fan
            ("Delta",   "Gamma"),   # Delta resolves Gamma's sensor
            ("Epsilon", "Delta"),   # Epsilon resolves Delta's chip
            ("Alpha",   "Epsilon"), # Alpha  resolves Epsilon's vault
        ]

        for resolver_name, authority_name in ring:
            daid = registered[authority_name][0].id
            _sub(f"{resolver_name} resolves {authority_name}'s product")
            async with DAIDClient(_node_url(resolver_name)) as client:
                result = await client.resolve(daid)
            _asset_summary(result.asset, source=result.source, verified=result.verified)

        # ------------------------------------------------------------------
        # Phase 3 — Cache hit demo (Beta resolves Alpha again — from cache)
        # ------------------------------------------------------------------
        _sep("PHASE 3 — Cache hit: Beta resolves Alpha's product a second time")
        print("  (Should be served from Beta's local cache — no network hop to Alpha)")

        daid = registered["Alpha"][0].id
        async with DAIDClient(_node_url("Beta")) as client:
            result = await client.resolve(daid)
        _asset_summary(result.asset, source=result.source, verified=result.verified)
        assert result.source == "local_cache", f"Expected local_cache, got {result.source}"
        print("\n  ✓ Confirmed: served from local_cache (no authority contacted)")

        # ------------------------------------------------------------------
        # Phase 4 — Cross-mesh: Delta resolves Alpha (never cached on Delta)
        # ------------------------------------------------------------------
        _sep("PHASE 4 — Cross-mesh: Delta resolves Alpha's wrench (cold path)")
        print("  (Delta has never seen this product — routes directly to Alpha)")

        daid = registered["Alpha"][0].id
        async with DAIDClient(_node_url("Delta")) as client:
            result = await client.resolve(daid)
        _asset_summary(result.asset, source=result.source, verified=result.verified)

        # ------------------------------------------------------------------
        # Phase 5 — Gamma's cache shows products from multiple authorities
        # ------------------------------------------------------------------
        _sep("PHASE 5 — Gamma's node now holds products from multiple authorities")

        async with DAIDClient(_node_url("Gamma")) as client:
            all_assets = await client.list_assets()

        print(f"  Gamma holds {len(all_assets)} records:\n")
        for a in all_assets:
            ad = a.authority_data
            flag = "★ AUTHORITATIVE" if a.authority == f"127.0.0.1:{NODES['Gamma']['port']}" else "  cached"
            print(f"  {flag}  {ad.get('manufacturer','?'):30s}  {ad.get('model_number','?')}")

        # ------------------------------------------------------------------
        # Phase 6 — Discovery documents for all 5 nodes
        # ------------------------------------------------------------------
        _sep("PHASE 6 — /.well-known/daid/server for all 5 nodes")

        for name in NODES:
            async with DAIDClient(_node_url(name)) as client:
                wk = await client.get_well_known()
            print(f"\n  [{name}]  node_id={wk['node_id']}")
            print(f"           pubkey ={wk['public_key'][:32]}…")

        # ------------------------------------------------------------------
        # Phase 7 — schema.org JSON-LD for Alpha's wrench (with IFC + docs)
        # ------------------------------------------------------------------
        _sep("PHASE 7 — schema.org JSON-LD for Alpha's wrench")
        print("  (Fetched from Beta — which cached it — demonstrating resolver JSON-LD)")

        daid = registered["Alpha"][0].id
        async with DAIDClient(_node_url("Beta")) as client:
            jsonld = await client.get_jsonld(daid)

        print(f"\n  @type:          {jsonld.get('@type')}")
        print(f"  name:           {jsonld.get('name')}")
        brand = jsonld.get('brand', {})
        print(f"  brand.name:     {brand.get('name') if isinstance(brand, dict) else brand}")
        print(f"  model:          {jsonld.get('model')}")
        print(f"  sku:            {jsonld.get('sku', '—')}")
        print(f"  gtin:           {jsonld.get('gtin', '—')}")
        print(f"  daid:id:        {jsonld.get('daid:id')}")
        print(f"  daid:version:   {jsonld.get('daid:version')}")
        docs = jsonld.get("subjectOf", [])
        if docs:
            print(f"\n  Documents ({len(docs)}):")
            for doc in docs:
                print(f"    [{doc.get('daid:documentType')}]  {doc.get('url')}")
                if doc.get('daid:sha256'):
                    print(f"      sha256: {doc['daid:sha256'][:32]}…")
        ifc_psets = jsonld.get("ifc:hasPropertySet", [])
        if ifc_psets:
            print(f"\n  IFC Property Sets ({len(ifc_psets)}):")
            for pset in ifc_psets:
                pset_name = pset.get("@type", "?")
                print(f"    {pset_name}")
                for k, v in pset.items():
                    if k != "@type":
                        print(f"      {k}: {v}")

        # ------------------------------------------------------------------
        # Phase 8 — Gossip mesh view
        # ------------------------------------------------------------------
        _sep("PHASE 8 — Gossip membership (waiting for rounds to propagate…)")
        print("  Gossip interval=5s — waiting 18s for full mesh convergence…")
        await asyncio.sleep(18)

        for name in NODES:
            async with DAIDClient(_node_url(name)) as client:
                peers = await client.get_gossip_peers()
            alive = [p for p in peers if p["status"] == "alive"]
            print(f"\n  [{name}]  knows {len(peers)} peer(s) ({len(alive)} alive):")
            for p in sorted(peers, key=lambda x: x["node_id"]):
                pk = (p.get("public_key") or "")[:24]
                print(f"    {p['status']:8s}  gen={p['generation']:3d}  "
                      f"{p['node_id']:22s}  pubkey={pk}…")

        print("\n\n✓ 5-node mesh demo complete.\n")

    finally:
        for p in processes:
            p.terminate()
        shutil.rmtree(tmpdir, ignore_errors=True)
        print("[daid] All nodes stopped, temp data cleaned up.")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    asyncio.run(main())


