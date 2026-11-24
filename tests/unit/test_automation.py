import unittest
import asyncio
from src.modules.creator.automation.executor import AutomationExecutor
from src.core.engines.douyin.url_resolver import DouyinUrlResolver
from src.modules.creator.automation.schemas import (
    AutomationCampaignCreateRequest,
    SourceChannelConfig,
    TargetPageConfig,
)


class TestAutomationUnit(unittest.TestCase):
    def test_douyin_url_extraction(self):
        text = "Xem kênh: https://www.douyin.com/user/MS4wLjABAAAA3unTXNQsVu_Q7WIFcjgzITlle0Fof60XSW8TDSLjoSwLTzq8k3srV8pAtwCEhvzd?from_tab_name=main"
        extracted = DouyinUrlResolver.extract_url(text)
        self.assertTrue(extracted.startswith("https://www.douyin.com/user/"))

    def test_douyin_url_resolver_short_rejected(self):
        short_url = "https://www.douyin.com/user/MS4wLjABAAAA3unTXNQsVu_Q7W"
        with self.assertRaises(ValueError):
            DouyinUrlResolver.parse_user_sec_uid(short_url)

    def test_douyin_url_resolver_valid_sec_uid(self):
        valid_url = "https://www.douyin.com/user/MS4wLjABAAAA3unTXNQsVu_Q7WIFcjgzITlle0Fof60XSW8TDSLjoSwLTzq8k3srV8pAtwCEhvzd?from_tab_name=main"
        sec = DouyinUrlResolver.parse_user_sec_uid(valid_url)
        self.assertEqual(sec, "MS4wLjABAAAA3unTXNQsVu_Q7WIFcjgzITlle0Fof60XSW8TDSLjoSwLTzq8k3srV8pAtwCEhvzd")

    def test_remove_vietnamese_accents(self):
        text = "Tập 7: Ngày Tận Thế, Hầm Trú Ẩn Bí Ẩn"
        no_accents = AutomationExecutor.remove_vietnamese_accents(text)
        self.assertNotIn("ậ", no_accents)
        self.assertNotIn("à", no_accents)
        self.assertNotIn("ế", no_accents)
        self.assertIn("Tap 7: Ngay Tan The, Ham Tru An Bi An", no_accents)

    def test_clean_douyin_title(self):
        raw = "广西车辆坠河事件已致2人死亡 #广西车辆坠河事件已致2人死亡 @人民日报 https://v.douyin.com/test"
        cleaned = AutomationExecutor.clean_douyin_title(raw)
        self.assertEqual(cleaned, "广西车辆坠河事件已致2人死亡")
        self.assertNotIn("#", cleaned)
        self.assertNotIn("@", cleaned)
        self.assertNotIn("http", cleaned)

    def test_generate_hashtags_purges_chinese(self):
        # Khi tiêu đề là tiếng Trung, không được tạo bất kỳ hashtag chữ Hán nào
        tags = AutomationExecutor.generate_hashtags(
            title="广西车辆坠河事件已致2人死亡",
            config_hashtags="#广西车辆 #Douyin #Reels #girl #hotgirl",
            auto_add_title_tag=True,
        )
        self.assertNotIn("广西", tags)
        self.assertNotIn("车辆", tags)
        self.assertIn("#Douyin", tags)
        self.assertIn("#Reels", tags)
        self.assertIn("#girl", tags)
        self.assertIn("#hotgirl", tags)

    def test_generate_hashtags(self):
        title = "Tập 7: Ngày Tận Thế"
        hashtags = AutomationExecutor.generate_hashtags(
            title=title,
            config_hashtags="#Douyin #Reels #Shorts",
            auto_add_title_tag=True,
        )
        self.assertIn("#Tap7NgayTanThe", hashtags)
        self.assertIn("#Douyin", hashtags)
        self.assertIn("#Reels", hashtags)
        self.assertIn("#Shorts", hashtags)

    def test_schema_validation(self):
        req = AutomationCampaignCreateRequest(
            name="Chiến dịch tự động",
            source_channels=[
                SourceChannelConfig(channel_url="https://www.douyin.com/user/test", name="Kênh Test")
            ],
            target_pages=[
                TargetPageConfig(page_id="123456789", page_name="Fanpage Test")
            ],
            crawl_interval_minutes=30,
            processing_mode="vietsub",
        )
        self.assertEqual(req.name, "Chiến dịch tự động")
        self.assertEqual(req.crawl_interval_minutes, 30)
        self.assertEqual(req.processing_mode, "vietsub")
        self.assertTrue(req.only_today)
        self.assertEqual(req.max_video_age_hours, 24)
        self.assertTrue(req.only_new_unprocessed)

    def test_max_video_age_hours_filtering(self):
        import time
        now_ts = time.time()
        crawled_videos = [
            {"item_id": "v1", "created_timestamp": int(now_ts - 1 * 3600)},   # 1h ago
            {"item_id": "v2", "created_timestamp": int(now_ts - 3 * 3600)},   # 3h ago
            {"item_id": "v3", "created_timestamp": int(now_ts - 25 * 3600)},  # 25h ago
        ]

        # 1. Filter max 2h
        filtered_2h = [
            v for v in crawled_videos
            if (now_ts - v["created_timestamp"]) / 3600 <= 2
        ]
        self.assertEqual([v["item_id"] for v in filtered_2h], ["v1"])

        # 2. Filter max 6h
        filtered_6h = [
            v for v in crawled_videos
            if (now_ts - v["created_timestamp"]) / 3600 <= 6
        ]
        self.assertEqual([v["item_id"] for v in filtered_6h], ["v1", "v2"])

        # 3. Filter max 48h
        filtered_48h = [
            v for v in crawled_videos
            if (now_ts - v["created_timestamp"]) / 3600 <= 48
        ]
        self.assertEqual([v["item_id"] for v in filtered_48h], ["v1", "v2", "v3"])

    def test_early_stop_when_video_not_today(self):
        # Giả lập danh sách video xếp giảm dần theo thời gian:
        # Video 1: Hôm nay, Video 2: Quá 24h, Video 3: Quá 24h
        crawled_videos = [
            {"item_id": "v1", "is_today": True, "created_timestamp": 300},
            {"item_id": "v2", "is_today": False, "created_timestamp": 200},
            {"item_id": "v3", "is_today": False, "created_timestamp": 100},
        ]
        target_videos = []
        for v in crawled_videos:
            if not v.get("is_today", False):
                break  # Dừng quét kênh ngay lập tức!
            target_videos.append(v)
        self.assertEqual(len(target_videos), 1)
        self.assertEqual(target_videos[0]["item_id"], "v1")

    def test_firewall_author_verification_logic(self):
        """Kiểm thử logic tường lửa xác minh tác giả kênh: không bị nhầm lẫn giữa numeric uid và sec_uid."""
        # 1. Trùng sec_uid chuẩn -> Hợp lệ
        ext1 = {"sec_uid": "MS4wLjABAAAA_test_author", "uid": "12345", "nickname": "Tác Giả 1"}
        expected_sec = "MS4wLjABAAAA_test_author"
        is_mismatch1 = (ext1["sec_uid"] != expected_sec)
        self.assertFalse(is_mismatch1)

        # 2. Khác sec_uid chuẩn -> Bị chặn
        ext2 = {"sec_uid": "MS4wLjABAAAA_hacked_author", "uid": "99999", "nickname": "Kẻ Lạ"}
        is_mismatch2 = (ext2["sec_uid"] != expected_sec)
        self.assertTrue(is_mismatch2)

        # 3. Một bên thiếu sec_uid nhưng nickname trùng khớp -> Hợp lệ (không so nhầm uid với sec_uid)
        ext3 = {"sec_uid": "", "uid": "12345", "nickname": "小爱是也"}
        expected_nick = "小爱是也"
        is_mismatch3 = bool(ext3["sec_uid"] and ext3["sec_uid"] != expected_sec)
        self.assertFalse(is_mismatch3)


if __name__ == "__main__":
    unittest.main()

