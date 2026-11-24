import os
import json
import uuid
import asyncio
import logging
from typing import List, Dict, Any, Optional
from src.core.config import settings
from src.core.engines.video.storyboard_generator import StoryboardScriptGenerator, STYLE_PRESETS
from src.core.engines.video.storyboard_renderer import StoryboardRenderer
from src.modules.creator.storyboard.schemas import (
    ScriptGenerateRequest,
    ScriptGenerateResponse,
    SceneItem,
    RenderStoryboardRequest,
    RenderStoryboardResponse,
    VoiceOptionItem,
)

logger = logging.getLogger("storyboard_service")

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_BE_ROOT = os.path.abspath(os.path.join(_CURRENT_DIR, "..", "..", "..", ".."))
STORYBOARD_STORAGE = os.path.join(_BE_ROOT, "storage", "temp", "storyboards")
_FALLBACK_STORYBOARD_STORAGE = os.path.join(
    _CURRENT_DIR, "..", "..", "..", "storage", "temp", "storyboards"
)

class StoryboardService:
    @classmethod
    def get_job_images_dir(cls, job_id: str) -> str:
        """Lấy thư mục ảnh của job, hỗ trợ cả đường dẫn chuẩn và fallback."""
        for base in [STORYBOARD_STORAGE, _FALLBACK_STORYBOARD_STORAGE]:
            p = os.path.join(base, job_id, "images")
            if os.path.exists(p):
                return p
        p1 = os.path.join(STORYBOARD_STORAGE, job_id, "images")
        os.makedirs(p1, exist_ok=True)
        return p1

    @classmethod
    async def generate_script(cls, payload: ScriptGenerateRequest) -> ScriptGenerateResponse:
        gemini_key = getattr(payload, "gemini_api_key", None)
        if not gemini_key:
            try:
                from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository
                keys = await asyncio.wait_for(GeminiKeysMongoRepository().get_active_keys(), timeout=3.5)
                if keys:
                    gemini_key = keys[0].get("key")
            except Exception:
                pass

        if not gemini_key:
            from src.core.config import settings
            gemini_key = getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY")

        art_style = payload.art_style or "stickman"
        genre = payload.genre or "knowledge_sharing"

        raw_scenes = await StoryboardScriptGenerator.generate_script(
            topic=payload.topic,
            art_style=art_style,
            genre=genre,
            scene_count=payload.scene_count,
            gemini_api_key=gemini_key,
            style=payload.style,
        )

        art_info = StoryboardScriptGenerator.get_art_style(art_style)
        genre_info = StoryboardScriptGenerator.get_genre(genre)
        scene_items = [
            SceneItem(
                scene_idx=s.get("scene_idx", idx + 1),
                narration=s.get("narration", ""),
                prompt_en=s.get("prompt_en", ""),
                estimated_duration=s.get("estimated_duration", 2.8),
            )
            for idx, s in enumerate(raw_scenes)
        ]

        return ScriptGenerateResponse(
            success=True,
            topic=payload.topic,
            art_style=art_style,
            art_style_name=art_info["name"],
            genre=genre,
            genre_name=genre_info["name"],
            style=art_style,
            style_name=f"{art_info['name']} • {genre_info['name']}",
            scenes=scene_items,
        )

    @classmethod
    async def save_uploaded_image(
        cls,
        job_id: str,
        scene_idx: int,
        file_bytes: bytes,
        filename: str,
        auto_clean: bool = False,
    ) -> Dict[str, Any]:
        job_dir = cls.get_job_images_dir(job_id)
        os.makedirs(job_dir, exist_ok=True)

        ext = os.path.splitext(filename)[1].lower() or ".jpg"
        detected = False
        if auto_clean:
            try:
                from src.core.engines.image.watermark_remover import WatermarkRemover
                file_bytes, detected = WatermarkRemover.clean_image_bytes(file_bytes, ext=ext)
            except Exception as e:
                logger.warning("Loi khi tu dong xoa watermark: %s", str(e))

        save_name = f"scene_{scene_idx}{ext}"
        save_path = os.path.join(job_dir, save_name)

        with open(save_path, "wb") as f:
            f.write(file_bytes)

        ts = int(uuid.uuid4().hex[:6], 16)
        url = f"/api/v1/creator/storyboard/media/{job_id}/images/{save_name}?v={ts}"
        return {"url": url, "path": save_path, "cleaned": detected}

    @classmethod
    async def clean_scene_watermark(
        cls,
        job_id: str,
        scene_idx: int,
        watermark_type: str = "gemini",
        custom_box: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        from src.core.engines.image.watermark_remover import WatermarkRemover

        job_dir = cls.get_job_images_dir(job_id)
        if not os.path.exists(job_dir):
            raise FileNotFoundError(f"Không tìm thấy thư mục ảnh của phiên {job_id}")

        target_file = None
        for fn in os.listdir(job_dir):
            if fn.startswith(f"scene_{scene_idx}."):
                target_file = os.path.join(job_dir, fn)
                break

        if not target_file or not os.path.exists(target_file):
            raise FileNotFoundError(f"Chưa có ảnh tải lên cho Cảnh #{scene_idx}")

        with open(target_file, "rb") as f:
            raw_bytes = f.read()

        ext = os.path.splitext(target_file)[1].lower() or ".jpg"
        clean_bytes, detected = WatermarkRemover.clean_image_bytes(
            file_bytes=raw_bytes,
            watermark_type=watermark_type,
            custom_box=custom_box,
            ext=ext,
        )

        with open(target_file, "wb") as f:
            f.write(clean_bytes)

        ts = int(uuid.uuid4().hex[:6], 16)
        base_name = os.path.basename(target_file)
        url = f"/api/v1/creator/storyboard/media/{job_id}/images/{base_name}?v={ts}"
        return {
            "scene_idx": scene_idx,
            "url": url,
            "path": target_file,
            "detected": detected,
        }

    @classmethod
    async def batch_clean_scenes(
        cls, job_id: str, scene_indices: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        job_dir = cls.get_job_images_dir(job_id)
        if not os.path.exists(job_dir):
            return {"cleaned_count": 0, "scenes": []}

        indices = scene_indices or sorted(list({
            int(fn.split("_")[1].split(".")[0])
            for fn in os.listdir(job_dir)
            if fn.startswith("scene_") and fn.split("_")[1].split(".")[0].isdigit()
        }))

        cleaned_scenes = []
        for idx in indices:
            try:
                res = await cls.clean_scene_watermark(job_id=job_id, scene_idx=idx)
                cleaned_scenes.append(res)
            except Exception as e:
                logger.warning("Loi khi clean scene %s: %s", idx, str(e))

        return {"cleaned_count": len(cleaned_scenes), "scenes": cleaned_scenes}

    @classmethod
    async def render_video(cls, payload: RenderStoryboardRequest) -> RenderStoryboardResponse:
        job_id = payload.job_id or uuid.uuid4().hex[:12]
        output_dir = os.path.join(STORYBOARD_STORAGE, job_id, "render")
        os.makedirs(output_dir, exist_ok=True)

        scenes_data = []
        for s in payload.scenes:
            img_path = s.image_path
            if not img_path and s.image_url and "/media/" in s.image_url:
                clean_url = s.image_url.split("?")[0]
                parts = clean_url.split("/media/")[1].split("/")
                # Thu o STORAGE chinh
                p1 = os.path.join(STORYBOARD_STORAGE, *parts)
                if os.path.exists(p1):
                    img_path = p1
                else:
                    img_path = os.path.join(_FALLBACK_STORYBOARD_STORAGE, *parts)

            scenes_data.append({
                "scene_idx": s.scene_idx,
                "narration": s.narration,
                "image_path": img_path,
            })

        render_res = await StoryboardRenderer.render_storyboard(
            scenes=scenes_data,
            voice_name=payload.voice_name,
            output_dir=output_dir,
        )

        final_url = f"/api/v1/creator/storyboard/media/{job_id}/render/final_storyboard.mp4"
        final_video_path = render_res.get("final_video_path")

        return RenderStoryboardResponse(
            success=True,
            job_id=job_id,
            video_url=final_url,
            video_path=final_video_path,
            duration=render_res["total_duration"],
            scenes_count=render_res["scenes_rendered"],
            message=f"Đã render thành công video ({render_res['total_duration']}s) từ {render_res['scenes_rendered']} phân cảnh!",
        )

    @classmethod
    async def get_available_voices(cls) -> List[VoiceOptionItem]:
        """Tổng hợp danh sách giọng đọc mặc định và các model giọng đã training."""
        voices = [
            VoiceOptionItem(id="vi-VN-NamMinhNeural", name="Nam Minh (Giọng Nam Truyền Cảm - Edge TTS)", gender="MALE", type="preset"),
            VoiceOptionItem(id="vi-VN-HoaiMyNeural", name="Hoài My (Giọng Nữ Nhẹ Nhàng - Edge TTS)", gender="FEMALE", type="preset"),
        ]
        seen = {"vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"}

        # 1. Quét kho lưu trữ file local (VOICE_PROFILES_DIR - tức thì 0ms)
        pdir = settings.VOICE_PROFILES_DIR
        if pdir.exists():
            for jf in pdir.glob("*.json"):
                try:
                    d = json.loads(jf.read_text(encoding="utf-8"))
                    pid = d.get("profile_id", jf.stem)
                    if pid and pid not in seen:
                        seen.add(pid)
                        voices.append(VoiceOptionItem(id=pid, name=d.get("profile_name", f"Model {pid[:8]}"), gender=d.get("gender", "NEUTRAL"), type="trained", is_finetuned=True))
                except Exception:
                    pass
            for pf in pdir.glob("*.pt"):
                if pf.stem not in seen:
                    seen.add(pf.stem)
                    voices.append(VoiceOptionItem(id=pf.stem, name=f"Model Trained ({pf.stem[:8]})", gender="NEUTRAL", type="trained", is_finetuned=True))

        return voices

