# Telegram Video & Image Downloader Bot

Bot Telegram mạnh mẽ hỗ trợ tải Video và Ảnh từ nhiều nguồn (YouTube, TikTok, Facebook, Instagram, Reels...) với chất lượng cao nhất, hỗ trợ tải hàng loạt và lách bản quyền/watermark.

## 🌟 Tính năng nổi bật

- **Tải Video chất lượng gốc**: Tự động chọn độ phân giải cao nhất (4K, 1080p...).
- **Chế độ Thông minh (Hybrid)**: 
  - Tự động tải bản tốt nhất nếu dung lượng ≤ 50MB.
  - Hiển thị Menu chọn chất lượng (720p, 480p...) nếu bản gốc > 50MB để phù hợp với Telegram Bot API.
- **Tải hàng loạt (Batch Download)**: Gửi danh sách nhiều link (mỗi link một dòng) để bot xử lý cùng lúc.
- **Hỗ trợ Ảnh**: Tự động nhận diện và tải ảnh/album từ Instagram, Facebook.
- **Xóa Watermark**: Tự động lấy bản "sạch" cho TikTok và Douyin.
- **Tự động dọn dẹp**: Xóa file tạm trên máy tính sau khi gửi để tiết kiệm bộ nhớ.
- **Chat gọn gàng**: Sau khi gửi video, bot tự xóa tin nhắn link gốc và tin nhắn trạng thái — link nguồn được giữ trong caption.
- **📊 Dashboard thống kê**: Web dashboard local tại `http://127.0.0.1:8350` — lượt tải theo ngày, tỉ lệ thành công, thống kê nền tảng, danh sách tải gần đây. Tự làm mới mỗi 4 giây, có dark mode.

## 🛠️ Cài đặt

1. **Yêu cầu hệ thống:**
   - Python 3.10 trở lên.
   - **FFmpeg**: Cần thiết để gộp video/âm thanh chất lượng cao.
     - Tải tại [ffmpeg.org](https://ffmpeg.org/download.html) và thêm vào PATH hệ thống.

2. **Cài đặt thư viện:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Cấu hình:**
   - Tạo file `.env` từ `.env.example`.
   - Điền `TELEGRAM_BOT_TOKEN` (lấy từ @BotFather).

4. **Cách tải nội dung riêng tư (video private, reels giới hạn):**
   - Sử dụng tiện ích "Get cookies.txt LOCALLY" trên trình duyệt.
   - Xuất file cookies của Facebook/Instagram và lưu tên là `cookies.txt` vào thư mục gốc của bot (bot tự nhận, không cần khởi động lại).
   - ⚠️ *Lưu ý: Facebook **Stories** hiện chưa được yt-dlp hỗ trợ, kể cả khi có cookies. Chỉ tải được video/reel/bài đăng.*

## 🚀 Khởi chạy

```bash
py bot.py
```
*(Dùng `python3 bot.py` nếu bạn dùng Linux/macOS)*

## 📖 Cách sử dụng
- Gửi 1 link hoặc nhiều link (mỗi link 1 dòng) vào bot.
- Làm theo hướng dẫn trên menu nếu video quá lớn.

## 📊 Dashboard
- Bot tự mở dashboard tại `http://127.0.0.1:8350` khi khởi động (chỉ truy cập được từ máy chạy bot).
- Đổi port bằng biến môi trường `DASHBOARD_PORT` trong `.env`; đặt `DASHBOARD_PORT=0` để tắt.
- Thống kê lưu trong `stats.json` (không đẩy lên git).

## ☁️ Deploy lên Render.com

Repo đã có sẵn `Dockerfile` (kèm FFmpeg) và `render.yaml`:

1. Đẩy code lên GitHub (public được — token nằm trong `.env` vốn không được commit).
2. Trên Render: **New → Web Service** → chọn repo → Render tự nhận Dockerfile.
3. Thêm biến môi trường `TELEGRAM_BOT_TOKEN` trong tab **Environment**.
4. Deploy xong, dashboard chính là trang chủ của service: `https://<tên-app>.onrender.com`.

**Lưu ý quan trọng:**
- **Không chạy bot trên máy local song song với Render** — hai instance cùng polling sẽ báo lỗi `Conflict` liên tục.
- **Gói Free của Render tự "ngủ" sau 15 phút không có traffic** → bot sẽ dừng nhận tin nhắn. Cách khắc phục miễn phí: dùng [UptimeRobot](https://uptimerobot.com) ping URL dashboard (`https://<tên-app>.onrender.com/api/stats`) mỗi 5 phút.
- Ổ đĩa của Render là tạm thời: `stats.json` sẽ reset mỗi lần deploy/restart.
- Cần `cookies.txt`? **Đừng commit nó lên repo public!** Vào Render → Environment → **Secret Files** → tạo file tên `cookies.txt` với nội dung cookies, mount path để mặc định.
- Dashboard trên Render là công khai (ai có link đều xem được thống kê). Muốn tắt: đặt biến `DASHBOARD_PORT=0` — nhưng khi đó Render Web Service sẽ fail port scan, hãy chuyển service sang loại **Background Worker** (mất phí) hoặc chấp nhận dashboard công khai.

## 👤 Tác giả & Ủng hộ
- **Phát triển bởi**: Toandn
- **Ủng hộ**: BIDV 1222172532 DINH NGOC TOAN
