import re
import logging
import datetime
from typing import List, Dict, Any, Optional

from src.modules.creator.automation.repository import AutomationMongoRepository
from src.modules.creator.automation.executor import AutomationExecutor
from src.modules.creator.automation.automation_notifier import AutomationNotifier
from src.modules.creator.automation.schemas import (
    AutomationCampaignCreateRequest,
    AutomationCampaignUpdateRequest,
)
from src.modules.shared.ws.notification_ws import notify_user
from src.core.utils.date_utils import get_vn_now, to_vn_iso

logger = logging.getLogger("automation_service")


class AutomationService:
    def __init__(self, repo: Optional[AutomationMongoRepository] = None):
        self.repo = repo or AutomationMongoRepository()

    async def create_campaign(self, user_id: str, req: AutomationCampaignCreateRequest) -> Dict[str, Any]:
        return await self.repo.create_campaign(user_id, req.model_dump())

    async def get_user_campaigns(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.repo.get_user_campaigns(user_id)

    async def get_campaign(self, campaign_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return await self.repo.get_campaign_by_id(campaign_id, user_id)

    async def update_campaign(self, campaign_id: str, user_id: str, req: AutomationCampaignUpdateRequest) -> Optional[Dict[str, Any]]:
        update_dict = {k: v for k, v in req.model_dump().items() if v is not None}
        return await self.repo.update_campaign(campaign_id, user_id, update_dict)

    async def delete_campaign(self, campaign_id: str, user_id: str) -> bool:
        return await self.repo.delete_campaign(campaign_id, user_id)

    async def toggle_active(self, campaign_id: str, user_id: str, is_active: bool) -> Optional[Dict[str, Any]]:
        return await self.repo.toggle_active(campaign_id, user_id, is_active)

    async def get_logs(self, user_id: str, campaign_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.repo.get_logs(user_id, campaign_id, limit)

    async def get_posted_videos(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return await self.repo.get_posted_videos(user_id, limit)

    async def clear_campaign_error(self, campaign_id: str, user_id: str) -> bool:
        return await self.repo.clear_campaign_error(campaign_id, user_id)

    async def run_campaign_now(self, campaign_id: str, user_id: str) -> Dict[str, Any]:
        """Kích hoạt chạy ngay 1 chu kỳ cào & đăng video mà không cần đợi lịch hẹn."""
        campaign = await self.repo.acquire_campaign_lock(campaign_id, user_id)
        if not campaign:
            raise ValueError("Chiến dịch đang trong tiến trình xử lý, vui lòng chờ chu kỳ hiện tại hoàn tất!")

        # Xóa vệt lỗi cũ ngay khi bấm chạy để reset trạng thái sạch sẽ
        await self.repo.clear_campaign_error(campaign_id, user_id)
        return await self.execute_campaign_cycle(campaign)

    async def execute_campaign_cycle(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        """Thực thi một chu kỳ cào video mới và đăng lên Facebook cho một chiến dịch."""
        campaign_id = campaign["id"]
        user_id = campaign["user_id"]
        interval = campaign.get("crawl_interval_minutes") or 30
        source_channels = campaign.get("source_channels") or []
        only_new = campaign.get("only_new_unprocessed", True)
        only_today = campaign.get("only_today", True)
        max_age_hours = float(campaign.get("max_video_age_hours") if campaign.get("max_video_age_hours") is not None else (24 if only_today else 0))
        max_videos = campaign.get("max_videos_per_crawl") or 1

        now_dt = get_vn_now()
        now_str = to_vn_iso(now_dt)
        next_run_str = to_vn_iso(now_dt + datetime.timedelta(minutes=interval))

        # Đánh dấu trạng thái đang chạy
        await self.repo.update_campaign_run_state(campaign_id, status="running")
        await notify_user(
            user_id=user_id,
            event_type="AUTOMATION_CYCLE_STARTED",
            data={"campaign_id": campaign_id, "campaign_name": campaign.get("name", "")},
        )

        total_new_posted = 0
        cycle_errors: List[str] = []

        try:
            if (campaign.get("dual_source") or {}).get("enabled"):
                from src.modules.creator.automation.dual_source_worker import DualSourceWorker
                await DualSourceWorker().harvest_hook_channel(campaign)

            for ch in source_channels:
                ch_url = ch.get("channel_url")
                ch_name = ch.get("name") or "Kênh Nguồn"
                if not ch_url:
                    continue

                logger.info(f"[{campaign.get('name')}] Đang quét kênh nguồn: {ch_name}...")
                await AutomationNotifier.notify_crawl_started(user_id, campaign_id, campaign.get("name", ""), ch_name, ch_url)
                try:
                    crawled_videos = await AutomationExecutor.crawl_channel_videos(ch_url, limit=12)
                except Exception as crawl_err:
                    err_msg = f"Lỗi cào kênh {ch_name}: {str(crawl_err)}"
                    logger.warning(err_msg)
                    cycle_errors.append(err_msg)
                    continue

                # Sắp xếp video theo thời gian mới nhất lên đầu tiên
                crawled_videos.sort(key=lambda x: x.get("created_timestamp", 0), reverse=True)

                target_videos = []
                now_ts = now_dt.timestamp()
                for v in crawled_videos:
                    item_id = str(v.get("item_id", ""))
                    if not item_id:
                        continue

                    # 1. Lọc theo độ mới (Cửa sổ thời gian trôi: max_video_age_hours)
                    if max_age_hours > 0:
                        create_ts = int(v.get("created_timestamp") or 0)
                        if create_ts > 0:
                            age_hours = (now_ts - create_ts) / 3600.0
                            if age_hours > max_age_hours:
                                logger.info(f"[{ch_name}] Video {item_id} đăng cách đây {age_hours:.1f}h (> {max_age_hours}h). Bỏ qua!")
                                continue
                        elif only_today and not v.get("is_today", False):
                            logger.info(f"[{ch_name}] Video {item_id} không thuộc hôm nay. Bỏ qua!")
                            continue

                    # 2. Kiểm tra video đã từng được lưu/đăng hoặc đang được xử lý chưa (liên thông DB)
                    if only_new:
                        video_url = v.get("video_url", f"https://www.douyin.com/video/{item_id}")
                        already = await self.repo.is_video_already_posted(
                            user_id=user_id,
                            video_item_id=item_id,
                            video_url=video_url,
                            only_today=False,
                        )
                        if already:
                            logger.info(f"[{ch_name}] Video {item_id} đã có trong DB hoặc đang xử lý. Bỏ qua, xét video tiếp theo!")
                            continue

                    target_videos.append(v)
                    if len(target_videos) >= max_videos:
                        break

                logger.info(f"[{campaign.get('name')}] Tìm thấy {len(target_videos)} video mới nhất từ {ch_name}")

                for v in target_videos:
                    item_id = str(v.get("item_id", ""))
                    video_url = v.get("video_url") or f"https://www.douyin.com/video/{item_id}"
                    raw_title = (v.get("title") or "").strip()
                    if re.match(r"^Video\s*\d+$", raw_title, flags=re.IGNORECASE):
                        raw_title = ""
                    notify_title = raw_title or "Video không tiêu đề"
                    await AutomationNotifier.notify_video_discovered(
                        user_id, campaign_id, campaign.get("name", ""), ch_name, ch_url, item_id, video_url, notify_title, v.get("cover_url")
                    )

                    # 1. KHÓA CHỐNG TRÙNG LẶP: Đánh dấu ngay vào Database trạng thái 'processing'
                    # Các chu kỳ quét tiếp theo sẽ thấy video đang được xử lý và bỏ qua ngay lập tức!
                    log_doc = await self.repo.create_log({
                        "campaign_id": campaign_id,
                        "campaign_name": campaign.get("name", "Chiến dịch"),
                        "user_id": user_id,
                        "source_channel_name": ch_name,
                        "video_item_id": item_id,
                        "video_url": video_url,
                        "video_original_title": raw_title,
                        "video_translated_title": "",
                        "processing_mode": campaign.get("processing_mode", "vietsub"),
                        "status": "processing",
                        "published_pages": [],
                        "published_youtube_channels": [],
                        "details": "Đang trong tiến trình bóc tách, dịch thuật và xuất bản...",
                    })
                    log_id = str(log_doc.get("id") or log_doc.get("_id") or "")

                    try:
                        current_post_num = int(campaign.get("total_posted", 0)) + total_new_posted + 1
                        res = await AutomationExecutor.process_and_publish_video(
                            campaign=campaign,
                            video_item=v,
                            source_name=ch_name,
                            post_number=current_post_num,
                        )

                        # Xác định trạng thái tổng thể lượt đăng (Facebook + YouTube Đa Kênh)
                        pub_pages = res.get("published_pages", [])
                        pub_yt_list = res.get("published_youtube_channels") or ([] if not res.get("published_youtube") else [res.get("published_youtube")])
                        successful_pages = [p for p in pub_pages if p.get("success")]
                        successful_yt = [y for y in pub_yt_list if y.get("success")]

                        total_targets = len(pub_pages) + len(pub_yt_list)
                        total_success = len(successful_pages) + len(successful_yt)

                        if total_success == total_targets and total_targets > 0:
                            log_status = "success"
                            total_new_posted += 1
                        elif total_success > 0:
                            log_status = "partial"
                            total_new_posted += 1
                        else:
                            log_status = "failed"

                        # Lưu video đã đăng vào database chống trùng lặp tuyệt đối
                        if log_status in ["success", "partial"]:
                            await self.repo.record_posted_video(
                                user_id=user_id,
                                data={
                                    "campaign_id": campaign_id, "campaign_name": campaign.get("name", "Chiến dịch"),
                                    "video_item_id": res["video_item_id"], "video_url": res.get("video_url") or video_url,
                                    "channel_name": ch_name, "title_original": res["video_original_title"],
                                    "title_translated": res["video_translated_title"], "processing_mode": res["processing_mode"],
                                    "published_pages": pub_pages, "published_youtube_channels": pub_yt_list,
                                    "published_youtube": pub_yt_list[0] if pub_yt_list else None,
                                },
                            )
                            await AutomationNotifier.notify_publish_success(
                                user_id=user_id, campaign_id=campaign_id, campaign_name=campaign.get("name", ""),
                                ch_name=ch_name, ch_url=ch_url, video_item_id=res["video_item_id"],
                                video_url=res.get("video_url") or video_url, orig_title=res["video_original_title"],
                                trans_title=res["video_translated_title"], pub_pages=pub_pages, pub_yt=pub_yt_list,
                                cover_url=v.get("cover_url"),
                            )

                        # Cập nhật log từ 'processing' sang trạng thái kết quả chính thức
                        await self.repo.update_log(log_id, {
                            "video_original_title": res["video_original_title"],
                            "video_translated_title": res["video_translated_title"],
                            "processing_mode": res["processing_mode"], "caption": res["caption"], "status": log_status,
                            "published_pages": pub_pages, "published_youtube_channels": pub_yt_list,
                            "details": f"Xuất bản thành công {total_success}/{total_targets} kênh đích",
                            "error": None if log_status != "failed" else "Lỗi xuất bản mạng xã hội",
                        })

                    except Exception as proc_err:
                        err_msg = f"Lỗi xử lý video {item_id}: {str(proc_err)}"
                        logger.error(err_msg)
                        cycle_errors.append(err_msg)
                        await AutomationNotifier.notify_error_alert(
                            user_id=user_id, campaign_id=campaign_id, campaign_name=campaign.get("name", ""),
                            item_id=item_id, error_msg=str(proc_err), ch_name=ch_name,
                        )
                        await self.repo.update_log(log_id, {
                            "status": "failed", "error": str(proc_err), "details": f"Thất bại: {str(proc_err)[:200]}",
                        })

            # Hoàn tất chu kỳ
            last_err = "; ".join(cycle_errors) if cycle_errors else None
            await self.repo.update_campaign_run_state(
                campaign_id=campaign_id,
                status="idle",
                last_run_at=now_str,
                next_run_at=next_run_str,
                increment_posted=total_new_posted,
                error=last_err,
            )

            # Bắn WebSocket realtime kết thúc chu kỳ
            await notify_user(
                user_id=user_id,
                event_type="AUTOMATION_CYCLE_COMPLETED",
                data={
                    "campaign_id": campaign_id,
                    "total_posted": total_new_posted,
                    "next_run_at": next_run_str,
                },
            )

            return {
                "success": True,
                "campaign_id": campaign_id,
                "total_posted": total_new_posted,
                "errors": cycle_errors,
                "next_run_at": next_run_str,
            }

        except Exception as global_err:
            logger.error(f"Lỗi toàn cục chu kỳ campaign {campaign_id}: {global_err}")
            await self.repo.update_campaign_run_state(
                campaign_id=campaign_id,
                status="error",
                last_run_at=now_str,
                next_run_at=next_run_str,
                error=str(global_err),
            )
            return {"success": False, "error": str(global_err)}

