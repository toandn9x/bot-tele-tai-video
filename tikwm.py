"""TikWM: đường dự phòng cho TikTok khi IP máy chủ bị TikTok chặn.

Vì sao cần: trên Render mọi người dùng bot chia sẻ CHUNG một IP datacenter, nên
TikTok rất dễ trả "Your IP address is blocked" cho cả bot. Lúc đó yt-dlp bó tay
vì request đi từ chính IP đó. TikWM tải hộ bằng hạ tầng của họ nên không dính.

Đây chỉ là DỰ PHÒNG — đường chính vẫn là yt-dlp + curl_cffi (tự chủ, đủ mức
chất lượng). Tắt bằng biến môi trường USE_TIKWM=0.

Đánh đổi cần biết: là dịch vụ bên thứ ba (có thể biến mất bất cứ lúc nào), giới
hạn 1 request/giây, và link người dùng gửi sẽ đi qua máy chủ của họ.
"""
import logging
import os
import threading
import time

import httpx

logger = logging.getLogger(__name__)

API = 'https://www.tikwm.com/api/'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
MIN_INTERVAL = 1.2  # TikWM giới hạn 1 req/giây — tự giữ nhịp để không bị khoá

_last_call = [0.0]
_throttle = threading.Lock()


def enabled():
    return os.getenv('USE_TIKWM', '1') == '1'


def is_tiktok(url):
    return 'tiktok.com' in url.lower()   # bao gồm cả vm./vt.tiktok.com


def _throttled_post(url):
    with _throttle:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        try:
            return httpx.post(API, data={'url': url, 'hd': 1}, timeout=45,
                              headers={'User-Agent': UA})
        finally:
            _last_call[0] = time.monotonic()


def get_detail(url):
    """Hỏi TikWM thông tin video. Ném lỗi nếu không lấy được."""
    resp = _throttled_post(url)
    resp.raise_for_status()
    body = resp.json()
    if body.get('code') != 0 or not body.get('data'):
        raise RuntimeError(f"TikWM không xử lý được link ({body.get('msg') or 'không rõ lý do'})")

    data = body['data']
    # Cả hai đều không watermark. Khác nhau ở CODEC — đã tải về ffprobe kiểm chứng:
    #   play   -> H.264 576x1024  ✅ Telegram phát inline được
    #   hdplay -> HEVC  1080x1920 ❌ Telegram hay treo, Windows cũng cần HEVC add-on
    # Nên xếp bản H.264 lên đầu và luôn ưu tiên nó. Đây là suy luận theo quy ước
    # CDN của TikTok, không phải TikWM công bố — nếu một ngày họ đổi thì chỉ là
    # mất ưu thế codec, không làm hỏng luồng tải.
    formats = []
    if data.get('play'):
        formats.append({'label': 'sd', 'url': data['play'],
                        'filesize': data.get('size') or 0, 'safe': True})
    if data.get('hdplay'):
        formats.append({'label': 'hd', 'url': data['hdplay'],
                        'filesize': data.get('hd_size') or 0, 'safe': False})
    if not formats:
        raise RuntimeError('TikWM không trả về link video nào')

    return {
        'id': str(data.get('id') or ''),
        'title': (data.get('title') or '').strip() or 'Video TikTok',
        'author': ((data.get('author') or {}).get('nickname') or '').strip(),
        'duration': data.get('duration') or 0,
        'formats': formats,
        'music': data.get('music'),
        'images': data.get('images') or [],
    }


def _best(detail):
    """Bản sẽ tải: luôn ưu tiên codec an toàn để mọi nơi phát được."""
    safe = [f for f in detail['formats'] if f.get('safe')]
    return (safe or detail['formats'])[0]


def video_info(url):
    """
    Khớp chữ ký get_video_info(): (best_mb, title, formats_menu).
    Menu rỗng vì TikWM chỉ có một bản dùng được — bot sẽ chỉ hiện nút "tốt nhất",
    và dung lượng báo ở đây đúng bằng bản thực sự tải về.
    """
    detail = get_detail(url)
    return (_best(detail)['filesize'] or 0) / (1024 * 1024), detail['title'], []


def _download(target_url, download_dir, progress_hook, name, title, audio=False):
    import yt_dlp
    os.makedirs(download_dir, exist_ok=True)
    opts = {
        'quiet': True, 'no_warnings': True, 'noprogress': True,
        'outtmpl': f'{download_dir}/{name}.%(ext)s',
        'http_headers': {'User-Agent': UA, 'Referer': 'https://www.tiktok.com/'},
    }
    if progress_hook:
        opts['progress_hooks'] = [progress_hook]
    if audio:
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192',
        }]

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target_url, download=True)
        downloads = info.get('requested_downloads') or []
        path = downloads[0]['filepath'] if downloads and downloads[0].get('filepath') \
            else ydl.prepare_filename(info)

    if audio:
        mp3 = os.path.splitext(path)[0] + '.mp3'
        if os.path.exists(mp3):
            path = mp3
    return path, title


def download(url, download_dir='downloads', progress_hook=None):
    detail = get_detail(url)
    return _download(_best(detail)['url'], download_dir, progress_hook,
                     f"tiktok_{detail['id'] or 'video'}", detail['title'])


def download_audio(url, download_dir='downloads', progress_hook=None):
    detail = get_detail(url)
    # music là link mp3 sẵn của TikTok; không có thì tách từ video
    target = detail['music'] or _best(detail)['url']
    return _download(target, download_dir, progress_hook,
                     f"tiktok_{detail['id'] or 'audio'}", detail['title'], audio=True)
