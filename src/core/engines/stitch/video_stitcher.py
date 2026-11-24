import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("video_stitcher")


class VideoStitcher:
    """Engine lõi xử lý cắt ghép 2 nguồn video (Hook + Body), hỗ trợ 9:16 / 16:9 và chuyển cảnh mượt mà xfade."""

    @staticmethod
    def get_media_duration(file_path: str) -> float:
        """Lấy tổng thời lượng (giây) của file media qua ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1", str(file_path),
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            return max(0.0, float(res.stdout.decode().strip()))
        except Exception as ex:
            logger.warning(f"Không thể lấy thời lượng file {file_path}: {ex}")
            return 0.0

    @staticmethod
    def has_audio_stream(file_path: str) -> bool:
        """Kiểm tra file video có track âm thanh hợp lệ hay không."""
        try:
            cmd = [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(file_path),
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
            return "audio" in res.stdout.decode().lower()
        except Exception:
            return True

    @staticmethod
    def extract_hook_clip(
        raw_video_path: str,
        duration: float,
        out_path: str,
        aspect_ratio: str = "9:16",
    ) -> str:
        """Cắt đoạn đầu (0 -> duration giây) và chuẩn hóa về tỷ lệ 9:16 (1080x1920) hoặc 16:9 (1920x1080)."""
        p_in = Path(raw_video_path)
        p_out = Path(out_path)
        p_out.parent.mkdir(parents=True, exist_ok=True)

        if not p_in.exists():
            raise FileNotFoundError(f"Không tìm thấy video nguồn Hook: {raw_video_path}")

        tw, th = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
        has_audio = VideoStitcher.has_audio_stream(raw_video_path)

        # Tạo nền video mờ (Blurred Background) thay vì dải đen nếu tỷ lệ video gốc khác với tỷ lệ đích
        filter_parts = [
            f"[0:v]split[bg_in][fg_in];"
            f"[bg_in]scale={tw}:{th}:force_original_aspect_ratio=increase,"
            f"crop={tw}:{th},boxblur=25:5,eq=brightness=-0.08:contrast=1.05,setsar=1,fps=30[bg];"
            f"[fg_in]scale={tw}:{th}:force_original_aspect_ratio=decrease,setsar=1,fps=30[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[vout]"
        ]

        cmd = [
            "ffmpeg", "-y", "-ss", "0", "-t", str(duration), "-i", str(p_in),
        ]

        if has_audio:
            cmd.extend([
                "-filter_complex", "".join(filter_parts),
                "-map", "[vout]", "-map", "0:a:0",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
            ])
        else:
            filter_parts.append(";anullsrc=channel_layout=stereo:sample_rate=44100[aout]")
            cmd.extend([
                "-filter_complex", "".join(filter_parts),
                "-map", "[vout]", "-map", "[aout]",
                "-c:a", "aac", "-b:a", "192k",
            ])

        cmd.extend([
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-shortest", str(p_out),
        ])

        logger.info(f"Đang cắt Hook clip ({duration}s, {aspect_ratio}) sang: {out_path}")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        if res.returncode != 0:
            err_msg = res.stderr.decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg extract hook failed: {err_msg}")
            raise RuntimeError(f"Lỗi cắt Hook clip: {err_msg[:250]}")

        return str(p_out)

    @staticmethod
    def stitch_hook_and_body(
        hook_path: str,
        body_path: str,
        body_skip_sec: float,
        out_path: str,
        audio_mode: str = "sequential",
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.9,
        aspect_ratio: str = "9:16",
        transition_duration: float = 1.2,
    ) -> str:
        """
        Ghép nối Hook (Đầu) và Body (Đuôi) bằng FFmpeg xfade (mờ dần video 1, hiện dần video 2).
        Hỗ trợ chuẩn 9:16 (1080x1920) hoặc 16:9 (1920x1080).
        Thời lượng chuyển cảnh mặc định 1.2s giúp hiệu ứng mờ dần chậm rãi, êm dịu và không bị giật/nhanh.
        """
        p_hook = Path(hook_path)
        p_body = Path(body_path)
        p_out = Path(out_path)
        p_out.parent.mkdir(parents=True, exist_ok=True)

        if not p_hook.exists():
            raise FileNotFoundError(f"Không tìm thấy file Hook: {hook_path}")
        if not p_body.exists():
            raise FileNotFoundError(f"Không tìm thấy file Body: {body_path}")

        tw, th = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)
        hook_dur = VideoStitcher.get_media_duration(hook_path)
        has_hook_a = VideoStitcher.has_audio_stream(hook_path)
        has_body_a = VideoStitcher.has_audio_stream(body_path)

        # Tính toán offset chuyển cảnh: video 1 mờ dần chậm rãi và video 2 hiện lên mượt mà
        max_allowed = max(0.5, hook_dur * 0.5)
        trans_dur = min(float(transition_duration), max_allowed)
        offset = max(0.1, round(hook_dur - trans_dur, 2))

        # 1. Chuẩn hóa 2 luồng video về cùng kích thước & fps với NỀN MỜ (Blurred Background)
        # Thay vì pad viền đen, luồng nền scale phóng to phủ kín khung hình + làm mờ (boxblur),
        # luồng gốc scale giữ tỷ lệ đặt chính giữa lên trên nền mờ.
        vf_hook = (
            f"[0:v]split[bg0_in][fg0_in];"
            f"[bg0_in]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},"
            f"boxblur=25:5,eq=brightness=-0.08:contrast=1.05,setsar=1,fps=30[bg0];"
            f"[fg0_in]scale={tw}:{th}:force_original_aspect_ratio=decrease,setsar=1,fps=30[fg0];"
            f"[bg0][fg0]overlay=(W-w)/2:(H-h)/2[v0];"
        )
        vf_body = (
            f"[1:v]trim=start={body_skip_sec},setpts=PTS-STARTPTS,split[bg1_in][fg1_in];"
            f"[bg1_in]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},"
            f"boxblur=25:5,eq=brightness=-0.08:contrast=1.05,setsar=1,fps=30[bg1];"
            f"[fg1_in]scale={tw}:{th}:force_original_aspect_ratio=decrease,setsar=1,fps=30[fg1];"
            f"[bg1][fg1]overlay=(W-w)/2:(H-h)/2[v1];"
        )
        # Chuyển cảnh xfade mượt mà: transition=fade (Crossfade / Dissolve)
        vf_transition = f"[v0][v1]xfade=transition=fade:duration={trans_dur}:offset={offset}[vout]"
        filter_parts = [vf_hook, vf_body, vf_transition]

        # 2. Xử lý các kịch bản Âm thanh
        inputs = ["-i", str(p_hook), "-i", str(p_body)]

        if audio_mode == "bgm_override" and bgm_path and Path(bgm_path).exists():
            inputs.extend(["-i", str(bgm_path)])
            af = (
                f";[2:a]aformat=channel_layouts=stereo:sample_rates=44100,"
                f"volume={bgm_volume},aloop=loop=-1:size=2e+09[aout]"
            )
            filter_parts.append(af)
        elif audio_mode == "body_audio" and has_body_a:
            af = ";[1:a]aformat=channel_layouts=stereo:sample_rates=44100[aout]"
            filter_parts.append(af)
        elif audio_mode == "hook_audio" and has_hook_a:
            af = ";[0:a]aformat=channel_layouts=stereo:sample_rates=44100,aloop=loop=-1:size=2e+09[aout]"
            filter_parts.append(af)
        else:
            # Chế độ sequential (Nối tiếp tự nhiên có hòa âm mềm acrossfade)
            if has_hook_a and has_body_a:
                af = (
                    f";[0:a]aformat=channel_layouts=stereo:sample_rates=44100[a0];"
                    f"[1:a]atrim=start={body_skip_sec},asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo:sample_rates=44100[a1];"
                    f"[a0][a1]acrossfade=d={trans_dur}:curve1=exp:curve2=exp[aout]"
                )
            elif has_body_a:
                af = f";[1:a]atrim=start={body_skip_sec},asetpts=PTS-STARTPTS,aformat=channel_layouts=stereo:sample_rates=44100[aout]"
            elif has_hook_a:
                af = ";[0:a]aformat=channel_layouts=stereo:sample_rates=44100,apad[aout]"
            else:
                af = ";anullsrc=channel_layout=stereo:sample_rate=44100[aout]"
            filter_parts.append(af)

        full_filter = "".join(filter_parts)

        cmd = [
            "ffmpeg", "-y", *inputs,
            "-filter_complex", full_filter,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(p_out),
        ]

        logger.info(
            f"Đang render ghép xfade ({aspect_ratio}, trans={trans_dur}s @ {offset}s): "
            f"Hook [{p_hook.name}] + Body [{p_body.name}] -> [{p_out.name}]"
        )
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240)
        if res.returncode != 0:
            err_msg = res.stderr.decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg stitch failed: {err_msg}")
            raise RuntimeError(f"Lỗi ghép nối video: {err_msg[:250]}")

        return str(p_out)
