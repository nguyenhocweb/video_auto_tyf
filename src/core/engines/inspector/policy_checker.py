import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("policy_checker")

POLICY_KEYWORD_RULES: Dict[str, Dict[str, Any]] = {
    # 1. Bạo lực & Chết chóc (Mức độ nghiêm trọng cao)
    "chết": {"cat": "violence", "lvl": "high", "repl": "hẹo / bay màu / sang thế giới khác"},
    "giết": {"cat": "violence", "lvl": "high", "repl": "xử lý / hạ gục / tiễn đi xa"},
    "tự tử": {"cat": "violence", "lvl": "high", "repl": "nghĩ quẩn / buông xuôi"},
    "đâm": {"cat": "violence", "lvl": "high", "repl": "tác động vật lý"},
    "máu": {"cat": "violence", "lvl": "medium", "repl": "siro đỏ / huyết"},
    "súng": {"cat": "violence", "lvl": "high", "repl": "đồ chơi bắn tỉa / công cụ"},
    "bắn": {"cat": "violence", "lvl": "high", "repl": "nhả đạn / khai hỏa"},
    "chém": {"cat": "violence", "lvl": "high", "repl": "vung tay / so tài"},
    "đánh nhau": {"cat": "violence", "lvl": "medium", "repl": "so găng / tranh luận gay gắt"},

    # 2. Cờ bạc & Tài chính nhạy cảm (Dễ bị khóa kênh)
    "tài xỉu": {"cat": "gambling", "lvl": "high", "repl": "bộ môn xí ngầu may rủi"},
    "cá độ": {"cat": "gambling", "lvl": "high", "repl": "dự đoán vui"},
    "cờ bạc": {"cat": "gambling", "lvl": "high", "repl": "trò đỏ đen"},
    "đổi thưởng": {"cat": "gambling", "lvl": "high", "repl": "nhận quà tri ân"},
    "nổ hũ": {"cat": "gambling", "lvl": "high", "repl": "trúng thưởng lớn"},
    "kiếm tiền": {"cat": "finance", "lvl": "warning", "repl": "tạo thêm thu nhập / kiếm ngân lượng"},
    "làm giàu nhanh": {"cat": "finance", "lvl": "high", "repl": "phát triển tài chính"},

    # 3. Nội dung 18+ & Khiêu dâm
    "18+": {"cat": "nsfw", "lvl": "high", "repl": "nội dung người lớn"},
    "khiêu dâm": {"cat": "nsfw", "lvl": "high", "repl": "nội dung nhạy cảm"},
    "khoả thân": {"cat": "nsfw", "lvl": "high", "repl": "trang phục thiếu vải"},
    "lộ clip": {"cat": "nsfw", "lvl": "high", "repl": "video rò rỉ"},
    "kích dục": {"cat": "nsfw", "lvl": "high", "repl": "nhạy cảm"},

    # 4. Lừa đảo & Quảng cáo quá đà
    "cam kết 100%": {"cat": "scam", "lvl": "medium", "repl": "hỗ trợ tối đa"},
    "chữa dứt điểm": {"cat": "scam", "lvl": "high", "repl": "hỗ trợ cải thiện rõ rệt"},
    "thuốc trị bách bệnh": {"cat": "scam", "lvl": "high", "repl": "thảo dược bổ trợ"},
    "lừa đảo": {"cat": "scam", "lvl": "medium", "repl": "chiêu trò trục lợi"},

    # 5. Chửi thề & Ngôn từ thù ghét
    "đm": {"cat": "profanity", "lvl": "high", "repl": "ôi trời"},
    "vcl": {"cat": "profanity", "lvl": "medium", "repl": "quá đỉnh / bất ngờ"},
    "chó đẻ": {"cat": "profanity", "lvl": "high", "repl": "kẻ xấu tính"},
    "thằng ngu": {"cat": "profanity", "lvl": "medium", "repl": "người ngây thơ"},
}


class PolicyChecker:
    """Engine soi từ ngữ vi phạm chính sách cộng đồng TikTok/FB/YouTube."""

    @classmethod
    def check_text(cls, text: str) -> Dict[str, Any]:
        """Quét văn bản phụ đề/kịch bản tìm từ khóa vi phạm và gợi ý từ thay thế."""
        if not text or not text.strip():
            return {
                "is_safe": True,
                "safety_score": 100,
                "total_violations": 0,
                "violations": [],
                "rewritten_text": "",
                "summary": "Nội dung trống, an toàn 100%.",
            }

        violations: List[Dict[str, Any]] = []
        lowered = text.lower()
        rewritten = text

        # Sắp xếp từ dài trước từ ngắn để tránh match đè
        sorted_keywords = sorted(POLICY_KEYWORD_RULES.keys(), key=lambda k: len(k), reverse=True)

        for kw in sorted_keywords:
            rule = POLICY_KEYWORD_RULES[kw]
            # Match theo word boundary hoặc cụm từ
            pattern = re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
            matches = list(pattern.finditer(lowered))

            if matches:
                for m in matches:
                    violations.append({
                        "word": kw,
                        "category": rule["cat"],
                        "level": rule["lvl"],
                        "start": m.start(),
                        "end": m.end(),
                        "replacement": rule["repl"],
                    })
                # Thay thế trong văn bản gợi ý
                first_repl = rule["repl"].split(" / ")[0]
                rewritten = pattern.sub(first_repl, rewritten)

        # Tính toán điểm an toàn (Safety Score: 0 - 100)
        penalty = 0
        for v in violations:
            lvl = v.get("level")
            if lvl == "high":
                penalty += 25
            elif lvl == "medium":
                penalty += 12
            else:
                penalty += 5

        safety_score = max(0, 100 - penalty)
        is_safe = safety_score >= 80

        if safety_score == 100:
            summary = "Tuyệt vời! Không phát hiện từ khóa nhạy cảm nào. Video an toàn 100% để đăng tải."
        elif safety_score >= 80:
            summary = f"Khá an toàn ({safety_score}/100). Phát hiện {len(violations)} từ khóa cảnh báo nhẹ, nên dùng từ thay thế."
        else:
            summary = f"CẢNH BÁO ({safety_score}/100): Phát hiện {len(violations)} từ vi phạm nặng (nguy cơ bóp tương tác/gậy bản quyền cao)."

        return {
            "is_safe": is_safe,
            "safety_score": safety_score,
            "total_violations": len(violations),
            "violations": violations,
            "rewritten_text": rewritten,
            "summary": summary,
        }

    @classmethod
    def check_image_skin_tone(cls, image_path: str) -> Dict[str, Any]:
        """Quét tỷ lệ vùng da người trên ảnh để cảnh báo nguy cơ hở hang 18+."""
        try:
            import cv2
            import numpy as np

            img = cv2.imread(image_path)
            if img is None:
                return {"is_safe": True, "skin_ratio": 0.0, "warning": "Không thể nạp ảnh."}

            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            # Ngưỡng màu da người chuẩn trong không gian HSV
            lower_skin = np.array([0, 20, 70], dtype=np.uint8)
            upper_skin = np.array([25, 255, 255], dtype=np.uint8)

            mask = cv2.inRange(hsv, lower_skin, upper_skin)
            skin_pixels = cv2.countNonZero(mask)
            total_pixels = img.shape[0] * img.shape[1]
            skin_ratio = round(float(skin_pixels) / float(total_pixels), 3)

            is_safe = skin_ratio < 0.40
            warning = ""
            if skin_ratio >= 0.50:
                warning = f"Cảnh báo: Tỷ lệ da thịt chiếm {int(skin_ratio*100)}% khung hình, nguy cơ bị quét 18+ cao."
            elif skin_ratio >= 0.35:
                warning = f"Lưu ý: Tỷ lệ da thịt {int(skin_ratio*100)}% ở mức trung bình, chú ý góc chụp."

            return {
                "is_safe": is_safe,
                "skin_ratio": skin_ratio,
                "skin_percent": round(skin_ratio * 100, 1),
                "warning": warning,
            }
        except Exception as e:
            logger.warning(f"Lỗi kiểm tra vùng da ảnh: {e}")
            return {"is_safe": True, "skin_ratio": 0.0, "warning": ""}

