import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from src.core.engines.douyin.channel_crawler import DouyinChannelCrawler
from src.core.engines.douyin.url_resolver import DouyinUrlResolver


class TestDouyinChannelCrawler(unittest.TestCase):
    """Kiểm thử engine trích xuất danh sách video và phân giải URL kênh Douyin."""

    def test_extract_url_from_text(self):
        raw = "Kênh hay nè https://www.douyin.com/user/MS4wLjABAAAA_test12345678901234567890123456789012345 xem đi"
        url = DouyinUrlResolver.extract_url(raw)
        self.assertIn("douyin.com/user/MS4wLjABAAAA", url)

    def test_parse_user_sec_uid(self):
        valid_url = "https://www.douyin.com/user/MS4wLjABAAAAabcdefghijklmnopqrstuvwxyz1234567890_ABC"
        sec_uid = DouyinUrlResolver.parse_user_sec_uid(valid_url)
        self.assertEqual(sec_uid, "MS4wLjABAAAAabcdefghijklmnopqrstuvwxyz1234567890_ABC")

    def test_parse_short_sec_uid_warning(self):
        short_url = "https://www.douyin.com/user/12345"
        with self.assertRaises(ValueError):
            DouyinUrlResolver.parse_user_sec_uid(short_url)

    def test_format_aweme_list(self):
        now_vn = datetime.now(timezone(timedelta(hours=7)))
        sample_aweme = [
            {
                "aweme_id": "7421839218391283",
                "desc": "Tập 1: Đại náo thiên cung",
                "create_time": int(now_vn.timestamp()),
                "video": {
                    "cover": {"url_list": ["https://p3.douyinpic.com/cover1.jpg"]}
                },
                "statistics": {"digg_count": 12500},
            }
        ]
        items = DouyinChannelCrawler._format_aweme_list(sample_aweme, limit=10, now_vn=now_vn)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["item_id"], "7421839218391283")
        self.assertEqual(items[0]["title"], "Tập 1: Đại náo thiên cung")
        self.assertEqual(items[0]["cover_url"], "https://p3.douyinpic.com/cover1.jpg")
        self.assertEqual(items[0]["likes_count"], 12500)
        self.assertTrue(items[0]["is_today"])

    def test_dom_cards_note_and_modal_id_normalization(self):
        """Kiểm thử chuẩn hóa link từ note và modal_id thành link video chuẩn."""
        import re
        sample_links = [
            ("https://www.douyin.com/note/7462819203911234567", "7462819203911234567"),
            ("https://www.douyin.com/user/MS4wLjAB...?modal_id=7462819203911234568", "7462819203911234568"),
            ("https://www.douyin.com/video/7462819203911234569", "7462819203911234569"),
        ]
        for link, expected_id in sample_links:
            id_match = re.search(r"/(?:video|note)/(\d+)", link) or re.search(r"modal_id=(\d+)", link)
            self.assertIsNotNone(id_match)
            self.assertEqual(id_match.group(1), expected_id)


if __name__ == "__main__":
    unittest.main()

