import yt_dlp
import os
import logging

logger = logging.getLogger(__name__)

def download_video(url, download_dir='downloads'):
    """
    Downloads a video from the given URL using yt-dlp.
    Returns the path to the downloaded file.
    """
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    # yt-dlp options
    # Ưu tiên mp4 và chất lượng tốt nhất. 
    # Đối với TikTok/Douyin, yt-dlp sẽ cố gắng lấy bản không watermark (nwm) nếu có thể.
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{download_dir}/%(title).50s_%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'tiktok': {
                'app_log_id': [''],
                'device_id': [''],
                'ms_token': [''],
            },
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Sometimes the extension changes during download (e.g. merging)
            # yt-dlp prepare_filename might not always reflect the final merged file extension if it changes
            # But usually it's correct. Let's verify existence.
            if not os.path.exists(filename):
                # Check for same name with different extension just in case
                base = os.path.splitext(filename)[0]
                for f in os.listdir(download_dir):
                    if f.startswith(os.path.basename(base)):
                        filename = os.path.join(download_dir, f)
                        break
            
            return filename, info.get('title', 'Video')
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        raise e

def get_best_format_info(url):
    """
    Lấy thông tin dung lượng của bản tốt nhất.
    """
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            size = info.get('filesize') or info.get('filesize_approx') or 0
            return size / (1024 * 1024), info.get('title', 'Video')
    except Exception as e:
        logger.error(f"Error checking best format size: {e}")
        return 0, "Video"

def get_available_formats(url):
# ... (rest remains same)
