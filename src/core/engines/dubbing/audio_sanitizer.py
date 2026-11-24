import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("audio_sanitizer")


class AudioSanitizerEngine:
    """Engine xử lý tín hiệu âm thanh (Audio DSP) & làm sạch dấu vân tay bản quyền (Content ID Bypass)."""

    @staticmethod
    def probe_audio_duration(file_path: Path | str) -> float:
        """Đo lường thời lượng bản nhạc (giây) bằng ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if res.returncode == 0:
                val = float(res.stdout.decode().strip())
                return round(val, 2)
        except Exception as e:
            logger.warning(f"Lỗi khi đo thời lượng audio bằng ffprobe: {e}")
        return 0.0

    @classmethod
    def sanitize_and_trim(
        cls,
        input_path: Path,
        output_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        sanitize: bool = True,
        pitch_ratio: float = 1.025,
        tempo_ratio: float = 1.01,
        target_lufs: float = -14.0,
    ) -> Tuple[bool, float]:
        """Cắt đoạn âm thanh và làm nhiễu sóng âm bẻ gãy thuật toán nhận diện bản quyền."""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["ffmpeg", "-y"]

            # 1. Cắt đoạn thời gian (Trimming)
            if start_time is not None and start_time > 0:
                cmd.extend(["-ss", f"{start_time:.2f}"])
            if end_time is not None and end_time > (start_time or 0):
                dur = end_time - (start_time or 0)
                cmd.extend(["-t", f"{dur:.2f}"])

            cmd.extend(["-i", str(input_path)])

            # 2. Xây dựng bộ lọc Audio DSP
            filters = []
            if sanitize:
                # Bẻ dải tần cao độ (+2.5%) và tái lấy mẫu
                filters.append(f"asetrate=44100*{pitch_ratio},aresample=44100")
                # Điều hòa lại nhịp điệu (Tempo Warp)
                filters.append(f"atempo={tempo_ratio}")
                # Đổi góc pha stereo & làm rộng âm trường (Stereo Widener)
                filters.append("stereotools=mlev=0.9:slev=1.2:sbal=0.05")
                # Lọc tần số cận biên
                filters.append("highpass=f=40,lowpass=f=17000")

            # Chuẩn hóa âm lượng EBU R128 theo chuẩn phát sóng mạng xã hội (-14 LUFS)
            filters.append(f"loudnorm=I={target_lufs}:LRA=7:TP=-1.5")

            filter_str = f"[0:a]{','.join(filters)}[out_a]"
            cmd.extend([
                "-filter_complex", filter_str,
                "-map", "[out_a]",
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                str(output_path),
            ])

            logger.info(f"Bắt đầu xử lý Audio DSP Sanitizer: sanitize={sanitize}, start={start_time}, end={end_time}")
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=60)
            if res.returncode == 0 and output_path.exists():
                dur = cls.probe_audio_duration(output_path)
                logger.info(f"Xử lý audio thành công! Thời lượng xuất xưởng: {dur}s")
                return True, dur
            else:
                err_msg = res.stderr.decode(errors="ignore") if res.stderr else "Lỗi không xác định"
                logger.warning(f"FFmpeg DSP Sanitizer thất bại: {err_msg}")
        except Exception as e:
            logger.error(f"Lỗi ngoại lệ trong quá trình sanitize audio: {e}")

        # Fallback sao chép nếu DSP phức tạp gặp sự cố
        try:
            copy_cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vn", "-c:a", "libmp3lame", "-b:a", "192k", str(output_path)]
            subprocess.run(copy_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if output_path.exists():
                dur = cls.probe_audio_duration(output_path)
                return True, dur
        except Exception:
            pass

        return False, 0.0

