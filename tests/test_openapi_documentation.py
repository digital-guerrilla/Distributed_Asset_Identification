import unittest

from node.app.main import app


class OpenApiDocumentationTests(unittest.TestCase):
    def test_openapi_spec_includes_api_key_security_and_tags(self):
        schema = app.openapi()

        self.assertIn("components", schema)
        self.assertIn("securitySchemes", schema["components"])
        self.assertIn("x_api_key", schema["components"]["securitySchemes"])

        self.assertIn("tags", schema)
        self.assertTrue(any(tag.get("name") == "records" for tag in schema["tags"]))
        self.assertTrue(any(tag.get("name") == "node" for tag in schema["tags"]))


if __name__ == "__main__":
    unittest.main()
