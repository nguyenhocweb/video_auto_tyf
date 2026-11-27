import os
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from src.core.config import settings
from src.core.engines.dubbing.video_mixer import DubbingVideoMixer
from src.modules.creator.bgm.service import BgmService

logger = logging.getLogger(__name__)


class ReupTransformer:
    """Xử lý biến đổi video cho Mô hình 2 (Lách pHash & Mix BGM bản quyền sạch)."""

    @classmethod
    async def transform_for_automation(
        cls,
        local_video_path: str,
        campaign: Dict[str, Any],
        item_id: str,
    ) -> str:
        """
        Thực hiện Mô hình 2:
        - Lấy thời lượng video nguồn.
        - Random 1 bài BGM từ danh sách user chọn (selected_bgm_ids) hoặc kho nhạc,
          ưu tiên chọn bài có thời lượng âm thanh >= video.
        - Cắt bỏ phần âm thanh dư thừa, fade out 2s cuối, zoom 1.04x lách pHash.
        """
        try:
            temp_dir = settings.TEMP_DIR / "automation_reup"
            temp_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(temp_dir / f"reup_{item_id}_{uuid.uuid4().hex[:6]}.mp4")

            video_dur = DubbingVideoMixer.get_media_duration(local_video_path)
            selected_ids = campaign.get("selected_bgm_ids") or []
            bgm_vol = float(campaign.get("bgm_volume") or 0.95)
            user_id = campaign.get("user_id")
            keep_orig_audio = bool(campaign.get("keep_original_audio", False))

            bgm_file_path: Optional[str] = None
            orig_audio_vol: float = 0.15

            if keep_orig_audio:
                logger.info(
                    f"Chiến dịch được thiết lập [Giữ nguyên âm thanh gốc], bảo toàn 100% tiếng & nhạc gốc cho video {item_id}"
                )
                bgm_file_path = None
                orig_audio_vol = 1.0
            else:
                bgm_service = BgmService()
                chosen_track, resolved_bgm = await bgm_service.pick_and_resolve_random_bgm(
                    user_id=user_id,
                    candidate_ids=selected_ids if len(selected_ids) > 0 else None,
                    min_duration=video_dur,
                )

                if chosen_track and resolved_bgm:
                    bgm_file_path = resolved_bgm
                    logger.info(
                        f"Đã chọn BGM '{chosen_track.get('title')}' "
                        f"(thời lượng {chosen_track.get('duration')}s vs video {video_dur:.1f}s) cho video {item_id}"
                    )
                else:
                    logger.warning(f"Không có bài BGM khả dụng cho video {item_id}, render biến đổi visual không kèm BGM mới.")

            final_path = DubbingVideoMixer.transform_reup_video(
                video_path=local_video_path,
                output_path=output_path,
                bgm_path=bgm_file_path,
                bgm_volume=bgm_vol,
                orig_audio_volume=orig_audio_vol,
                zoom_factor=1.04,
            )
            return final_path
        except Exception as e:
            logger.error(f"Lỗi khi biến đổi Re-up Mô hình 2 cho video {item_id}: {e}", exc_info=True)
            return local_video_path

    @classmethod
    async def apply_dual_source_stitch_if_enabled(
        cls,
        local_video_path: str,
        campaign: Dict[str, Any],
        item_id: str,
    ) -> str:
        """Nếu chiến dịch bật Dual Source Stitching, tiến hành ghép Hook Nguồn 1 vào Body Nguồn 2."""
        dual_cfg = campaign.get("dual_source") or {}
        if not dual_cfg.get("enabled"):
            return local_video_path

        try:
            from src.modules.creator.automation.dual_source_worker import DualSourceWorker
            worker = DualSourceWorker()
            stitched = await worker.prepare_stitched_video(
                campaign=campaign,
                body_video_path=local_video_path,
                body_item_id=item_id,
            )
            return stitched or local_video_path
        except Exception as ex:
            logger.error(f"Lỗi khi ghép 2 nguồn cho video {item_id}: {ex}")
            return local_video_path


