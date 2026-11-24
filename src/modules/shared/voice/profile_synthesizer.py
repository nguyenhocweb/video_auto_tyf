import time
import uuid
import asyncio
from pathlib import Path
from typing import Any
import soundfile as sf  # type: ignore

from src.core.config import settings
from src.modules.shared.cloudinary.service import FastCloudinaryService
from src.modules.shared.voice.repository_mongo import VoiceMongoRepository
from src.modules.shared.voice.schemas import (
    VoiceSynthesizeFromProfileRequest,
    AudioGenerationResponse,
)

# Import OmniVoice config & prompt
try:
    from omnivoice import OmniVoiceGenerationConfig, VoiceClonePrompt  # type: ignore
except ImportError:
    from src.core.engines.omnivoice import OmniVoiceGenerationConfig, VoiceClonePrompt  # type: ignore

__all__ = [
    "resolve_voice_prompt",
    "synthesize_segment_local",
    "synthesize_script_from_profile",
    "calculate_vietnamese_speech_duration",
]



async def _resolve_voice_prompt(
    model: Any, profile_id_or_path: str
) -> Any:
    """Tìm nạp VoiceClonePrompt từ local cache hoặc tải fallback từ Cloudinary/MongoDB."""
    profile_path = Path(profile_id_or_path)
    if not profile_path.exists():
        profile_path = settings.VOICE_PROFILES_DIR / f"{profile_id_or_path}.pt"

    if profile_path.exists():
        try:
            return VoiceClonePrompt.load(str(profile_path))
        except Exception as e:
            print(f"[profile_synthesizer] Local prompt load error: {e}")

    # Fallback: Tải từ MongoDB & Cloudinary
    try:
        import httpx

        mongo_repo = VoiceMongoRepository()
        doc = await mongo_repo.get_voice_profile_by_id(profile_id_or_path)
        if not doc:
            return None


        cloud_emb = doc.get("cloudinary_embedding", {})
        secure_url = cloud_emb.get("secure_url", "")
        if secure_url and secure_url.startswith("http") and (secure_url.endswith(".pt") or cloud_emb.get("format") == "pt"):
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(secure_url)
                if resp.status_code == 200:
                    profile_path.write_bytes(resp.content)
                    return VoiceClonePrompt.load(str(profile_path))

        # Nếu không có .pt, thử tạo từ source sample audio
        if doc.get("source_sample_id"):
            sample_doc = await mongo_repo.get_voice_sample(doc["source_sample_id"])
            if sample_doc and sample_doc.get("cloudinary", {}).get("secure_url"):
                sample_url = sample_doc["cloudinary"]["secure_url"]
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(sample_url)
                    if resp.status_code == 200:
                        temp_file = settings.TEMP_DIR / f"temp_{doc['_id']}.wav"
                        temp_file.write_bytes(resp.content)
                        prompt = model.create_voice_clone_prompt(
                            ref_audio=str(temp_file),
                            ref_text="",
                        )
                        prompt.save(str(profile_path))
                        temp_file.unlink(missing_ok=True)
                        return prompt
    except Exception as exc:
        print(f"[profile_synthesizer] Fallback retrieval error: {exc}")

    return None


async def resolve_voice_prompt(model: Any, profile_id_or_path: str) -> Any:
    """Pre-resolve VoiceClonePrompt vào RAM cache để dùng lặp lại cho các câu phụ đề."""
    return await _resolve_voice_prompt(model, profile_id_or_path)


async def synthesize_segment_local(
    model: Any,
    prompt: Any,
    text: str,
    output_path: str,
    speed: float = 1.0,
    num_step: int = 16,
    gender: str = "MALE",
) -> bool:
    """
    Sinh âm thanh cục bộ tuần tự (Sequential) cho từng câu phụ đề:
    - Chạy đơn luồng trên CPU/GPU để kiểm soát tuyệt đối RAM/VRAM
    - KHÔNG upload Cloudinary, KHÔNG ghi Mongo lặp lại
    - Tối ưu bộ nhớ, ghi thẳng ra file WAV cục bộ
    """
    try:
        gen_config = OmniVoiceGenerationConfig(num_step=num_step)
        if prompt is not None:
            if not getattr(prompt, "ref_text", None):
                prompt.ref_text = "Xin chào các bạn, đây là mẫu giọng đọc thuyết minh tiếng Việt chuẩn."
            audio_outputs = await asyncio.to_thread(
                model.generate,
                text=text,
                voice_clone_prompt=prompt,
                language="vi",
                speed=speed or 1.0,
                duration=None,
                generation_config=gen_config,
            )
        else:
            is_male = str(gender).upper() != "FEMALE"
            instruct = "male, warm tone, vietnamese accent" if is_male else "female, young adult, warm tone"
            audio_outputs = await asyncio.to_thread(
                model.generate,
                text=text,
                instruct=instruct,
                language="vi",
                speed=speed or 1.0,
                duration=None,
                generation_config=gen_config,
            )
        raw_audio = audio_outputs[0]
        sample_rate = 24000
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), raw_audio, sample_rate)
        return Path(output_path).exists() and Path(output_path).stat().st_size > 400
    except Exception as exc:
        print(f"[profile_synthesizer] synthesize_segment_local error: {exc}")
        return False



def calculate_vietnamese_speech_duration(text: str, speed: float = 1.0) -> float:
    """
    Tính thời lượng phát âm tự nhiên chuẩn xác cho tiếng Việt:
    - Trung bình 0.35s - 0.38s cho mỗi từ đơn âm tiết.
    - 0.30s cho mỗi dấu ngắt nghỉ (. , ! ? ; : ...).
    - Thêm 0.8s đệm âm đuôi (anti-truncation) để AI không bao giờ bị nuốt chữ hay cắt cụt kịch bản.
    """
    clean_text = text.strip()
    words = clean_text.split()
    word_count = max(1, len(words))
    punct_count = sum(clean_text.count(p) for p in [".", ",", "!", "?", ";", ":", "...", "\n"])
    base_duration = (word_count * 0.36) + (punct_count * 0.35) + 0.8
    effective_speed = max(1.0, min(float(speed or 1.0), 2.0))
    return round(max(3.0, base_duration / effective_speed), 2)


async def synthesize_script_from_profile(
    model: Any, payload: VoiceSynthesizeFromProfileRequest
) -> AudioGenerationResponse:
    """Đọc kịch bản video bằng profile giọng đã lưu với tốc độ tối ưu."""
    t0 = time.time()
    prompt = await _resolve_voice_prompt(model, payload.profile_id_or_path)

    gen_config = OmniVoiceGenerationConfig(num_step=payload.num_step)
    calculated_duration = calculate_vietnamese_speech_duration(payload.text, payload.speed)

    if prompt is not None:
        # Đảm bảo prompt có ref_text để cơ chế Attention của mô hình OmniVoice không bị lệch âm
        if not getattr(prompt, "ref_text", None):
            prompt.ref_text = "Xin chào các bạn, đây là mẫu giọng đọc thuyết minh tiếng Việt chuẩn."
        audio_outputs = await asyncio.to_thread(
            model.generate,
            text=payload.text,
            voice_clone_prompt=prompt,
            language="vi",
            speed=payload.speed or 1.0,
            duration=None,
            generation_config=gen_config,
        )
    else:
        # Fallback instruct chuẩn theo đúng giới tính của payload/profile
        gender_str = getattr(payload, "gender", "MALE") or "MALE"
        is_male = str(gender_str).upper() != "FEMALE"
        instruct = "male, warm tone, vietnamese accent" if is_male else "female, young adult, warm tone"
        audio_outputs = await asyncio.to_thread(
            model.generate,
            text=payload.text,
            instruct=instruct,
            language="vi",
            speed=payload.speed or 1.0,
            duration=None,
            generation_config=gen_config,
        )

    output_filename = f"tts_{uuid.uuid4().hex[:8]}.wav"
    output_filepath = settings.AUDIO_OUTPUT_DIR / output_filename

    raw_audio = audio_outputs[0]
    sample_rate = 24000
    sf.write(str(output_filepath), raw_audio, sample_rate)

    duration = len(raw_audio) / sample_rate
    elapsed_time = round(time.time() - t0, 2)

    # Upload Cloudinary
    cloudinary_url = None
    mp3_stream_url = None
    try:
        audio_bytes = output_filepath.read_bytes()
        cloud_res = await FastCloudinaryService.upload_audio_bytes(
            audio_bytes=audio_bytes,
            filename=output_filename,
            folder="video_ai/audio_generations",
        )
        if cloud_res:
            cloudinary_url = cloud_res.get("secure_url")
            mp3_stream_url = cloud_res.get("mp3_stream_url")
    except Exception as exc:
        print(f"[profile_synthesizer] Cloudinary upload skipped: {exc}")

    # Cập nhật số lần sử dụng profile (việc lưu AudioGeneration do voice_queue_manager đảm nhiệm duy nhất)
    try:
        mongo_repo = VoiceMongoRepository()
        await asyncio.wait_for(mongo_repo.increment_profile_usage(payload.profile_id_or_path), timeout=1.0)
    except Exception as exc:
        print(f"[profile_synthesizer] Mongo usage count update skipped: {exc}")

    return AudioGenerationResponse(
        audio_path=str(output_filepath),
        audio_filename=output_filename,
        duration_seconds=round(duration, 2),
        sample_rate=sample_rate,
        message="Đọc thuyết minh video thành công",
        cloudinary_url=cloudinary_url,
        mp3_stream_url=mp3_stream_url,
        process_time_seconds=elapsed_time,
    )

