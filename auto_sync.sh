#!/usr/bin/env bash
# ==============================================================================
#      VIDEO AUTO TYF - AUTO SYNC DAEMON SCRIPT FOR VPS
#      Tự động phát hiện code mới trên GitHub và cập nhật Docker Containers
# ==============================================================================

cd "$(dirname "$0")"

echo "=============================================================================="
echo "  🚀 BẮT ĐẦU TIẾN TRÌNH TỰ ĐỘNG CẬP NHẬT (AUTO-SYNC DAEMON) CHO SERVER VPS   "
echo "  Hệ thống sẽ tự động kiểm tra GitHub mỗi 60 giây và cập nhật container      "
echo "=============================================================================="

while true; do
    # Lấy thông tin mới nhất từ GitHub mà không ghi đè
    git fetch origin main --quiet 2>/dev/null || true

    LOCAL_HASH=$(git rev-parse HEAD)
    REMOTE_HASH=$(git rev-parse origin/main 2>/dev/null || echo "$LOCAL_HASH")

    if [ "$LOCAL_HASH" != "$REMOTE_HASH" ]; then
        echo ""
        echo "=============================================================================="
        echo "🔔 [$(date '+%Y-%m-%d %H:%M:%S')] Phát hiện Code mới trên GitHub!"
        echo "📥 Đang tải code mới về (git pull origin main)..."
        git pull origin main
        
        echo "🐳 Đang tự động cập nhật Docker Containers..."
        docker compose up -d --build
        
        echo "✅ Cập nhật hoàn tất thành công!"
        echo "=============================================================================="
    fi

    # Nghỉ 60 giây trước lần kiểm tra tiếp theo
    sleep 60
done
