import urllib.parse
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
import httpx

logger = logging.getLogger("creator_video_router")
from src.modules.shared.auth.dependencies import get_current_user
from src.modules.creator.video.schemas import (
    VideoExtractRequest,
    VideoMetadataResponse,
    VideoSaveRequest,
    VideoRecordResponse,
    VideoPaginationResponse,
    ChannelCrawlRequest,
    ChannelTodayVideosResponse,
    SavedChannelCreateRequest,
    SavedChannelUpdateRequest,
    SavedChannelResponse,
    SavedChannelListResponse,
)
from src.modules.creator.video.service import VideoDownloadService

video_router = APIRouter(prefix="/video", tags=["Creator - Auto Tải Video"])


def get_video_service() -> VideoDownloadService:
    return VideoDownloadService()


@video_router.post(
    "/extract",
    response_model=VideoMetadataResponse,
    summary="Bóc tách link video Douyin lấy MP4 không logo",
)
async def extract_video_endpoint(
    payload: VideoExtractRequest,
    service: VideoDownloadService = Depends(get_video_service),
):
    try:
        return await service.extract_douyin(payload.url)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi trích xuất video: {str(exc)}",
        )


@video_router.post(
    "/channel/today",
    response_model=ChannelTodayVideosResponse,
    summary="Quét danh sách video mới nhất mà kênh đăng",
)
async def crawl_channel_today_endpoint(
    payload: ChannelCrawlRequest,
    service: VideoDownloadService = Depends(get_video_service),
):
    try:
        return await service.crawl_channel_today(payload.url, payload.limit)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as exc:
        logger.exception("Chi tiết lỗi khi cào dữ liệu kênh Douyin:")
        err_msg = str(exc).strip()
        if not err_msg:
            err_msg = f"{type(exc).__name__} ({repr(exc)})"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi cào dữ liệu kênh Douyin: {err_msg}",
        )


@video_router.post(
    "/save",
    response_model=VideoRecordResponse,
    summary="Lưu video vào thư viện cá nhân của người dùng",
)
async def save_video_endpoint(
    payload: VideoSaveRequest,
    current_user: dict = Depends(get_current_user),
    service: VideoDownloadService = Depends(get_video_service),
):
    return await service.save_video_to_library(current_user["id"], payload)


@video_router.get(
    "/history",
    response_model=VideoPaginationResponse,
    summary="Lấy danh sách video đã lưu trong thư viện (phân trang)",
)
async def get_history_endpoint(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
    service: VideoDownloadService = Depends(get_video_service),
):
    return await service.get_user_history(current_user["id"], page=page, limit=limit)


@video_router.delete(
    "/{record_id}",
    summary="Xóa video khỏi thư viện cá nhân",
)
async def delete_video_endpoint(
    record_id: str,
    current_user: dict = Depends(get_current_user),
    service: VideoDownloadService = Depends(get_video_service),
):
    success = await service.delete_record(current_user["id"], record_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy video cần xóa hoặc bạn không có quyền.",
        )
    return {"success": True, "message": "Xóa video thành công"}


@video_router.api_route(
    "/proxy-download",
    methods=["GET", "HEAD"],
    summary="Stream tải file hoặc xem trực tiếp MP4 / MP3 (vượt hạn chế CORS)",
)
async def proxy_download_endpoint(
    request: Request,
    url: str = Query(..., description="URL file video hoặc âm thanh từ CDN"),
    filename: str = Query("video_no_watermark.mp4", description="Tên file tải về"),
    inline: bool = Query(False, description="True nếu xem trực tiếp trên trình duyệt"),
):
    desktop_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    headers = {"User-Agent": desktop_ua, "Referer": "https://www.douyin.com/"}
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    client = httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0)

    try:
        req = client.build_request("GET", url)
        res = await client.send(req, stream=True)

        async def stream_generator():
            try:
                async for chunk in res.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk
            finally:
                await res.aclose()
                await client.aclose()

        encoded_filename = urllib.parse.quote(filename)
        content_type = res.headers.get("content-type", "video/mp4")
        resp_headers = {
            "Accept-Ranges": "bytes",
        }
        if "content-range" in res.headers:
            resp_headers["Content-Range"] = res.headers["content-range"]
        if "content-length" in res.headers:
            resp_headers["Content-Length"] = res.headers["content-length"]

        if inline:
            resp_headers["Content-Disposition"] = "inline"
        else:
            resp_headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"

        return StreamingResponse(
            stream_generator(),
            status_code=res.status_code,
            media_type=content_type,
            headers=resp_headers,
        )
    except Exception as exc:
        await client.aclose()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể stream tải file: {str(exc)}",
        )


@video_router.post(
    "/channel/saved",
    response_model=SavedChannelResponse,
    summary="Lưu thông tin kênh Douyin vào thư viện cá nhân của user",
)
async def save_channel_endpoint(
    payload: SavedChannelCreateRequest,
    current_user: dict = Depends(get_current_user),
    service: VideoDownloadService = Depends(get_video_service),
):
    return await service.save_channel(current_user["id"], payload)


@video_router.get(
    "/channel/saved",
    response_model=SavedChannelListResponse,
    summary="Lấy danh sách các kênh Douyin đã lưu của user (cách ly hoàn toàn)",
)
async def get_saved_channels_endpoint(
    current_user: dict = Depends(get_current_user),
    service: VideoDownloadService = Depends(get_video_service),
):
    return await service.get_saved_channels(current_user["id"])


@video_router.patch(
    "/channel/saved/{channel_id}",
    response_model=SavedChannelResponse,
    summary="Đổi tên kênh Douyin đã lưu",
)
async def update_saved_channel_name_endpoint(
    channel_id: str,
    payload: SavedChannelUpdateRequest,
    current_user: dict = Depends(get_current_user),
    service: VideoDownloadService = Depends(get_video_service),
):
    updated = await service.update_saved_channel_name(channel_id, current_user["id"], payload.name)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy kênh hoặc bạn không có quyền sửa kênh này",
        )
    return updated


@video_router.delete(
    "/channel/saved/{channel_id}",
    summary="Xóa kênh Douyin đã lưu khỏi thư viện cá nhân",
)
async def delete_saved_channel_endpoint(
    channel_id: str,
    current_user: dict = Depends(get_current_user),
    service: VideoDownloadService = Depends(get_video_service),
):
    deleted = await service.delete_saved_channel(channel_id, current_user["id"])
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy kênh hoặc bạn không có quyền xóa kênh này",
        )
    return {"success": True, "message": "Đã xóa kênh thành công"}


from src.modules.creator.video.slicer_router import slicer_router
video_router.include_router(slicer_router)

