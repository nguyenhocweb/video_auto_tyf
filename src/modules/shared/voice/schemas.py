from pydantic import BaseModel, Field

class VoiceCloneRequest(BaseModel):
    text: str = Field(..., description="Văn bản cần chuyển đổi thành giọng nói")
    ref_audio_path: str = Field(..., description="Đường dẫn file audio giọng mẫu (3-10 giây)")
    ref_text: str | None = Field(default=None, description="Transcript chữ của file mẫu (nếu để trống, AI tự bóc băng bằng Whisper)")
    speed: float = Field(default=1.0, ge=1.0, le=2.0, description="Tốc độ nói (1.0x đến 2.0x, tối thiểu 1.0x bình thường)")
    num_step: int = Field(default=16, ge=8, le=64, description="Số bước diffusion (12-32 bước, khuyến nghị 16)")
    guidance_scale: float = Field(default=2.0, ge=1.0, le=5.0, description="Độ tuân thủ prompt")

class VoiceDesignRequest(BaseModel):
    text: str = Field(..., description="Văn bản cần đọc")
    instruct: str = Field(..., description="Mô tả phong cách giọng (vd: 'female, young adult, warm tone, vietnamese accent')")
    speed: float = Field(default=1.0, ge=1.0, le=2.0)
    num_step: int = Field(default=16, ge=8, le=64)
    guidance_scale: float = Field(default=2.0, ge=1.0, le=5.0)

class VoiceProfileCreateRequest(BaseModel):
    profile_name: str = Field(..., min_length=2, max_length=50, description="Tên hồ sơ giọng nói")
    ref_audio_path: str = Field(..., description="Đường dẫn file audio giọng mẫu để trích xuất embedding")
    ref_text: str | None = Field(default=None, description="Transcript chữ (tùy chọn)")
    description: str | None = Field(default=None, description="Mô tả phong cách giọng")
    gender: str = Field(default="NEUTRAL", description="Giới tính giọng: MALE | FEMALE | NEUTRAL")

class VoiceProfileResponse(BaseModel):
    profile_id: str
    profile_name: str
    prompt_file_path: str
    created_at: str
    cloudinary_url: str | None = None
    cloudinary_embedding_url: str | None = None
    gender: str | None = "NEUTRAL"
    usage_count: int | None = 0
    is_preset: bool = False

class VoiceSynthesizeFromProfileRequest(BaseModel):
    profile_id_or_path: str = Field(..., description="ID hồ sơ giọng hoặc đường dẫn file .pt")
    text: str = Field(..., description="Kịch bản video cần đọc")
    speed: float = Field(default=1.0, ge=1.0, le=2.0)
    num_step: int = Field(default=16, ge=8, le=64, description="Số bước diffusion (khuyến nghị 16)")

class AudioGenerationResponse(BaseModel):
    audio_path: str
    audio_filename: str
    duration_seconds: float
    sample_rate: int = 24000
    message: str = "Tạo giọng nói thành công"
    cloudinary_url: str | None = None
    mp3_stream_url: str | None = None
    process_time_seconds: float | None = None

