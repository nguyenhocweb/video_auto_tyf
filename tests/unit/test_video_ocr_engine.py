import unittest
import numpy as np
import cv2
from src.core.engines.dubbing.video_ocr_engine import VideoOCREngine


class TestVideoOCREngine(unittest.TestCase):
    """Kiểm thử Engine bóc tách văn bản gốc từ khung hình video (Video OCR)."""

    def test_clean_ocr_text(self):
        """Lọc sạch ký tự rác, bảo toàn chữ Hán và khoảng trắng chuẩn."""
        raw_1 = "  王鹏展那把电烫棒改的武器也归了他！ "
        self.assertEqual(VideoOCREngine._clean_ocr_text(raw_1), "王鹏展那把电烫棒改的武器也归了他")

        raw_2 = "【第1集】 游戏时间推进到... "
        self.assertEqual(VideoOCREngine._clean_ocr_text(raw_2), "第1集 游戏时间推进到")

        raw_3 = "---...///"
        self.assertEqual(VideoOCREngine._clean_ocr_text(raw_3), "")

    def test_has_text_presence_gate(self):
        """Bộ lọc toán học 1ms (Text-Presence Gate) phân biệt chính xác nét chữ và nền trống."""
        # 1. Nền đen hoàn toàn -> Không có chữ -> False
        black_img = np.zeros((100, 400), dtype=np.uint8)
        self.assertFalse(VideoOCREngine._has_text_presence(black_img))

        # 2. Nền xám trơn đồng nhất (nhiễu chuyển động camera) -> Không có chữ -> False
        uniform_gray = np.full((100, 400), 180, dtype=np.uint8)
        self.assertFalse(VideoOCREngine._has_text_presence(uniform_gray))

        # 3. Nền có nét chữ phụ đề tương phản cao (chữ trắng trên nền tối) -> Có chữ -> True
        text_img = np.zeros((100, 400), dtype=np.uint8)
        cv2.putText(text_img, "SUBTITLE TEXT 123", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 255, 3)
        self.assertTrue(VideoOCREngine._has_text_presence(text_img))

    def test_ocr_engine_initialization(self):
        """RapidOCR instance nạp thành công và sẵn sàng xử lý."""
        ocr = VideoOCREngine.get_ocr()
        self.assertIsNotNone(ocr)

    def test_extract_subtitles_nonexistent_file(self):
        """Video không tồn tại trả về danh sách rỗng an toàn."""
        res = VideoOCREngine.extract_subtitles_from_video("nonexistent_video_path.mp4")
        self.assertEqual(res, [])


if __name__ == "__main__":
    unittest.main()


