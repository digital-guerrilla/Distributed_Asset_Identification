import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from node.app import dependencies
from node.app.api.assets import replication_endpoints
from node.app.config import settings
from node.app.core.crypto import NodeKeyManager
from node.app.core.guid import parse_daid
from node.app.federation.resolver import _discovery_scheme
from node.app.main import app


class V3ApiTest(unittest.TestCase):
    def test_restricted_replication_uses_explicit_routing_hosts(self) -> None:
        from node.app.core.models import AvailabilityPolicy, GossipPeerState

        settings.NODE_DOMAIN = "127.0.0.1:8999"
        policy = AvailabilityPolicy(
            visibility="restricted",
            allowed_nodes=["127.0.0.1:8998"],
        )
        fingerprint_peer = GossipPeerState(
            node_id="z6MkFingerprint",
            endpoint="http://127.0.0.1:8998",
        )
        self.assertEqual(
            replication_endpoints(policy, [fingerprint_peer]),
            ["http://127.0.0.1:8998"],
        )

    def test_discovery_scheme_requires_explicit_http_opt_in(self) -> None:
        original = settings.ALLOW_INSECURE_HTTP_DISCOVERY
        try:
            settings.ALLOW_INSECURE_HTTP_DISCOVERY = False
            self.assertEqual(_discovery_scheme("authority.example"), "https")
            self.assertEqual(_discovery_scheme("127.0.0.1:8000"), "http")

            settings.ALLOW_INSECURE_HTTP_DISCOVERY = True
            self.assertEqual(_discovery_scheme("node-manufacturer:8000"), "http")
        finally:
            settings.ALLOW_INSECURE_HTTP_DISCOVERY = original

    def test_publish_verify_and_resolve_graph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings.DATABASE_URL = f"sqlite+aiosqlite:///{root / 'node.db'}"
            settings.PRIVATE_KEY_FILE = str(root / "node.key")
            settings.GOSSIP_SEEDS = ""
            settings.NODE_DOMAIN = "localhost:8999"
            settings.NODE_API_BASE = "http://localhost:8999"
            settings.API_KEY = "test-key"
            dependencies._key_manager = None

            with TestClient(app) as client:
                descriptor_response = client.get("/.well-known/daid/server")
                self.assertEqual(descriptor_response.status_code, 200)
                descriptor = descriptor_response.json()

                create_response = client.post(
                    "/v3/records",
                    headers={"x-api-key": "test-key"},
                    json={
                        "record_kind": "type",
                        "subject": {
                            "name": "Fire Door FD60",
                            "manufacturer": "Example Manufacturing",
                            "model_number": "FD60-01",
                        },
                    },
                )
                self.assertEqual(create_response.status_code, 201, create_response.text)
                record = create_response.json()
                parsed = parse_daid(record["id"])

                fetch_response = client.get(
                    f"/v3/records/{parsed.authority_key_fingerprint}/{parsed.record_uuid}"
                )
                self.assertEqual(fetch_response.status_code, 200, fetch_response.text)
                method = descriptor["verification_methods"][0]
                self.assertTrue(NodeKeyManager.verify(
                    fetch_response.json(),
                    record["proof"]["proof_value"],
                    method["public_key_base64"],
                ))

                graph_response = client.post(
                    "/v3/resolve-graph",
                    json={"root": record["id"], "depth": 0, "max_nodes": 10},
                )
                self.assertEqual(graph_response.status_code, 200, graph_response.text)
                graph = graph_response.json()
                self.assertTrue(graph["complete"])
                self.assertIn(record["id"], graph["nodes"])

    def test_upload_document_versions_record_and_serves_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings.DATABASE_URL = f"sqlite+aiosqlite:///{root / 'node.db'}"
            settings.PRIVATE_KEY_FILE = str(root / "node.key")
            settings.DOCUMENT_STORAGE_DIR = str(root / "documents")
            settings.GOSSIP_SEEDS = ""
            settings.NODE_DOMAIN = "localhost:8998"
            settings.NODE_API_BASE = "http://localhost:8998"
            settings.API_KEY = "test-key"
            dependencies._key_manager = None

            with TestClient(app) as client:
                created = client.post(
                    "/v3/records",
                    headers={"x-api-key": "test-key"},
                    json={"record_kind": "instance", "subject": {"name": "Test Pump"}},
                ).json()
                parsed = parse_daid(created["id"])
                content = b"commissioning evidence"
                upload = client.post(
                    f"/v3/documents/upload/{parsed.authority_key_fingerprint}/{parsed.record_uuid}",
                    headers={
                        "x-api-key": "test-key",
                        "x-file-name": "commissioning.txt",
                        "content-type": "text/plain",
                    },
                    content=content,
                )
                self.assertEqual(upload.status_code, 201, upload.text)
                document = upload.json()

                updated = client.get(
                    f"/v3/records/{parsed.authority_key_fingerprint}/{parsed.record_uuid}"
                ).json()
                self.assertEqual(updated["version"], 2)
                self.assertEqual(updated["subject"]["documents"][0]["sha256"], document["sha256"])
                retrieved = client.get(f"/v3/documents/{document['sha256']}")
                self.assertEqual(retrieved.status_code, 200)
                self.assertEqual(retrieved.content, content)

    def test_restricted_record_requires_local_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings.DATABASE_URL = f"sqlite+aiosqlite:///{root / 'node.db'}"
            settings.PRIVATE_KEY_FILE = str(root / "node.key")
            settings.GOSSIP_SEEDS = ""
            settings.NODE_DOMAIN = "localhost:8997"
            settings.NODE_API_BASE = "http://localhost:8997"
            settings.API_KEY = "owner-key"
            dependencies._key_manager = None

            with TestClient(app) as client:
                created = client.post(
                    "/v3/records",
                    headers={"x-api-key": "owner-key"},
                    json={
                        "record_kind": "instance",
                        "subject": {"name": "Private Installed Asset"},
                        "availability": {
                            "visibility": "restricted",
                            "allowed_nodes": ["localhost:8995"],
                        },
                    },
                ).json()
                parsed = parse_daid(created["id"])
                path = f"/v3/records/{parsed.authority_key_fingerprint}/{parsed.record_uuid}"

                anonymous_catalog = client.get("/v3/records").json()
                self.assertEqual(anonymous_catalog["total"], 0)
                self.assertEqual(client.get(path).status_code, 403)

                authorized_catalog = client.get(
                    "/v3/records", headers={"x-api-key": "owner-key"}
                ).json()
                self.assertEqual(authorized_catalog["total"], 1)
                self.assertEqual(
                    client.get(path, headers={"x-api-key": "owner-key"}).status_code,
                    200,
                )
                public_graph = client.post(
                    "/v3/resolve-graph",
                    json={"root": created["id"], "depth": 0, "view": "public"},
                )
                self.assertEqual(public_graph.status_code, 403)
                confidential_graph = client.post(
                    "/v3/resolve-graph",
                    headers={"x-api-key": "owner-key"},
                    json={"root": created["id"], "depth": 0, "view": "confidential"},
                )
                self.assertEqual(confidential_graph.status_code, 200, confidential_graph.text)

                document = client.post(
                    f"/v3/documents/upload/{parsed.authority_key_fingerprint}/{parsed.record_uuid}",
                    headers={
                        "x-api-key": "owner-key",
                        "x-file-name": "private.txt",
                        "content-type": "text/plain",
                    },
                    content=b"private inspection evidence",
                ).json()
                document_path = f"/v3/documents/{document['sha256']}"
                self.assertEqual(client.get(document_path).status_code, 403)
                self.assertEqual(
                    client.get(document_path, headers={"x-api-key": "owner-key"}).status_code,
                    200,
                )

                updated = client.put(
                    path,
                    headers={"x-api-key": "owner-key"},
                    json={
                        "subject": created["subject"],
                        "relationships": created["relationships"],
                        "availability": {
                            **created["availability"],
                            "visibility": "public",
                            "allowed_nodes": [],
                        },
                    },
                )
                self.assertEqual(updated.status_code, 200, updated.text)
                self.assertEqual(updated.json()["availability"]["visibility"], "public")
                self.assertEqual(client.get(path).status_code, 200)


if __name__ == "__main__":
    unittest.main()