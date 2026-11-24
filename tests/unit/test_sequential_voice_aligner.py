import pytest
import asyncio
from pathlib import Path
from src.core.utils.text_sanitizer import clean_text_for_tts, optimize_text_for_pace
from src.core.engines.dubbing.audio_aligner import DubbingAudioAligner


def test_clean_text_for_tts():
    # Test trailing punctuation stripping
    raw = "Khá lắm, con trạch tinh,"
    cleaned = clean_text_for_tts(raw)
    assert cleaned.endswith(".")
    assert not cleaned.endswith(",")

    # Test acronym translation
    raw_js = "Một con JS xuất hiện."
    cleaned_js = clean_text_for_tts(raw_js)
    assert "cương thi" in cleaned_js


def test_optimize_text_for_pace():
    text = "thực ra thì ở tại nơi này chúng ta hoàn toàn không có gì phải sợ hãi cả"
    optimized = optimize_text_for_pace(text, available_dur_sec=1.5)
    assert "ở tại nơi này" not in optimized
    assert "tại đây" in optimized or len(optimized.split()) < len(text.split())


@pytest.mark.asyncio
async def test_sequential_dubbing_track():
    test_segments = [
        {"id": 0, "start": 0.0, "end": 1.5, "text_translated": "Chào mừng bạn đến với kênh."},
        {"id": 1, "start": 1.6, "end": 3.0, "text_translated": "Hôm nay chúng ta cùng xem một đoạn phim hay."},
    ]
    output_wav = "D:/DuAnCaNhan/video_ai/be/tests/unit/test_output_seq.wav"
    try:
        res = await DubbingAudioAligner.build_dubbing_track(
            segments=test_segments,
            total_duration_sec=3.5,
            output_track_path=output_wav,
            voice="vi-VN-NamMinhNeural",
            voice_profile_id=None,
        )
        assert Path(res).exists()
        assert Path(res).stat().st_size > 1000
    finally:
        Path(output_wav).unlink(missing_ok=True)
