import sys
from pathlib import Path
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Add be/ to sys.path
be_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(be_dir))

from src.modules.creator.bgm.service import BgmService


async def test_reup_bgm_selection():
    """Kiểm thử logic chọn nhạc BGM cho Mô hình 2 (Random trong danh sách & Ưu tiên thời lượng >= video)."""
    mock_repo = MagicMock()
    mock_repo.seed_presets_if_needed = AsyncMock()

    tracks_pool = [
        {"id": "id_short", "title": "Nhạc ngắn 15s", "duration": 15.0, "file_path": "/tmp/15.mp3"},
        {"id": "id_long1", "title": "Nhạc dài 45s", "duration": 45.0, "file_path": "/tmp/45.mp3"},
        {"id": "id_long2", "title": "Nhạc dài 60s", "duration": 60.0, "file_path": "/tmp/60.mp3"},
    ]

    mock_repo.get_tracks_by_ids = AsyncMock(return_value=tracks_pool)
    mock_repo.get_tracks = AsyncMock(return_value=tracks_pool)

    service = BgmService(repo=mock_repo)

    # Video dài 30s -> Phải chọn id_long1 hoặc id_long2
    selected = await service.get_random_bgm_for_auto(
        candidate_ids=["id_short", "id_long1", "id_long2"],
        min_duration=30.0,
    )

    assert selected is not None, "Bài được chọn không được là None"
    assert selected["id"] in ["id_long1", "id_long2"], f"Id chọn sai: {selected['id']}"
    assert selected["duration"] >= 30.0, f"Thời lượng bài ({selected['duration']}) phải >= 30.0s"
    print(f"PASS test 1: Đã chọn đúng bài '{selected['title']}' dài hơn video ({selected['duration']}s >= 30s)")

    # Test 2: Fallback khi không bài nào dài hơn
    tracks_short = [
        {"id": "id_short1", "title": "Nhạc ngắn 10s", "duration": 10.0, "file_path": "/tmp/10.mp3"},
        {"id": "id_short2", "title": "Nhạc ngắn 20s", "duration": 20.0, "file_path": "/tmp/20.mp3"},
    ]
    mock_repo.get_tracks_by_ids = AsyncMock(return_value=tracks_short)

    selected_fallback = await service.get_random_bgm_for_auto(
        candidate_ids=["id_short1", "id_short2"],
        min_duration=40.0,
    )

    assert selected_fallback is not None, "Fallback không được là None"
    assert selected_fallback["id"] in ["id_short1", "id_short2"]
    print(f"PASS test 2: Đã fallback thành công chọn '{selected_fallback['title']}' từ pool để loop")

    print("ALL TESTS PASSED: test_reup_bgm_selection hoàn tất 100%!")


if __name__ == "__main__":
    asyncio.run(test_reup_bgm_selection())
