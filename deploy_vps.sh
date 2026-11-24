#!/usr/bin/env bash
# ==============================================================================
#           VIDEO AUTO TYF - ONE-CLICK DEPLOYMENT SCRIPT FOR UBUNTU VPS
# ==============================================================================
set -e

echo "=============================================================================="
echo "          CÀI ĐẶT TỰ ĐỘNG SERVER VIDEO AUTO TYF (TIKTOK - YOUTUBE - FB)       "
echo "=============================================================================="

# 1. Cập nhật hệ thống và cài đặt các gói cần thiết
echo "📦 [1/5] Đang cập nhật hệ thống và cài đặt ffmpeg, python3, git..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg git curl

# 2. Tạo môi trường ảo Virtual Environment
echo "🐍 [2/5] Đang khởi tạo Python Virtual Environment (venv)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

# 3. Cài đặt các thư viện Python
echo "📥 [3/5] Đang cài đặt thư viện từ requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Cài đặt Playwright Chromium (cho crawler Douyin/TikTok)
echo "🌐 [4/5] Đang cài đặt Chromium headless cho crawler..."
playwright install chromium
playwright install-deps chromium || true

# 5. Khởi tạo file .env nếu chưa có
echo "⚙️ [5/5] Kiểm tra cấu hình .env..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "⚠️ ĐÃ TẠO FILE .env TỪ MẪU .env.example. VUI LÒNG CHỈNH SỬA .env TRƯỚC KHI CHẠY THẬT!"
fi

# Cấp quyền thực thi cho run_vps.sh
chmod +x run_vps.sh deploy_vps.sh

echo "=============================================================================="
echo "✅ CÀI ĐẶT HOÀN TẤT!"
echo "👉 Để cấu hình API keys: nano .env"
echo "👉 Để chạy server ngay: ./run_vps.sh"
echo "👉 Để chạy ngầm 24/7 bằng PM2 hoặc Systemd, xem chi tiết trong README.md"
echo "=============================================================================="
