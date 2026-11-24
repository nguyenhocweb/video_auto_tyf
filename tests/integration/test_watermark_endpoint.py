import os
import unittest
from fastapi.testclient import TestClient
from src.main import app

class TestWatermarkEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.sample_img_path = r"C:/Users/win/.gemini/antigravity/brain/dff6ba05-ab2b-4f0d-be19-1db69e6178d7/.user_uploaded/media_1794580270246_4e008053.jpg"

    def test_upload_image_with_auto_clean(self):
        if not os.path.exists(self.sample_img_path):
            self.skipTest("Sample image not found on machine")

        with open(self.sample_img_path, "rb") as f:
            file_bytes = f.read()

        job_id = "test_clean_job_123"
        response = self.client.post(
            "/api/v1/creator/storyboard/upload-image",
            data={"job_id": job_id, "scene_idx": 1, "auto_clean": "true"},
            files={"file": ("scene_1.jpg", file_bytes, "image/jpeg")},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("cleaned"))
        self.assertIn("scene_1.jpg", data.get("url"))

    def test_clean_watermark_endpoint(self):
        job_id = "test_clean_job_123"
        response = self.client.post(
            "/api/v1/creator/storyboard/clean-watermark",
            json={"job_id": job_id, "scene_idx": 1, "watermark_type": "gemini"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("scene_idx"), 1)
        self.assertTrue(data.get("detected"))

if __name__ == "__main__":
    unittest.main()

