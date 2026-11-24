import os
import cv2
import logging
import numpy as np
from typing import Optional, Tuple, Dict, Any, Union

logger = logging.getLogger("watermark_remover")


class WatermarkRemover:
    """
    Engine chuyên dụng tẩy sạch Watermark & Logo AI trên ảnh.
    Hỗ trợ tự động nhận diện logo lấp lánh (Sparkle Astroid) của Google Gemini / Imagen 3
    và xóa watermark tùy chỉnh theo bounding box với thuật toán phục hồi Navier-Stokes.
    """

    @staticmethod
    def generate_astroid_mask(size: int = 42, p: float = 0.65) -> np.ndarray:
        """Tạo mask hình học astroid 4 cánh chuẩn logo Gemini."""
        half = size / 2.0
        y, x = np.ogrid[:size, :size]
        norm_x = (x - half + 0.5) / (half * 0.95)
        norm_y = (y - half + 0.5) / (half * 0.95)
        mask = (np.abs(norm_x) ** p + np.abs(norm_y) ** p <= 1.0).astype(np.float32)
        return mask

    @classmethod
    def detect_gemini_sparkle(
        cls, img: np.ndarray
    ) -> Tuple[Optional[Tuple[int, int, int, int]], float]:
        """
        Quét vùng góc dưới phải tìm tọa độ logo 4 cánh của Gemini / Imagen 3.
        Trả về ((x, y, w, h), match_score).
        """
        h, w = img.shape[:2]
        sw = max(180, int(w * 0.22))
        sh = max(160, int(h * 0.28))
        x0 = max(0, w - sw)
        y0 = max(0, h - sh)

        roi = img[y0:h, x0:w]
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        morph_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
        tophat = cv2.morphologyEx(gray_roi, cv2.MORPH_TOPHAT, morph_k).astype(np.float32)

        base_size = int(round(min(w, h) * 0.045))
        scales = [36, 40, 42, 46, 50, 54]
        if base_size > 50:
            scales.extend([base_size, int(base_size * 1.15)])
        scales = sorted(list(set(scales)))

        best_score = -1.0
        best_box = None

        for sz in scales:
            if sz >= tophat.shape[0] or sz >= tophat.shape[1]:
                continue
            astroid = cls.generate_astroid_mask(size=sz, p=0.65)
            match_map = cv2.matchTemplate(tophat, astroid, cv2.TM_CCOEFF_NORMED)

            locs = np.where(match_map >= 0.35)
            for pt_y, pt_x in zip(*locs):
                gx = x0 + pt_x
                gy = y0 + pt_y
                dist_right = w - (gx + sz)
                dist_bottom = h - (gy + sz)
                # Logo Gemini luon o cach le phai va le duoi tu 25px den 135px
                if 25 <= dist_right <= 135 and 25 <= dist_bottom <= 135:
                    score = float(match_map[pt_y, pt_x])
                    if score > best_score:
                        best_score = score
                        best_box = (int(gx), int(gy), sz, sz)

        if best_score >= 0.35 and best_box:
            logger.info("Phat hien logo Gemini: %s voi diem tin cay %.3f", best_box, best_score)
            return best_box, best_score

        return None, best_score

    @classmethod
    def clean_gemini_watermark(
        cls,
        image_input: Union[str, bytes, np.ndarray],
        output_path: Optional[str] = None,
    ) -> Tuple[np.ndarray, bool]:
        """
        Tự động khử watermark logo lấp lánh của Gemini ở góc dưới phải.
        Trả về (cleaned_image, is_detected).
        """
        img = cls._load_image(image_input)
        h, w = img.shape[:2]

        box, score = cls.detect_gemini_sparkle(img)
        mask = np.zeros((h, w), dtype=np.uint8)
        detected = False

        if box and score >= 0.35:
            bx, by, bw, bh = box
            astroid = cls.generate_astroid_mask(size=bw, p=0.65)
            dil_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            dil_astroid = cv2.dilate(
                (astroid * 255).astype(np.uint8), dil_k, iterations=2
            )
            mask[by : by + bh, bx : bx + bw] = dil_astroid
            detected = True
        else:
            # Fallback hop goc duoi phai chuan Gemini
            bx1 = max(0, w - int(w * 0.13))
            by1 = max(0, h - int(h * 0.22))
            bx2 = max(0, w - int(w * 0.04))
            by2 = max(0, h - int(h * 0.06))
            cv2.rectangle(mask, (bx1, by1), (bx2, by2), 255, -1)

        cleaned = cv2.inpaint(img, mask, inpaintRadius=4, flags=cv2.INPAINT_NS)

        if output_path:
            cls._save_image(cleaned, output_path)

        return cleaned, detected

    @classmethod
    def clean_custom_box(
        cls,
        image_input: Union[str, bytes, np.ndarray],
        box: Dict[str, Union[int, float]],
        output_path: Optional[str] = None,
    ) -> np.ndarray:
        """
        Xóa logo hoặc watermark theo tọa độ hộp chữ nhật tùy chỉnh.
        box: {'x': ..., 'y': ..., 'w': ..., 'h': ...} (pixels hoặc normalized 0.0 - 1.0)
        """
        img = cls._load_image(image_input)
        h, w = img.shape[:2]

        bx = box.get("x", 0)
        by = box.get("y", 0)
        bw = box.get("w", box.get("width", 50))
        bh = box.get("h", box.get("height", 50))

        if isinstance(bx, float) and bx <= 1.0:
            bx = int(bx * w)
        if isinstance(by, float) and by <= 1.0:
            by = int(by * h)
        if isinstance(bw, float) and bw <= 1.0:
            bw = int(bw * w)
        if isinstance(bh, float) and bh <= 1.0:
            bh = int(bh * h)

        bx, by = max(0, int(bx)), max(0, int(by))
        bw, bh = min(w - bx, int(bw)), min(h - by, int(bh))

        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.rectangle(mask, (bx, by), (bx + bw, by + bh), 255, -1)

        cleaned = cv2.inpaint(img, mask, inpaintRadius=4, flags=cv2.INPAINT_NS)

        if output_path:
            cls._save_image(cleaned, output_path)

        return cleaned

    @classmethod
    def clean_image_bytes(
        cls,
        file_bytes: bytes,
        watermark_type: str = "gemini",
        custom_box: Optional[Dict[str, Any]] = None,
        ext: str = ".jpg",
    ) -> Tuple[bytes, bool]:
        """Tẩy sạch ảnh từ mảng bytes và trả về bytes ảnh kết quả."""
        if watermark_type == "custom" and custom_box:
            cleaned = cls.clean_custom_box(file_bytes, custom_box)
            detected = True
        else:
            cleaned, detected = cls.clean_gemini_watermark(file_bytes)

        quality = 95
        encode_ext = ext if ext.startswith(".") else f".{ext}"
        if encode_ext.lower() in [".jpg", ".jpeg"]:
            params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        elif encode_ext.lower() == ".png":
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), 3]
        else:
            params = []

        _, buf = cv2.imencode(encode_ext, cleaned, params)
        return buf.tobytes(), detected

    @staticmethod
    def _load_image(image_input: Union[str, bytes, np.ndarray]) -> np.ndarray:
        """Đọc ảnh an toàn tương thích mọi hệ điều hành."""
        if isinstance(image_input, np.ndarray):
            return image_input.copy()
        if isinstance(image_input, bytes):
            img = cv2.imdecode(np.frombuffer(image_input, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Khong the giai ma du lieu byte anh.")
            return img
        if isinstance(image_input, str):
            if not os.path.exists(image_input):
                raise FileNotFoundError(f"Khong tim thay tep anh: {image_input}")
            with open(image_input, "rb") as f:
                data = f.read()
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError(f"Khong the giai ma anh tu file: {image_input}")
            return img
        raise TypeError("Dinh dang input anh khong duoc ho tro.")

    @staticmethod
    def _save_image(img: np.ndarray, output_path: str):
        """Lưu ảnh an toàn hỗ trợ ký tự Unicode trên Windows."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        ext = os.path.splitext(output_path)[1].lower() or ".jpg"
        if ext in [".jpg", ".jpeg"]:
            params = [int(cv2.IMWRITE_JPEG_QUALITY), 95]
        else:
            params = []
        res, enc = cv2.imencode(ext, img, params)
        if res:
            with open(output_path, "wb") as f:
                f.write(enc.tobytes())
