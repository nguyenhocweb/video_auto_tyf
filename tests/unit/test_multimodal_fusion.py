import unittest
from src.core.engines.dubbing.multimodal_fusion import MultimodalFusionEngine
from src.core.engines.dubbing.qa_gate import AutomatedQAGate


class TestMultimodalFusionAndQAGate(unittest.TestCase):
    """Bộ kiểm thử đơn vị cho Tầng Dung Hợp Đa Phương Thức & Automated QA Gate."""

    def test_semantic_sentence_stitching(self):
        """Kiểm tra tính năng ghép nối các mảnh phụ đề bị cắt vụn trên màn hình."""
        raw_ocr = [
            {"start": 10.0, "end": 11.2, "text_origin": "人都死了2000"},
            {"start": 11.4, "end": 12.8, "text_origin": "多年了还有意识"},
            {"start": 13.5, "end": 15.0, "text_origin": "不是说僵师都丧失人性的吗？"},
        ]
        stitched = MultimodalFusionEngine.stitch_consecutive_ocr_fragments(raw_ocr, max_gap_sec=0.65)
        self.assertEqual(len(stitched), 2)
        self.assertEqual(stitched[0]["text_origin"], "人都死了2000多年了还有意识")
        self.assertEqual(stitched[0]["start"], 10.0)
        self.assertEqual(stitched[0]["end"], 12.8)
        self.assertEqual(stitched[1]["text_origin"], "不是说僵师都丧失人性的吗？")

    def test_multimodal_fusion_ocr_groundtruth_and_hallucination_drop(self):
        """Kiểm tra dung hợp OCR và ASR: OCR giữ chữ gốc, ASR tinh chỉnh mốc, ASR ảo giác BGM bị drop."""
        ocr_segs = [
            {"start": 18.5, "end": 20.0, "text_origin": "老祖宗是晚辈不孝"},
            {"start": 20.1, "end": 22.0, "text_origin": "没有保护好您的幕穴"},
        ]
        # Whisper nghe nhầm chữ hoặc hallucinate ở 0s và dóng timeline ở 18s
        asr_segs = [
            {"start": 0.5, "end": 3.0, "text_origin": "只要我帮帮你", "no_speech_prob": 0.8},
            {"start": 18.2, "end": 19.8, "text_origin": "老祖宗是万倍不晓"},  # Nghe nhầm từ đồng âm
            {"start": 20.2, "end": 22.3, "text_origin": "没有保护好您的母穴"},  # Nghe nhầm từ đồng âm
        ]

        fused = MultimodalFusionEngine.fuse(ocr_segs, asr_segs)
        self.assertEqual(len(fused), 2)

        # Câu 1: Giữ 100% chữ chuẩn từ OCR ('老祖宗是晚辈不孝'), lấy timeline mở rộng từ ASR (18.2s)
        self.assertEqual(fused[0]["text_origin"], "老祖宗是晚辈不孝")
        self.assertAlmostEqual(fused[0]["start"], 18.2, places=1)

        # Câu 2: Giữ 100% chữ chuẩn từ OCR ('没有保护好您的幕穴')
        self.assertEqual(fused[1]["text_origin"], "没有保护好您的幕穴")

        # Câu ảo giác Whisper ở 0.5s ('只要我帮帮你') phải bị DROP hoàn toàn!
        all_texts = [f["text_origin"] for f in fused]
        self.assertNotIn("只要我帮帮你", all_texts)

    def test_qa_gate_removes_hallucinations_and_calculates_score(self):
        """Kiểm tra QA Gate tự động phát hiện và dọn sạch câu dịch rác."""
        dubbed_subs = [
            {"id": 0, "start": 0.5, "end": 2.5, "text_origin": "帮帮你", "text_translated": "Chỉ cần tôi giúp giúp bạn"},
            {"id": 1, "start": 3.0, "end": 4.5, "text_origin": "解释", "text_translated": "Tôi sẽ giúp bạn giải thích nhé"},
            {"id": 2, "start": 18.5, "end": 20.0, "text_origin": "老祖宗是晚辈不孝", "text_translated": "Tổ tông, đồ nhi bất hiếu!"},
            {"id": 3, "start": 20.1, "end": 22.0, "text_origin": "没有保护好您的幕穴", "text_translated": "Đã không bảo vệ được lăng mộ của Ngài!"},
        ]
        cleaned, report = AutomatedQAGate.audit_and_clean_subtitles(dubbed_subs)
        self.assertEqual(report["hallucinations_removed"], 2)
        # Hai câu đầu bị làm rỗng
        self.assertEqual(cleaned[0]["text_translated"], "")
        self.assertEqual(cleaned[1]["text_translated"], "")
        # Hai câu sau giữ nguyên vẹn
        self.assertEqual(cleaned[2]["text_translated"], "Tổ tông, đồ nhi bất hiếu!")
        self.assertEqual(cleaned[3]["text_translated"], "Đã không bảo vệ được lăng mộ của Ngài!")

    def test_subtitle_pacer_splits_long_multisentence_into_progressive_single_lines(self):
        """Kiểm tra SubtitlePacer tách câu dài 2 dòng thành các câu ngắn 1 dòng chuyển tiếp tuần tự."""
        from src.core.engines.dubbing.subtitle_pacer import SubtitlePacer
        long_sub = [{
            "id": 14,
            "start": 36.83,
            "end": 41.16,
            "duration": 4.33,
            "text_origin": "无关人等速速离去至于剩下的交给我来处理",
            "text_translated": "Những kẻ không liên quan hãy rời khỏi đây. Còn mấy tên kia, ta sẽ tự xử lý.",
        }]
        paced = SubtitlePacer.pace_segments(long_sub)
        self.assertEqual(len(paced), 2)
        # Câu 1
        self.assertEqual(paced[0]["text_translated"], "Những kẻ không liên quan hãy rời khỏi đây.")
        self.assertEqual(paced[0]["start"], 36.83)
        self.assertEqual(paced[0]["end"], 39.29)
        # Câu 2
        self.assertEqual(paced[1]["text_translated"], "Còn mấy tên kia, ta sẽ tự xử lý.")
        self.assertEqual(paced[1]["start"], 39.29)
        self.assertEqual(paced[1]["end"], 41.16)


if __name__ == "__main__":
    unittest.main()

