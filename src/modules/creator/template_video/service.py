"""Service xử lý nghiệp vụ cho tính năng Mẫu Video CapCut (Template Video).
Tích hợp tự động đẩy video lên Cloudinary, lưu trữ MongoDB và dọn sạch ổ cứng.
"""

import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import HTTPException, UploadFile, status

from src.core.engines.template_renderer.capcut_draft_project_builder import CapCutDraftProjectBuilder
from src.core.engines.template_renderer.engine import TemplateRenderEngine
from src.core.engines.template_renderer.spec_models import TemplateSpec
from src.core.engines.template_renderer.template_parser import CapCutTemplateParser
from src.modules.creator.template_video.repository import TemplateVideoRepository
from src.modules.creator.template_video.schemas import (
    CreateCapCutDesktopResponse,
    DeleteTemplateDbResponse,
    LaunchCapCutResponse,
    ParsedSlotResponse,
    ParsedTemplateResponse,
    SaveTemplateDbRequest,
    SavedTemplateDbItem,
    SavedTemplateDbListResponse,
    SlotItemResponse,
    TemplateItemResponse,
    TemplateListResponse,
    TemplateRenderResponse,
)
from src.modules.shared.cloudinary.service import FastCloudinaryService

logger = logging.getLogger("template_video_service")


class TemplateVideoService:
    """Service điều phối logic render và quản lý CSDL mẫu video CapCut."""

    def __init__(self):
        self.engine = TemplateRenderEngine()
        self.repo = TemplateVideoRepository()
        self.upload_temp_dir = Path("be/storage/temp/template_uploads")
        self.upload_temp_dir.mkdir(parents=True, exist_ok=True)

    def _convert_spec_to_response(self, spec: TemplateSpec) -> TemplateItemResponse:
        """Chuyển đổi Pydantic Spec nội bộ sang Schema response API."""
        return TemplateItemResponse(
            template_id=spec.template_id,
            name=spec.name,
            description=spec.description,
            category=spec.category,
            version=spec.version,
            total_duration=spec.total_duration,
            width=spec.resolution.width,
            height=spec.resolution.height,
            fps=spec.resolution.fps,
            slots=[
                SlotItemResponse(
                    slot_id=s.slot_id,
                    slot_type=s.slot_type,
                    title=s.title,
                    description=s.description,
                    start_time=s.start_time,
                    duration=s.duration,
                    required=s.required,
                )
                for s in spec.slots
            ],
            default_bgm=spec.default_bgm,
        )

    def list_templates(self) -> TemplateListResponse:
        """Lấy danh sách các mẫu video có sẵn từ engine."""
        specs = self.engine.list_available_templates()
        items = [self._convert_spec_to_response(s) for s in specs]
        return TemplateListResponse(total=len(items), items=items)

    def get_template(self, template_id: str) -> TemplateItemResponse:
        """Lấy chi tiết 1 mẫu video theo ID."""
        try:
            spec = self.engine.load_template_spec(template_id)
            return self._convert_spec_to_response(spec)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy mẫu: {template_id}")

    async def parse_template(
        self, url_or_id: Optional[str] = None, draft_file: Optional[UploadFile] = None
    ) -> ParsedTemplateResponse:
        """Tự động phân tích và bóc tách kịch bản mẫu CapCut từ URL/ID hoặc draft JSON."""
        try:
            if draft_file and draft_file.filename:
                content = await draft_file.read()
                data = json.loads(content.decode("utf-8"))
                parsed = CapCutTemplateParser.parse_from_draft_json(data, template_id="uploaded_draft")
            elif url_or_id:
                parsed = CapCutTemplateParser.parse_from_template_id_or_url(url_or_id)
            else:
                raise ValueError("Cần cung cấp Link/ID mẫu CapCut hoặc file draft_content.json!")

            is_saved = await self.repo.is_template_saved(parsed.template_id)

            return ParsedTemplateResponse(
                success=True,
                template_id=parsed.template_id,
                title=parsed.title,
                author_name=parsed.author_name,
                total_duration=parsed.total_duration,
                total_slots=parsed.total_slots,
                image_slots_count=parsed.image_slots_count,
                video_slots_count=parsed.video_slots_count,
                slots=[
                    ParsedSlotResponse(
                        slot_id=s.slot_id,
                        slot_type=s.slot_type,
                        start_time=s.start_time,
                        end_time=s.end_time,
                        duration=s.duration,
                        description=s.description,
                        is_replaceable=s.is_replaceable,
                        video_width=s.video_width,
                        video_height=s.video_height,
                    )
                    for s in parsed.slots
                ],
                has_audio=parsed.has_audio,
                music_title=parsed.music_title,
                cover_url=parsed.cover_url,
                video_url=parsed.video_url,
                template_url=parsed.template_url,
                source_url=parsed.source_url,
                is_saved_in_db=is_saved,
                message="Đã phân tích kịch bản mẫu CapCut thành công!",
            )
        except Exception as ex:
            logger.error(f"Lỗi phân tích mẫu CapCut: {ex}")
            raise HTTPException(status_code=400, detail=f"Không thể phân tích mẫu: {str(ex)}")

    async def save_template_to_db(self, user_id: str, payload: SaveTemplateDbRequest) -> SavedTemplateDbItem:
        """Lưu cấu trúc mẫu CapCut vào MongoDB."""
        try:
            data = payload.model_dump()
            saved = await self.repo.save_template(user_id=user_id, template_data=data)
            return SavedTemplateDbItem(**saved)
        except Exception as ex:
            logger.error(f"Lỗi lưu mẫu CapCut vào DB: {ex}")
            raise HTTPException(status_code=500, detail=f"Lỗi lưu mẫu vào CSDL: {str(ex)}")

    async def list_db_templates(self, user_id: Optional[str] = None) -> SavedTemplateDbListResponse:
        """Lấy danh sách các mẫu CapCut đã lưu trong MongoDB."""
        docs = await self.repo.list_templates(user_id=user_id)
        items = [SavedTemplateDbItem(**d) for d in docs]
        return SavedTemplateDbListResponse(total=len(items), items=items)

    async def get_db_template(self, template_id: str) -> SavedTemplateDbItem:
        """Lấy chi tiết 1 mẫu CapCut đã lưu trong MongoDB."""
        doc = await self.repo.get_template_by_id(template_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy mẫu {template_id} trong DB")
        return SavedTemplateDbItem(**doc)

    async def delete_db_template(self, template_id: str, user_id: Optional[str] = None) -> DeleteTemplateDbResponse:
        """Xóa mẫu CapCut khỏi MongoDB."""
        success = await self.repo.delete_template(template_id=template_id, user_id=user_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy mẫu {template_id} để xóa")
        return DeleteTemplateDbResponse(success=True, template_id=template_id, message="Đã xóa mẫu thành công!")

    async def _save_uploaded_slots(self, job_dir: Path, slots_files: Dict[int, UploadFile]) -> Dict[int, str]:
        """Lưu các file slot người dùng tải lên vào thư mục tác vụ tạm thời."""
        saved_map: Dict[int, str] = {}
        for slot_id, ufile in slots_files.items():
            if ufile and getattr(ufile, "filename", None):
                save_path = job_dir / f"slot_{slot_id}_{ufile.filename}"
                with open(save_path, "wb") as f:
                    f.write(await ufile.read())
                saved_map[slot_id] = str(save_path.resolve())
        return saved_map

    async def render_template(
        self,
        template_id: str,
        slots_files: Dict[int, UploadFile],
        audio_file: Optional[UploadFile] = None,
        user_id: str = "creator",
    ) -> TemplateRenderResponse:
        """Nhận file upload, render video mẫu và tự động đẩy lên Cloudinary."""
        job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        job_dir = self.upload_temp_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        resolved_audio_path: Optional[str] = None

        try:
            media_inputs = await self._save_uploaded_slots(job_dir, slots_files)

            if audio_file and audio_file.filename and 4 not in media_inputs:
                audio_path = job_dir / f"audio_{audio_file.filename}"
                with open(audio_path, "wb") as f:
                    f.write(await audio_file.read())
                resolved_audio_path = str(audio_path)

            render_res = self.engine.render(
                template_id=template_id,
                media_inputs=media_inputs,
                audio_path=resolved_audio_path,
            )

            filename = render_res["output_filename"]
            local_output = render_res["output_path"]
            stream_url = f"/api/v1/creator/templates/stream/{filename}"
            download_url = f"/api/v1/creator/templates/download/{filename}"
            cloud_msg = "Render hoàn tất!"

            try:
                cloud_res = await FastCloudinaryService.upload_large_file(
                    file_path=local_output,
                    filename=filename,
                    folder="video_ai/template_renders",
                    resource_type="video",
                )
                if cloud_res and cloud_res.get("secure_url"):
                    stream_url = cloud_res["secure_url"]
                    download_url = cloud_res["secure_url"]
                    cloud_msg = "Đã lưu lên Cloudinary CDN & giải phóng ổ cứng!"
                    if os.path.exists(local_output):
                        os.remove(local_output)
            except Exception as c_err:
                logger.warning(f"Lỗi Cloudinary: {c_err}")

            return TemplateRenderResponse(
                success=True,
                template_id=template_id,
                filename=filename,
                stream_url=stream_url,
                download_url=download_url,
                duration=render_res["duration"],
                file_size_mb=render_res["file_size_mb"],
                elapsed_seconds=render_res["elapsed_seconds"],
                fps_rendered=render_res["fps_rendered"],
                encoder_used=render_res["encoder_used"],
                beat_count=render_res["beat_count"],
                message=cloud_msg,
            )
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except Exception as ex:
            raise HTTPException(status_code=500, detail=f"Lỗi render video: {str(ex)}")
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    async def create_capcut_desktop_project(
        self,
        template_id: str,
        template_url: Optional[str] = None,
        project_title: Optional[str] = None,
        slots_files: Optional[Dict[int, UploadFile]] = None,
    ) -> CreateCapCutDesktopResponse:
        """Tạo dự án CapCut PC 100% nguyên bản và nạp media người dùng vào timeline."""
        job_id = f"job_pc_{int(time.time())}_{uuid.uuid4().hex[:4]}"
        job_dir = self.upload_temp_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            media_inputs = await self._save_uploaded_slots(job_dir, slots_files or {})
            res = CapCutDraftProjectBuilder.create_desktop_project(
                template_id=template_id,
                template_url=template_url,
                media_slots=media_inputs,
                project_title=project_title,
            )
            return CreateCapCutDesktopResponse(
                success=True,
                template_id=template_id,
                project_name=res["project_name"],
                project_path=res["project_path"],
                total_duration=res["total_duration"],
                slots_count=len(media_inputs),
                message=res["message"],
            )
        except Exception as ex:
            logger.error(f"Lỗi tạo dự án CapCut PC: {ex}")
            raise HTTPException(status_code=500, detail=f"Lỗi tạo dự án CapCut PC: {str(ex)}")

    async def launch_capcut(self, project_path: Optional[str] = None) -> LaunchCapCutResponse:
        """Mở ứng dụng CapCut PC hoặc mở thư mục dự án."""
        res = CapCutDraftProjectBuilder.launch_capcut(project_path=project_path)
        return LaunchCapCutResponse(success=res["success"], message=res["message"])

