import re
import logging
from typing import List, Dict, Any, Tuple
from rapidfuzz import fuzz

logger = logging.getLogger("dubbing_qa_gate")


class AutomatedQAGate:
    """
    Cổng Kiểm Soát Chất Lượng Phụ Đề Tự Động (Automated QA Gate):
    - Đánh giá chất lượng dịch thuật và bóc tách trên thang điểm 10 theo tiêu chuẩn Netflix/Senior.
    - Quét sạch toàn bộ các câu ảo giác rác tiếng Việt bị sót (vd: 'Tôi sẽ giúp bạn giải thích').
    - Phát hiện các khoảng trống mất sub bất thường (> 20s) để cảnh báo và tự động ghi log.
    - Chặn đứng hiện tượng câu dịch bị lặp vô nghĩa 3 lần liên tiếp.
    """

    _BANNED_VIETNAMESE_PATTERNS = [
        re.compile(r"tôi sẽ giúp bạn", re.IGNORECASE),
        re.compile(r"chỉ cần tôi giúp", re.IGNORECASE),
        re.compile(r"để tôi để giúp", re.IGNORECASE),
        re.compile(r"tôi sẽ giúp giúp", re.IGNORECASE),
        re.compile(r"tôi sẽ chịu ti[êệ]u", re.IGNORECASE),
        re.compile(r"giúp bạn giải thích", re.IGNORECASE),
        re.compile(r"giúp giải thích các nhân vật", re.IGNORECASE),
        re.compile(r"đăng ký kênh", re.IGNORECASE),
        re.compile(r"nhấn chuông thông báo", re.IGNORECASE),
        re.compile(r"^(?:đến từ\s*)+[\.\,\!\?\s]*$", re.IGNORECASE),
        re.compile(r"\b(?:đến từ\s+){2,}đến từ\b", re.IGNORECASE),
        re.compile(r"^(?:đồng thời\s*)+[\.\,\!\?\s]*$", re.IGNORECASE),
        re.compile(r"^(?:nếu chịu không có đến|đến một đến)[\.\,\!\?\s\w]*$", re.IGNORECASE),
        re.compile(r"(\b\w+\b)(?:[\s,、]+(?:\1|để\s+\1)){2,}", re.IGNORECASE),
        re.compile(r"^[\.\,\s\-\_\–\—\…]+$", re.IGNORECASE),
    ]

    @classmethod
    def audit_and_clean_subtitles(
        cls, segments: List[Dict[str, Any]], total_duration: float = 0.0
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Kiểm định và làm sạch danh sách phụ đề đã dịch.
        Trả về: (cleaned_segments, audit_report)
        """
        if not segments:
            return [], {
                "score": 0.0,
                "is_approved": False,
                "total_lines": 0,
                "cleaned_lines": 0,
                "hallucinations_detected": 0,
                "long_gaps": [],
                "note": "Danh sách phụ đề rỗng hoàn toàn.",
            }

        cleaned: List[Dict[str, Any]] = []
        hallucinations_count = 0
        repetition_count = 0
        long_gaps = []

        # 1. Phát hiện các khoảng trống dài bất thường
        prev_end = 0.0
        for seg in segments:
            gap = seg["start"] - prev_end
            if gap >= 22.0:
                long_gaps.append({
                    "start": round(prev_end, 2),
                    "end": round(seg["start"], 2),
                    "duration": round(gap, 2),
                })
            prev_end = seg["end"]

        # 2. Quét lọc ảo giác và câu rác trong text_translated
        consecutive_same_count = 1
        last_trans = ""

        for seg in segments:
            item = dict(seg)
            vi_text = item.get("text_translated", "").strip()

            # Kiểm tra mẫu từ cấm
            is_banned = False
            for pat in cls._BANNED_VIETNAMESE_PATTERNS:
                if pat.search(vi_text):
                    is_banned = True
                    break

            if is_banned:
                hallucinations_count += 1
                logger.warning(f"QA Gate phát hiện và gạt bỏ câu dịch rác: '{vi_text}' ({item['start']}s -> {item['end']}s)")
                item["text_translated"] = ""
                vi_text = ""

            # Kiểm tra lặp câu dịch >= 3 lần liên tiếp
            if vi_text and last_trans:
                sim = fuzz.ratio(vi_text.lower(), last_trans.lower())
                if sim >= 88:
                    consecutive_same_count += 1
                    if consecutive_same_count >= 3:
                        repetition_count += 1
                        logger.warning(f"QA Gate phát hiện lặp câu dịch >= 3 lần: '{vi_text}'")
                        item["text_translated"] = ""
                        vi_text = ""
                else:
                    consecutive_same_count = 1
            else:
                consecutive_same_count = 1

            last_trans = vi_text
            cleaned.append(item)

        # 3. Tính điểm chất lượng chuẩn Senior (Quality Score trên thang điểm 10.0)
        total_count = len(cleaned)
        valid_trans_count = sum(1 for s in cleaned if s.get("text_translated", "").strip())
        trans_ratio = valid_trans_count / total_count if total_count > 0 else 0.0

        base_score = trans_ratio * 7.0
        # Kiểm tra mật độ phụ đề (Subtitle Density): Video > 45s phải có mật độ thoại tối thiểu
        density_warning = False
        if total_duration > 45.0:
            expected_min = total_duration / 12.0
            if valid_trans_count < expected_min * 0.35:
                # Mất sub nghiêm trọng (như 258s chỉ có 6 câu) -> Phạt nặng điểm số phản ánh đúng thực tế
                base_score = min(base_score, 3.5)
                density_warning = True

        if not density_warning:
            if hallucinations_count == 0 and repetition_count == 0:
                base_score += 3.0
            else:
                base_score -= min(3.0, (hallucinations_count + repetition_count) * 0.6)

        # Trừ điểm nếu có khoảng trống quá dài
        if long_gaps:
            base_score -= min(3.0, len(long_gaps) * 0.9)

        final_score = max(1.0, min(10.0, round(base_score, 1)))
        is_approved = final_score >= 6.5 and valid_trans_count >= 1 and not density_warning

        report = {
            "score": final_score,
            "is_approved": is_approved,
            "total_lines": total_count,
            "valid_translated_lines": valid_trans_count,
            "hallucinations_removed": hallucinations_count,
            "repetitions_removed": repetition_count,
            "long_gaps_count": len(long_gaps),
            "long_gaps": long_gaps,
        }

        logger.info(
            f"QA Gate hoàn tất: Điểm {final_score}/10 | Hợp lệ: {valid_trans_count}/{total_count} câu | "
            f"Đã loại bỏ {hallucinations_count} ảo giác, {repetition_count} lặp."
        )
        return cleaned, report

