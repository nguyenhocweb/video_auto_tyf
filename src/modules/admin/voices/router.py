from fastapi import APIRouter, Depends, HTTPException, status
from src.modules.shared.auth.dependencies import require_admin
from src.modules.shared.voice.repository_mongo import VoiceMongoRepository
from src.core.config import settings

admin_voices_router = APIRouter(prefix="/voices", tags=["Admin - Voice Models Management"])


@admin_voices_router.get(
    "",
    summary="Xem toàn bộ các mô hình giọng nói trong hệ thống",
)
async def list_all_system_voices_endpoint(_: dict = Depends(require_admin)):
    repo = VoiceMongoRepository()
    profiles = await repo.list_voice_profiles(limit=200)

    clean_profiles = []
    for p in profiles:
        clean_profiles.append({
            "id": p["_id"],
            "profile_name": p["profile_name"],
            "gender": p.get("gender", "NEUTRAL"),
            "usage_count": p.get("usage_count", 0),
            "is_preset": p.get("is_preset", False),
            "quality_metrics": p.get("quality_metrics", {}),
            "created_at": str(p.get("created_at", "")),
            "cloudinary_url": p.get("cloudinary_embedding", {}).get("secure_url", ""),
        })

    return {"total": len(clean_profiles), "voices": clean_profiles}


@admin_voices_router.delete(
    "/{voice_id}",
    summary="Quản trị viên xóa mô hình giọng nói vi phạm",
)
async def delete_system_voice_endpoint(
    voice_id: str,
    _: dict = Depends(require_admin),
):
    repo = VoiceMongoRepository()
    doc = await repo.get_voice_profile_by_id(voice_id)

    # Xóa file local nếu có
    files = [
        settings.VOICE_PROFILES_DIR / f"{voice_id}.pt",
        settings.VOICE_PROFILES_DIR / f"{voice_id}.json",
    ]
    if doc:
        cloud_emb = doc.get("cloudinary_embedding", {})
        for text in [cloud_emb.get("public_id", ""), cloud_emb.get("secure_url", "")]:
            for part in text.split("/"):
                clean = part.replace("embedding_", "").replace("prompt_", "").replace(".pt", "")
                if len(clean) >= 12:
                    files.append(settings.VOICE_PROFILES_DIR / f"{clean}.pt")
                    files.append(settings.VOICE_PROFILES_DIR / f"{clean}.json")

    for f in set(files):
        if f.exists():
            f.unlink()

    deleted = await repo.delete_voice_profile(voice_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy mô hình giọng để xóa")

    return {"message": "Admin đã xóa thành công mô hình giọng nói", "voice_id": voice_id}

