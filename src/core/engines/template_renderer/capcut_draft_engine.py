"""Bộ chuyển đổi và điều phối Dự án CapCut/JianYing Draft tự động (pyJianYingDraft & pycapcut).
Tự động sinh cấu trúc draft_content.json chuẩn native của CapCut Desktop và hỗ trợ kích hoạt export.
"""

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("capcut_draft_engine")


class CapCutDraftEngine:
    """Bộ tạo và đồng bộ dự án CapCut/JianYing Draft từ mã nguồn mẫu."""

    def __init__(self, custom_draft_dir: Optional[str] = None):
        if custom_draft_dir:
            self.draft_base_dir = Path(custom_draft_dir)
        else:
            # Thư mục draft ngầm định của CapCut trên Windows
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            capcut_draft_path = Path(local_appdata) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
            if capcut_draft_path.is_dir():
                self.draft_base_dir = capcut_draft_path
            else:
                self.draft_base_dir = Path("be/storage/temp/capcut_drafts")
        self.draft_base_dir.mkdir(parents=True, exist_ok=True)

    def create_three_photo_draft(
        self,
        project_name: str,
        image1_path: str,
        image2_path: str,
        image3_path: str,
        audio_path: Optional[str] = None,
    ) -> Path:
        """Tạo dự án CapCut Draft native chứa 3 ảnh và nhạc nền beat sync."""
        project_dir = self.draft_base_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        try:
            import pyJianYingDraft as draft
            script = draft.ScriptFile(width=720, height=1280, fps=30)
            v_track = script.add_track(draft.TrackType.video)

            # Thêm ảnh 1 (0.0s - 18.6s)
            p1_mat = draft.VideoMaterial(image1_path)
            v_track.add_segment(
                draft.VideoSegment(p1_mat, draft.Timerange(0, 18600000))  # microseconds
            )

            # Thêm ảnh 2 và ảnh 3 luân phiên
            p2_mat = draft.VideoMaterial(image2_path)
            p3_mat = draft.VideoMaterial(image3_path)
            v_track.add_segment(draft.VideoSegment(p2_mat, draft.Timerange(18600000, 4267000)))
            v_track.add_segment(draft.VideoSegment(p3_mat, draft.Timerange(22867000, 3333000)))
            v_track.add_segment(draft.VideoSegment(p2_mat, draft.Timerange(26200000, 1800000)))
            v_track.add_segment(draft.VideoSegment(p3_mat, draft.Timerange(28000000, 3233000)))

            if audio_path and Path(audio_path).is_file():
                a_track = script.add_track(draft.TrackType.audio)
                a_mat = draft.AudioMaterial(audio_path)
                a_track.add_segment(draft.AudioSegment(a_mat, draft.Timerange(0, 31233000)))

            draft_json_file = project_dir / "draft_content.json"
            script.save(str(draft_json_file))
            logger.info(f"Đã tạo thành công CapCut draft native tại: {project_dir}")
            return project_dir

        except Exception as ex:
            logger.warning(f"Lỗi khi dựng draft qua pyJianYingDraft: {ex}")
            # Fallback tạo cấu hình JSON draft tối thiểu
            meta = {
                "draft_id": project_name,
                "draft_name": project_name,
                "materials": [image1_path, image2_path, image3_path],
                "created_at": time.time(),
            }
            with open(project_dir / "draft_meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            return project_dir

    def try_export_via_capcut(self, project_name: str, output_file: str) -> bool:
        """Thử gọi CapCut Controller tự động xuất video nếu CapCut Desktop đang mở."""
        try:
            import pyJianYingDraft as draft
            ctrl = draft.JianyingController()
            ctrl.export_draft(project_name, output_file)
            logger.info(f"CapCut Desktop đã xuất file thành công tới: {output_file}")
            return True
        except Exception as ex:
            logger.warning(f"CapCut Desktop automation không khả dụng ({ex}). Tự động dùng GPU Hybrid Engine.")
            return False
