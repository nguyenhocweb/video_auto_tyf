import os
import uuid
import httpx
import logging
from typing import Dict, Any
from src.core.engines.video.slot_slicer import SlotSlicerEngine
from src.modules.creator.video.slicer_schemas import (
    SliceVideoToTemplateRequest,
    SliceVideoToTemplateResponse,
    SlicedAssetResponse,
)

logger = logging.getLogger("slot_slicer_service")

# Duong dan storage goc tuyet doi den be/storage/temp
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_BE_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, "..", "..", ".."))
STORAGE_BASE = os.path.join(_BE_ROOT, "storage", "temp")

class VideoSlicerService:
    STORAGE_BASE = STORAGE_BASE

    @classmethod
    async def process_slice(cls, payload: SliceVideoToTemplateRequest) -> SliceVideoToTemplateResponse:
        job_id = uuid.uuid4().hex[:12]
        job_dir = os.path.join(cls.STORAGE_BASE, f"slicer_{job_id}")
        os.makedirs(job_dir, exist_ok=True)

        source_video_path = None

        # Truong hop 1: Co video_path
        if payload.video_path:
            candidates = [
                payload.video_path,
                os.path.join(_BE_ROOT, payload.video_path),
                os.path.abspath(payload.video_path),
            ]
            for cand in candidates:
                if os.path.exists(cand):
                    source_video_path = cand
                    break

        # Truong hop 2: Co video_url tu ngoai -> Tai ve truoc khi phan tich
        elif payload.video_url:
            download_dest = os.path.join(job_dir, "source_video.mp4")
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                )
            }
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True, headers=headers) as client:
                resp = await client.get(payload.video_url)
                if resp.status_code != 200:
                    raise ValueError(f"Khong the tai video tu URL (HTTP {resp.status_code})")
                with open(download_dest, "wb") as f:
                    f.write(resp.content)
            source_video_path = download_dest

        if not source_video_path or not os.path.exists(source_video_path):
            raise ValueError("Vui long cung cap duong dan video (video_path) hoac URL hop le.")

        # Xu ly slots mac dinh neu rong
        slots_data = [s.model_dump() for s in payload.slots]
        if not slots_data:
            slots_data = [
                {"id": "slot_1", "type": "image"},
                {"id": "slot_2", "type": "video", "duration": 2.0},
                {"id": "slot_3", "type": "image"},
                {"id": "slot_4", "type": "image"},
                {"id": "slot_5", "type": "video", "duration": 2.5},
                {"id": "slot_6", "type": "image"},
            ]

        # Thuc thi giai phau video
        raw_result = SlotSlicerEngine.slice_for_template(
            video_path=source_video_path,
            slots=slots_data,
            output_dir=job_dir,
        )

        # Build response URLs
        assets_res = []
        base_asset_url = f"/api/v1/creator/video/slicer-assets/{job_id}"
        for asset in raw_result["assets"]:
            assets_res.append(
                SlicedAssetResponse(
                    slot_id=asset["slot_id"],
                    index=asset["index"],
                    type=asset["type"],
                    file_name=asset["file_name"],
                    download_url=f"{base_asset_url}/{asset['file_name']}",
                    timestamp=asset["timestamp"],
                    duration=asset.get("duration"),
                )
            )

        zip_url = f"{base_asset_url}/{raw_result['zip_name']}"

        return SliceVideoToTemplateResponse(
            success=True,
            job_id=job_id,
            video_info=raw_result["video_info"],
            detected_scenes_count=raw_result["detected_scenes_count"],
            total_slots=len(assets_res),
            assets=assets_res,
            zip_download_url=zip_url,
            message=f"Da giai phau thanh cong {len(assets_res)} slots tai nguyen tu video!",
        )
