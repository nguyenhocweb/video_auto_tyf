import re
import logging
from typing import Optional, List, Dict, Any
from collections import Counter

logger = logging.getLogger("hallucination_filter")

# 1. Danh sách từ khóa metadata/quảng cáo/kênh truyền thông tự sinh của Whisper khi gặp BGM
_EXPLICIT_METADATA = re.compile(
    r"(?:"
    r"谢谢收看|感谢收看|感谢观看|谢谢观看|欢迎收看|欢迎观看|敬请期待|下集更精彩|下集预告|"
    r"关注我|请关注|求关注|点赞|请订阅|点赞关注|投币|收藏|转发|"
    r"字幕制作|字幕由|本字幕|字幕组|中文字幕|英文字幕|压制|听译|"
    r"微信|公众号|抖音|快手|B站|bilibili|优酷|爱奇艺|腾讯视频|"
    r"完结|未完待续|下一集|阿西吧"
    r")",
    re.IGNORECASE,
)

# 2. Cụm từ '显示' (như '你显示', '显示', '为您显示') - kinh điển của Whisper khi gặp nhạc nền
_DISPLAY_PATTERNS = re.compile(r"(?:你|为您|为你|请|画面)?显示")

# 3. Các cụm ảo giác giải mã âm thanh kinh điển của Whisper khi gặp BGM / SFX không có thoại
_MUSIC_HALLUCINATIONS = re.compile(
    r"(?:"
    r"我也来(?:帮[你您])?解释|来(?:帮[你您])?解释|帮你解释|解释吧|来解释|不想解释|"
    r"消受|我说灵感|说灵感|灵感来|来杀来解|杀来解|"
    r"我们也(?:可以)?去|头摸去|头摸一下|有过来|"
    r"^来自.*$|^来自(?:来自)+$|^(?:来自|从)+$"
    r")"
)

_PUNCTUATION_OR_GARBAGE = re.compile(
    r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]+$"
)


def _is_repeated_text(text: str) -> bool:
    """Kiểm tra lặp từ vô nghĩa do Whisper loop trên nhạc nền (VD: '暖和暖和' hoặc '啊啊啊')."""
    if len(text) < 4:
        return False
    if len(set(text)) == 1 and len(text) >= 3:
        return True
    for k in (2, 3, 4):
        if len(text) >= k * 2 and len(text) % k == 0:
            chunks = [text[i : i + k] for i in range(0, len(text), k)]
            if len(set(chunks)) == 1:
                return True
    return False


def is_hallucinated_segment(
    text: str, duration: float, no_speech_prob: Optional[float] = None
) -> bool:
    """
    Kiểm tra một phân đoạn nhận diện giọng nói có phải là ảo giác (Hallucination) do nhạc nền BGM hay không.
    - Triệt tiêu hoàn toàn thảm họa '你显示' (Bạn hiển thị) kéo dài hàng chục giây.
    - Triệt tiêu các ảo giác âm nhạc kinh điển của Whisper ('我也来帮你解释吧', '我说灵感').
    - Lọc bỏ các cụm từ đệm tự sinh của Whisper khi không có người nói.
    """
    clean_txt = (text or "").strip()
    if not clean_txt:
        return True

    # 1. Toàn dấu câu hoặc ký tự vô nghĩa
    if _PUNCTUATION_OR_GARBAGE.fullmatch(clean_txt):
        return True

    stripped_punct = re.sub(r"[\s，。！？、；：“”‘’（）~～\•\*\_]+", "", clean_txt)
    char_count = len(stripped_punct)
    if char_count == 0:
        return True

    # 2. Khớp cụm từ ảo giác '显示' / '你显示' (tối đa 8 ký tự)
    if _DISPLAY_PATTERNS.search(stripped_punct) and char_count <= 8:
        logger.info(f"Phát hiện và loại bỏ ảo giác '显示': '{clean_txt}' ({duration:.2f}s)")
        return True

    # 3. Khớp từ khóa metadata / quảng cáo tự sinh
    if _EXPLICIT_METADATA.search(stripped_punct):
        logger.info(f"Phát hiện và loại bỏ ảo giác metadata BGM: '{clean_txt}' ({duration:.2f}s)")
        return True

    # 3.1. Khớp ảo giác âm nhạc kinh điển của Whisper (như '我也来帮你解释吧', '我说灵感')
    if _MUSIC_HALLUCINATIONS.search(stripped_punct):
        logger.info(f"Phát hiện và loại bỏ ảo giác âm nhạc Whisper: '{clean_txt}' ({duration:.2f}s)")
        return True

    # 4. Lặp từ vô nghĩa do loop decoder Whisper
    if _is_repeated_text(stripped_punct):
        logger.info(f"Phát hiện lặp từ vô nghĩa: '{clean_txt}' ({duration:.2f}s)")
        return True

    # 5. No-speech probability quá cao (> 0.65)
    if no_speech_prob is not None and no_speech_prob > 0.65:
        logger.info(f"Loại bỏ phân đoạn no_speech_prob={no_speech_prob:.2f} > 0.65: '{clean_txt}'")
        return True

    # 6. Tỷ lệ ký tự / thời lượng bất thường (Vụ án '把这' 17.5s hoặc '暖和' 27.8s)
    if duration > 6.0 and char_count <= 2:
        logger.warning(
            f"Phát hiện ảo giác BGM thời lượng dài ({duration:.2f}s) chỉ có {char_count} chữ: '{clean_txt}'"
        )
        return True

    if duration >= 8.0 and (char_count / duration) < 0.35:
        logger.warning(
            f"Phát hiện mật độ âm thoại quá loãng ({char_count / duration:.2f} chars/s < 0.35): '{clean_txt}' ({duration:.2f}s)"
        )
        return True

    return False


def filter_repeated_hallucination_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Kỹ thuật lọc ảo giác chuỗi vòng lặp (Cross-Segment & Global Loop Squashing):
    - Triệt tiêu hoàn toàn thảm họa Whisper lặp lại cùng một câu (như '过来', '我说灵感') hàng chục lần.
    - Cắt bỏ chuỗi lặp liên tiếp >= 2 lần của cùng một câu thoại.
    - Lọc bỏ các câu ngắn lặp lại bất thường trên toàn bộ video (> 4 lần cho câu <= 6 chữ).
    """
    if not segments:
        return []

    def _norm(txt: str) -> str:
        return re.sub(r"[\s，。！？、；：“”‘’（）~～\•\*\_]+", "", txt or "").strip()

    # 1. Thống kê tần suất xuất hiện toàn cục của các câu thoại
    all_norms = [_norm(s.get("text_origin", "")) for s in segments]
    global_counts = Counter(n for n in all_norms if n)

    # 2. Lọc chuỗi lặp liên tiếp và lặp bất thường
    pruned: List[Dict[str, Any]] = []
    consecutive_text = ""
    consecutive_run = 0

    for seg in segments:
        norm = _norm(seg.get("text_origin", ""))
        if not norm:
            continue

        # Câu ngắn (<= 6 chữ) mà xuất hiện trên 4 lần trong video -> 99.9% là ảo giác vòng lặp Whisper
        if len(norm) <= 6 and global_counts[norm] >= 4:
            logger.warning(
                f"Loại bỏ câu thoại lặp bất thường toàn cục ({global_counts[norm]} lần): '{seg.get('text_origin')}'"
            )
            continue

        # Kiểm tra lặp liên tiếp
        if norm == consecutive_text:
            consecutive_run += 1
            if consecutive_run >= 2:
                logger.info(
                    f"Bỏ qua phân đoạn lặp liên tiếp lần thứ {consecutive_run}: '{seg.get('text_origin')}'"
                )
                continue
        else:
            consecutive_text = norm
            consecutive_run = 1

        pruned.append(seg)

    # Đánh lại ID cho danh sách phân đoạn sạch
    for idx, s in enumerate(pruned):
        s["id"] = idx

    return pruned
