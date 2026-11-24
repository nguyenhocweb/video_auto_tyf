import time
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from google import genai
from google.genai import types
from google.genai.errors import APIError

from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.dubbing.gemini_keys_schemas import (
    GeminiKeyCreateRequest,
    GeminiKeyResponse,
    GeminiKeyListResponse,
    GeminiKeyTestRequest,
    GeminiKeyTestResponse,
    GeminiKeyUpdateModelRequest,
)
from src.modules.creator.dubbing.gemini_keys_repository import GeminiKeysMongoRepository

logger = logging.getLogger("gemini_keys_router")

gemini_keys_router = APIRouter(prefix="/gemini-keys", tags=["Creator - Gemini API Keys"])


def _get_user_id(user) -> str:
    if isinstance(user, dict):
        return str(user.get("id") or user.get("_id") or "")
    return str(getattr(user, "id", ""))


@gemini_keys_router.get("", response_model=GeminiKeyListResponse)
async def list_gemini_keys_endpoint(current_user: dict = Depends(get_current_user)):
    """Lấy danh sách các Gemini API Keys trong hệ thống kèm trạng thái và số lượt sử dụng."""
    try:
        repo = GeminiKeysMongoRepository()
        items = await repo.get_all_keys()
        return GeminiKeyListResponse(total=len(items), items=items)
    except Exception as ex:
        logger.error(f"Lỗi lấy danh sách Gemini Keys: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@gemini_keys_router.post("/test", response_model=GeminiKeyTestResponse)
async def test_gemini_key_endpoint(
    payload: GeminiKeyTestRequest,
    current_user: dict = Depends(get_current_user),
):
    """Kiểm tra tính hợp lệ và tốc độ phản hồi của Gemini API Key với Model được chỉ định."""
    target_key = payload.key.strip() if payload.key else ""
    repo = GeminiKeysMongoRepository()

    if not target_key and payload.key_id:
        target_key = await repo.get_key_raw(payload.key_id) or ""

    if not target_key:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp API Key hoặc key_id để kiểm tra.")

    model_name = payload.model.strip() if payload.model else "gemini-2.5-flash"
    start_t = time.perf_counter()

    try:
        client = genai.Client(api_key=target_key)
        response = client.models.generate_content(
            model=model_name,
            contents="Dịch sang tiếng Việt: Hello World",
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=64,
            ),
        )
        latency_ms = int((time.perf_counter() - start_t) * 1000)
        output_text = getattr(response, "text", "") or ""
        clean_output = output_text.strip().replace("\n", " ")

        return GeminiKeyTestResponse(
            success=True,
            model=model_name,
            latency_ms=latency_ms,
            test_output=clean_output,
            message=f"Key hoạt động hoàn hảo! Phản hồi trong {latency_ms}ms.",
        )
    except APIError as ae:
        latency_ms = int((time.perf_counter() - start_t) * 1000)
        code = getattr(ae, "code", 400)
        err_msg = ae.message or str(ae)

        if code in (400, 401, 403):
            desc = f"Lỗi xác thực (HTTP {code}): API Key không hợp lệ hoặc bị vô hiệu hóa."
        elif code == 429:
            desc = "Lỗi quá tải (HTTP 429): API Key này đã chạm trần hạn mức Quota (RPM/RPD)."
        elif code == 404:
            desc = f"Lỗi không tìm thấy (HTTP 404): Model '{model_name}' không tồn tại hoặc tài khoản chưa được mở quyền."
        elif code == 503:
            desc = f"Máy chủ Google của model '{model_name}' đang quá tải tạm thời (HTTP 503). Key này vẫn SỐNG 100%, bạn hãy thử chọn model khác như 'Gemini 1.5 Flash' hoặc bấm test lại sau vài giây!"
        else:
            desc = f"Lỗi Google API (HTTP {code}): {err_msg[:120]}"

        return GeminiKeyTestResponse(
            success=False,
            model=model_name,
            latency_ms=latency_ms,
            error_code=code,
            message=desc,
        )
    except Exception as ex:
        latency_ms = int((time.perf_counter() - start_t) * 1000)
        return GeminiKeyTestResponse(
            success=False,
            model=model_name,
            latency_ms=latency_ms,
            error_code=500,
            message=f"Lỗi kết nối: {str(ex)[:120]}",
        )


@gemini_keys_router.post("", response_model=GeminiKeyResponse, status_code=status.HTTP_201_CREATED)
async def add_gemini_key_endpoint(
    payload: GeminiKeyCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Thêm một Gemini API Key mới vào Database để xoay tua tự động kèm Model chỉ định."""
    user_id = _get_user_id(current_user)
    repo = GeminiKeysMongoRepository()
    try:
        return await repo.add_key(
            user_id=user_id,
            key=payload.key,
            note=payload.note or "",
            model=payload.model or "gemini-2.5-flash",
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as ex:
        logger.error(f"Lỗi thêm Gemini Key: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@gemini_keys_router.patch("/{key_id}/model", response_model=GeminiKeyResponse)
async def update_gemini_key_model_endpoint(
    key_id: str,
    payload: GeminiKeyUpdateModelRequest,
    current_user: dict = Depends(get_current_user),
):
    """Cập nhật Model Gemini được ưu tiên sử dụng cho API Key."""
    repo = GeminiKeysMongoRepository()
    updated = await repo.update_key_model(key_id, payload.model)
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy Key.")
    return updated


@gemini_keys_router.delete("/{key_id}")
async def delete_gemini_key_endpoint(
    key_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Xóa một Gemini API Key khỏi Database."""
    repo = GeminiKeysMongoRepository()
    success = await repo.delete_key(key_id)
    if not success:
        raise HTTPException(status_code=404, detail="Không tìm thấy Key cần xóa.")
    return {"success": True, "message": "Đã xóa API Key thành công."}


@gemini_keys_router.patch("/{key_id}/toggle")
async def toggle_gemini_key_endpoint(
    key_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Bật hoặc tạm tắt một Gemini API Key."""
    repo = GeminiKeysMongoRepository()
    new_status = await repo.toggle_key(key_id)
    if new_status is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy Key.")
    status_label = "kích hoạt" if new_status else "tạm tắt"
    return {"success": True, "is_active": new_status, "message": f"Đã {status_label} Key thành công."}
