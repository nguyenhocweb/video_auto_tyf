import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from src.core.engines.facebook.facebook_reels_publisher import FacebookReelsPublisher
from src.core.config import settings


def sync_run(coro):
    return asyncio.run(coro)


class TestFacebookReelsPublisher(unittest.IsolatedAsyncioTestCase):
    """Kiểm thử Engine xuất bản video Facebook Reels."""

    @patch.object(settings, "FB_PAGE_ID", "")
    @patch.object(settings, "FB_PAGE_ACCESS_TOKEN", "")
    def test_missing_credentials(self):
        """Kiểm tra báo lỗi khi thiếu Page ID hoặc Token."""
        with self.assertRaises(ValueError):
            FacebookReelsPublisher._get_page_credentials(page_id="", access_token="")

    @patch("httpx.AsyncClient")
    async def test_publish_reel_from_file_mock(self, mock_client_cls):
        """Kiểm tra luồng 3 bước xuất bản Reel."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_cls.return_value = mock_client

        # Giả lập response cho 3 bước: start, upload, finish
        res_start = MagicMock(status_code=200)
        res_start.json.return_value = {"video_id": "test_video_123", "upload_url": "https://rupload.facebook.com/test"}

        res_upload = MagicMock(status_code=200)
        res_upload.text = "OK"

        res_finish = MagicMock(status_code=200)
        res_finish.json.return_value = {"success": True}

        mock_client.post.side_effect = [res_start, res_upload, res_finish]

        res_chk = MagicMock(status_code=200)
        res_chk.json.return_value = {"status": {"video_status": "ready"}}
        mock_client.get = AsyncMock(return_value=res_chk)

        temp_video = Path("be/storage/temp/test_fake_video.mp4")
        temp_video.parent.mkdir(parents=True, exist_ok=True)
        temp_video.write_bytes(b"fake_mp4_bytes")

        try:
            res = await FacebookReelsPublisher.publish_reel_from_file(
                video_path=str(temp_video),
                caption="Test Reel #shorts",
                page_id="12345",
                access_token="fake_token",
            )
            self.assertTrue(res["success"])
            self.assertEqual(res["video_id"], "test_video_123")
            self.assertEqual(res["meta_status"], "ready")
            self.assertIn("facebook.com/reel/test_video_123", res["reel_url"])
            self.assertEqual(mock_client.post.call_count, 3)
        finally:
            if temp_video.exists():
                temp_video.unlink()


if __name__ == "__main__":
    unittest.main()
