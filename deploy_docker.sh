#!/usr/bin/env bash
# ==============================================================================
#      VIDEO AUTO TYF - ONE-CLICK DOCKER & NGINX DEPLOYMENT FOR UBUNTU VPS
# ==============================================================================
set -e

echo "=============================================================================="
echo "      TRIỂN KHAI DOCKER & NGINX REVERSE PROXY CHO VIDEO AUTO TYF SERVER       "
echo "=============================================================================="

# 1. Cài đặt Docker & Docker Compose nếu chưa có
if ! command -v docker &> /dev/null; then
    echo "🐳 [1/4] Docker chưa được cài đặt. Đang tiến hành cài đặt Docker..."
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo systemctl enable docker
    sudo systemctl start docker
    echo "✅ Docker đã được cài đặt thành công!"
else
    echo "✅ [1/4] Docker đã có sẵn trên máy chủ."
fi

# 2. Kiểm tra file cấu hình .env
echo "⚙️ [2/4] Kiểm tra biến môi trường .env..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "⚠️ ĐÃ TẠO FILE .env TỪ .env.example. VUI LÒNG ĐIỀN API KEYS (nano .env)!"
fi

# Đảm bảo các thư mục storage tồn tại để mount vào Docker
mkdir -p storage/temp storage/bgm storage/voice_profiles storage/audio_output storage/dubbing_output

# 3. Build & Khởi động Docker Containers (Backend + Nginx)
echo "🚀 [3/4] Đang build image và khởi động Docker Compose (Backend + Nginx)..."
docker compose down || true
docker compose up -d --build

# 4. Kiểm tra trạng thái hệ thống
echo "🔍 [4/4] Đang kiểm tra sức khỏe hệ thống..."
sleep 5
docker compose ps

echo "=============================================================================="
echo "🎉 HỆ THỐNG ĐÃ KHỞI CHẠY THÀNH CÔNG!"
echo "👉 Cổng Nginx (Reverse Proxy): http://103.20.102.228 (Cổng 80 tiêu chuẩn)"
echo "👉 Cổng Backend Trực tiếp:     http://103.20.102.228:8001"
echo "👉 Kiểm tra Swagger Docs:      http://103.20.102.228/docs"
echo "👉 Xem logs thời gian thực:    docker compose logs -f"
echo "=============================================================================="
