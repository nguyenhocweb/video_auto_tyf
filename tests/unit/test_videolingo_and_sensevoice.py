import unittest
from src.core.engines.dubbing.hallucination_filter import is_hallucinated_segment
from src.core.engines.dubbing.videolingo_prompt import build_videolingo_prompt
from src.core.engines.dubbing.sensevoice_engine import SenseVoiceEngine
from src.core.engines.dubbing.qwen_translator import QwenInProcessTranslator
from src.core.engines.dubbing.translator import DubbingTranslator


class TestVideoLingoAndSenseVoice(unittest.TestCase):
    """Kiểm thử chuyên sâu chống thảm họa 'Bạn hiển thị', tích hợp SenseVoice và chuẩn VideoLingo."""

    def test_ban_hien_thi_whisper_hallucination_detected(self):
        """Vụ án '你显示' kéo dài 42.2s trong video người dùng phải bị loại bỏ 100%."""
        # 1. Đoạn 42.2s chỉ có 3 chữ '你显示'
        self.assertTrue(is_hallucinated_segment("你显示", duration=42.2))
        self.assertTrue(is_hallucinated_segment("显示", duration=15.0))
        self.assertTrue(is_hallucinated_segment("谢谢收看", duration=3.0))
        self.assertTrue(is_hallucinated_segment("点赞关注", duration=4.0))

    def test_low_density_music_noise_detected(self):
        """Mật độ âm thoại quá thấp (âm nhạc kéo dài có 1-2 từ đệm) bị coi là ảo giác."""
        self.assertTrue(is_hallucinated_segment("啊", duration=8.0))
        self.assertTrue(is_hallucinated_segment("你好", duration=12.0))
        self.assertTrue(is_hallucinated_segment("。。。", duration=2.0))

    def test_valid_speech_not_flagged(self):
        """Lời thoại thực tế của nhân vật trong phim không được coi là ảo giác."""
        self.assertFalse(is_hallucinated_segment("快走，敌人已经追上来了！", duration=3.0))
        self.assertFalse(is_hallucinated_segment("大王饶命，小的什么都不知道", duration=3.5))

    def test_videolingo_prompt_builder(self):
        """Prompt VideoLingo phải chứa đầy đủ ràng buộc và định dạng dòng kịch bản."""
        prompt = build_videolingo_prompt(["你好", "老大快跑"], durations=[2.0, 3.0])
        self.assertIn("LINE_0: 你好", prompt)
        self.assertIn("LINE_1: 老大快跑", prompt)
        self.assertIn("QUY TẮC BẮT BUỘC", prompt)

    def test_extract_terms_and_context_ancient_genre(self):
        """Kiểm tra trích xuất thuật ngữ và nhận diện thể loại phim VideoLingo Step 4.1."""
        from src.core.engines.dubbing.videolingo_prompt import extract_terms_and_context
        ctx = extract_terms_and_context(["陛下息怒", "师父救我", "老大快走"])
        self.assertIn("Cổ trang", ctx["genre"])
        self.assertIn("Ta - Ngươi", ctx["pronouns_rule"])
        self.assertIn("老大", ctx["locked_terms"])

    def test_zero_google_translate_in_codebase(self):
        """DubbingTranslator hoàn toàn sử dụng LLM điện ảnh mà không dùng translate.googleapis.com."""
        import inspect
        trans_src = inspect.getsource(DubbingTranslator)
        gemini_src = inspect.getsource(QwenInProcessTranslator._call_single_gemini_api)
        self.assertNotIn("translate.googleapis.com", trans_src)
        self.assertNotIn("translate.googleapis.com", gemini_src)

    def test_sensevoice_engine_availability(self):
        """SenseVoice engine sẵn sàng hoạt động sau khi mô hình đã tải xong trên ổ D."""
        self.assertTrue(SenseVoiceEngine.is_available())
        self.assertIsNotNone(SenseVoiceEngine._find_model_dir())
        self.assertIsNotNone(SenseVoiceEngine._find_vad_dir())


if __name__ == "__main__":
    unittest.main()

