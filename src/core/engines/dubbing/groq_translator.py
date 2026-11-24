import os
import re
import time
import logging
import asyncio
import concurrent.futures
from typing import List, Dict, Any, Optional, Callable
from groq import Groq, APIError, APIStatusError, AuthenticationError, RateLimitError

from src.core.config import settings
from src.core.utils.text_sanitizer import clean_subtitle_text, is_ai_boilerplate, is_length_hallucination
from src.core.engines.dubbing.videolingo_prompt import build_videolingo_prompt

logger = logging.getLogger("groq_translator")


class GroqTranslator:
    """
    Engine dịch thuật phụ đề phim sử dụng Groq Cloud API siêu tốc (Llama-3.3-70B).
    - Ưu tiên hàng đầu trong chuỗi dịch thuật (nhanh gấp 5-10 lần, miễn phí 14.4k req/ngày).
    - Tự động xoay tua danh sách Key Groq từ MongoDB.
    """

    _key_index: int = 0

    @classmethod
    def _parse_indexed_translation(
        cls, raw_output: str, expected_count: int, texts: Optional[List[str]] = None
    ) -> Dict[int, str]:
        """Trích xuất kết quả dịch thuật chuẩn 'LINE_x: ...' và loại bỏ rác/ảo giác."""
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
    def _call_single_groq_api(
        cls,
        texts: List[str],
        api_key: str,
        durations: Optional[List[float]] = None,
        context: Optional[Dict[str, Any]] = None,
        preferred_model: Optional[str] = None,
        prev_lines: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """Gửi batch kịch bản sang Groq API."""
        prompt = build_videolingo_prompt(texts, durations=durations, context=context, prev_lines=prev_lines)
        sys_prompt = (
            "Bạn là đạo diễn lồng tiếng & biên kịch phụ đề điện ảnh cao cấp. "
            "CHỈ dịch từng dòng và bọc toàn bộ trong: --- NỘI DUNG ĐÃ DỊCH --- ... --- HẾT NỘI DUNG ĐÃ DỊCH ---. "
            "Định dạng mỗi dòng: 'LINE_x: <bản dịch>' hoặc 'LINE_x: [SKIP]'. "
            "TUYỆT ĐỐI KHÔNG ghi chú, không Note, không giải thích bên trong thẻ."
        )

        model_candidates = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "allam-2-7b"]
        if preferred_model and preferred_model.strip():
            m = preferred_model.strip()
            if m in model_candidates:
                model_candidates.remove(m)
            model_candidates.insert(0, m)

        client = Groq(api_key=api_key, timeout=15.0)
        for model_name in model_candidates:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=2048,
                )
                output_text = response.choices[0].message.content or ""
                if output_text:
                    parsed = cls._parse_indexed_translation(output_text, len(texts), texts=texts)
                    if len(parsed) >= len(texts) * 0.7:
                        return [parsed.get(i, "") for i in range(len(texts))]
            except RateLimitError:
                logger.warning(f"Groq Key ({api_key[:8]}...) chạm giới hạn 429 RPM. Chuyển key tiếp...")
                return None
            except AuthenticationError:
                logger.warning(f"Groq Key ({api_key[:8]}...) lỗi xác thực 401. Key không hợp lệ.")
                return None
            except APIStatusError as ae:
                logger.warning(f"Groq Key ({api_key[:8]}...) model '{model_name}' lỗi HTTP {ae.status_code}: {ae.message}")
                # Nếu tài khoản đã bị Groq khóa (organization_restricted), bỏ qua ngay lập tức toàn bộ model của key này
                err_msg = str(ae.message).lower()
                if "organization_restricted" in err_msg or ae.status_code in (401, 403):
                    logger.error(f"Groq Key ({api_key[:8]}...) tài khoản đã bị Groq khóa (organization_restricted). Chuyển ngay key khác...")
                    return None
            except APIError as ae:
                logger.warning(f"Groq Key ({api_key[:8]}...) model '{model_name}' lỗi: {ae.message}")
            except Exception as e:
                logger.warning(f"Groq Key ({api_key[:8]}...) model '{model_name}' lỗi: {e}")

        return None

    @classmethod
    def translate_with_groq_pool(
        cls,
        texts: List[str],
        groq_keys: Optional[List[Dict[str, Any]]] = None,
        durations: Optional[List[float]] = None,
        context: Optional[Dict[str, Any]] = None,
        on_key_used: Optional[Callable[[str, bool], None]] = None,
        prev_lines: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """Duyệt qua danh sách Groq Keys và xoay tua tự động."""
        active_keys: List[Dict[str, Any]] = list(groq_keys) if groq_keys else []
        if not active_keys:
            try:
                from src.modules.creator.dubbing.groq_keys_repository import GroqKeysMongoRepository
                repo = GroqKeysMongoRepository()
                try:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        active_keys = executor.submit(lambda: asyncio.run(repo.get_active_keys())).result()
                except Exception:
                    pass
            except Exception as db_err:
                logger.debug(f"Không thể đọc Groq keys từ DB: {db_err}")

        # Kiểm tra thêm biến môi trường nếu có
        env_key = getattr(settings, "GROQ_API_KEY", "").strip() or os.getenv("GROQ_API_KEY", "").strip()
        if env_key and not any(k["key"] == env_key for k in active_keys):
            active_keys.append({"id": "env_groq_key", "key": env_key, "note": "Env Groq Key"})

        if not active_keys:
            return None

        start_idx = cls._key_index % len(active_keys)
        ordered_keys = active_keys[start_idx:] + active_keys[:start_idx]

        max_rounds = 2
        for round_num in range(1, max_rounds + 1):
            for k_idx, k_info in enumerate(ordered_keys):
                raw_key = k_info.get("key", "").strip()
                key_id = k_info.get("id", "")
                if not raw_key:
                    continue

                res = cls._call_single_groq_api(
                    texts,
                    raw_key,
                    durations=durations,
                    context=context,
                    preferred_model=k_info.get("model"),
                    prev_lines=prev_lines,
                )
                if res:
                    cls._key_index = (start_idx + k_idx + 1) % len(active_keys)
                    logger.info(f"⚡ Dịch thành công {len(texts)} câu với GROQ Key [{k_info.get('note', key_id)}].")
                    if on_key_used and key_id and key_id != "env_groq_key":
                        on_key_used(key_id, True)
                    return res
                else:
                    logger.warning(f"Groq Key [{k_info.get('note', key_id)}] lỗi, thử key tiếp theo...")
                    if on_key_used and key_id and key_id != "env_groq_key":
                        on_key_used(key_id, False)

            if round_num < max_rounds:
                time.sleep(1.5)

        logger.warning("Toàn bộ Groq Keys đều tạm thời bận hoặc chạm hạn mức. Chuyển sang Gemini...")
        return None

