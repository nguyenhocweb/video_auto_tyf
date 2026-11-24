import os
import shutil
from src.core.engines.video.slot_slicer import SlotSlicerEngine

def test_slot_slicer_engine():
    video_path = "storage/dubbing_output/template_render_141e3f92808f.mp4"
    if not os.path.exists(video_path):
        video_path = "be/" + video_path
    
    assert os.path.exists(video_path), f"Video test khong ton tai: {video_path}"

    test_output_dir = "storage/temp/test_slicer_output"
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)

    # Dinh nghia mau gom 4 slots: 2 anh va 2 clip ngan
    slots = [
        {"id": "slot_1", "type": "image"},
        {"id": "slot_2", "type": "video", "duration": 2.0},
        {"id": "slot_3", "type": "image"},
        {"id": "slot_4", "type": "video", "duration": 1.5},
    ]

    result = SlotSlicerEngine.slice_for_template(
        video_path=video_path,
        slots=slots,
        output_dir=test_output_dir
    )

    print("Result summary:", result["video_info"])
    print("Detected scenes:", result["detected_scenes_count"])
    assert result["total_slots"] == 4
    assert len(result["assets"]) == 4
    assert os.path.exists(result["zip_path"])

    for asset in result["assets"]:
        assert os.path.exists(asset["file_path"]), f"File thieu: {asset['file_path']}"
        print(f" -> Slot {asset['index']} ({asset['type']}): {asset['file_name']} (ts={asset['timestamp']})")

    print("SUCCESS: SlotSlicerEngine hoat dong hoan hao!")

if __name__ == "__main__":
    test_slot_slicer_engine()

