import io
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydub import AudioSegment

from src.core.config import settings
from src.modules.shared.cloudinary.service import FastCloudinaryService
from src.modules.shared.voice.repository_mongo import VoiceMongoRepository
from src.modules.shared.voice.training_prompts import get_training_prompts
from src.modules.creator.voice.long_audio_processor import process_and_train_long_audio
from src.modules.creator.voice.voice_training_worker import execute_booth_training
from src.modules.shared.voice.audio_quality_inspector import inspect_audio_quality
from src.modules.shared.auth.dependencies import get_current_user

training_router = APIRouter(prefix="/training", tags=["Creator - Voice Training"])


@training_router.get(
    "/prompts",
    summary="Lấy danh sách 30 câu đọc mẫu tiếng Việt chuẩn âm vị"
)
async def get_training_prompts_endpoint():
    return {"prompts": get_training_prompts()}


@training_router.post(
    "/job",
    summary="Khởi tạo phiên phòng thu huấn luyện giọng nói mới"
)
async def create_training_job_endpoint(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    voice_name = payload.get("voice_name", "").strip()
    if not voice_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tên giọng nói không được để trống",
        )

    mongo_repo = VoiceMongoRepository()
    job = await mongo_repo.create_training_job({
        "user_id": current_user["id"],
        "voice_name": voice_name,
        "gender": payload.get("gender", "NEUTRAL"),
        "target_epochs": 20,
    })
    return {"message": "Tạo phiên huấn luyện thành công", "job": job}


@training_router.get(
    "/job/{job_id}",
    summary="Chi tiết phiên huấn luyện và danh sách các câu đã thu"
)
async def get_training_job_endpoint(job_id: str):
    mongo_repo = VoiceMongoRepository()
    job = await mongo_repo.get_training_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phiên huấn luyện",
        )

    samples = await mongo_repo.get_training_samples_by_job(job_id)
    return {"job": job, "samples": samples}


@training_router.post(
    "/sample",
    summary="Tải lên từng câu ghi âm mẫu và lưu trực tiếp lên Cloudinary"
)
async def upload_training_sample_endpoint(
    job_id: str = Form(...),
    prompt_id: int = Form(...),
    prompt_text: str = Form(...),
    file: UploadFile = File(...),
):
    try:
        content = await file.read()
        raw_audio = AudioSegment.from_file(io.BytesIO(content))
        clean_audio = raw_audio.set_channels(1).set_frame_rate(settings.AUDIO_SAMPLE_RATE)

        out_buffer = io.BytesIO()
        clean_audio.export(out_buffer, format="wav")
        audio_bytes = out_buffer.getvalue()

        # Lưu bản sao tạm thời trên ổ D để AI huấn luyện trích xuất nhanh
        local_sample_file = settings.TEMP_DIR / f"train_{job_id}_{prompt_id}.wav"
        local_sample_file.write_bytes(audio_bytes)

        filename = f"sample_prompt_{prompt_id}.wav"
        cloud_res = await FastCloudinaryService.upload_audio_bytes(
            audio_bytes=audio_bytes,
            filename=filename,
            folder=f"video_ai/training_datasets/{job_id}",
        )

        duration = round(len(clean_audio) / 1000.0, 2)
        mongo_repo = VoiceMongoRepository()
        saved_doc = await mongo_repo.save_training_sample({
            "job_id": job_id,
            "prompt_id": prompt_id,
            "prompt_text": prompt_text,
            "duration_seconds": duration,
            "cloudinary_url": cloud_res.get("secure_url", "") if cloud_res else "",
            "public_id": cloud_res.get("public_id", "") if cloud_res else "",
            "file_size": len(audio_bytes),
        })

        return {
            "message": f"Đã lưu câu {prompt_id} thành công lên Cloudinary",
            "sample": saved_doc,
            "duration_seconds": duration,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi xử lý câu ghi âm: {str(exc)}",
        )


@training_router.post(
    "/start/{job_id}",
    summary="Bắt đầu chạy tiến trình Huấn luyện Mô hình Chuyên sâu (LoRA Engine)"
)
async def start_training_endpoint(job_id: str):
    mongo_repo = VoiceMongoRepository()
    job = await mongo_repo.get_training_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phiên huấn luyện",
        )

    samples = await mongo_repo.get_training_samples_by_job(job_id)
    if len(samples) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cần tối thiểu 5 câu thu âm để bắt đầu huấn luyện (Hiện có {len(samples)} câu)",
        )

    asyncio.create_task(
        execute_booth_training(
            job_id=job_id,
            voice_name=job.get("voice_name", "Giọng Độc Quyền"),
            gender=job.get("gender", "NEUTRAL"),
        )
    )

    return {
        "message": "Đã khởi chạy tiến trình huấn luyện chuyên sâu thành công!",
        "job_id": job_id,
        "status": "TRAINING",
    }


@training_router.post(
    "/upload-long-audio",
    summary="Tải lên file âm thanh dài (15-30 phút), tự động cắt lát thông minh và huấn luyện"
)
async def upload_long_audio_endpoint(
    voice_name: str = Form(...),
    gender: str = Form("NEUTRAL"),
    auto_start: bool = Form(True),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    allowed_exts = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".mp4", ".mov"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Định dạng file không được hỗ trợ ({suffix}). Vui lòng tải file audio (.mp3, .wav, .m4a, .aac, .flac)!",
        )

    mongo_repo = VoiceMongoRepository()
    job = await mongo_repo.create_training_job({
        "user_id": current_user["id"],
        "voice_name": voice_name,
        "gender": gender,
        "target_epochs": 20,
    })
    job_id = job["_id"]

    temp_path = settings.TEMP_DIR / f"long_{job_id}_{file.filename}"
    try:
        with open(temp_path, "wb") as out_f:
            while chunk := await file.read(1024 * 1024):
                out_f.write(chunk)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi tiếp nhận file audio: {str(exc)}",
        )

    asyncio.create_task(
        process_and_train_long_audio(
            job_id=job_id,
            voice_name=voice_name,
            gender=gender,
            auto_start=auto_start,
            temp_path=temp_path,
            original_filename=file.filename or "audio.mp3",
            user_id=current_user["id"],
        )
    )

    return {
        "message": "Đã tiếp nhận file âm thanh dài và đang tự động cắt lát thông minh để huấn luyện!",
        "job_id": job_id,
        "status": "PREPROCESSING",
    }


@training_router.post(
    "/inspect-audio",
    summary="Kiểm định chất lượng âm thanh, đo SNR và phát hiện tạp âm môi trường",
)
async def inspect_audio_endpoint(audio_file: UploadFile = File(...)):
    if not audio_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vui lòng đính kèm file âm thanh",
        )

    content = await audio_file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File âm thanh rỗng",
        )

    try:
        report = inspect_audio_quality(content)
        return {"success": True, "report": report}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể phân tích âm thanh: {str(exc)}",
        )
