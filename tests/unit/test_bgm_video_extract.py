import os
import io
from pathlib import Path
from fastapi import UploadFile
from src.modules.creator.bgm.service import BgmService

async def test_extract_audio_from_video():
    vid_path = Path("storage/dubbing_output/template_render_141e3f92808f.mp4")
    if not vid_path.exists():
        vid_path = Path("be") / vid_path
    
    assert vid_path.exists(), f"Video test khong ton tai: {vid_path}"

    with open(vid_path, "rb") as f:
        file_bytes = f.read()

    upload_file = UploadFile(
        file=io.BytesIO(file_bytes),
        filename="sample_video_clip.mp4",
        headers={"content-type": "video/mp4"}
    )

    service = BgmService()
    track = await service.upload_bgm(
        file=upload_file,
        user_id="test_user_video_extract",
        title="Nhạc Trích Xuất Từ Video",
        mood="chill",
        tags_str="video,extracted,test",
        sanitize_audio=True
    )

    print("SUCCESS: Trích xuất nhạc từ video thành công!")
    print(f"Track ID: {track['id']}")
    print(f"Title: {track['title']}")
    print(f"Duration: {track['duration']}s")
    print(f"Audio URL: {track['audio_url']}")
    print(f"Saved File Path: {track['file_path']}")

    # Dam bao file luu phai la file am thanh .mp3, khong phai .mp4
    assert track['file_path'].endswith(".mp3")
    assert os.path.exists(track['file_path'])
    assert os.path.getsize(track['file_path']) > 0

    # Don dep track test
    await service.delete_track(str(track['id']), "test_user_video_extract")
    print("Cleaned up test track.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_extract_audio_from_video())

