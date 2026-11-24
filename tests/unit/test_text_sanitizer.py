import unittest
from src.core.utils.text_sanitizer import clean_subtitle_text, is_ai_boilerplate, is_length_hallucination


class TestTextSanitizer(unittest.TestCase):
    def test_clean_subtitle_text(self):
        cases = [
            ("- [[5]] - Đúng là con người", "Đúng là con người"),
            ("[[[0]]] Xin chào thế giới", "Xin chào thế giới"),
            ("[[5]] Xem anh mở cửa", "Xem anh mở cửa"),
            ("- [[0]] - Tôi - bạn", ""),
            ("1. Thất bại rồi", "Thất bại rồi"),
            ("<<<LINE_3>>> Đó là gì?", "Đó là gì?"),
            ("[Tôi - bạn] Bạn có đi không?", "Bạn có đi không?"),
            ("Dịch kịch bản sang tiếng Việt:", ""),
            ("- 5 - Nơi này không an toàn", "Nơi này không an toàn"),
            ("(Tôi - bạn) Ngươi hãy dừng tay!", "Ngươi hãy dừng tay!"),
            ("Tôi - bạn: Chúng ta đi đâu?", "Chúng ta đi đâu?"),
            ("[Thời lượng: 2.2s] [Thời lượng: 1.1s] [Thời lượng: 1.7s]", ""),
            ("<<<LINE_0>>> [Thời lượng: 2.2s] Lúc này Liệt thấy khó chịu", "Lúc này Liệt thấy khó chịu"),
            ("[Thời lượng: 1.5s] Hãy dừng tay lại ngay", "Hãy dừng tay lại ngay"),
            ("[Duration: 3.0s] Trả quả táo lại cho tao", "Trả quả táo lại cho tao"),
            ("SároNote: Tên Đã Được Chuyển Đổi Sang Tiếng Việt Theo Quy Tắc Đã Đ", ""),
            ("Đứng lại mau! Note: Tên nhân vật đã được giữ nguyên", "Đứng lại mau!"),
            ("Chạy đi! (Lưu ý: chuyển đổi xưng hô theo quy tắc)", "Chạy đi!"),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                self.assertEqual(clean_subtitle_text(inp), expected)

    def test_is_ai_boilerplate(self):
        self.assertTrue(is_ai_boilerplate("TUYỆT ĐỐI CẤM:"))
        self.assertTrue(is_ai_boilerplate("Tôi muốn tìm hiểu thêm về một bộ phim ngắn kịch tính mới. Bạn có thể giới thiệu cho tôi một dự án hay không?"))
        self.assertTrue(is_ai_boilerplate("Dạ, tôi không thể dịch câu này vì nó có thể gây hiểu lầm"))
        self.assertFalse(is_ai_boilerplate("Chắc là Zygarde dạng 50% rồi."))
        self.assertFalse(is_ai_boilerplate("Bên trong là ba lô cấp ba."))

    def test_is_length_hallucination(self):
        # Câu gốc 9 chữ Hán nhưng dịch ra 23 từ -> Ảo giác
        self.assertTrue(is_length_hallucination("基格尔德50%形态吧", "Tôi muốn tìm hiểu thêm về một bộ phim ngắn kịch tính mới. Bạn có thể giới thiệu cho tôi một dự án hay không?"))
        # Câu dịch hợp lý 7 từ -> Không ảo giác
        self.assertFalse(is_length_hallucination("基格尔德50%形态吧", "Chắc là Zygarde dạng 50% rồi."))


if __name__ == "__main__":
    unittest.main()
