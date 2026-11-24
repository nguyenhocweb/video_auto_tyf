import unittest
from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository
from src.modules.creator.dubbing.gemini_keys_schemas import (
    GeminiKeyCreateRequest,
    GeminiKeyResponse,
    GeminiKeyListResponse,
)


class TestGeminiKeysRepositoryUnit(unittest.TestCase):
    def test_mask_key_long(self):
        """Kiểm tra che giấu key dài hơn 10 ký tự."""
        raw_key = "AIzaSyDu83bKj982348_zlkjA1992zZ"
        masked = GeminiKeysMongoRepository.mask_key(raw_key)
        self.assertTrue(masked.startswith("AIzaSyD"))
        self.assertTrue(masked.endswith("92zZ"))
        self.assertIn("...", masked)
        self.assertNotIn("83bKj982348", masked)

    def test_mask_key_short(self):
        """Kiểm tra che giấu key ngắn (<= 10 ký tự)."""
        raw_key = "12345678"
        masked = GeminiKeysMongoRepository.mask_key(raw_key)
        self.assertEqual(masked, "123...678")

    def test_schema_validation(self):
        """Kiểm tra validate dữ liệu đầu vào theo Pydantic v2."""
        # Key hợp lệ
        valid_req = GeminiKeyCreateRequest(key="AIzaSy1234567890abcdef", note="Key chính")
        self.assertEqual(valid_req.note, "Key chính")

        # Response schema
        resp = GeminiKeyResponse(
            id="gkey_test_123",
            key_masked="AIzaSy1...cdef",
            note="Key test",
            is_active=True,
            usage_count=10,
            error_count=1,
            last_used_at="2026-11-07T18:00:00+07:00",
            created_at="2026-11-07T12:00:00+07:00",
        )
        self.assertEqual(resp.id, "gkey_test_123")
        self.assertTrue(resp.is_active)

        # List Response schema
        list_resp = GeminiKeyListResponse(total=1, items=[resp])
        self.assertEqual(list_resp.total, 1)
        self.assertEqual(len(list_resp.items), 1)


if __name__ == "__main__":
    unittest.main()

