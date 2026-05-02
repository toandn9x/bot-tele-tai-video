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
- **Lách chặn & Tải Story**: Hỗ trợ sử dụng file `cookies.txt` để tải Facebook Stories hoặc nội dung yêu cầu đăng nhập.
- **Menu tiện lợi**: Tích hợp sẵn các lệnh `/start`, `/help`, `/author` trong menu bot.
- **Tự động dọn dẹp**: Xóa file tạm trên máy tính sau khi gửi để tiết kiệm bộ nhớ.

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

4. **Cách tải Facebook Stories/Nội dung riêng tư:**
   - Sử dụng tiện ích "Get cookies.txt" trên trình duyệt.
   - Xuất file cookies của Facebook/Instagram và lưu tên là `cookies.txt` vào thư mục gốc của bot.

## 🚀 Khởi chạy

```bash
py bot.py
```
*(Dùng `python3 bot.py` nếu bạn dùng Linux/macOS)*

## 📖 Cách sử dụng
- Gửi 1 link hoặc nhiều link (mỗi link 1 dòng) vào bot.
- Làm theo hướng dẫn trên menu nếu video quá lớn.

## 👤 Tác giả & Ủng hộ
- **Phát triển bởi**: Toandn
- **Ủng hộ**: BIDV 1222172532 DINH NGOC TOAN
