import unittest
from types import SimpleNamespace
from src.core.engines.dubbing.transcriber import DubbingTranscriber


class TestTranscriberSplitting(unittest.TestCase):
    def test_split_long_segment_by_punctuation(self):
        """Kiểm tra câu thoại dài bị gộp được tách thành từng câu đơn súc tích chuẩn timeline."""
        words = [
            SimpleNamespace(word="我", start=5.0, end=5.3),
            SimpleNamespace(word="是", start=5.3, end=5.6),
            SimpleNamespace(word="道", start=5.6, end=6.0),
            SimpleNamespace(word="士", start=6.0, end=6.4),
            SimpleNamespace(word="。", start=6.4, end=6.6),
            SimpleNamespace(word="居", start=7.5, end=7.8),
            SimpleNamespace(word="然", start=7.8, end=8.1),
            SimpleNamespace(word="被", start=8.1, end=8.4),
            SimpleNamespace(word="银", start=8.4, end=8.8),
            SimpleNamespace(word="僵", start=8.8, end=9.2),
            SimpleNamespace(word="揩", start=9.2, end=9.6),
            SimpleNamespace(word="油", start=9.6, end=10.0),
            SimpleNamespace(word="！", start=10.0, end=10.2),
        ]
        mock_seg = SimpleNamespace(
            start=5.0,
            end=10.2,
            text="我是道士。居然被银僵揩油！",
            words=words,
        )

        sub_items = DubbingTranscriber._split_segment_by_sentences(mock_seg)
        self.assertEqual(len(sub_items), 2)
        self.assertEqual(sub_items[0]["start"], 5.0)
        self.assertEqual(sub_items[0]["end"], 6.6)
        self.assertEqual(sub_items[0]["text_origin"], "我是道士。")

        self.assertEqual(sub_items[1]["start"], 7.5)
        self.assertEqual(sub_items[1]["end"], 10.2)
        self.assertEqual(sub_items[1]["text_origin"], "居然被银僵揩油！")

    def test_discard_lone_punctuation(self):
        """Kiểm tra loại bỏ hoàn toàn các segment chỉ chứa dấu phẩy/chấm/kỹ thuật."""
        mock_seg = SimpleNamespace(start=0.0, end=2.2, text="，", words=[])
        res = DubbingTranscriber._split_segment_by_sentences(mock_seg)
        self.assertEqual(len(res), 0)

    def test_concurrent_transcribe_dual_stream(self):
        """Kiểm tra luồng song song Dual-Stream Video OCR & Faster-Whisper ASR."""
        from unittest.mock import patch
        from src.core.engines.dubbing.video_ocr_engine import VideoOCREngine

        mock_ocr_segs = [
            {"id": 0, "start": 1.0, "end": 3.0, "text_origin": "王鹏展那把电烫棒", "duration": 2.0}
        ]
        mock_asr_segs = [
            {"id": 0, "start": 0.9, "end": 3.1, "text_origin": "王朋展那把电烫棒", "duration": 2.2}
        ]

        progress_calls = []

        def fake_cb(cur, tot, pct):
            progress_calls.append(pct)

        with patch.object(DubbingTranscriber, "extract_audio_from_video", return_value="dummy.wav"), \
             patch.object(VideoOCREngine, "extract_subtitles_from_video", return_value=mock_ocr_segs) as mock_ocr, \
             patch.object(DubbingTranscriber, "_run_whisper_asr", return_value=mock_asr_segs) as mock_asr:

            # Tạo file dummy tạm thời để pass os.path.exists(media_path) tự nhiên không cần mock global
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
                tf.write(b"0" * 20000)
                temp_vid_path = tf.name

            try:
                fused = DubbingTranscriber.transcribe(
                    media_path=temp_vid_path,
                    use_ocr=True,
                    progress_callback=fake_cb,
                )

                # Đảm bảo cả OCR và ASR đều được gọi trong ThreadPool
                mock_ocr.assert_called_once()
                mock_asr.assert_called_once()

                # Kết quả được dung hợp: Lấy chữ chuẩn từ OCR (王鹏展) thay vì từ ASR (王朋展)
                self.assertEqual(len(fused), 1)
                self.assertEqual(fused[0]["text_origin"], "王鹏展那把电烫棒")
            finally:
                import os
                if os.path.exists(temp_vid_path):
                    os.remove(temp_vid_path)


if __name__ == "__main__":
    unittest.main()

