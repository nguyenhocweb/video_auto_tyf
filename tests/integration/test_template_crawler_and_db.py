"""Test tích hợp tự động cào mẫu CapCut và lưu trữ MongoDB."""

import pytest
import pytest_asyncio
from src.core.engines.template_renderer.template_parser import CapCutTemplateParser
from src.modules.creator.template_video.repository import TemplateVideoRepository


@pytest.mark.asyncio
async def test_crawl_and_save_template():
    target_url = (
        "https://www.capcut.com/templates/7164622511613725953"
        "?scene=search&search_keyword=tr%C3%A1i+tim+anh+ch%E1%BA%B3ng+c%C3%B2n"
    )

    # 1. Bóc tách kịch bản
    parsed = CapCutTemplateParser.parse_from_template_id_or_url(target_url)
    assert parsed is not None
    assert parsed.template_id == "7164622511613725953"
    assert len(parsed.slots) == 2
    assert parsed.slots[0].duration > 0
    assert parsed.slots[1].duration > 0

    # 2. Thao tác MongoDB Repository
    repo = TemplateVideoRepository()
    saved = await repo.save_template(
        user_id="test_user",
        template_data=parsed.model_dump(),
    )
    assert saved["template_id"] == "7164622511613725953"
    assert "id" in saved

    # 3. Kiểm tra is_template_saved
    is_saved = await repo.is_template_saved("7164622511613725953")
    assert is_saved is True

    # 4. Lấy chi tiết
    fetched = await repo.get_template_by_id("7164622511613725953")
    assert fetched is not None
    assert fetched["title"] == parsed.title

    # 5. Dọn dẹp xóa
    deleted = await repo.delete_template("7164622511613725953")
    assert deleted is True
