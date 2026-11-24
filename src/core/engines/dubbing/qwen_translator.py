import os
import re
import time
import logging
import asyncio
import concurrent.futures
from typing import List, Dict, Any, Optional, Callable

from src.core.config import settings
from src.core.utils.text_sanitizer import clean_subtitle_text, is_ai_boilerplate, is_length_hallucination
from src.core.engines.dubbing.videolingo_prompt import build_videolingo_prompt

logger = logging.getLogger("qwen_translator")


class QwenInProcessTranslator:
    """
    Engine dịch thuật phụ đề phim chuẩn VideoLingo (100% Cloud LLM điện ảnh).
    - Ưu tiên số 1: Groq API Pool (Qwen 3.8 27B LPU siêu tốc ~0.5s, 0% tốn RAM/VRAM máy).
    - Dự phòng số 2: Google Gemini Multi-Key Pool (Tự động xoay tua đa chìa khóa khi 429).
    """

    _key_index: int = 0

    @classmethod
    def _call_single_gemini_api(
        cls,
        texts: List[str],
        api_key: str,
        durations: Optional[List[float]] = None,
        context: Optional[Dict[str, Any]] = None,
        preferred_model: Optional[str] = None,
        prev_lines: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """Gửi batch kịch bản sang Gemini API qua SDK chính thức google-genai."""
        from google import genai
        from google.genai import types
        from google.genai.errors import APIError

        prompt = build_videolingo_prompt(texts, durations=durations, context=context, prev_lines=prev_lines)
        sys_prompt = (
            "Bạn là đạo diễn lồng tiếng & biên kịch phụ đề điện ảnh cao cấp. "
            "CHỈ dịch từng dòng và bọc toàn bộ trong: --- NỘI DUNG ĐÃ DỊCH --- ... --- HẾT NỘI DUNG ĐÃ DỊCH ---. "
            "Định dạng mỗi dòng: 'LINE_x: <bản dịch>' hoặc 'LINE_x: [SKIP]'. "
            "TUYỆT ĐỐI KHÔNG ghi chú, không Note, không giải thích bên trong thẻ."
        )
        model_candidates = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
        configured = str(getattr(settings, "GEMINI_MODEL_ID", "") or "").strip()
        if configured and configured not in ("gemini-3.8-flash", "gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"):
            model_candidates.insert(0, configured)
        if preferred_model and preferred_model.strip():
            m = preferred_model.strip()
            if m in model_candidates:
                model_candidates.remove(m)
            model_candidates.insert(0, m)

        client = genai.Client(api_key=api_key)
        for model_name in model_candidates:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=sys_prompt,
                        temperature=0.1,
                        max_output_tokens=2048,
                    ),
                )
                output_text = getattr(response, "text", "") or ""
                if output_text:
                    parsed = cls._parse_indexed_translation(output_text, len(texts), texts=texts)
                    if len(parsed) >= len(texts) * 0.7:
                        return [parsed.get(i, "") for i in range(len(texts))]
            except APIError as ae:
                code = getattr(ae, "code", 0)
                if code == 429:
                    logger.warning(f"Gemini Key ({api_key[:6]}...) chạm giới hạn 429 (Hết Quota/RPM). Đang chờ hồi...")
                    return None
                elif code in (400, 401, 403):
                    logger.warning(f"Gemini Key ({api_key[:6]}...) lỗi xác thực (HTTP {code}). Vui lòng kiểm tra lại Key.")
                    return None
                elif code in (404, 503):
                    logger.warning(f"Model '{model_name}' gặp HTTP {code} (quá tải/không tìm thấy) trên Key ({api_key[:6]}...). Tự động thử model dự phòng...")
                    continue
                logger.warning(f"Gemini Key ({api_key[:6]}...) model '{model_name}' lỗi HTTP {code}: {ae.message}")
            except Exception as e:
                logger.warning(f"Gemini Key ({api_key[:6]}...) model '{model_name}' lỗi: {e}")

        return None

    @classmethod
    def _translate_with_gemini_pool(
        cls,
        texts: List[str],
        gemini_keys: Optional[List[Dict[str, Any]]] = None,
        on_key_used: Optional[Callable[[str, bool], None]] = None,
        durations: Optional[List[float]] = None,
        context: Optional[Dict[str, Any]] = None,
        prev_lines: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """Duyệt qua danh sách Key Gemini trong Database và xoay tua tự động (chờ hồi Quota nếu 429)."""
        active_keys: List[Dict[str, Any]] = list(gemini_keys) if gemini_keys else []
        if not active_keys:
            try:
                from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository
                repo = GeminiKeysMongoRepository()
                try:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        active_keys = executor.submit(lambda: asyncio.run(repo.get_active_keys())).result()
                except Exception:
                    pass
            except Exception as db_err:
                logger.debug(f"Không thể đọc Gemini keys từ DB: {db_err}")

        env_key = getattr(settings, "GEMINI_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
        if env_key and not any(k["key"] == env_key for k in active_keys):
            active_keys.append({"id": "env_key", "key": env_key, "note": "Env Key"})

        if not active_keys:
            return None

        start_idx = cls._key_index % len(active_keys)
        ordered_keys = active_keys[start_idx:] + active_keys[:start_idx]

        max_rounds = 3
        for round_num in range(1, max_rounds + 1):
            for k_idx, k_info in enumerate(ordered_keys):
                raw_key = k_info.get("key", "").strip()
                key_id = k_info.get("id", "")
                if not raw_key:
                    continue

                res = cls._call_single_gemini_api(
                    texts,
                    raw_key,
                    durations=durations,
                    context=context,
                    preferred_model=k_info.get("model"),
                    prev_lines=prev_lines,
                )
                if res:
                    cls._key_index = (start_idx + k_idx + 1) % len(active_keys)
                    logger.info(f"Dịch thành công {len(texts)} câu với Gemini Key [{k_info.get('note', key_id)}] (Lượt {round_num}).")
                    if on_key_used and key_id and key_id != "env_key":
                        on_key_used(key_id, True)
                    return res
                else:
                    logger.warning(f"Key [{k_info.get('note', key_id)}] 429/lỗi (Lượt {round_num}), xoay tua Key tiếp...")
                    if on_key_used and key_id and key_id != "env_key":
                        on_key_used(key_id, False)

            if round_num < max_rounds:
                wait_sec = 2.5 * round_num
                logger.info(f"Toàn bộ {len(ordered_keys)} Keys bị nghẽn ở lượt {round_num}. Đợi {wait_sec:.1f}s để hồi hạn mức RPM...")
                time.sleep(wait_sec)

        logger.warning("Toàn bộ các Key Gemini đều tạm thời chạm hạn ngạch sau 3 lượt thử.")
        return None

    @classmethod
    def _parse_indexed_translation(
        cls, raw_output: str, expected_count: int, texts: Optional[List[str]] = None
    ) -> Dict[int, str]:
        """Trích xuất kết quả dịch thuật chuẩn và loại bỏ triệt để mọi rác thời lượng/chữ Hán/ảo giác."""
        result = {}
        # 1. Trích xuất khối nội dung bên trong delimiter nếu có
        block_m = re.search(
            r"---\s*(?:NỘI DUNG ĐÃ DỊCH|BEGIN_TRANSLATION|BẢN DỊCH)\s*---(.*?)---\s*(?:HẾT NỘI DUNG ĐÃ DỊCH|END_TRANSLATION|HẾT BẢN DỊCH)\s*---",
            raw_output,
            re.DOTALL | re.IGNORECASE,
        )
        content = block_m.group(1) if block_m else raw_output

        lines = [line.strip() for line in content.split("\n") if line.strip()]
        pat = re.compile(
            r"^\s*(?:<<<|\[\[\[|\[\[|\[|[\-\*\•]?\s*\[*)\s*(?:LINE_)?(\d+)\s*(?:>>>|\]\]\]|\]\]|\])*[\.\:\-\s]*(.*)",
            re.I,
        )
        for line in lines:
            m = pat.match(line)
            if m:
                idx = int(m.group(1))
                val = m.group(2).strip()
                if re.search(r"\[\s*SKIP\s*\]", val, re.I) or val.upper() == "SKIP":
                    continue
                cleaned = re.sub(r"[\u4e00-\u9fff]", "", clean_subtitle_text(val)).strip()
                zh_ref = texts[idx] if texts and 0 <= idx < len(texts) else ""
                if (
                    0 <= idx < expected_count
                    and cleaned
                    and not is_ai_boilerplate(cleaned)
                    and not is_length_hallucination(zh_ref, cleaned)
                ):
                    result[idx] = cleaned

        return result

    @classmethod
    def translate_single_line(
        cls,
        text: str,
        duration: float = 2.5,
        groq_keys: Optional[List[Dict[str, Any]]] = None,
        gemini_keys: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Dịch một câu thoại duy nhất bằng Cloud LLM an toàn không làm vỡ tiến trình."""
        if not text or not text.strip():
            return ""
        try:
            res_batch = cls.translate_batch(
                [text],
                durations=[duration],
                groq_keys=groq_keys,
                gemini_keys=gemini_keys,
            )
            return res_batch[0] if res_batch and res_batch[0] else text
        except Exception as e:
            logger.debug(f"translate_single_line bypass ({e}), giữ nguyên text gốc.")
            return text

    @classmethod
    def translate_batch(
        cls,
        texts: List[str],
        source_lang: str = "zh",
        target_lang: str = "vi",
        gemini_keys: Optional[List[Dict[str, Any]]] = None,
        groq_keys: Optional[List[Dict[str, Any]]] = None,
        on_key_used: Optional[Callable[[str, bool], None]] = None,
        durations: Optional[List[float]] = None,
        context: Optional[Dict[str, Any]] = None,
        prev_lines: Optional[List[str]] = None,
    ) -> List[str]:
        """Dịch 1 batch phụ đề bằng 100% Cloud LLM siêu tốc (Groq LPU -> Gemini Multi-Key Pool)."""
        if not texts:
            return []

        # 1. Ưu tiên số 1: Groq API Pool (Qwen 3.8 27B siêu tốc 0.5s, 0% tốn RAM/VRAM)
        try:
            from src.core.engines.dubbing.groq_translator import GroqTranslator
            candidates = GroqTranslator.translate_with_groq_pool(
                texts,
                groq_keys=groq_keys,
                on_key_used=on_key_used,
                durations=durations,
                context=context,
                prev_lines=prev_lines,
            )
        except Exception as ge:
            logger.debug(f"Groq pool error/bypass: {ge}")
            candidates = None

        # 2. Dự phòng số 2: Gemini Multi-Key Pool nếu Groq chưa cấu hình hoặc tạm bận
        if not candidates:
            candidates = cls._translate_with_gemini_pool(
                texts,
                gemini_keys=gemini_keys,
                on_key_used=on_key_used,
                durations=durations,
                context=context,
                prev_lines=prev_lines,
            )

        # Nếu cả Groq Pool và Gemini Pool đều không có kết quả -> Báo lỗi rõ ràng để kiểm tra Key
        if not candidates:
            raise RuntimeError(
                "Dịch thuật kịch bản thất bại: Cả Groq Cloud và Gemini Pool đều chưa có Key khả dụng hoặc đã chạm hạn mức. "
                "Vui lòng vào trang 'Cài đặt AI' để bổ sung hoặc kiểm tra lại Key!"
            )

        # 3. Hậu kiểm tra nghiêm ngặt: Loại bỏ ảo giác (Nếu rác -> trả về chuỗi rỗng để loại bỏ)
        final_results = []
        for i, zh in enumerate(texts):
            trans = candidates[i] if i < len(candidates) else ""
            if not trans or is_ai_boilerplate(trans) or is_length_hallucination(zh, trans):
                final_results.append("")
            else:
                final_results.append(trans)

        return final_results
