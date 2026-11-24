import time
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from groq import Groq, APIError, AuthenticationError, RateLimitError

from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.dubbing.groq_keys_schemas import (
    GroqKeyCreateRequest,
    GroqKeyResponse,
    GroqKeyListResponse,
    GroqKeyTestRequest,
    GroqKeyTestResponse,
    GroqKeyUpdateModelRequest,
)
from src.modules.creator.dubbing.groq_keys_repository import GroqKeysMongoRepository

logger = logging.getLogger("groq_keys_router")

groq_keys_router = APIRouter(prefix="/groq-keys", tags=["Creator - Groq API Keys"])


def _get_user_id(user) -> str:
    if isinstance(user, dict):
        return str(user.get("id") or user.get("_id") or "")
    return str(getattr(user, "id", ""))


@groq_keys_router.get("", response_model=GroqKeyListResponse)
async def list_groq_keys_endpoint(current_user: dict = Depends(get_current_user)):
    """Lấy danh sách các Groq API Keys trong hệ thống kèm trạng thái và số lượt sử dụng."""
    try:
        repo = GroqKeysMongoRepository()
        items = await repo.get_all_keys()
        return GroqKeyListResponse(total=len(items), items=items)
    except Exception as ex:
        logger.error(f"Lỗi lấy danh sách Groq Keys: {ex}")
        raise HTTPException(status_code=500, detail=str(ex))


@groq_keys_router.post("/test", response_model=GroqKeyTestResponse)
async def test_groq_key_endpoint(
    payload: GroqKeyTestRequest,
    current_user: dict = Depends(get_current_user),
):
    """Kiểm tra tính hợp lệ và tốc độ phản hồi siêu tốc của Groq API Key."""
    target_key = payload.key.strip() if payload.key else ""
    repo = GroqKeysMongoRepository()

    if not target_key and payload.key_id:
        target_key = await repo.get_key_raw(payload.key_id) or ""

    if not target_key:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp API Key hoặc key_id để kiểm tra.")

    model_name = payload.model.strip() if payload.model else "qwen/qwen3.8-27b"
    start_t = time.perf_counter()

    try:
        client = Groq(api_key=target_key, timeout=12.0)
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "Bạn là chuyên gia dịch thuật. Dịch ngắn gọn sang tiếng Việt."},
                {"role": "user", "content": "Hello World"},
            ],
            temperature=0.1,
            max_tokens=64,
        )
        latency_ms = int((time.perf_counter() - start_t) * 1000)
        output_text = completion.choices[0].message.content or ""
        clean_output = output_text.strip().replace("\n", " ")

        return GroqKeyTestResponse(
            success=True,
            model=model_name,
            latency_ms=latency_ms,
            test_output=clean_output,
            message=f"Groq phản hồi siêu tốc trong {latency_ms}ms!",
        )
    except AuthenticationError as auth_err:
        latency_ms = int((time.perf_counter() - start_t) * 1000)
        return GroqKeyTestResponse(
            success=False,
            model=model_name,
            latency_ms=latency_ms,
            error_code=401,
            message="Lỗi xác thực (HTTP 401): API Key Groq không hợp lệ hoặc đã bị thu hồi.",
        )
    except RateLimitError as rl_err:
        latency_ms = int((time.perf_counter() - start_t) * 1000)
        return GroqKeyTestResponse(
            success=False,
            model=model_name,
            latency_ms=latency_ms,
            error_code=429,
            message="Lỗi quá tải (HTTP 429): Key này đã chạm hạn ngạch RPM của Groq. Vui lòng thử lại sau.",
        )
    except APIError as ae:
        latency_ms = int((time.perf_counter() - start_t) * 1000)
        code = getattr(ae, "status_code", 400)
        err_msg = str(ae)
        return GroqKeyTestResponse(
            success=False,
            model=model_name,
            latency_ms=latency_ms,
            error_code=code,
            message=f"Lỗi Groq API (HTTP {code}): {err_msg[:120]}",
        )
    except Exception as e:
        latency_ms = int((time.perf_counter() - start_t) * 1000)
        return GroqKeyTestResponse(
            success=False,
            model=model_name,
            latency_ms=latency_ms,
            error_code=500,
            message=f"Lỗi kết nối Groq ({type(e).__name__}): {str(e)[:120]}",
        )


@groq_keys_router.post("", response_model=GroqKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_groq_key_endpoint(
    payload: GroqKeyCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Thêm Groq API Key mới vào Database."""
    try:
        repo = GroqKeysMongoRepository()
        user_id = _get_user_id(current_user)
        created = await repo.add_key(
            user_id=user_id,
            key=payload.key,
            note=payload.note or "",
            model=payload.model or "qwen/qwen3.8-27b",
        )
        return GroqKeyResponse(**created)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as ex:
        logger.error(f"Lỗi thêm Groq Key: {ex}")
        raise HTTPException(status_code=500, detail="Không thể lưu API Key.")


@groq_keys_router.patch("/{key_id}/model", response_model=GroqKeyResponse)
async def update_groq_key_model_endpoint(
    key_id: str,
    payload: GroqKeyUpdateModelRequest,
    current_user: dict = Depends(get_current_user),
):
    """Chỉ định Model Groq mặc định cho Key này."""
    repo = GroqKeysMongoRepository()
    updated = await repo.update_key_model(key_id=key_id, model=payload.model)
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy Key cần cập nhật Model.")
    return GroqKeyResponse(**updated)


@groq_keys_router.patch("/{key_id}/toggle")
async def toggle_groq_key_endpoint(
    key_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Bật / Tắt trạng thái hoạt động của Key."""
    repo = GroqKeysMongoRepository()
    new_status = await repo.toggle_key(key_id)
    if new_status is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy Key để cập nhật trạng thái.")
    return {"id": key_id, "is_active": new_status, "message": "Đã cập nhật trạng thái Key."}


@groq_keys_router.delete("/{key_id}")
async def delete_groq_key_endpoint(
    key_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Xóa một Groq API Key khỏi hệ thống."""
    repo = GroqKeysMongoRepository()
    deleted = await repo.delete_key(key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy Key để xóa.")
    return {"message": "Đã xóa Key thành công."}

