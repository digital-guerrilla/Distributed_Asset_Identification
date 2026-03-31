# DAID — Distributed Asset Identification

A federated, encrypted, node-based product and asset tracking protocol.  
Each asset is assigned a globally unique, routable identifier. Any node on the
network can resolve that identifier to a cryptographically-verified record by
routing the request to the authoritative node — without a central registry.

Conceptually similar to the [Matrix protocol](https://matrix.org/) for
messaging or [ActivityPub](https://activitypub.rocks/) for social media, but
purpose-built for **supply-chain asset databasing**.

---

## Core Concepts

| Concept | Description |
|---|---|
| **DAID URI** | `daid:{authority}:{uuid4}` — globally unique, self-routing |
| **Authority Node** | The server responsible for issuing and owning a record |
| **Federation** | Any node can cache/mirror records; authority node is source of truth |
| **Cryptographic Signing** | Every record is signed with the authority node's Ed25519 key |
| **Discovery** | Nodes are found via `/.well-known/daid/server` on the authority domain |

### Example DAID URI

```
daid:products.acme.com:550e8400-e29b-41d4-a716-446655440000
      └───────────────┘ └──────────────────────────────────┘
         Authority            UUID v4 (unique asset ID)
```

To resolve this asset, any client or peer node:
1. Parses the authority: `products.acme.com`
2. Fetches `https://products.acme.com/.well-known/daid/server` → gets the API endpoint + public key
3. Fetches the record from the authority node's API
4. Verifies the Ed25519 signature using the public key
5. Trusts nothing without a valid signature

---

## Architecture at a Glance

```
   CLIENT                    PEER NODE B                  AUTHORITY NODE A
     │                           │                              │
     │  resolve(daid:nodeA.com:uuid)                           │
     │──────────────────────────>│                              │
     │                           │  GET /.well-known/daid/server│
     │                           │─────────────────────────────>│
     │                           │<─── {endpoint, public_key} ──│
     │                           │  GET /v1/assets/nodeA.com/uuid
     │                           │─────────────────────────────>│
     │                           │<───── signed AssetRecord ────│
     │                           │  verify_sig(record, pubkey)  │
     │<──── verified record ─────│                              │
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Docker (optional, for multi-node development)

### Run a single node

```bash
cd node
pip install -r requirements.txt

# Copy and edit the environment file
cp ../.env.example .env

# Start the node
uvicorn app.main:app --reload --port 8000
```

The node will auto-generate an Ed25519 keypair on first run and save it to the
path configured in `PRIVATE_KEY_FILE`.

### Run two federated nodes (Docker)

```bash
docker compose up --build
# Node Alpha → http://localhost:8001
# Node Beta  → http://localhost:8002
```

### Register an asset

```bash
curl -X POST http://localhost:8000/v1/assets \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-api-key" \
  -d '{
    "metadata": {
      "name": "Widget Pro 3000",
      "category": "electronics",
      "manufacturer": "Acme Corp",
      "sku": "WP-3000",
      "gtin": "00012345678905"
    }
  }'
```

Response:
```json
{
  "id": "daid:localhost:8000:550e8400-e29b-41d4-a716-446655440000",
  "authority": "localhost:8000",
  "metadata": { "name": "Widget Pro 3000", ... },
  "created_at": "2026-03-31T12:00:00+00:00",
  "updated_at": "2026-03-31T12:00:00+00:00",
  "version": 1,
  "signature": "base64-encoded-ed25519-signature"
}
```

### Resolve an asset (from any node)

```bash
# Any node can resolve any DAID — it routes automatically
curl "http://localhost:8002/v1/resolve/localhost:8000/550e8400-e29b-41d4-a716-446655440000"
```

### Python client SDK

```python
import asyncio
from client.daid_client import DAIDClient

async def main():
    client = DAIDClient("http://localhost:8000", api_key="your-api-key")

    # Create an asset
    asset = await client.create_asset({
        "name": "Widget Pro 3000",
        "manufacturer": "Acme Corp",
        "sku": "WP-3000"
    })
    print(f"Created: {asset.id}")

    # Resolve from any node (routes automatically, verifies signature)
    result = await client.resolve(asset.id)
    print(f"Verified: {result.verified}, Source: {result.source}")

asyncio.run(main())
```

---

## Project Structure

```
├── README.md
├── docs/
│   ├── architecture.md          # Deep-dive architecture
│   └── protocol-spec.md         # Protocol specification
├── node/                        # Node server (Python / FastAPI)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI entry point
│       ├── config.py            # Settings (env-driven)
│       ├── dependencies.py      # FastAPI dependency injection
│       ├── core/
│       │   ├── guid.py          # DAID parsing and generation
│       │   ├── crypto.py        # Ed25519 signing and verification
│       │   └── models.py        # Pydantic data models
│       ├── db/
│       │   ├── database.py      # Async SQLAlchemy setup
│       │   └── orm_models.py    # ORM table definitions
│       ├── api/
│       │   ├── assets.py        # Asset CRUD endpoints
│       │   ├── federation.py    # Node-to-node sync endpoint
│       │   ├── discovery.py     # /.well-known/daid/server
│       │   └── node_info.py     # Node metadata endpoint
│       └── federation/
│           ├── client.py        # Push records to peer nodes
│           └── resolver.py      # Resolve DAIDs from remote nodes
├── client/
│   └── daid_client.py           # Python SDK
├── examples/
│   └── demo.py                  # Full workflow demonstration
├── docker-compose.yml
└── .env.example
```

---

## API Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/v1/assets` | — | List assets on this node |
| `GET` | `/v1/assets/{authority}/{uuid}` | — | Get a specific asset (local) |
| `POST` | `/v1/assets` | API Key | Register a new asset |
| `PUT` | `/v1/assets/{authority}/{uuid}` | API Key | Update asset metadata |
| `GET` | `/v1/assets/{authority}/{uuid}/history` | — | Version history |
| `GET` | `/v1/resolve/{authority}/{uuid}` | — | Resolve from network (routed) |
| `POST` | `/v1/federation/sync` | — | Receive a synced record from a peer |
| `GET` | `/v1/node/info` | — | Node public key and capabilities |
| `GET` | `/.well-known/daid/server` | — | Node discovery document |

---

## Security Model

- **Signatures**: Every record is signed with the authority node's Ed25519 private key. Clients and peer nodes verify before trusting.
- **Authority enforcement**: Only the node whose domain matches the DAID authority can issue or update a record.
- **Transport**: All production traffic must use TLS (HTTPS). The `.well-known` lookup enforces HTTPS first.
- **API Keys**: Write operations require an API key (header `x-api-key`). Rotate this regularly; replace with JWT/mTLS for production.
- **No blind trust of caches**: Cached records on peer nodes are always verified against the authority node's public key before being stored.

---

## Comparison with Matrix Protocol

| Feature | Matrix | DAID |
|---|---|---|
| Federation model | Federated homeservers | Federated authority nodes |
| Global ID format | `@user:server.com` | `daid:node.com:uuid4` |
| Discovery | DNS + `.well-known` | DNS + `.well-known/daid/server` |
| Data type | Messages/rooms | Asset/product records |
| Cryptographic proofs | Room state signatures | Ed25519 record signatures |
| Authority | Room creator's server | Record-issuing node |
| Caching | Server-side sync | Peer node caching with sig verify |

---

## Roadmap

- [ ] DHT-based discovery (no DNS dependency)
- [ ] Verifiable Credentials (W3C VC) export format
- [ ] DID method (`did:daid:...`) for W3C compatibility
- [ ] Webhook/event subscriptions for record changes
- [ ] Asset lineage graph (tracks components → assemblies)
- [ ] Recall/revocation mechanism with propagation
- [ ] Web UI for node management
- [ ] gRPC transport option for high-throughput federation
