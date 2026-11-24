import unittest
from src.core.engines.dubbing.hallucination_filter import (
    is_hallucinated_segment,
    filter_repeated_hallucination_segments,
)
from src.core.utils.text_sanitizer import is_ai_boilerplate, clean_subtitle_text
from src.core.engines.dubbing.videolingo_prompt import build_videolingo_prompt
from src.core.engines.dubbing.groq_translator import GroqTranslator


class TestHallucinationAndRepetition(unittest.TestCase):
    def test_music_hallucination_filter(self):
        """Kiểm tra bộ lọc ảo giác âm nhạc Whisper."""
        self.assertTrue(is_hallucinated_segment("我也来帮你解释吧", duration=2.5))
        self.assertTrue(is_hallucinated_segment("消受解释", duration=1.8))
        self.assertTrue(is_hallucinated_segment("不想解释", duration=1.2))
        self.assertTrue(is_hallucinated_segment("我说灵感", duration=1.8))
        self.assertTrue(is_hallucinated_segment("来杀来解", duration=1.2))
        self.assertTrue(is_hallucinated_segment("我们也去", duration=1.5))
        # Câu hội thoại bình thường phải không bị lọc
        self.assertFalse(is_hallucinated_segment("天师使用蛮雷咒", duration=2.0))
        self.assertFalse(is_hallucinated_segment("快跟我一起走", duration=1.5))

    def test_repeated_hallucination_segments(self):
        """Kiểm tra loại bỏ lặp chuỗi phân đoạn liên tiếp và lặp toàn cục."""
        fake_segs = [
            {"id": 0, "text_origin": "过来"},
            {"id": 1, "text_origin": "过来"},
            {"id": 2, "text_origin": "过来"},
            {"id": 3, "text_origin": "天师在此"},
            {"id": 4, "text_origin": "妖孽休走"},
            {"id": 5, "text_origin": "过来"},
            {"id": 6, "text_origin": "过来"},
        ]
        pruned = filter_repeated_hallucination_segments(fake_segs)
        texts = [s["text_origin"] for s in pruned]
        self.assertNotIn("过来", texts)
        self.assertIn("天师在此", texts)
        self.assertIn("妖孽休走", texts)

    def test_ai_boilerplate_detection(self):
        """Kiểm tra phát hiện câu đệm trợ lý và câu lặp ảo giác."""
        self.assertTrue(is_ai_boilerplate("Tôi sẽ giúp bạn giải thích nhé."))
        self.assertTrue(is_ai_boilerplate("Tôi sẽ chịu tiệu để giải thích"))
        self.assertTrue(is_ai_boilerplate("Tôi sẽ chịu tiêu để giải thích"))
        self.assertTrue(is_ai_boilerplate("chịu tiêu"))
        self.assertTrue(is_ai_boilerplate("Tôi không muốn giải thích"))
        self.assertTrue(is_ai_boilerplate("Tôi nói cảm hứng"))
        self.assertTrue(is_ai_boilerplate("Đến để giết để giải thích"))
        # Câu phụ đề bình thường
        self.assertFalse(is_ai_boilerplate("Thiên sư đã giáng hạ man lôi chú!"))
        self.assertFalse(is_ai_boilerplate("Làm sao có thể như vậy được..."))

    def test_videolingo_prompt_builder(self):
        """Kiểm tra prompt dịch phụ đề có đầy đủ ràng buộc chống ảo giác và SKIP."""
        texts = ["天师使用蛮雷咒", "消受解释"]
        context = {
            "genre": "Cổ trang / Tiên hiệp",
            "pronouns_rule": "Ta - Ngươi, Huynh - Đệ. CẤM 'Tôi - Bạn'",
        }
        prompt = build_videolingo_prompt(texts, context=context)
        self.assertIn("Cổ trang / Tiên hiệp", prompt)
        self.assertIn("[SKIP]", prompt)
        self.assertIn("LINE_0: 天师使用蛮雷咒", prompt)

    def test_parse_skip_in_groq_translator(self):
        """Kiểm tra parser của GroqTranslator loại bỏ nhãn [SKIP]."""
        raw_output = "LINE_0: Thiên sư giáng hạ man lôi chú!\nLINE_1: [SKIP]\nLINE_2: SKIP"
        parsed = GroqTranslator._parse_indexed_translation(raw_output, expected_count=3)
        self.assertIn(0, parsed)
        self.assertNotIn(1, parsed)
        self.assertNotIn(2, parsed)


if __name__ == "__main__":
    unittest.main()
