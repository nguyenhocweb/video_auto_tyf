import unittest
from src.core.engines.dubbing.video_mixer import DubbingVideoMixer


class TestVideoMixerDucking(unittest.TestCase):
    """Kiểm thử tính năng hòa âm thông minh (Sidechain Dynamic Audio Ducking) và fallback."""

    def test_dynamic_sidechain_filter_generation(self):
        """Bộ lọc dynamic sidechain phải chứa sidechaincompress với các tham số chuẩn."""
        filter_str = DubbingVideoMixer._build_audio_filter(
            has_orig_audio=True, voice_vol=1.35, bgm_vol=0.08, dynamic=True
        )
        self.assertIn("sidechaincompress", filter_str)
        self.assertIn("asplit=2", filter_str)
        self.assertIn("threshold=0.025", filter_str)
        self.assertIn("ratio=12", filter_str)
        self.assertIn("attack=12", filter_str)
        self.assertIn("release=1000", filter_str)
        self.assertIn("volume=1.35", filter_str)
        self.assertIn("volume=0.92", filter_str)
        self.assertIn("amix=inputs=2", filter_str)

    def test_static_fallback_filter_generation(self):
        """Bộ lọc static fallback phải sử dụng volume scaling và amix tiêu chuẩn."""
        filter_str = DubbingVideoMixer._build_audio_filter(
            has_orig_audio=True, voice_vol=1.2, bgm_vol=0.05, dynamic=False
        )
        self.assertNotIn("sidechaincompress", filter_str)
        self.assertIn("volume=0.2", filter_str)
        self.assertIn("volume=1.2", filter_str)
        self.assertIn("amix=inputs=2", filter_str)

    def test_no_orig_audio_stream(self):
        """Khi video không có track âm thanh, chỉ xuất stream thuyết minh mà không mix."""
        filter_str = DubbingVideoMixer._build_audio_filter(
            has_orig_audio=False, voice_vol=1.5, bgm_vol=0.08, dynamic=True
        )
        self.assertEqual(filter_str, "[1:a]volume=1.5[aout]")

    def test_escape_filter_path_windows(self):
        """Thoát ký tự ổ đĩa và dấu gạch chéo chuẩn FFmpeg Windows."""
        raw_path = r"D:\DuAnCaNhan\video_ai\storage\sub.ass"
        escaped = DubbingVideoMixer._escape_filter_path(raw_path)
        self.assertIn(r"D\:/", escaped)
        self.assertNotIn(r"\DuAnCaNhan", escaped)


if __name__ == "__main__":
    unittest.main()
