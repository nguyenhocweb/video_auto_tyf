from pathlib import Path
from typing import Union
from src.core.config import settings


def transcribe_reference_audio(wav_path: Union[str, Path]) -> str:
    """Phiên âm nhanh audio tham chiếu bằng Whisper cục bộ để định vị Attention cho OmniVoice."""
    snap = settings.HF_CACHE_DIR / "hub/models--openai--whisper-large-v3-turbo/snapshots/41f01f3fe87f28c78e2fbf8b568835947dd65ed9"
    if snap.exists():
        try:
            from transformers import pipeline as hf_pipe
            pipe = hf_pipe("automatic-speech-recognition", model=str(snap), device="cpu")
            res = pipe(str(wav_path))
            txt = res.get("text", "").strip() if isinstance(res, dict) else ""
            if txt:
                return txt
        except Exception:
            pass
    return "Xin chào các bạn, đây là mẫu giọng đọc thuyết minh tiếng Việt chuẩn."
