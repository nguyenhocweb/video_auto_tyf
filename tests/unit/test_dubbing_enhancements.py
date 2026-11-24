import os
import unittest
from unittest.mock import patch, MagicMock
from src.core.engines.dubbing.translator import DubbingTranslator
from src.core.engines.dubbing.audio_aligner import DubbingAudioAligner
from src.core.engines.dubbing.subtitle_remover import SubtitleRemover


class TestDubbingEnhancements(unittest.TestCase):
    def test_export_ass_reels_golden_yellow_style(self):
        """Kiểm tra file ASS xuất ra mang màu vàng nghệ và viền đen dày chuẩn mẫu Ảnh 2."""
        segments = [
            {"start": 1.0, "end": 2.5, "text_translated": "Trường An có yêu quái hoành hành"}
        ]
        out_path = "be/storage/temp/test_reels.ass"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            DubbingTranslator.export_ass(segments, out_path, font_size=21)
            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Kiểm tra màu vàng nghệ &H0000E6FF
            self.assertIn("&H0000E6FF", content)
            # Kiểm tra viền đen 4.2 và shadow 2.5
            self.assertIn(",4.2,2.5,", content)
            # Kiểm tra nội dung phụ đề
            self.assertIn("Trường An có yêu quái hoành hành", content)
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)

    def test_clean_text_for_tts(self):
        """Kiểm tra bộ lọc sạch văn bản đầu vào cho TTS chống mất chữ và xóa triệt để tag [Tôi - bạn]."""
        raw = "[[[0]]] [Tôi - bạn] 长安有妖! Đây là câu thoại tiếng Việt 😊👍 {đặc biệt}."
        cleaned = DubbingAudioAligner.clean_text_for_tts(raw)
        self.assertNotIn("[[[0]]]", cleaned)
        self.assertNotIn("[Tôi - bạn]", cleaned)
        self.assertNotIn("长安有妖", cleaned)
        self.assertNotIn("😊", cleaned)
        self.assertIn("Đây là câu thoại tiếng Việt", cleaned)

    def test_build_timeline_enable_expr(self):
        """Kiểm tra tạo biểu thức timeline bật/tắt dải mờ có xuất hiện sớm (lead_in) và gộp khoảng trống gần."""
        segments = [
            {"start": 1.0, "end": 2.5},
            {"start": 2.7, "end": 4.0},
            {"start": 8.0, "end": 10.0},
        ]
        expr = SubtitleRemover.build_timeline_enable_expr(segments, lead_in=0.20, tail_out=0.15, merge_gap=0.25)
        # Câu 1 và 2 được gộp liền mạch từ 0.80s đến 4.15s (xuất hiện sớm 0.2s)
        self.assertIn("between(t,0.80,4.15)", expr)
        self.assertIn("between(t,7.80,10.15)", expr)

    def test_optimize_text_for_pace(self):
        """Kiểm tra tối ưu hóa câu thoại tinh gọn khi thời lượng nói ngắn."""
        long_text = "ngay tại thời điểm này ở tại nơi này chúng ta hoàn toàn không có cách nào khác"
        condensed = DubbingAudioAligner.optimize_text_for_pace(long_text, available_dur_sec=1.5)
        self.assertIn("lúc này", condensed)
        self.assertIn("tại đây", condensed)
        self.assertNotIn("ngay tại thời điểm này", condensed)

        # Kiểm tra tối ưu các câu dài trong bối cảnh phim thực tế
        t1 = "Không cần lo lắng, bạn đang một cây cỏ."
        c1 = DubbingAudioAligner.optimize_text_for_pace(t1, available_dur_sec=1.2)
        self.assertIn("đừng lo", c1.lower())

        t2 = "Đợi cho đến khi bạn có năng lượng và năng lượng."
        c2 = DubbingAudioAligner.optimize_text_for_pace(t2, available_dur_sec=1.2)
        self.assertIn("chờ khi", c2.lower())
        self.assertNotIn("năng lượng và năng lượng", c2.lower())

    @patch("subprocess.run")
    def test_subtitle_remover_soft_blur_strip(self, mock_subproc):
        """Kiểm tra SubtitleRemover sinh đúng dải mờ gblur và lớp phủ mờ che sạch nét chữ."""
        mock_subproc.return_value = MagicMock(returncode=0)
        with patch("os.path.exists", return_value=True):
            out = SubtitleRemover.clean_video(
                input_video_path="fake_input.mp4",
                output_video_path="fake_output.mp4",
                segments=[{"start": 1.0, "end": 3.0}],
                ymin_ratio=0.84,
                ymax_ratio=0.96,
                blur_radius=28,
            )
            self.assertEqual(out, "fake_output.mp4")
            called_cmd = mock_subproc.call_args[0][0]
            cmd_str = " ".join(called_cmd)
            self.assertIn("gblur=sigma=28", cmd_str)
            self.assertIn("overlay=", cmd_str)

    def test_detect_subtitle_region_mock(self):
        """Kiểm tra logic nhận diện vùng phụ đề và tính MarginV tương ứng."""
        # Khi không mở được video, trả về fallback an toàn
        ymin, ymax, margin_v = SubtitleRemover.detect_subtitle_region("non_existent.mp4")
        self.assertGreater(ymax, ymin)
        self.assertGreater(margin_v, 0)

    def test_is_suspicious_or_non_vietnamese_detection(self):
        """Kiểm tra bộ lọc phát hiện chính xác mọi trường hợp lọt tiếng Anh hoặc chữ Hán."""
        from src.core.engines.dubbing.translator import is_suspicious_or_non_vietnamese

        # Các câu lỗi thực tế từ mô hình Qwen
        self.assertTrue(is_suspicious_or_non_vietnamese("Sau khi chúng ăn, xuyên qua their heads"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Khi trời tối ngày càng黑"))
        self.assertTrue(is_suspicious_or_non_vietnamese("No thing"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Notify them"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Let's rest for a day"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Big boss"))
        self.assertTrue(is_suspicious_or_non_vietnamese("I also want to pick some"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Tell everyone"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Play"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Child"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Fast enough tonight"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Slow enough tomorrow"))
        self.assertTrue(is_suspicious_or_non_vietnamese("Give me back the apple"))

        # Các câu tiếng Việt chuẩn không bị nhận diện nhầm
        self.assertFalse(is_suspicious_or_non_vietnamese("Ở đây có chuyện gì đang xảy ra vậy?"))
        self.assertFalse(is_suspicious_or_non_vietnamese("Chúng ta nên tìm một nơi an toàn."))
        self.assertFalse(is_suspicious_or_non_vietnamese("Đúng rồi, hãy đợi một chút."))
        self.assertFalse(is_suspicious_or_non_vietnamese("Đại ca, trời ngày càng tối rồi."))


if __name__ == "__main__":
    unittest.main()
