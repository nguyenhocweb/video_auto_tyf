import unittest
from unittest.mock import MagicMock, patch

from src.modules.creator.inspector.service import InspectorService
from src.modules.creator.inspector.repository import InspectorMongoRepository


def sync_run(coro):
    """Thực thi coroutine thuần túy không cần socket event loop trong môi trường sandbox."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value


class TestInspectorService(unittest.TestCase):
    """Kiểm thử tầng nghiệp vụ InspectorService."""

    def setUp(self):
        self.mock_repo = MagicMock(spec=InspectorMongoRepository)
        self.mock_repo.db = MagicMock()
        self.saved_calls = []

        async def fake_save(user_id, inspect_type, score, details, summary):
            self.saved_calls.append({
                "user_id": user_id,
                "type": inspect_type,
                "score": score,
                "details": details,
                "summary": summary,
            })
            return {"id": "mock_123"}

        self.mock_repo.save_record = fake_save
        self.service = InspectorService(repo=self.mock_repo)

    def test_inspect_text(self):
        """Kiểm tra thẩm định kịch bản phụ đề."""
        res = sync_run(self.service.inspect_text("user_1", "Đây là một video cực kỳ thú vị và bổ ích."))
        self.assertTrue(res.is_safe)
        self.assertEqual(res.safety_score, 100)
        self.assertEqual(len(self.saved_calls), 1)
        self.assertEqual(self.saved_calls[0]["score"], 100)

    @patch("src.modules.creator.inspector.service.ImageAnalyzer.analyze_image")
    @patch("src.modules.creator.inspector.service.PolicyChecker.check_image_skin_tone")
    def test_inspect_image_bytes(self, mock_skin, mock_analyze):
        """Kiểm tra thẩm định ảnh dạng bytes với mock analyze."""
        mock_analyze.return_value = {
            "overall_viral_score": 88,
            "rating": "Rất Dễ Lên Xu Hướng 🔥",
            "face_analysis": {"face_count": 1, "face_ratio_percent": 25.0, "face_boxes": [], "score": 95},
            "visual_analysis": {
                "brightness": 120.0,
                "saturation": 140.0,
                "contrast_std": 60.0,
                "sharpness": 150.0,
                "contrast_score": 90,
                "color_pop_score": 92,
                "is_sharp": True,
            },
            "text_analysis": {
                "has_text": True,
                "detected_texts": ["HOT NEWS"],
                "text_count": 1,
                "text_ratio_percent": 15.0,
                "score": 95,
            },
            "actionable_advice": ["Bố cục ảnh rất tốt!"],
        }
        mock_skin.return_value = {"is_safe": True, "skin_ratio": 0.15, "skin_percent": 15.0, "warning": ""}

        res = sync_run(self.service.inspect_image_bytes("user_1", b"fake_jpg_data", "test.jpg"))
        self.assertEqual(res.overall_viral_score, 88)
        self.assertEqual(res.rating, "Rất Dễ Lên Xu Hướng 🔥")
        self.assertEqual(len(self.saved_calls), 1)


if __name__ == "__main__":
    unittest.main()
