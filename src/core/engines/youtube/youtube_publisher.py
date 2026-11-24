import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx
from src.core.config import settings
from src.core.engines.youtube.video_aspect_converter import VideoAspectConverter
from src.core.engines.youtube.youtube_auth import YouTubeAuthHelper, API_BASE, UPLOAD_BASE

logger = logging.getLogger("youtube_publisher")


class YouTubePublisher:
    """Engine lõi xử lý tải lên, truy vấn và quản lý video trên YouTube Data API v3."""

    # Ủy quyền các hàm OAuth sang YouTubeAuthHelper để đảm bảo chuẩn đơn trách nhiệm
    get_auth_url = staticmethod(YouTubeAuthHelper.get_auth_url)
    exchange_code_for_tokens = staticmethod(YouTubeAuthHelper.exchange_code_for_tokens)
    refresh_access_token = staticmethod(YouTubeAuthHelper.refresh_access_token)
    get_my_channel = staticmethod(YouTubeAuthHelper.get_my_channel)
    get_google_user_email = staticmethod(YouTubeAuthHelper.get_google_user_email)

    @staticmethod
    async def upload_shorts(
        access_token: str,
        video_path: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        privacy_status: str = "public",
        video_type: str = "video",
    ) -> Dict[str, Any]:
        """Tải video lên Kênh YouTube với cơ chế Resumable Upload protocol."""
        p = Path(video_path)
        if not p.exists():
            raise FileNotFoundError(f"Không tìm thấy file video: {video_path}")

        is_shorts = (video_type == "shorts")
        converted_file = None
        clean_title = title.strip()
        if is_shorts and "#shorts" not in clean_title.lower():
            clean_title = f"{clean_title} #shorts"

        if is_shorts:
            conv = VideoAspectConverter.ensure_vertical_9_16(str(p))
            if conv != str(p):
                converted_file = Path(conv)
                p = converted_file
        else:
            conv = VideoAspectConverter.ensure_horizontal_16_9(str(p))
            if conv != str(p):
                converted_file = Path(conv)
                p = converted_file

        file_size = p.stat().st_size
        headers = {
            "Authorization": f"Bearer {access_token.strip()}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        }

        body_meta = {
            "snippet": {
                "title": clean_title[:100],
                "description": description or f"{clean_title}\n\n#Shorts #Reels",
                "tags": tags or ["Shorts", "VideoAI"],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                init_url = f"{UPLOAD_BASE}/videos?uploadType=resumable&part=snippet,status"
                init_res = await client.post(init_url, headers=headers, json=body_meta)
                if init_res.status_code != 200:
                    raise ValueError(f"Lỗi khởi tạo upload YouTube: {init_res.text}")

                upload_url = init_res.headers.get("Location")
                if not upload_url:
                    raise ValueError("Không nhận được Upload Location từ YouTube.")

                with open(p, "rb") as f:
                    video_data = f.read()

                upload_headers = {
                    "Content-Type": "video/mp4",
                    "Content-Length": str(file_size),
                }

                upload_res = await client.put(upload_url, headers=upload_headers, content=video_data, timeout=600.0)
                if upload_res.status_code not in [200, 201]:
                    raise ValueError(f"Lỗi tải video lên YouTube: {upload_res.text}")

                result_data = upload_res.json()
                vid_id = str(result_data.get("id", ""))
                shorts_url = f"https://www.youtube.com/shorts/{vid_id}"
                watch_url = f"https://www.youtube.com/watch?v={vid_id}"

                return {
                    "video_id": vid_id,
                    "shorts_url": shorts_url,
                    "watch_url": watch_url,
                    "video_url": shorts_url if is_shorts else watch_url,
                    "video_type": "shorts" if is_shorts else "video",
                    "title": clean_title,
                    "status": privacy_status,
                }
        finally:
            if converted_file and converted_file.exists():
                try:
                    converted_file.unlink()
                except Exception:
                    pass

    @staticmethod
    async def get_channel_videos(
        access_token: str, channel_id: Optional[str] = None, max_results: int = 25
    ) -> List[Dict[str, Any]]:
        """Lấy danh sách video của kênh kèm thông tin thống kê, chế độ hiển thị và hạn chế bản quyền."""
        headers = {"Authorization": f"Bearer {access_token.strip()}"}
        uploads_id = None
        if channel_id and channel_id.startswith("UC"):
            uploads_id = "UU" + channel_id[2:]
        else:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(f"{API_BASE}/channels?part=contentDetails&mine=true", headers=headers)
                if res.status_code == 200:
                    items = res.json().get("items", [])
                    if items:
                        uploads_id = items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")

        if not uploads_id:
            return []

        async with httpx.AsyncClient(timeout=20.0) as client:
            pl_url = f"{API_BASE}/playlistItems?part=snippet,contentDetails&playlistId={uploads_id}&maxResults={max_results}"
            pl_res = await client.get(pl_url, headers=headers)
            if pl_res.status_code != 200:
                logger.warning(f"Lỗi lấy playlist uploads YouTube: {pl_res.text}")
                return []

            pl_items = pl_res.json().get("items", [])
            vid_ids = [it.get("contentDetails", {}).get("videoId") for it in pl_items if it.get("contentDetails", {}).get("videoId")]
            if not vid_ids:
                return []

            # Truy vấn chi tiết video bao gồm statistics, contentDetails và status (chế độ riêng tư, vi phạm bản quyền)
            v_url = f"{API_BASE}/videos?part=snippet,statistics,contentDetails,status&id={','.join(vid_ids)}"
            v_res = await client.get(v_url, headers=headers)
            detail_map = {}
            if v_res.status_code == 200:
                for v in v_res.json().get("items", []):
                    detail_map[v.get("id")] = v

            results = []
            for it in pl_items:
                vid_id = it.get("contentDetails", {}).get("videoId")
                if not vid_id:
                    continue
                snippet = it.get("snippet", {})
                v_detail = detail_map.get(vid_id, {})
                v_stats = v_detail.get("statistics", {})
                v_status = v_detail.get("status", {})
                c_details = v_detail.get("contentDetails", {})

                thumbs = snippet.get("thumbnails", {})
                thumb_url = thumbs.get("high", {}).get("url") or thumbs.get("medium", {}).get("url") or thumbs.get("default", {}).get("url")

                # Phân tích hạn chế bản quyền và kiểm duyệt
                upload_status = v_status.get("uploadStatus", "processed")
                rejection_reason = v_status.get("rejectionReason")
                region_restriction = c_details.get("regionRestriction", {})
                privacy = v_status.get("privacyStatus", "public")

                restriction = "none"
                restriction_detail = "Không có thông báo. Video này đang tiếp cận người xem và đủ điều kiện theo cài đặt của bạn."

                if rejection_reason in ["claim", "copyright"]:
                    restriction = "copyright"
                    restriction_detail = f"Khiếu nại bản quyền ({rejection_reason}). Video bị hạn chế hiển thị hoặc gỡ bỏ âm thanh."
                elif rejection_reason:
                    restriction = "rejected"
                    restriction_detail = f"Bị từ chối: {rejection_reason}."
                elif region_restriction.get("blocked"):
                    cnt = len(region_restriction.get("blocked", []))
                    restriction = "region_blocked"
                    restriction_detail = f"Hạn chế vùng: Bị chặn phát tại {cnt} quốc gia/vùng lãnh thổ do bản quyền."
                elif upload_status == "rejected":
                    restriction = "rejected"
                    restriction_detail = "Video bị từ chối phê duyệt trên YouTube."

                results.append({
                    "id": vid_id,
                    "title": snippet.get("title", "Video"),
                    "description": snippet.get("description", ""),
                    "thumbnail": thumb_url,
                    "published_at": snippet.get("publishedAt"),
                    "views": int(v_stats.get("viewCount", 0)),
                    "likes": int(v_stats.get("likeCount", 0)),
                    "comments": int(v_stats.get("commentCount", 0)),
                    "duration": c_details.get("duration", ""),
                    "privacy_status": privacy,
                    "restriction": restriction,
                    "restriction_detail": restriction_detail,
                    "shorts_url": f"https://www.youtube.com/shorts/{vid_id}",
                    "watch_url": f"https://www.youtube.com/watch?v={vid_id}",
                })
            return results

    @staticmethod
    async def delete_video(access_token: str, video_id: str) -> bool:
        """Xóa vĩnh viễn một video trên kênh YouTube qua API."""
        headers = {"Authorization": f"Bearer {access_token.strip()}"}
        url = f"{API_BASE}/videos?id={video_id.strip()}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.delete(url, headers=headers)
            if res.status_code in [200, 204]:
                logger.info(f"Đã xóa thành công video YouTube {video_id}")
                return True
            if res.status_code == 404:
                logger.warning(f"Video {video_id} đã không còn tồn tại trên YouTube (404)")
                return True
            raise ValueError(f"Lỗi xóa video YouTube: ({res.status_code}) {res.text}")
