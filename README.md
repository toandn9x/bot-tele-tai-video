# Telegram Video Downloader Bot

Bot Telegram hỗ trợ tải video từ nhiều nguồn (YouTube, TikTok, Facebook, Instagram...) với chất lượng gốc sử dụng `yt-dlp`.

## Cài đặt

1. **Yêu cầu hệ thống:**
   - Python 3.10 trở lên.
   - FFmpeg (rất quan trọng để gộp video và âm thanh chất lượng cao).
     - Windows: Tải tại [ffmpeg.org](https://ffmpeg.org/download.html) và thêm vào PATH.

2. **Cài đặt thư viện:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Cấu hình:**
   - Copy file `.env.example` thành `.env`.
   - Mở file `.env` và điền `TELEGRAM_BOT_TOKEN` của bạn (lấy từ @BotFather trên Telegram).

4. **Chạy Bot:**
   ```bash
   py bot.py
   ```
   *(Nếu bạn dùng Linux/macOS, hãy dùng `python3 bot.py`)*

## Các lệnh hỗ trợ
- `/start`: Khởi động và chào mừng.
- `/help`: Hướng dẫn cách dùng.
- `/author`: Thông tin tác giả.

## Cách sử dụng
- Gửi link video trực tiếp cho bot.
- Bot sẽ tự động tải về và gửi lại file video cho bạn.

## Lưu ý về watermark (TikTok/Douyin)
- `yt-dlp` thường hỗ trợ tải video không watermark một cách tự động.
- Để đảm bảo tính năng này hoạt động ổn định nhất, hãy thường xuyên cập nhật `yt-dlp` bằng lệnh:
  ```bash
  pip install -U yt-dlp
  ```

## Lưu ý về giới hạn dung lượng
- Telegram Bot API có giới hạn tải lên tối đa **50MB** cho mỗi file.
- Nếu video vượt quá 50MB, bot có thể không gửi được file trừ khi bạn sử dụng "Local Bot API Server".
- Bot này được thiết lập để ưu tiên định dạng MP4 để có thể xem trực tiếp trên Telegram.
