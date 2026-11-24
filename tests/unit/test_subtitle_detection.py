import unittest
import numpy as np
import cv2
import tempfile
import os
from src.core.engines.dubbing.subtitle_remover import SubtitleRemover


class TestSubtitleDetection(unittest.TestCase):
    def test_edge_detects_text_rejects_white_clothing(self):
        """Kiểm tra thuật toán Sobel-X bắt đúng dòng text ở đáy và loại bỏ 100% áo trắng của nhân vật."""
        h, w = 1920, 1080
        frame = np.full((h, w, 3), (120, 120, 120), dtype=np.uint8)

        # Mô phỏng áo trắng của nhân vật (Y: 1350 đến 1600)
        cv2.rectangle(frame, (200, 1350), (880, 1600), (255, 255, 255), -1)

        # Mô phỏng dòng phụ đề chữ tiếng Trung ở đáy (Y: 1720 đến 1760)
        cv2.putText(frame, "TEXT SUBTITLE CHINESE LINE", (150, 1750), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 4)
        cv2.putText(frame, "TEXT SUBTITLE CHINESE LINE", (150, 1750), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2)

        # Lưu thành video mp4 tạm
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_vid = os.path.join(tmp_dir, "test_vertical.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(test_vid, fourcc, 10.0, (w, h))
            for _ in range(10):
                out.write(frame)
            out.release()

            ymin_r, ymax_r, margin_v = SubtitleRemover.detect_subtitle_region(test_vid)

            # Phụ đề nằm ở 1720/1920 ≈ 89.5% đến 1760/1920 ≈ 91.6%
            # Vùng nhận diện phải nằm trọn ở đáy (> 85%), tuyệt đối không được rơi vào áo trắng (70%-83%)
            self.assertGreater(ymin_r, 0.85, "Ymin phải ở vùng đáy (> 85%), không được dính áo trắng")
            self.assertGreater(ymax_r, ymin_r)
            self.assertLessEqual(ymax_r, 0.985)
            self.assertGreater(margin_v, 30)

    def test_fallback_when_no_text_in_video(self):
        """Kiểm tra fallback Cinematic an toàn khi video trơn không có text."""
        h, w = 1080, 1920
        frame = np.full((h, w, 3), (50, 50, 50), dtype=np.uint8)

        with tempfile.TemporaryDirectory() as tmp_dir:
            test_vid = os.path.join(tmp_dir, "test_plain.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(test_vid, fourcc, 10.0, (w, h))
            for _ in range(5):
                out.write(frame)
            out.release()

            ymin_r, ymax_r, margin_v = SubtitleRemover.detect_subtitle_region(test_vid)
            self.assertEqual(ymin_r, 0.840)
            self.assertEqual(ymax_r, 0.935)
            self.assertGreater(margin_v, 50)


if __name__ == "__main__":
    unittest.main()

