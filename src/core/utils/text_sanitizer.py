import re

__all__ = [
    "clean_subtitle_text",
    "clean_text_for_tts",
    "optimize_text_for_pace",
    "is_ai_boilerplate",
    "is_length_hallucination",
]



def clean_subtitle_text(text: str) -> str:
    """
    Chuẩn hóa và thanh lọc triệt để văn bản phụ đề và câu thoại TTS.
    - Xóa sạch triệt để mọi nhãn thời lượng, ngân sách từ ((nói 1.5s, TỐI ĐA 5 TỪ), [Thời lượng: 2.2s]) ở mọi vị trí.
    - Cắt bỏ mọi tiền tố danh sách, số thứ tự, gạch đầu dòng (- [[5]] - , 1. , - [0] -).
    - Cắt bỏ mọi tag định danh (<<<LINE_5>>>, [[[5]]], [[5]], [5], (5)).
    - Cắt bỏ các nhãn thừa như [Tôi - bạn], [Cổ trang], (Giải thích), Tôi - bạn: ...
    - Loại bỏ preamble giải thích từ LLM (Dịch kịch bản sang tiếng Việt...).
    """
    if not text:
        return ""

    t = text.strip().strip("\"'`")

    # 0. Nếu văn bản có bọc trong dấu ngoặc kép -> Trích xuất nội dung bên trong dấu ngoặc kép trước
    quote_match = re.search(r'["“]([^"”]+)["”]', text)
    if quote_match and len(quote_match.group(1).strip()) >= 1:
        t = quote_match.group(1).strip()

    # Cắt bỏ mọi ghi chú / Note / Giải thích do LLM tự ý chú thích ở đầu hoặc đuôi câu
    t = re.sub(r"(?:^|\s+|\b)\S*(?:note|lưu\s*ý|ghi\s*chú|ps|p\/s)\s*[\:\-].*$", "", t, flags=re.IGNORECASE).strip()
    t = re.split(r"(?:\b|\S*)(?:Note|Lưu\s*ý|Ghi\s*chú|PS|P\/S)\s*[\:\-]", t, flags=re.IGNORECASE)[0].strip()
    t = re.sub(r"\s*[\(\[][^\)\]]*?(?:note|lưu ý|ghi chú|quy tắc|chuyển đổi)[^\)\]]*?[\)\]]", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"(?:Tên\s+đã\s+được\s+chuyển\s+đổi|chuyển\s+đổi\s+sang\s+tiếng\s+việt|theo\s+quy\s+tắc\s+đã).*$", "", t, flags=re.IGNORECASE).strip()

    # 0.1. Nếu LLM đánh dấu [SKIP] hoặc câu bị bỏ qua
    if re.search(r"\[\s*SKIP\s*\]", t, re.IGNORECASE) or t.upper() == "SKIP":
        return ""

    # 1. Bỏ dòng mở đầu / giải thích của LLM
    if re.match(r"^(?:Dịch kịch bản|Dưới đây là|Bản dịch|Kịch bản|Here is|Translation)[\:\s\-]*", t, re.IGNORECASE):
        return ""

    # 2. Xóa triệt để mọi nhãn thời lượng, ngân sách từ ở BẤT CỨ VỊ TRÍ NÀO trong chuỗi
    t = re.sub(r"[\(\[]\s*(?:nói\s*(?:trong\s*)?[\d\.]+s|thời lượng|duration|tối đa\s*\d+\s*từ)[^\)\]]*[\)\]]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:Thời lượng|Duration)\s*[\:\=]\s*[\d\.]+\s*(?:s|giây|seconds)?\b", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:nói\s*(?:trong\s*)?[\d\.]+s|tối đa\s*\d+\s*từ)\b", "", t, flags=re.IGNORECASE)

    # 3. Xóa tag định danh dạng <<<LINE_...>>> hoặc <<<...>>> ở mọi vị trí
    t = re.sub(r"<<<[^>]+>>>", "", t)

    # 4. Vòng lặp bóc tách nhiều tầng ngoặc, số thứ tự và gạch đầu dòng ở đầu câu
    for _ in range(4):
        # Bỏ tag ngoặc vuông lồng nhau: [[5]], [[[5]]], [Tôi - bạn]
        t = re.sub(r"^\[+[^\]]+\]+\s*", "", t).strip()
        # Bỏ ngoặc tròn: (5), (Tôi - bạn)
        t = re.sub(r"^\([^)]+\)\s*", "", t).strip()
        # Bỏ gạch đầu dòng, dấu sao, số thứ tự, dấu hai chấm ở đầu câu: "- ", "* ", "1. ", "- 5 - "
        t = re.sub(r"^[\-\*\•\:\s\d\.\)]+[\-\:\s]*", "", t).strip()

    # 5. Lọc bỏ các tiền tố xưng hô thừa nếu còn sót lại ở đầu câu
    t = re.sub(r"^(?:Cổ trang|Hiện đại|Tôi\s*[\-\:]\s*bạn|Ta\s*[\-\:]\s*ngươi)[\:\s\-]*", "", t, flags=re.IGNORECASE).strip()

    # 6. Kiểm tra nếu sau khi lọc chỉ toàn dấu ngoặc, số, rác thời lượng hoặc dấu câu
    t = re.sub(r"\s+", " ", t).strip()
    if re.fullmatch(r"^[\d\.\s\-\:\,\[\]\(\)\<\>\|\/，。！？、；：“”‘’（）~～\•\*\_]*$", t):
        return ""

    # 7. Nếu toàn bộ chuỗi chỉ là nhãn xưng hô thuần túy thì hủy bỏ
    if re.fullmatch(r"^(?:Tôi\s*[\-\:]\s*bạn|Ta\s*[\-\:]\s*ngươi|Cổ trang|Hiện đại)$", t, flags=re.IGNORECASE):
        return ""

    return t


def is_ai_boilerplate(text: str) -> bool:
    """Kiểm tra và loại bỏ triệt để các câu từ chối, giải thích hoặc chào hỏi của AI."""
    if not text:
        return True
    low = text.lower()
    forbidden = [
        "dạ, tôi", "tôi có thể giúp", "tôi không thể dịch", "hiểu lầm về ngữ cảnh",
        "chuyên gia ngôn ngữ", "đoạn văn đã được", "câu thoại tiếng việt", "đại từ xưng hô",
        "định dạng ngôn ngữ", "quy tắc này", "dưới đây là lời dịch", "chúc bạn",
        "<câu thoại", "<bản dịch", "câu dịch tiếng việt", "bản dịch tiếng việt",
        "tuyệt đối cấm", "tôi muốn tìm hiểu", "giới thiệu cho tôi", "bộ phim ngắn kịch tính",
        "chào bạn, tôi muốn", "thảo luận về các phương pháp", "kỹ năng học tập",
        "ở đây, chúng ta", "ở đây, tôi muốn", "ở đây, tôi đã", "tôi mới không muốn",
        "tôi đã nói trước", "ngày sau, một cô gái", "cố gắng dịch câu",
        "dự án hay", "bạn có thể", "hãy cho tôi biết", "tôi sẵn sàng",
        "tôi sẽ giúp bạn giải thích", "giúp bạn để giải thích", "giúp bạn giải thích nhé",
        "tôi nói cảm hứng", "đến để giết để giải thích", "đến để giải thích",
        "tôi sẽ chịu tiêu", "tôi sẽ chịu tiệu", "chịu tiêu để giải thích", "chịu tiệu để giải thích",
        "chịu tiêu", "chịu tiệu", "không muốn giải thích", "chuyên gia của chương trình",
        "tên đã được chuyển đổi", "chuyển đổi sang tiếng việt", "theo quy tắc đã",
        "theo quy tắc", "lưu ý:", "ghi chú:", "note:", "saronote", "saro",
        "nội dung đã dịch", "hết nội dung", "tên đã dịch", "tên kênh", "tên tác giả",
    ]
    if any(s in low for s in forbidden):
        return True
    if re.search(
        r"\b(?:bạn có thể|giới thiệu cho tôi|tôi muốn tìm hiểu|dự án hay|bạn muốn|tôi có thể giúp|chào bạn|"
        r"tôi sẽ giúp bạn|giúp bạn để giải thích|giúp bạn giải thích|tôi nói cảm hứng|đến để giết để giải thích|"
        r"chịu\s*ti[êệ]u|ti[êệ]u\s*để\s*giải\s*thích|không\s*muốn\s*giải\s*thích)\b",
        low,
    ):
        return True
    return False


def is_length_hallucination(zh_text: str, vi_text: str) -> bool:
    """Phát hiện ảo giác nếu câu gốc ngắn mà bản dịch dài lê thê bất thường (chặn đoạn văn chatbot)."""
    if not zh_text or not vi_text:
        return False
    zh_len = len(re.sub(r"\s+", "", zh_text))
    vi_words = len(vi_text.strip().split())
    if zh_len <= 5 and vi_words > 10:
        return True
    if zh_len <= 10 and vi_words > 15:
        return True
    if zh_len <= 16 and vi_words > 24:
        return True
    if zh_len <= 25 and vi_words > 36:
        return True
    if zh_len <= 40 and vi_words > 55:
        return True
    return False


def clean_text_for_tts(text: str) -> str:
    """Làm sạch văn bản đầu vào cho TTS, loại bỏ emoji, tag xưng hô và ký tự lạ gây drop audio."""
    if not text:
        return ""
    clean = clean_subtitle_text(text)
    clean = re.sub(r"[\u4e00-\u9fff]+", "", clean)
    _num_map = {"0": "không", "1": "một", "2": "hai", "3": "ba", "4": "bốn", "5": "năm", "6": "sáu", "7": "bảy", "8": "tám", "9": "chín", "10": "mười"}
    clean = re.sub(r"\b(\d{1,2})\b", lambda m: _num_map.get(m.group(1), m.group(1)), clean)
    _acronyms = {r"\bJS\b": "cương thi", r"\bWeChat\b": "tin nhắn", r"\bDouyin\b": "mạng xã hội", r"\bvcl\b": "quá", r"\bvãi\b": "thật sự"}
    for pat, repl in _acronyms.items():
        clean = re.sub(pat, repl, clean, flags=re.IGNORECASE)
    clean = re.sub(r"([A-Za-zÀ-ỹ\s]{3,20}),\s*\1", r"\1", clean)
    clean = re.sub(r"[^\w\s\.,!\?\'\"\-\–]", " ", clean, flags=re.UNICODE)
    clean = re.sub(r"[\,\;\:\-\–\~]+$", ".", clean).strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    if clean and len(re.sub(r"[^\w]", "", clean)) <= 2:
        clean = f"{clean}..."
    return clean


def optimize_text_for_pace(text: str, available_dur_sec: float) -> str:
    """Tối ưu câu thoại súc tích chuẩn điện ảnh khớp với thời lượng phát âm (~3.5 từ/giây)."""
    if not text or available_dur_sec <= 0:
        return text
    words = text.split()
    comfortable_max_words = max(3, int(available_dur_sec * 3.5))
    if len(words) <= comfortable_max_words:
        return text
    condensed = text
    replacements = [
        (r"\bở tại nơi này\b", "tại đây"), (r"\bngay tại thời điểm này\b", "lúc này"),
        (r"\btại thời điểm hiện tại\b", "bây giờ"), (r"\bchẳng phải là .*? hay sao\b", "chẳng phải sao"),
        (r"\bchính là vì lý do\b", "bởi vì"), (r"\bthực sự là rất\b", "rất"),
        (r"\bhoàn toàn không có\b", "không có"), (r"\bkhông thể nào mà\b", "không thể"),
        (r"\bcho dù là như thế nào\b", "dù thế nào"), (r"\bcó thể được xem là\b", "chính là"),
        (r"\bkhông cần phải lo lắng\b", "đừng lo"), (r"\bkhông cần lo lắng\b", "đừng lo"),
        (r"\bđợi cho đến khi\b", "chờ khi"), (r"\bsau khi chúng ăn chúng ta\b", "khi chúng ăn"),
        (r"\bnăng lượng và sức mạnh\b", "sức mạnh"), (r"\bnăng lượng và năng lượng\b", "năng lượng"),
        (r"\bthay đổi thành hình dạng\b", "biến thành"), (r"\bngười bảo vệ tự tin\b", "người bảo vệ"),
        (r"\bchôn cất người lính\b", "chôn cất"), (r"\btrở thành con người\b", "thành người"),
        (r"\bchúng ta đã không ăn\b", "ta chưa ăn"), (r"\btrong thời gian này\b", "dạo này"),
        (r"\btiêu thụ quả cay\b", "ăn quả"), (r"\btiêu thụ quả\b", "ăn quả"), (r"\btiêu thụ\b", "ăn"),
        (r"\bkhông có ai ở gần nơi này\b", "quanh đây không có ai"), (r"\btôi cũng không hiểu\b", "tôi không hiểu"),
        (r"\bnhất định phải\b", "phải"), (r"^(thực ra thì|thế nhưng mà|bởi vì là|nói tóm lại là|cho nên là)\s+", ""),
    ]
    for pattern, repl in replacements:
        condensed = re.sub(pattern, repl, condensed, flags=re.IGNORECASE).strip()
    if len(condensed.split()) > comfortable_max_words:
        secondary = [
            (r"\bchúng ta\b", "ta"), (r"\bbọn họ\b", "họ"), (r"\bbọn chúng\b", "chúng"),
            (r"\bcủa chúng ta\b", ""), (r"\bcủa mình\b", ""), (r"\bcủa bạn\b", ""), (r"\bcủa tôi\b", ""),
            (r"\bđang là một\b", "là"), (r"\bđang một\b", "là"), (r"\bđể mà\b", "để"),
            (r"\bnhưng mà\b", "nhưng"), (r"\bvậy thì\b", "vậy"),
        ]
        for pattern, repl in secondary:
            condensed = re.sub(pattern, repl, condensed, flags=re.IGNORECASE).strip()
    return re.sub(r"\s+", " ", condensed).strip()

