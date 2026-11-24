import json
import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from src.core.config import settings
from src.modules.shared.voice.service import OmniVoiceService
from src.modules.shared.voice.schemas import (
    VoiceProfileCreateRequest,
    VoiceProfileResponse,
)
from src.modules.shared.voice.repository_mongo import VoiceMongoRepository
from src.modules.shared.auth.dependencies import get_current_user

profile_router = APIRouter(tags=["Creator - Voice Profiles"])


def get_voice_service() -> OmniVoiceService:
    return OmniVoiceService()


@profile_router.post(
    "/profile",
    response_model=VoiceProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo hồ sơ giọng nói cố định và gắn quyền sở hữu cho User",
)
async def create_profile_endpoint(
    payload: VoiceProfileCreateRequest,
    current_user: dict = Depends(get_current_user),
    voice_service: OmniVoiceService = Depends(get_voice_service),
) -> VoiceProfileResponse:
    try:
        return await voice_service.create_voice_profile(payload, user_id=current_user["id"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi tạo hồ sơ giọng: {str(exc)}",
        )


@profile_router.get(
    "/profiles",
    summary="Danh sách hồ sơ giọng (Phân quyền: User chỉ thấy giọng mình & Preset, Admin thấy toàn bộ)",
)
async def list_profiles_endpoint(
    current_user: dict = Depends(get_current_user),
):
    profiles = []
    seen_identifiers = set()
    is_admin = current_user.get("role") == "ADMIN"
    user_id = current_user["id"]

    # 1. Lấy danh sách từ MongoDB theo phân quyền
    try:
        mongo_repo = VoiceMongoRepository()
        mongo_profiles = await mongo_repo.list_voice_profiles(
            limit=100, user_id=user_id, is_admin=is_admin
        )
        for doc in mongo_profiles:
            created_at_val = doc.get("created_at")
            if isinstance(created_at_val, datetime.datetime):
                created_str = created_at_val.strftime("%d/%m/%Y %H:%M")
            else:
                created_str = str(created_at_val or "")

            doc_id = str(doc["_id"])
            cloud_emb = doc.get("cloudinary_embedding", {})
            pub_id = cloud_emb.get("public_id", "")
            sec_url = cloud_emb.get("secure_url", "")

            seen_identifiers.add(doc_id)
            for raw_val in [pub_id, sec_url]:
                for part in raw_val.split("/"):
                    clean_uuid = part.replace("embedding_", "").replace("prompt_", "").replace(".pt", "")
                    if len(clean_uuid) >= 12:
                        seen_identifiers.add(clean_uuid)

            is_preset = doc.get("is_preset", False)
            is_owner = (doc.get("user_id") == user_id) or is_admin

            profiles.append({
                "profile_id": doc_id,
                "profile_name": doc["profile_name"],
                "prompt_file_path": sec_url or pub_id or doc_id,
                "created_at": created_str,
                "gender": doc.get("gender", "NEUTRAL"),
                "usage_count": doc.get("usage_count", 0),
                "is_preset": is_preset,
                "is_owner": is_owner,
                "owner_user_id": doc.get("user_id"),
            })
    except Exception as exc:
        print(f"[list_profiles_endpoint] Mongo query skipped: {exc}")

    # 2. Preset mẫu mặc định dự phòng nếu chưa có giọng nào
    if len(profiles) == 0:
        profiles = [
            {
                "profile_id": "preset_news_vi",
                "profile_name": "Giọng Nam BTV Thời Sự (Hệ thống)",
                "created_at": "Hệ thống",
                "gender": "MALE",
                "usage_count": 12,
                "is_preset": True,
                "is_owner": False,
            },
            {
                "profile_id": "preset_story_vi",
                "profile_name": "Giọng Nữ Kể Chuyện Truyền Cảm (Hệ thống)",
                "created_at": "Hệ thống",
                "gender": "FEMALE",
                "usage_count": 8,
                "is_preset": True,
                "is_owner": False,
            },
        ]

    return {"profiles": profiles}


@profile_router.delete(
    "/profile/{profile_id}",
    summary="Xóa hồ sơ giọng nói (Chỉ chủ sở hữu hoặc Super Admin mới có quyền xóa)",
)
async def delete_profile_endpoint(
    profile_id: str,
    current_user: dict = Depends(get_current_user),
):
    mongo_repo = VoiceMongoRepository()
    is_admin = current_user.get("role") == "ADMIN"
    user_id = current_user["id"]

    # 1. Tìm thông tin trong MongoDB để kiểm tra quyền sở hữu
    doc = await mongo_repo.get_voice_profile_by_id(profile_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy hồ sơ giọng nói để xóa",
        )

    # 2. Kiểm tra phân quyền:
    # Nếu là giọng preset hệ thống: User không được xóa
    if doc.get("is_preset") and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không thể xóa giọng mẫu mặc định của hệ thống!",
        )

    # Nếu không phải Admin và không phải người tạo: Chặn 403 Forbidden!
    doc_owner_id = doc.get("user_id")
    if not is_admin and doc_owner_id and doc_owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Truy cập bị từ chối! Bạn chỉ có quyền xóa giọng do chính bạn tạo ra.",
        )

    # 3. Thu thập các file cần xóa trên ổ đĩa
    files_to_delete = [
        settings.VOICE_PROFILES_DIR / f"{profile_id}.pt",
        settings.VOICE_PROFILES_DIR / f"{profile_id}.json",
    ]

    cloud_emb = doc.get("cloudinary_embedding", {})
    for text in [cloud_emb.get("public_id", ""), cloud_emb.get("secure_url", "")]:
        for part in text.split("/"):
            clean = part.replace("embedding_", "").replace("prompt_", "").replace(".pt", "")
            if len(clean) >= 12:
                files_to_delete.append(settings.VOICE_PROFILES_DIR / f"{clean}.pt")
                files_to_delete.append(settings.VOICE_PROFILES_DIR / f"{clean}.json")

    deleted = False
    for f in set(files_to_delete):
        if f.exists():
            f.unlink()
            deleted = True

    try:
        mongo_deleted = await mongo_repo.delete_voice_profile(profile_id)
        if mongo_deleted:
            deleted = True
    except Exception as exc:
        print(f"[delete_profile_endpoint] Mongo delete error: {exc}")

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy hồ sơ giọng nói để xóa",
        )

    return {
        "message": "Đã xóa hồ sơ giọng nói thành công",
        "profile_id": profile_id,
        "deleted_by": current_user["email"],
    }
