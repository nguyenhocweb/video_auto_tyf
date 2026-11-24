import unittest
from src.modules.creator.dubbing.groq_keys_repository import GroqKeysMongoRepository
from src.modules.creator.dubbing.groq_keys_schemas import GroqKeyCreateRequest
from src.core.engines.dubbing.groq_translator import GroqTranslator


class TestGroqKeys(unittest.TestCase):
    def test_mask_groq_key(self):
        short_key = "gsk_12345"
        self.assertIn("...", GroqKeysMongoRepository.mask_key(short_key))

        full_key = "gsk_abc1234567890xyz"
        masked = GroqKeysMongoRepository.mask_key(full_key)
        self.assertTrue(masked.startswith("gsk_abc"))
        self.assertTrue(masked.endswith("xyz"))

    def test_groq_key_create_schema(self):
        req = GroqKeyCreateRequest(
            key="gsk_123456789012345",
            note="Test Key",
            model="qwen/qwen3.8-27b",
        )
        self.assertEqual(req.key, "gsk_123456789012345")
        self.assertEqual(req.model, "qwen/qwen3.8-27b")

    def test_groq_parse_indexed_translation(self):
        raw_output = "LINE_0: Xin chào thế giới\nLINE_1: Chúc một ngày tốt lành"
        parsed = GroqTranslator._parse_indexed_translation(raw_output, expected_count=2, texts=["Hello", "Have a nice day"])
        self.assertEqual(parsed[0], "Xin chào thế giới")
        self.assertEqual(parsed[1], "Chúc một ngày tốt lành")


if __name__ == "__main__":
    unittest.main()
