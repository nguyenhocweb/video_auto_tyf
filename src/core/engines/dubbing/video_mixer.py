import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger("dubbing_video_mixer")


class DubbingVideoMixer:
    """Engine kết hợp FFmpeg dập phụ đề (Hardsub) và hòa âm điện ảnh thông minh (Dynamic Sidechain Audio Ducking)."""

    @classmethod
    def _escape_filter_path(cls, file_path: str) -> str:
        """Chuẩn hóa đường dẫn file để tương thích an toàn với bộ lọc FFmpeg trên Windows."""
        resolved = str(Path(file_path).resolve()).replace("\\", "/")
        return resolved.replace(":", "\\:").replace("'", "\\'")

    @classmethod
    def _has_audio_stream(cls, file_path: str) -> bool:
        """Kiểm tra file video có track âm thanh hợp lệ hay không bằng ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", file_path,
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
            return "audio" in res.stdout.decode().lower()
        except Exception:
            return True

    @classmethod
    def _build_audio_filter(
        cls, has_orig_audio: bool, voice_vol: float, bgm_vol: float = 0.08, dynamic: bool = True
    ) -> str:
        """
        Tạo filter complex hòa âm điện ảnh:
        - dynamic=True (Sidechain): Tách luồng giọng đọc bằng asplit=2 (1 nhánh kích hoạt nén nhạc nền, 1 nhánh hòa âm chính).
          Nhạc nền tự hạ xuống ~10% khi có giọng nói, dâng lên mượt mà dứt khoát chuẩn Short-form (release=280ms).
        - dynamic=False (Fallback): Hạ đều âm lượng gốc xuống mức cố định an toàn.
        """
        if not has_orig_audio:
            return (
                f"[1:a]aformat=channel_layouts=stereo:sample_rates=44100,highpass=f=80,"
                f"volume={voice_vol},alimiter=limit=0.96:attack=5:release=50[aout]"
            )

        safe_bgm = max(0.03, min(bgm_vol, 0.15))
        if dynamic:
            return (
                f"[0:a]aformat=channel_layouts=stereo:sample_rates=44100,volume={safe_bgm}[bgm];"
                f"[1:a]aformat=channel_layouts=stereo:sample_rates=44100,highpass=f=80,lowpass=f=12000,volume={voice_vol},asplit=2[vox_sc][vox_main];"
                f"[bgm][vox_sc]sidechaincompress=threshold=0.020:ratio=14:attack=5:release=220:knee=2.0:makeup=1[ducked];"
                f"[ducked][vox_main]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.96:attack=5:release=50[aout]"
            )
        return (
            f"[0:a]aformat=channel_layouts=stereo:sample_rates=44100,volume={safe_bgm}[a0];"
            f"[1:a]aformat=channel_layouts=stereo:sample_rates=44100,highpass=f=80,volume={voice_vol}[a1];"
            f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.96:attack=5:release=50[aout]"
        )

    @classmethod
    def mix_video(
        cls,
        video_path: str,
        output_path: str,
        mode: str = "both",
        subtitle_path: Optional[str] = None,
        dubbed_audio_path: Optional[str] = None,
        bgm_volume: float = 0.08,
        voice_volume: float = 1.35,
    ) -> str:
        """Render video theo 3 chế độ: 'vietsub', 'dubbing', 'both' kèm Sidechain Audio Ducking điện ảnh."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        has_orig_audio = cls._has_audio_stream(video_path)

        if mode == "vietsub":
            if not subtitle_path or not os.path.exists(subtitle_path):
                raise ValueError("Thiếu file phụ đề (.ass hoặc .srt) cho chế độ vietsub.")
            esc_sub = cls._escape_filter_path(subtitle_path)
            filter_str = f"ass='{esc_sub}'" if subtitle_path.endswith(".ass") else f"subtitles='{esc_sub}'"
            cmd = [
                "ffmpeg", "-y", "-i", video_path, "-vf", filter_str,
                "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "copy", output_path,
            ]
            cls._execute_ffmpeg(cmd, "Chỉ Vietsub")
            return output_path

        elif mode == "dubbing":
            if not dubbed_audio_path or not os.path.exists(dubbed_audio_path):
                raise ValueError("Thiếu file âm thanh thuyết minh cho chế độ dubbing.")

            fc_dyn = cls._build_audio_filter(has_orig_audio, voice_volume, bgm_volume, dynamic=True)
            cmd_dyn = [
                "ffmpeg", "-y", "-i", video_path, "-i", dubbed_audio_path,
                "-filter_complex", fc_dyn, "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", output_path,
            ]
            fc_fb = cls._build_audio_filter(has_orig_audio, voice_volume, bgm_volume, dynamic=False)
            cmd_fb = [
                "ffmpeg", "-y", "-i", video_path, "-i", dubbed_audio_path,
                "-filter_complex", fc_fb, "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", output_path,
            ]
            cls._execute_ffmpeg(cmd_dyn, "Thuyết Minh (Sidechain Ducking)", fallback_cmd=cmd_fb)
            return output_path

        elif mode == "both":
            if not subtitle_path or not os.path.exists(subtitle_path):
                raise ValueError("Thiếu file phụ đề cho chế độ both.")
            if not dubbed_audio_path or not os.path.exists(dubbed_audio_path):
                raise ValueError("Thiếu file âm thanh thuyết minh cho chế độ both.")

            esc_sub = cls._escape_filter_path(subtitle_path)
            vf_sub = f"ass='{esc_sub}'" if subtitle_path.endswith(".ass") else f"subtitles='{esc_sub}'"

            fc_dyn = f"[0:v]{vf_sub}[vout];" + cls._build_audio_filter(has_orig_audio, voice_volume, bgm_volume, dynamic=True)
            cmd_dyn = [
                "ffmpeg", "-y", "-i", video_path, "-i", dubbed_audio_path,
                "-filter_complex", fc_dyn, "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac", "-b:a", "192k", output_path,
            ]
            fc_fb = f"[0:v]{vf_sub}[vout];" + cls._build_audio_filter(has_orig_audio, voice_volume, bgm_volume, dynamic=False)
            cmd_fb = [
                "ffmpeg", "-y", "-i", video_path, "-i", dubbed_audio_path,
                "-filter_complex", fc_fb, "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac", "-b:a", "192k", output_path,
            ]
            cls._execute_ffmpeg(cmd_dyn, "Vietsub & Thuyết Minh (Sidechain Ducking)", fallback_cmd=cmd_fb)
            return output_path

        else:
            raise ValueError(f"Chế độ '{mode}' không hợp lệ. Chọn 'vietsub', 'dubbing', hoặc 'both'.")

    @classmethod
    def get_media_duration(cls, file_path: str) -> float:
        """Lấy thời lượng video/audio qua ffprobe."""
        try:
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", file_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
            return float(res.stdout.decode().strip())
        except Exception:
            return 30.0

    @classmethod
    def transform_reup_video(
        cls,
        video_path: str,
        output_path: str,
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.95,
        orig_audio_volume: float = 0.15,
        zoom_factor: float = 1.04,
    ) -> str:
        """
        Mô hình 2: Biến đổi video tự động lách bản quyền & thuật toán pHash/Content ID:
        - Zoom nhẹ 1.04x và crop giữa (làm biến dạng lưới tọa độ điểm ảnh pHash).
        - Chỉnh màu nhẹ (contrast +2%, saturation +3%) làm lệch biểu đồ màu Histogram.
        - Xóa sạch metadata của ByteDance/Douyin (-map_metadata -1).
        - Tách bỏ/hạ nhạc nền cũ xuống mức an toàn, lồng ghép BGM bản quyền sạch (kèm tự động loop & fade out 2s cuối).
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        dur = cls.get_media_duration(video_path)
        has_orig_audio = cls._has_audio_stream(video_path)

        vf_reup = (
            f"scale=iw*{zoom_factor:.2f}:ih*{zoom_factor:.2f},"
            f"crop=iw/{zoom_factor:.2f}:ih/{zoom_factor:.2f}:(iw*{zoom_factor:.2f}-iw)/2:(ih*{zoom_factor:.2f}-ih)/2,"
            "eq=contrast=1.02:brightness=0.01:saturation=1.03"
        )

        fade_start = max(0.5, dur - 2.0)
        if bgm_path and os.path.exists(bgm_path):
            if has_orig_audio and orig_audio_volume > 0.01:
                fc = (
                    f"[0:v]{vf_reup}[vout];"
                    f"[0:a]volume={orig_audio_volume:.2f}[a_orig];"
                    f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{dur:.2f},asetpts=PTS-STARTPTS,"
                    f"volume={bgm_volume:.2f},afade=t=out:st={fade_start:.2f}:d=2[a_bgm];"
                    f"[a_orig][a_bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
                )
            else:
                fc = (
                    f"[0:v]{vf_reup}[vout];"
                    f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{dur:.2f},asetpts=PTS-STARTPTS,"
                    f"volume={bgm_volume:.2f},afade=t=out:st={fade_start:.2f}:d=2[aout]"
                )
            cmd = [
                "ffmpeg", "-y", "-i", video_path, "-i", bgm_path,
                "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
                "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                "-c:a", "aac", "-b:a", "192k", "-map_metadata", "-1", output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", video_path, "-vf", vf_reup,
                "-t", f"{dur:.2f}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "21",
                "-c:a", "copy" if has_orig_audio else "aac", "-map_metadata", "-1", output_path,
            ]

        cls._execute_ffmpeg(cmd, "Lách Thuật Toán Re-up (Mô hình 2)")
        return output_path

    @classmethod
    def _execute_ffmpeg(cls, cmd: List[str], task_name: str, fallback_cmd: Optional[List[str]] = None) -> None:
        """Thực thi câu lệnh FFmpeg với cơ chế tự động chuyển sang fallback nếu cần."""
        logger.info(f"Bắt đầu render FFmpeg [{task_name}]...")
        process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.returncode != 0:
            err_msg = process.stderr.decode("utf-8", errors="ignore")
            logger.warning(f"FFmpeg [{task_name}] cảnh báo/lỗi: {err_msg[-350:]}")
            if fallback_cmd:
                logger.info(f"Chạy hòa âm dự phòng cho [{task_name}]...")
                fb_proc = subprocess.run(fallback_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if fb_proc.returncode == 0:
                    logger.info(f"Hòa âm dự phòng [{task_name}] thành công.")
                    return
                fb_err = fb_proc.stderr.decode("utf-8", errors="ignore")
                raise RuntimeError(f"Lỗi khi xử lý video bằng FFmpeg (kèm fallback): {fb_err[-300:]}")
            raise RuntimeError(f"Lỗi khi xử lý video bằng FFmpeg: {err_msg[-300:]}")
        logger.info(f"FFmpeg [{task_name}] hoàn tất thành công.")
