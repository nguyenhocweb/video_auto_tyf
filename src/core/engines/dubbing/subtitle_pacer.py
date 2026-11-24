import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger("subtitle_pacer")


class SubtitlePacer:
    """
    Bộ Phân Tách & Điều Phối Nhịp Phụ Đề Chuẩn Reels / TikTok (Progressive Subtitle Pacing):
    - Triệt tiêu hoàn toàn hiện tượng phụ đề nối dài 2-3 dòng gây rối mắt.
    - Tự động tách câu tại dấu chấm (.), hỏi (?), than (!), hoặc dấu phẩy (,) khi câu dài.
    - Đọc xong câu nào chuyển tiếp câu đó tức thì (đúng mốc thời lượng âm thanh).
    - Đảm bảo mỗi dòng phụ đề luôn ngắn gọn, thanh thoát trên 1 dòng duy nhất.
    """

    @classmethod
    def _split_text_into_clauses(cls, text: str) -> List[str]:
        """Tách một chuỗi dài thành các phân đoạn ngắn hơn theo dấu câu tự nhiên."""
        if not text:
            return []

        # 1. Ưu tiên tách theo dấu chấm, hỏi, than, ba chấm
        sentences = re.split(r"(?<=[\.\!\?…])\s+", text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        clauses: List[str] = []
        for s in sentences:
            # Nếu một câu vẫn quá dài (> 40 ký tự) và có dấu phẩy / chấm phẩy
            if len(s) > 40 and re.search(r"[,;，；]", s):
                # Tách tại dấu phẩy ở vị trí cân bằng
                comma_parts = re.split(r"(?<=[,;，；])\s*", s)
                comma_parts = [cp.strip() for cp in comma_parts if cp.strip()]

                # Gom lại nếu mẩu sau quá ngắn (< 18 ký tự) để tránh câu bị ngắt vụn
                merged_parts: List[str] = []
                temp = ""
                for part in comma_parts:
                    if not temp:
                        temp = part
                    elif len(temp) < 28 or len(part) < 18:
                        temp = f"{temp} {part}"
                    else:
                        merged_parts.append(temp)
                        temp = part
                if temp:
                    merged_parts.append(temp)

                clauses.extend(merged_parts if merged_parts else [s])
            else:
                clauses.append(s)

        return clauses

    @classmethod
    def pace_segments(
        cls, segments: List[Dict[str, Any]], max_chars: int = 38, min_dur_to_split: float = 2.4
    ) -> List[Dict[str, Any]]:
        """
        Duyệt danh sách segments đã dịch, tự động tách các câu dài thành các phân đoạn nhỏ 1 dòng.
        Phân bổ thời gian (start -> end) tỷ lệ thuận với số lượng ký tự/từ ngữ của từng phân đoạn.
        """
        if not segments:
            return []

        paced_segments: List[Dict[str, Any]] = []

        for seg in segments:
            text_vi = seg.get("text_translated", "").strip()
            total_dur = float(seg.get("duration", 0) or (float(seg.get("end", 0)) - float(seg.get("start", 0))))
            start_sec = float(seg["start"])
            end_sec = float(seg["end"])

            # Điều kiện tách câu:
            # 1. Thời lượng đủ dài (>= 2.4s)
            # 2. Độ dài văn bản vượt quá 38 ký tự hoặc chứa nhiều hơn 1 câu kết thúc bằng dấu chấm/hỏi/than
            has_multiple_sentences = bool(re.search(r"[\.\!\?…]\s+\S", text_vi))
            is_long_text = len(text_vi) > max_chars

            if total_dur >= min_dur_to_split and (has_multiple_sentences or is_long_text):
                sub_clauses = cls._split_text_into_clauses(text_vi)

                if len(sub_clauses) >= 2:
                    # Tính tổng trọng số độ dài để phân bổ thời gian
                    weights = [max(8, len(c)) for c in sub_clauses]
                    total_weight = sum(weights)

                    curr_start = start_sec
                    for idx, clause in enumerate(sub_clauses):
                        clause_ratio = weights[idx] / total_weight
                        clause_dur = round(total_dur * clause_ratio, 2)

                        # Đảm bảo mỗi phân đoạn có tối thiểu 0.9s
                        clause_dur = max(0.9, clause_dur)
                        clause_end = round(curr_start + clause_dur, 2)

                        # Giữ cho phân đoạn cuối không vượt quá end_sec ban đầu
                        if idx == len(sub_clauses) - 1:
                            clause_end = end_sec
                            clause_dur = round(clause_end - curr_start, 2)

                        sub_item = dict(seg)
                        sub_item["id"] = len(paced_segments)
                        sub_item["start"] = round(curr_start, 2)
                        sub_item["end"] = round(clause_end, 2)
                        sub_item["duration"] = round(clause_end - curr_start, 2)
                        sub_item["text_translated"] = clause

                        paced_segments.append(sub_item)
                        curr_start = clause_end
                    continue

            # Nếu câu ngắn hoặc không cần tách -> Giữ nguyên
            seg_copy = dict(seg)
            seg_copy["id"] = len(paced_segments)
            paced_segments.append(seg_copy)

        logger.info(
            f"SubtitlePacer: Tối ưu nhịp xuất hiện phụ đề từ {len(segments)} câu dài -> {len(paced_segments)} câu ngắn 1 dòng thanh thoát."
        )
        return paced_segments
