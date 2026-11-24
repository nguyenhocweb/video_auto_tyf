import unittest
from unittest.mock import patch, MagicMock
from src.modules.creator.facebook.facebook_cache import FacebookCache
from src.modules.creator.facebook.schemas import (
    FacebookPageItem,
    FacebookVideoItem,
)
from src.modules.creator.facebook.service import FacebookService


def sync_run(coro):
    """Chạy coroutine đơn giản mà không cần khởi tạo socket IOCP trong Windows sandbox."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value


class TestFacebookCache(unittest.TestCase):
    @patch("src.modules.creator.facebook.facebook_cache.get_mongo_db")
    def test_get_cached_pages(self, mock_get_db):
        mock_db = MagicMock()
        mock_cursor = MagicMock()

        async def async_generator():
            yield {
                "id": "page_123",
                "name": "Test Page",
                "category": "Entertainment",
                "picture_url": "https://example.com/pic.jpg",
                "fan_count": 5000,
                "followers_count": 6000,
                "access_token": "token_abc",
            }

        mock_cursor.__aiter__ = lambda self: async_generator()
        mock_db.facebook_pages.find.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        pages = sync_run(FacebookCache.get_cached_pages())
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].id, "page_123")
        self.assertEqual(pages[0].name, "Test Page")
        self.assertEqual(pages[0].fan_count, 5000)

    @patch("src.modules.creator.facebook.facebook_cache.get_mongo_db")
    def test_save_cached_pages(self, mock_get_db):
        mock_db = MagicMock()
        called = False

        async def fake_update_one(*args, **kwargs):
            nonlocal called
            called = True
            return MagicMock()

        mock_db.facebook_pages.update_one = fake_update_one
        mock_get_db.return_value = mock_db

        test_pages = [
            FacebookPageItem(
                id="page_1",
                name="Page One",
                fan_count=100,
                followers_count=120,
            )
        ]
        sync_run(FacebookCache.save_cached_pages(test_pages))
        self.assertTrue(called)

    @patch("src.modules.creator.facebook.facebook_cache.get_mongo_db")
    def test_get_and_save_cached_videos(self, mock_get_db):
        mock_db = MagicMock()

        async def fake_find_one(*args, **kwargs):
            return {
                "page_id": "page_123",
                "videos": [
                    {
                        "id": "vid_01",
                        "title": "Video 1",
                        "views": 1000,
                        "reactions_count": 50,
                    }
                ],
            }

        mock_db.facebook_cached_videos.find_one = fake_find_one

        saved = False
        async def fake_update_one(*args, **kwargs):
            nonlocal saved
            saved = True
            return MagicMock()

        mock_db.facebook_cached_videos.update_one = fake_update_one
        mock_get_db.return_value = mock_db

        videos = sync_run(FacebookCache.get_cached_videos("page_123"))
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0].id, "vid_01")
        self.assertEqual(videos[0].views, 1000)

        test_vids = [FacebookVideoItem(id="vid_02", title="Video 2")]
        sync_run(FacebookCache.save_cached_videos("page_123", test_vids))
        self.assertTrue(saved)

    @patch("src.modules.creator.facebook.service.FacebookCache.get_cached_pages")
    @patch("src.core.engines.facebook.facebook_reels_publisher.FacebookReelsPublisher.get_managed_pages")
    def test_service_get_pages_cache_first(self, mock_get_managed, mock_get_cached):
        # Khi force_refresh=False và cache có dữ liệu: KHÔNG gọi get_managed_pages (Meta)
        async def fake_cached():
            return [FacebookPageItem(id="p1", name="Cached Page")]

        mock_get_cached.side_effect = fake_cached
        mock_get_managed.return_value = []

        pages = sync_run(FacebookService.get_pages(force_refresh=False))
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].name, "Cached Page")
        mock_get_managed.assert_not_called()

        # Khi force_refresh=True: BẮT BUỘC gọi Meta
        async def fake_managed():
            return [
                {
                    "id": "p2",
                    "name": "Live Page",
                    "category": "News",
                    "picture_url": "",
                    "fan_count": 10,
                    "followers_count": 20,
                }
            ]

        mock_get_managed.side_effect = fake_managed
        with patch("src.modules.creator.facebook.service.FacebookCache.save_cached_pages") as mock_save:
            async def fake_save(*args, **kwargs):
                return None
            mock_save.side_effect = fake_save

            pages_refreshed = sync_run(FacebookService.get_pages(force_refresh=True))
            self.assertEqual(len(pages_refreshed), 1)
            self.assertEqual(pages_refreshed[0].name, "Live Page")
            self.assertTrue(mock_get_managed.called)


if __name__ == "__main__":
    unittest.main()
