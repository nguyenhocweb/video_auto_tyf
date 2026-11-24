import os
import cv2
import numpy as np
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.core.engines.inspector.policy_checker import PolicyChecker
from src.core.engines.inspector.image_analyzer import ImageAnalyzer
from src.core.engines.inspector.video_pacing import VideoPacingAnalyzer


class TestInspectorEngines(unittest.TestCase):
    """Kiểm thử toàn diện 3 AI engines: PolicyChecker, ImageAnalyzer, VideoPacingAnalyzer."""

    def test_policy_checker_clean_text(self):
        """Văn bản sạch không từ cấm -> 100 điểm an toàn."""
        text = "Hôm nay thời tiết rất đẹp, chào mừng các bạn đến với video trải nghiệm."
        res = PolicyChecker.check_text(text)
        self.assertTrue(res["is_safe"])
        self.assertEqual(res["safety_score"], 100)
        self.assertEqual(res["total_violations"], 0)

    def test_policy_checker_violation_replacement(self):
        """Phát hiện từ cấm và thay thế bằng từ lóng né kiểm duyệt."""
        text = "Anh ta đã chết trong trận đấu súng và mất hết tiền tài xỉu."
        res = PolicyChecker.check_text(text)
        self.assertFalse(res["is_safe"])
        self.assertLess(res["safety_score"], 80)
        self.assertGreaterEqual(res["total_violations"], 3)
        # Kiểm tra từ thay thế xuất hiện trong văn bản viết lại
        self.assertIn("hẹo", res["rewritten_text"])
        self.assertIn("đồ chơi", res["rewritten_text"])
        self.assertIn("xí ngầu", res["rewritten_text"])

    def test_image_analyzer_synthetic_image(self):
        """Tạo ảnh nhân tạo kiểm thử phân tích màu sắc và độ tương phản."""
        with NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Tạo ảnh màu rực rỡ (vàng/đỏ) kích thước 400x400
            img = np.zeros((400, 400, 3), dtype=np.uint8)
            img[:200, :] = (0, 255, 255)  # Màu vàng
            img[200:, :] = (0, 0, 255)    # Màu đỏ
            cv2.imwrite(tmp_path, img)

            res = ImageAnalyzer.analyze_image(tmp_path)
            self.assertIn("overall_viral_score", res)
            self.assertGreaterEqual(res["overall_viral_score"], 10)
            self.assertIn("visual_analysis", res)
            self.assertGreaterEqual(res["visual_analysis"]["saturation"], 100)
            self.assertIn("actionable_advice", res)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_video_pacing_analyzer_scene_cuts(self):
        """Tạo video giả lập có 2 cảnh đổi màu rõ rệt để kiểm tra bắt chuyển cảnh."""
        with NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(tmp_path, fourcc, 10.0, (160, 120))

            # Cảnh 1: 20 frame màu đen (2 giây)
            frame_black = np.zeros((120, 160, 3), dtype=np.uint8)
            for _ in range(20):
                out.write(frame_black)

            # Cảnh 2: 20 frame màu trắng (2 giây) -> Có 1 chuyển cảnh tại giây thứ 2
            frame_white = np.ones((120, 160, 3), dtype=np.uint8) * 255
            for _ in range(20):
                out.write(frame_white)

            out.release()

            res = VideoPacingAnalyzer.analyze_video_pacing(tmp_path, sample_fps=3)
            self.assertGreater(res["duration_seconds"], 0)
            self.assertGreaterEqual(res["total_scene_cuts"], 1)
            self.assertIn("pacing_score", res)
            self.assertIn("actionable_advice", res)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
