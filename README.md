# 🎬 Video Auto TYF Server (TikTok - YouTube - Facebook)

Hệ thống máy chủ Backend tự động hóa chu kỳ cào video Douyin, xử lý lách bản quyền, đóng gói tiêu đề/hashtag và xuất bản tự động lên 3 nền tảng mạng xã hội: **TikTok**, **YouTube Shorts**, và **Facebook Reels**.

---

## 🚀 1. Triển khai siêu tốc bằng Docker & Nginx Reverse Proxy (Khuyên dùng)

### Bước 1: SSH vào VPS và Clone mã nguồn
```bash
git clone https://github.com/nguyenhocweb/video_auto_tyf.git
cd video_auto_tyf
```

### Bước 2: Cấp quyền và chạy script triển khai Docker tự động
```bash
chmod +x deploy_docker.sh deploy_vps.sh run_vps.sh
./deploy_docker.sh
```
*Script sẽ tự động cài đặt Docker, Docker Compose, build container Backend, cấu hình Nginx Reverse Proxy cổng 80 chuẩn và khởi động toàn bộ hệ thống ngầm 24/7.*

### Bước 3: Cấu hình biến môi trường `.env`
```bash
nano .env
```
Điền các thông tin quan trọng:
* `DATABASE_URL`: Đường dẫn kết nối MongoDB Atlas (hoặc MongoDB local).
* `CLOUDINARY_*`: Thông tin Cloudinary lưu trữ media.
* `YOUTUBE_*`, `TIKTOK_*`, `FB_*`: Thông tin xác thực các kênh mạng xã hội.

Sau khi sửa file `.env`, khởi động lại containers để áp dụng:
```bash
docker compose restart
```

---

## 📡 2. Kết nối từ Frontend (Next.js)

Khi hệ thống đã chạy qua Nginx trên VPS `103.20.102.228`:
* **API Base URL:** `http://103.20.102.228` (Cổng 80 tiêu chuẩn, không cần gõ port `:8001`).
* **WebSocket Host:** `103.20.102.228`
* **Swagger API Docs:** `http://103.20.102.228/docs`

Cấu hình trong file `fe/.env.local` hoặc Environment Variables trên Vercel:
```env
NEXT_PUBLIC_API_URL=http://103.20.102.228
NEXT_PUBLIC_WS_HOST=103.20.102.228
```

---

## 🛠️ 3. Các lệnh quản lý Docker hữu ích

```bash
# Xem log hệ thống thời gian thực:
docker compose logs -f

# Xem trạng thái các container:
docker compose ps

# Khởi động lại toàn bộ:
docker compose restart

# Dừng hệ thống:
docker compose down
```

---

## ⚡ 4. Hoặc Chạy trực tiếp bằng Python Virtualenv (Không dùng Docker)

Nếu VPS ít RAM và bạn không muốn dùng Docker:
```bash
./deploy_vps.sh
./run_vps.sh
```
*(Xem cấu hình Systemd chạy ngầm 24/7 trong file `deploy_vps.sh`).*
