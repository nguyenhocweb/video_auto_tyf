import os
import asyncio
from src.core.engines.video.storyboard_generator import StoryboardScriptGenerator
from src.core.engines.video.storyboard_renderer import StoryboardRenderer

def test_storyboard_script_generator():
    topic = "Áp lực phải thành công trước tuổi 30"
    # Test kết hợp ĐỘC LẬP: Art Style = Stickman Người Que + Genre = Kể Chuyện Chia Sẻ Kiến Thức
    art_info = StoryboardScriptGenerator.get_art_style("stickman")
    genre_info = StoryboardScriptGenerator.get_genre("knowledge_sharing")
    scenes = StoryboardScriptGenerator._generate_fallback_script(
        topic=topic,
        art_info=art_info,
        genre_info=genre_info,
        scene_count=50
    )
    assert len(scenes) == 50, f"Số lượng cảnh phải là 50, nhận được: {len(scenes)}"
    for s in scenes:
        assert "narration" in s
        assert "prompt_en" in s
        # Bắt buộc ảnh vẫn vẽ theo phong cách Người Que mũ snapback đen như mẫu gốc!
        assert "stick figure" in s["prompt_en"]
        assert "snapback cap" in s["prompt_en"]
        word_count = len(s["narration"].split())
        assert word_count <= 20, f"Lời thoại quá dài ({word_count} từ): {s['narration']}"
    print(f"SUCCESS: Đã test thành công 50 cảnh Stickman + Chia Sẻ Kiến Thức!")

async def test_storyboard_renderer_mock():
    out_dir = "storage/temp/test_storyboard_run"
    if not os.path.exists(out_dir):
        out_dir = "be/" + out_dir
    os.makedirs(out_dir, exist_ok=True)

    scenes = [
        {"scene_idx": 1, "narration": "Đêm hôm đó dưới căn hầm tối tăm."},
        {"scene_idx": 2, "narration": "Chúng tôi nhìn thấy một cánh cửa sắt đóng chặt."},
    ]

    res = await StoryboardRenderer.render_storyboard(
        scenes=scenes,
        voice_name="vi-VN-NamMinhNeural",
        output_dir=out_dir
    )

    assert "final_video_path" in res
    assert os.path.exists(res["final_video_path"])
    assert res["scenes_rendered"] == 2
    print(f"SUCCESS: StoryboardRenderer passed! Video: {res['final_video_path']}, Dur: {res['total_duration']}s")

if __name__ == "__main__":
    test_storyboard_script_generator()
    asyncio.run(test_storyboard_renderer_mock())

