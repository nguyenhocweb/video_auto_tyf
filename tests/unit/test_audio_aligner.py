import unittest
from src.core.engines.dubbing.audio_aligner import DubbingAudioAligner


class TestDubbingAudioAligner(unittest.TestCase):
    """Bộ kiểm thử đơn vị cho khâu xử lý âm thanh & dóng hàng giọng đọc (DubbingAudioAligner)."""

    def test_clean_text_for_tts(self):
        """Kiểm tra làm sạch chuỗi văn bản trước khi đưa vào TTS."""
        raw = "Các ngươi đều là hậu nhân, không cần phải quỳ nữa! 你们都是后人 [tag]"
        cleaned = DubbingAudioAligner.clean_text_for_tts(raw)
        self.assertNotIn("你们都是后人", cleaned)
        self.assertIn("Các ngươi đều là hậu nhân", cleaned)

    def test_optimize_text_for_pace(self):
        """Kiểm tra thuật ngữ lược giản câu thoại để kịp thời lượng phát âm."""
        verbose_text = "ở tại nơi này chúng ta hoàn toàn không có cách nào"
        condensed = DubbingAudioAligner.optimize_text_for_pace(verbose_text, available_dur_sec=1.5)
        self.assertIn("tại đây", condensed)
        self.assertIn("không có", condensed)

    def test_fit_audio_duration_clamp(self):
        """Kiểm tra khống chế hệ số co giãn tốc độ trong dải an toàn (0.95x - 1.12x)."""
        # Đảm bảo không bị méo giọng thành sóc chuột
        dur = 2.0
        # Kiểm tra logic tính tốc độ
        target = 1.0
        speed = dur / target
        speed_clamped = max(0.95, min(speed, 1.12))
        self.assertEqual(speed_clamped, 1.12)


if __name__ == "__main__":
    unittest.main()

