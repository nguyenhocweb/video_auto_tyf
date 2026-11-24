import os
import re
import html
import logging
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from src.core.engines.dubbing.qwen_translator import QwenInProcessTranslator
from src.core.engines.dubbing.videolingo_prompt import extract_terms_and_context
from src.core.utils.text_sanitizer import clean_subtitle_text, is_ai_boilerplate, is_length_hallucination

logger = logging.getLogger("dubbing_translator")

_VN_ACCENT_PATTERN = re.compile(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]", re.IGNORECASE)
_EN_WORDS_PATTERN = re.compile(
    r"\b(the|is|are|am|was|were|be|been|being|have|has|had|will|would|shall|should|could|might|must|"
    r"you|your|yours|him|his|she|her|hers|it|its|they|them|their|theirs|we|our|ours|my|mine|me|"
    r"this|that|these|those|what|which|who|whom|whose|when|where|why|how|"
    r"just|now|here|there|then|play|child|children|boss|girl|boy|people|"
    r"tree|run|walk|eat|drink|sleep|head|heads|hand|hands|eye|eyes|door|house|home|room|"
    r"fast|slow|enough|today|tomorrow|tonight|yesterday|thing|things|father|mother|brother|sister|"
    r"apple|apples|poison|poisonous|kill|die|dead|death|stop|wait|help|please|thank|thanks|sorry|"
    r"hello|notify|rest|pick|tell|everyone|back|give|take|look|stare|see|watch|get|got|let|"
    r"say|said|know|knew|think|thought|come|came|went|good|bad|big|small|world)\b",
    re.IGNORECASE,
)


def is_suspicious_or_non_vietnamese(text: str) -> bool:
    """Kiểm tra văn bản có bị lọt tiếng Anh, sót chữ Hán, nhãn thời lượng hoặc không phải tiếng Việt."""
    if not text or not text.strip():
        return True

    # 1. Chứa chữ Hán hoặc chữ Nhật
    if re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", text):
        return True

    # 2. Chứa nhãn kỹ thuật thời lượng
    if re.search(r"\b(?:Thời lượng|Duration|LINE_)\b", text, re.IGNORECASE):
        return True

    # 3. Chứa từ vựng tiếng Anh
    if _EN_WORDS_PATTERN.search(text):
        return True

    # 4. Nếu không có bất kỳ dấu tiếng Việt nào mà có từ 2 từ Latinh trở lên
    has_accents = bool(_VN_ACCENT_PATTERN.search(text))
    if not has_accents:
        latin_words = re.findall(r"\b[a-zA-Z]{2,}\b", text)
        if len(latin_words) >= 2:
            return True

    return False


class DubbingTranslator:
    """Engine dịch thuật phụ đề bằng LLM ngữ cảnh điện ảnh (Tuyệt đối không dùng Google Translate thô)."""

    @classmethod
    def translate_segments(
        cls,
        segments: List[Dict[str, Any]],
        source_lang: str = "zh-CN",
        target_lang: str = "vi",
        batch_size: int = 25,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        groq_keys: Optional[List[Dict[str, Any]]] = None,
        gemini_keys: Optional[List[Dict[str, Any]]] = None,
        on_key_used: Optional[Callable[[str, bool], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Dịch danh sách các segments phụ đề qua LLM Cinematic có nhận thức ngữ cảnh phim."""
        if not segments:
            return []

        # VideoLingo Step 4.1: Khóa bảng thuật ngữ và nhận diện phong cách xưng hô cho toàn bộ video
        all_origin_texts = [s.get("text_origin", "").strip() for s in segments if s.get("text_origin")]
        video_context = extract_terms_and_context(all_origin_texts)

        updated_segments = []
        total_count = len(segments)
        recent_translations: List[str] = []

        for i in range(0, total_count, batch_size):
            batch_slice = segments[i : i + batch_size]
            batch_texts = [s.get("text_origin", "").strip() for s in batch_slice]
            batch_durations = [
                float(s.get("duration", 0) or (float(s.get("end", 0)) - float(s.get("start", 0))))
                for s in batch_slice
            ]

            translated_batch = QwenInProcessTranslator.translate_batch(
                texts=batch_texts,
                source_lang=source_lang,
                target_lang=target_lang,
                groq_keys=groq_keys,
                gemini_keys=gemini_keys,
                on_key_used=on_key_used,
                durations=batch_durations,
                context=video_context,
                prev_lines=recent_translations[-4:] if recent_translations else None,
            )

            for seg, trans_text in zip(batch_slice, translated_batch):
                seg_copy = dict(seg)
                raw_trans = str(trans_text or "").strip()
                # 1. Nếu LLM đánh dấu [SKIP] hoặc kết quả rỗng do lọc ảo giác -> bỏ qua ngay
                if not raw_trans or re.search(r"\[\s*SKIP\s*\]", raw_trans, re.I):
                    continue

                clean_trans = clean_subtitle_text(html.unescape(raw_trans))
                if not clean_trans:
                    continue

                origin_text = seg.get("text_origin", "").strip()
                # 2. Nếu câu gốc chứa từ khóa ảo giác âm nhạc -> bỏ qua
                from src.core.engines.dubbing.hallucination_filter import _MUSIC_HALLUCINATIONS
                if _MUSIC_HALLUCINATIONS.search(origin_text):
                    continue

                # 3. Nếu câu dịch dính ảo giác AI / boilerplate -> bỏ qua luôn, TUYỆT ĐỐI KHÔNG retry
                if is_ai_boilerplate(clean_trans):
                    continue

                # 4. Chỉ retry câu đơn nếu câu dịch bị lọt tiếng Anh hoặc độ dài bất thường
                if is_suspicious_or_non_vietnamese(clean_trans) or is_length_hallucination(origin_text, clean_trans):
                    if origin_text and len(origin_text) >= 2:
                        try:
                            retried = QwenInProcessTranslator.translate_single_line(
                                origin_text,
                                groq_keys=groq_keys,
                                gemini_keys=gemini_keys,
                            )
                            clean_retried = clean_subtitle_text(retried)
                            if clean_retried and not is_ai_boilerplate(clean_retried):
                                clean_trans = clean_retried
                        except Exception as r_err:
                            logger.debug(f"Retry câu đơn '{origin_text[:20]}' thất bại ({r_err}), giữ bản dịch ban đầu.")

                # Xóa sạch mọi chữ Hán hoặc nhãn kỹ thuật còn sót lại
                clean_trans = re.sub(r"[\u4e00-\u9fff]", "", clean_trans).strip()
                clean_trans = re.sub(r"\[\s*Thời lượng[^\s\]]*\s*\]", "", clean_trans, flags=re.I).strip()

                # Tinh chỉnh khẩu ngữ điện ảnh VideoLingo: Triệt tiêu dịch máy ngô nghê & ảo giác
                clean_trans = re.sub(r"\b(?:bạn\s+)?(?:hiển\s+thị|biểu\s+thị)\b", "", clean_trans, flags=re.I)
                clean_trans = re.sub(r"^(?:bạn\s+)?(?:hiển\s+thị|biểu\s+thị)$", "", clean_trans, flags=re.I)
                clean_trans = re.sub(r"\b(xiaomi)\b", "Tiểu Mễ", clean_trans, flags=re.I)
                clean_trans = re.sub(r"\b(ông lớn|ông trùm|sếp lớn|big boss)\b", "đại ca", clean_trans, flags=re.I)
                clean_trans = re.sub(r"\b(sự phát triển của bạn|sự phát triển của ngươi)\b", "xem ngươi lớn ra sao", clean_trans, flags=re.I)
                clean_trans = re.sub(r"\bchờ đợi sự phát triển\b", "chờ xem ngươi lớn thế nào", clean_trans, flags=re.I)
                clean_trans = re.sub(r"\btiêu thụ quả cay\b", "ăn quả", clean_trans, flags=re.I)
                clean_trans = re.sub(r"\btiêu thụ quả\b", "ăn quả", clean_trans, flags=re.I)
                clean_trans = re.sub(r"\bchôn cất người lính\b", "chôn cất đồng đội", clean_trans, flags=re.I)
                clean_trans = re.sub(r"\s+", " ", clean_trans).strip()

                # Nếu câu dịch rỗng hoặc chỉ còn dấu câu, lập tức bỏ qua phân đoạn ảo giác này
                if not clean_trans or re.fullmatch(r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]+$", clean_trans):
                    continue

                seg_copy["text_translated"] = clean_trans
                updated_segments.append(seg_copy)
                recent_translations.append(clean_trans)

            if progress_callback:
                progress_callback(min(i + batch_size, total_count), total_count)

        # Lọc bỏ triệt để các câu phụ đề dịch lặp lại liên tiếp do lỗi nhạc nền
        final_segments: List[Dict[str, Any]] = []
        last_clean = ""
        repeat_count = 0
        for seg in updated_segments:
            txt = (seg.get("text_translated") or "").strip().lower()
            if txt and txt == last_clean:
                repeat_count += 1
                if repeat_count >= 2:
                    continue
            else:
                last_clean = txt
                repeat_count = 1
            final_segments.append(seg)

        for idx, s in enumerate(final_segments):
            s["id"] = idx

        return final_segments

    @classmethod
    def _format_timestamp_srt(cls, seconds: float) -> str:
        """Đổi số giây sang định dạng thời gian SRT (HH:MM:SS,mmm)."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int(round((seconds - int(seconds)) * 1000))
        return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

    @classmethod
    def _format_timestamp_ass(cls, seconds: float) -> str:
        """Đổi số giây sang định dạng thời gian ASS (H:MM:SS.cc)."""
        hrs = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centis = int(round((seconds - int(seconds)) * 100))
        return f"{hrs:01d}:{mins:02d}:{secs:02d}.{centis:02d}"

    @classmethod
    def export_srt(cls, segments: List[Dict[str, Any]], output_path: str, use_translated: bool = True) -> str:
        """Xuất danh sách segments sang file phụ đề định dạng .SRT (Tuyệt đối không lọt chữ tiếng Trung)."""
        lines = []
        out_idx = 1
        for seg in segments:
            start_str = cls._format_timestamp_srt(float(seg["start"]))
            end_str = cls._format_timestamp_srt(float(seg["end"]))
            if use_translated:
                text = seg.get("text_translated", "").strip()
                text = re.sub(r"[\u4e00-\u9fff]", "", text).strip()
            else:
                text = seg.get("text_origin", "").strip()

            clean_text = clean_subtitle_text(text)
            clean_text = re.sub(r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]+$", "", clean_text).strip()
            if clean_text:
                lines.append(f"{out_idx}\n{start_str} --> {end_str}\n{clean_text}\n")
                out_idx += 1

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return output_path

    @classmethod
    def export_ass(
        cls,
        segments: List[Dict[str, Any]],
        output_path: str,
        font_size: int = 31,
        use_translated: bool = True,
        margin_v: int = 100,
    ) -> str:
        """
        Xuất file phụ đề ASS chuẩn mẫu Reels: Chữ vàng nghệ tươi sáng, viền đen dày nổi bật.
        - PrimaryColour: &H0000E6FF (Vàng nghệ rực rỡ BGR).
        - OutlineColour: &H00000000 (Viền đen 4.2px chống chìm chữ).
        - BackColour: &H80000000 (Bóng đổ Shadow 2.5px).
        - margin_v: Căn chữ đè chuẩn xác 100% vào giữa dải phụ đề gốc đã làm mờ.
        - font_size: Mặc định 31 (Fontsize = 62px trên canvas 1080p), to rõ nét chuẩn điện ảnh/Reels.
        """
        actual_size = max(24, int(font_size * 2))
        header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{actual_size},&H0000E6FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4.2,2.5,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for seg in segments:
            start_str = cls._format_timestamp_ass(float(seg["start"]))
            end_str = cls._format_timestamp_ass(float(seg["end"]))
            if use_translated:
                text = seg.get("text_translated", "").strip()
                text = re.sub(r"[\u4e00-\u9fff]", "", text).strip()
            else:
                text = seg.get("text_origin", "").strip()

            clean_text = clean_subtitle_text(text.replace("\n", " ").replace("{", "").replace("}", ""))
            clean_text = re.sub(r"[\u4e00-\u9fff]", "", clean_text).strip()
            clean_text = re.sub(r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]+$", "", clean_text).strip()
            if clean_text:
                events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{clean_text}")

        content = header + "\n".join(events) + "\n"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        return output_path
