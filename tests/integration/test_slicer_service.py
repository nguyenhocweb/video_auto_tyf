import asyncio
import os
from src.modules.creator.video.slicer_schemas import SliceVideoToTemplateRequest, SlotRequirement
from src.modules.creator.video.slicer_service import VideoSlicerService

async def run_test():
    video_path = "storage/dubbing_output/template_render_141e3f92808f.mp4"
    if not os.path.exists(video_path):
        video_path = "be/" + video_path
    
    assert os.path.exists(video_path)

    req = SliceVideoToTemplateRequest(
        video_path=video_path,
        slots=[
            SlotRequirement(id="slot_1", type="image"),
            SlotRequirement(id="slot_2", type="video", duration=1.5),
            SlotRequirement(id="slot_3", type="image")
        ]
    )

    res = await VideoSlicerService.process_slice(req)
    print("SUCCESS: Service processed slice successfully!")
    print(f"Total slots: {res.total_slots}, Scenes: {res.detected_scenes_count}")
    print(f"Zip URL: {res.zip_download_url}")
    for a in res.assets:
        print(f" -> Slot {a.slot_id} ({a.type}): {a.file_name} -> {a.download_url}")

if __name__ == "__main__":
    asyncio.run(run_test())

