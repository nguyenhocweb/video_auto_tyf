import unittest
from src.core.engines.stitch.video_stitcher import VideoStitcher
from src.modules.creator.automation.schemas import DualSourceConfig, AutomationCampaignCreateRequest
from src.modules.creator.automation.hook_pool_repo import HookPoolMongoRepository
from src.modules.creator.automation.dual_source_worker import DualSourceWorker


class TestVideoStitcher(unittest.TestCase):
    def test_dual_source_config_defaults(self):
        cfg = DualSourceConfig(
            enabled=True,
            hook_channel_url="https://www.douyin.com/user/MS4wLjABAAAA...",
            hook_channel_name="Kênh Hook Gái Xinh",
            hook_duration_sec=4.0,
            body_skip_start_sec=3.5,
            audio_mode="sequential",
            fallback_policy="reuse_oldest",
        )
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.hook_duration_sec, 4.0)
        self.assertEqual(cfg.body_skip_start_sec, 3.5)
        self.assertEqual(cfg.audio_mode, "sequential")
        self.assertEqual(cfg.fallback_policy, "reuse_oldest")
        self.assertEqual(cfg.aspect_ratio, "9:16")
        self.assertEqual(cfg.transition_duration_sec, 1.2)

    def test_campaign_create_with_dual_source(self):
        req = AutomationCampaignCreateRequest(
            name="Chiến dịch Ghép 2 Nguồn",
            source_channels=[{"channel_url": "https://www.douyin.com/user/test", "name": "Kênh Thân Bài"}],
            dual_source=DualSourceConfig(
                enabled=True,
                hook_channel_url="https://www.douyin.com/user/hook",
                hook_channel_name="Kênh Hook",
                hook_duration_sec=3.0,
                body_skip_start_sec=2.5,
            ),
        )
        self.assertIsNotNone(req.dual_source)
        self.assertTrue(req.dual_source.enabled)
        self.assertEqual(req.dual_source.hook_duration_sec, 3.0)

    def test_stitcher_engine_methods_exist(self):
        self.assertTrue(hasattr(VideoStitcher, "get_media_duration"))
        self.assertTrue(hasattr(VideoStitcher, "has_audio_stream"))
        self.assertTrue(hasattr(VideoStitcher, "extract_hook_clip"))
        self.assertTrue(hasattr(VideoStitcher, "stitch_hook_and_body"))

    def test_hook_pool_repo_methods_exist(self):
        repo = HookPoolMongoRepository()
        self.assertTrue(hasattr(repo, "is_hook_already_saved"))
        self.assertTrue(hasattr(repo, "save_hook"))
        self.assertTrue(hasattr(repo, "get_available_hook"))
        self.assertTrue(hasattr(repo, "get_fallback_hook"))
        self.assertTrue(hasattr(repo, "mark_hook_used"))

    def test_dual_source_worker_methods(self):
        worker = DualSourceWorker()
        self.assertTrue(hasattr(worker, "harvest_hook_channel"))
        self.assertTrue(hasattr(worker, "prepare_stitched_video"))
        self.assertTrue(callable(worker.harvest_hook_channel))
        self.assertTrue(callable(worker.prepare_stitched_video))


if __name__ == "__main__":
    unittest.main()
