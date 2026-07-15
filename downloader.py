import yt_dlp
import os
import re
import json
import shutil
import logging

import httpx  # có sẵn theo python-telegram-bot

logger = logging.getLogger(__name__)

HAS_FFMPEG = bool(shutil.which('ffmpeg'))


def _cookies_path():
    """Tìm cookies.txt: biến COOKIES_FILE > thư mục bot > Render Secret Files."""
    for p in (os.getenv('COOKIES_FILE'), 'cookies.txt', '/etc/secrets/cookies.txt'):
        if p and os.path.exists(p):
            return p
    return None

if HAS_FFMPEG:
    # Không giới hạn ext=mp4 để lấy được cả 4K/VP9/AV1 (chỉ có bản webm);
    # ưu tiên audio m4a để merge vào mp4 mượt nhất, không có thì lấy audio tốt nhất
    BEST_FORMAT = 'bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
else:
    # Thiếu FFmpeg thì không merge được video+audio rời — dùng bản single-file
    # tốt nhất (YouTube thường chỉ tới 720p). Cài FFmpeg để có chất lượng cao nhất.
    BEST_FORMAT = 'best'
    logger.warning("Không tìm thấy FFmpeg — chạy chế độ hạn chế (tối đa ~720p, không merge). "
                   "Hãy cài FFmpeg hoặc deploy bằng Dockerfile kèm sẵn.")


def _build_opts(extra=None):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'noplaylist': True,
    }
    cookies = _cookies_path()
    if cookies:
        opts['cookiefile'] = cookies
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
    try:
        with yt_dlp.YoutubeDL(_build_opts({'format': BEST_FORMAT})) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        if _douyin_blocked(url, e):
            # Plan B: lấy info từ trang share; formats rỗng -> bot tải thẳng bản này
            share = _douyin_share_info(url)
            return _douyin_share_size_mb(share['url']), share['title'], []
        raise

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
    }
    if HAS_FFMPEG:
        extra['merge_output_format'] = 'mp4'
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


def _extract_audio(target_url, download_dir, progress_hook=None, outtmpl=None, title_hint=None):
    """Tải audio tốt nhất rồi chuyển sang MP3 192kbps (cần FFmpeg)."""
    os.makedirs(download_dir, exist_ok=True)
    extra = {
        'format': 'bestaudio/best',
        'outtmpl': outtmpl or f'{download_dir}/%(title).50s_%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    if progress_hook:
        extra['progress_hooks'] = [progress_hook]

    with yt_dlp.YoutubeDL(_build_opts(extra)) as ydl:
        info = ydl.extract_info(target_url, download=True)
        downloads = info.get('requested_downloads') or []
        if downloads and downloads[0].get('filepath'):
            filename = downloads[0]['filepath']
        else:
            filename = ydl.prepare_filename(info)
        # sau postprocessor đuôi đã đổi thành .mp3
        mp3 = os.path.splitext(filename)[0] + '.mp3'
        if os.path.exists(mp3):
            filename = mp3
        return filename, (title_hint or info.get('title', 'Audio'))


def download_audio(url, download_dir='downloads', progress_hook=None):
    """Tải file MP3 (chỉ dùng được khi có FFmpeg)."""
    if not HAS_FFMPEG:
        raise RuntimeError('Cần FFmpeg để tạo file MP3')
    try:
        return _extract_audio(url, download_dir, progress_hook)
    except yt_dlp.utils.DownloadError as e:
        if _douyin_blocked(url, e):
            # Douyin chặn yt-dlp → lấy link mp4 từ trang share rồi rút audio
            logger.info(f"Douyin chặn yt-dlp (audio), chuyển sang trang share: {url}")
            share = _douyin_share_info(url)
            return _extract_audio(
                share['url'], download_dir, progress_hook,
                outtmpl=f'{download_dir}/douyin_{share["id"]}.%(ext)s',
                title_hint=share['title'])
        raise


# ---------- Plan B cho Douyin ----------
# yt-dlp cần cookie chống-bot (s_v_web_id) mà chỉ trình duyệt thật tạo được.
# May là trang share iesdouyin.com render sẵn server-side, chứa link video
# mà KHÔNG cần cookie — đổi /playwm/ thành /play/ là được bản không watermark.

DOUYIN_UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
             'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1')


def _is_douyin(url):
    return 'douyin.com' in url.lower()


def _douyin_blocked(url, error):
    return _is_douyin(url) and 'cookies' in str(error).lower()


def _find_key(obj, key):
    """Tìm đệ quy giá trị đầu tiên của key trong JSON lồng nhau."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_key(v, key)
            if found is not None:
                return found
    return None


def _douyin_share_info(url):
    """Lấy tiêu đề + link mp4 không watermark từ trang share SSR của Douyin."""
    resp = httpx.get(url, headers={'User-Agent': DOUYIN_UA}, follow_redirects=True, timeout=20)
    m = re.search(r'window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>', resp.text, re.DOTALL)
    if not m:
        raise ValueError('Không tìm thấy dữ liệu video trong trang share Douyin')
    data = json.loads(m.group(1))
    item = _find_key(data, 'item_list') or _find_key(data, 'aweme_detail')
    if isinstance(item, list):
        item = item[0] if item else None
    if not item:
        raise ValueError('Trang share Douyin không có video (album ảnh hoặc video riêng tư?)')
    urls = (((item.get('video') or {}).get('play_addr') or {}).get('url_list')) or []
    if not urls:
        raise ValueError('Không lấy được link video từ trang share Douyin')
    return {
        'title': (item.get('desc') or 'Video Douyin').strip(),
        'url': urls[0].replace('/playwm/', '/play/'),
        'id': str(item.get('aweme_id') or 'video'),
    }


def _douyin_share_size_mb(play_url):
    """Hỏi dung lượng file qua HEAD request để bot chặn sớm video quá 50MB."""
    try:
        head = httpx.head(play_url, headers={'User-Agent': DOUYIN_UA},
                          follow_redirects=True, timeout=15)
        return int(head.headers.get('content-length') or 0) / (1024 * 1024)
    except Exception:
        return 0


def _download_douyin_share(url, download_dir, progress_hook=None):
    info = _douyin_share_info(url)
    os.makedirs(download_dir, exist_ok=True)
    extra = {
        'format': 'best',
        'outtmpl': f'{download_dir}/douyin_{info["id"]}.%(ext)s',
        'http_headers': {'User-Agent': DOUYIN_UA},
    }
    if progress_hook:
        extra['progress_hooks'] = [progress_hook]
    with yt_dlp.YoutubeDL(_build_opts(extra)) as ydl:
        result = ydl.extract_info(info['url'], download=True)
        downloads = result.get('requested_downloads') or []
        if downloads and downloads[0].get('filepath'):
            filename = downloads[0]['filepath']
        else:
            filename = ydl.prepare_filename(result)
    return filename, info['title']
# ---------- hết Plan B Douyin ----------


def download_video(url, download_dir='downloads', progress_hook=None):
    """Tải bản chất lượng tốt nhất."""
    try:
        return _download(url, BEST_FORMAT, download_dir, progress_hook)
    except yt_dlp.utils.DownloadError as e:
        if _douyin_blocked(url, e):
            logger.info(f"Douyin chặn yt-dlp, chuyển sang trang share: {url}")
            return _download_douyin_share(url, download_dir, progress_hook)
        raise


def download_specific_format(url, format_id, download_dir='downloads', progress_hook=None):
    """Tải theo format_id người dùng chọn, tự merge thêm audio tốt nhất."""
    if HAS_FFMPEG:
        return _download(url, f'{format_id}+bestaudio/best', download_dir, progress_hook)
    # Thiếu FFmpeg: format video-only sẽ không có tiếng — ưu tiên bản có sẵn audio
    return _download(url, f'{format_id}[acodec!=none]/best', download_dir, progress_hook)
