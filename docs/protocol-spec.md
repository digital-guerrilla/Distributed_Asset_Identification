# DAID Protocol Specification v1.0

## 1. Terminology

- **DAID** (Distributed Asset Identification) — the protocol and URI scheme
- **Authority Node** — a server that issues and owns records under its domain
- **Peer Node** — a server that caches/mirrors records from other nodes
- **Asset Record** — a signed, versioned data document describing an asset
- **DAID URI** — a globally unique identifier in the form `daid:{authority}:{uuid4}`
- **Resolver** — any client or node that converts a DAID URI into an Asset Record
- **Canonical JSON** — deterministic JSON serialization used as the signing payload

---

## 2. DAID URI Syntax

```
DAID-URI    = "daid" ":" authority ":" uuid4
authority   = hostname / hostname ":" port
hostname    = 1*( ALPHA / DIGIT / "-" / "." )
port        = 1*DIGIT
uuid4       = 8HEXDIG "-" 4HEXDIG "-" "4" 3HEXDIG "-" VARIANT 3HEXDIG "-" 12HEXDIG
VARIANT     = "8" / "9" / "a" / "b"
```

Examples:
```
daid:acme.com:550e8400-e29b-41d4-a716-446655440000
daid:node1.distributor.io:8443:6ba7b810-9dad-11d1-80b4-00c04fd430c8
daid:localhost:8001:a8098c1a-f86e-11da-bd1a-00112444be1e
```

---

## 3. Discovery Document

**Endpoint**: `GET https://{authority}/.well-known/daid/server`
**Content-Type**: `application/json`

```json
{
  "endpoint":    "https://api.acme.com",
  "node_id":     "acme.com",
  "public_key":  "base64-encoded 32-byte Ed25519 public key",
  "api_version": "1.0"
}
```

Resolvers MUST use HTTPS when fetching the discovery document in production.
HTTP is permitted only in explicitly non-production (development) contexts.

The `public_key` field is the trust anchor. Implementations MUST NOT cache
the public key for longer than the HTTP response's `Cache-Control` duration
or 3600 seconds (1 hour), whichever is shorter.

---

## 4. Asset Record Schema

```json
{
  "id":        "daid:{authority}:{uuid4}",
  "authority": "{authority}",
  "metadata":  {AssetMetadata},
  "created_at": "{ISO 8601 UTC}",
  "updated_at": "{ISO 8601 UTC}",
  "version":   {integer >= 1},
  "signature": "{base64-encoded Ed25519 signature}"
}
```

Datetime fields MUST be in full ISO 8601 format with explicit UTC offset
(`+00:00`), e.g., `2026-03-31T12:00:00+00:00`.

### 4.1 AssetMetadata Schema

All fields are optional except `name`.

```json
{
  "name":           "string",
  "description":    "string | null",
  "category":       "string | null",
  "manufacturer":   "string | null",
  "model":          "string | null",
  "sku":            "string | null",
  "gtin":           "string | null",
  "attributes":     {"key": "value"},
  "tags":           ["string"],
  "origin_country": "string | null"
}
```

The `attributes` field is an open-ended key-value store for domain-specific
extensions. Keys SHOULD be namespaced (e.g., `"pharma:lot_number": "L20260331"`).

---

## 5. Canonical JSON Signing Payload

The payload that is signed / verified is produced by:

1. Taking the Asset Record dict
2. Removing the `"signature"` key
3. Serializing with `json.dumps(record, sort_keys=True, separators=(',', ':'))`
   — all nested dict keys are also sorted recursively

This is performed identically at signing time and verification time.

**Critical**: All datetime values MUST be serialized as strings in the form
`YYYY-MM-DDTHH:MM:SS.ffffff+00:00` (Python `datetime.isoformat()` output for
UTC-aware datetimes). Implementations in other languages MUST match this format
exactly.

---

## 6. HTTP API

Base path: the `endpoint` value from the discovery document.

### 6.1 Get Asset (local)

```
GET /v1/assets/{authority}/{uuid}
```

Returns the asset record if held by this node (authoritative or cached).
Returns `404` if not held locally.

### 6.2 List Assets (local)

```
GET /v1/assets?limit=50&offset=0
```

Returns a paginated list of assets held by this node.

### 6.3 Create Asset

```
POST /v1/assets
Authorization: x-api-key: {key}
Content-Type: application/json

{
  "metadata": {AssetMetadata}
}
```

The authority is automatically set to the node's own `NODE_DOMAIN`.
Response: created Asset Record with `201 Created`.

### 6.4 Update Asset

```
PUT /v1/assets/{authority}/{uuid}
Authorization: x-api-key: {key}
Content-Type: application/json

{
  "metadata": {AssetMetadata}
}
```

Only permitted on records where `is_authoritative = true`. Increments
`version`, saves previous version to history, re-signs.

### 6.5 Asset Version History

```
GET /v1/assets/{authority}/{uuid}/history
```

Returns an array of previous versions (not including current). Ordered by
version ascending.

### 6.6 Resolve (network-aware)

```
GET /v1/resolve/{authority}/{uuid}
```

Checks local storage first, then resolves from the authority node if needed.
Returns:
```json
{
  "asset":     {AssetRecord},
  "verified":  true,
  "source":    "local_authoritative | local_cache | remote_authoritative"
}
```

### 6.7 Node Info

```
GET /v1/node/info
```

Returns:
```json
{
  "node_id":             "authority-domain",
  "public_key":          "base64 Ed25519 pubkey",
  "api_version":         "1.0",
  "supported_features":  ["assets", "federation", "history"]
}
```

### 6.8 Federation Sync (receive)

```
POST /v1/federation/sync
Content-Type: application/json

{AssetRecord}
```

Used by authority nodes (or other peers) to push a signed record to this node.
The receiving node MUST:
1. Verify the record signature by fetching the authority's public key from
   their `.well-known` endpoint.
2. Reject with `400` if the signature is invalid.
3. Store as a cached record (non-authoritative) if valid.
4. Update if a record with higher `version` already exists.

Returns `202 Accepted` on success.

---

## 7. Error Responses

All errors return JSON:

```json
{
  "detail": "human-readable error message"
}
```

| Status | Meaning |
|---|---|
| `400` | Bad request (invalid DAID, bad signature, malformed body) |
| `401` | Missing or invalid API key |
| `403` | Operation not permitted (e.g., updating a non-authoritative record) |
| `404` | Asset not found |
| `502` | Failed to reach authority node during resolution |
| `503` | Node temporarily unavailable |

---

## 8. Versioning

The protocol version is `1.0`. Breaking changes will increment the major
version. Nodes MUST advertise their supported version in the discovery document
and in `/v1/node/info`. A node receiving a request for an unsupported version
MUST return `400`.

---

## 9. Reserved Metadata Keys

The following `attributes` key prefixes are reserved for future standard use:

| Prefix | Reserved for |
|---|---|
| `daid:` | Core protocol extensions |
| `gs1:` | GS1/EAN interoperability |
| `vc:` | W3C Verifiable Credentials linkage |
| `recall:` | Recall and revocation data |
| `lineage:` | Component/assembly lineage |
