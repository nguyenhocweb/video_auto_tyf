import os
import cv2
import zipfile
import subprocess
import numpy as np
from typing import List, Dict, Any, Optional

class SlotSlicerEngine:
    """Engine phan tich video bang AI/CV, do chuyen canh, loc anh net nhat va cat clip theo slot mau."""

    @staticmethod
    def get_video_info(video_path: str) -> Dict[str, Any]:
        """Lay thong tin co ban cua video (duration, fps, total_frames, width, height)."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Khong the mo video: {video_path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0.0
        cap.release()
        return {
            "duration": round(duration, 2),
            "fps": round(fps, 2),
            "total_frames": total_frames,
            "width": w,
            "height": h,
        }

    @classmethod
    def analyze_scenes(cls, video_path: str) -> List[Dict[str, Any]]:
        """Do chuyen canh (Scene Detection) va do do sac net (Laplacian Sharpness) tung frame."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Khong the mo video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        total_duration = total_frames / fps if fps > 0 else 0.0

        step = max(1, int(fps / 5))  # Quet 5 frames/giay de toi uu toc do
        prev_gray = None
        scenes = [{"start": 0.0, "end": total_duration, "sharpest_ts": 0.0, "max_sharpness": 0.0}]

        frame_idx = 0
        cur_scene = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % step == 0:
                small = cv2.resize(frame, (160, 90))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                timestamp = frame_idx / fps

                if prev_gray is not None:
                    diff = cv2.absdiff(gray, prev_gray)
                    score = float(np.mean(diff))
                    # Neu do lech lon hon nguong va cach scene cu it nhat 1s
                    if score > 28.0 and (timestamp - scenes[-1]["start"]) >= 1.0:
                        scenes[-1]["end"] = timestamp
                        scenes.append({
                            "start": timestamp,
                            "end": total_duration,
                            "sharpest_ts": timestamp,
                            "max_sharpness": sharpness,
                        })
                        cur_scene += 1

                if sharpness > scenes[cur_scene]["max_sharpness"]:
                    scenes[cur_scene]["max_sharpness"] = sharpness
                    scenes[cur_scene]["sharpest_ts"] = timestamp

                prev_gray = gray
            frame_idx += 1

        cap.release()
        scenes[-1]["end"] = total_duration

        # Format lai thong tin scene
        for s in scenes:
            s["start"] = round(s["start"], 2)
            s["end"] = round(s["end"], 2)
            s["duration"] = round(max(0.1, s["end"] - s["start"]), 2)
            s["sharpest_ts"] = round(s["sharpest_ts"], 2)

        return scenes

    @classmethod
    def extract_sharp_frame(cls, video_path: str, timestamp: float, output_path: str) -> bool:
        """Trich xuat frame goc chat luong cao nhat tai moc thoi gian chi dinh."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        target_frame = int(timestamp * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            cv2.imwrite(output_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            return True
        return False

    @classmethod
    def slice_clip_ffmpeg(
        cls, video_path: str, start_sec: float, duration_sec: float, output_path: str
    ) -> bool:
        """Cat video clip ngan bang FFmpeg voi thoi luong chuan xac."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{start_sec:.2f}",
            "-t", f"{duration_sec:.2f}",
            "-i", video_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return res.returncode == 0 and os.path.exists(output_path)

    @classmethod
    def slice_for_template(
        cls, video_path: str, slots: List[Dict[str, Any]], output_dir: str
    ) -> Dict[str, Any]:
        """Nhac truong giai phau 1 video thanh bo tai nguyen dap ung cac slot cua mau."""
        os.makedirs(output_dir, exist_ok=True)
        info = cls.get_video_info(video_path)
        scenes = cls.analyze_scenes(video_path)
        total_duration = info["duration"]

        assigned_assets = []
        num_slots = len(slots)
        num_scenes = len(scenes)

        for idx, slot in enumerate(slots):
            slot_id = slot.get("id", str(idx + 1))
            slot_type = slot.get("type", "image")  # "image" hoac "video"
            slot_duration = float(slot.get("duration", 2.0))

            # Phan phoi scene: neu it scene hon slots, phan bo theo ty le thoi gian deu
            if num_scenes >= num_slots:
                scene = scenes[idx % num_scenes]
            else:
                ratio = idx / max(1, num_slots - 1)
                scene_start = ratio * max(0.0, total_duration - 1.5)
                scene = {
                    "start": scene_start,
                    "end": min(total_duration, scene_start + 3.0),
                    "sharpest_ts": min(total_duration, scene_start + 0.5),
                    "duration": 3.0,
                }

            if slot_type == "image":
                file_name = f"slot_{idx+1:02d}_image.jpg"
                file_path = os.path.join(output_dir, file_name)
                target_ts = scene["sharpest_ts"]
                cls.extract_sharp_frame(video_path, target_ts, file_path)
                assigned_assets.append({
                    "slot_id": slot_id,
                    "index": idx + 1,
                    "type": "image",
                    "file_name": file_name,
                    "file_path": file_path,
                    "timestamp": target_ts,
                    "duration": None,
                })
            else:
                file_name = f"slot_{idx+1:02d}_video_{slot_duration:.1f}s.mp4"
                file_path = os.path.join(output_dir, file_name)
                # Tinh thoi diem bat dau de khong bi vuot qua cuoi video
                max_start = max(0.0, total_duration - slot_duration)
                clip_start = min(scene["start"], max_start)
                cls.slice_clip_ffmpeg(video_path, clip_start, slot_duration, file_path)
                assigned_assets.append({
                    "slot_id": slot_id,
                    "index": idx + 1,
                    "type": "video",
                    "file_name": file_name,
                    "file_path": file_path,
                    "timestamp": clip_start,
                    "duration": slot_duration,
                })

        # Dong goi toan bo thanh file ZIP de nguoi dung tai ve
        zip_name = "template_assets_pack.zip"
        zip_path = os.path.join(output_dir, zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for asset in assigned_assets:
                if os.path.exists(asset["file_path"]):
                    zipf.write(asset["file_path"], arcname=asset["file_name"])

        return {
            "video_info": info,
            "detected_scenes_count": len(scenes),
            "scenes": scenes,
            "total_slots": len(assigned_assets),
            "assets": assigned_assets,
            "zip_path": zip_path,
            "zip_name": zip_name,
        }

