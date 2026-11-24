import os
import time
import logging
import urllib.request
from typing import Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("fast_model_downloader")


def download_chunk(url: str, start: int, end: int, dest_path: str, chunk_id: int):
    """Tải một chunk byte bằng HTTP Range và ghi trực tiếp vào file."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Range": f"bytes={start}-{end}",
        },
    )
    max_retries = 5
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                with open(dest_path, "r+b") as f:
                    f.seek(start)
                    f.write(data)
            return len(data)
        except Exception as e:
            if attempt == max_retries - 1:
                raise RuntimeError(f"Chunk {chunk_id} ({start}-{end}) thất bại sau {max_retries} lần: {e}")
            time.sleep(2)


def download_file_multithreaded(
    url: str, dest_path: str, num_threads: int = 8, expected_size: Optional[int] = None
) -> str:
    """Tải file lớn tốc độ cao qua nhiều kết nối đồng thời với HTTP Range."""
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # 1. Lấy tổng kích thước file
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        total_size = int(resp.headers.get("Content-Length", 0))

    if total_size <= 0 and expected_size:
        total_size = expected_size

    if total_size <= 0:
        raise ValueError(f"Không thể xác định kích thước file từ URL: {url}")

    print(f"Bắt đầu tải file: {dest.name} ({total_size / (1024 * 1024):.2f} MB) với {num_threads} luồng...")

    # 2. Tạo trước file với đúng kích thước (Pre-allocate)
    temp_dest = dest.with_suffix(".tmp_download")
    with open(temp_dest, "wb") as f:
        f.seek(total_size - 1)
        f.write(b"\0")

    # 3. Phân chia các dải byte cho từng luồng
    chunk_size = total_size // num_threads
    ranges = []
    for i in range(num_threads):
        start = i * chunk_size
        end = (start + chunk_size - 1) if i < num_threads - 1 else (total_size - 1)
        ranges.append((start, end, i))

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(download_chunk, url, r[0], r[1], str(temp_dest), r[2])
            for r in ranges
        ]
        for idx, fut in enumerate(futures):
            fut.result()
            elapsed = time.time() - start_time
            print(f"Chunk {idx + 1}/{num_threads} hoàn tất ({elapsed:.1f}s)...")

    # 4. Đổi tên từ file tạm sang file chính thức
    if dest.exists():
        dest.unlink()
    temp_dest.rename(dest)

    total_time = time.time() - start_time
    avg_speed = (total_size / (1024 * 1024)) / max(0.1, total_time)
    print(f"Tải thành công: {dest_path} ({total_size / (1024 * 1024):.2f} MB trong {total_time:.1f}s - {avg_speed:.2f} MB/s)")
    return str(dest)


def download_sensevoice_weights() -> str:
    """Tải trọng số mô hình SenseVoice-Small vào đúng thư mục ModelScope cache trên ổ D."""
    from src.core.config import settings

    target_dir = settings.STORAGE_DIR / "modelscope_cache" / "models" / "iic--SenseVoiceSmall" / "snapshots" / "master"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "model.pt"

    if target_file.exists() and target_file.stat().st_size > 500_000_000:
        print(f"Mô hình SenseVoice đã tồn tại sẵn: {target_file} ({target_file.stat().st_size / (1024*1024):.2f} MB)")
        return str(target_file)

    primary_url = "https://hf-mirror.com/FunAudioLLM/SenseVoiceSmall/resolve/main/model.pt"
    backup_url = "https://huggingface.co/FunAudioLLM/SenseVoiceSmall/resolve/main/model.pt"

    try:
        return download_file_multithreaded(primary_url, str(target_file), num_threads=8)
    except Exception as e:
        print(f"HF Mirror gặp sự cố ({e}), chuyển sang HuggingFace direct...")
        return download_file_multithreaded(backup_url, str(target_file), num_threads=6)


if __name__ == "__main__":
    download_sensevoice_weights()
