#!/usr/bin/env bash
# ==============================================================================
#                  VIDEO AUTO TYF - START SERVER ON VPS
# ==============================================================================
set -e

# Chuyển đến thư mục chứa script
cd "$(dirname "$0")"

# Kích hoạt môi trường ảo
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "⚠️ Không tìm thấy venv! Đang dùng Python hệ thống..."
fi

echo "🚀 Đang khởi động Video Auto TYF Server trên cổng 8001..."
python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8001 --workers 2
