import unittest
from datetime import datetime, timezone, timedelta
from src.modules.creator.facebook.schemas import TokenStatusResponse


class TestFacebookTokenUnit(unittest.TestCase):
    def test_token_status_never_expires(self):
        resp = TokenStatusResponse(
            is_valid=True,
            has_token=True,
            expires_at=0,
            expires_in_days=9999.0,
            expires_at_formatted="Vĩnh viễn (Không bao giờ hết hạn)",
            token_type_label="Token Vĩnh Viễn",
        )
        self.assertTrue(resp.is_valid)
        self.assertEqual(resp.expires_at, 0)
        self.assertIn("Vĩnh viễn", resp.expires_at_formatted)

    def test_token_status_expired(self):
        resp = TokenStatusResponse(
            is_valid=False,
            has_token=True,
            expires_at=None,
            expires_in_days=None,
            expires_at_formatted="Đã hết hạn",
            token_type_label="Đã hết hạn",
        )
        self.assertFalse(resp.is_valid)
        self.assertEqual(resp.expires_at_formatted, "Đã hết hạn")


if __name__ == "__main__":
    unittest.main()

