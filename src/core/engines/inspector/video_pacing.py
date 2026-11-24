import cv2
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("video_pacing")


class VideoPacingAnalyzer:
    """Engine phân tích nhịp độ cắt cảnh và tỷ lệ giữ chân người xem của video."""

    @classmethod
    def analyze_video_pacing(
        cls,
        video_path: str,
        sample_fps: int = 3,
        threshold: float = 0.62,
    ) -> Dict[str, Any]:
        """Phân tích các mốc cắt cảnh bằng OpenCV Color Histogram Correlation."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Không thể mở file video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = round(float(total_frames) / float(fps), 2) if fps > 0 else 0.0

        if duration <= 0:
            cap.release()
            return cls._empty_result()

        step = max(1, int(fps // sample_fps))
        prev_hist = None
        scene_cut_timestamps: List[float] = []
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % step == 0:
                current_time = round(float(frame_idx) / float(fps), 2)
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                # Tính histogram H-S 2D chuẩn hóa
                hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
                cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

                if prev_hist is not None:
                    # So sánh độ tương đồng histogram (1.0 là giống hệt, < 0.62 là đổi cảnh)
                    corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
                    if corr < threshold:
                        # Đảm bảo 2 cảnh cắt cách nhau ít nhất 0.6 giây
                        if not scene_cut_timestamps or (current_time - scene_cut_timestamps[-1] >= 0.6):
                            scene_cut_timestamps.append(current_time)

                prev_hist = hist

            frame_idx += 1

        cap.release()

        # Tính toán các chỉ số nhịp độ
        total_cuts = len(scene_cut_timestamps)
        total_scenes = total_cuts + 1
        avg_scene_duration = round(duration / total_scenes, 2)
        cuts_per_minute = round((total_cuts / duration) * 60.0, 1) if duration > 0 else 0.0

        # Đánh giá Hook trong 3.5 giây đầu
        hook_cuts = [t for t in scene_cut_timestamps if t <= 3.5]
        has_hook = len(hook_cuts) > 0

        # Tính Điểm Nhịp Độ (Pacing Score: 0 - 100)
        pacing_score = cls._calculate_pacing_score(avg_scene_duration, has_hook, duration)
        pacing_rating = cls._get_pacing_level(avg_scene_duration)
        advice = cls._generate_pacing_advice(avg_scene_duration, has_hook, total_cuts, duration)

        return {
            "duration_seconds": duration,
            "total_scene_cuts": total_cuts,
            "total_scenes": total_scenes,
            "avg_scene_duration_sec": avg_scene_duration,
            "cuts_per_minute": cuts_per_minute,
            "scene_cut_timestamps": scene_cut_timestamps[:50],  # Lưu tối đa 50 mốc tiêu biểu
            "has_early_hook": has_hook,
            "pacing_score": pacing_score,
            "pacing_level": pacing_rating,
            "actionable_advice": advice,
        }

    @classmethod
    def _calculate_pacing_score(cls, avg_scene_sec: float, has_hook: bool, duration: float) -> int:
        """Tính điểm giữ chân dựa trên tốc độ chuyển cảnh chuẩn TikTok/Reels."""
        if duration < 5:
            return 80

        # Chuẩn vàng video ngắn: 1.8s - 3.2s / cảnh
        if 1.5 <= avg_scene_sec <= 3.2:
            base = 92
        elif 3.2 < avg_scene_sec <= 4.8:
            base = 80
        elif 1.0 <= avg_scene_sec < 1.5:
            base = 85  # Cắt cảnh hơi dồn dập
        elif 4.8 < avg_scene_sec <= 6.5:
            base = 65  # Hơi chậm
        else:
            base = 50  # Quá chậm

        # Thưởng điểm nếu có chuyển cảnh giật hook trong 3 giây đầu
        if has_hook:
            base = min(100, base + 8)
        else:
            base = max(35, base - 6)

        return int(base)

    @classmethod
    def _get_pacing_level(cls, avg_scene_sec: float) -> str:
        if avg_scene_sec <= 3.2:
            return "Nhanh & Giữ Chân Tốt (Viral Pace) 🔥"
        elif avg_scene_sec <= 5.0:
            return "Vừa Phải (Ổn định cho review/kể chuyện) 👍"
        return "Chậm (Dễ làm người xem lướt qua) ⚠️"

    @classmethod
    def _generate_pacing_advice(
        cls, avg_scene_sec: float, has_hook: bool, total_cuts: int, duration: float
    ) -> List[str]:
        """Tạo gợi ý dựng video cụ thể cho creator."""
        advice = []
        if not has_hook and duration > 5:
            advice.append("Thiếu Hook 3s đầu: Hãy thêm 1 cảnh cắt bất ngờ hoặc zoom khung hình trong 3 giây đầu tiên.")

        if avg_scene_sec > 5.0:
            advice.append(f"Nhịp độ trung bình {avg_scene_sec}s/cảnh là quá chậm. Hãy chèn thêm b-roll, text động hoặc đổi góc máy mỗi 2-3s.")
        elif avg_scene_sec < 1.4:
            advice.append("Nhịp cắt cảnh quá dồn dập (<1.4s/cảnh). Chú ý tránh làm người xem bị mỏi mắt nếu là video dài.")
        else:
            advice.append("Nhịp độ cắt cảnh rất tốt, đạt tiêu chuẩn giữ chân cao của các video xu hướng TikTok.")

        if duration > 90 and total_cuts < 20:
            advice.append("Video dài hơn 1 phút 30 giây cần tăng tần suất hiệu ứng chuyển cảnh để giữ tỷ lệ xem trọn vẹn (Watch Time).")

        return advice

    @classmethod
    def _empty_result(cls) -> Dict[str, Any]:
        return {
            "duration_seconds": 0.0,
            "total_scene_cuts": 0,
            "total_scenes": 0,
            "avg_scene_duration_sec": 0.0,
            "cuts_per_minute": 0.0,
            "scene_cut_timestamps": [],
            "has_early_hook": False,
            "pacing_score": 50,
            "pacing_level": "Không xác định",
            "actionable_advice": ["Không thể đọc thời lượng video."],
        }

