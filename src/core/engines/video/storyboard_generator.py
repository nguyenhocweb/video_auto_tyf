import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from src.core.engines.video.storyboard_beat_library import generate_progressive_story_beats

logger = logging.getLogger("storyboard_generator")

# 1. Danh mục Phong Cách Hội Họa & DNA Nhân Vật (Art Style & Character DNA)
ART_STYLES: Dict[str, Dict[str, str]] = {
    "stickman": {
        "name": "Stickman Người Que (Mẫu video gốc)",
        "style_prefix": (
            "2D graphic storytime animation style, stick figure webcomic illustration, "
            "thick clean black outlines, cel-shaded, muted moody vintage dark grunge color palette, "
            "cinematic eerie lighting, 16:9 aspect ratio."
        ),
        "protagonist_dna": (
            "a minimalist stick figure character with a large white circular head, expressive cartoon eyes, "
            "messy shaggy black hair, wearing a black backwards snapback cap with a bold white skull emblem, "
            "thin black stick body wearing a black t-shirt"
        ),
        "companion_dna": (
            "a timid stick figure companion with a large white circular head, wearing a mustard yellow "
            "ribbed knit beanie hat and a thick dark grey wool scarf around the neck"
        ),
    },
    "modern_vector": {
        "name": "Flat Vector Hiện Đại (Modern Explainer / Infographic)",
        "style_prefix": (
            "modern 2D flat vector explainer art style, clean graphic novel illustration, "
            "vibrant minimalist color palette, subtle textured gradients, dramatic focal lighting, "
            "professional conceptual infographic storytelling aesthetic, 16:9 aspect ratio."
        ),
        "protagonist_dna": (
            "a relatable modern young character with expressive emotive eyes, stylish casual smart attire, "
            "thoughtful body language reflecting human ambition, inner struggle, and growth"
        ),
        "companion_dna": (
            "an insightful conversational mentor or symbolic reflection figure with neat spectacles and empathetic posture"
        ),
    },
    "anime": {
        "name": "Anime Điện Ảnh (Makoto Shinkai)",
        "style_prefix": (
            "modern anime film style, highly detailed digital painting, dramatic cinematic lighting, "
            "vibrant colors, depth of field, 16:9 aspect ratio, masterpiece quality."
        ),
        "protagonist_dna": (
            "an adventurous young anime boy with dark messy hair, curious eyes, wearing a casual jacket"
        ),
        "companion_dna": (
            "a friendly anime companion wearing a warm hoodie, expressive anime features"
        ),
    },
    "comic_webtoon": {
        "name": "Truyện Tranh Webtoon Đời Thường",
        "style_prefix": (
            "clean modern manhwa webtoon style, warm pastel lighting, soft cel-shading, "
            "expressive character design, 16:9 aspect ratio."
        ),
        "protagonist_dna": (
            "a charismatic young person in casual streetwear with stylish hair"
        ),
        "companion_dna": (
            "a cute expressive friend with round spectacles and comfortable knit sweater"
        ),
    },
    "doodle_sketch": {
        "name": "Doodle Phác Thảo Trắng Đen (Hand-Drawn Sketch)",
        "style_prefix": (
            "hand-drawn monochrome ink sketch, expressive line art, cross-hatching shadows, "
            "white textured paper background, minimal artistic story illustration, 16:9 aspect ratio."
        ),
        "protagonist_dna": (
            "a charming minimalist hand-drawn cartoon figure with simple expressive ink lines and dynamic poses"
        ),
        "companion_dna": (
            "a small hand-drawn companion figure with humorous expressive doodles"
        ),
    },
}

# 2. Danh mục Thể Loại Nội Dung & Giọng Kể (Genre & Narrative Tone)
GENRES: Dict[str, Dict[str, str]] = {
    "knowledge_sharing": {
        "name": "Kể Chuyện & Chia Sẻ Kiến Thức (Triết Lý, Tâm Lý, Bài Học)",
        "narrative_guide": (
            "Tập trung phân tích tâm lý, chia sẻ bài học cuộc sống, sự thật ngầm hiểu (insights). "
            "Dẫn dắt: Đặt vấn đề / áp lực vô hình -> Thực tế trớ trêu -> Bước ngoặt nhận thức mới -> Đúc kết triết lý sâu sắc."
        ),
    },
    "horror_mystery": {
        "name": "Bí Ẩn, Gay Cấn, Kinh Dị (Suspense & Mystery)",
        "narrative_guide": (
            "Không khí kỳ bí, căng thẳng hồi hộp. "
            "Dẫn dắt: Khởi đầu tĩnh mịch -> Phát hiện điều bất thường -> Đi sâu vào hiểm nguy -> Manh mối rợn người -> Bí mật hé lộ."
        ),
    },
    "motivation": {
        "name": "Truyền Cảm Hứng & Động Lực (Inspirational)",
        "narrative_guide": (
            "Ý chí kiên định và vượt qua nghịch cảnh. "
            "Dẫn dắt: Cảm giác bế tắc -> Ngọn lửa ý chí bên trong -> Từng hành động nhỏ bền bỉ -> Đột phá và chạm tới thành công."
        ),
    },
    "daily_comedy": {
        "name": "Hài Hước, Đời Thường, Châm Biếm (Comedy Slice of Life)",
        "narrative_guide": (
            "Tình huống trớ trêu quen thuộc hàng ngày. "
            "Dẫn dắt: Dự định ngây thơ -> Thực tế va đập cười ra nước mắt -> Tình huống éo le tăng tiến -> Cái kết bất ngờ hài hước."
        ),
    },
}

STYLE_PRESETS = ART_STYLES  # Alias tương thích ngược


class StoryboardScriptGenerator:
    """Tự động sinh kịch bản phân cảnh và câu Prompt vẽ ảnh chuẩn DNA."""

    @classmethod
    def get_art_style(cls, key: str) -> Dict[str, str]:
        legacy_map = {
            "stickman_horror": "stickman",
            "knowledge_sharing": "modern_vector",
            "cinematic_anime": "anime",
            "comic_chill": "comic_webtoon",
        }
        resolved = legacy_map.get(key, key)
        return ART_STYLES.get(resolved, ART_STYLES["stickman"])

    @classmethod
    def get_genre(cls, key: str) -> Dict[str, str]:
        legacy_map = {
            "stickman_horror": "horror_mystery",
            "knowledge_sharing": "knowledge_sharing",
            "cinematic_anime": "horror_mystery",
            "comic_chill": "daily_comedy",
        }
        resolved = legacy_map.get(key, key)
        return GENRES.get(resolved, GENRES["knowledge_sharing"])

    @classmethod
    def get_style_preset(cls, style_key: str) -> Dict[str, str]:
        return cls.get_art_style(style_key)

    @classmethod
    async def generate_script(
        cls,
        topic: str,
        art_style: str = "stickman",
        genre: str = "knowledge_sharing",
        scene_count: int = 8,
        gemini_api_key: Optional[str] = None,
        style: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Tương thích ngược nếu client cũ truyền 'style'
        effective_art = style or art_style
        effective_genre = genre
        if style:
            if "horror" in style:
                effective_genre = "horror_mystery"
            elif "knowledge" in style:
                effective_genre = "knowledge_sharing"

        art_info = cls.get_art_style(effective_art)
        genre_info = cls.get_genre(effective_genre)
        scene_count = max(3, min(60, scene_count))

        # Thử gọi Gemini qua SDK nếu có key
        if gemini_api_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_api_key)
                prompt = (
                    f"Bạn là chuyên gia biên kịch video hoạt hình triệu view (phong cách kênh Vẽ Xàm Xí / Khoa học & Đời sống dí dỏm).\n"
                    f"Hãy sáng tác kịch bản gồm ĐÚNG {scene_count} phân cảnh (scenes) cho chủ đề: '{topic}'.\n\n"
                    f"TIÊU CHUẨN XƯNG HÔ & VĂN PHONG KỂ CHUYỆN (BẮT BUỘC):\n"
                    f"1. Xưng hô: Tự nhiên, gần gũi ('Bạn', 'chúng ta', 'họ'). Tuyệt đối CẤM giọng giảng đạo lý sáo rỗng hoặc văn phong sách vở.\n"
                    f"2. Giọng điệu: Hóm hỉnh, tò mò, bất ngờ, đối thoại mượt mà như một người bạn kể chuyện cuốn hút.\n"
                    f"3. Cấu trúc lôi cuốn (Hook & Twist):\n"
                    f"   - Cảnh 1-2 (Hook): Mở đầu bằng câu hỏi tò mò ('Bạn có bao giờ thắc mắc... khi chưa có... không?').\n"
                    f"   - Cảnh tiếp: Bẻ lái bất ngờ, hé lộ sự thật thú vị ('Thực tế thì...', 'Hóa ra là...').\n"
                    f"   - Cảnh cuối: Đúc kết dí dỏm, ấn tượng ('Chứ không phải... đâu nhé!').\n"
                    f"4. Độ dài mỗi cảnh: PHẢI CỰC KỲ NGẮN GỌN (8-14 từ, đọc 2.5s - 3.5s). Tuyệt đối không kéo dài lê thê.\n\n"
                    f"QUY TẮC PROMPT VẼ ẢNH (prompt_en):\n"
                    f"- Bắt đầu bằng: {art_info['style_prefix']}\n"
                    f"- Minh họa TRỰC DIỆN cho câu nói (nói nằm đất -> vẽ nằm đất; nói về giấc mơ -> vẽ bong bóng giấc mơ).\n"
                    f"- Giữ đúng DNA nhân vật chính: {art_info['protagonist_dna']}.\n\n"
                    f"YÊU CẦU: Trả về duy nhất một mảng JSON thuần túy (không kèm markdown) gồm đúng {scene_count} phần tử:\n"
                    f"[\n"
                    f"  {{\n"
                    f"    \"scene_idx\": 1,\n"
                    f"    \"narration\": \"Lời dẫn cực ngắn 8-12 từ...\",\n"
                    f"    \"prompt_en\": \"Full detailed English image prompt starting with the style prefix...\",\n"
                    f"    \"estimated_duration\": 2.8\n"
                    f"  }}\n"
                    f"]"
                )
                from src.core.config import settings
                model_name = getattr(settings, "GEMINI_MODEL_ID", None) or "gemini-2.0-flash"
                try:
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name,
                            contents=prompt,
                        ),
                        timeout=40.0,
                    )
                except Exception:
                    # Fallback thu model 1.5 neu 2.0 ban quyen chua bat
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model="gemini-1.5-flash",
                            contents=prompt,
                        ),
                        timeout=30.0,
                    )
                raw_text = (getattr(resp, "text", "") or "").strip()
                if not raw_text:
                    raise ValueError("Gemini trả về nội dung rỗng")
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                parsed = json.loads(raw_text)
                if isinstance(parsed, list) and len(parsed) >= 2:
                    if len(parsed) < scene_count:
                        needed = scene_count - len(parsed)
                        extra_beats = generate_progressive_story_beats(
                            topic, art_info, genre_info, scene_count
                        )
                        for eb in extra_beats[len(parsed):scene_count]:
                            parsed.append(eb)
                    return parsed[:scene_count]
            except Exception as ge:
                logger.warning(f"Lỗi khi gọi Gemini sinh kịch bản: {ge}. Sử dụng kịch bản mẫu thông minh.")

        return generate_progressive_story_beats(topic, art_info, genre_info, scene_count)
