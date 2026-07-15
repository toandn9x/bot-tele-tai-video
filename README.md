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
- **Douyin không cần cookies**: Khi Douyin chặn yt-dlp, bot tự chuyển sang trang share (Plan B) — vẫn tải được bản không watermark.
- **Dán nguyên share text**: Không cần cắt link — dán cả đoạn "复制打开抖音..." bot tự tìm URL.
- **Tự động dọn dẹp**: Xóa file tạm trên máy tính sau khi gửi để tiết kiệm bộ nhớ.
- **Chat gọn gàng**: Sau khi gửi video, bot tự xóa tin nhắn link gốc và tin nhắn trạng thái — link nguồn được giữ trong caption.
- **🎵 Tải nhạc MP3**: Cuối menu chọn chất lượng (cả bot lẫn web) có nút tách audio sang MP3 192kbps (cần FFmpeg).
- **🌐 Web tải trực tiếp**: Trang chủ (`http://127.0.0.1:8350`) là giao diện tải video kiểu cobalt.tools — dán link, chọn chất lượng, file tải thẳng về máy. Không cần Telegram.
- **📊 Dashboard thống kê**: Tại `/stats` — lượt tải theo ngày, tỉ lệ thành công, thống kê nền tảng, danh sách tải gần đây. Tự làm mới mỗi 4 giây, có dark mode.

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

4. **Cách tải nội dung riêng tư / YouTube trên server (cookies.txt):**
   - Sử dụng tiện ích "Get cookies.txt LOCALLY" trên trình duyệt, xuất cookies rồi lưu thành `cookies.txt`.
   - Bot tự tìm cookies theo thứ tự: biến môi trường `COOKIES_FILE` → `cookies.txt` trong thư mục bot → `/etc/secrets/cookies.txt` (Render Secret Files).
   - ⚠️ *Facebook **Stories** chưa được yt-dlp hỗ trợ kể cả khi có cookies.*
   - ⚠️ *Chạy trên máy chủ (Render, VPS...): **YouTube thường chặn IP datacenter** và bắt đăng nhập "xác minh không phải bot". Đây không phải video riêng tư — cần thêm `cookies.txt` của YouTube (nên dùng **tài khoản phụ**, vì hoạt động bất thường có thể khiến tài khoản bị khóa). Máy tính cá nhân thường tải YouTube bình thường không cần cookies.*

## 🚀 Khởi chạy

```bash
py bot.py
```
*(Dùng `python3 bot.py` nếu bạn dùng Linux/macOS)*

## 📖 Cách sử dụng
- Gửi 1 link hoặc nhiều link (mỗi link 1 dòng) vào bot.
- Làm theo hướng dẫn trên menu nếu video quá lớn.

## 🌐 Web & Dashboard
- Khi khởi động, bot mở web server tại `http://127.0.0.1:8350`:
  - **`/`** — trang tải video trực tiếp (dán link → tải file về máy, không cần Telegram).
  - **`/stats`** — dashboard thống kê.
- Web chỉ tải từ các nền tảng trong danh sách cho phép (YouTube, TikTok, Douyin, Facebook, Instagram, X) và giới hạn 2 lượt tải cùng lúc để không quá tải server.
- Đổi port bằng biến môi trường `DASHBOARD_PORT` trong `.env`; đặt `DASHBOARD_PORT=0` để tắt.
- Thống kê lưu trong `stats.json` (không đẩy lên git).

## ☁️ Deploy lên Render.com

Repo đã có sẵn `Dockerfile` (kèm FFmpeg) và `render.yaml`:

1. Đẩy code lên GitHub (public được — token nằm trong `.env` vốn không được commit).
2. Trên Render: **New → Web Service** → chọn repo → Render tự nhận Dockerfile.
3. Thêm biến môi trường `TELEGRAM_BOT_TOKEN` trong tab **Environment**.
4. Deploy xong, dashboard chính là trang chủ của service: `https://<tên-app>.onrender.com`.

**Cloudflare WARP (lách chặn YouTube trên server):**
- YouTube chặn IP datacenter; Dockerfile đã cài sẵn Cloudflare WARP, `entrypoint.sh` bật WARP ở chế độ proxy và **chỉ định tuyến YouTube qua đó** (TikTok/Douyin/Facebook vẫn đi thẳng).
- Bật/tắt bằng biến `USE_WARP` (mặc định `1`). Muốn tắt nhanh: đặt `USE_WARP=0` trong Environment rồi deploy lại — không cần sửa code.
- Nếu WARP không kết nối được, bot vẫn chạy bình thường (chỉ YouTube có thể bị chặn), không làm hỏng nền tảng khác.
- ⚠️ *Đây là mẹo miễn phí, không đảm bảo bền — YouTube có thể siết dải IP Cloudflare bất cứ lúc nào. Khi đó quay lại dùng cookies hoặc chạy máy nhà.*

**Webhook vs Polling (tự động):**
- Khi có biến `RENDER_EXTERNAL_URL` (Render tự set) hoặc `WEBHOOK_URL`, bot chạy **webhook** — Telegram gọi thẳng vào server nên **hết lỗi `Conflict` khi deploy** (không còn polling để tranh nhau), và tin nhắn tự đánh thức service khi ngủ. Webhook dùng chung cổng với web/dashboard (đường dẫn bí mật `/tg/<hash-token>`).
- Chạy **local** (không có 2 biến trên) thì tự động dùng **polling** như thường.

**Lưu ý quan trọng:**
- **Không chạy bot local song song với instance trên Render** — dù webhook đã hết xung đột polling, chạy 2 nơi cùng token vẫn dễ loạn.
- **Gói Free của Render tự "ngủ" sau 15 phút không traffic** (Telegram không ping định kỳ nên không tự giữ thức được):
  - Bot có sẵn **keep-alive**: tự ping URL công khai của chính nó mỗi `KEEP_ALIVE_MINUTES` phút (mặc định 10, đặt `0` để tắt) → không cần dịch vụ ngoài. *Lưu ý: chạy 24/7 dùng gần hết 750 giờ/tháng của gói free — hợp lý nếu chỉ có 1 service.*
  - Hoặc dùng [UptimeRobot](https://uptimerobot.com) ping `https://<tên-app>.onrender.com/api/stats` mỗi 5 phút (bền hơn: đánh thức cả khi service crash/redeploy).
  - Không bật gì thì tin nhắn vẫn đánh thức bot, nhưng **tin đầu sau khi ngủ trễ ~30-60s** (cold start; Telegram tự gửi lại nên không mất).
- Ổ đĩa của Render là tạm thời: `stats.json` sẽ reset mỗi lần deploy/restart.
- Cần `cookies.txt`? **Đừng commit nó lên repo public!** Vào Render → Environment → **Secret Files** → tạo file tên `cookies.txt` với nội dung cookies, mount path để mặc định.
- Dashboard trên Render là công khai (ai có link đều xem được thống kê). Muốn tắt: đặt biến `DASHBOARD_PORT=0` — nhưng khi đó Render Web Service sẽ fail port scan, hãy chuyển service sang loại **Background Worker** (mất phí) hoặc chấp nhận dashboard công khai.

## 💡 Mẹo tái sử dụng: lách chặn IP datacenter bằng Cloudflare WARP

Áp dụng cho **bất kỳ dự án nào** bị dịch vụ đích chặn IP của cloud host (YouTube, một số API, trang có geo/anti-bot theo IP). Ý tưởng: chạy **Cloudflare WARP ở chế độ proxy** trong container — traffic thoát ra bằng IP Cloudflare (thường không bị blacklist) thay vì IP datacenter.

**Khi nào dùng:** đang chạy trên Render/Koyeb/Fly/VPS và gặp lỗi kiểu "sign in to confirm you're not a bot" / bị chặn theo IP, mà máy cá nhân (IP dân cư) lại không bị.

**1. Dockerfile — cài WARP (base Debian bookworm):**
```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | gpg --yes --dearmor -o /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ bookworm main" > /etc/apt/sources.list.d/cloudflare-client.list \
    && apt-get update && apt-get install -y --no-install-recommends cloudflare-warp \
    && rm -rf /var/lib/apt/lists/*
```

**2. entrypoint.sh — bật WARP proxy (SOCKS5 `127.0.0.1:40000`) rồi chạy app:**
```sh
warp-svc &                                        # daemon
sleep 3
warp-cli --accept-tos registration new            # đăng ký (không cần tài khoản)
warp-cli --accept-tos mode proxy                  # chế độ proxy — KHÔNG cần TUN/NET_ADMIN
warp-cli --accept-tos connect
# đợi tới khi status có "Connected" rồi mới export
export PROXY_URL="socks5://127.0.0.1:40000"
exec python your_app.py
```
> Chế độ **proxy** (không phải VPN full-tunnel) là chìa khoá: không đụng network stack nên chạy được trong container hạn chế quyền như Render/Koyeb. Cần `PySocks` để client hỗ trợ `socks5://`.

**3. Trong code — chỉ định tuyến traffic cần thiết qua proxy:**
```python
proxy = os.getenv("PROXY_URL")
if proxy and is_target(url):      # chỉ áp cho host bị chặn
    opts["proxy"] = proxy         # các host khác đi thẳng
```

**Nguyên tắc an toàn (rút ra từ dự án này):**
- **Chỉ định tuyến host thực sự bị chặn qua proxy** — phần còn lại đi thẳng, để WARP hỏng không kéo sập cả hệ thống.
- **Fail-safe:** WARP không kết nối được thì app vẫn chạy (chỉ host kia bị chặn), đừng để crash.
- **Công tắc env** (`USE_WARP=0`) để tắt tức thì không cần sửa code/revert.
- **Kiểm chứng bằng** `curl --socks5-hostname 127.0.0.1:40000 https://www.cloudflare.com/cdn-cgi/trace` → phải thấy `warp=on` và IP thoát thuộc dải Cloudflare.
- ⚠️ Không đảm bảo bền — dịch vụ đích có thể chặn dải Cloudflare bất cứ lúc nào. Dự phòng: cookies hoặc IP dân cư (chạy máy nhà / residential proxy trả phí).

## 👤 Tác giả & Ủng hộ
- **Phát triển bởi**: Toandn
- **Ủng hộ**: BIDV 1222172532 DINH NGOC TOAN
