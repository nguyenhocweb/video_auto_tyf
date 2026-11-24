import unittest
from unittest.mock import patch, AsyncMock
from src.modules.creator.facebook.schemas import (
    FacebookPageItem,
    FacebookVideoItem,
    FacebookPostItem,
    PublishReelRequest,
)
from src.modules.creator.facebook.service import FacebookService


class TestFacebookService(unittest.IsolatedAsyncioTestCase):
    @patch("src.modules.creator.facebook.service.FacebookReelsPublisher.get_managed_pages", new_callable=AsyncMock)
    async def test_get_pages(self, mock_get_pages):
        mock_get_pages.return_value = [
            {
                "id": "123456",
                "name": "Test Page",
                "category": "Entertainment",
                "picture_url": "https://example.com/pic.jpg",
                "fan_count": 500,
                "followers_count": 1200,
                "access_token": "token_123",
            }
        ]
        pages = await FacebookService.get_pages()
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].id, "123456")
        self.assertEqual(pages[0].name, "Test Page")
        self.assertEqual(pages[0].followers_count, 1200)

    @patch("src.modules.creator.facebook.service.FacebookService.get_page_token", new_callable=AsyncMock)
    @patch("src.modules.creator.facebook.service.FacebookReelsPublisher.get_page_videos", new_callable=AsyncMock)
    async def test_get_page_videos(self, mock_get_videos, mock_get_token):
        mock_get_token.return_value = "token_123"
        mock_get_videos.return_value = [
            {
                "id": "vid_01",
                "title": "Review Phim Hay",
                "description": "Mô tả phim",
                "created_time": "2026-11-06T08:00:00+0000",
                "thumbnail": "https://example.com/thumb.jpg",
                "permalink_url": "https://facebook.com/reel/vid_01",
                "length": 45.2,
                "views": 1500,
                "reactions_count": 230,
                "comments_count": 45,
            }
        ]
        videos = await FacebookService.get_page_videos("123456")
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0].id, "vid_01")
        self.assertEqual(videos[0].views, 1500)
        self.assertEqual(videos[0].reactions_count, 230)

    @patch("src.modules.creator.facebook.service.FacebookService.get_page_token", new_callable=AsyncMock)
    @patch("src.modules.creator.facebook.service.FacebookReelsPublisher.get_page_posts", new_callable=AsyncMock)
    async def test_get_page_posts(self, mock_get_posts, mock_get_token):
        mock_get_token.return_value = "token_123"
        mock_get_posts.return_value = [
            {
                "id": "post_01",
                "message": "Chào buổi sáng cả nhà!",
                "created_time": "2026-11-06T07:00:00+0000",
                "thumbnail": "",
                "permalink_url": "https://facebook.com/post_01",
                "shares_count": 10,
                "reactions_count": 89,
                "comments_count": 12,
            }
        ]
        posts = await FacebookService.get_page_posts("123456")
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].shares_count, 10)
        self.assertEqual(posts[0].reactions_count, 89)

    @patch("src.modules.creator.facebook.service.FacebookService.get_page_token", new_callable=AsyncMock)
    @patch("src.modules.creator.facebook.service.FacebookReelsPublisher.publish_reel_from_file", new_callable=AsyncMock)
    async def test_publish_reel(self, mock_publish, mock_token):
        mock_token.return_value = "token_123"
        mock_publish.return_value = {
            "success": True,
            "video_id": "vid_999",
            "page_id": "123456",
            "page_name": "Test Page",
            "caption": "Phim mới cực cuốn #shorts",
            "reel_url": "https://www.facebook.com/reel/vid_999",
        }
        req = PublishReelRequest(
            page_id="123456",
            video_path="/path/to/vid.mp4",
            caption="Phim mới cực cuốn #shorts",
        )
        res = await FacebookService.publish_reel(req)
        self.assertTrue(res.success)
        self.assertEqual(res.video_id, "vid_999")
        self.assertEqual(res.reel_url, "https://www.facebook.com/reel/vid_999")


if __name__ == "__main__":
    unittest.main(argv=[""], exit=False)
