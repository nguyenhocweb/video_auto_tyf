import asyncio
import sys
import logging
from pathlib import Path

# Add be to path
be_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(be_dir))

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)

from src.core.engines.douyin.extractor import DouyinExtractor

async def main():
    raw_input = "7.64 :9pm U@Y.7M 05/08 zGI:/ 众所周知，人死是真的能复活的！#欺神演出 https://v.douyin.com/OxiQoISMevs/ 复制此链接，打开Dou音搜索，直接观看视频！"
    try:
        res = await DouyinExtractor.extract_no_watermark_video(raw_input)
        print("EXTRACTION SUCCESS!")
        print("Result:", res)
    except Exception as e:
        print("EXTRACTION FAILED:", type(e), e)
        import traceback
        traceback.print_exc()

asyncio.run(main())

