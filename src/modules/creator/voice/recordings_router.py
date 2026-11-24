from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.shared.voice.schemas import VoiceSynthesizeFromProfileRequest
from src.modules.shared.voice.audio_generation_repository import AudioGenerationMongoRepository
from src.modules.creator.voice.voice_queue_manager import VoiceGenerationQueueManager

recordings_router = APIRouter(tags=["Creator - Audio Recordings"])


@recordings_router.post(
    "/synthesize/async",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Tạo giọng nói bất đồng bộ (Đẩy vào hàng đợi xử lý ngầm và thông báo socket)",
)
async def synthesize_async_endpoint(
    payload: VoiceSynthesizeFromProfileRequest,
    voice_name: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    repo = AudioGenerationMongoRepository()
    queue_mgr = VoiceGenerationQueueManager.get_instance()

    # 1. Tạo bản ghi ban đầu ở trạng thái PENDING gắn với user_id
    gen_doc = await repo.create_generation({
        "user_id": current_user["id"],
        "voice_profile_id": payload.profile_id_or_path,
        "voice_name": voice_name or "Giọng Đọc AI",
        "input_text": payload.text,
        "speed": payload.speed,
        "num_step": payload.num_step,
        "status": "PENDING",
    })

    # 2. Đưa vào hàng đợi xử lý ngầm
    queue_res = await queue_mgr.enqueue_synthesize_task(
        generation_id=gen_doc["id"],
        user_id=current_user["id"],
        payload_data={
            "profile_id_or_path": payload.profile_id_or_path,
            "text": payload.text,
            "speed": payload.speed,
            "num_step": payload.num_step,
            "voice_name": voice_name or "Giọng Đọc AI",
        },
    )

    return {
        "success": True,
        "generation_id": gen_doc["id"],
        "status": "PENDING",
        "queue_position": queue_res["queue_position"],
        "message": "Đã tiếp nhận kịch bản vào hàng đợi xử lý ngầm! Hệ thống sẽ thông báo khi hoàn tất.",
    }


@recordings_router.get(
    "/recordings",
    summary="Danh sách các bản thu âm (Chỉ user sở hữu mới xem được, Admin xem tất cả)",
)
async def list_recordings_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    repo = AudioGenerationMongoRepository()
    is_admin = current_user.get("role") == "ADMIN"
    user_id = current_user["id"]
    skip = (page - 1) * page_size

    items = await repo.list_user_recordings(
        user_id=user_id,
        is_admin=is_admin,
        skip=skip,
        limit=page_size,
    )
    total = await repo.count_recordings(user_id=user_id, is_admin=is_admin)

    formatted_items = []
    for doc in items:
        created_val = doc.get("created_at")
        created_str = created_val.strftime("%d/%m/%Y %H:%M") if hasattr(created_val, "strftime") else str(created_val or "")

        cloud_audio = doc.get("cloudinary_audio") or {}
        formatted_items.append({
            "id": doc["id"],
            "input_text": doc.get("input_text", ""),
            "voice_name": doc.get("voice_name", "Giọng AI"),
            "voice_profile_id": doc.get("voice_profile_id"),
            "speed": doc.get("speed", 1.0),
            "status": doc.get("status", "PENDING"),
            "audio_url": cloud_audio.get("secure_url") or cloud_audio.get("mp3_stream_url"),
            "duration_seconds": cloud_audio.get("duration_seconds", 0.0),
            "process_time_seconds": doc.get("process_time_seconds"),
            "error_message": doc.get("error_message"),
            "created_at": created_str,
            "is_owner": (doc.get("user_id") == user_id) or is_admin,
        })

    return {
        "items": formatted_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@recordings_router.delete(
    "/recordings/{recording_id}",
    summary="Xóa bản thu âm (Chỉ chủ sở hữu hoặc Admin mới có quyền xóa)",
)
async def delete_recording_endpoint(
    recording_id: str,
    current_user: dict = Depends(get_current_user),
):
    repo = AudioGenerationMongoRepository()
    is_admin = current_user.get("role") == "ADMIN"
    user_id = current_user["id"]

    success = await repo.delete_recording(
        generation_id=recording_id,
        user_id=user_id,
        is_admin=is_admin,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy bản thu âm hoặc bạn không có quyền xóa",
        )

    return {"message": "Đã xóa bản thu âm thành công", "id": recording_id}

