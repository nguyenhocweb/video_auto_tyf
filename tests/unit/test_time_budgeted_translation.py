import unittest
from src.core.utils.text_sanitizer import clean_subtitle_text
from src.core.engines.dubbing.qwen_translator import QwenInProcessTranslator


class TestTimeBudgetedTranslation(unittest.TestCase):
    """Kiểm thử tính năng Biên kịch theo ngân sách thời gian (Time-Budgeted Scriptwriting)."""

    def test_clean_subtitle_text_strips_budget_hints(self):
        """Khử sạch các nhãn gợi ý ngân sách từ và thời lượng khỏi văn bản phụ đề."""
        raw_1 = "<<<LINE_0>>>(nói 1.8s, TỐI ĐA 6 TỪ): Ngươi điên thật rồi!"
        self.assertEqual(clean_subtitle_text(raw_1), "Ngươi điên thật rồi!")

        raw_2 = "(nói trong 2.5s) Đi mau lên!"
        self.assertEqual(clean_subtitle_text(raw_2), "Đi mau lên!")

        raw_3 = "Đại ca, bảo trọng! (TỐI ĐA 5 TỪ)"
        self.assertEqual(clean_subtitle_text(raw_3), "Đại ca, bảo trọng!")

        raw_4 = "[Thời lượng: 2.2s] Hãy chờ ta!"
        self.assertEqual(clean_subtitle_text(raw_4), "Hãy chờ ta!")

    def test_parse_indexed_translation_with_budget_labels(self):
        """Trích xuất chính xác chỉ số dòng và câu thoại kể cả khi LLM in kèm nhãn ngân sách."""
        llm_output = (
            "<<<LINE_0>>>(nói 1.2s, TỐI ĐA 4 TỪ): Ngươi dám sao?\n"
            "<<<LINE_1>>> Ta tuyệt đối không lùi bước!\n"
            "<<<LINE_2>>> (TỐI ĐA 6 TỪ) Mau chạy đi!"
        )
        parsed = QwenInProcessTranslator._parse_indexed_translation(llm_output, 3)
        self.assertEqual(parsed.get(0), "Ngươi dám sao?")
        self.assertEqual(parsed.get(1), "Ta tuyệt đối không lùi bước!")
        self.assertEqual(parsed.get(2), "Mau chạy đi!")

    def test_word_budget_calculation(self):
        """Tính toán ngân sách từ hợp lý dựa trên tốc độ nói chuẩn ~3.1 từ/giây."""
        durations = [0.8, 1.5, 2.5, 4.0]
        expected_budgets = [
            max(3, int(round(0.8 * 3.1))),  # 3 từ
            max(3, int(round(1.5 * 3.1))),  # 5 từ
            max(3, int(round(2.5 * 3.1))),  # 8 từ
            max(3, int(round(4.0 * 3.1))),  # 12 từ
        ]
        self.assertEqual(expected_budgets, [3, 5, 8, 12])


if __name__ == "__main__":
    unittest.main()

