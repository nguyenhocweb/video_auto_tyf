import os
import unittest
import tempfile
from pathlib import Path
import cv2
import numpy as np
from src.modules.creator.dubbing.schemas import SubtitleSegmentSchema
from src.core.engines.dubbing.translator import DubbingTranslator
from src.core.engines.dubbing.video_mixer import DubbingVideoMixer
from src.core.engines.dubbing.subtitle_remover import SubtitleRemover


class TestDubbingUnit(unittest.TestCase):
    def test_subtitle_segment_schema(self):
        seg = SubtitleSegmentSchema(
            id=0,
            start=1.25,
            end=4.50,
            duration=3.25,
            text_origin="众所周知，人死是真的能够复活的！",
            text_translated="Như mọi người đều biết, người chết thực sự có thể sống lại!"
        )
        self.assertEqual(seg.id, 0)
        self.assertEqual(seg.duration, 3.25)
        self.assertIn("sống lại", seg.text_translated)

    def test_srt_and_ass_export(self):
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            segments = [
                {
                    "id": 0,
                    "start": 0.5,
                    "end": 3.2,
                    "duration": 2.7,
                    "text_origin": "你好世界",
                    "text_translated": "Xin chào thế giới"
                },
                {
                    "id": 1,
                    "start": 3.5,
                    "end": 6.0,
                    "duration": 2.5,
                    "text_origin": "这是第二句话",
                    "text_translated": "Đây là câu thứ hai"
                }
            ]

            srt_path = str(tmp_path / "test.srt")
            ass_path = str(tmp_path / "test.ass")

            DubbingTranslator.export_srt(segments, srt_path, use_translated=True)
            DubbingTranslator.export_ass(segments, ass_path, font_size=20, use_translated=True)

            self.assertTrue(os.path.exists(srt_path))
            self.assertTrue(os.path.exists(ass_path))

            with open(srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()
            self.assertIn("00:00:00,500 --> 00:00:03,200", srt_content)
            self.assertIn("Xin chào thế giới", srt_content)

            with open(ass_path, "r", encoding="utf-8") as f:
                ass_content = f.read()
            self.assertIn("[Script Info]", ass_content)
            self.assertIn("[V4+ Styles]", ass_content)
            self.assertIn("Xin chào thế giới", ass_content)

    def test_video_mixer_escape_path(self):
        path_win = r"D:\DuAnCaNhan\video_ai\storage\test.ass"
        escaped = DubbingVideoMixer._escape_filter_path(path_win)
        self.assertIn("D\\:", escaped)
        self.assertIn("/", escaped)

    def test_subtitle_remover_timeline_expr(self):
        # 1. Hai câu thoại có khoảng nghỉ lớn hơn merge_gap (1.8s) -> tách thành 2 khoảng mờ riêng
        segments = [
            {"start": 1.25, "end": 3.40, "text": "Câu 1"},
            {"start": 7.50, "end": 9.00, "text": "Câu 2"},
        ]
        expr = SubtitleRemover.build_timeline_enable_expr(segments)
        self.assertIn("between(t,0.40,3.75)", expr)
        self.assertIn("between(t,6.65,9.35)", expr)
        self.assertIn("+", expr)

        # 2. Hai câu thoại gần nhau (nghỉ < 1.8s) -> tự động gộp mượt mà chống chớp tắt
        close_segments = [
            {"start": 1.25, "end": 3.40, "text": "Câu 1"},
            {"start": 4.50, "end": 7.00, "text": "Câu 2"},
        ]
        merged_expr = SubtitleRemover.build_timeline_enable_expr(close_segments)
        self.assertIn("between(t,0.40,7.35)", merged_expr)

    def test_doc_serialization_fastapi(self):
        from bson import ObjectId
        import datetime
        from fastapi.encoders import jsonable_encoder

        doc = {
            "_id": ObjectId(),
            "user_id": ObjectId(),
            "title": "Test Video",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
            "updated_at": datetime.datetime.now(datetime.timezone.utc),
        }
        # Áp dụng logic chuẩn hóa repository
        doc["id"] = str(doc["_id"])
        doc["_id"] = str(doc["_id"])
        doc["user_id"] = str(doc["user_id"])
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()

        encoded = jsonable_encoder({"items": [doc], "total": 1})
        self.assertEqual(encoded["total"], 1)
        self.assertIsInstance(encoded["items"][0]["_id"], str)
        self.assertIsInstance(encoded["items"][0]["user_id"], str)

    def test_vietnam_timezone_conversion(self):
        from src.core.utils.date_utils import to_vn_iso, format_vn_datetime
        import datetime

        # Giả lập datetime UTC naive như trong MongoDB
        utc_naive = datetime.datetime(2026, 11, 4, 3, 25, 27)
        vn_iso = to_vn_iso(utc_naive)
        self.assertIn("+07:00", vn_iso)
        self.assertIn("10:25:27", vn_iso)

        formatted = format_vn_datetime(utc_naive)
        self.assertIn("10:25:27", formatted)
        self.assertIn("04/11/2026", formatted)

    def test_delimited_output_parsing(self):
        from src.core.engines.dubbing.groq_translator import GroqTranslator
        from src.core.engines.dubbing.qwen_translator import QwenInProcessTranslator

        raw_llm_output = (
            "Chào bạn, dưới đây là bản dịch kịch bản:\n"
            "--- NỘI DUNG ĐÃ DỊCH ---\n"
            "LINE_0: \"Đứng lại ngay!\"\n"
            "LINE_1: \"Ta sẽ không tha cho ngươi.\"\n"
            "--- HẾT NỘI DUNG ĐÃ DỊCH ---\n"
            "Note: Tên đã được chuyển đổi sang tiếng Việt theo quy tắc đã định.\n"
            "1. Lưu ý: Cần kiểm tra lại ngữ cảnh."
        )

        groq_parsed = GroqTranslator._parse_indexed_translation(raw_llm_output, expected_count=2, texts=["站住！", "我不会放过你。"])
        self.assertEqual(len(groq_parsed), 2)
        self.assertEqual(groq_parsed[0], "Đứng lại ngay!")
        self.assertEqual(groq_parsed[1], "Ta sẽ không tha cho ngươi.")
        self.assertNotIn(2, groq_parsed)

        qwen_parsed = QwenInProcessTranslator._parse_indexed_translation(raw_llm_output, expected_count=2, texts=["站住！", "我不会放过你。"])
        self.assertEqual(len(qwen_parsed), 2)
        self.assertEqual(qwen_parsed[0], "Đứng lại ngay!")
        self.assertEqual(qwen_parsed[1], "Ta sẽ không tha cho ngươi.")


if __name__ == "__main__":
    unittest.main()
