import os
import shutil
import time
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from src.core.config import settings
from src.core.engines.facebook.facebook_reels_publisher import FacebookReelsPublisher
from src.core.engines.facebook.facebook_feed_publisher import FacebookFeedPublisher
from src.core.engines.facebook.facebook_token_helper import FacebookTokenHelper
from src.core.utils.video_resolver import resolve_local_video_path
from src.modules.creator.facebook.facebook_cache import FacebookCache
from src.modules.creator.facebook.schemas import (
    FacebookPageItem,
    FacebookVideoItem,
    FacebookPostItem,
    AvailableVideoItem,
    PublishReelRequest,
    PublishReelResponse,
    TokenStatusResponse,
    UpdateTokenRequest,
)

logger = logging.getLogger("facebook_service")


class FacebookService:
    @staticmethod
    async def get_token_status() -> TokenStatusResponse:
        """Kiểm tra tính hợp lệ và thời hạn sống của User Token."""
        info = await FacebookTokenHelper.inspect_token()
        is_valid = info.get("is_valid", False)
        expires_at = info.get("expires_at")
        data_access = info.get("data_access_expires_at")

        expires_in_days: Optional[float] = None
        expires_at_formatted: str = "Chưa kết nối Token"
        token_type_label: str = "Chưa kết nối"

        if is_valid:
            if expires_at == 0:
                token_type_label = "Token Vĩnh Viễn"
                expires_at_formatted = "Vĩnh viễn (Không bao giờ hết hạn)"
                expires_in_days = 9999.0
            elif isinstance(expires_at, int) and expires_at > 0:
                diff_sec = expires_at - int(time.time())
                if diff_sec > 0:
                    expires_in_days = round(diff_sec / 86400.0, 1)
                    dt = datetime.fromtimestamp(expires_at, tz=timezone(timedelta(hours=7)))
                    dt_str = dt.strftime("%d/%m/%Y %H:%M")
                    label = "Token Dài Hạn (60 ngày)" if expires_in_days >= 30 else "Token Trung Hạn"
                    token_type_label = label if expires_in_days >= 1 else "Token Ngắn Hạn"
                    expires_at_formatted = f"Còn {expires_in_days} ngày (Hết: {dt_str})"
                else:
                    is_valid = False
                    token_type_label = "Đã hết hạn"
                    expires_at_formatted = "Đã hết hạn"
        elif getattr(settings, "FB_USER_ACCESS_TOKEN", "").strip():
            token_type_label = "Token hết hạn"
            expires_at_formatted = "Đã hết hạn hoặc không hợp lệ"

        return TokenStatusResponse(
            is_valid=is_valid,
            has_token=bool(getattr(settings, "FB_USER_ACCESS_TOKEN", "").strip()),
            error=info.get("error"),
            expires_at=expires_at,
            scopes=info.get("scopes", []),
            expires_in_days=expires_in_days,
            expires_at_formatted=expires_at_formatted,
            token_type_label=token_type_label,
            data_access_expires_at=data_access,
        )

    @staticmethod
    async def update_user_token(req: UpdateTokenRequest) -> Dict[str, Any]:
        """Đổi User Token sang Long-Lived Token (60 ngày), lưu vào .env và đồng bộ Pages."""
        token_to_use = req.user_token.strip()
        days_valid = 60.0
        is_long_lived = False
        try:
            ex_res = await FacebookTokenHelper.exchange_to_long_lived_token(token_to_use)
            if ex_res.get("access_token"):
                token_to_use = ex_res["access_token"]
                days_valid = ex_res.get("expires_days", 60.0)
                is_long_lived = True
        except Exception as ex:
            logger.warning(f"Không thể nâng cấp sang Long-Lived: {ex}")

        FacebookTokenHelper.save_user_token_to_env(token_to_use)
        raw_pages = await FacebookReelsPublisher.get_managed_pages(user_token=token_to_use)
        pages = [FacebookPageItem(**p) for p in raw_pages]
        await FacebookCache.save_cached_pages(pages)

        msg = f"Đã gia hạn Token 60 ngày ({len(pages)} Pages)" if is_long_lived else f"Đã lưu Token ({len(pages)} Pages)"
        return {
            "success": True,
            "message": msg,
            "is_long_lived": is_long_lived,
            "days_valid": days_valid if is_long_lived else None,
            "pages_count": len(pages),
            "pages": [p.model_dump() for p in pages],
        }

    @staticmethod
    async def get_page_token(page_id: str) -> Optional[str]:
        """Lấy Page Access Token từ MongoDB cache, live pages hoặc .env."""
        cached_tok = await FacebookCache.get_page_token(page_id)
        if cached_tok:
            return cached_tok
        if str(page_id) == getattr(settings, "FB_PAGE_ID", "").strip():
            return getattr(settings, "FB_PAGE_ACCESS_TOKEN", "").strip()
        try:
            pages = await FacebookReelsPublisher.get_managed_pages()
            for p in pages:
                if str(p.get("id")) == str(page_id) and p.get("access_token"):
                    return p.get("access_token")
        except Exception:
            pass
        return None

    @staticmethod
    async def get_pages(force_refresh: bool = False) -> List[FacebookPageItem]:
        """Lấy danh sách tất cả các Trang Facebook (Ưu tiên Cache-First)."""
        if not force_refresh:
            cached = await FacebookCache.get_cached_pages()
            if cached:
                return cached
        try:
            raw_pages = await FacebookReelsPublisher.get_managed_pages()
            pages = [FacebookPageItem(**p) for p in raw_pages]
            if pages:
                await FacebookCache.save_cached_pages(pages)
                return pages
        except Exception as ex:
            logger.warning(f"Lỗi lấy Fanpage trực tiếp từ Meta: {ex}")
        return await FacebookCache.get_cached_pages()

    @staticmethod
    async def get_page_videos(
        page_id: str, limit: int = 25, force_refresh: bool = False
    ) -> List[FacebookVideoItem]:
        """Lấy danh sách video Fanpage (Ưu tiên Cache-First từ MongoDB)."""
        if not force_refresh:
            cached = await FacebookCache.get_cached_videos(page_id)
            if cached:
                return cached[:limit]
        token = await FacebookService.get_page_token(page_id)
        try:
            raw_videos = await FacebookReelsPublisher.get_page_videos(
                page_id=page_id, access_token=token, limit=limit
            )
            videos = [FacebookVideoItem(**v) for v in raw_videos]
            if videos:
                await FacebookCache.save_cached_videos(page_id, videos)
                return videos
        except Exception as ex:
            logger.warning(f"Lỗi lấy video trực tiếp từ Meta: {ex}")
        cached = await FacebookCache.get_cached_videos(page_id)
        return cached[:limit]

    @staticmethod
    async def get_page_posts(
        page_id: str, limit: int = 25, force_refresh: bool = False
    ) -> List[FacebookPostItem]:
        """Lấy danh sách bài viết Fanpage (Ưu tiên Cache-First từ MongoDB)."""
        if not force_refresh:
            cached = await FacebookCache.get_cached_posts(page_id)
            if cached:
                return cached[:limit]
        token = await FacebookService.get_page_token(page_id)
        try:
            raw_posts = await FacebookReelsPublisher.get_page_posts(
                page_id=page_id, access_token=token, limit=limit
            )
            posts = [FacebookPostItem(**p) for p in raw_posts]
            if posts:
                await FacebookCache.save_cached_posts(page_id, posts)
                return posts
        except Exception as ex:
            logger.warning(f"Lỗi lấy bài viết trực tiếp từ Meta: {ex}")
        cached = await FacebookCache.get_cached_posts(page_id)
        return cached[:limit]

    @staticmethod
    def get_available_rendered_videos() -> List[AvailableVideoItem]:
        """Quét kho video đã làm sạch / Dubbing để đăng Reels 1-Click."""
        results: List[AvailableVideoItem] = []
        scan_dirs = [
            (settings.DUBBING_OUTPUT_DIR, "Dubbing Hoàn thiện"),
            (settings.TEMP_DIR, "Video đã làm sạch"),
            (settings.AUDIO_OUTPUT_DIR, "Kho Media"),
        ]
        for scan_dir, source_label in scan_dirs:
            if not scan_dir.exists():
                continue
            for mp4_file in scan_dir.rglob("*.mp4"):
                try:
                    stat = mp4_file.stat()
                    if stat.st_size < 100 * 1024:
                        continue
                    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M")
                    results.append(
                        AvailableVideoItem(
                            id=mp4_file.name,
                            name=mp4_file.name,
                            path=str(mp4_file.resolve()),
                            size_mb=round(stat.st_size / (1024 * 1024), 2),
                            source=source_label,
                            modified_time=mtime,
                        )
                    )
                except Exception as ex:
                    logger.debug(f"Không thể đọc file {mp4_file}: {ex}")
        results.sort(key=lambda x: x.modified_time, reverse=True)
        return results[:30]

    @staticmethod
    async def publish_reel(req: PublishReelRequest) -> PublishReelResponse:
        """Đăng video lên Facebook (Hỗ trợ chọn Thước phim Reels hoặc Bài viết Feed Post)."""
        resolved_path = await resolve_local_video_path(req.video_path)
        token = req.access_token
        if not token and req.page_id:
            token = await FacebookService.get_page_token(req.page_id)

        post_type = getattr(req, "post_type", "reel") or "reel"
        if post_type == "feed":
            result = await FacebookFeedPublisher.publish_feed_video(
                video_path=resolved_path,
                caption=req.caption,
                title=getattr(req, "title", "") or "",
                page_id=req.page_id,
                access_token=token,
            )
            return PublishReelResponse(
                success=result.get("success", False),
                video_id=result.get("video_id", ""),
                page_id=result.get("page_id", ""),
                page_name=result.get("page_name", ""),
                caption=result.get("caption", ""),
                reel_url=result.get("post_url", ""),
                post_type="feed",
                message="Đã đăng thành công Bài viết video lên Fanpage!",
            )

        result = await FacebookReelsPublisher.publish_reel_from_file(
            video_path=resolved_path,
            caption=req.caption,
            page_id=req.page_id,
            access_token=token,
        )
        return PublishReelResponse(
            success=result.get("success", False),
            video_id=result.get("video_id", ""),
            page_id=result.get("page_id", ""),
            page_name=result.get("page_name", ""),
            caption=result.get("caption", ""),
            reel_url=result.get("reel_url", ""),
            post_type="reel",
            message="Đã đăng thành công Thước phim (Reel) lên Facebook!",
        )

    @staticmethod
    async def upload_and_publish_reel(
        file_bytes: bytes,
        filename: str,
        caption: str,
        page_id: Optional[str] = None,
        access_token: Optional[str] = None,
        post_type: str = "reel",
    ) -> PublishReelResponse:
        """Lưu file tải lên từ trình duyệt vào temp và xuất bản lên Facebook."""
        temp_dir = settings.TEMP_DIR / "fb_uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file_path = temp_dir / f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
        with open(temp_file_path, "wb") as f:
            f.write(file_bytes)
        req = PublishReelRequest(
            page_id=page_id,
            video_path=str(temp_file_path.resolve()),
            caption=caption,
            post_type=post_type,
            access_token=access_token,
        )
        return await FacebookService.publish_reel(req)
