import asyncio
import sys
from pathlib import Path
import httpx

be_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(be_dir))
sys.stdout.reconfigure(encoding='utf-8')

from src.main import app

async def test_endpoint():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "url": "7.64 :9pm U@Y.7M 05/08 zGI:/ 众所周知，人死是真的能复活的！#欺神演出 https://v.douyin.com/OxiQoISMevs/ 复制此链接，打开Dou音搜索，直接观看视频！"
        }
        print("Calling /api/v1/creator/video/extract...")
        r = await client.post("/api/v1/creator/video/extract", json=payload, timeout=30.0)
        print("Status Code:", r.status_code)
        if r.status_code == 200:
            print("Response 200 OK! Data:")
            print("Title:", r.json().get("title"))
            print("Video URL:", r.json().get("video_url")[:100])
            print("Author:", r.json().get("author"))
        else:
            print("Response Error:", r.json())

if __name__ == "__main__":
    asyncio.run(test_endpoint())
