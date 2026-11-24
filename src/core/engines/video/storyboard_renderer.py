import os
import subprocess
import asyncio
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("storyboard_renderer")

class StoryboardRenderer:
    """Engine ghep anh tĩnh sắc nét và long tieng AI thanh video kịch bản hoàn chỉnh."""

    @classmethod
    async def synthesize_audio_edge(
        cls, text: str, voice_name: str, output_path: str
    ) -> float:
        """Tao giong doc thuyet minh tieng Viet bang edge-tts hoac tao silence fallback."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, voice_name or "vi-VN-NamMinhNeural")
            await asyncio.wait_for(communicate.save(output_path), timeout=12.0)
            dur = cls.get_audio_duration(output_path)
            if dur > 0.5:
                return dur
        except Exception as te:
            logger.warning(f"edge-tts offline/timeout ({te}). Tao audio fallback de render...")

        # Fallback neu offline: Tao audio dem tuong ung voi toc do doc (khoang 0.35s/tu)
        words = len(text.split())
        calc_dur = max(2.5, round(words * 0.35 + 0.8, 1))
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(calc_dur),
            "-c:a", "libmp3lame",
            output_path,
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return calc_dur

    @classmethod
    async def synthesize_audio(
        cls, text: str, voice_name: str, output_path: str
    ) -> float:
        """
        Tổng hợp giọng thuyết minh:
        - Nếu là preset Edge-TTS (vi-VN-...): sử dụng Edge-TTS.
        - Nếu là Profile Model đã training: sử dụng OmniVoice Clone.
        - Nếu có sự cố / offline: tự động fallback mượt mà sang Edge-TTS để video luôn render thành công.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        is_edge = not voice_name or voice_name.startswith("vi-") or "Neural" in voice_name

        if not is_edge:
            try:
                from src.modules.shared.voice.schemas import VoiceSynthesizeFromProfileRequest
                from src.modules.shared.voice.service import OmniVoiceService

                req = VoiceSynthesizeFromProfileRequest(
                    profile_id_or_path=voice_name,
                    text=text,
                    speed=1.0,
                    num_step=16,
                )
                voice_service = OmniVoiceService()
                res = await voice_service.synthesize_from_profile(req)
                if res.audio_path and os.path.exists(res.audio_path):
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", res.audio_path,
                        "-c:a", "libmp3lame",
                        "-b:a", "192k",
                        output_path,
                    ]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    dur = cls.get_audio_duration(output_path)
                    if dur > 0.5:
                        return dur
            except Exception as exc:
                logger.warning(
                    f"Không thể sinh giọng bằng profile '{voice_name}' ({exc}). Fallback sang Edge-TTS..."
                )

        # Fallback sang Edge-TTS giọng Việt chuẩn (Nam Minh hoặc Hoài My)
        fallback_voice = voice_name if (is_edge and voice_name) else "vi-VN-NamMinhNeural"
        return await cls.synthesize_audio_edge(text, fallback_voice, output_path)

    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        """Lay thoi luong file am thanh bang ffprobe."""
        if not os.path.exists(audio_path):
            return 3.0
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            return float(res.stdout.strip())
        except Exception:
            return 3.0

    @classmethod
    def render_scene_clip(
        cls, image_path: str, audio_path: str, duration: float, output_path: str
    ) -> bool:
        """
        Ket hop 1 anh va 1 file am thanh thanh 1 video clip sac net, chuyen canh muot ma.
        Tu dong phat hien ti le anh (9:16 doc hoac 16:9 ngang) de tranh cat meo hinh.
        Them khoang ngat nhịp tu nhien 0.25s giua cac cau giup video khong bi don dap, do cung.
        """
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        is_vertical = False
        try:
            from PIL import Image
            with Image.open(image_path) as im:
                w, h = im.size
                if h > w * 1.15:
                    is_vertical = True
        except Exception:
            pass

        target_wh = "1080:1920" if is_vertical else "1920:1080"
        vf = f"scale={target_wh}:force_original_aspect_ratio=increase,crop={target_wh},fps=30"

        pad_dur = 0.25
        clip_dur = max(1.0, duration + pad_dur)

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-t", f"{clip_dur:.2f}",
            "-i", image_path,
            "-i", audio_path,
            "-vf", vf,
            "-af", f"apad=pad_dur={pad_dur:.2f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return res.returncode == 0 and os.path.exists(output_path)

    @classmethod
    def concat_clips(cls, clip_paths: List[str], output_path: str) -> bool:
        """Ghep noi tat ca cac clip con thanh video dai hoan chinh bang concat demuxer."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        list_txt_path = os.path.join(os.path.dirname(output_path), "concat_list.txt")

        with open(list_txt_path, "w", encoding="utf-8") as f:
            for cp in clip_paths:
                clean_path = os.path.abspath(cp).replace("\\", "/")
                f.write(f"file '{clean_path}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_txt_path,
            "-c", "copy",
            output_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return res.returncode == 0 and os.path.exists(output_path)

    @classmethod
    async def render_storyboard(
        cls,
        scenes: List[Dict[str, Any]],
        voice_name: str,
        output_dir: str,
    ) -> Dict[str, Any]:
        """Quy trinh tong the: tao voice -> render tat ca clip canh -> ghep video cuoi cung."""
        os.makedirs(output_dir, exist_ok=True)
        scene_clips = []
        total_duration = 0.0
        last_valid_img = None

        for idx, scene in enumerate(scenes):
            s_idx = scene.get("scene_idx", idx + 1)
            narration = scene.get("narration", "").strip() or f"Cảnh {s_idx}"
            image_path = scene.get("image_path", "")

            # Neu co anh thi luu lai anh gan nhat
            if image_path and os.path.exists(image_path):
                last_valid_img = image_path
            elif last_valid_img:
                # Ke thua anh hop le gan nhat de video lien mach, khong bi man hinh den
                image_path = last_valid_img
            else:
                # Neu chua co bat ky anh nao duoc nap, tao placeholder
                alt_placeholder = os.path.join(output_dir, f"placeholder_{s_idx}.jpg")
                cmd_p = [
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", "color=c=0x18181b:s=1920x1080:d=1",
                    "-vframes", "1", alt_placeholder
                ]
                subprocess.run(cmd_p, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                image_path = alt_placeholder

            # 1. Tao voiceover cho canh
            audio_path = os.path.join(output_dir, f"scene_{s_idx}_voice.mp3")
            dur = await cls.synthesize_audio(narration, voice_name, audio_path)
            total_duration += (dur + 0.25)

            # 2. Render clip canh (anh tinh mac dinh sac net)
            clip_path = os.path.join(output_dir, f"scene_{s_idx}_clip.mp4")
            success = cls.render_scene_clip(image_path, audio_path, dur, clip_path)
            if success:
                scene_clips.append(clip_path)

        if not scene_clips:
            raise RuntimeError("Không thể kết xuất bất kỳ phân cảnh nào của kịch bản.")

        # 3. Ghep toan bo tat ca cac canh thanh video final
        final_mp4 = os.path.join(output_dir, "final_storyboard.mp4")
        concat_ok = cls.concat_clips(scene_clips, final_mp4)
        if not concat_ok:
            raise RuntimeError("Lỗi khi ghép nối các phân cảnh thành video hoàn chỉnh.")

        return {
            "final_video_path": final_mp4,
            "total_duration": round(total_duration, 2),
            "scenes_rendered": len(scene_clips),
        }
