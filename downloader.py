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
            
            if not os.path.exists(filename):
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
    """
    Trả về danh sách các độ phân giải có sẵn (mp4).
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    formats = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            for f in info.get('formats', []):
                if f.get('vcodec') != 'none' and f.get('ext') == 'mp4':
                    res = f.get('height')
                    if res and res not in [fmt['height'] for fmt in formats]:
                        formats.append({
                            'height': res,
                            'format_id': f.get('format_id'),
                            'filesize': f.get('filesize') or f.get('filesize_approx')
                        })
            formats.sort(key=lambda x: x['height'], reverse=True)
            return formats[:5], info.get('title', 'Video')
    except Exception as e:
        logger.error(f"Error getting formats: {e}")
        return [], "Video"

def download_specific_format(url, format_id, download_dir='downloads'):
    """
    Tải video với format_id cụ thể.
    """
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    ydl_opts = {
        'format': f'{format_id}+bestaudio/best',
        'outtmpl': f'{download_dir}/%(title).50s_%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
    }
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # Verify merged extension
        if not os.path.exists(filename):
             base = os.path.splitext(filename)[0]
             for f in os.listdir(download_dir):
                 if f.startswith(os.path.basename(base)):
                     filename = os.path.join(download_dir, f)
                     break
        return filename, info.get('title', 'Video')
