import unittest

from node.app.core.content_crypto import combine_key, decrypt_fragments, encrypt_fragments, split_key


class ContentCryptoTest(unittest.TestCase):
    def test_fragments_are_not_plaintext_and_round_trip(self) -> None:
        content = b"confidential inspection evidence" * 200
        key, manifest, fragments = encrypt_fragments(content, chunk_size=1024)

        self.assertGreater(manifest.fragment_count, 1)
        self.assertNotIn(content[:32], b"".join(fragment.ciphertext for fragment in fragments))
        self.assertEqual(decrypt_fragments(key, manifest, fragments), content)

    def test_tampered_fragment_is_rejected(self) -> None:
        content = b"signed evidence"
        key, manifest, fragments = encrypt_fragments(content, chunk_size=1024)
        tampered = list(fragments)
        fragment = tampered[0]
        tampered[0] = type(fragment)(fragment.index, fragment.nonce, fragment.ciphertext + b"x", fragment.sha256)

        with self.assertRaises(ValueError):
            decrypt_fragments(key, manifest, tampered)

    def test_key_requires_threshold_of_shares(self) -> None:
        key, _, _ = encrypt_fragments(b"threshold protected")
        shares = split_key(key, share_count=5, threshold=3)
        self.assertEqual(combine_key(shares[:3], threshold=3), key)
        with self.assertRaises(ValueError):
            combine_key(shares[:2], threshold=3)