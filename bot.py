import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from dotenv import load_dotenv
from downloader import download_video, get_available_formats, download_specific_format, get_best_format_info

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
        "Hãy gửi link video cho tôi. Nếu bản tốt nhất dưới 50MB tôi sẽ tải ngay, nếu không tôi sẽ cho bạn chọn chất lượng."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Gửi link video trực tiếp vào khung chat.\n"
        "Lưu ý: Telegram Bot giới hạn gửi file tối đa 50MB."
    )

async def author_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot được phát triển bởi Toandn\n"
        "Ủng hộ tác giả: BIDV 1222172532 DINH NGOC TOAN\n"
        "Chúc bạn sử dụng bot vui vẻ!"
    )

async def post_init(application):
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
        await update.message.reply_text(" Xin hãy gửi một đường link video hợp lệ.")
        return

    status_msg = await update.message.reply_text(" Đang kiểm tra video...")
    
    try:
        best_size, title = await asyncio.to_thread(get_best_format_info, url)
        
        # Nếu video nhỏ hơn 50MB, tải ngay bản tốt nhất
        if 0 < best_size <= 50:
            await status_msg.edit_text(f" Video hợp lệ (~{best_size:.1f}MB). Đang tải bản tốt nhất...")
            await download_and_send(update, context, url, status_msg, "best")
        else:
            # Nếu > 50MB hoặc không rõ dung lượng, cho chọn chất lượng
            await status_msg.edit_text(" Bản tốt nhất > 50MB. Vui lòng chọn chất lượng thấp hơn để tải lên Telegram:")
            formats, title = await asyncio.to_thread(get_available_formats, url)
            
            if not formats:
                await status_msg.edit_text(" Không tìm thấy bản nhẹ hơn. Đang thử tải bản tốt nhất...")
                await download_and_send(update, context, url, status_msg, "best")
                return

            keyboard = []
            for fmt in formats:
                size_str = f" (~{fmt['filesize']/(1024*1024):.1f}MB)" if fmt['filesize'] else ""
                btn_text = f"{fmt['height']}p{size_str}"
                callback_data = f"dl|{fmt['format_id']}|{url}"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=callback_data)])
            
            keyboard.append([InlineKeyboardButton(" Vẫn tải bản tốt nhất", callback_data=f"dl|best|{url}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await status_msg.edit_text(f" Video: {title}\nBản gốc (~{best_size:.1f}MB) quá lớn.", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await status_msg.edit_text(" Có lỗi xảy ra khi kiểm tra video.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")
    if data[0] == "dl":
        await query.edit_message_text(text=" Đang tải video bạn đã chọn...")
        await download_and_send(query, context, data[2], query.message, data[1])

async def download_and_send(update_or_query, context, url, status_msg, format_id):
    file_path = None
    try:
        if format_id == "best":
            file_path, title = await asyncio.to_thread(download_video, url, DOWNLOAD_DIR)
        else:
            file_path, title = await asyncio.to_thread(download_specific_format, url, format_id, DOWNLOAD_DIR)
        
        await status_msg.edit_text(f" Đang gửi video: {title}")
        
        chat_id = update_or_query.message.chat_id if hasattr(update_or_query, 'message') else update_or_query.chat_id
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        if file_size > 50:
             await context.bot.send_message(chat_id=chat_id, text=f" Cảnh báo: File vẫn nặng {file_size:.1f}MB. Có thể thất bại.")

        with open(file_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=chat_id,
                video=video_file,
                caption=f" {title}\n\nĐã tải xong!",
                supports_streaming=True
            )
        
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(" Lỗi khi tải hoặc gửi video.")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

if __name__ == '__main__':
    if not TOKEN:
        print("Lỗi Token!")
        exit(1)
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("author", author_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("Bot đang chạy (Hybrid Mode)...")
    app.run_polling()
