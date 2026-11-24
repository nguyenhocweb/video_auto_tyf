# 🎬 Video Auto TYF Server (TikTok - YouTube - Facebook)

Hệ thống máy chủ Backend tự động hóa chu kỳ cào video Douyin, xử lý lách bản quyền, đóng gói tiêu đề/hashtag và xuất bản tự động lên 3 nền tảng mạng xã hội: **TikTok**, **YouTube Shorts**, và **Facebook Reels**.

---

## 🚀 1. Yêu cầu hệ thống trên VPS

* **Hệ điều hành:** Ubuntu 22.04 LTS hoặc Ubuntu 24.04 LTS (Khuyên dùng).
* **Phần cứng tối thiểu:** 2 Core CPU, 4GB RAM, 35GB+ SSD/NVMe.
* **Môi trường:** Python 3.10+, FFmpeg, Git.

---

## 📦 2. Hướng dẫn cài đặt nhanh trên VPS (One-Click Deploy)

### Bước 1: Clone mã nguồn về VPS
```bash
git clone https://github.com/nguyenhocweb/video_auto_tyf.git
cd video_auto_tyf
```

### Bước 2: Chạy script cài đặt tự động
```bash
chmod +x deploy_vps.sh run_vps.sh
./deploy_vps.sh
```
*Script sẽ tự động: cài đặt FFmpeg, Python virtualenv, thư viện trong `requirements.txt`, và Chromium headless cho Playwright.*

### Bước 3: Cấu hình biến môi trường `.env`
```bash
nano .env
```
Điền các thông tin quan trọng:
* `DATABASE_URL`: Đường dẫn kết nối MongoDB Atlas (hoặc MongoDB local).
* `CLOUDINARY_*`: Thông tin Cloudinary lưu trữ media.
* `YOUTUBE_*`, `TIKTOK_*`, `FB_*`: Thông tin xác thực các kênh mạng xã hội.

### Bước 4: Chạy thử nghiệm Server
```bash
./run_vps.sh
```
Server sẽ chạy tại cổng **8001** (`http://IP_VPS:8001`).

---

## 🛡️ 3. Cấu hình chạy ngầm 24/7 bằng Systemd (Khuyên dùng cho Production)

Để server tự động chạy ngầm và tự khởi động lại khi VPS bị reboot, hãy tạo Systemd Service:

### 1. Tạo file service:
```bash
sudo nano /etc/systemd/system/video_auto_tyf.service
```

### 2. Dán nội dung sau (thay `/root/video_auto_tyf` bằng đường dẫn thực tế trên VPS của bạn):
```ini
[Unit]
Description=Video Auto TYF Automation Backend Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/video_auto_tyf
ExecStart=/root/video_auto_tyf/venv/bin/python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8001 --workers 2
Restart=always
RestartSec=10
EnvironmentFile=/root/video_auto_tyf/.env

[Install]
WantedBy=multi-user.target
```

### 3. Kích hoạt và khởi động service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable video_auto_tyf
sudo systemctl start video_auto_tyf
```

### 4. Kiểm tra trạng thái và xem log:
```bash
# Kiểm tra trạng thái đang chạy
sudo systemctl status video_auto_tyf

# Xem log trực tiếp thời gian thực
sudo journalctl -u video_auto_tyf -f
```

---

## ⚡ 4. Hoặc Chạy ngầm bằng PM2
Nếu máy chủ đã cài sẵn NodeJS & PM2:
```bash
pm2 start ./run_vps.sh --name "video_auto_tyf"
pm2 save
pm2 startup
```

---

## 📡 5. Các cổng và kết nối mạng
* **Port API chính:** `8001`
* **Kiểm tra sức khỏe hệ thống (Health Check):** `http://IP_VPS:8001/health`
* **Tài liệu API Swagger:** `http://IP_VPS:8001/docs`
