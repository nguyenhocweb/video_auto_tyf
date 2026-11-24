import os
import uuid
import base64
import urllib.request
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorDatabase

from src.core.config import settings
from src.core.engines.inspector import ImageAnalyzer, PolicyChecker, VideoPacingAnalyzer
from .schemas import (
    ImageInspectResponse,
    TextPolicyInspectResponse,
    VideoInspectResponse,
)
from .repository import InspectorMongoRepository

logger = logging.getLogger("inspector_service")


class InspectorService:
    """Service thực hiện các nghiệp vụ thẩm định vi phạm và dự đoán tiềm năng Viral."""

    def __init__(self, repo: Optional[InspectorMongoRepository] = None, db: Optional[AsyncIOMotorDatabase] = None):
        self.repo = repo if repo is not None else InspectorMongoRepository(db)

    async def inspect_image_bytes(
        self, user_id: str, image_bytes: bytes, filename: str = "upload.jpg"
    ) -> ImageInspectResponse:
        """Thẩm định ảnh từ dữ liệu nhị phân (Upload trực tiếp hoặc Paste Clipboard)."""
        temp_dir = settings.TEMP_DIR / "inspector"
        temp_dir.mkdir(parents=True, exist_ok=True)
        unique_file = temp_dir / f"img_{uuid.uuid4().hex[:8]}_{filename}"

        try:
            with open(unique_file, "wb") as f:
                f.write(image_bytes)

            # 1. Phân tích thị giác, khuôn mặt, chữ trên ảnh
            analysis = ImageAnalyzer.analyze_image(str(unique_file))

            # 2. Kiểm tra tỷ lệ da thịt 18+
            skin_check = PolicyChecker.check_image_skin_tone(str(unique_file))

            overall_score = analysis["overall_viral_score"]
            # Nếu tỷ lệ da thịt vượt ngưỡng an toàn, trừ điểm viral
            if not skin_check["is_safe"]:
                overall_score = max(10, overall_score - 25)
                analysis["actionable_advice"].insert(
                    0, f"CẢNH BÁO VI PHẠM: {skin_check.get('warning', 'Tỷ lệ da thịt quá cao, nguy cơ vi phạm 18+.')}"
                )

            res = ImageInspectResponse(
                overall_viral_score=overall_score,
                rating=ImageAnalyzer._get_rating_label(overall_score),
                face_analysis=analysis["face_analysis"],
                visual_analysis=analysis["visual_analysis"],
                text_analysis=analysis["text_analysis"],
                skin_safety=skin_check,
                actionable_advice=analysis["actionable_advice"],
            )

            # Lưu vào MongoDB
            await self.repo.save_record(
                user_id=user_id,
                inspect_type="image",
                score=overall_score,
                details=res.model_dump(),
                summary=f"Thẩm định ảnh {filename}: Điểm Viral {overall_score}/100",
            )
            return res

        finally:
            if unique_file.exists():
                try:
                    unique_file.unlink()
                except Exception:
                    pass

    async def inspect_image_payload(
        self, user_id: str, image_base64: Optional[str] = None, image_url: Optional[str] = None
    ) -> ImageInspectResponse:
        """Xử lý yêu cầu thẩm định ảnh từ Base64 hoặc Image URL."""
        if image_base64:
            clean_b64 = image_base64
            if "," in clean_b64:
                clean_b64 = clean_b64.split(",", 1)[1]
            img_bytes = base64.b64decode(clean_b64)
            return await self.inspect_image_bytes(user_id, img_bytes, "clipboard.jpg")

        if image_url:
            req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                img_bytes = resp.read()
            return await self.inspect_image_bytes(user_id, img_bytes, "downloaded.jpg")

        raise ValueError("Vui lòng cung cấp image_base64 hoặc image_url hợp lệ.")

    async def inspect_text(self, user_id: str, text: str) -> TextPolicyInspectResponse:
        """Kiểm tra từ ngữ nhạy cảm trong kịch bản."""
        audit = PolicyChecker.check_text(text)
        res = TextPolicyInspectResponse(**audit)
        await self.repo.save_record(
            user_id=user_id,
            inspect_type="text_policy",
            score=audit["safety_score"],
            details=res.model_dump(),
            summary=audit["summary"],
        )
        return res

    async def inspect_video(
        self, user_id: str, job_id: Optional[str] = None, video_url: Optional[str] = None
    ) -> VideoInspectResponse:
        """Thẩm định nhịp độ và vi phạm của video."""
        temp_dir = settings.TEMP_DIR / "inspector"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local_video = temp_dir / f"vid_{uuid.uuid4().hex[:8]}.mp4"
        subtitles_text = ""

        try:
            # Nếu có job_id, tìm video đã xử lý trong database
            if job_id:
                col = self.repo.db["dubbing_jobs"]
                job = await col.find_one({"_id": job_id})
                if not job:
                    from bson import ObjectId
                    try:
                        job = await col.find_one({"_id": ObjectId(job_id)})
                    except Exception:
                        pass

                if job:
                    # Lấy text phụ đề đã dịch
                    segments = job.get("segments", [])
                    subtitles_text = " ".join([s.get("text_translated", "") for s in segments])
                    cand_video = job.get("output_video_url") or job.get("video_url")
                    if cand_video and not video_url:
                        video_url = cand_video

            if not video_url:
                raise ValueError("Không tìm thấy đường link video hợp lệ để thẩm định.")

            # Tải video về thư mục tạm nếu là URL online
            if video_url.startswith("http"):
                req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=45) as resp, open(local_video, "wb") as f_out:
                    f_out.write(resp.read())
            elif os.path.exists(video_url):
                local_video = Path(video_url)

            # 1. Phân tích nhịp độ cắt cảnh
            pacing_res = VideoPacingAnalyzer.analyze_video_pacing(str(local_video))

            # 2. Phân tích vi phạm kịch bản
            policy_res = PolicyChecker.check_text(subtitles_text) if subtitles_text else {
                "is_safe": True, "safety_score": 100, "total_violations": 0, "violations": [], "summary": "Chưa có dữ liệu phụ đề để quét."
            }

            pacing_score = pacing_res["pacing_score"]
            policy_score = policy_res["safety_score"]
            composite_score = int(round(pacing_score * 0.55 + policy_score * 0.45))

            advice = list(pacing_res["actionable_advice"])
            if not policy_res["is_safe"]:
                advice.insert(0, f"CẢNH BÁO TỪ NGỮ: Kịch bản chứa {policy_res['total_violations']} từ nhạy cảm có thể bị bóp reach.")

            res = VideoInspectResponse(
                composite_viral_score=composite_score,
                pacing=pacing_res,
                policy=policy_res,
                actionable_advice=advice,
            )

            await self.repo.save_record(
                user_id=user_id,
                inspect_type="video",
                score=composite_score,
                details=res.model_dump(),
                summary=f"Thẩm định video: Điểm tổng hợp {composite_score}/100",
            )
            return res

        finally:
            if local_video.exists() and "vid_" in local_video.name:
                try:
                    local_video.unlink()
                except Exception:
                    pass
