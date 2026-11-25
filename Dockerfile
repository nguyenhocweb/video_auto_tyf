# ==============================================================================
#                  VIDEO AUTO TYF - DOCKERFILE
# ==============================================================================
FROM python:3.11-slim

# Ngăn Python tạo các file .pyc và bật stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Cài đặt các gói hệ thống cần thiết: FFmpeg, Git, Curl và các thư viện đồ họa cho Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    build-essential \
    libnss3 \
    libatk-bridge2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt các gói phụ thuộc Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Cài đặt Playwright Chromium headless cho crawler Douyin
RUN playwright install chromium && \
    playwright install-deps chromium || true

# Sao chép toàn bộ mã nguồn vào container
COPY src ./src
COPY storage ./storage

# Mở cổng 8001
EXPOSE 8001

# Lệnh khởi chạy server FastAPI với 2 workers tối ưu cho VPS
CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
