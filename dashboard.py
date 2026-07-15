"""Web server local: trang tải video trực tiếp (kiểu cobalt) + dashboard thống kê.

Dùng http.server có sẵn của Python — không cần cài thêm gì.
"""
import json
import logging
import os
import shutil
import threading
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

from yt_dlp.utils import sanitize_filename

import stats
import downloader

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_WEB = os.path.join(BASE_DIR, 'web.html')
HTML_STATS = os.path.join(BASE_DIR, 'dashboard.html')
WEB_DL_DIR = os.path.join(BASE_DIR, 'downloads', 'web')

# Chỉ cho web tải từ các nền tảng quen thuộc — chặn việc lợi dụng server
# tải URL tùy ý (SSRF / proxy chùa)
ALLOWED_HOSTS = (
    'youtube.com', 'youtu.be', 'tiktok.com', 'douyin.com', 'iesdouyin.com',
    'facebook.com', 'fb.watch', 'instagram.com', 'twitter.com', 'x.com',
)

# Render free chỉ có 0.1 CPU / 512MB RAM — giới hạn 2 lượt tải web cùng lúc
_dl_sem = threading.Semaphore(2)

MIME = {
    '.mp4': 'video/mp4', '.webm': 'video/webm', '.mkv': 'video/x-matroska',
    '.mov': 'video/quicktime', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.png': 'image/png', '.webp': 'image/webp',
    '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4',
}


def _host_allowed(url):
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    return any(host == h or host.endswith('.' + h) for h in ALLOWED_HOSTS)


def _friendly(url, error):
    """Bản rút gọn của thông báo lỗi thân thiện cho web (không import bot.py để tránh vòng lặp)."""
    low = str(error).lower()
    if 'douyin' in url.lower() and ('cookie' in low or 'login' in low):
        return 'Douyin đang chặn — video có thể riêng tư, đã bị xóa hoặc là album ảnh.'
    if 'login' in low or 'cookie' in low or 'private' in low:
        return 'Nội dung này riêng tư hoặc yêu cầu đăng nhập — web không tải được.'
    if 'unsupported url' in low:
        return 'Link này chưa được hỗ trợ.'
    if 'unavailable' in low or 'removed' in low or 'does not exist' in low:
        return 'Video không tồn tại hoặc đã bị xóa.'
    return 'Không tải được video này. Thử lại hoặc dùng link khác nhé.'


class _Handler(BaseHTTPRequestHandler):
    # ---------- routing ----------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/api/stats':
            body = json.dumps(stats.snapshot(), ensure_ascii=False).encode('utf-8')
            self._respond(body, 'application/json; charset=utf-8')
        elif path == '/api/download':
            self._download()
        elif path in ('/', '/index.html'):
            self._file(HTML_WEB)
        elif path == '/stats':
            self._file(HTML_STATS)
        else:
            self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == '/api/resolve':
            self._resolve()
        else:
            self.send_error(404)

    # ---------- helpers ----------
    def _respond(self, body, content_type, status=200, extra_headers=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status=200):
        self._respond(json.dumps(obj, ensure_ascii=False).encode('utf-8'),
                      'application/json; charset=utf-8', status)

    def _file(self, path):
        try:
            with open(path, 'rb') as f:
                self._respond(f.read(), 'text/html; charset=utf-8')
        except OSError:
            self.send_error(500, 'Thieu file giao dien')

    def _check_url(self, url):
        """Trả về thông báo lỗi nếu URL không hợp lệ, None nếu OK."""
        if not url.startswith(('http://', 'https://')):
            return 'Link không hợp lệ — hãy dán link đầy đủ bắt đầu bằng https://'
        if not _host_allowed(url):
            return 'Chỉ hỗ trợ YouTube, TikTok, Douyin, Facebook, Instagram và X/Twitter.'
        return None

    # ---------- API ----------
    def _resolve(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(length) or b'{}')
            url = (body.get('url') or '').strip()
        except (ValueError, OSError):
            self._json({'ok': False, 'error': 'Yêu cầu không hợp lệ.'}, 400)
            return

        err = self._check_url(url)
        if err:
            self._json({'ok': False, 'error': err})
            return

        try:
            size_mb, title, formats = downloader.get_video_info(url)
            self._json({
                'ok': True,
                'title': title,
                'size_mb': round(size_mb, 1),
                'platform': stats.detect_platform(url),
                'audio': downloader.HAS_FFMPEG,  # có thể tách MP3 hay không
                'formats': [{
                    'format_id': f['format_id'],
                    'height': f['height'],
                    'size_mb': round(f['filesize'] / 1048576, 1) if f.get('filesize') else None,
                } for f in formats],
            })
        except Exception as e:
            logger.error(f"Web resolve error {url}: {e}")
            self._json({'ok': False, 'error': _friendly(url, e)})

    def _download(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        url = (q.get('url') or [''])[0].strip()
        fmt = (q.get('format') or ['best'])[0]

        err = self._check_url(url)
        if err:
            self._respond(err.encode('utf-8'), 'text/plain; charset=utf-8', 400)
            return

        if not _dl_sem.acquire(blocking=False):
            self._respond('Server đang bận tải video khác, thử lại sau ít phút nhé.'.encode('utf-8'),
                          'text/plain; charset=utf-8', 429)
            return

        file_path = None
        headers_sent = False
        try:
            if fmt == 'best':
                file_path, title = downloader.download_video(url, WEB_DL_DIR)
            elif fmt == 'mp3':
                file_path, title = downloader.download_audio(url, WEB_DL_DIR)
            else:
                file_path, title = downloader.download_specific_format(url, fmt, WEB_DL_DIR)

            size = os.path.getsize(file_path)
            ext = os.path.splitext(file_path)[1].lower()
            nice_name = (sanitize_filename(title, restricted=False)[:60] or 'video').strip() + ext
            quoted = urllib.parse.quote(nice_name)

            self.send_response(200)
            self.send_header('Content-Type', MIME.get(ext, 'application/octet-stream'))
            self.send_header('Content-Length', str(size))
            self.send_header('Content-Disposition',
                             f"attachment; filename=\"video{ext}\"; filename*=UTF-8''{quoted}")
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            headers_sent = True

            with open(file_path, 'rb') as f:
                shutil.copyfileobj(f, self.wfile, 64 * 1024)

            stats.record(url, ok=True, size_mb=size / 1048576, title=title,
                         quality='tốt nhất' if fmt == 'best' else fmt)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            logger.info(f"Web download bị hủy giữa chừng: {url}")
        except Exception as e:
            logger.error(f"Web download error {url}: {e}")
            stats.record(url, ok=False)
            if not headers_sent:
                self._respond(_friendly(url, e).encode('utf-8'), 'text/plain; charset=utf-8', 500)
        finally:
            _dl_sem.release()
            if file_path and os.path.exists(file_path):
                os.remove(file_path)

    def log_message(self, format, *args):
        pass  # không xả log request vào console của bot


def start_dashboard(port=8350, host='127.0.0.1'):
    """Chạy web server trong thread nền; trả về URL hoặc None nếu không mở được port."""
    try:
        server = ThreadingHTTPServer((host, port), _Handler)
    except OSError as e:
        logger.warning(f"Không mở được dashboard trên {host}:{port}: {e}")
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    display_host = '127.0.0.1' if host in ('0.0.0.0', '') else host
    return f'http://{display_host}:{port}'
