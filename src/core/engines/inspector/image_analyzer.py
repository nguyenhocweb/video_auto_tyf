import cv2
import numpy as np
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from src.core.config import settings

logger = logging.getLogger("image_analyzer")


class ImageAnalyzer:
    """Engine phân tích ảnh bìa/ảnh chụp màn hình và dự đoán tiềm năng Viral CTR."""

    _face_cascade = None
    _ocr_reader = None

    @classmethod
    def _get_face_cascade(cls):
        """Khởi tạo Haar Cascade phát hiện khuôn mặt nếu có hỗ trợ."""
        if cls._face_cascade is None:
            if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data") and hasattr(cv2.data, "haarcascades"):
                try:
                    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                    cls._face_cascade = cv2.CascadeClassifier(cascade_path)
                except Exception:
                    cls._face_cascade = False
            else:
                cls._face_cascade = False
        return cls._face_cascade if cls._face_cascade is not False else None

    @classmethod
    def _get_ocr_reader(cls):
        """Khởi tạo EasyOCR reader (Lazy Loading) an toàn, tránh treo khi offline."""
        if cls._ocr_reader is None:
            try:
                import easyocr
                ocr_dir = getattr(settings, "STORAGE_DIR", Path("storage")) / "easyocr"
                ocr_dir.mkdir(parents=True, exist_ok=True)
                model_file = ocr_dir / "craft_mlt_25k.pth"
                # Chỉ kích hoạt download nếu model đã có hoặc được phép
                can_load = model_file.exists()
                if can_load:
                    cls._ocr_reader = easyocr.Reader(
                        ["vi", "en"],
                        gpu=False,
                        model_storage_directory=str(ocr_dir),
                        user_network_directory=str(ocr_dir),
                        download_enabled=False,
                        verbose=False,
                    )
                else:
                    # Model chưa tải về máy, tắt reader để dùng OpenCV heuristic siêu tốc
                    cls._ocr_reader = False
            except Exception as e:
                logger.debug(f"EasyOCR không khả dụng: {e}")
                cls._ocr_reader = False
        return cls._ocr_reader if cls._ocr_reader is not False else None

    @classmethod
    def analyze_image(cls, image_path: str) -> Dict[str, Any]:
        """Phân tích toàn diện ảnh bìa / ảnh chụp màn hình để chấm điểm Viral."""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Không thể mở file ảnh từ đường dẫn: {image_path}")

        height, width = img.shape[:2]
        total_pixels = height * width

        # 1. Phân tích khuôn mặt & cảm xúc
        face_info = cls._analyze_faces(img, total_pixels)

        # 2. Phân tích màu sắc, độ tương phản và độ nét
        visual_info = cls._analyze_visual_metrics(img)

        # 3. Phân tích chữ trên ảnh (Text Overlay)
        text_info = cls._analyze_text_overlay(image_path, total_pixels)

        # 4. Tính toán điểm số thành phần (0 - 100)
        face_score = face_info["score"]
        contrast_score = visual_info["contrast_score"]
        color_pop_score = visual_info["color_pop_score"]
        text_score = text_info["score"]

        # 5. Tổng hợp Điểm Tiềm Năng Viral (0 - 100)
        overall_viral_score = int(round(
            face_score * 0.30 +
            contrast_score * 0.25 +
            color_pop_score * 0.25 +
            text_score * 0.20
        ))
        overall_viral_score = max(10, min(99, overall_viral_score))

        # 6. Tạo lời khuyên hành động cụ thể (Actionable Advice)
        advice_list = cls._generate_advice(face_info, visual_info, text_info, overall_viral_score)

        return {
            "overall_viral_score": overall_viral_score,
            "rating": cls._get_rating_label(overall_viral_score),
            "face_analysis": face_info,
            "visual_analysis": visual_info,
            "text_analysis": text_info,
            "actionable_advice": advice_list,
        }

    @classmethod
    def _analyze_faces(cls, img: np.ndarray, total_pixels: int) -> Dict[str, Any]:
        """Phát hiện khuôn mặt và tính toán tỷ lệ chiếm dụng khung hình."""
        cascade = cls._get_face_cascade()
        face_boxes: List[Dict[str, int]] = []
        biggest_ratio = 0.0

        if cascade:
            try:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                for (x, y, w, h) in faces:
                    area = w * h
                    ratio = float(area) / float(total_pixels)
                    if ratio > biggest_ratio:
                        biggest_ratio = ratio
                    face_boxes.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
            except Exception as e:
                logger.debug(f"Cascade error: {e}")
        else:
            # Heuristic contour detection for prominent face-like oval skin regions
            try:
                hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                lower_skin = np.array([0, 25, 60], dtype=np.uint8)
                upper_skin = np.array([25, 255, 255], dtype=np.uint8)
                mask = cv2.inRange(hsv, lower_skin, upper_skin)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for c in contours:
                    area = cv2.contourArea(c)
                    if area > total_pixels * 0.03:
                        x, y, w, h = cv2.boundingRect(c)
                        ratio = float(area) / float(total_pixels)
                        aspect = float(h) / max(1, w)
                        if 0.8 <= aspect <= 2.2:
                            if ratio > biggest_ratio:
                                biggest_ratio = ratio
                            face_boxes.append({"x": int(x), "y": int(y), "w": int(w), "h": int(h)})
            except Exception as e:
                logger.debug(f"Skin-face heuristic error: {e}")

        face_count = len(face_boxes)
        if face_count == 0:
            score = 60  # Thumbnail dạng phong cảnh/sản phẩm
        elif 0.12 <= biggest_ratio <= 0.45:
            score = 95  # Khuôn mặt to, rõ, hút mắt
        elif biggest_ratio < 0.12:
            score = 75  # Khuôn mặt hơi nhỏ
        else:
            score = 70  # Khuôn mặt quá to che hết bối cảnh

        return {
            "face_count": face_count,
            "face_ratio_percent": round(biggest_ratio * 100, 1),
            "face_boxes": face_boxes[:4],
            "score": score,
        }

    @classmethod
    def _analyze_visual_metrics(cls, img: np.ndarray) -> Dict[str, Any]:
        """Đo lường độ sáng, độ tương phản và độ rực rỡ màu sắc."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Độ bão hòa màu trung bình (0 - 255)
        mean_sat = float(np.mean(s))
        # Độ sáng trung bình (0 - 255)
        mean_val = float(np.mean(v))
        # Độ tương phản (độ lệch chuẩn độ sáng)
        contrast_std = float(np.std(gray))
        # Độ sắc nét (phương sai toán tử Laplacian)
        sharpness_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # Điểm tương phản (chuẩn 40 - 75 là đẹp)
        if contrast_std >= 55:
            contrast_score = 90
        elif contrast_std >= 40:
            contrast_score = 75
        else:
            contrast_score = 50

        # Điểm rực rỡ (màu sắc bắt mắt thu hút click)
        if mean_sat >= 100:
            color_pop_score = 92
        elif mean_sat >= 60:
            color_pop_score = 78
        else:
            color_pop_score = 55

        return {
            "brightness": round(mean_val, 1),
            "saturation": round(mean_sat, 1),
            "contrast_std": round(contrast_std, 1),
            "sharpness": round(sharpness_var, 1),
            "contrast_score": contrast_score,
            "color_pop_score": color_pop_score,
            "is_sharp": sharpness_var > 100.0,
        }

    @classmethod
    def _analyze_text_overlay(cls, image_path: str, total_pixels: int) -> Dict[str, Any]:
        """Phát hiện chữ trên ảnh bìa bằng EasyOCR."""
        reader = cls._get_ocr_reader()
        if not reader:
            return {"has_text": False, "detected_texts": [], "text_ratio_percent": 0.0, "score": 70}

        try:
            results = reader.readtext(image_path)
            detected_texts = []
            total_text_area = 0

            for (bbox, text, conf) in results:
                if conf > 0.35 and len(text.strip()) > 1:
                    detected_texts.append(text.strip())
                    # Tính diện tích hộp chứa chữ
                    pts = np.array(bbox, dtype=np.int32)
                    w = int(np.linalg.norm(pts[0] - pts[1]))
                    h = int(np.linalg.norm(pts[1] - pts[2]))
                    total_text_area += (w * h)

            text_ratio = float(total_text_area) / float(total_pixels)
            has_text = len(detected_texts) > 0

            # Chuẩn chữ trên thumbnail: 5% - 25% diện tích ảnh
            if not has_text:
                score = 65  # Thiếu chữ giật tít trên thumbnail
            elif 0.04 <= text_ratio <= 0.28:
                score = 95  # Chữ to, vừa vặn, giật tít tốt
            elif text_ratio < 0.04:
                score = 75  # Chữ hơi nhỏ trên màn hình di động
            else:
                score = 60  # Quá nhiều chữ gây rối mắt

            return {
                "has_text": has_text,
                "detected_texts": detected_texts[:5],
                "text_count": len(detected_texts),
                "text_ratio_percent": round(text_ratio * 100, 1),
                "score": score,
            }
        except Exception as e:
            logger.warning(f"Lỗi khi chạy OCR: {e}")
            return {"has_text": False, "detected_texts": [], "text_ratio_percent": 0.0, "score": 70}

    @classmethod
    def _generate_advice(
        cls, face_info: dict, visual_info: dict, text_info: dict, score: int
    ) -> List[str]:
        """Tạo các gợi ý cải thiện cụ thể cho Creator."""
        advice = []
        if face_info["face_count"] == 0:
            advice.append("Gợi ý: Thêm khuôn mặt cận cảnh với biểu cảm giật mình/hào hứng để tăng CTR thêm ~35%.")
        elif face_info["face_ratio_percent"] < 12.0:
            advice.append("Khuôn mặt hơi nhỏ trên màn hình điện thoại. Hãy phóng to mặt nhân vật chiếm 20-30% ảnh.")

        if visual_info["brightness"] < 90:
            advice.append("Ảnh hơi tối. Hãy tăng độ sáng (+15%) để thumbnail nổi bật hơn trên giao diện tối của TikTok/YouTube.")
        if visual_info["color_pop_score"] < 70:
            advice.append("Màu sắc hơi nhạt. Tăng độ bão hòa màu (Saturation) hoặc thêm viền màu neon để kích thích thị giác.")

        if not text_info["has_text"]:
            advice.append("Chưa có chữ giật tít trên ảnh. Nên thêm 3-5 từ khóa gây tò mò (VD: 'SỰ THẬT...', 'ĐỪNG XEM NẾU...').")
        elif text_info["text_ratio_percent"] > 28.0:
            advice.append("Quá nhiều chữ che mất hình ảnh. Rút gọn tiêu đề lại thành 3-5 từ trọng tâm, in đậm.")

        if not advice:
            advice.append("Bố cục ảnh rất tốt! Màu sắc rực rỡ, chữ rõ nét và khuôn mặt có sức hút cao.")

        return advice

    @classmethod
    def _get_rating_label(cls, score: int) -> str:
        if score >= 85:
            return "Rất Dễ Lên Xu Hướng 🔥"
        elif score >= 70:
            return "Tiềm Năng Khá Tốt 👍"
        elif score >= 50:
            return "Mức Độ Trung Bình ⚠️"
        return "Cần Tối Ưu Lại ❌"
