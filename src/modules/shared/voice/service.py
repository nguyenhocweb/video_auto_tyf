import sys
import json
import time
import uuid
import hashlib
import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List
import soundfile as sf  # type: ignore
import torch

from src.core.config import settings
from src.modules.shared.voice.schemas import (
    VoiceCloneRequest, VoiceDesignRequest, VoiceProfileCreateRequest,
    VoiceProfileResponse, VoiceSynthesizeFromProfileRequest, AudioGenerationResponse,
)
from src.modules.shared.voice.profile_synthesizer import synthesize_script_from_profile
from src.modules.shared.voice.reference_transcriber import transcribe_reference_audio

# Đảm bảo đường dẫn app/core/engines có trong sys.path khi chạy runtime
if settings.ENGINES_DIR.exists() and str(settings.ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(settings.ENGINES_DIR))

# Import OmniVoice engine từ app/core/engines/omnivoice
try:
    from omnivoice import OmniVoice, OmniVoiceGenerationConfig  # type: ignore
except ImportError:
    from src.core.engines.omnivoice import OmniVoice, OmniVoiceGenerationConfig  # type: ignore


class OmniVoiceService:
    """
    Service dùng chung (Shared Service) bọc mô hình OmniVoice (k2-fsa).
    Chịu trách nhiệm quản lý mô hình, trích xuất embedding, voice cloning và voice design.
    """

    _model: Any = None

    @classmethod
    def get_model(cls) -> Any:
        """Lazy load mô hình OmniVoice vào GPU/CPU khi có request đầu tiên."""
        if cls._model is None:
            try:
                device = settings.OMNIVOICE_DEVICE
                if "cuda" in device and not torch.cuda.is_available():
                    device = "cpu"

                dtype = (
                    torch.float16
                    if settings.OMNIVOICE_DTYPE == "float16" and "cuda" in device
                    else torch.float32
                )

                print(f"[OmniVoiceService] Loading model {settings.OMNIVOICE_MODEL_ID} on {device} ({dtype})...")
                cls._model = OmniVoice.from_pretrained(
                    settings.OMNIVOICE_MODEL_ID,
                    device_map=device,
                    dtype=dtype,
                    load_asr=False,
                )
                print("[OmniVoiceService] Model loaded successfully.")
            except Exception as exc:
                raise RuntimeError(
                    f"Không thể nạp mô hình OmniVoice. Vui lòng kiểm tra môi trường: {exc}"
                ) from exc
        return cls._model

    async def clone_voice(self, payload: VoiceCloneRequest) -> AudioGenerationResponse:
        """Nhái giọng nói tức thì từ audio mẫu 3 - 10 giây và upload thẳng lên Cloudinary."""
        from src.modules.shared.cloudinary.service import FastCloudinaryService
        from src.modules.shared.voice.repository_mongo import VoiceMongoRepository

        t0 = time.time()
        model = self.get_model()

        gen_config = OmniVoiceGenerationConfig(
            num_step=payload.num_step,
            guidance_scale=payload.guidance_scale,
        )

        audio_outputs = model.generate(
            text=payload.text,
            ref_audio=payload.ref_audio_path,
            ref_text=payload.ref_text,
            speed=payload.speed,
            generation_config=gen_config,
        )

        output_filename = f"clone_{uuid.uuid4().hex[:8]}.wav"
        output_filepath = settings.AUDIO_OUTPUT_DIR / output_filename

        raw_audio = audio_outputs[0]
        sample_rate = 24000
        sf.write(str(output_filepath), raw_audio, sample_rate)

        duration = len(raw_audio) / sample_rate
        elapsed_time = round(time.time() - t0, 2)

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

            mongo_repo = VoiceMongoRepository()
            await mongo_repo.create_audio_generation({
                "generation_type": "CLONE",
                "input_text": payload.text,
                "speed": payload.speed,
                "num_step": payload.num_step,
                "guidance_scale": payload.guidance_scale,
                "status": "COMPLETED",
                "cloudinary_audio": {
                    "secure_url": cloudinary_url or f"/api/v1/creator/voice/audio/{output_filename}",
                    "mp3_stream_url": mp3_stream_url,
                    "duration_seconds": round(duration, 2),
                    "format": "wav",
                },
                "process_time_seconds": elapsed_time,
            })
        except Exception as exc:
            print(f"[clone_voice] Cloudinary/Mongo save skipped: {exc}")

        return AudioGenerationResponse(
            audio_path=str(output_filepath),
            audio_filename=output_filename,
            duration_seconds=round(duration, 2),
            sample_rate=sample_rate,
            message="Clone giọng nói thành công",
            cloudinary_url=cloudinary_url,
            mp3_stream_url=mp3_stream_url,
            process_time_seconds=elapsed_time,
        )

    async def design_voice(self, payload: VoiceDesignRequest) -> AudioGenerationResponse:
        """Tự tạo chất giọng mới bằng mô tả bằng chữ (Voice Design)."""
        model = self.get_model()

        gen_config = OmniVoiceGenerationConfig(
            num_step=payload.num_step,
            guidance_scale=payload.guidance_scale,
        )

        audio_outputs = model.generate(
            text=payload.text,
            instruct=payload.instruct,
            speed=payload.speed,
            generation_config=gen_config,
        )

        output_filename = f"design_{uuid.uuid4().hex[:8]}.wav"
        output_filepath = settings.AUDIO_OUTPUT_DIR / output_filename

        raw_audio = audio_outputs[0]
        sample_rate = 24000
        sf.write(str(output_filepath), raw_audio, sample_rate)

        duration = len(raw_audio) / sample_rate

        return AudioGenerationResponse(
            audio_path=str(output_filepath),
            audio_filename=output_filename,
            duration_seconds=round(duration, 2),
            sample_rate=sample_rate,
            message="Thiết kế giọng nói thành công",
        )

    async def create_voice_profile(
        self, payload: VoiceProfileCreateRequest, user_id: Optional[str] = None
    ) -> VoiceProfileResponse:
        """
        Trích xuất embedding giọng từ mẫu và lưu lại thành file `.pt`.
        Lưu đồng bộ cả trên Cloudinary (CDN) và MongoDB (Database), đồng thời ghi cache local.
        """
        from src.modules.shared.cloudinary.service import FastCloudinaryService
        from src.modules.shared.voice.repository_mongo import VoiceMongoRepository

        model = self.get_model()
        ref_text = payload.ref_text
        if not ref_text:
            ref_text = transcribe_reference_audio(payload.ref_audio_path)

        prompt = model.create_voice_clone_prompt(
            ref_audio=payload.ref_audio_path,
            ref_text=ref_text,
        )

        profile_id = str(uuid.uuid4())
        prompt_path = settings.VOICE_PROFILES_DIR / f"{profile_id}.pt"
        prompt.save(str(prompt_path))

        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

        # 1. Upload audio mẫu lên Cloudinary & lưu MongoDB VoiceSample
        ref_path = Path(payload.ref_audio_path)
        sample_id = None
        cloud_sample = None
        if ref_path.exists():
            try:
                audio_bytes = ref_path.read_bytes()
                file_hash = hashlib.sha256(audio_bytes).hexdigest()
                cloud_sample = await FastCloudinaryService.upload_audio_bytes(
                    audio_bytes=audio_bytes,
                    filename=ref_path.name,
                    folder="video_ai/voice_samples",
                )
                mongo_repo = VoiceMongoRepository()
                sample_doc = await mongo_repo.create_voice_sample({
                    "original_filename": ref_path.name,
                    "file_hash": file_hash,
                    "duration_seconds": cloud_sample.get("duration_seconds", 0.0) if cloud_sample else 0.0,
                    "sample_rate": settings.AUDIO_SAMPLE_RATE,
                    "channels": 1,
                    "format": "wav",
                    "size_bytes": len(audio_bytes),
                    "cloudinary": cloud_sample or {},
                })
                sample_id = sample_doc.get("_id")
            except Exception as e:
                print(f"[create_voice_profile] Sample upload/mongo skipped: {e}")

        # 2. Upload vector embedding .pt lên Cloudinary & lưu MongoDB VoiceProfile
        cloud_embedding = None
        if prompt_path.exists():
            try:
                pt_bytes = prompt_path.read_bytes()
                cloud_embedding = await FastCloudinaryService.upload_raw_embedding(
                    embedding_bytes=pt_bytes,
                    profile_id=profile_id,
                    folder="video_ai/voice_profiles",
                )
                mongo_repo = VoiceMongoRepository()
                await mongo_repo.create_voice_profile({
                    "user_id": user_id,
                    "profile_name": payload.profile_name,
                    "description": payload.description or "",
                    "gender": payload.gender or "NEUTRAL",
                    "cloudinary_embedding": cloud_embedding or {
                        "secure_url": str(prompt_path),
                        "public_id": f"local_{profile_id}",
                        "format": "pt",
                        "bytes": len(pt_bytes),
                    },
                    "source_sample_id": sample_id,
                })
            except Exception as e:
                print(f"[create_voice_profile] Embedding upload/mongo skipped: {e}")

        # 3. Lưu JSON metadata local cache
        cloudinary_url = cloud_sample.get("secure_url") if cloud_sample else None
        cloudinary_embedding_url = cloud_embedding.get("secure_url") if cloud_embedding else None

        meta_path = settings.VOICE_PROFILES_DIR / f"{profile_id}.json"
        meta = {
            "profile_id": profile_id,
            "profile_name": payload.profile_name,
            "prompt_file_path": str(prompt_path),
            "created_at": now_str,
            "gender": payload.gender or "NEUTRAL",
            "cloudinary_url": cloudinary_url,
            "cloudinary_embedding_url": cloudinary_embedding_url,
        }
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return VoiceProfileResponse(
            profile_id=profile_id,
            profile_name=payload.profile_name,
            prompt_file_path=str(prompt_path),
            created_at=now_str,
            gender=payload.gender or "NEUTRAL",
            cloudinary_url=cloudinary_url,
            cloudinary_embedding_url=cloudinary_embedding_url,
        )

    async def synthesize_from_profile(
        self, payload: VoiceSynthesizeFromProfileRequest
    ) -> AudioGenerationResponse:
        """Đọc kịch bản video bằng profile giọng đã lưu (tốc độ siêu nhanh qua profile_synthesizer)."""
        return await synthesize_script_from_profile(self.get_model(), payload)
