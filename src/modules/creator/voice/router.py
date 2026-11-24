import io
import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from pydub import AudioSegment

from src.core.config import settings
from src.modules.shared.cloudinary.service import FastCloudinaryService
from src.modules.shared.voice.service import OmniVoiceService
from src.modules.shared.voice.repository_mongo import VoiceMongoRepository
from src.modules.shared.voice.schemas import (
    VoiceCloneRequest,
    VoiceDesignRequest,
    VoiceSynthesizeFromProfileRequest,
    AudioGenerationResponse,
)
from src.modules.creator.voice.profile_router import profile_router
from src.modules.creator.voice.training_router import training_router
from src.modules.creator.voice.recordings_router import recordings_router

router = APIRouter(prefix="/voice", tags=["Creator - Voice AI"])

def get_voice_service() -> OmniVoiceService:
    return OmniVoiceService()

@router.post(
    "/clone",
    response_model=AudioGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Zero-shot Voice Cloning (Nhái giọng từ mẫu 3-10s)"
)
async def clone_voice_endpoint(
    payload: VoiceCloneRequest,
    voice_service: OmniVoiceService = Depends(get_voice_service)
) -> AudioGenerationResponse:
    try:
        return await voice_service.clone_voice(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi thực hiện clone giọng nói: {str(exc)}"
        )

@router.post(
    "/design",
    response_model=AudioGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Voice Design (Tự tạo chất giọng mới bằng mô tả bằng chữ)"
)
async def design_voice_endpoint(
    payload: VoiceDesignRequest,
    voice_service: OmniVoiceService = Depends(get_voice_service)
) -> AudioGenerationResponse:
    try:
        return await voice_service.design_voice(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi thiết kế giọng nói: {str(exc)}"
        )

@router.post(
    "/synthesize",
    response_model=AudioGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Đọc kịch bản video bằng hồ sơ giọng đã lưu"
)
async def synthesize_endpoint(
    payload: VoiceSynthesizeFromProfileRequest,
    voice_service: OmniVoiceService = Depends(get_voice_service)
) -> AudioGenerationResponse:
    try:
        return await voice_service.synthesize_from_profile(payload)
    except FileNotFoundError as fnf:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(fnf)
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi tạo thuyết minh video: {str(exc)}"
        )

@router.post(
    "/upload-sample",
    status_code=status.HTTP_201_CREATED,
    summary="Tải lên và xử lý âm thanh mẫu trực tiếp lên Cloudinary (Zero-Disk)"
)
async def upload_sample_endpoint(file: UploadFile = File(...)):
    try:
        saved_filename = f"sample_{uuid.uuid4().hex[:8]}.wav"
        saved_path = settings.VOICE_SAMPLES_DIR / saved_filename

        content = await file.read()

        # 1. Làm sạch và chuẩn hóa audio trên RAM (mono, 24kHz, trim)
        raw_audio = AudioSegment.from_file(io.BytesIO(content))
        clean_audio = raw_audio.set_channels(1).set_frame_rate(settings.AUDIO_SAMPLE_RATE)

        max_duration_ms = int(settings.MAX_AUDIO_SAMPLE_DURATION_SEC * 1000)
        if len(clean_audio) > max_duration_ms:
            clean_audio = clean_audio[:max_duration_ms]

        audio_buffer = io.BytesIO()
        clean_audio.export(audio_buffer, format="wav")
        audio_bytes = audio_buffer.getvalue()

        # 2. Upload thẳng lên Cloudinary
        cloud_res = await FastCloudinaryService.upload_audio_bytes(
            audio_bytes=audio_bytes,
            filename=saved_filename,
            folder="video_ai/voice_samples",
        )
        cloudinary_url = cloud_res.get("secure_url") if cloud_res else None

        # 3. Lưu bản ghi vào MongoDB voice_samples
        file_hash = hashlib.sha256(audio_bytes).hexdigest()
        try:
            mongo_repo = VoiceMongoRepository()
            await mongo_repo.create_voice_sample({
                "original_filename": file.filename,
                "file_hash": file_hash,
                "duration_seconds": round(len(clean_audio) / 1000.0, 2),
                "sample_rate": settings.AUDIO_SAMPLE_RATE,
                "channels": 1,
                "format": "wav",
                "size_bytes": len(audio_bytes),
                "cloudinary": cloud_res or {},
            })
        except Exception as e:
            print(f"[upload_sample_endpoint] MongoDB save skipped: {e}")

        # 4. Ghi bản sao lưu trữ tại ổ D (không đụng ổ C) để AI trích xuất embedding
        saved_path.write_bytes(audio_bytes)

        return {
            "sample_path": str(saved_path),
            "sample_filename": saved_filename,
            "sample_url": cloudinary_url or f"/api/v1/creator/voice/sample/{saved_filename}",
            "cloudinary_url": cloudinary_url,
            "original_name": file.filename,
            "size_bytes": len(audio_bytes),
            "duration_seconds": round(len(clean_audio) / 1000.0, 2),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lưu và xử lý file audio mẫu: {str(exc)}"
        )

@router.get(
    "/audio/{filename}",
    summary="Phát và tải file audio đã sinh"
)
async def get_audio_endpoint(filename: str):
    file_path = settings.AUDIO_OUTPUT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file audio")
    return FileResponse(file_path, media_type="audio/wav", filename=filename)

@router.get(
    "/sample/{filename}",
    summary="Phát và tải file audio mẫu"
)
async def get_sample_endpoint(filename: str):
    file_path = settings.VOICE_SAMPLES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy file audio mẫu")
    return FileResponse(file_path, media_type="audio/wav", filename=filename)

# Gắn profile_router, training_router & recordings_router
router.include_router(profile_router)
router.include_router(training_router)
router.include_router(recordings_router)
