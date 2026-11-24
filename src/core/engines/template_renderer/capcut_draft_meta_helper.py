"""Helper xử lý metadata, đăng ký dự án và khởi chạy ứng dụng CapCut PC."""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("capcut_draft_meta_helper")


class CapCutDraftMetaHelper:
    """Helper quản lý metadata và liên kết ứng dụng CapCut Desktop."""

    @classmethod
    def build_meta_info(
        cls,
        target_proj_dir: Path,
        draft_root: Path,
        draft_content_path: Path,
        cover_path: Path,
        project_name: str,
        draft_id: str,
        total_duration_us: int,
    ) -> Dict[str, Any]:
        """Tạo từ điển metadata chuẩn 100% tương thích với CapCut Desktop."""
        now_us = int(time.time() * 1_000_000)
        t_dir_str = str(target_proj_dir).replace("\\", "/")
        r_dir_str = str(draft_root).replace("\\", "/")
        c_file_str = str(draft_content_path).replace("\\", "/")
        cov_str = str(cover_path).replace("\\", "/") if cover_path.is_file() else f"{t_dir_str}/draft_cover.jpg"

        return {
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": cov_str,
            "draft_fold_path": t_dir_str,
            "draft_id": draft_id,
            "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_infinite_canvas_draft": False,
            "draft_is_invisible": False,
            "draft_is_pippit_draft": False,
            "draft_is_web_article_video": False,
            "draft_json_file": c_file_str,
            "draft_name": project_name,
            "draft_new_version": "",
            "draft_root_path": r_dir_str,
            "draft_timeline_materials_size": 1989481,
            "draft_type": "",
            "draft_web_article_video_enter_from": "",
            "pippit_avatar_url": "",
            "pippit_extra_info": "",
            "pippit_id": "",
            "pippit_user_name": "",
            "streaming_edit_draft_ready": True,
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1,
            "tm_draft_create": now_us,
            "tm_draft_modified": now_us,
            "tm_draft_removed": 0,
            "tm_duration": total_duration_us,
        }

    @classmethod
    def register_to_root_meta(cls, draft_root: Path, meta_info: Dict[str, Any]):
        """Thêm dự án vào danh sách root_meta_info.json để CapCut PC hiển thị ở trang chủ."""
        root_meta_path = draft_root / "root_meta_info.json"
        if not root_meta_path.is_file():
            return
        try:
            with open(root_meta_path, "r", encoding="utf-8") as f:
                root_data = json.load(f)

            store = root_data.get("all_draft_store", [])
            store = [p for p in store if p.get("draft_name") != meta_info["draft_name"]]
            store.insert(0, meta_info)
            root_data["all_draft_store"] = store

            with open(root_meta_path, "w", encoding="utf-8") as f:
                json.dump(root_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Đã đăng ký dự án '{meta_info['draft_name']}' vào root_meta_info.json")
        except Exception as ex:
            logger.warning(f"Không thể cập nhật root_meta_info.json: {ex}")

    @classmethod
    def launch_capcut(cls, draft_root: Path, project_path: Optional[str] = None) -> Dict[str, Any]:
        """Khởi chạy ứng dụng CapCut PC hoặc mở thư mục dự án trên Windows Explorer."""
        if project_path and os.path.exists(project_path):
            try:
                subprocess.Popen(["explorer.exe", str(Path(project_path).resolve())])
                return {"success": True, "message": f"Đã mở thư mục dự án: {project_path}"}
            except Exception as ex:
                logger.warning(f"Lỗi mở thư mục dự án: {ex}")

        capcut_exe_paths = [
            Path(r"C:\Users\win\AppData\Local\CapCut\Apps\CapCut.exe"),
            Path(os.path.expandvars(r"%LOCALAPPDATA%\CapCut\Apps\CapCut.exe")),
        ]
        for exe in capcut_exe_paths:
            if exe.is_file():
                try:
                    subprocess.Popen([str(exe)])
                    return {"success": True, "message": f"Đã mở ứng dụng CapCut PC ({exe.name})"}
                except Exception as ex:
                    logger.warning(f"Lỗi khởi chạy {exe}: {ex}")

        if draft_root.exists():
            try:
                subprocess.Popen(["explorer.exe", str(draft_root)])
                return {"success": True, "message": "Đã mở thư mục lưu dự án của CapCut PC"}
            except Exception as ex:
                return {"success": False, "message": f"Lỗi mở thư mục: {ex}"}

        return {"success": False, "message": "Không tìm thấy đường dẫn cài đặt CapCut PC"}
