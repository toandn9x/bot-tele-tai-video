import yt_dlp
import os
import logging

logger = logging.getLogger(__name__)

COOKIES_FILE = 'cookies.txt'
# Không giới hạn ext=mp4 để lấy được cả 4K/VP9/AV1 (chỉ có bản webm);
# ưu tiên audio m4a để merge vào mp4 mượt nhất, không có thì lấy audio tốt nhất
BEST_FORMAT = 'bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best'


def _build_opts(extra=None):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'noplaylist': True,
    }
    if os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
    if extra:
        opts.update(extra)
    return opts


def _selected_size_mb(info):
    """Dung lượng bản đã chọn; khi merge video+audio phải cộng cả hai phần."""
    requested = info.get('requested_formats')
    if requested:
        size = sum(f.get('filesize') or f.get('filesize_approx') or 0 for f in requested)
    else:
        size = info.get('filesize') or info.get('filesize_approx') or 0
    return size / (1024 * 1024)


def get_video_info(url):
    """
    Gọi extract_info đúng một lần cho cả dung lượng, tiêu đề và danh sách format.
    Trả về (best_size_mb, title, formats) — best_size_mb = 0 nếu không rõ.
    """
    with yt_dlp.YoutubeDL(_build_opts({'format': BEST_FORMAT})) as ydl:
        info = ydl.extract_info(url, download=False)

    by_height = {}
    for f in info.get('formats', []):
        height = f.get('height')
        if f.get('vcodec') == 'none' or not height:
            continue
        # Mỗi độ phân giải lấy một format, ưu tiên mp4
        if height not in by_height or (f.get('ext') == 'mp4' and by_height[height]['ext'] != 'mp4'):
            by_height[height] = {
                'height': height,
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'filesize': f.get('filesize') or f.get('filesize_approx'),
            }
    formats = sorted(by_height.values(), key=lambda x: x['height'], reverse=True)[:5]

    return _selected_size_mb(info), info.get('title', 'Video'), formats


def _download(url, format_spec, download_dir, progress_hook=None):
    os.makedirs(download_dir, exist_ok=True)
    extra = {
        'format': format_spec,
        'outtmpl': f'{download_dir}/%(title).50s_%(id)s.%(ext)s',
        'merge_output_format': 'mp4',
    }
    if progress_hook:
        extra['progress_hooks'] = [progress_hook]

    with yt_dlp.YoutubeDL(_build_opts(extra)) as ydl:
        info = ydl.extract_info(url, download=True)
        # yt-dlp trả sẵn đường dẫn cuối cùng (sau khi merge/đổi đuôi)
        downloads = info.get('requested_downloads') or []
        if downloads and downloads[0].get('filepath'):
            filename = downloads[0]['filepath']
        else:
            filename = ydl.prepare_filename(info)
        return filename, info.get('title', 'Video')


def download_video(url, download_dir='downloads', progress_hook=None):
    """Tải bản chất lượng tốt nhất."""
    return _download(url, BEST_FORMAT, download_dir, progress_hook)


def download_specific_format(url, format_id, download_dir='downloads', progress_hook=None):
    """Tải theo format_id người dùng chọn, tự merge thêm audio tốt nhất."""
    return _download(url, f'{format_id}+bestaudio/best', download_dir, progress_hook)
