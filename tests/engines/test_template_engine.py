"""Unit test cho TemplateRenderEngine và AudioBeatTracker."""

import unittest
from pathlib import Path
from src.core.engines.template_renderer.audio_beat_tracker import AudioBeatTracker
from src.core.engines.template_renderer.engine import TemplateRenderEngine


class TestTemplateEngine(unittest.TestCase):
    def setUp(self):
        self.engine = TemplateRenderEngine()
        self.sample_audio = "be/src/core/engines/template_renderer/assets/sample_t01_audio.mp4"
        self.tpl02_audio = "be/src/core/engines/template_renderer/assets/real_tpl02_audio.m4a"

    def test_list_templates(self):
        templates = self.engine.list_available_templates()
        self.assertTrue(len(templates) >= 2)
        tpl_ids = [t.template_id for t in templates]
        self.assertIn("t01_beat_drop", tpl_ids)
        self.assertIn("t02_three_photos", tpl_ids)

    def test_load_template_spec_t01(self):
        spec = self.engine.load_template_spec("t01_beat_drop")
        self.assertEqual(spec.template_id, "t01_beat_drop")
        self.assertEqual(spec.resolution.width, 720)
        self.assertEqual(spec.resolution.height, 1280)
        self.assertEqual(len(spec.slots), 3)

    def test_load_template_spec_t02(self):
        spec = self.engine.load_template_spec("t02_three_photos")
        self.assertEqual(spec.template_id, "t02_three_photos")
        self.assertEqual(spec.resolution.width, 720)
        self.assertEqual(spec.resolution.height, 1280)
        self.assertEqual(len(spec.slots), 4)

    def test_beat_tracker_onsets(self):
        audio_file = self.tpl02_audio if Path(self.tpl02_audio).is_file() else self.sample_audio
        if Path(audio_file).is_file():
            beats = AudioBeatTracker.detect_onsets(audio_file)
            self.assertTrue(isinstance(beats, list))
            self.assertTrue(len(beats) > 0)


if __name__ == "__main__":
    unittest.main()
