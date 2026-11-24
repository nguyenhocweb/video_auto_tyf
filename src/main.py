import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings
from src.modules.creator.inspector.router import inspector_router
from src.modules.creator.facebook.router import facebook_router
from src.modules.creator.youtube.router import router as youtube_router
from src.modules.creator.tiktok.router import tiktok_router
from src.modules.creator.douyin.router import router as douyin_router
from src.modules.creator.automation.router import automation_router
from src.modules.creator.bgm.router import bgm_router
from src.modules.shared.auth.router import auth_router
from src.modules.shared.notifications.router import notifications_router
from src.modules.admin.dashboard.router import admin_dashboard_router
from src.modules.admin.users.router import admin_users_router
from src.modules.admin.voices.router import admin_voices_router
from src.modules.admin.settings.router import admin_settings_router
from src.modules.shared.ws.notification_ws import ws_router
from src.modules.creator.automation.scheduler import AutomationScheduler

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API nền tảng Video AI Automation (Core Management, Crawl & Publish)",
    version="1.0.0",
)

# Cấu hình CORS (Cho phép local dev và mọi domain triển khai trên Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Khởi động bộ lập lịch Automation cào và đăng video tự động."""
    AutomationScheduler.get_instance().start()


@app.on_event("shutdown")
async def shutdown_event():
    """Dừng các background tasks khi tắt server."""
    AutomationScheduler.get_instance().stop()


# Đăng ký Routers Core: Auth, Admin, Automation, Crawl & Publish
app.include_router(auth_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")
app.include_router(inspector_router, prefix="/api/v1/creator")
app.include_router(facebook_router, prefix="/api/v1/creator")
app.include_router(youtube_router, prefix="/api/v1/creator")
app.include_router(tiktok_router, prefix="/api/v1/creator")
app.include_router(douyin_router, prefix="/api/v1/creator")
app.include_router(automation_router, prefix="/api/v1/creator")
app.include_router(bgm_router, prefix="/api/v1/creator")
app.include_router(admin_dashboard_router, prefix="/api/v1/admin")
app.include_router(admin_users_router, prefix="/api/v1/admin")
app.include_router(admin_voices_router, prefix="/api/v1/admin")
app.include_router(admin_settings_router, prefix="/api/v1/admin")


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "engine": settings.OMNIVOICE_MODEL_ID,
        "device": settings.OMNIVOICE_DEVICE,
    }


@app.get("/", response_class=HTMLResponse, tags=["Public"])
async def home_page():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Auto Video AI Studio</title>
    <meta name="tiktok-developers-site-verification" content="ExEJvY6WIw6HL5yDRx1sXyMPE9NjdKtp">
</head>
<body style="font-family:sans-serif;padding:40px;line-height:1.6;">
    <h1>Auto Video AI Studio</h1>
    <p>AI Video creation and content automation platform for creators.</p>
    <p><a href="/terms">Terms of Service</a> | <a href="/privacy">Privacy Policy</a></p>
</body>
</html>"""


@app.get("/terms", response_class=HTMLResponse, tags=["Public"])
async def terms_page():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Terms of Service - Auto Video AI</title>
    <meta name="tiktok-developers-site-verification" content="ExEJvY6WIw6HL5yDRx1sXyMPE9NjdKtp">
</head>
<body style="font-family:sans-serif;padding:40px;line-height:1.6;">
    <h1>Terms of Service</h1>
    <p>Welcome to Auto Video AI. By accessing or using our platform, you agree to comply with our terms.</p>
</body>
</html>"""


@app.get("/tiktokExEJvY6WIw6HL5yDRx1sXyMPE9NjdKtp.txt", response_class=PlainTextResponse, tags=["Public"])
async def tiktok_verification():
    return "tiktok-developers-site-verification=ExEJvY6WIw6HL5yDRx1sXyMPE9NjdKtp"


@app.get("/privacy", response_class=HTMLResponse, tags=["Public"])
async def privacy_page():
    return """<!DOCTYPE html>
<html>
<head>
    <title>Privacy Policy - Auto Video AI</title>
    <meta name="tiktok-developers-site-verification" content="ExEJvY6WIw6HL5yDRx1sXyMPE9NjdKtp">
</head>
<body style="font-family:sans-serif;padding:40px;line-height:1.6;">
    <h1>Privacy Policy</h1>
    <p>Auto Video AI respects your privacy. We only use authorized access tokens to publish videos as requested by you.</p>
</body>
</html>"""


