import os
import re
import uuid
import asyncio
import logging
from typing import Dict, Any, List, Optional

from src.core.config import settings
from src.core.engines.douyin.extractor import DouyinExtractor
from src.core.engines.douyin.channel_crawler import DouyinChannelCrawler
from src.modules.creator.facebook.service import FacebookService
from src.modules.creator.facebook.schemas import PublishReelRequest
from src.modules.creator.youtube.service import YouTubeService
from src.modules.creator.youtube.schemas import PublishShortsRequest
from src.modules.creator.automation.executor_helpers import ExecutorHelpers
from src.modules.creator.automation.reup_transformer import ReupTransformer

logger = logging.getLogger("automation_executor")


class AutomationExecutor:
    # Proxy helpers for backward compatibility
    remove_vietnamese_accents = staticmethod(ExecutorHelpers.remove_vietnamese_accents)
    clean_douyin_title = staticmethod(ExecutorHelpers.clean_douyin_title)
    translate_to_vietnamese = staticmethod(ExecutorHelpers.translate_to_vietnamese)
    generate_hashtags = staticmethod(ExecutorHelpers.generate_hashtags)
    download_stream_to_file = staticmethod(ExecutorHelpers.download_stream_to_file)

    @staticmethod
    def _run_crawler_in_proactor(channel_url: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Chạy crawler Douyin trong ProactorEventLoop riêng biệt trên Windows."""
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            crawler = DouyinChannelCrawler()
            res = loop.run_until_complete(crawler.crawl_today_videos(channel_url, limit=limit))
            return res.get("videos", []) if isinstance(res, dict) else (res or [])
        finally:
            loop.close()

    @classmethod
    async def crawl_channel_videos(cls, channel_url: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Quét video của một kênh Douyin an toàn không lỗi event loop."""
        return await asyncio.to_thread(cls._run_crawler_in_proactor, channel_url, limit)

    @classmethod
    async def _publish_to_facebook(
        cls, pages: List[Dict[str, Any]], video_path: str, caption: str, post_type: str = "reel"
    ) -> List[Dict[str, Any]]:
        """Đăng Reels / Bài viết lên danh sách Fanpage Facebook đã chọn."""
        results: List[Dict[str, Any]] = []
        for p in pages:
            page_id = str(p.get("page_id"))
            page_name = p.get("page_name", f"Page {page_id}")
            token = p.get("access_token")
            p_type = p.get("post_type") or post_type
            try:
                logger.info(f"Đang đăng {p_type} lên Fanpage: {page_name} ({page_id})...")
                res = await FacebookService.publish_reel(
                    PublishReelRequest(page_id=page_id, video_path=video_path, caption=caption, access_token=token, post_type=p_type)
                )
                results.append({
                    "page_id": page_id, "page_name": page_name,
                    "success": res.success, "video_id": res.video_id,
                    "reel_url": res.reel_url, "error": None if res.success else res.message,
                })
            except Exception as fb_err:
                logger.error(f"Lỗi đăng lên Fanpage {page_name}: {fb_err}")
                results.append({
                    "page_id": page_id, "page_name": page_name,
                    "success": False, "video_id": None, "reel_url": None, "error": str(fb_err),
                })
        return results

    @classmethod
    async def _publish_to_youtube(
        cls,
        user_id: str,
        channels: List[Dict[str, Any]],
        video_path: str,
        title: str,
        description: str,
        video_type: str = "shorts",
    ) -> List[Dict[str, Any]]:
        """Tự động xuất bản video lên danh sách Kênh YouTube (Shorts hoặc Video dài 16:9)."""
        results: List[Dict[str, Any]] = []
        yt_service = YouTubeService()
        is_shorts = (video_type == "shorts")
        clean_title = title.strip()
        if is_shorts and "#shorts" not in clean_title.lower():
            clean_title = (clean_title[:90] + " #shorts").strip() if len(clean_title) > 90 else f"{clean_title} #shorts"
        else:
            clean_title = clean_title[:100].strip()

        # Nếu không chỉ định kênh, mặc định đăng lên kênh đầu tiên của user
        channel_list = channels if channels else [{"channel_id": None, "channel_title": "Kênh YouTube"}]

        for ch in channel_list:
            ch_id = ch.get("channel_id")
            ch_title = ch.get("channel_title") or f"Kênh {ch_id or ''}"
            ch_vtype = ch.get("video_type") or video_type
            try:
                logger.info(f"Đang đăng video ({ch_vtype}) lên YouTube kênh '{ch_title}' ({ch_id})...")
                res = await yt_service.publish_shorts(
                    user_id=user_id,
                    req=PublishShortsRequest(
                        channel_id=ch_id,
                        video_path=video_path,
                        title=clean_title,
                        description=description,
                        privacy_status="public",
                        video_type=ch_vtype,
                    ),
                )
                results.append({
                    "channel_id": ch_id, "channel_title": ch_title, "success": res.success,
                    "video_id": res.video_id, "shorts_url": res.shorts_url, "watch_url": res.watch_url,
                    "video_type": ch_vtype, "error": res.error,
                })
            except Exception as yt_err:
                logger.error(f"Lỗi xuất bản YouTube kênh '{ch_title}': {yt_err}")
                results.append({
                    "channel_id": ch_id, "channel_title": ch_title, "success": False,
                    "video_id": None, "shorts_url": None, "error": str(yt_err),
                })
        return results

    @classmethod
    async def process_and_publish_video(
        cls,
        campaign: Dict[str, Any],
        video_item: Dict[str, Any],
        source_name: str,
        post_number: int = 1,
    ) -> Dict[str, Any]:
        """Quy trình bóc tách, dịch thuật, xử lý video và tự động đăng lên Facebook & YouTube."""
        raw_title = (video_item.get("title") or "").strip()
        if re.match(r"^Video\s*\d+$", raw_title, flags=re.IGNORECASE):
            raw_title = ""

        video_url = video_item.get("video_url") or f"https://www.douyin.com/video/{video_item.get('item_id')}"
        item_id = str(video_item.get("item_id", uuid.uuid4().hex[:8]))
        user_id = campaign.get("user_id", "default_user")

        # 1. Xác định Tiêu đề bài đăng: Ưu tiên 'Bài đăng {n}' chống trùng lặp tên Douyin rác
        is_dual_source = bool((campaign.get("dual_source") or {}).get("enabled"))
        title_mode = campaign.get("title_mode", "auto_number" if is_dual_source else "auto_number")
        prefix = (campaign.get("custom_title_prefix") or "Bài đăng").strip()

        translated_title = await ExecutorHelpers.translate_to_vietnamese(raw_title) if raw_title else ""
        if translated_title in ["Video Mới Cực Hot", "Video Douyin Mới"]:
            translated_title = ""

        if title_mode == "auto_number" or not translated_title:
            base_title = f"{prefix} {post_number}"
        else:
            base_title = translated_title

        # 2. Xây dựng Hashtags (Nếu auto_number thì chỉ dùng config_hashtags)
        tags_str = ExecutorHelpers.generate_hashtags(
            title=translated_title if title_mode != "auto_number" else "",
            config_hashtags=campaign.get("hashtags"),
            auto_add_title_tag=bool(translated_title and campaign.get("auto_add_title_tag", True) and title_mode != "auto_number"),
        )

        caption_tpl = campaign.get("caption_template", "{title}")
        caption_body = caption_tpl.replace("{title}", base_title).strip()
        final_caption = f"{caption_body}\n\n{tags_str}".strip() if tags_str else caption_body

        if re.search(r"[\u4e00-\u9fff]", final_caption):
            final_caption = re.sub(r"[\u4e00-\u9fff]", "", final_caption).strip()
            final_caption = re.sub(r"#\s+", "", final_caption)
            final_caption = re.sub(r"#$", "", final_caption).strip()

        # Ghép tiêu đề kèm đầy đủ hashtags cho YouTube Shorts (tối đa 100 ký tự)
        yt_title = base_title
        if tags_str:
            combined = f"{base_title} {tags_str}".strip()
            yt_title = combined if len(combined) <= 100 else f"{combined[:97].strip()}..."

        # 3. Trích xuất luồng MP4 sạch logo: Ưu tiên dùng ngay stream URL đã bắt được khi quét kênh
        clean_stream_url = video_item.get("clean_stream_url")
        music_url = video_item.get("music_url")
        if not clean_stream_url:
            extracted_info = await DouyinExtractor.extract_no_watermark_video(video_url)
            clean_stream_url = extracted_info.get("video_url")
            music_url = extracted_info.get("music_url") or music_url
            ext_author = extracted_info.get("author", {})
            ext_sec, ext_uid = ext_author.get("sec_uid"), ext_author.get("uid")
            ext_nick = (ext_author.get("nickname") or "").strip()
        else:
            logger.info(f"Đã có sẵn luồng MP4 sạch từ lúc quét kênh cho video {item_id}, bỏ qua mở browser lại!")
            ext_sec, ext_uid = video_item.get("author_sec_uid"), None
            ext_nick = (video_item.get("author_nickname") or "").strip()

        if not clean_stream_url:
            raise ValueError(f"Không thể lấy luồng video sạch logo cho item {item_id}")

        expected_sec = video_item.get("author_sec_uid")
        expected_nick = (video_item.get("author_nickname") or "").strip()

        clean_ext = re.sub(r"[@\s]|认证徽章|徽章", "", ext_nick).strip().lower()
        clean_exp = re.sub(r"[@\s]|认证徽章|徽章", "", expected_nick).strip().lower()

        # Loại bỏ các giá trị điều hướng rác của giao diện Douyin (như /user/self hoặc '我的')
        if ext_sec and not ext_sec.startswith("MS4wLjAB"):
            ext_sec = None
        if clean_ext in ["我的", "self", "首页", "douyin creator"]:
            clean_ext = ""

        is_mismatch = False
        if expected_sec and ext_sec:
            is_mismatch = (ext_sec != expected_sec)
        elif clean_ext and clean_exp and clean_ext != "douyin creator" and clean_exp != "douyin creator":
            if clean_ext == clean_exp or clean_ext in clean_exp or clean_exp in clean_ext:
                is_mismatch = False
            elif not expected_sec:
                is_mismatch = True

        if is_mismatch:
            err_msg = (
                f"TƯỜNG LỬA CHẶN ĐỨNG: Video {item_id} có tác giả '{ext_nick}' "
                f"({ext_sec or ext_uid}) KHÔNG KHỚP với kênh nguồn '{source_name}' ({expected_sec})! "
                "Hệ thống đã HỦY XUẤT BẢN NGAY LẬP TỨC để bảo vệ uy tín kênh!"
            )
            logger.error(err_msg)
            raise ValueError(err_msg)

        temp_dir = settings.TEMP_DIR / "automation"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local_mp4_path = str(temp_dir / f"auto_{item_id}_{uuid.uuid4().hex[:6]}.mp4")
        await asyncio.to_thread(ExecutorHelpers.download_stream_to_file, clean_stream_url, local_mp4_path)

        processing_mode = campaign.get("processing_mode", "download_only")
        ready_video_path = local_mp4_path

        # Nếu chọn chế độ Vietsub hoặc Thuyết minh AI -> Chạy pipeline render phụ đề & giọng đọc
        # Nếu chọn Mô hình 2 (download_only) -> Lách pHash, xóa metadata & mix BGM bản quyền sạch
        try:
            if processing_mode in ["vietsub", "dubbing", "both"]:
                ready_video_path = await ExecutorHelpers.render_dubbed_video_for_automation(
                    local_video_path=local_mp4_path,
                    campaign=campaign,
                    item_id=item_id,
                    music_url=music_url,
                )
            elif processing_mode == "download_only":
                ready_video_path = await ReupTransformer.transform_for_automation(
                    local_video_path=local_mp4_path,
                    campaign=campaign,
                    item_id=item_id,
                )

            ready_video_path = await ReupTransformer.apply_dual_source_stitch_if_enabled(
                ready_video_path, campaign, item_id
            )

            # 4. Xuất bản lên Fanpage Facebook (nếu có chọn)
            target_pages = campaign.get("target_pages", [])
            fb_type = campaign.get("fb_post_type", "reel")
            published_pages = await cls._publish_to_facebook(target_pages, ready_video_path, final_caption, post_type=fb_type)

            # 5. Xuất bản lên Kênh YouTube (nếu có chọn hoặc bật)
            target_yt_channels = campaign.get("target_youtube_channels", [])
            publish_to_yt = campaign.get("publish_to_youtube", False) or len(target_yt_channels) > 0
            yt_type = campaign.get("youtube_video_type", "shorts")
            published_youtube: List[Dict[str, Any]] = []

            if publish_to_yt:
                published_youtube = await cls._publish_to_youtube(
                    user_id=user_id,
                    channels=target_yt_channels,
                    video_path=ready_video_path,
                    title=yt_title,
                    description=final_caption,
                    video_type=yt_type,
                )
        finally:
            for p in {local_mp4_path, ready_video_path}:
                if p and os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass

        return {
            "video_item_id": item_id,
            "video_url": video_url,
            "video_original_title": raw_title,
            "video_translated_title": base_title,
            "source_channel_name": source_name,
            "caption": final_caption,
            "processing_mode": processing_mode,
            "published_pages": published_pages,
            "published_youtube_channels": published_youtube,
            "published_youtube": published_youtube[0] if published_youtube else None,
        }
