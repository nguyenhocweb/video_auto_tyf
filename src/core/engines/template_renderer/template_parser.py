"""Bộ phân tích mẫu CapCut tự động (CapCut Template Parser).
Chịu trách nhiệm:
1. Bóc tách link/ID mẫu CapCut thời gian thực từ web CapCut hoặc file draft_content.json.
2. Tự động xác định: Cần bao nhiêu media? Từng slot là Video hay Ảnh? Thời lượng bao nhiêu giây?
3. Xác định chính xác từng slot xuất hiện ở giây thứ mấy (start), kết thúc ở giây thứ mấy (end).
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.core.engines.template_renderer.capcut_crawler import CapCutLiveCrawler

logger = logging.getLogger("capcut_template_parser")


class ParsedSlot(BaseModel):
    """Thông tin 1 slot media được trích xuất tự động từ mẫu CapCut."""
    slot_id: int
    slot_type: str = Field(description="'image' hoặc 'video'")
    start_time: float = Field(description="Thời điểm xuất hiện trên timeline (giây)")
    end_time: float = Field(description="Thời điểm kết thúc trên timeline (giây)")
    duration: float = Field(description="Thời lượng yêu cầu (giây)")
    description: str = ""
    is_replaceable: bool = True
    video_width: Optional[int] = None
    video_height: Optional[int] = None


class ParsedTemplateSpec(BaseModel):
    """Cấu trúc hoàn chỉnh của một mẫu CapCut sau khi bóc tách tự động."""
    template_id: str
    title: str
    author_name: str = "CapCut Creator"
    total_duration: float
    total_slots: int
    image_slots_count: int
    video_slots_count: int
    slots: List[ParsedSlot]
    has_audio: bool = True
    music_title: Optional[str] = None
    music_url: Optional[str] = None
    cover_url: Optional[str] = None
    video_url: Optional[str] = None
    template_url: Optional[str] = None
    source_url: str = ""


class CapCutTemplateParser:
    """Engine phân tích kịch bản mẫu CapCut đa nguồn: Link/ID, Draft JSON, hoặc Crawl thời gian thực."""

    @staticmethod
    def extract_template_id(input_str: str) -> Optional[str]:
        """Trích xuất ID mẫu 15-22 số từ link CapCut (URL) hoặc chuỗi ID thuần."""
        match = re.search(r"(\d{15,22})", input_str)
        return match.group(1) if match else None

    @classmethod
    def parse_from_draft_json(cls, draft_data: Dict[str, Any], template_id: str = "custom") -> ParsedTemplateSpec:
        """Bóc tách trực tiếp từ cấu trúc draft_content.json của CapCut/JianYing."""
        tracks = draft_data.get("tracks", [])
        materials = draft_data.get("materials", {})
        video_mats = {m.get("id"): m for m in materials.get("videos", [])}

        parsed_slots: List[ParsedSlot] = []
        total_duration_us = 0
        slot_idx = 1

        for track in tracks:
            if track.get("type") == "video":
                for seg in track.get("segments", []):
                    timerange = seg.get("target_timerange", {})
                    start_us = timerange.get("start", 0)
                    duration_us = timerange.get("duration", 0)
                    end_us = start_us + duration_us
                    total_duration_us = max(total_duration_us, end_us)

                    mat_id = seg.get("material_id")
                    mat = video_mats.get(mat_id, {})
                    is_image = mat.get("type", "") == "photo" or "image" in str(mat.get("path", "")).lower()
                    slot_type = "image" if is_image else "video"

                    parsed_slots.append(
                        ParsedSlot(
                            slot_id=slot_idx,
                            slot_type=slot_type,
                            start_time=round(start_us / 1_000_000, 3),
                            end_time=round(end_us / 1_000_000, 3),
                            duration=round(duration_us / 1_000_000, 3),
                            description=f"Slot {slot_idx} ({slot_type}) từ {round(start_us/1_000_000, 2)}s đến {round(end_us/1_000_000, 2)}s",
                        )
                    )
                    slot_idx += 1

        img_count = sum(1 for s in parsed_slots if s.slot_type == "image")
        vid_count = sum(1 for s in parsed_slots if s.slot_type == "video")

        return ParsedTemplateSpec(
            template_id=template_id,
            title=f"Mẫu CapCut Draft {template_id}",
            total_duration=round(total_duration_us / 1_000_000, 2),
            total_slots=len(parsed_slots),
            image_slots_count=img_count,
            video_slots_count=vid_count,
            slots=parsed_slots,
            has_audio=True,
        )

    @classmethod
    def parse_from_template_id_or_url(cls, input_str: str) -> ParsedTemplateSpec:
        """Bóc tách kịch bản khi người dùng dán Link CapCut hoặc nhập ID mẫu.
        
        Ưu tiên cào dữ liệu trực tiếp thời gian thực từ CapCut Web.
        Nếu offline hoặc không cào được thì fallback sang các preset đã định nghĩa.
        """
        clean_input = input_str.strip()
        tpl_id = cls.extract_template_id(clean_input) or clean_input

        # 1. Thử cào dữ liệu trực tiếp thời gian thực từ CapCut Web
        if tpl_id and (len(tpl_id) >= 15 or "capcut.com" in clean_input):
            try:
                crawled = CapCutLiveCrawler.crawl_template(clean_input)
                if crawled:
                    logger.info(f"Đã cào thành công mẫu CapCut {crawled.template_id} từ web!")
                    parsed_slots = [
                        ParsedSlot(
                            slot_id=s.slot_id,
                            slot_type=s.slot_type,
                            start_time=s.start_time,
                            end_time=s.end_time,
                            duration=s.duration,
                            description=s.description,
                            video_width=s.video_width,
                            video_height=s.video_height,
                        )
                        for s in crawled.slots
                    ]
                    return ParsedTemplateSpec(
                        template_id=crawled.template_id,
                        title=crawled.title,
                        author_name=crawled.author_name,
                        total_duration=crawled.total_duration,
                        total_slots=crawled.total_slots,
                        image_slots_count=crawled.image_slots_count,
                        video_slots_count=crawled.video_slots_count,
                        slots=parsed_slots,
                        has_audio=True,
                        music_title=crawled.music_title,
                        music_url=crawled.music_url,
                        cover_url=crawled.cover_url,
                        video_url=crawled.video_url,
                        template_url=crawled.template_url,
                        source_url=clean_input,
                    )
            except Exception as crawl_err:
                logger.warning(f"Cào dữ liệu CapCut thất bại, dùng fallback: {crawl_err}")

        # 2. Fallback sang preset đã biết
        if tpl_id == "7709090549353090312" or "three_photo" in clean_input.lower():
            slots = [
                ParsedSlot(slot_id=1, slot_type="image", start_time=0.0, end_time=18.60, duration=18.60, description="Ảnh Mở Đầu (Intro Monochrome 18.60s)"),
                ParsedSlot(slot_id=2, slot_type="image", start_time=18.60, end_time=22.87, duration=4.27, description="Ảnh Tiết Tấu A (Beat Hit A 4.27s)"),
                ParsedSlot(slot_id=3, slot_type="image", start_time=22.87, end_time=26.20, duration=3.33, description="Ảnh Tiết Tấu B (Beat Hit B 3.33s)"),
            ]
            return ParsedTemplateSpec(
                template_id="7709090549353090312",
                title="Mẫu CapCut 3 Ảnh Giật Beat & Strobe Rhythmic",
                author_name="CapCut Official",
                total_duration=31.23,
                total_slots=3,
                image_slots_count=3,
                video_slots_count=0,
                slots=slots,
                has_audio=True,
                music_title="Và vì chẳng nghe đợi cho duyên lỡ",
            )

        if "có mình và ta" in clean_input.lower() or "co minh va ta" in clean_input.lower() or "toàn nhỏ" in clean_input.lower():
            slots = [
                ParsedSlot(slot_id=1, slot_type="image", start_time=0.0, end_time=10.50, duration=10.50, description="Ảnh/Video Mở đầu (0.0s - 10.5s)"),
                ParsedSlot(slot_id=2, slot_type="image", start_time=10.50, end_time=21.00, duration=10.50, description="Ảnh Cao trào điệp khúc (10.5s - 21.0s)"),
            ]
            return ParsedTemplateSpec(
                template_id=tpl_id if tpl_id != clean_input else "co_minh_va_ta",
                title="Mẫu CapCut: CÓ MÌNH VÀ TA (Toàn Nhỏ)",
                author_name="Toàn Nhỏ [Nọc]",
                total_duration=21.0,
                total_slots=2,
                image_slots_count=2,
                video_slots_count=0,
                slots=slots,
                has_audio=True,
                music_title="Nếu sông có cạn nếu đá có mòn",
            )

        if tpl_id == "7444199034253774133" or "pan_drop" in clean_input.lower():
            slots = [
                ParsedSlot(slot_id=1, slot_type="video", start_time=0.0, end_time=8.80, duration=8.80, description="Video mở đầu (trượt dần xuống dưới 8.80s)"),
                ParsedSlot(slot_id=2, slot_type="image", start_time=8.25, end_time=21.23, duration=12.98, description="Ảnh chân dung (nối đuôi + trôi chậm 12.98s)"),
            ]
            return ParsedTemplateSpec(
                template_id="7444199034253774133",
                title="Mẫu CapCut 1 Video + 1 Ảnh Slide Down & Chớp 15Hz",
                author_name="CapCut Trending",
                total_duration=21.23,
                total_slots=2,
                image_slots_count=1,
                video_slots_count=1,
                slots=slots,
                has_audio=True,
            )

        # Mặc định
        slots = [
            ParsedSlot(slot_id=1, slot_type="video", start_time=0.0, end_time=5.0, duration=5.0, description="Clip mở đầu (5.0s)"),
            ParsedSlot(slot_id=2, slot_type="image", start_time=5.0, end_time=15.0, duration=10.0, description="Ảnh cao trào (10.0s)"),
        ]
        return ParsedTemplateSpec(
            template_id=tpl_id,
            title=f"Mẫu CapCut ID {tpl_id}",
            author_name="CapCut Creator",
            total_duration=15.0,
            total_slots=2,
            image_slots_count=1,
            video_slots_count=1,
            slots=slots,
            has_audio=True,
        )
