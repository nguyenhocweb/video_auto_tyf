import io
from pathlib import Path
from typing import Union, Tuple, Optional
import numpy as np
import scipy.signal as signal  # type: ignore
import soundfile as sf  # type: ignore
from pydub import AudioSegment  # type: ignore

from src.modules.shared.voice.audio_quality_inspector import (
    _load_waveform,
    calculate_snr_db,
)


def apply_bandpass_filter(
    waveform: np.ndarray,
    sr: int,
    low_cut: float = 80.0,
    high_cut: float = 8500.0,
) -> np.ndarray:
    """Lọc thông dải Butterworth: Triệt tiếng ù điện 50Hz và tiếng rít cao tần."""
    nyquist = 0.5 * sr
    low = max(0.001, low_cut / nyquist)
    high = min(0.999, high_cut / nyquist)

    sos = signal.butter(4, [low, high], btype="bandpass", output="sos")
    filtered = signal.sosfiltfilt(sos, waveform)
    return np.asarray(filtered, dtype=np.float32)


def spectral_subtraction_denoise(
    waveform: np.ndarray,
    sr: int,
    alpha: float = 1.6,
    beta: float = 0.03,
) -> np.ndarray:
    """Khử nhiễu nền bằng phương pháp trừ phổ động (Spectral Subtraction).

    Bảo tồn ngữ điệu tự nhiên và âm sắc giọng nói, không tạo cảm giác robot.
    """
    n_fft = 1024
    hop_length = 256
    win_length = 1024
    window = np.hanning(win_length)

    # 1. Tính biến đổi Fourier ngắn hạn (STFT)
    stft = signal.stft(
        waveform,
        fs=sr,
        window=window,
        nperseg=win_length,
        noverlap=win_length - hop_length,
        nfft=n_fft,
        boundary="zeros",
    )
    freqs, times, zxx = stft
    magnitude = np.abs(zxx)
    phase = np.angle(zxx)

    # 2. Ước tính phổ tạp âm từ 10% các frame có năng lượng thấp nhất
    frame_energy = np.mean(magnitude ** 2, axis=0)
    noise_idx = np.argsort(frame_energy)[: max(2, int(len(frame_energy) * 0.12))]
    noise_spec = np.mean(magnitude[:, noise_idx], axis=1, keepdims=True)

    # 3. Trừ phổ theo thuật toán Berouti
    sub_mag = magnitude - alpha * noise_spec
    # Giữ sàn phổ tối thiểu beta * magnitude để tránh hiện tượng musical noise
    clean_mag = np.maximum(sub_mag, beta * magnitude)

    # 4. Tái cấu trúc tín hiệu qua ISTFT với góc pha ban đầu
    clean_zxx = clean_mag * np.exp(1j * phase)
    _, clean_wav = signal.istft(
        clean_zxx,
        fs=sr,
        window=window,
        nperseg=win_length,
        noverlap=win_length - hop_length,
        nfft=n_fft,
    )

    clean_wav = clean_wav[: len(waveform)]
    return np.asarray(clean_wav, dtype=np.float32)


def normalize_loudness(
    waveform: np.ndarray,
    target_rms_dbfs: float = -20.0,
) -> np.ndarray:
    """Cân bằng âm lượng hiệu dụng (RMS Normalization) chuẩn phát thanh."""
    current_rms = float(np.sqrt(np.mean(waveform ** 2))) + 1e-9
    current_dbfs = 20.0 * np.log10(current_rms)

    gain_db = target_rms_dbfs - current_dbfs
    gain_linear = 10.0 ** (gain_db / 20.0)

    scaled = waveform * gain_linear
    # Giới hạn đỉnh ở mức -0.5 dB (~0.94) để tránh clipping
    max_peak = np.max(np.abs(scaled))
    if max_peak > 0.94:
        scaled = scaled * (0.94 / max_peak)

    return np.asarray(scaled, dtype=np.float32)


def clean_and_enhance_audio(
    source: Union[str, Path, bytes, io.BytesIO],
    output_path: Optional[Union[str, Path]] = None,
    target_sr: int = 24000,
) -> Tuple[np.ndarray, int, float, float]:
    """Quy trình làm sạch âm thanh trọn gói: Lọc dải tần -> Khử tạp âm -> Cân bằng âm lượng.

    Trả về: (waveform, sr, snr_truoc, snr_sau)
    """
    raw_wav, sr = _load_waveform(source, target_sr=target_sr)
    snr_before = calculate_snr_db(raw_wav, sr)

    # 1. Cắt ù và rít tần số cực đoan
    filtered_wav = apply_bandpass_filter(raw_wav, sr, low_cut=80.0, high_cut=8500.0)

    # 2. Khử tạp âm phổ nếu có tiếng ồn nền
    if snr_before < 28.0:
        denoised_wav = spectral_subtraction_denoise(filtered_wav, sr)
    else:
        denoised_wav = filtered_wav

    # 3. Cân bằng âm lượng chuẩn phòng thu
    enhanced_wav = normalize_loudness(denoised_wav, target_rms_dbfs=-20.0)
    snr_after = calculate_snr_db(enhanced_wav, sr)

    if output_path is not None:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_p), enhanced_wav, sr, subtype="PCM_16")

    return enhanced_wav, sr, snr_before, snr_after

