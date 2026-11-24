






import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.automation.service import AutomationService
from src.modules.creator.automation.schemas import (
    AutomationCampaignCreateRequest,
    AutomationCampaignUpdateRequest,
    AutomationCampaignResponse,
    AutomationCampaignListResponse,
    AutomationLogListResponse,
    PostedVideoListResponse,
)

logger = logging.getLogger("automation_router")

automation_router = APIRouter(prefix="/automation", tags=["Creator Automation"])


def get_automation_service() -> AutomationService:
    return AutomationService()


@automation_router.get(
    "/campaigns",
    response_model=AutomationCampaignListResponse,
    summary="Lấy danh sách các chiến dịch Automation của user",
)
async def get_campaigns_endpoint(
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    campaigns = await service.get_user_campaigns(current_user["id"])
    return {"total": len(campaigns), "campaigns": campaigns}


@automation_router.post(
    "/campaigns",
    response_model=AutomationCampaignResponse,
    summary="Tạo mới chiến dịch Automation tự động cào và đăng Facebook",
)
async def create_campaign_endpoint(
    payload: AutomationCampaignCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    return await service.create_campaign(current_user["id"], payload)


@automation_router.get(
    "/campaigns/{campaign_id}",
    response_model=AutomationCampaignResponse,
    summary="Lấy chi tiết một chiến dịch Automation",
)
async def get_campaign_detail_endpoint(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    campaign = await service.get_campaign(campaign_id, current_user["id"])
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chiến dịch hoặc bạn không có quyền truy cập.",
        )
    return campaign


@automation_router.put(
    "/campaigns/{campaign_id}",
    response_model=AutomationCampaignResponse,
    summary="Cập nhật cấu hình chiến dịch Automation",
)
async def update_campaign_endpoint(
    campaign_id: str,
    payload: AutomationCampaignUpdateRequest,
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    updated = await service.update_campaign(campaign_id, current_user["id"], payload)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chiến dịch để cập nhật.",
        )
    return updated


@automation_router.delete(
    "/campaigns/{campaign_id}",
    summary="Xóa chiến dịch Automation",
)
async def delete_campaign_endpoint(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    deleted = await service.delete_campaign(campaign_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chiến dịch để xóa.",
        )
    return {"success": True, "message": "Xóa chiến dịch thành công."}


@automation_router.patch(
    "/campaigns/{campaign_id}/toggle",
    response_model=AutomationCampaignResponse,
    summary="Bật / Tắt trạng thái kích hoạt chiến dịch",
)
async def toggle_campaign_endpoint(
    campaign_id: str,
    is_active: bool = Query(..., description="True để bật, False để tạm dừng"),
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    updated = await service.toggle_active(campaign_id, current_user["id"], is_active)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy chiến dịch.",
        )
    return updated


@automation_router.post(
    "/campaigns/{campaign_id}/run-now",
    summary="Kích hoạt chạy thử ngay 1 chu kỳ cào và đăng video",
)
async def run_campaign_now_endpoint(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    try:
        res = await service.run_campaign_now(campaign_id, current_user["id"])
        return res
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi thực thi chiến dịch: {str(exc)}",
        )


@automation_router.post(
    "/campaigns/{campaign_id}/clear-error",
    summary="Xóa cảnh báo lỗi của chiến dịch",
)
async def clear_campaign_error_endpoint(
    campaign_id: str,
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    await service.clear_campaign_error(campaign_id, current_user["id"])
    return {"success": True, "message": "Đã xóa cảnh báo lỗi."}


@automation_router.get(
    "/logs",
    response_model=AutomationLogListResponse,
    summary="Lấy lịch sử cào và tự động đăng video",
)
async def get_logs_endpoint(
    campaign_id: Optional[str] = Query(None, description="Lọc theo ID chiến dịch cụ thể"),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    logs = await service.get_logs(current_user["id"], campaign_id=campaign_id, limit=limit)
    return {"total": len(logs), "logs": logs}


@automation_router.get(
    "/posted-videos",
    response_model=PostedVideoListResponse,
    summary="Lấy danh sách các video đã lưu trong Database để chống trùng lặp",
)
async def get_posted_videos_endpoint(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    service: AutomationService = Depends(get_automation_service),
):
    videos = await service.get_posted_videos(current_user["id"], limit=limit)
    return {"total": len(videos), "posted_videos": videos}

