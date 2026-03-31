# DAID Architecture — Deep Dive

## 1. Overview

DAID is a **federated asset identification network**. There is no central
registry. Instead, any organization runs one or more **authority nodes** that
own a namespace (their domain) and issue records within it. Any other node,
client, or service can resolve any DAID URI without being registered — just
like you can fetch any webpage without asking permission from a central server.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DAID Network                                 │
│                                                                     │
│  ┌──────────────┐    federates    ┌──────────────┐                  │
│  │  acme.com    │◄───────────────►│  supplier.io │                  │
│  │  Node        │                 │  Node        │                  │
│  │              │    federates    └──────────────┘                  │
│  │  daid:acme   │◄────────────────────────────────►┌─────────────┐  │
│  └──────────────┘                                  │  retail.net │  │
│         ▲                                          │  Node       │  │
│         │ resolves                                 └─────────────┘  │
│  ┌──────┴──────┐                                        ▲           │
│  │   Client    │────────────── resolves ────────────────┘           │
│  └─────────────┘                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. DAID URI Format

```
daid : {authority} : {uuid4}
└─┘   └──────────┘   └─────────────────────────────────────────────┘
scheme  domain:port    UUID v4 — 128-bit random, globally unique

Examples:
  daid:products.acme.com:550e8400-e29b-41d4-a716-446655440000
  daid:assets.supplier.io:6ba7b810-9dad-11d1-80b4-00c04fd430c8
  daid:localhost:8001:a8098c1a-f86e-11da-bd1a-00112444be1e
```

### Properties

- **Self-routing**: The authority embedded in the URI tells any resolver
  exactly where to find the record — no lookup table needed.
- **Opaque UUID**: The UUID component is randomly generated (v4), giving no
  information about the issuing system's internal structure.
- **Authority ownership**: Only the node whose domain matches the authority
  segment can issue, update, or revoke a record with that authority.
- **Globally unique**: Combination of authority + UUID v4 is practically
  collision-proof (2^122 possible UUIDs per authority).

---

## 3. Node Architecture

Each DAID node is an independent service with these internal components:

```
┌───────────────────────────────────────────────────────┐
│                      DAID Node                        │
│                                                       │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  REST API   │  │  Federation  │  │  Discovery   │  │
│  │  /v1/assets │  │  /v1/fed/    │  │  /.well-known│  │
│  └──────┬──────┘  └──────┬───────┘  └──────────────┘  │
│         │                │                            │
│  ┌──────▼────────────────▼─────────────────────────┐  │
│  │                 Business Logic                  │  │
│  │   Asset CRUD │ Signature Verify │ Resolver      │  │
│  └──────────────────────┬──────────────────────────┘  │
│                         │                             │
│  ┌──────────────┐  ┌────▼─────────┐  ┌─────────────┐  │
│  │  Key Manager │  │   Database   │  │  Federation │  │
│  │  Ed25519     │  │  SQLAlchemy  │  │  HTTP Client│  │
│  │  Private Key │  │  (async)     │  │  (httpx)    │  │
│  └──────────────┘  └──────────────┘  └─────────────┘  │
└───────────────────────────────────────────────────────┘
```

### Storage

A node stores two categories of records:

| Type | `is_authoritative` | Description |
|---|---|---|
| **Authoritative** | `true` | Issued by this node; this node has the private key that signed them |
| **Cached** | `false` | Obtained from a remote authority node; stored locally for performance; signature verified before storing |

Cached records must always be re-verifiable. The authority node's public key
is fetched fresh from their `.well-known` endpoint when verifying.

---

## 4. Discovery Protocol

Node discovery uses the same pattern as Matrix's server-server API and
ActivityPub's WebFinger: an HTTPS-accessible well-known document.

```
Step 1: Parse authority from DAID
        daid:products.acme.com:uuid  →  authority = "products.acme.com"

Step 2: Fetch discovery document
        GET https://products.acme.com/.well-known/daid/server

        Response:
        {
          "endpoint":    "https://api.acme.com",
          "node_id":     "products.acme.com",
          "public_key":  "base64url-encoded-ed25519-public-key",
          "api_version": "1.0"
        }

Step 3: Fetch the asset record
        GET https://api.acme.com/v1/assets/products.acme.com/{uuid}

Step 4: Verify signature
        verify_ed25519(
          message   = canonical_json(record, excluding "signature" field),
          signature = record.signature,
          pubkey    = well_known.public_key
        )
```

**Security note**: The well-known endpoint MUST be served over HTTPS. The
public key in the well-known document is the trust anchor — it is fetched
fresh on every resolution (no long-lived key caching) unless a local trust
store is explicitly configured.

---

## 5. Cryptographic Model

### Key Generation

Each node generates a single **Ed25519** keypair on first boot:
- **Private key**: 32 bytes, stored at `PRIVATE_KEY_FILE` path, never leaves the node
- **Public key**: 32 bytes, published openly via `/.well-known/daid/server`

Ed25519 was chosen over RSA/ECDSA because:
- Deterministic signatures (no random nonce leakage)
- Very fast sign/verify (~100k ops/sec)
- Small key + signature size (32 + 64 bytes)
- Resistant to side-channel attacks

### What Gets Signed

The signature covers a **canonical JSON** representation of the record,
excluding the `signature` field itself:

```json
{
  "authority": "products.acme.com",
  "created_at": "2026-03-31T12:00:00+00:00",
  "id": "daid:products.acme.com:550e8400-e29b-41d4-a716-446655440000",
  "metadata": {
    "category": "electronics",
    "manufacturer": "Acme Corp",
    "name": "Widget Pro 3000",
    "sku": "WP-3000"
  },
  "updated_at": "2026-03-31T12:00:00+00:00",
  "version": 1
}
```

Canonical form rules:
1. Keys sorted alphabetically at every nesting level
2. No extra whitespace (`separators=(',', ':')`)
3. All datetime values in UTC ISO 8601 format (`+00:00`)
4. The `signature` key is excluded from the signed payload

### Signature Verification Flow

```
Resolver                   Client/Peer Node
    │
    │  1. Fetch well-known document (get public_key)
    │
    │  2. Fetch asset record
    │
    │  3. Remove "signature" from record
    │
    │  4. Serialize to canonical JSON
    │
    │  5. Ed25519 verify (canonical_json, sig_bytes, pubkey_bytes)
    │
    │  6. Return verified=True/False with the record
```

---

## 6. Federation Protocol

Nodes propagate records to each other via the **sync** endpoint. This is
useful when:
- A downstream node wants to pre-cache frequently-accessed records
- A distributor wants to mirror a supplier's product catalog
- A retailer wants push notifications on record changes

### Sync Push Flow

```
Authority Node A                    Peer Node B
       │                                │
       │  POST /v1/federation/sync      │
       │  Body: signed AssetRecord      │
       │───────────────────────────────>│
       │                                │  1. Parse authority from record
       │                                │  2. Fetch well-known from authority
       │                                │  3. Verify signature
       │                                │  4. Store as cached record
       │<────── 202 Accepted ───────────│
```

### Verification Before Caching

A peer node **never** stores a record without verifying its signature. This
prevents a compromised or malicious peer from injecting false records into the
network.

### No Global Gossip

Unlike some distributed systems, DAID does not use a gossip protocol to
propagate all records everywhere. Propagation is **explicit and selective**:
a node operator decides which records to mirror. This keeps the network lean
and avoids data you don't want.

---

## 7. Asset Data Model

```json
{
  "id":        "daid:authority:uuid4",
  "authority": "authority-domain",
  "metadata": {
    "name":           "string (required)",
    "description":    "string | null",
    "category":       "string | null",
    "manufacturer":   "string | null",
    "model":          "string | null",
    "sku":            "string | null",
    "gtin":           "string | null  (EAN-13 / UPC-A / GTIN-14)",
    "attributes":     { "key": "value" },
    "tags":           ["string"],
    "origin_country": "ISO 3166-1 alpha-2 | null"
  },
  "created_at": "ISO 8601 UTC datetime",
  "updated_at": "ISO 8601 UTC datetime",
  "version":    "integer (monotonic, increments on each update)",
  "signature":  "base64-encoded Ed25519 signature"
}
```

### Version History

Every update to an asset's metadata increments `version` and saves the
previous version to the `asset_history` table. This gives a full audit trail:

```
GET /v1/assets/{authority}/{uuid}/history
→ [v1 record, v2 record, v3 record, ...]
```

---

## 8. Security Model

### Threat Model

| Threat | Mitigation |
|---|---|
| Fake records injected by a malicious node | Signature verification against authority's public key |
| MITM between client and authority | TLS required for all production traffic |
| Stale/outdated cached records | `version` field; clients can re-verify from authority |
| Private key compromise | Key rotation procedure (announce new key via well-known; re-sign all records) |
| DNS hijacking of authority domain | DNSSEC; HTTPS certificate pinning in high-security deployments |
| Unauthorized record creation | API key authentication on write endpoints (upgrade to mTLS/JWT for production) |
| Replay attacks | Timestamp in signed payload; verifiers can reject too-old signatures |

### Production Hardening Checklist

- [ ] Enable HTTPS with a valid certificate (Let's Encrypt / commercial CA)
- [ ] Enable DNSSEC on your authority domain
- [ ] Replace static API key with short-lived JWT tokens (or mTLS)
- [ ] Store the node private key in a hardware security module (HSM) or vault (HashiCorp Vault / AWS KMS)
- [ ] Rate-limit the `/v1/resolve` endpoint to prevent node enumeration
- [ ] Implement key rotation: sign new records with new key, provide transition window
- [ ] Add audit logging for all record mutations
- [ ] Set up health monitoring and alerting on the authority node

---

## 9. Comparison with Related Systems

### vs. Matrix Protocol
Matrix is federated chat; DAID is federated asset data. Both use the same
discovery pattern (`.well-known`), both have authority-based identity, and
both use cryptographic signing. DAID borrows heavily from Matrix's server
discovery model.

### vs. ActivityPub / Mastodon
ActivityPub federates social activity streams. DAID could be implemented as
an ActivityPub extension but would carry unnecessary overhead. The core
routing pattern is similar.

### vs. IPFS / Content-Addressed Storage
IPFS addresses content by hash (immutable). DAID addresses assets by identity
(mutable). When an asset's metadata changes, the DAID URI stays the same, only
`version` increments — this is a fundamental difference from content-addressing.

### vs. GS1 / EAN / Barcode Systems
GS1 is centralized and requires registration fees. DAID is permissionless and
self-hosted. A DAID can embed a GTIN in its `metadata.gtin` field for
interoperability with existing barcode systems.

### vs. W3C DIDs (Decentralized Identifiers)
DAID is structurally very similar to a DID method. A future version could
register `did:daid` as an official DID method, making DAID identifiers fully
compatible with the W3C Verifiable Credentials ecosystem.

---

## 10. Scalability Considerations

For small-to-medium deployments, a single SQLite-backed node is sufficient.
For larger deployments:

| Scale | Recommendation |
|---|---|
| < 100k assets | SQLite + single node |
| 100k – 10M assets | PostgreSQL + async SQLAlchemy |
| > 10M assets | PostgreSQL + read replicas + Redis cache layer |
| Global CDN-scale | Asset records are immutable-per-version; cache at CDN edge after verification |

The signature-per-record model means records can be safely cached at any level
(CDN, Redis, peer node) without needing to trust the cache.
