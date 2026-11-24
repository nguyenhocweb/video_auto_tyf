import re
import json
import urllib.parse
import logging
import asyncio
from typing import List, Dict, Any, Optional

from src.modules.creator.video.sino_vietnamese_dict import SINO_VIETNAMESE_DICT
from src.core.utils.text_sanitizer import clean_subtitle_text, is_ai_boilerplate

logger = logging.getLogger("channel_translator")


class ChannelMetadataTranslator:
    """Bộ chuyển ngữ thông minh chuyên biệt cho Tên Kênh và Tiêu đề video Douyin."""

    @classmethod
    def to_sino_vietnamese(cls, text: str) -> str:
        """Chuyển đổi từng ký tự chữ Hán sang âm Hán-Việt chuẩn."""
        if not text:
            return ""
        result = []
        i = 0
        n = len(text)
        while i < n:
            if i + 2 <= n and text[i : i + 2] in SINO_VIETNAMESE_DICT:
                result.append(SINO_VIETNAMESE_DICT[text[i : i + 2]])
                i += 2
                continue
            ch = text[i]
            if ch in SINO_VIETNAMESE_DICT:
                result.append(SINO_VIETNAMESE_DICT[ch])
            else:
                result.append(ch)
            i += 1
        joined = " ".join([w for w in result if w.strip()]).strip()
        joined = re.sub(r"\s+", " ", joined)
        return joined.title()

    @classmethod
    async def _fetch_gtx(cls, text: str) -> Optional[str]:
        """Dịch nhanh qua Google Translate GTX REST API."""
        encoded = urllib.parse.quote(text.strip())
        api_url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=zh-CN&tl=vi&dt=t&q={encoded}"
        try:
            import httpx
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=httpx.Timeout(4.0, connect=2.5),
            ) as client:
                resp = await client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json()
                    res = "".join([item[0] for item in data[0] if item and item[0]]).strip()
                    return res if res else None
        except Exception:
            return None
        return None

    @classmethod
    def _extract_clean_name(cls, content: str) -> Optional[str]:
        """Trích xuất tên chuẩn từ khối phân tách và loại bỏ triệt để ghi chú/Note/SároNote."""
        if not content:
            return None
        # Bắt nội dung bên trong khối, kể cả khi thẻ đóng bị cắt ngắn hoặc thiếu
        block_m = re.search(
            r"---\s*(?:NỘI DUNG ĐÃ DỊCH|NOI DUNG DA DICH|TRANSLATED CONTENT)\s*---\s*(.*?)(?:---\s*(?:HẾT|HET|END)|$)",
            content,
            re.DOTALL | re.IGNORECASE,
        )
        raw = block_m.group(1).strip() if block_m else content.strip()
        # Xóa bỏ hoàn toàn bất kỳ tàn dư thẻ phân tách nào nếu còn sót
        raw = re.sub(
            r"---\s*(?:NỘI DUNG ĐÃ DỊCH|HẾT[^\-]*|END[^\-]*)\s*---?",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        valid = [l for l in lines if not re.search(r"\b(?:note|lưu ý|ghi chú|quy tắc|chuyển đổi)\b", l, re.I)]
        candidate = " ".join(valid).strip() if valid else raw
        # Xóa tiền tố nhãn nếu LLM lặp lại chữ 'Tên Đã Dịch:' hoặc 'Bản dịch:'
        candidate = re.sub(
            r"^(?:Tên\s*(?:đã\s*)?dịch|Bản\s*dịch|Tên\s*kênh|Tên\s*tác\s*giả)\s*[\:\-\=]\s*",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip()
        candidate = re.sub(r"^[\[\(\"']+|[\]\)\"']+$", "", candidate).strip()
        candidate = re.sub(r"^[\[\(\"']+|[\]\)\"']+$", "", candidate).strip()
        cleaned = re.sub(r"[\u4e00-\u9fff\"]", "", clean_subtitle_text(candidate)).strip()
        if not cleaned:
            cleaned = re.sub(r"[\u4e00-\u9fff\[\]\(\)\"']", "", candidate).strip()
        # Chặn đứng tuyệt đối nếu chuỗi vẫn chứa tàn dư delimiter
        if re.search(r"nội\s*dung\s*đã\s*dịch|hết\s*nội\s*dung|tên\s*đã\s*dịch", cleaned, re.IGNORECASE):
            return None
        if cleaned and len(cleaned) >= 2 and not is_ai_boilerplate(cleaned):
            return cleaned.title()
        return None

    @classmethod
    def _translate_with_llm_name_sync(
        cls,
        raw_name: str,
        groq_keys: Optional[List[Dict[str, Any]]] = None,
        gemini_keys: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """Dịch tên tác giả/kênh Douyin bằng Groq hoặc Gemini đồng bộ (ép buộc khối phân tách)."""
        sys_prompt = (
            "Bạn là chuyên gia chuyển ngữ Hán-Việt tên tác giả/kênh Douyin Trung sang Việt.\n"
            "Quy tắc tối cao:\n"
            "1. Chuyển sang âm Hán-Việt tự nhiên chuẩn xác (VD: '月岛雯' -> 'Nguyệt Đảo Văn', '夏小沛' -> 'Hạ Tiểu Phái', '李子柒' -> 'Lý Tử Thất').\n"
            "2. Viết hoa chữ cái đầu mỗi từ.\n"
            "3. BẮT BUỘC chỉ trả về tên đã dịch bên trong khối phân tách chuẩn (cấm viết chữ 'Tên Đã Dịch', cấm giải thích):\n"
            "--- NỘI DUNG ĐÃ DỊCH ---\n"
            "Nguyệt Đảo Văn\n"
            "--- HẾT NỘI DUNG ĐÃ DỊCH ---\n"
            "4. Tuyệt đối không thêm bất kỳ chữ nào khác ngoài tên."
        )
        user_prompt = f"Dịch tên tác giả sau: {raw_name}"

        if groq_keys:
            try:
                from groq import Groq
                for k_info in groq_keys:
                    key = k_info.get("key", "").strip()
                    if not key:
                        continue
                    client = Groq(api_key=key, timeout=3.0)
                    resp = client.chat.completions.create(
                        model=k_info.get("model") or "qwen/qwen3.8-27b",
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        temperature=0.1,
                        max_tokens=128,
                    )
                    content = (resp.choices[0].message.content or "").strip()
                    extracted = cls._extract_clean_name(content)
                    if extracted:
                        return extracted
            except Exception as ge:
                logger.debug(f"LLM Groq name translate bypassed: {ge}")

        if gemini_keys:
            try:
                from google import genai
                from google.genai import types
                for k_info in gemini_keys:
                    key = k_info.get("key", "").strip()
                    if not key:
                        continue
                    client = genai.Client(api_key=key)
                    resp = client.models.generate_content(
                        model=k_info.get("model") or "gemini-2.0-flash",
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=sys_prompt,
                            temperature=0.1,
                            max_output_tokens=128,
                        ),
                    )
                    content = (getattr(resp, "text", "") or "").strip()
                    extracted = cls._extract_clean_name(content)
                    if extracted:
                        return extracted
            except Exception as me:
                logger.debug(f"LLM Gemini name translate bypassed: {me}")

        return None

    @classmethod
    async def translate_channel_name(
        cls,
        raw_name: str,
        groq_keys: Optional[List[Dict[str, Any]]] = None,
        gemini_keys: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Dịch tên kênh tác giả Douyin sang tiếng Việt (Đa tầng: Hán-Việt Dictionary -> LLM -> GTX)."""
        name = (raw_name or "").strip()
        if not name or not re.search(r"[\u4e00-\u9fff]", name):
            return name

        # Tầng 1: Phiên âm Hán-Việt nội bộ chuẩn xác (0% latency, 0% tốn Quota, chuẩn 100% cho tên người/kênh)
        sino_res = cls.to_sino_vietnamese(name)
        if sino_res and not re.search(r"[\u4e00-\u9fff]", sino_res):
            return sino_res

        # Tầng 2: LLM (Groq / Gemini) chuyên biệt tên riêng nếu có key
        if groq_keys is None and gemini_keys is None:
            try:
                from src.modules.creator.dubbing.groq_keys_repository import GroqKeysMongoRepository
                from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository
                groq_keys = await GroqKeysMongoRepository().get_active_keys()
                gemini_keys = await GeminiKeysMongoRepository().get_active_keys()
            except Exception:
                pass

        if groq_keys or gemini_keys:
            try:
                llm_res = await asyncio.to_thread(
                    cls._translate_with_llm_name_sync, name, groq_keys, gemini_keys
                )
                if llm_res and not re.search(r"[\u4e00-\u9fff]", llm_res):
                    return llm_res
            except Exception as e:
                logger.debug(f"LLM name translate error: {e}")

        # Tầng 3: Google Translate GTX (Online)
        try:
            gtx_res = await cls._fetch_gtx(name)
            if gtx_res and not re.search(r"[\u4e00-\u9fff]", gtx_res) and len(gtx_res) >= 2:
                cleaned = clean_subtitle_text(gtx_res) or gtx_res
                cleaned = re.sub(r"^[\[\(\"']+|[\]\)\"']+$", "", cleaned).strip()
                if cleaned and len(cleaned) >= 2 and not is_ai_boilerplate(cleaned):
                    return cleaned.title()
        except Exception as ge:
            logger.debug(f"GTX name translate error: {ge}")

        # Tầng 4: Fallback tối ưu giữ lại các âm Hán-Việt đã nhận diện
        cleaned_fallback = re.sub(r"[\u4e00-\u9fff]", "", sino_res).strip()
        return cleaned_fallback or sino_res or name

    @classmethod
    async def translate_video_titles(
        cls,
        titles: List[str],
        groq_keys: Optional[List[Dict[str, Any]]] = None,
        gemini_keys: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """Dịch danh sách tiêu đề video Douyin sang tiếng Việt tự nhiên."""
        if not titles:
            return []

        async def _trans_one(title: str) -> str:
            t = (title or "").strip()
            if not t or not re.search(r"[\u4e00-\u9fff]", t):
                return t
            try:
                res = await cls._fetch_gtx(t)
                if res and not re.search(r"[\u4e00-\u9fff]", res):
                    cleaned = clean_subtitle_text(res)
                    if cleaned and not is_ai_boilerplate(cleaned):
                        return cleaned
            except Exception:
                pass
            cleaned = re.sub(r"[\u4e00-\u9fff]", "", t).strip()
            return cleaned or t

        tasks = [_trans_one(t) for t in titles]
        return await asyncio.gather(*tasks)
