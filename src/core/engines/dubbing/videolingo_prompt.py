import re
from typing import List, Optional, Dict, Any


def extract_terms_and_context(all_texts: List[str]) -> Dict[str, Any]:
    """
    Kỹ thuật VideoLingo Step 4.1: Phân tích thể loại và trích xuất bảng thuật ngữ/đại từ xưng hô toàn cục.
    Khóa cố định phong cách dịch cho toàn bộ video, chống phân mảnh cách gọi giữa các đoạn.
    """
    joined_sample = " ".join(all_texts[:80])

    # 1. Nhận diện thể loại tác phẩm
    ancient_score = len(
        re.findall(
            r"(?:陛下|皇上|师[父傅兄弟妹]|本座|妖|魔|仙|宗门|江湖|大侠|弟子|神医|夫人|将军|老夫|老祖|晚辈|祖师|道长|贫道|天师|尸变|雷法)",
            joined_sample,
        )
    )
    action_score = len(re.findall(r"(?:老大|大哥|兄弟|警官|手下|堂口|混混|帮派|干掉|弄死)", joined_sample))

    if ancient_score >= 2:
        genre = "Cổ trang / Tiên hiệp / Kiếm hiệp"
        pronouns_rule = "Ta - Ngươi, Huynh - Đệ, Sư phụ - Đồ nhi, Bổn tọa, Tỷ muội, Nàng - Chàng. CẤM 'Tôi - Bạn'."
    elif action_score >= 2:
        genre = "Hành động / Giới ngầm / Đô thị giang hồ"
        pronouns_rule = "Đại ca - Em, Mày - Tao, Tôi - Ông/Cậu. CẤM dịch '老大' thành 'ông trùm' (phải gọi là 'Đại ca')."
    else:
        genre = "Đời sống / Phim ngắn kịch tính"
        pronouns_rule = "Xưng hô tự nhiên theo quan hệ đời thường (Tôi - Cậu/Anh/Em). CẤM dịch máy rập khuôn."

    # 2. Bảng chuyển ngữ tên riêng & từ ngữ cốt lõi (Locked Glossary)
    locked_terms: Dict[str, str] = {
        "幕穴": "Lăng mộ",
        "墓穴": "Lăng mộ",
        "蛮雷咒": "Mạn Lôi Chú",
        "祖师": "Tổ sư",
        "居士": "Cư sĩ",
        "贫道": "Bần đạo",
        "天师": "Thiên sư",
        "龙虎山": "Long Hổ Sơn",
        "张道陵": "Trương Đạo Lăng",
        "五雷神霄": "Ngũ Lôi Thần Tiêu",
        "青微雷法": "Thanh Vi Lôi pháp",
        "天心正法": "Thiên Tâm Chính Pháp",
        "老大": "Đại ca",
        "小米": "Tiểu Mễ",
        "大伯": "Bác cả",
        "二伯": "Bác hai",
        "万山群岛": "Quần đảo Vạn Sơn",
        "钱二": "Tiền Nhị",
    }

    return {
        "genre": genre,
        "pronouns_rule": pronouns_rule,
        "locked_terms": locked_terms,
    }


def build_videolingo_prompt(
    texts: List[str],
    durations: Optional[List[float]] = None,
    context: Optional[Dict[str, Any]] = None,
    prev_lines: Optional[List[str]] = None,
) -> str:
    """
    Xây dựng prompt dịch thuật phụ đề điện ảnh: Đầy đủ ý nghĩa, tự nhiên, chống ảo giác.
    Có Sliding Window Context kế thừa ngữ cảnh mạch phim của các câu trước.
    """
    indexed_lines = []
    for i, text in enumerate(texts):
        indexed_lines.append(f"LINE_{i}: {text}")

    joined_input = "\n".join(indexed_lines)

    genre_desc = ""
    pronouns_desc = ""
    terms_desc = ""
    prev_context_desc = ""

    if prev_lines:
        clean_prev = [p.strip() for p in prev_lines[-4:] if p.strip()]
        if clean_prev:
            prev_context_desc = "CÁC CÂU THOẠI LIỀN TRƯỚC (Dùng để nối liền mạch cảm xúc & xưng hô):\n" + "\n".join(f"- {p}" for p in clean_prev) + "\n\n"

    if context:
        if context.get("genre"):
            genre_desc = f"Bối cảnh thể loại: {context['genre']}.\n"
        if context.get("pronouns_rule"):
            pronouns_desc = f"Quy tắc xưng hô: {context['pronouns_rule']}.\n"
        if context.get("locked_terms"):
            pairs = [
                f"{k} -> {v}"
                for k, v in context["locked_terms"].items()
                if any(k in t for t in texts)
            ]
            if pairs:
                terms_desc = "Thuật ngữ bắt buộc: " + ", ".join(pairs) + ".\n"

    return (
        "Vai trò: Biên kịch dịch thoại điện ảnh Trung -> Việt khẩu ngữ tự nhiên.\n"
        f"{genre_desc}"
        f"{pronouns_desc}"
        f"{terms_desc}"
        f"{prev_context_desc}"
        "QUY TẮC BẮT BUỘC:\n"
        "1. Nếu câu gốc vô nghĩa, lặp từ hoặc tạp âm nhạc nền BGM -> Trả về: LINE_x: [SKIP]\n"
        "2. CHỈ TRẢ VỀ DUY NHẤT danh sách trong khối phân tách, cấm mọi lời giải thích, cấm Note/SároNote:\n"
        "--- NỘI DUNG ĐÃ DỊCH ---\n"
        "LINE_0: \"<câu thoại ngắn gọn>\"\n"
        "LINE_1: [SKIP]\n"
        "--- HẾT NỘI DUNG ĐÃ DỊCH ---\n\n"
        f"Kịch bản cần dịch:\n{joined_input}\n\n"
        "Bản dịch tiếng Việt:"
    )
