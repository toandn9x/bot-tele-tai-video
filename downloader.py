import yt_dlp
import os
import time
import shutil
import logging

import douyin
import tikwm

logger = logging.getLogger(__name__)

HAS_FFMPEG = bool(shutil.which('ffmpeg'))

# TikTok bắt giải JS challenge và đòi giả mạo TLS fingerprint của trình duyệt
# (yt-dlp gọi _download_webpage_handle(..., impersonate=True)). Không có
# curl_cffi thì yt-dlp không có impersonate target nào và TikTok trả về trang
# lạ -> "Unexpected response from webpage request".
try:
    import curl_cffi  # noqa: F401
    HAS_IMPERSONATE = True
except ImportError:
    HAS_IMPERSONATE = False
    logger.warning("Không tìm thấy curl_cffi — TikTok sẽ lỗi 'Unexpected response from "
                   "webpage request'. Cài bằng: pip install curl_cffi")

# TikTok thỉnh thoảng trả trang thiếu dữ liệu dù đã qua challenge — thử lại là được
_TIKTOK_RETRYABLE = (
    'unable to extract universal data',
    'unexpected response from webpage request',
    'unable to extract webpage video data',
)
TIKTOK_TRIES = 3


def _cookies_path():
    """Tìm cookies.txt: biến COOKIES_FILE > thư mục bot > Render Secret Files."""
    for p in (os.getenv('COOKIES_FILE'), 'cookies.txt', '/etc/secrets/cookies.txt'):
        if p and os.path.exists(p):
            return p
    return None


def _proxy_for(url):
    """
    Proxy (nếu có PROXY_URL) CHỈ áp dụng cho YouTube — nơi bị chặn IP datacenter.
    TikTok/Douyin/Facebook đi thẳng, không phụ thuộc proxy nên WARP hỏng cũng
    không ảnh hưởng các nền tảng đang chạy tốt.
    """
    proxy = os.getenv('PROXY_URL')
    if proxy and ('youtube.com' in url.lower() or 'youtu.be' in url.lower()):
        return proxy
    return None


def _is_tiktok(url):
    return 'tiktok.com' in url.lower()


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


# Codec Telegram hay treo/không phát inline được khi send_video
_BAD_VCODEC = ('hev', 'h265', 'av01', 'vp9', 'vp09')


def _no_bad_codec():
    """Chuỗi lọc loại bỏ các codec Telegram không nuốt nổi."""
    return ''.join(f'[vcodec!^={c}]' for c in _BAD_VCODEC)


def _tg_format(max_height=1080):
    """
    Format cho video gửi qua Telegram: ưu tiên H.264 + AAC trong mp4 —
    Telegram phát inline mượt nhất. H.265/AV1/VP9 hay gây lỗi/treo khi send_video.

    Lưu ý: tên codec KHÔNG thống nhất giữa các trang — YouTube báo `avc1`, còn
    TikTok báo `h264`/`h265`. Chỉ khớp mỗi `avc1` thì nhánh TikTok không bao giờ
    trúng, rơi xuống nhánh chót và vớ đúng bản H.265 (đã đo thực tế). Nên phải
    khớp cả hai tên, và nhánh dự phòng phải loại codec xấu một cách tường minh.

    Cap ≤1080p (bản lớn hơn cũng vượt 50MB của bot). Không có FFmpeg thì lấy
    single-file mp4 sẵn.
    """
    safe = _no_bad_codec()
    if not HAS_FFMPEG:
        return (f'best[ext=mp4][vcodec^=avc1][height<={max_height}]/'
                f'best[ext=mp4][vcodec^=h264][height<={max_height}]/'
                f'best[ext=mp4]{safe}[height<={max_height}]/'
                f'best[ext=mp4][height<={max_height}]/best[ext=mp4]/best')
    return (f'bestvideo[vcodec^=avc1][height<={max_height}]+bestaudio[ext=m4a]/'
            f'bestvideo[vcodec^=h264][height<={max_height}]+bestaudio[ext=m4a]/'
            f'best[vcodec^=avc1][height<={max_height}]/'
            f'best[vcodec^=h264][height<={max_height}]/'
            f'best[ext=mp4]{safe}[height<={max_height}]/'
            f'best{safe}[height<={max_height}]/'
            f'best[ext=mp4][height<={max_height}]/best[height<={max_height}]/best')


def _build_opts(extra=None, url=None):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        'noplaylist': True,
    }
    cookies = _cookies_path()
    if cookies:
        opts['cookiefile'] = cookies
    if url:
        proxy = _proxy_for(url)
        if proxy:
            opts['proxy'] = proxy
    if extra:
        opts.update(extra)
    return opts


def _tiktok_retry(func):
    """
    Chạy func, thử lại khi TikTok trả trang thiếu dữ liệu.
    Đo thực tế: gọi dồn dập dễ bị chặn, giãn cách vài giây là qua.
    """
    last_error = None
    for attempt in range(TIKTOK_TRIES):
        try:
            return func()
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            if not any(s in str(e).lower() for s in _TIKTOK_RETRYABLE):
                raise
            if attempt < TIKTOK_TRIES - 1:
                delay = 2 * (attempt + 1)
                logger.info(f"TikTok trả trang thiếu dữ liệu, thử lại sau {delay}s "
                            f"(lần {attempt + 2}/{TIKTOK_TRIES})")
                time.sleep(delay)
    raise last_error


def _tiktok_fallback(primary, fallback):
    """
    Chạy đường chính (yt-dlp); hỏng thì thử TikWM.
    TikWM tải hộ bằng hạ tầng của họ nên cứu được ca IP máy chủ bị TikTok chặn.
    TikWM cũng hỏng thì ném lại lỗi GỐC của yt-dlp (thông tin hữu ích hơn).
    """
    try:
        return _tiktok_retry(primary)
    except Exception as original:
        if not tikwm.enabled():
            raise
        logger.info(f"yt-dlp thất bại với TikTok, chuyển sang TikWM: {str(original)[:120]}")
        try:
            return fallback()
        except Exception as e:
            logger.warning(f"TikWM cũng thất bại: {str(e)[:120]}")
            raise original


def _selected_size_mb(info):
    """Dung lượng bản đã chọn; khi merge video+audio phải cộng cả hai phần."""
    requested = info.get('requested_formats')
    if requested:
        size = sum(f.get('filesize') or f.get('filesize_approx') or 0 for f in requested)
    else:
        size = info.get('filesize') or info.get('filesize_approx') or 0
    return size / (1024 * 1024)


def _info_via_ytdlp(url):
    with yt_dlp.YoutubeDL(_build_opts({'format': BEST_FORMAT}, url=url)) as ydl:
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


def get_video_info(url):
    """
    Gọi extract_info đúng một lần cho cả dung lượng, tiêu đề và danh sách format.
    Trả về (best_size_mb, title, formats) — best_size_mb = 0 nếu không rõ.
    """
    if douyin.is_douyin(url):
        return douyin.video_info(url)
    if _is_tiktok(url):
        return _tiktok_fallback(lambda: _info_via_ytdlp(url),
                                lambda: tikwm.video_info(url))
    return _info_via_ytdlp(url)


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

    with yt_dlp.YoutubeDL(_build_opts(extra, url=url)) as ydl:
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

    with yt_dlp.YoutubeDL(_build_opts(extra, url=target_url)) as ydl:
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
    if douyin.is_douyin(url):
        return douyin.download_audio(url, download_dir, progress_hook)
    if _is_tiktok(url):
        return _tiktok_fallback(
            lambda: _extract_audio(url, download_dir, progress_hook),
            lambda: tikwm.download_audio(url, download_dir, progress_hook))
    return _extract_audio(url, download_dir, progress_hook)


def download_video(url, download_dir='downloads', progress_hook=None, telegram=False):
    """
    Tải bản chất lượng tốt nhất.
    telegram=True → ưu tiên H.264 ≤1080p để Telegram phát inline được (bot).
    telegram=False → best thật sự, cho phép AV1/VP9 4K (web tải thẳng).
    """
    if douyin.is_douyin(url):
        return douyin.download(url, download_dir, progress_hook)
    if _is_tiktok(url):
        fmt = _tg_format() if telegram else BEST_FORMAT
        return _tiktok_fallback(
            lambda: _download(url, fmt, download_dir, progress_hook),
            lambda: tikwm.download(url, download_dir, progress_hook))
    fmt = _tg_format() if telegram else BEST_FORMAT
    return _download(url, fmt, download_dir, progress_hook)


def download_height(url, height, download_dir='downloads', progress_hook=None):
    """Tải video ≤ height cụ thể, ưu tiên H.264 (cho bot — Telegram phát được)."""
    if douyin.is_douyin(url):
        return douyin.download(url, download_dir, progress_hook, height=height)
    if _is_tiktok(url):
        return _tiktok_fallback(
            lambda: _download(url, _tg_format(height), download_dir, progress_hook),
            lambda: tikwm.download(url, download_dir, progress_hook))
    return _download(url, _tg_format(height), download_dir, progress_hook)


def download_specific_format(url, format_id, download_dir='downloads', progress_hook=None):
    """Tải theo format_id người dùng chọn (web — giữ đúng format best-quality)."""
    if douyin.is_douyin(url):
        # menu Douyin dùng chính độ phân giải làm format_id
        height = int(format_id) if str(format_id).isdigit() else None
        return douyin.download(url, download_dir, progress_hook, height=height)
    if _is_tiktok(url):
        return _tiktok_fallback(
            lambda: _download(url, f'{format_id}+bestaudio/best' if HAS_FFMPEG
                              else f'{format_id}[acodec!=none]/best',
                              download_dir, progress_hook),
            lambda: tikwm.download(url, download_dir, progress_hook))
    if HAS_FFMPEG:
        return _download(url, f'{format_id}+bestaudio/best', download_dir, progress_hook)
    # Thiếu FFmpeg: format video-only sẽ không có tiếng — ưu tiên bản có sẵn audio
    return _download(url, f'{format_id}[acodec!=none]/best', download_dir, progress_hook)
