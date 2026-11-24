import unittest
from unittest.mock import MagicMock

from src.core.engines.youtube.youtube_publisher import YouTubePublisher
from src.modules.creator.youtube.schemas import (
    YouTubeChannelResponse,
    PublishShortsRequest,
    PublishShortsResponse,
)
from src.modules.creator.youtube.service import YouTubeService


def sync_run(coro):
    """Chạy coroutine đơn giản mà không cần khởi tạo socket IOCP trong Windows sandbox."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value


class TestYouTubeUnit(unittest.TestCase):
    def test_get_auth_url(self):
        url = YouTubePublisher.get_auth_url(state="user_123")
        self.assertIn("accounts.google.com", url)
        self.assertIn("client_id=", url)
        self.assertIn("state=user_123", url)
        self.assertIn("youtube.upload", url)

    def test_channel_status_not_connected(self):
        mock_repo = MagicMock()
        async def fake_get_channel(uid):
            return None
        mock_repo.get_channel = fake_get_channel
        service = YouTubeService(repo=mock_repo)

        status = sync_run(service.get_channel_status("user_test"))
        self.assertFalse(status.is_connected)
        self.assertIsNone(status.channel_id)

    def test_channel_status_connected(self):
        mock_repo = MagicMock()
        async def fake_get_channel(uid):
            return {
                "channel_id": "UC_TEST_123",
                "channel_title": "Kênh Phim Hay",
                "avatar_url": "https://example.com/avatar.jpg",
                "subscriber_count": 15000,
                "video_count": 42,
                "access_token": "valid_token",
                "refresh_token": "refresh_123",
            }
        mock_repo.get_channel = fake_get_channel
        service = YouTubeService(repo=mock_repo)

        status = sync_run(service.get_channel_status("user_test"))
        self.assertTrue(status.is_connected)
        self.assertEqual(status.channel_id, "UC_TEST_123")
        self.assertEqual(status.channel_title, "Kênh Phim Hay")
        self.assertTrue(status.has_refresh_token)
        self.assertEqual(status.subscriber_count, 15000)

    def test_aspect_converter_skip_when_already_9_16(self):
        from src.core.engines.youtube.video_aspect_converter import VideoAspectConverter
        from unittest.mock import patch

        with patch.object(VideoAspectConverter, "get_video_dimensions", return_value={"width": 1080, "height": 1920, "duration": 15.0, "is_vertical": True}):
            with patch("pathlib.Path.exists", return_value=True):
                res = VideoAspectConverter.ensure_vertical_9_16("sample_vertical.mp4")
                self.assertEqual(res, "sample_vertical.mp4")

    def test_aspect_converter_skip_when_already_16_9(self):
        from src.core.engines.youtube.video_aspect_converter import VideoAspectConverter
        from unittest.mock import patch

        with patch.object(VideoAspectConverter, "get_video_dimensions", return_value={"width": 1920, "height": 1080, "duration": 45.0, "is_vertical": False}):
            with patch("pathlib.Path.exists", return_value=True):
                res = VideoAspectConverter.ensure_horizontal_16_9("sample_horizontal.mp4")
                self.assertEqual(res, "sample_horizontal.mp4")


if __name__ == "__main__":
    unittest.main()
