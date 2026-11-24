import unittest
from unittest.mock import patch, MagicMock
from src.core.engines.dubbing.translator import DubbingTranslator
from src.core.engines.dubbing.qwen_translator import QwenInProcessTranslator


class TestTranslationEngines(unittest.TestCase):
    """Kiểm thử các cơ chế dịch thuật, parsing token và bảo vệ không lọt chữ tiếng Trung."""

    def test_qwen_parse_indexed_translation(self):
        """Kiểm tra tách đúng token <<<LINE_i>>>, [[[i]]], - [[i]] - từ output."""
        sample_output = """
        <<<LINE_0>>> Chào mọi người, hôm nay mình sẽ kể một câu chuyện rất thú vị.
        - [[1]] - Đúng lúc này, sếp bước vào và làm mọi người giật mình.
        [[[2]]] Anh em thấy hay thì nhớ thả tim nhé!
        """
        parsed = QwenInProcessTranslator._parse_indexed_translation(sample_output, expected_count=3)
        self.assertEqual(len(parsed), 3)
        self.assertIn("Chào mọi người", parsed[0])
        self.assertIn("sếp bước vào", parsed[1])
        self.assertIn("thả tim", parsed[2])

    def test_translator_fallback_when_qwen_fails(self):
        """Kiểm tra dịch các segments phụ đề qua translate_segments."""
        segments = [
            {"start": 0.0, "end": 2.0, "text_origin": "你好"},
            {"start": 2.0, "end": 4.0, "text_origin": "世界"},
        ]
        with patch.object(
            QwenInProcessTranslator,
            "translate_batch",
            return_value=["Xin chào", "Thế giới"],
        ):
            result = DubbingTranslator.translate_segments(segments)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["text_translated"], "Xin chào")
            self.assertEqual(result[1]["text_translated"], "Thế giới")

    def test_export_ass_never_leaks_chinese_origin(self):
        """Kiểm tra tuyệt đối không bao giờ dập chữ tiếng Trung gốc vào file phụ đề ASS Vietsub."""
        import tempfile
        from pathlib import Path
        import os

        segments = [
            {"start": 1.0, "end": 3.0, "text_origin": "既然是决切了虚烈天赋", "text_translated": ""},
            {"start": 3.5, "end": 5.0, "text_origin": "你好", "text_translated": "Xin chào"},
        ]
        with tempfile.TemporaryDirectory() as td:
            out_ass = str(Path(td) / "test_no_chinese.ass")
            DubbingTranslator.export_ass(segments, out_ass, use_translated=True)
            with open(out_ass, "r", encoding="utf-8") as f:
                content = f.read()

            # Chữ tiếng Trung gốc tuyệt đối không được xuất hiện trong phụ đề Vietsub
            self.assertNotIn("既然是决切了虚烈天赋", content)
            self.assertIn("Xin chào", content)


    def test_qwen_parse_delimited_output_and_strip_notes(self):
        """Kiểm tra ép buộc lấy nội dung trong khối phân tách và loại bỏ triệt để Note / SároNote."""
        sample_output = """
        Dưới đây là bản dịch phụ đề:
        --- NỘI DUNG ĐÃ DỊCH ---
        <<<LINE_0>>> Hôm nay trời rất đẹp.
        - [[1]] - SároNote: Tên Đã Được Chuyển Đổi Sang Tiếng Việt Theo Quy Tắc Đã Đ
        [[[2]]] Đúng vậy, chúng ta cùng đi dạo nhé! Note: Quy tắc xưng hô
        --- HẾT NỘI DUNG ĐÃ DỊCH ---
        Note: Bản dịch đã được kiểm duyệt chất lượng cao.
        """
        parsed = QwenInProcessTranslator._parse_indexed_translation(sample_output, expected_count=3)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0], "Hôm nay trời rất đẹp.")
        # Line 1 bị hủy hoàn toàn do chỉ chứa Note rác
        self.assertNotIn(1, parsed)
        # Line 2 đã cắt bỏ đuôi Note: Quy tắc xưng hô và giữ lại câu thoại sạch
        self.assertEqual(parsed[2], "Đúng vậy, chúng ta cùng đi dạo nhé!")


if __name__ == "__main__":
    unittest.main()
