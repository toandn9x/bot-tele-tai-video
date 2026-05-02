import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from downloader import download_video

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_PATH", "downloads")

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Chào mừng bạn đến với Bot tải Video!\n"
        "Hãy gửi cho tôi link video (YouTube, TikTok, Facebook,...) và tôi sẽ tải bản chất lượng tốt nhất cho bạn."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Gửi link video trực tiếp vào khung chat để bắt đầu tải.\n"
        "Lưu ý: Các video quá lớn (> 50MB) có thể gặp khó khăn khi tải lên Telegram do giới hạn của Bot API."
    )

async def author_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot được phát triển bởi Toandn\n"
        "Ủng hộ tác giả: BIDV 1222172532 DINH NGOC TOAN\n"
        "Chúc bạn sử dụng bot vui vẻ!"
    )

async def post_init(application):
    """Thiết lập menu command tự động khi bot khởi động."""
    from telegram import BotCommand
    commands = [
        BotCommand("start", "Khởi động bot"),
        BotCommand("help", "Hướng dẫn sử dụng"),
        BotCommand("author", "Thông tin tác giả")
    ]
    await application.bot.set_my_commands(commands)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url or not url.startswith("http"):
        await update.message.reply_text(
            " Xin lỗi, tôi chỉ hỗ trợ tải video từ đường link (bắt đầu bằng http).\n"
            "Hãy gửi cho tôi một link video từ YouTube, TikTok, Facebook... nhé!"
        )
        return

    status_msg = await update.message.reply_text(" đang xử lý video... Vui lòng đợi trong giây lát.")
    
    try:
        # Run download in a thread to not block the event loop
        file_path, title = await asyncio.to_thread(download_video, url, DOWNLOAD_DIR)
        
        await status_msg.edit_text(f" Đang tải video lên Telegram: {title}")
        
        # Check file size
        file_size = os.path.getsize(file_path) / (1024 * 1024) # MB
        
        if file_size > 50:
             await update.message.reply_text(
                 f" Cảnh báo: Video này nặng {file_size:.2f}MB. "
                 "Telegram Bot API mặc định giới hạn tải lên 50MB. Đang thử gửi..."
             )

        with open(file_path, 'rb') as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f" {title}\n\nĐã tải xong!",
                supports_streaming=True
            )
        
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error handling message: {e}")
        error_msg = str(e)
        if "Unsupported URL" in error_msg:
            await status_msg.edit_text(" Xin lỗi, link này không được hỗ trợ hoặc không tìm thấy video.")
        elif "Video too large" in error_msg:
            await status_msg.edit_text(" Video quá lớn so với giới hạn của Telegram (50MB).")
        else:
            await status_msg.edit_text(" Có lỗi xảy ra khi xử lý link này. Vui lòng kiểm tra lại link của bạn.")
        
        # Cleanup if file exists but failed to send
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)

if __name__ == '__main__':
    if not TOKEN:
        print("Lỗi: Vui lòng cấu hình TELEGRAM_BOT_TOKEN trong file .env")
        exit(1)

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("author", author_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot đang chạy...")
    app.run_polling()
