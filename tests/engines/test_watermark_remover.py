import os
import unittest
import numpy as np
from src.core.engines.image.watermark_remover import WatermarkRemover

class TestWatermarkRemover(unittest.TestCase):
    def setUp(self):
        self.sample_img_path = r"C:/Users/win/.gemini/antigravity/brain/dff6ba05-ab2b-4f0d-be19-1db69e6178d7/.user_uploaded/media_1794580270246_4e008053.jpg"

    def test_generate_astroid_mask(self):
        mask = WatermarkRemover.generate_astroid_mask(size=42, p=0.65)
        self.assertEqual(mask.shape, (42, 42))
        self.assertTrue(np.max(mask) == 1.0)
        # Center should be filled (1.0)
        self.assertEqual(mask[21, 21], 1.0)
        # Top-left corner (0, 0) should be 0.0
        self.assertEqual(mask[0, 0], 0.0)

    def test_detect_and_clean_gemini_watermark(self):
        if not os.path.exists(self.sample_img_path):
            self.skipTest("Sample image not found on machine")

        cleaned, detected = WatermarkRemover.clean_gemini_watermark(self.sample_img_path)
        self.assertTrue(detected, "Gemini sparkle watermark should be automatically detected")
        self.assertEqual(cleaned.shape, (572, 1024, 3))

    def test_clean_custom_box(self):
        synthetic_img = np.zeros((200, 200, 3), dtype=np.uint8)
        # Draw a bright logo in corner
        synthetic_img[150:180, 150:180] = 255
        cleaned = WatermarkRemover.clean_custom_box(
            synthetic_img,
            box={"x": 150, "y": 150, "w": 30, "h": 30}
        )
        self.assertEqual(cleaned.shape, (200, 200, 3))
        # After inpaint, mean value in that box should be close to background (0)
        self.assertLess(np.mean(cleaned[150:180, 150:180]), 10.0)

if __name__ == "__main__":
    unittest.main()

