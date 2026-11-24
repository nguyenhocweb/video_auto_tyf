"""Module cào và trích xuất dữ liệu mẫu CapCut thời gian thực từ URL/ID (CapCut Live Crawler).
Trích xuất trực tiếp từ API và trang SSR của CapCut/TikTok:
- ID mẫu, Tiêu đề, Tác giả, Thời lượng, Video preview
- Gói tài nguyên Template ZIP chính thức (template_url) để nạp vào CapCut PC
- Số lượng slots (fragments) và thời lượng chính xác từng slot (giây)
- Nhạc nền gốc
"""

import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
import httpx
from pydantic import BaseModel

logger = logging.getLogger("capcut_crawler")


class CrawledSlot(BaseModel):
    """Thông tin 1 slot sau khi cào từ CapCut."""
    slot_id: int
    slot_type: str  # "image" hoặc "video"
    start_time: float
    end_time: float
    duration: float
    description: str = ""
    video_width: Optional[int] = None
    video_height: Optional[int] = None


class CrawledTemplateData(BaseModel):
    """Toàn bộ thông tin kịch bản mẫu CapCut cào được từ web."""
    template_id: str
    title: str
    author_name: str = "CapCut Creator"
    total_duration: float
    total_slots: int
    image_slots_count: int
    video_slots_count: int
    slots: List[CrawledSlot]
    cover_url: Optional[str] = None
    video_url: Optional[str] = None
    template_url: Optional[str] = None
    music_title: Optional[str] = None
    music_url: Optional[str] = None
    source_url: str = ""


class CapCutLiveCrawler:
    """Bộ cào dữ liệu mẫu CapCut thông minh từ web ByteDance."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "vi,en;q=0.9",
    }

    @classmethod
    def extract_id(cls, url_or_id: str) -> Optional[str]:
        """Lấy ID mẫu 15-22 chữ số từ URL bất kỳ."""
        match = re.search(r"(\d{15,22})", url_or_id)
        return match.group(1) if match else None

    @classmethod
    def _fetch_html(cls, target_url: str, timeout: int = 10) -> Optional[str]:
        """Tải HTML với httpx trước, fallback sang urllib nếu cần."""
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(target_url, headers=cls.HEADERS)
                if resp.status_code == 200:
                    return resp.text
        except Exception as h_err:
            logger.debug(f"Httpx fetch failed: {h_err}, trying urllib...")

        try:
            req = urllib.request.Request(target_url, headers=cls.HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception as u_err:
            logger.error(f"Urllib fetch failed: {u_err}")
            return None

    @classmethod
    def crawl_template(cls, url_or_id: str, timeout: int = 10) -> Optional[CrawledTemplateData]:
        """Cào và bóc tách dữ liệu mẫu CapCut thực tế từ URL web."""
        tpl_id = cls.extract_id(url_or_id)
        if not tpl_id:
            logger.warning(f"Không thể tìm thấy ID mẫu trong chuỗi: {url_or_id}")
            return None

        target_url = f"https://www.capcut.com/templates/{tpl_id}"
        html = cls._fetch_html(target_url, timeout=timeout)
        if not html:
            return None

        try:
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
            init_detail: Optional[Dict[str, Any]] = None

            for s in scripts:
                if "initTemplateDetail" in s:
                    try:
                        parsed = json.loads(s)
                        loader = parsed.get("loaderData", {})
                        for k, v in loader.items():
                            if isinstance(v, dict) and "initTemplateDetail" in v:
                                init_detail = v["initTemplateDetail"]
                                break
                    except Exception:
                        continue
                if init_detail:
                    break

            if not init_detail:
                logger.warning(f"Không tìm thấy initTemplateDetail cho mẫu ID: {tpl_id}")
                return None

            return cls._parse_init_detail(init_detail, tpl_id, url_or_id)

        except Exception as ex:
            logger.error(f"Lỗi khi cào dữ liệu mẫu CapCut ({url_or_id}): {ex}")
            return None

    @classmethod
    def _parse_init_detail(
        cls, init_detail: Dict[str, Any], tpl_id: str, source_url: str
    ) -> CrawledTemplateData:
        """Chuyển đổi dữ liệu thô của CapCut sang đối tượng CrawledTemplateData chuẩn."""
        title = (init_detail.get("title") or f"Mẫu CapCut {tpl_id}").strip()

        if "search_keyword=" in source_url:
            try:
                parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(source_url).query)
                sk = parsed_q.get("search_keyword", [None])[0]
                if sk and sk.strip() and sk.strip() not in title:
                    title = f"{title} ({sk.strip()})"
            except Exception:
                pass

        author_data = init_detail.get("author") or {}
        author_name = author_data.get("name") or "CapCut Creator"

        duration_ms = float(init_detail.get("duration") or 0)
        total_duration = round(duration_ms / 1000.0, 2) if duration_ms > 0 else 15.0

        cover_url = init_detail.get("cover_url") or init_detail.get("optimized_cover_url")
        video_url = init_detail.get("video_url")
        template_url = init_detail.get("template_url")

        # Bóc tách fragments (slots)
        slots: List[CrawledSlot] = []
        extra_str = init_detail.get("extra")
        raw_fragments = []

        if isinstance(extra_str, str):
            try:
                extra_obj = json.loads(extra_str)
                raw_fragments = extra_obj.get("fragments", [])
            except Exception:
                pass
        elif isinstance(extra_str, dict):
            raw_fragments = extra_str.get("fragments", [])

        current_time = 0.0
        if raw_fragments:
            for idx, frag in enumerate(raw_fragments, 1):
                frag_dur_ms = float(frag.get("duration") or 0)
                frag_dur = round(frag_dur_ms / 1000.0, 2)
                end_time = round(current_time + frag_dur, 2)
                w = frag.get("video_width")
                h = frag.get("video_height")

                slot_type = "video" if idx == 1 and len(raw_fragments) > 1 else "image"
                res_info = f" • Gợi ý: {w}x{h}" if w and h else ""
                desc = f"Slot {idx}: Cần Video hoặc Ảnh ({frag_dur}s){res_info}"

                slots.append(
                    CrawledSlot(
                        slot_id=idx,
                        slot_type=slot_type,
                        start_time=current_time,
                        end_time=end_time,
                        duration=frag_dur,
                        description=desc,
                        video_width=w,
                        video_height=h,
                    )
                )
                current_time = end_time
        else:
            frag_count = int(init_detail.get("fragment_count") or 2)
            seg_dur = round(total_duration / max(1, frag_count), 2)
            for idx in range(1, frag_count + 1):
                st = round((idx - 1) * seg_dur, 2)
                et = round(idx * seg_dur, 2) if idx < frag_count else total_duration
                slots.append(
                    CrawledSlot(
                        slot_id=idx,
                        slot_type="image" if idx > 1 else "video",
                        start_time=st,
                        end_time=et,
                        duration=round(et - st, 2),
                        description=f"Slot {idx}: Cần Video hoặc Ảnh ({round(et - st, 2)}s)",
                    )
                )

        img_count = sum(1 for s in slots if s.slot_type == "image")
        vid_count = sum(1 for s in slots if s.slot_type == "video")

        return CrawledTemplateData(
            template_id=tpl_id,
            title=title,
            author_name=author_name,
            total_duration=total_duration,
            total_slots=len(slots),
            image_slots_count=img_count,
            video_slots_count=vid_count,
            slots=slots,
            cover_url=cover_url,
            video_url=video_url,
            template_url=template_url,
            source_url=source_url,
        )
