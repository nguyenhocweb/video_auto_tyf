from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from src.modules.shared.auth.dependencies import require_admin
from src.modules.shared.settings.system_settings_repository import SystemSettingsMongoRepository
from src.modules.creator.voice.voice_queue_manager import VoiceGenerationQueueManager
from src.modules.creator.dubbing.dubbing_queue_manager import DubbingQueueManager

admin_settings_router = APIRouter(prefix="/settings", tags=["Admin - System Settings & Queue"])


class UpdateConcurrencyRequest(BaseModel):
    max_concurrency: int = Field(..., ge=1, le=64, description="Số luồng tạo giọng song song tối đa")
    server_ram_gb: Optional[int] = Field(None, ge=4, le=512, description="Dung lượng RAM máy chủ")


def compute_ram_simulation():
    """Bảng mô phỏng phân tích mức tiêu thụ RAM cho các cấu hình phần cứng."""
    presets = [
        {"ram_gb": 8, "optimal_concurrency": 2, "max_concurrency": 3, "status": "ENTRY", "desc": "Máy chủ cơ bản / PC cá nhân"},
        {"ram_gb": 16, "optimal_concurrency": 6, "max_concurrency": 8, "status": "RECOMMENDED", "desc": "Máy chủ Cloud tiêu chuẩn"},
        {"ram_gb": 32, "optimal_concurrency": 16, "max_concurrency": 20, "status": "HIGH_PERFORMANCE", "desc": "Workstation / Máy chủ AI chuyên dụng"},
        {"ram_gb": 64, "optimal_concurrency": 32, "max_concurrency": 40, "status": "ENTERPRISE", "desc": "Cụm Cloud phục vụ nhiều người dùng lớn"},
    ]
    return presets


@admin_settings_router.get(
    "/concurrency",
    summary="Lấy cấu hình hàng đợi song song và dữ liệu mô phỏng RAM máy chủ",
)
async def get_concurrency_settings_endpoint(_: dict = Depends(require_admin)):
    repo = SystemSettingsMongoRepository()
    queue_mgr = VoiceGenerationQueueManager.get_instance()
    dubbing_queue_mgr = DubbingQueueManager.get_instance()

    cfg = await repo.get_concurrency_settings()
    queue_status = queue_mgr.get_queue_status()
    dubbing_status = dubbing_queue_mgr.get_queue_status()
    sim_presets = compute_ram_simulation()

    curr_n = cfg.get("max_concurrency", 2)
    est_ram = round(2.0 + 3.0 + (curr_n * 1.4), 1)

    return {
        "max_concurrency": cfg.get("max_concurrency", 2),
        "server_ram_gb": cfg.get("server_ram_gb", 16),
        "active_jobs": queue_status.get("active_jobs", 0) + dubbing_status.get("active_jobs", 0),
        "queued_jobs": queue_status.get("queued_jobs", 0) + dubbing_status.get("queued_jobs", 0),
        "estimated_ram_usage_gb": est_ram,
        "ram_presets": sim_presets,
    }


@admin_settings_router.patch(
    "/concurrency",
    summary="Cập nhật giới hạn số luồng tạo giọng song song và cấu hình RAM",
)
async def update_concurrency_settings_endpoint(
    payload: UpdateConcurrencyRequest,
    _: dict = Depends(require_admin),
):
    repo = SystemSettingsMongoRepository()
    queue_mgr = VoiceGenerationQueueManager.get_instance()
    dubbing_queue_mgr = DubbingQueueManager.get_instance()

    updated = await repo.update_concurrency_settings(
        max_concurrency=payload.max_concurrency,
        server_ram_gb=payload.server_ram_gb,
    )
    # Cập nhật semaphore tức thì vào hàng đợi đang chạy
    queue_mgr.update_max_concurrency(payload.max_concurrency)
    dubbing_queue_mgr.update_max_concurrency(payload.max_concurrency)

    return {
        "message": f"Đã áp dụng cấu hình chạy song song: {payload.max_concurrency} luồng",
        "settings": {
            "max_concurrency": updated.get("max_concurrency"),
            "server_ram_gb": updated.get("server_ram_gb"),
        },
    }
