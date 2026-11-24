"""Unit test cho CapCutTemplateParser."""

import unittest
from src.core.engines.template_renderer.template_parser import CapCutTemplateParser


class TestCapCutTemplateParser(unittest.TestCase):
    def test_extract_template_id(self):
        url = "https://www.capcut.com/template-detail/7709090549353090312"
        tpl_id = CapCutTemplateParser.extract_template_id(url)
        self.assertEqual(tpl_id, "7709090549353090312")

    def test_parse_three_photos_template(self):
        res = CapCutTemplateParser.parse_from_template_id_or_url("7709090549353090312")
        self.assertEqual(res.template_id, "7709090549353090312")
        self.assertEqual(res.total_slots, 3)
        self.assertEqual(res.image_slots_count, 3)
        self.assertEqual(res.video_slots_count, 0)
        self.assertEqual(res.slots[0].slot_type, "image")
        self.assertEqual(res.slots[0].duration, 18.60)
        self.assertEqual(res.slots[1].slot_type, "image")
        self.assertEqual(res.slots[1].duration, 4.27)

    def test_parse_from_draft_json(self):
        draft_mock = {
            "tracks": [
                {
                    "type": "video",
                    "segments": [
                        {"target_timerange": {"start": 0, "duration": 5000000}, "material_id": "m1"},
                        {"target_timerange": {"start": 5000000, "duration": 10000000}, "material_id": "m2"},
                    ],
                }
            ],
            "materials": {
                "videos": [
                    {"id": "m1", "type": "video", "path": "clip.mp4"},
                    {"id": "m2", "type": "photo", "path": "pic.jpg"},
                ]
            },
        }
        res = CapCutTemplateParser.parse_from_draft_json(draft_mock, "test_draft")
        self.assertEqual(res.total_slots, 2)
        self.assertEqual(res.slots[0].slot_type, "video")
        self.assertEqual(res.slots[0].duration, 5.0)
        self.assertEqual(res.slots[1].slot_type, "image")
        self.assertEqual(res.slots[1].duration, 10.0)


if __name__ == "__main__":
    unittest.main()
