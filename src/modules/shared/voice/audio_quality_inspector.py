import io
from pathlib import Path
from typing import Union, Dict, Any, Tuple
import numpy as np
from pydub import AudioSegment  # type: ignore

try:
    import librosa  # type: ignore
except ImportError:
    librosa = None


def _load_waveform(
    source: Union[str, Path, bytes, io.BytesIO],
    target_sr: int = 24000,
) -> Tuple[np.ndarray, int]:
    """Tải và chuẩn hóa waveform dạng mono float32 trong khoảng [-1.0, 1.0]."""
    if isinstance(source, (bytes, bytearray)):
        bio = io.BytesIO(source)
        audio = AudioSegment.from_file(bio)
    elif isinstance(source, io.BytesIO):
        audio = AudioSegment.from_file(source)
    else:
        audio = AudioSegment.from_file(str(source))

    audio = audio.set_channels(1).set_frame_rate(target_sr)
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)

    max_val = float(1 << (audio.sample_width * 8 - 1))
    waveform = samples / max_val
    return waveform, target_sr


def calculate_snr_db(waveform: np.ndarray, sr: int) -> float:
    """Tính tỷ số tín hiệu trên nhiễu (Signal-to-Noise Ratio in dB) chuẩn âm học."""
    if len(waveform) < sr * 0.2:
        return 0.0

    frame_len = int(sr * 0.03)  # Khung 30ms
    hop_len = int(sr * 0.015)   # Bước nhảy 15ms
    num_frames = (len(waveform) - frame_len) // hop_len
    if num_frames < 5:
        return 0.0

    energies = np.array([
        np.mean(waveform[i * hop_len : i * hop_len + frame_len] ** 2)
        for i in range(num_frames)
    ])

    sorted_e = np.sort(energies)
    # 10% năng lượng thấp nhất làm mẫu tạp âm nền (Noise Floor)
    noise_count = max(1, int(len(sorted_e) * 0.10))
    noise_power = float(np.mean(sorted_e[:noise_count])) + 1e-12

    # 50% năng lượng cao nhất làm mẫu giọng nói (Speech Frames)
    speech_start = int(len(sorted_e) * 0.50)
    speech_power = float(np.mean(sorted_e[speech_start:])) + 1e-12

    if speech_power <= noise_power:
        return 0.0

    snr = 10.0 * np.log10(speech_power / noise_power)
    # Giới hạn ngưỡng hiển thị thực tế từ 0 đến 40 dB
    return float(np.clip(snr, 0.0, 40.0))


def detect_clipping(waveform: np.ndarray, threshold: float = 0.985) -> Tuple[bool, float]:
    """Phát hiện lỗi vỡ tiếng do nói quá sát micro (Clipping distortion)."""
    if len(waveform) == 0:
        return False, 0.0
    clipped_samples = np.sum(np.abs(waveform) >= threshold)
    ratio = float(clipped_samples / len(waveform))
    is_clipped = bool(ratio > 0.001)  # Vượt quá 0.1% số mẫu bão hòa
    return is_clipped, round(ratio * 100, 3)


def analyze_spectral_flatness(waveform: np.ndarray, sr: int) -> float:
    """Đo độ phẳng phổ âm học (Spectral Flatness): Nhận diện tiếng quạt gió, rít hiss."""
    if librosa is not None and len(waveform) >= 1024:
        try:
            flatness = librosa.feature.spectral_flatness(y=waveform)[0]
            return float(np.mean(flatness))
        except Exception:
            pass

    # Fallback ước lượng nếu librosa không nạp được
    fft_mag = np.abs(np.fft.rfft(waveform[: min(len(waveform), 8192)])) + 1e-9
    geo_mean = np.exp(np.mean(np.log(fft_mag)))
    arith_mean = np.mean(fft_mag)
    return float(geo_mean / arith_mean)


def inspect_audio_quality(
    source: Union[str, Path, bytes, io.BytesIO],
) -> Dict[str, Any]:
    """Đánh giá toàn diện chất lượng âm thanh trước khi huấn luyện AI."""
    waveform, sr = _load_waveform(source)
    duration_sec = round(len(waveform) / sr, 2)

    snr_db = round(calculate_snr_db(waveform, sr), 1)
    is_clipped, clip_pct = detect_clipping(waveform)
    flatness = round(analyze_spectral_flatness(waveform, sr), 4)

    # Tính RMS dBFS
    rms = float(np.sqrt(np.mean(waveform ** 2))) + 1e-9
    rms_dbfs = round(20.0 * np.log10(rms), 1)

    issues = []
    # Điểm chất lượng tính theo thang 100:
    # SNR đóng góp tối đa 75 điểm (25dB đạt tối đa 75 điểm)
    score = int(min(75, (snr_db / 28.0) * 75))

    if is_clipped:
        score -= 30
        issues.append(f"Âm thanh bị vỡ rè do nói quá gần mic ({clip_pct}% clipped)")

    if snr_db < 15.0:
        issues.append(f"Tạp âm môi trường lớn (SNR {snr_db} dB < 15 dB)")
    elif snr_db < 22.0:
        issues.append(f"Có tiếng ồn nền nhẹ (SNR {snr_db} dB)")

    if flatness > 0.08:
        score -= 15
        issues.append("Phát hiện tiếng quạt gió hoặc tiếng rít micro (Hiss)")
    else:
        score += 15  # Thưởng điểm cho giọng có tính chu kỳ hài hòa

    if rms_dbfs < -38.0:
        score -= 15
        issues.append(f"Âm lượng quá nhỏ ({rms_dbfs} dBFS), cần nói to hơn")
    elif -28.0 <= rms_dbfs <= -12.0:
        score += 10
    else:
        score += 5

    score = int(np.clip(score, 5, 99))

    # Xác định nhãn và khuyến nghị
    if is_clipped:
        quality_label = "CLIPPED"
        recommendation = "RETRY_RECORDING"
    elif snr_db >= 25.0 and flatness <= 0.05:
        quality_label = "STUDIO"
        recommendation = "PROCEED"
    elif snr_db >= 17.0:
        quality_label = "ACCEPTABLE"
        recommendation = "AUTO_DENOISE"
    else:
        quality_label = "NOISY"
        recommendation = "AUTO_DENOISE"

    return {
        "snr_db": snr_db,
        "quality_score": score,
        "quality_label": quality_label,
        "recommendation": recommendation,
        "is_clean": snr_db >= 24.0 and not is_clipped,
        "is_clipped": is_clipped,
        "clip_percentage": clip_pct,
        "spectral_flatness": flatness,
        "rms_dbfs": rms_dbfs,
        "duration_seconds": duration_sec,
        "issues": issues,
    }
