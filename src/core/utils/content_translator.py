import re
import urllib.parse
import asyncio
import logging
from typing import Tuple, List, Dict, Any, Optional
import httpx

logger = logging.getLogger("content_translator")


class ContentTranslator:
    """Tiện ích dịch thuật tiêu đề và mô tả video Douyin/tiếng Trung sang tiếng Việt."""

    @classmethod
    async def _get_active_keys(cls) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Tải danh sách Groq & Gemini keys đang hoạt động từ MongoDB."""
        groq_keys, gemini_keys = [], []
        try:
            from src.modules.creator.dubbing.groq_keys_repository import GroqKeysMongoRepository
            from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository

            groq_keys = await GroqKeysMongoRepository().get_active_keys()
            gemini_keys = await GeminiKeysMongoRepository().get_active_keys()
        except Exception as e:
            logger.debug(f"Không thể tải AI keys từ database: {e}")
        return groq_keys, gemini_keys

    @classmethod
    async def _translate_via_rest(cls, text: str) -> str:
        """Dự phòng qua REST API (MyMemory và Google Translate) nếu LLM không khả dụng."""
        if not text:
            return ""

        # 1. MyMemory Translation API (miễn phí, ổn định cao)
        try:
            encoded = urllib.parse.quote(text)
            url_mm = f"https://api.mymemory.translated.net/get?q={encoded}&langpair=zh|vi"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url_mm)
                if resp.status_code == 200:
                    data = resp.json()
                    trans_text = str(data.get("responseData", {}).get("translatedText", "")).strip()
                    if trans_text and not re.search(r"[\u4e00-\u9fff]", trans_text):
                        return trans_text
        except Exception as mm_err:
            logger.debug(f"MyMemory fallback error: {mm_err}")

        # 2. Google Translate REST
        try:
            encoded = urllib.parse.quote(text)
            url_gt = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=vi&dt=t&q={encoded}"
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url_gt, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    data = resp.json()
                    chunks = [c[0] for c in data[0] if c and len(c) > 0 and c[0]]
                    trans = "".join(chunks).strip()
                    if trans and not re.search(r"[\u4e00-\u9fff]", trans):
                        return trans
        except Exception:
            pass

        return text

    @classmethod
    async def translate_text(cls, text: str) -> str:
        """Dịch một đoạn văn bản ngắn tiếng Trung sang tiếng Việt."""
        if not text or not str(text).strip():
            return ""

        cleaned = str(text).strip()
        cleaned = re.sub(r"@\S+", "", cleaned).strip()
        if not cleaned:
            return ""

        groq_keys, gemini_keys = await cls._get_active_keys()
        if groq_keys or gemini_keys:
            try:
                from src.core.engines.dubbing.qwen_translator import QwenInProcessTranslator
                from src.core.utils.text_sanitizer import clean_subtitle_text, is_ai_boilerplate

                results = await asyncio.to_thread(
                    QwenInProcessTranslator.translate_batch,
                    texts=[cleaned],
                    source_lang="zh",
                    target_lang="vi",
                    groq_keys=groq_keys,
                    gemini_keys=gemini_keys,
                )
                if results and results[0]:
                    clean = clean_subtitle_text(results[0])
                    if clean and not is_ai_boilerplate(clean) and not re.search(r"[\u4e00-\u9fff]", clean):
                        return clean
            except Exception as e:
                logger.warning(f"Lỗi dịch LLM: {e}")

        return await cls._translate_via_rest(cleaned)

    @classmethod
    async def translate_title_and_caption(
        cls, title: str, caption: str
    ) -> Tuple[str, str]:
        """
        Dịch đồng thời tiêu đề và mô tả:
        - Tách hashtags khỏi caption.
        - Dịch batch qua Gemini/Groq LLM để đạt chất lượng dịch điện ảnh cao nhất.
        - Ghép lại các hashtag vào cuối mô tả.
        """
        raw_title = str(title or "").strip()
        raw_caption = str(caption or "").strip()

        # Bóc tách hashtags từ caption
        hashtags = re.findall(r"#\S+", raw_caption)
        caption_text = re.sub(r"#\S+", "", raw_caption).strip()

        groq_keys, gemini_keys = await cls._get_active_keys()

        trans_title = ""
        trans_caption_text = ""

        # Ưu tiên dịch batch bằng LLM
        if groq_keys or gemini_keys:
            try:
                from src.core.engines.dubbing.qwen_translator import QwenInProcessTranslator
                from src.core.utils.text_sanitizer import clean_subtitle_text, is_ai_boilerplate

                texts_to_translate: List[str] = []
                if raw_title:
                    texts_to_translate.append(raw_title)
                if caption_text and caption_text != raw_title:
                    texts_to_translate.append(caption_text)

                if texts_to_translate:
                    results = await asyncio.to_thread(
                        QwenInProcessTranslator.translate_batch,
                        texts=texts_to_translate,
                        source_lang="zh",
                        target_lang="vi",
                        groq_keys=groq_keys,
                        gemini_keys=gemini_keys,
                    )
                    idx = 0
                    if raw_title and idx < len(results):
                        c = clean_subtitle_text(results[idx])
                        if c and not is_ai_boilerplate(c) and not re.search(r"[\u4e00-\u9fff]", c):
                            trans_title = c
                        idx += 1
                    if caption_text and caption_text != raw_title and idx < len(results):
                        c = clean_subtitle_text(results[idx])
                        if c and not is_ai_boilerplate(c) and not re.search(r"[\u4e00-\u9fff]", c):
                            trans_caption_text = c

            except Exception as ex:
                logger.warning(f"Lỗi dịch batch qua LLM: {ex}")

        # Fallback REST nếu tiêu đề hoặc caption chưa dịch xong
        if not trans_title and raw_title:
            trans_title = await cls._translate_via_rest(raw_title)

        if not trans_caption_text:
            if caption_text and caption_text != raw_title:
                trans_caption_text = await cls._translate_via_rest(caption_text)
            else:
                trans_caption_text = trans_title

        # Ghép lại với hashtags
        if hashtags:
            unique_tags = list(dict.fromkeys(hashtags))
            final_caption = f"{trans_caption_text}\n\n{' '.join(unique_tags)}".strip()
        else:
            final_caption = trans_caption_text

        return trans_title, final_caption
