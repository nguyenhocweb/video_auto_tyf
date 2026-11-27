import os
import uuid
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from src.core.config import settings
from src.core.utils.date_utils import get_vn_now
from src.core.engines.stitch.video_stitcher import VideoStitcher
from src.core.engines.douyin.extractor import DouyinExtractor
from src.modules.creator.automation.hook_pool_repo import HookPoolMongoRepository
from src.modules.creator.automation.executor_helpers import ExecutorHelpers

logger = logging.getLogger("dual_source_worker")


class DualSourceWorker:
    """Worker chuyên trách thu hoạch Kênh Hook (Nguồn 1) và ghép nối vào Kênh Body (Nguồn 2)."""

    def __init__(self, hook_repo: Optional[HookPoolMongoRepository] = None):
        self._hook_repo = hook_repo

    @property
    def hook_repo(self) -> HookPoolMongoRepository:
        if self._hook_repo is None:
            self._hook_repo = HookPoolMongoRepository()
        return self._hook_repo

    async def harvest_hook_channel(self, campaign: Dict[str, Any]) -> int:
        """Quét Kênh Hook (hỗ trợ nhiều kênh), tải video mới nhất, cắt đoạn đầu và nạp vào kho đệm."""
        dual_cfg = campaign.get("dual_source") or {}
        if not dual_cfg.get("enabled"):
            return 0

        hook_channels = dual_cfg.get("hook_channels") or []
        if not hook_channels and dual_cfg.get("hook_channel_url"):
            hook_channels = [{
                "channel_url": dual_cfg["hook_channel_url"],
                "name": dual_cfg.get("hook_channel_name") or "Kênh Hook",
            }]

        if not hook_channels:
            return 0

        campaign_id = str(campaign.get("id") or campaign.get("_id") or "")
        user_id = str(campaign.get("user_id", "default_user"))
        hook_duration = float(dual_cfg.get("hook_duration_sec") or 3.5)
        total_harvested = 0

        now_dt = get_vn_now()
        now_ts = now_dt.timestamp()
        max_age_hours = float(campaign.get("max_video_age_hours") if campaign.get("max_video_age_hours") is not None else 24)
        only_today = bool(campaign.get("only_today", True))

        for target_ch in hook_channels:
            ch_url = target_ch.get("channel_url")
            ch_name = target_ch.get("name") or "Kênh Hook"
            if not ch_url:
                continue

            logger.info(f"[{campaign.get('name')}] Đang quét Kênh Hook [{ch_name}]...")
            try:
                from src.modules.creator.automation.executor import AutomationExecutor
                crawled = await AutomationExecutor.crawl_channel_videos(ch_url, limit=6)
            except Exception as ex:
                logger.warning(f"Không thể cào Kênh Hook {ch_name}: {ex}")
                continue

            if not crawled:
                continue

            crawled.sort(key=lambda x: x.get("created_timestamp", 0), reverse=True)

            for v in crawled:
                item_id = str(v.get("item_id", ""))
                if not item_id:
                    continue

                # Lọc theo khoảng thời gian video đăng (Độ mới)
                if max_age_hours > 0:
                    create_ts = int(v.get("created_timestamp") or 0)
                    if create_ts > 0:
                        age_hours = (now_ts - create_ts) / 3600.0
                        if age_hours > max_age_hours:
                            logger.info(f"[{ch_name}] Hook video {item_id} đăng cách đây {age_hours:.1f}h (> {max_age_hours}h). Bỏ qua!")
                            continue
                    elif only_today and not v.get("is_today", False):
                        continue

                already_saved = await self.hook_repo.is_hook_already_saved(campaign_id, item_id)
                if already_saved:
                    continue

                video_url = v.get("video_url") or f"https://www.douyin.com/video/{item_id}"
                stream_url = v.get("clean_stream_url")
                if not stream_url:
                    try:
                        info = await DouyinExtractor.extract_no_watermark_video(video_url)
                        stream_url = info.get("video_url")
                    except Exception as ex:
                        logger.warning(f"Lỗi extract hook video {item_id}: {ex}")
                        continue

                if not stream_url:
                    continue

                temp_hooks_dir = settings.TEMP_DIR / "hook_pool"
                temp_hooks_dir.mkdir(parents=True, exist_ok=True)
                raw_tmp_path = temp_hooks_dir / f"raw_hook_{item_id}_{uuid.uuid4().hex[:6]}.mp4"
                clipped_hook_path = temp_hooks_dir / f"hook_{campaign_id}_{item_id}.mp4"

                try:
                    await asyncio.to_thread(ExecutorHelpers.download_stream_to_file, stream_url, str(raw_tmp_path))
                    if not raw_tmp_path.exists() or raw_tmp_path.stat().st_size == 0:
                        continue

                    await asyncio.to_thread(
                        VideoStitcher.extract_hook_clip,
                        raw_video_path=str(raw_tmp_path),
                        duration=hook_duration,
                        out_path=str(clipped_hook_path),
                        aspect_ratio=dual_cfg.get("aspect_ratio") or "9:16",
                    )

                    await self.hook_repo.save_hook({
                        "campaign_id": campaign_id,
                        "user_id": user_id,
                        "item_id": item_id,
                        "video_url": video_url,
                        "title": v.get("title") or f"Hook {item_id}",
                        "hook_path": str(clipped_hook_path),
                        "duration": hook_duration,
                    })
                    total_harvested += 1
                    logger.info(f"Đã nạp thành công Hook [{item_id}] ({hook_duration}s) từ kênh [{ch_name}] vào kho!")
                    break
                except Exception as ex:
                    logger.error(f"Lỗi xử lý cắt Hook clip {item_id}: {ex}")
                finally:
                    if raw_tmp_path.exists():
                        try:
                            raw_tmp_path.unlink()
                        except Exception:
                            pass

        return total_harvested

    async def prepare_stitched_video(
        self,
        campaign: Dict[str, Any],
        body_video_path: str,
        body_item_id: str,
        bgm_file_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Lấy Hook từ kho đệm và ghép vào đầu video thân bài (Kênh 2).
        Trả về đường dẫn file đã ghép hoàn chỉnh, hoặc None nếu không thể ghép.
        """
        dual_cfg = campaign.get("dual_source") or {}
        if not dual_cfg.get("enabled"):
            return body_video_path

        campaign_id = str(campaign.get("id") or campaign.get("_id") or "")
        user_id = str(campaign.get("user_id", "default_user"))
        skip_sec = float(dual_cfg.get("body_skip_start_sec") or 3.0)
        audio_mode = str(dual_cfg.get("audio_mode") or "sequential")
        fallback_policy = str(dual_cfg.get("fallback_policy") or "reuse_oldest")

        hook_doc = await self.hook_repo.get_available_hook(campaign_id)
        if not hook_doc:
            logger.warning(
                f"[{campaign.get('name')}] Kho Hook hiện tại chưa có video mới! "
                f"Đang kích hoạt fallback: {fallback_policy}..."
            )
            hook_doc = await self.hook_repo.get_fallback_hook(campaign_id, policy=fallback_policy)

        if not hook_doc:
            if fallback_policy == "bypass":
                logger.info("Chính sách fallback là 'bypass': Tiến hành đăng video thân bài gốc.")
                return body_video_path
            logger.warning(f"Chính sách '{fallback_policy}': Không có Hook hợp lệ để ghép. Tạm hoãn video {body_item_id}.")
            return None

        hook_path = str(hook_doc.get("hook_path") or "")
        if not hook_path or not os.path.exists(hook_path):
            logger.warning(f"File Hook {hook_path} không tồn tại trên đĩa.")
            return body_video_path

        out_dir = settings.TEMP_DIR / "stitched_videos"
        out_dir.mkdir(parents=True, exist_ok=True)
        stitched_out = str(out_dir / f"stitched_{campaign_id}_{body_item_id}_{uuid.uuid4().hex[:6]}.mp4")

        # Nếu chọn chế độ đè BGM mà chưa có file BGM cụ thể -> Random bài hát từ danh sách đã chọn (tự tải từ Cloudinary)
        if audio_mode == "bgm_override" and not bgm_file_path:
            try:
                from src.modules.creator.bgm.service import BgmService
                bgm_service = BgmService()
                raw_bgm_ids = campaign.get("selected_bgm_ids")
                selected_ids = [str(i) for i in raw_bgm_ids] if isinstance(raw_bgm_ids, list) else []
                body_dur = VideoStitcher.get_media_duration(str(body_video_path))
                chosen, resolved_fp = await bgm_service.pick_and_resolve_random_bgm(
                    user_id=user_id,
                    candidate_ids=selected_ids if len(selected_ids) > 0 else None,
                    min_duration=body_dur,
                )
                if chosen and resolved_fp:
                    bgm_file_path = resolved_fp
                    logger.info(f"Đã chọn ngẫu nhiên bài BGM '{chosen.get('title')}' cho video ghép!")
                else:
                    logger.warning("Không tìm thấy bài BGM khả dụng cho video ghép Dual Source!")
            except Exception as ex:
                logger.warning(f"Không thể random bài BGM cho video ghép: {ex}")

        try:
            trans_sec = float(dual_cfg.get("transition_duration_sec") or 1.2)
            logger.info(
                f"Tiến hành ghép: Hook [{hook_doc.get('item_id')}] + "
                f"Body [{body_item_id}] (Bỏ {skip_sec}s đầu) | Audio: {audio_mode} | Trans: {trans_sec}s"
            )
            stitched_file = await asyncio.to_thread(
                VideoStitcher.stitch_hook_and_body,
                hook_path=hook_path,
                body_path=str(body_video_path),
                body_skip_sec=skip_sec,
                out_path=stitched_out,
                audio_mode=audio_mode,
                bgm_path=bgm_file_path,
                aspect_ratio=str(dual_cfg.get("aspect_ratio") or "9:16"),
                transition_duration=trans_sec,
            )

            hook_id = str(hook_doc.get("id") or "")
            await self.hook_repo.mark_hook_used(hook_id, body_item_id)
            return stitched_file
        except Exception as ex:
            logger.error(f"Lỗi trong quá trình ghép nối video: {ex}")
            return body_video_path
