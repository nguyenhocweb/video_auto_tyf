import json
import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from src.modules.shared.auth.security import decode_access_token

logger = logging.getLogger("notification_ws")
ws_router = APIRouter(prefix="/ws", tags=["Realtime - WebSockets"])


class NotificationConnectionManager:
    """Quản lý các kết nối WebSocket realtime theo user_id."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"WebSocket client connected: user_id={user_id}. Active: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WebSocket client disconnected: user_id={user_id}")

    async def send_to_user(self, user_id: str, message: Dict[str, Any]):
        """Bắn sự kiện realtime trực tiếp tới tất cả các tab/thiết bị của User."""
        if user_id not in self.active_connections:
            return

        payload_str = json.dumps(message, ensure_ascii=False)
        stale_sockets = []

        for ws in self.active_connections[user_id]:
            try:
                await ws.send_text(payload_str)
            except Exception as exc:
                logger.warning(f"Error sending to ws client: {exc}")
                stale_sockets.append(ws)

        for stale in stale_sockets:
            self.disconnect(user_id, stale)


# Singleton instance
notification_manager = NotificationConnectionManager()


async def notify_user(user_id: str, event_type: str, data: Dict[str, Any]):
    """Helper phát thông báo realtime tới người dùng."""
    await notification_manager.send_to_user(
        user_id=user_id,
        message={
            "event": event_type,
            "data": data,
        },
    )


@ws_router.websocket("/notifications")
async def websocket_notifications_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
):
    """Cổng kết nối WebSocket nhận thông báo tiến trình tạo giọng ngầm."""
    if not token:
        await websocket.accept()
        await websocket.send_text(json.dumps({"event": "AUTH_FAILED", "message": "Missing token"}, ensure_ascii=False))
        await websocket.close(code=4401)
        return

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        await websocket.accept()
        await websocket.send_text(json.dumps({"event": "AUTH_FAILED", "message": "Token expired or invalid"}, ensure_ascii=False))
        await websocket.close(code=4401)
        return

    user_id = payload["sub"]
    await notification_manager.connect(user_id, websocket)

    try:
        # Gửi lời chào kết nối thành công
        await websocket.send_text(json.dumps({
            "event": "CONNECTED",
            "message": "Kết nối WebSocket thông báo thành công",
            "user_id": user_id,
        }, ensure_ascii=False))

        while True:
            # Giữ kết nối lắng nghe heartbeat/ping
            text = await websocket.receive_text()
            if text == "ping":
                await websocket.send_text(json.dumps({"event": "PONG"}))
    except WebSocketDisconnect:
        notification_manager.disconnect(user_id, websocket)
    except Exception as exc:
        logger.warning(f"WebSocket session exception: {exc}")
        notification_manager.disconnect(user_id, websocket)

