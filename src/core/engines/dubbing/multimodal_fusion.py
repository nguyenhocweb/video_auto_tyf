import re
import logging
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz
from src.core.engines.dubbing.hallucination_filter import is_hallucinated_segment

logger = logging.getLogger("multimodal_fusion")


class MultimodalFusionEngine:
    """
    Tầng Dung Hợp Đa Phương Thức (Multi-Modal Fusion Engine):
    - Kết hợp đồng thời Thị giác Máy tính (Video OCR) và Thính giác (Audio ASR - Whisper).
    - Lấy chữ Hán từ OCR làm Chân lý Tuyệt đối (Ground Truth), triệt tiêu lỗi đồng âm/nghe nhầm.
    - Lấy mốc thời gian từ ASR để dóng hàng chuẩn xác theo khẩu hình miệng của nhân vật.
    - Tái tạo câu trọn vẹn ngữ nghĩa (Semantic Stitching) trước khi chuyển sang LLM dịch.
    """

    @classmethod
    def stitch_consecutive_ocr_fragments(
        cls, ocr_segments: List[Dict[str, Any]], max_gap_sec: float = 0.65, max_len: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Gom các mảnh câu vụn vặt do chữ nhấp nháy trên màn hình thành câu trọn vẹn ngữ nghĩa.
        Ví dụ: '人都死了2000' + '多年了还有意识' -> '人都死了2000多年了还有意识'
        """
        if not ocr_segments:
            return []

        stitched: List[Dict[str, Any]] = []
        curr = dict(ocr_segments[0])
        sentence_end_punc = re.compile(r"[。！？!?；;]$")

        for next_seg in ocr_segments[1:]:
            curr_text = curr.get("text_origin", "").strip()
            next_text = next_seg.get("text_origin", "").strip()
            gap = next_seg["start"] - curr["end"]
            combined_len = len(curr_text) + len(next_text)
            combined_dur = next_seg["end"] - curr["start"]

            # Điều kiện ghép câu:
            # 1. Khoảng cách thời gian ngắn (<= 0.65s)
            # 2. Câu hiện tại chưa có dấu chấm hết câu
            # 3. Một trong 2 vế bị ngắn (<= 7 ký tự) hoặc kết thúc bằng dấu phẩy (bị cắt vụn)
            # 4. Tổng độ dài không vượt quá 22 chữ và thời lượng <= 5.5s
            is_fragment = len(curr_text) <= 7 or len(next_text) <= 7 or curr_text.endswith((",", "，", "、"))
            can_stitch = (
                gap <= max_gap_sec
                and is_fragment
                and not sentence_end_punc.search(curr_text)
                and combined_len <= max_len
                and combined_dur <= 5.5
                and curr_text != next_text
                and not (curr_text in next_text or next_text in curr_text)
            )

            if can_stitch:
                curr["text_origin"] = f"{curr_text}{next_text}"
                curr["end"] = next_seg["end"]
                curr["duration"] = round(curr["end"] - curr["start"], 2)
            else:
                stitched.append(curr)
                curr = dict(next_seg)

        stitched.append(curr)
        return stitched

    @classmethod
    def fuse(
        cls,
        ocr_segments: List[Dict[str, Any]],
        asr_segments: List[Dict[str, Any]],
        total_duration: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Dung hợp đồng thời danh sách OCR và ASR thành danh sách phụ đề chuẩn xác duy nhất.
        """
        # Bước 1: Tiền xử lý tái tạo câu hoàn chỉnh từ OCR
        clean_ocr = cls.stitch_consecutive_ocr_fragments(ocr_segments)
        logger.info(f"Fusion: OCR thô {len(ocr_segments)} -> OCR tái tạo câu {len(clean_ocr)}.")

        fused: List[Dict[str, Any]] = []
        used_asr_indices = set()

        # Bước 2: Dóng hàng OCR với ASR (OCR giữ chữ gốc, ASR tinh chỉnh timeline khẩu hình)
        for ocr in clean_ocr:
            ocr_start = float(ocr["start"])
            ocr_end = float(ocr["end"])
            ocr_text = ocr["text_origin"].strip()

            best_asr_idx = None
            best_overlap = 0.0

            for a_idx, asr in enumerate(asr_segments):
                if a_idx in used_asr_indices:
                    continue
                a_start = float(asr["start"])
                a_end = float(asr["end"])

                # Tính thời gian giao thoa (overlap)
                overlap_start = max(ocr_start, a_start)
                overlap_end = min(ocr_end, a_end)
                overlap_dur = max(0.0, overlap_end - overlap_start)

                if overlap_dur > best_overlap:
                    best_overlap = overlap_dur
                    best_asr_idx = a_idx

            final_start = ocr_start
            final_end = ocr_end

            if best_asr_idx is not None and best_overlap >= 0.3:
                matched_asr = asr_segments[best_asr_idx]
                used_asr_indices.add(best_asr_idx)
                # Tinh chỉnh nhẹ timeline theo âm thanh nếu chênh lệch <= 0.8s
                a_start = float(matched_asr["start"])
                a_end = float(matched_asr["end"])
                if abs(a_start - ocr_start) <= 0.8:
                    final_start = min(ocr_start, a_start)
                if abs(a_end - ocr_end) <= 0.8:
                    final_end = max(ocr_end, a_end)

            fused.append({
                "start": round(final_start, 2),
                "end": round(final_end, 2),
                "duration": round(final_end - final_start, 2),
                "text_origin": ocr_text,
                "text_translated": "",
                "source": "ocr_groundtruth",
            })

        # Bước 3: Thu nạp các đoạn thoại ASR thực tế không có chữ trên màn hình (Unsubtitled Audio)
        for a_idx, asr in enumerate(asr_segments):
            if a_idx in used_asr_indices:
                continue

            a_start = float(asr["start"])
            a_end = float(asr["end"])
            a_dur = round(a_end - a_start, 2)
            a_text = asr.get("text_origin", "").strip()

            # Kiểm tra xem có giao thoa với bất kỳ đoạn OCR nào đã thêm không
            is_covered = any(
                max(0.0, min(f["end"], a_end) - max(f["start"], a_start)) >= 0.45
                for f in fused
            )
            if is_covered:
                continue

            # Kiểm tra và đào thải ảo giác Whisper trên nhạc nền BGM
            no_speech = asr.get("no_speech_prob")
            if is_hallucinated_segment(a_text, a_dur, no_speech_prob=no_speech):
                logger.info(f"Fusion gạt bỏ ảo giác ASR không có chữ trên màn hình: '{a_text}' ({a_dur}s)")
                continue

            # Nếu là lời thoại thật sự (không có phụ đề trên màn hình)
            fused.append({
                "start": round(a_start, 2),
                "end": round(a_end, 2),
                "duration": a_dur,
                "text_origin": a_text,
                "text_translated": "",
                "source": "asr_voiceover",
            })

        # Bước 4: Sắp xếp theo thứ tự thời gian và giải quyết xung đột timeline
        fused.sort(key=lambda x: x["start"])

        # Chuẩn hóa lại ID và loại trừ va chạm mốc thời gian
        result: List[Dict[str, Any]] = []
        for idx, item in enumerate(fused):
            if result:
                prev = result[-1]
                # Nếu câu sau đè lên câu trước, cắt mốc end của câu trước
                if prev["end"] > item["start"]:
                    if item["start"] - prev["start"] >= 0.4:
                        prev["end"] = item["start"]
                        prev["duration"] = round(prev["end"] - prev["start"], 2)
                    else:
                        continue  # Bỏ qua nếu bị đè quá sát

            item["id"] = len(result)
            result.append(item)

        logger.info(f"Dung hợp hoàn tất: Kết xuất {len(result)} câu thoại chuẩn xác cho toàn bộ video.")
        return result
