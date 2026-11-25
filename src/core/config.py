import sys
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Video AI Automation Platform"
    ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "127.0.0.1"
    PORT: int = 8001
    
    # Engine Settings
    OMNIVOICE_MODEL_ID: str = "k2-fsa/OmniVoice"
    OMNIVOICE_DEVICE: str = "cuda:0"
    OMNIVOICE_DTYPE: str = "float16" # float16 hoặc float32
    OMNIVOICE_DEFAULT_STEPS: int = 16
    WHISPER_MODEL_SIZE: str = "base"
    JWT_SECRET: str = "video_ai_secure_jwt_secret_key_2026_super_safe"

    # Translation Engine Settings (In-Process Qwen2.5 & LLM APIs)
    TRANSLATION_ENGINE: str = "qwen" # "qwen" hoặc "gemini"
    QWEN_MODEL_ID: str = "Qwen/Qwen2.5-0.5B-Instruct"
    QWEN_DEVICE: str = "cuda:0"
    QWEN_DTYPE: str = "float16" # float16 hoặc float32
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_ID: str = "gemini-2.5-flash"
    
    # Audio Settings
    AUDIO_SAMPLE_RATE: int = 24000
    MAX_AUDIO_SAMPLE_DURATION_SEC: float = 12.0

    # Database Settings (MongoDB)
    DATABASE_URL: str = "mongodb://localhost:27017/video_ai?authSource=admin"
    MONGO_DB_NAME: str = "video_ai"

    # Cloudinary Settings
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    CLOUDINARY_URL: str = ""

    # Douyin Crawler Settings (Tùy chọn)
    DOUYIN_COOKIE: str = ""
    DOUYIN_TIMEOUT_SEC: float = 35.0
    PLAYWRIGHT_HEADLESS: bool = True

    # Facebook Reels Publisher Settings
    FB_APP_ID: str = "1815527473001673"
    FB_APP_SECRET: str = ""
    FB_USER_ACCESS_TOKEN: str = ""
    FB_PAGE_ID: str = ""
    FB_PAGE_NAME: str = ""
    FB_PAGE_ACCESS_TOKEN: str = ""

    # YouTube Shorts Publisher Settings
    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_REDIRECT_URI: str = "http://localhost:8001/api/v1/creator/youtube/callback"
    FRONTEND_URL: str = "https://nguyen-video.vercel.app"

    # TikTok Publisher Settings
    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    TIKTOK_REDIRECT_URI: str = "https://giant-drudge-pastime.ngrok-free.dev/api/v1/creator/tiktok/callback"
    TIKTOK_AUTH_BASE_URL: str = "https://www.tiktok.com/v2/auth/authorize/"
    TIKTOK_API_BASE_URL: str = "https://open.tiktokapis.com/v2"
    
    # Internal Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    SRC_DIR: Path = Path(__file__).resolve().parent.parent
    CORE_DIR: Path = Path(__file__).resolve().parent
    ENGINES_DIR: Path = CORE_DIR / "engines"
    
    # Storage Paths
    STORAGE_DIR: Path = BASE_DIR / "storage"
    VOICE_PROFILES_DIR: Path = STORAGE_DIR / "voice_profiles"
    VOICE_SAMPLES_DIR: Path = STORAGE_DIR / "voice_samples"
    AUDIO_OUTPUT_DIR: Path = STORAGE_DIR / "audio_output"
    DUBBING_OUTPUT_DIR: Path = STORAGE_DIR / "dubbing_output"
    BGM_STORAGE_DIR: Path = STORAGE_DIR / "bgm"
    TEMP_DIR: Path = STORAGE_DIR / "temp"
    HF_CACHE_DIR: Path = STORAGE_DIR / "hf_cache"

    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3002",
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://103.20.102.228",
        "http://103.20.102.228:8001",
        "https://desktop-barley-pushup.ngrok-free.dev",
        "https://giant-drudge-pastime.ngrok-free.dev",
        "https://nguyen-video.vercel.app",
    ]

    model_config = SettingsConfigDict(
        env_file=(
            Path(__file__).resolve().parent.parent.parent / ".env",
            "be/.env",
            ".env",
        ),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()

# Cấu hình chuyển toàn bộ Cache và Temp sang ổ D (Hoàn toàn không chiếm dụng ổ C)
import os
import tempfile

temp_storage_dir = settings.STORAGE_DIR / "temp"
temp_storage_dir.mkdir(parents=True, exist_ok=True)

# Chuyển hướng thư mục temp của Python và Windows sang ổ D
tempfile.tempdir = str(temp_storage_dir)
os.environ["TMPDIR"] = str(temp_storage_dir)
os.environ["TEMP"] = str(temp_storage_dir)
os.environ["TMP"] = str(temp_storage_dir)

# Chuyển cache của Hugging Face và PyTorch sang ổ D
os.environ["HF_HOME"] = str(settings.STORAGE_DIR / "hf_cache")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TORCH_HOME"] = str(settings.STORAGE_DIR / "torch_cache")
os.environ["MODELSCOPE_CACHE"] = str(settings.STORAGE_DIR / "modelscope_cache")

# Tự động nạp src/core/engines vào sys.path để import trực tiếp omnivoice
if settings.ENGINES_DIR.exists() and str(settings.ENGINES_DIR) not in sys.path:
    sys.path.insert(0, str(settings.ENGINES_DIR))

# Đảm bảo các thư mục lưu trữ tồn tại
settings.VOICE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
settings.VOICE_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
settings.AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.DUBBING_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.BGM_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
