import os
import re
import time
import logging
import asyncio
import secrets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from downloader import get_video_info, download_video, download_specific_format, download_audio, HAS_FFMPEG
import stats
from dashboard import start_dashboard

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_PATH", "downloads")

TELEGRAM_LIMIT_MB = 50      # Giới hạn gửi file của Telegram Bot API
MAX_CONCURRENT_DOWNLOADS = 3
URL_REGISTRY_MAX = 500      # Số link tối đa giữ trong bộ nhớ chờ người dùng bấm nút

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# httpx log mỗi request kèm cả token bot trong URL — hạ mức để không lộ token
logging.getLogger("httpx").setLevel(logging.WARNING)

download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


def friendly_error(url, error):
    """Dịch lỗi yt-dlp thành hướng dẫn dễ hiểu cho người dùng."""
    err = re.sub(r'\x1b\[[0-9;]*m', '', str(error))  # bỏ mã màu ANSI của yt-dlp
    low = err.lower()

    if 'facebook.com/stories' in url:
        return ("⚠️ Facebook Stories hiện chưa được yt-dlp hỗ trợ (kể cả khi đã có cookies đăng nhập).\n"
                "Bạn hãy gửi link video/reel/bài đăng thông thường.")
    if 'douyin' in url.lower() and ('cookie' in low or 'login' in low):
        return ("⚠️ Douyin chặn cả hai đường tải của bot — video có thể riêng tư, đã bị xóa, "
                "hoặc là album ảnh.\nCó thể thử: mở douyin.com trên trình duyệt (không cần đăng nhập), "
                "xuất cookies.txt và thêm vào bot.")
    if 'login' in low or 'cookie' in low or 'logged' in low or 'private' in low:
        if os.path.exists('cookies.txt'):
            return ("🔒 Nội dung yêu cầu đăng nhập nhưng cookies hiện tại không truy cập được.\n"
                    "Cookies có thể đã hết hạn — hãy xuất lại file cookies.txt mới từ trình duyệt.")
        return ("🔒 Nội dung này yêu cầu đăng nhập.\n"
                "Dùng tiện ích \"Get cookies.txt LOCALLY\" trên trình duyệt, xuất cookies của trang đó "
                "và lưu thành file cookies.txt vào thư mục bot (không cần khởi động lại bot).")
    if 'entity too large' in low or 'too large' in low:
        return f"😢 File vượt giới hạn {TELEGRAM_LIMIT_MB}MB của Telegram Bot nên gửi thất bại. Hãy thử chất lượng thấp hơn."
    if 'unsupported url' in low:
        return "⚠️ Trang này chưa được yt-dlp hỗ trợ tải."
    if 'unavailable' in low or 'removed' in low or 'does not exist' in low:
        return "⚠️ Video không tồn tại, đã bị xóa hoặc bị giới hạn người xem."
    if 'not available in your country' in low:
        return "🌍 Video bị chặn theo khu vực địa lý."
    return f"❌ Lỗi: {err[:200]}"


def remember_url(context, url, job):
    """
    Lưu URL (kèm job của tin nhắn gốc) vào bot_data và trả về token ngắn.
    callback_data của Telegram giới hạn 64 byte nên không nhét URL trực tiếp được.
    """
    urls = context.bot_data.setdefault('urls', {})
    while len(urls) >= URL_REGISTRY_MAX:
        urls.pop(next(iter(urls)))
    token = secrets.token_hex(4)
    urls[token] = {'url': url, 'job': job}
    return token


async def finish_job_item(job, success):
    """
    Đánh dấu một link trong tin nhắn gốc đã xử lý xong.
    Khi tất cả link đều gửi thành công thì xóa tin nhắn link gốc
    (kèm preview) để chat gọn gàng — link đã được giữ trong caption video.
    """
    job['remaining'] -= 1
    if not success:
        job['failed'] += 1
    if job['remaining'] <= 0 and job['failed'] == 0:
        try:
            await job['message'].delete()
        except Exception:
            pass  # trong nhóm bot cần quyền "Delete messages" — không có thì bỏ qua


def _render_bar(pct, width=12):
    """Vẽ thanh tiến trình dạng ▰▰▰▰▱▱▱▱."""
    filled = round(pct / 100 * width)
    return '▰' * filled + '▱' * (width - filled)


def start_animation(bot, chat_id, status_msg, text, action=None):
    """
    Quay spinner đồng hồ trên status_msg (kèm chat action native của Telegram
    nếu có) cho tới khi gọi hàm stop() được trả về.
    """
    frames = '🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚🕛'
    stop_event = asyncio.Event()

    async def _loop():
        i = 0
        while not stop_event.is_set():
            if action and i % 2 == 0:
                try:
                    await bot.send_chat_action(chat_id=chat_id, action=action)
                except Exception:
                    pass
            try:
                await status_msg.edit_text(f"{frames[i % len(frames)]} {text}")
            except Exception:
                pass  # flood limit hoặc nội dung không đổi — bỏ qua
            i += 1
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(_loop())

    async def stop():
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    return stop


def make_progress_hook(loop, status_msg, title):
    """Tạo hook cho yt-dlp: cập nhật thanh tiến trình lên status_msg, tối đa 3 giây/lần."""
    state = {'last': 0.0}

    async def _edit(text):
        try:
            await status_msg.edit_text(text)
        except Exception:
            pass  # "Message is not modified" hoặc flood limit — bỏ qua

    def hook(d):
        if d.get('status') != 'downloading':
            return
        now = time.monotonic()
        if now - state['last'] < 3:
            return
        state['last'] = now
        done = d.get('downloaded_bytes') or 0
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        if total:
            pct = done / total * 100
            text = (f"⬇️ Đang tải: {title}\n"
                    f"{_render_bar(pct)} {pct:.0f}% · {done / 1048576:.1f}/{total / 1048576:.1f}MB")
        else:
            text = f"⬇️ Đang tải: {title}\n📥 {done / 1048576:.1f}MB đã tải..."
        # Hook chạy trong thread tải, phải đẩy việc sửa tin nhắn về event loop
        asyncio.run_coroutine_threadsafe(_edit(text), loop)

    return hook


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Chào mừng bạn đến với Bot tải Video!\n"
        "Hãy gửi link video cho tôi. Nếu bản tốt nhất dưới 50MB tôi sẽ tải ngay, nếu không tôi sẽ cho bạn chọn chất lượng."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Gửi link video trực tiếp vào khung chat (nhiều link thì mỗi link một dòng).\n"
        "Lưu ý: Telegram Bot giới hạn gửi file tối đa 50MB."
    )


async def author_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot được phát triển bởi Toandn\n"
        "Ủng hộ tác giả: BIDV 1222172532 DINH NGOC TOAN\n"
        "Chúc bạn sử dụng bot vui vẻ!"
    )


async def post_init(application):
    commands = [
        BotCommand("start", "Khởi động bot"),
        BotCommand("help", "Hướng dẫn sử dụng"),
        BotCommand("author", "Thông tin tác giả")
    ]
    await application.bot.set_my_commands(commands)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if not text:
        return

    # Nhặt URL ở bất kỳ đâu trong tin nhắn — dán nguyên share text của
    # TikTok/Douyin (lẫn chữ tàu, emoji...) bot vẫn tự tìm ra link
    urls = [u.rstrip('.,;:!?)]}>\'"') for u in re.findall(r'https?://\S+', text)]
    urls = list(dict.fromkeys(urls))  # bỏ trùng, giữ thứ tự

    if not urls:
        await update.message.reply_text("Không thấy link nào trong tin nhắn. Hãy gửi link video (dán nguyên đoạn share cũng được).")
        return

    # Job theo dõi tin nhắn gốc: khi mọi link gửi xong thì xóa tin nhắn link cho gọn chat
    job = {'message': update.message, 'remaining': len(urls), 'failed': 0}

    # Các link chạy song song, số lượt tải đồng thời do semaphore khống chế
    await asyncio.gather(*(process_url(update, context, url, job) for url in urls), return_exceptions=True)


async def process_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, job: dict):
    status_msg = await update.message.reply_text(f"🔍 Đang kiểm tra: {url}")
    stop_anim = start_animation(context.bot, update.message.chat_id, status_msg,
                                f"Đang kiểm tra: {url}", ChatAction.TYPING)

    try:
        best_size, title, formats = await asyncio.to_thread(get_video_info, url)
    except Exception as e:
        logger.error(f"Error checking {url}: {e}")
        await stop_anim()
        await status_msg.edit_text(f"Không tải được: {url}\n\n{friendly_error(url, e)}")
        stats.record(url, ok=False)
        await finish_job_item(job, False)
        return
    finally:
        await stop_anim()

    # Biết trước quá nặng mà lại không có menu chất lượng để lùi → báo luôn, khỏi tải
    if best_size > TELEGRAM_LIMIT_MB and not formats:
        msg = (f"😢 {title}\nVideo nặng ~{best_size:.0f}MB, vượt giới hạn {TELEGRAM_LIMIT_MB}MB "
               f"của Telegram Bot — không gửi được.")
        if HAS_FFMPEG:
            # Video không gửi được, nhưng bản MP3 nhẹ hơn nhiều → mời tải nhạc
            token = remember_url(context, url, job)
            await status_msg.edit_text(
                msg + "\nBạn có thể tải riêng phần nhạc MP3:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "🎵 Tải nhạc MP3", callback_data=f"dl|mp3|{token}")]])
            )
            return  # người dùng bấm nút; job kết thúc khi tải xong/hủy
        await status_msg.edit_text(msg)
        stats.record(url, ok=False, title=title)
        await finish_job_item(job, False)
        return

    # Bản tốt nhất đủ nhỏ (hoặc không có format nào để chọn) → tải luôn
    if 0 < best_size <= TELEGRAM_LIMIT_MB or not formats:
        size_note = f" (~{best_size:.1f}MB)" if best_size else ""
        await status_msg.edit_text(f"⬇️ Đang tải: {title}{size_note}")
        ok = await download_and_send(update.message.chat_id, context, url, status_msg, "best", title)
        await finish_job_item(job, ok)
        return

    # Quá lớn hoặc không rõ dung lượng → cho chọn chất lượng
    token = remember_url(context, url, job)
    keyboard = []
    for fmt in formats:
        size_str = f" (~{fmt['filesize'] / 1048576:.1f}MB)" if fmt['filesize'] else ""
        keyboard.append([InlineKeyboardButton(
            f"{fmt['height']}p{size_str}",
            callback_data=f"dl|{fmt['format_id']}|{token}"
        )])
    keyboard.append([InlineKeyboardButton("🎯 Vẫn tải bản tốt nhất", callback_data=f"dl|best|{token}")])
    if HAS_FFMPEG:
        keyboard.append([InlineKeyboardButton("🎵 Tải nhạc MP3", callback_data=f"dl|mp3|{token}")])

    size_note = f"Bản gốc ~{best_size:.1f}MB, vượt giới hạn 50MB." if best_size else "Không rõ dung lượng bản gốc."
    await status_msg.edit_text(
        f"🎬 {title}\n{size_note} Vui lòng chọn chất lượng:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("|")
    if parts[0] != "dl" or len(parts) != 3:
        return

    format_id, token = parts[1], parts[2]
    entry = context.bot_data.get('urls', {}).get(token)
    if not entry:
        await query.edit_message_text("⚠️ Phiên đã hết hạn (bot vừa khởi động lại). Vui lòng gửi lại link.")
        return

    await query.edit_message_text("⏳ Đang chuẩn bị tải video bạn đã chọn...")
    ok = await download_and_send(query.message.chat_id, context, entry['url'], query.message, format_id, "video")
    await finish_job_item(entry['job'], ok)


async def download_and_send(chat_id, context, url, status_msg, format_id, title="video"):
    """Tải rồi gửi file; trả về True nếu gửi thành công."""
    file_path = None
    try:
        async with download_semaphore:
            hook = make_progress_hook(asyncio.get_running_loop(), status_msg, title)
            if format_id == "best":
                file_path, title = await asyncio.to_thread(download_video, url, DOWNLOAD_DIR, hook)
            elif format_id == "mp3":
                file_path, title = await asyncio.to_thread(download_audio, url, DOWNLOAD_DIR, hook)
            else:
                file_path, title = await asyncio.to_thread(download_specific_format, url, format_id, DOWNLOAD_DIR, hook)

        file_size = os.path.getsize(file_path) / (1024 * 1024)
        if file_size > TELEGRAM_LIMIT_MB:
            # 50MB là giới hạn cứng của Telegram Bot API — cố gửi chỉ tốn
            # thời gian upload rồi nhận "Request Entity Too Large"
            await status_msg.edit_text(
                f"😢 {title}\nFile nặng {file_size:.1f}MB, vượt giới hạn {TELEGRAM_LIMIT_MB}MB "
                f"của Telegram Bot nên không gửi được. Hãy thử chọn chất lượng thấp hơn (nếu có menu)."
            )
            stats.record(url, ok=False, title=title)
            return False

        # Tin nhắn link gốc sẽ bị xóa nên giữ lại link trong caption
        caption = f"{title[:700]}\n\n🔗 {url}"

        # Kiểm tra định dạng file để gửi đúng kiểu (và chọn chat action tương ứng)
        ext = os.path.splitext(file_path)[1].lower()
        is_video = ext in ['.mp4', '.mkv', '.mov', '.webm']
        is_image = ext in ['.jpg', '.jpeg', '.png', '.webp']
        is_audio = ext in ['.mp3', '.m4a', '.opus', '.ogg', '.wav', '.flac']
        action = ChatAction.UPLOAD_VIDEO if is_video else (
            ChatAction.UPLOAD_PHOTO if is_image else (
                ChatAction.UPLOAD_VOICE if is_audio else ChatAction.UPLOAD_DOCUMENT))

        stop_anim = start_animation(context.bot, chat_id, status_msg,
                                    f"Đang gửi: {title} ({file_size:.1f}MB)", action)
        try:
            with open(file_path, 'rb') as f:
                if is_video:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=f,
                        caption=caption,
                        supports_streaming=True
                    )
                elif is_image:
                    await context.bot.send_photo(chat_id=chat_id, photo=f, caption=caption)
                elif is_audio:
                    await context.bot.send_audio(chat_id=chat_id, audio=f, caption=caption, title=title[:60])
                else:
                    await context.bot.send_document(chat_id=chat_id, document=f, caption=caption)
        finally:
            await stop_anim()

        await status_msg.delete()
        stats.record(url, ok=True, size_mb=file_size, title=title,
                     quality='tốt nhất' if format_id == 'best' else format_id)
        return True

    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            await status_msg.edit_text(friendly_error(url, e))
        except Exception:
            # edit thất bại (pool nghẽn, message bị xóa...) — không được nuốt
            # luôn cả việc báo lỗi, thử gửi tin nhắn mới
            try:
                await context.bot.send_message(chat_id=chat_id, text=friendly_error(url, e))
            except Exception:
                logger.exception("Không báo được lỗi cho người dùng")
        stats.record(url, ok=False, title=title if title != 'video' else '')
        return False
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


async def error_handler(update, context):
    """Nuốt các lỗi nền ồn ào (nhất là Conflict khi có 2 instance polling)."""
    from telegram.error import Conflict
    err = context.error
    if isinstance(err, Conflict):
        logger.warning("Conflict: có instance bot khác đang chạy. Chỉ nên chạy 1 bot cho mỗi token.")
        return
    logger.error("Lỗi không xử lý được", exc_info=err)


if __name__ == '__main__':
    if not TOKEN:
        print("Lỗi: chưa cấu hình TELEGRAM_BOT_TOKEN trong file .env!")
        exit(1)

    builder = (
        ApplicationBuilder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(60)
        .write_timeout(300)  # Upload file lớn cần timeout dài hơn mặc định 20s
        # Mặc định PTB chỉ có 1 connection + pool_timeout 1s — upload dài chiếm
        # connection làm animation/edit_text văng PoolTimeout và treo trạng thái
        .connection_pool_size(16)
        .pool_timeout(30)
    )
    # PTB >= 20.7 tách riêng timeout cho media upload
    if hasattr(builder, 'media_write_timeout'):
        builder = builder.media_write_timeout(300)

    # Trên Render/cloud: biến PORT được cấp sẵn và service phải bind 0.0.0.0
    # để qua vòng port scan. Chạy local thì giữ 127.0.0.1 cho riêng tư.
    cloud_port = os.getenv("PORT")
    dashboard_port = int(cloud_port or os.getenv("DASHBOARD_PORT", "8350"))
    dashboard_host = "0.0.0.0" if cloud_port else os.getenv("DASHBOARD_HOST", "127.0.0.1")
    if dashboard_port:
        dashboard_url = start_dashboard(dashboard_port, dashboard_host)
        if dashboard_url:
            print(f"📊 Dashboard: {dashboard_url}", flush=True)

    app = builder.post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("author", author_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_error_handler(error_handler)

    import yt_dlp
    print(f"Bot đang chạy (Hybrid Mode)... [yt-dlp {yt_dlp.version.__version__}]", flush=True)
    app.run_polling()
