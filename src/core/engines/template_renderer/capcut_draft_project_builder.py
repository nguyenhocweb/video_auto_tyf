"""Bộ máy khởi tạo và tiêm dữ liệu vào Dự Án CapCut Desktop (CapCut Draft Project Builder).
Chịu trách nhiệm:
1. Tải gói mẫu nguyên bản (ZIP Package) từ máy chủ ByteDance CDN (chứa 100% hiệu ứng, sticker, transition, nhạc gốc).
2. Giải nén trực tiếp vào thư mục Projects của CapCut PC (com.lveditor.draft).
3. Tiêm (inject) chính xác video/ảnh của người dùng vào từng Slot tương ứng trong Track 0.
4. Đăng ký dự án vào root_meta_info.json để CapCut PC hiển thị ngay trên màn hình chính.
"""

import json
import logging
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional
import httpx
from src.core.engines.template_renderer.capcut_draft_meta_helper import CapCutDraftMetaHelper

logger = logging.getLogger("capcut_draft_project_builder")


class CapCutDraftProjectBuilder:
    """Builder chuyển hóa gói mẫu CapCut web thành dự án CapCut PC 100% nguyên bản."""

    CAPCUT_DRAFT_ROOT = Path(
        r"C:\Users\win\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft"
    )
    CACHE_DIR = Path("be/storage/temp/templates_cache").resolve()

    @classmethod
    def _ensure_dirs(cls):
        cls.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cls.CAPCUT_DRAFT_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def download_template_package(cls, template_id: str, template_url: str) -> Optional[Path]:
        """Tải và lưu cache gói tài nguyên ZIP chính thức từ ByteDance CDN."""
        cls._ensure_dirs()
        cache_file = cls.CACHE_DIR / f"capcut_tpl_{template_id}.zip"
        if cache_file.is_file() and cache_file.stat().st_size > 1024:
            logger.info(f"Sử dụng gói mẫu đã cache: {cache_file}")
            return cache_file

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
        }
        try:
            with httpx.Client(timeout=25.0, follow_redirects=True) as client:
                res = client.get(template_url, headers=headers)
                if res.status_code == 200 and len(res.content) > 1024:
                    with open(cache_file, "wb") as f:
                        f.write(res.content)
                    logger.info(f"Đã tải thành công gói mẫu ZIP ({len(res.content)} bytes)")
                    return cache_file
                else:
                    logger.error(f"Tải gói mẫu thất bại, mã trạng thái: {res.status_code}")
                    return None
        except Exception as ex:
            logger.error(f"Lỗi khi tải gói mẫu {template_id} từ {template_url}: {ex}")
            return None

    @classmethod
    def create_desktop_project(
        cls,
        template_id: str,
        template_url: Optional[str] = None,
        media_slots: Optional[Dict[int, str]] = None,
        project_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Tạo dự án CapCut PC hoàn chỉnh sẵn sàng mở hoặc xuất video."""
        cls._ensure_dirs()
        media_slots = media_slots or {}
        cache_file = cls.CACHE_DIR / f"capcut_tpl_{template_id}.zip"

        if cache_file.is_file() and cache_file.stat().st_size > 1024:
            zip_path = cache_file
        elif template_url:
            zip_path = cls.download_template_package(template_id, template_url)
        else:
            from src.core.engines.template_renderer.capcut_crawler import CapCutLiveCrawler
            crawled = CapCutLiveCrawler.crawl_template(template_id)
            if crawled and crawled.template_url:
                zip_path = cls.download_template_package(template_id, crawled.template_url)
            else:
                zip_path = None

        if not zip_path or not zip_path.is_file():
            raise RuntimeError(f"Không thể tải gói tài nguyên gốc cho mẫu ID {template_id}")

        import re, unicodedata
        nfkd = unicodedata.normalize("NFKD", project_title or template_id)
        ascii_title = "".join(c for c in nfkd if not unicodedata.combining(c))
        safe_title = re.sub(r"[^a-zA-Z0-9_]", "_", ascii_title)
        safe_title = re.sub(r"_+", "_", safe_title).strip("_")
        project_name = f"Tpl_{template_id[:8]}_{safe_title[:18]}_{int(time.time())}"
        target_proj_dir = cls.CAPCUT_DRAFT_ROOT / project_name
        target_proj_dir.mkdir(parents=True, exist_ok=True)
        user_assets_dir = target_proj_dir / "user_assets"
        user_assets_dir.mkdir(parents=True, exist_ok=True)

        # 1. Giải nén toàn bộ tài nguyên gốc vào thư mục dự án CapCut PC
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(target_proj_dir)

        template_json_path = target_proj_dir / "template.json"
        if not template_json_path.is_file():
            # Thử tìm file template.json ở các thư mục con
            found = list(target_proj_dir.glob("**/template.json"))
            if found:
                template_json_path = found[0]
            else:
                raise FileNotFoundError("Không tìm thấy file template.json trong gói mẫu!")

        with open(template_json_path, "r", encoding="utf-8") as f:
            draft_data = json.load(f)

        # 2. Định vị Track 0 (Main Video Track) và các slot cần thay thế
        materials = draft_data.get("materials", {})
        videos_list = materials.get("videos", [])
        videos_by_id = {v.get("id"): v for v in videos_list}

        main_video_track = None
        for track in draft_data.get("tracks", []):
            if track.get("type") == "video" and len(track.get("segments", [])) >= len(media_slots):
                main_video_track = track
                break
        if not main_video_track:
            for track in draft_data.get("tracks", []):
                if track.get("type") == "video":
                    main_video_track = track
                    break

        # 3. Tiêm file media người dùng vào đúng các slot
        if main_video_track:
            segments = main_video_track.get("segments", [])
            for slot_id, user_file in media_slots.items():
                seg_idx = slot_id - 1
                if seg_idx < len(segments):
                    seg = segments[seg_idx]
                    mat_id = seg.get("material_id")
                    mat_obj = videos_by_id.get(mat_id)
                    if mat_obj and os.path.exists(user_file):
                        ext = Path(user_file).suffix.lower()
                        dest_file = user_assets_dir / f"slot_{slot_id}_{Path(user_file).name}"
                        shutil.copy2(user_file, dest_file)
                        abs_dest_str = str(dest_file.resolve()).replace("\\", "/")

                        mat_obj["path"] = abs_dest_str
                        mat_obj["material_name"] = dest_file.name
                        mat_obj["type"] = "photo" if ext in (".jpg", ".jpeg", ".png", ".webp") else "video"
                        logger.info(f"Đã tiêm Slot {slot_id} -> {abs_dest_str} ({mat_obj['type']})")

        # 4. Chuẩn hóa đường dẫn tương đối của audios và videos gốc sang đường dẫn tuyệt đối
        for a in materials.get("audios", []):
            rel_p = a.get("path", "")
            if rel_p and not os.path.isabs(rel_p):
                a_abs = (target_proj_dir / rel_p).resolve()
                if a_abs.is_file():
                    a["path"] = str(a_abs).replace("\\", "/")

        for v in videos_list:
            rel_p = v.get("path", "")
            if rel_p and not os.path.isabs(rel_p):
                v_abs = (target_proj_dir / rel_p).resolve()
                if v_abs.is_file():
                    v["path"] = str(v_abs).replace("\\", "/")

        # Xóa các đường dẫn hệ thống Android (/data/user/0/...) gây lỗi CapCut Windows
        for cat in ["effects", "video_effects", "transitions", "filters"]:
            for item in materials.get(cat, []):
                p = item.get("path", "")
                if "/data/user/" in p or p.startswith("/"):
                    item["path"] = ""

        # Gán platform chuẩn Windows Native
        draft_data["platform"] = {
            "os": "windows",
            "os_version": "10.0.26200",
            "app_id": 359289,
            "app_version": "9.8.0",
            "app_source": "cc",
        }

        # 5. Lưu thành draft_content.json chuẩn của CapCut PC
        draft_content_path = target_proj_dir / "draft_content.json"
        with open(draft_content_path, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, ensure_ascii=False, indent=2)

        if template_json_path.name == "template.json":
            try:
                os.remove(template_json_path)
            except Exception:
                pass

        # 6. Tạo ảnh bìa thumbnail (draft_cover.jpg)
        cover_path = target_proj_dir / "draft_cover.jpg"
        if not cover_path.is_file():
            user_imgs = [f for f in user_assets_dir.glob("*") if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
            if user_imgs:
                shutil.copy2(user_imgs[0], cover_path)
            else:
                existing = list(cls.CAPCUT_DRAFT_ROOT.glob("*/draft_cover.jpg"))
                if existing:
                    shutil.copy2(existing[0], cover_path)

        # 7. Tạo draft_meta_info.json với 100% đường dẫn chuẩn
        now_us = int(time.time() * 1_000_000)
        draft_id = str(uuid.uuid4()).upper()
        total_duration_us = draft_data.get("duration", 0)

        meta_info = CapCutDraftMetaHelper.build_meta_info(
            target_proj_dir=target_proj_dir,
            draft_root=cls.CAPCUT_DRAFT_ROOT,
            draft_content_path=draft_content_path,
            cover_path=cover_path,
            project_name=project_name,
            draft_id=draft_id,
            total_duration_us=total_duration_us,
        )
        with open(target_proj_dir / "draft_meta_info.json", "w", encoding="utf-8") as f:
            json.dump(meta_info, f, ensure_ascii=False)

        # 8. Đăng ký dự án vào root_meta_info.json của CapCut PC
        CapCutDraftMetaHelper.register_to_root_meta(cls.CAPCUT_DRAFT_ROOT, meta_info)

        # Tìm file audio gốc
        audio_file = None
        audios_dir = target_proj_dir / "audios"
        if audios_dir.is_dir():
            audio_files = list(audios_dir.glob("*.m4a")) or list(audios_dir.glob("*.mp3"))
            if audio_files:
                audio_file = str(audio_files[0].resolve())

        return {
            "success": True,
            "project_name": project_name,
            "project_path": str(target_proj_dir),
            "draft_json": str(draft_content_path),
            "audio_path": audio_file,
            "total_duration": round(total_duration_us / 1_000_000, 2),
            "message": f"Đã khởi tạo thành công dự án '{project_name}' trong CapCut PC!",
        }

    @classmethod
    def launch_capcut(cls, project_path: Optional[str] = None) -> Dict[str, Any]:
        """Khởi chạy ứng dụng CapCut PC hoặc mở thư mục dự án trên Windows Explorer."""
        return CapCutDraftMetaHelper.launch_capcut(cls.CAPCUT_DRAFT_ROOT, project_path)


