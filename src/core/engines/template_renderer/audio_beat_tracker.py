"""Audio Beat Tracker: Thuật toán phân tích nhịp trống (Kick/Snare Onset & Bass Drop).
Sử dụng FFmpeg xuất PCM nhẹ + tính năng lượng RMS vi sai (Spectral Flux Approximation).
Không phụ thuộc thư viện nặng ngoài, tốc độ phân tích < 0.3s cho file 15s.
"""

import logging
import math
import struct
import subprocess
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger("audio_beat_tracker")


class AudioBeatTracker:
    """Bộ bóc tách nhịp điệu âm thanh độ chính xác cao cho Video Templates."""

    @staticmethod
    def detect_onsets(
        audio_path: str,
        min_interval_sec: float = 0.3,
        threshold_ratio: float = 1.35,
    ) -> List[float]:
        """Phát hiện các điểm nảy nhịp (Beat Onset Timestamps) trong file âm thanh.
        
        Args:
            audio_path: Đường dẫn tới file âm thanh hoặc video
            min_interval_sec: Khoảng cách tối thiểu giữa 2 nhịp nảy (chống trùng nhịp)
            threshold_ratio: Hệ số nhân ngưỡng năng lượng (càng cao nhịp càng chọn lọc)
            
        Returns:
            Danh sách thời điểm xuất hiện beat tính bằng giây (ví dụ: [3.8, 4.5, 5.2, ...])
        """
        path = Path(audio_path)
        if not path.is_file():
            logger.warning(f"File audio không tồn tại: {audio_path}")
            return []

        try:
            # Lấy raw PCM 16-bit Mono ở tần số lấy mẫu thấp 1000Hz (1 sample = 1ms)
            cmd = [
                "ffmpeg", "-y", "-i", str(path),
                "-vn", "-ac", "1", "-ar", "1000",
                "-f", "s16le", "-"
            ]
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            raw_data, _ = process.communicate()

            if not raw_data:
                return []

            # Unpack mẫu PCM
            num_samples = len(raw_data) // 2
            samples = struct.unpack(f"<{num_samples}h", raw_data)

            # Tính RMS năng lượng cho từng khung 50ms (50 mẫu ở 1000Hz)
            frame_ms = 50
            hop_ms = 25
            energies: List[Tuple[float, float]] = []

            for i in range(0, num_samples - frame_ms, hop_ms):
                window = samples[i : i + frame_ms]
                rms = math.sqrt(sum(s * s for s in window) / frame_ms)
                time_sec = (i + frame_ms / 2.0) / 1000.0
                energies.append((time_sec, rms))

            if not energies:
                return []

            # Tính năng lượng trung bình toàn bài
            avg_energy = sum(e[1] for e in energies) / len(energies)
            threshold = avg_energy * threshold_ratio

            # Phát hiện Onset qua độ dốc gia tăng năng lượng (Flux > 0)
            onsets: List[float] = []
            last_onset_time = -10.0

            for idx in range(1, len(energies) - 1):
                t, curr_e = energies[idx]
                _, prev_e = energies[idx - 1]
                _, next_e = energies[idx + 1]

                # Điều kiện Onset: Năng lượng vượt ngưỡng và là đỉnh cục bộ (Local Peak)
                is_peak = curr_e > prev_e and curr_e >= next_e
                is_loud_enough = curr_e > threshold
                flux = curr_e - prev_e

                if is_peak and is_loud_enough and flux > 300:
                    if (t - last_onset_time) >= min_interval_sec:
                        onsets.append(round(t, 2))
                        last_onset_time = t

            logger.info(f"Đã phát hiện {len(onsets)} nhịp beat trong audio ({audio_path}): {onsets}")
            return onsets

        except Exception as e:
            logger.error(f"Lỗi khi phân tích beat audio: {e}", exc_info=True)
            return []
