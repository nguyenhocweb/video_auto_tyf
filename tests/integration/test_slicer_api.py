import os
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.modules.creator.video.slicer_router import slicer_router

def test_slicer_api_endpoint():
    app = FastAPI()
    app.include_router(slicer_router, prefix="/api/v1/creator/video")
    client = TestClient(app)

    video_path = "storage/dubbing_output/template_render_141e3f92808f.mp4"
    if not os.path.exists(video_path):
        video_path = "be/" + video_path
    
    assert os.path.exists(video_path), f"Video test khong ton tai: {video_path}"

    payload = {
        "video_path": video_path,
        "slots": [
            {"id": "slot_1", "type": "image"},
            {"id": "slot_2", "type": "video", "duration": 1.5},
            {"id": "slot_3", "type": "image"}
        ]
    }

    response = client.post("/api/v1/creator/video/slice-to-template", json=payload)
    assert response.status_code == 200, f"Error: {response.text}"
    data = response.json()
    assert data["success"] is True
    assert data["total_slots"] == 3
    assert len(data["assets"]) == 3
    assert "zip_download_url" in data

    # Test lay asset ve
    first_asset = data["assets"][0]
    asset_url = first_asset["download_url"]
    get_res = client.get(asset_url)
    assert get_res.status_code == 200
    assert len(get_res.content) > 0
    print("API Integration test passed! Assets returned successfully.")

if __name__ == "__main__":
    test_slicer_api_endpoint()
