"""Lõi điều phối Render Template Video (GPU Hybrid Engine).
Hỗ trợ đa mẫu video CapCut: Mẫu 01 (1 Video/Ảnh + 1 Ảnh) và Mẫu 02 (3 Ảnh Tĩnh).
Tự động thích ứng số lượng Slot linh hoạt, chống crash khi nạp mẫu CapCut động.
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw

from src.core.engines.template_renderer.audio_beat_tracker import AudioBeatTracker
from src.core.engines.template_renderer.shader_filters import ShaderFilterBuilder
from src.core.engines.template_renderer.spec_models import TemplateSpec

logger = logging.getLogger("template_render_engine")


class TemplateRenderEngine:
    """Bộ máy render video mẫu tự động hóa theo chuẩn kiến trúc Hybrid Pipeline."""

    def __init__(self, templates_dir: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent
        self.templates_dir = Path(templates_dir) if templates_dir else base_dir / "templates"
        self.assets_dir = base_dir / "assets"
        self.output_dir = Path("be/storage/temp/templates_output").resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.mask_path = self._ensure_rounded_corner_overlay()
        self._has_nvenc = self._probe_nvenc_runtime()

    def _ensure_rounded_corner_overlay(self) -> Path:
        """Đảm bảo file viền đen bo góc tròn (rounded_corner_overlay.png) luôn sẵn sàng."""
        overlay_file = (self.assets_dir / "rounded_corner_overlay.png").resolve()
        if not overlay_file.is_file():
            self.assets_dir.mkdir(parents=True, exist_ok=True)
            w, h, radius = 720, 1280, 42
            scale = 2
            overlay_hi = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 255))
            draw = ImageDraw.Draw(overlay_hi)
            draw.rounded_rectangle([0, 0, w * scale - 1, h * scale - 1], radius=radius * scale, fill=(0, 0, 0, 0))
            overlay = overlay_hi.resize((w, h), Image.Resampling.LANCZOS)
            overlay.save(str(overlay_file))
        return overlay_file

    def _probe_nvenc_runtime(self) -> bool:
        """Kiểm tra thực tế GPU có chạy được h264_nvenc hay không."""
        try:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=0.1:size=64x64:rate=30", "-c:v", "h264_nvenc", "-f", "null", "-"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def load_template_spec(self, template_id: str) -> TemplateSpec:
        """Đọc và parse file JSON cấu hình mẫu."""
        spec_path = self.templates_dir / f"{template_id}.json"
        if not spec_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy mẫu template: {template_id}")
        with open(spec_path, "r", encoding="utf-8") as f:
            return TemplateSpec(**json.load(f))

    def list_available_templates(self) -> List[TemplateSpec]:
        """Lấy danh sách toàn bộ các mẫu có sẵn trong thư mục templates."""
        templates: List[TemplateSpec] = []
        if self.templates_dir.is_dir():
            for p in sorted(self.templates_dir.glob("*.json")):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        templates.append(TemplateSpec(**json.load(f)))
                except Exception as ex:
                    logger.warning(f"Lỗi đọc file template {p.name}: {ex}")
        return templates

    def _is_image(self, file_path: str) -> bool:
        """Kiểm tra file có phải ảnh tĩnh hay video dựa trên đuôi mở rộng và ffprobe."""
        ext = Path(file_path).suffix.lower()
        if ext in (".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv"):
            return False
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic"):
            return True
        return not self._validate_media(file_path, is_video=True)

    def _resolve_input_arg(self, file_path: str) -> List[str]:
        """Tạo tham số đầu vào cho FFmpeg: Ảnh thì -loop 1, Video thì chỉ -i."""
        abs_p = str(Path(file_path).resolve())
        if self._is_image(abs_p):
            return ["-loop", "1", "-i", abs_p]
        return ["-i", abs_p]

    def _validate_media(self, file_path: str, is_video: bool = False) -> bool:
        """Kiểm tra tính hợp lệ của file đầu vào qua ffprobe."""
        path = Path(file_path).resolve()
        if not path.is_file() or path.stat().st_size < 100:
            return False
        try:
            cmd = ["ffprobe", "-v", "error", "-show_streams", "-print_format", "json", str(path)]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode != 0:
                return True
            streams = json.loads(res.stdout).get("streams", [])
            return any(s.get("codec_type") == "video" for s in streams) if is_video else len(streams) > 0
        except Exception:
            return True

    def render(
        self,
        template_id: str,
        video_path: Optional[str] = None,
        image_path: Optional[str] = None,
        media_inputs: Optional[Dict[int, str]] = None,
        audio_path: Optional[str] = None,
        custom_duration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Render video mẫu theo đặc tả template_id với cơ chế tự thích ứng Slot thông minh."""
        start_ts = time.time()
        inputs: Dict[int, str] = dict(media_inputs or {})

        # Tương thích ngược: map video_path & image_path sang media_inputs
        if video_path and 1 not in inputs:
            inputs[1] = video_path
        if image_path and 2 not in inputs:
            inputs[2] = image_path

        # Tự động chọn kịch bản render phù hợp dựa trên số slot truyền vào
        target_tpl = template_id
        if target_tpl not in ("t01_beat_drop", "t02_three_photos"):
            target_tpl = "t01_beat_drop" if len(inputs) <= 2 else "t02_three_photos"

        # Nếu chọn t02_three_photos nhưng chỉ có 2 ảnh/video: tự động dùng ảnh 2 cho slot 3
        if target_tpl == "t02_three_photos":
            if 3 not in inputs and 2 in inputs:
                inputs[3] = inputs[2]
            elif 3 not in inputs and 1 in inputs:
                inputs[3] = inputs[1]

        spec = self.load_template_spec(target_tpl)

        # Xác thực đầu vào dựa trên slots yêu cầu
        for slot in spec.slots:
            if slot.required:
                file_p = inputs.get(slot.slot_id)
                if not file_p:
                    raise ValueError(f"Thiếu file đầu vào bắt buộc cho {slot.title} (Slot {slot.slot_id})!")
                if not self._validate_media(file_p, is_video=False):
                    raise ValueError(f"File đầu vào cho {slot.title} không hợp lệ hoặc bị hỏng!")

        # Giải quyết đường dẫn Audio BGM
        resolved_audio = audio_path or inputs.get(next((s.slot_id for s in spec.slots if s.slot_type == "audio"), 99))
        if not resolved_audio or not Path(resolved_audio).is_file():
            default_bgm = self.assets_dir / (spec.default_bgm or "real_capcut_audio.m4a")
            resolved_audio = str(default_bgm.resolve()) if default_bgm.is_file() else inputs[1]

        beat_times = AudioBeatTracker.detect_onsets(resolved_audio)
        total_dur = custom_duration or spec.total_duration

        if target_tpl == "t02_three_photos":
            cmd = self._build_cmd_t02(spec, inputs, resolved_audio, total_dur)
        else:
            cmd = self._build_cmd_t01(spec, inputs, resolved_audio, total_dur)

        out_path = Path(cmd[-1])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if res.returncode != 0:
                logger.error(f"FFmpeg render thất bại: {res.stderr[-600:]}")
                raise RuntimeError(f"FFmpeg render lỗi: {res.stderr[-300:]}")

            elapsed = round(time.time() - start_ts, 2)
            file_size_mb = round(out_path.stat().st_size / (1024 * 1024), 2)
            fps_avg = round((total_dur * spec.resolution.fps) / max(0.1, elapsed), 1)

            return {
                "success": True,
                "template_id": template_id,
                "output_filename": out_path.name,
                "output_path": str(out_path),
                "duration": total_dur,
                "file_size_mb": file_size_mb,
                "elapsed_seconds": elapsed,
                "fps_rendered": fps_avg,
                "encoder_used": "h264_nvenc" if self._has_nvenc else "libx264",
                "beat_count": len(beat_times),
            }
        except subprocess.TimeoutExpired:
            raise TimeoutError("Render video vượt quá thời gian tối đa cho phép (Timeout 120s)!")

    def _build_cmd_t01(self, spec: TemplateSpec, inputs: Dict[int, str], audio: str, dur: float) -> List[str]:
        """Tạo lệnh FFmpeg cho Mẫu 01 (1 Video/Ảnh + 1 Ảnh) tự thích ứng kiểu media."""
        w, h = spec.resolution.width, spec.resolution.height
        v1_filter = ShaderFilterBuilder.build_video_slot_filter(0, "v1", 8.80, w, h)
        p2_filter = ShaderFilterBuilder.build_photo_pan_strobe_filter(1, "v2", max(1.0, dur - 8.25), 11.62, 128, w, h)
        pipe = ShaderFilterBuilder.build_slidedown_pipeline("v1", "v2", 3, "v_out", 0.55, 8.25)
        out_file = self.output_dir / f"tpl_01_{int(time.time())}.mp4"
        enc = "h264_nvenc" if self._has_nvenc else "libx264"
        preset = "p4" if self._has_nvenc else "veryfast"

        in1_args = self._resolve_input_arg(inputs[1])
        in2_args = self._resolve_input_arg(inputs[2])
        audio_abs = str(Path(audio).resolve())
        mask_abs = str(Path(self.mask_path).resolve())

        return [
            "ffmpeg", "-y",
            *in1_args,
            *in2_args,
            "-i", audio_abs,
            "-loop", "1", "-i", mask_abs,
            "-filter_complex", f"{v1_filter};{p2_filter};{pipe}",
            "-map", "[v_out]", "-map", "2:a?", "-t", str(dur),
            "-c:v", enc, "-preset", preset, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(out_file.resolve())
        ]

    def _build_cmd_t02(self, spec: TemplateSpec, inputs: Dict[int, str], audio: str, dur: float) -> List[str]:
        """Tạo lệnh FFmpeg cho Mẫu 02 (3 Ảnh Tĩnh) khớp 100% từng mili-giây."""
        w, h = spec.resolution.width, spec.resolution.height
        filtergraph = ShaderFilterBuilder.build_template_02_filtergraph(
            p1_idx=0, p2_idx=1, p3_idx=2, mask_idx=4, target_w=w, target_h=h
        )
        out_file = self.output_dir / f"tpl_02_{int(time.time())}.mp4"
        enc = "h264_nvenc" if self._has_nvenc else "libx264"
        preset = "p4" if self._has_nvenc else "veryfast"

        in1_args = self._resolve_input_arg(inputs[1])
        in2_args = self._resolve_input_arg(inputs[2])
        in3_args = self._resolve_input_arg(inputs[3])
        audio_abs = str(Path(audio).resolve())
        mask_abs = str(Path(self.mask_path).resolve())

        return [
            "ffmpeg", "-y",
            *in1_args,
            *in2_args,
            *in3_args,
            "-i", audio_abs,
            "-loop", "1", "-i", mask_abs,
            "-filter_complex", filtergraph,
            "-map", "[v_out]", "-map", "3:a?", "-t", str(dur),
            "-c:v", enc, "-preset", preset, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(out_file.resolve())
        ]
