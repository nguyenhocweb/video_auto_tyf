from fastapi import APIRouter, Depends
from src.modules.shared.auth.dependencies import require_admin
from src.modules.shared.auth.repository import AuthMongoRepository
from src.modules.shared.voice.repository_mongo import VoiceMongoRepository

admin_dashboard_router = APIRouter(prefix="/dashboard", tags=["Admin - Dashboard"])


@admin_dashboard_router.get(
    "/stats",
    summary="Thống kê tổng quan toàn hệ thống cho Quản trị viên",
)
async def get_admin_stats_endpoint(_: dict = Depends(require_admin)):
    auth_repo = AuthMongoRepository()
    voice_repo = VoiceMongoRepository()

    total_users = await auth_repo.count_users()
    admin_users = len(await auth_repo.list_users(limit=100, role="ADMIN"))
    creator_users = len(await auth_repo.list_users(limit=100, role="CREATOR"))

    profiles = await voice_repo.list_voice_profiles(limit=500)
    total_profiles = len(profiles)

    # Đếm số training jobs
    total_jobs = await voice_repo.db["voice_training_jobs"].count_documents({})
    running_jobs = await voice_repo.db["voice_training_jobs"].count_documents({"status": "TRAINING"})
    completed_jobs = await voice_repo.db["voice_training_jobs"].count_documents({"status": "COMPLETED"})

    # Đếm số generations
    total_generations = await voice_repo.db["audio_generations"].count_documents({})

    return {
        "users": {
            "total": total_users,
            "admins": admin_users,
            "creators": creator_users,
        },
        "voices": {
            "total": total_profiles,
        },
        "training": {
            "total_jobs": total_jobs,
            "running": running_jobs,
            "completed": completed_jobs,
        },
        "generations": {
            "total": total_generations,
        },
        "system": {
            "status": "OPERATIONAL",
            "engine": "OmniVoice (600+ Langs)",
            "database": "MongoDB Cloud Connected",
            "cdn": "Cloudinary CDN Active",
        },
    }

