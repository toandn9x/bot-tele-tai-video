"""Douyin: gọi thẳng API web detail của Douyin thay vì để yt-dlp tự lo.

Vì sao cần module riêng:
- yt-dlp không tải được Douyin — nó cần cookie chữ ký mà chính source của nó
  còn ghi "TODO: Run verification challenge code". Kể cả đưa cookies.txt thật,
  còn tươi, xuất từ trình duyệt cũng vẫn hỏng (yt-dlp issue #9667, #16831).
- Cách cũ (parse window._ROUTER_DATA của trang share iesdouyin) đã chết hẳn:
  Douyin bỏ toàn bộ dữ liệu video khỏi SSR, trang share giờ không còn URL mp4 nào.

Cách làm ở đây: gọi thẳng https://www.douyin.com/aweme/v1/web/aweme/detail/
với cookie `ttwid` — và `ttwid` xin được TỰ ĐỘNG từ endpoint đăng ký của
ByteDance, không cần trình duyệt, không cần đăng nhập, không cần cookies.txt.

Đã đo: chỉ `ttwid` là đủ. `s_v_web_id` không cần, chữ ký `a_bogus` cũng không
cần (đã thử cả 4 tổ hợp có/không). Nhờ vậy module này không kéo thêm dependency
nào — chỉ dùng httpx vốn đã có sẵn theo python-telegram-bot.
"""
import logging
import os
import re
import threading
import time

import httpx
import yt_dlp

logger = logging.getLogger(__name__)

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

DETAIL_API = 'https://www.douyin.com/aweme/v1/web/aweme/detail/'
TTWID_API = 'https://ttwid.bytedance.com/ttwid/union/register/'
TTWID_TTL = 3600  # xin lại mỗi giờ cho chắc, cookie thực tế sống lâu hơn nhiều

# Tham số Douyin bắt buộc phải có, thiếu là trả về body rỗng
_BASE_PARAMS = {
    'device_platform': 'webapp', 'aid': '6383', 'channel': 'channel_pc_web',
    'pc_client_type': '1', 'version_code': '190500', 'version_name': '19.5.0',
    'cookie_enabled': 'true', 'screen_width': '1920', 'screen_height': '1080',
    'browser_language': 'zh-CN', 'browser_platform': 'Win32', 'browser_name': 'Chrome',
    'browser_version': '128.0.0.0', 'browser_online': 'true', 'engine_name': 'Blink',
    'engine_version': '128.0.0.0', 'os_name': 'Windows', 'os_version': '10',
    'cpu_core_num': '8', 'device_memory': '8', 'platform': 'PC',
}

_ttwid_cache = {'value': None, 'ts': 0.0}
_ttwid_lock = threading.Lock()


class DouyinAlbumError(Exception):
    """Bài đăng là album ảnh, không phải video."""


def is_douyin(url):
    low = url.lower()
    return 'douyin.com' in low or 'iesdouyin.com' in low


def _ttwid():
    """
    Xin cookie ttwid từ ByteDance (cache theo TTL).
    Đây là cookie DUY NHẤT mà API detail đòi — không cần đăng nhập.
    """
    # Giữ khoá trong SUỐT lúc gọi mạng, không chỉ lúc đọc/ghi cache: bot tải
    # nhiều link song song nên nhiều luồng cùng miss một lúc là chuyện thường —
    # nhả khoá ra sớm thì mỗi luồng tự bắn một request và nhận một cookie khác
    # nhau, vừa phí vừa dễ bị ByteDance chặn. Luồng đầu xin xong, các luồng còn
    # lại vào là đã có cache.
    with _ttwid_lock:
        cached = _ttwid_cache['value']
        if cached and time.time() - _ttwid_cache['ts'] < TTWID_TTL:
            return cached

        payload = {
            'region': 'cn', 'aid': 1768, 'needFid': False,
            'service': 'www.ixigua.com',
            'migrate_info': {'ticket': '', 'source': 'node'},
            'cbUrlProtocol': 'https', 'union': True,
        }
        resp = httpx.post(TTWID_API, json=payload, timeout=25, headers={'User-Agent': UA})
        set_cookie = resp.headers.get('set-cookie', '')
        if 'ttwid=' not in set_cookie:
            raise RuntimeError('Không xin được cookie ttwid từ ByteDance')

        value = set_cookie.split('ttwid=')[1].split(';')[0]
        _ttwid_cache.update(value=value, ts=time.time())
        return value


def _reset_ttwid():
    """Vứt cookie đang cache để lần gọi sau xin cookie mới."""
    with _ttwid_lock:
        _ttwid_cache.update(value=None, ts=0.0)


def _aweme_id(url):
    """Lấy aweme_id; link rút gọn v.douyin.com thì phải đi theo redirect."""
    match = re.search(r'/(?:video|note|slides)/(\d+)', url)
    if match:
        return match.group(1)
    resp = httpx.get(url, headers={'User-Agent': UA}, follow_redirects=True, timeout=20)
    match = re.search(r'/(?:video|note|slides)/(\d+)', str(resp.url))
    if match:
        return match.group(1)
    match = re.search(r'(\d{15,})', str(resp.url))
    if match:
        return match.group(1)
    raise ValueError('Không tìm được ID video trong link Douyin này')


def _fetch_detail(aweme_id):
    """Gọi API detail. Douyin chặn bằng cách trả HTTP 200 kèm body RỖNG."""
    params = dict(_BASE_PARAMS, aweme_id=aweme_id)
    resp = httpx.get(
        DETAIL_API, params=params, timeout=30,
        cookies={'ttwid': _ttwid()},
        headers={'User-Agent': UA, 'Referer': f'https://www.douyin.com/video/{aweme_id}'},
    )
    if not resp.text.strip():
        raise RuntimeError('empty')
    detail = resp.json().get('aweme_detail')
    if not detail:
        raise RuntimeError('empty')
    return detail


def get_detail(url):
    """
    Trả về thông tin video đã chuẩn hoá.
    Body rỗng = bị chặn → xin ttwid mới rồi thử lại một lần.
    """
    aweme_id = _aweme_id(url)
    try:
        detail = _fetch_detail(aweme_id)
    except RuntimeError:
        logger.info('Douyin trả về rỗng, xin ttwid mới rồi thử lại')
        _reset_ttwid()
        try:
            detail = _fetch_detail(aweme_id)
        except RuntimeError:
            raise RuntimeError(
                'Douyin từ chối trả dữ liệu (video có thể riêng tư, đã bị xóa, '
                'hoặc Douyin vừa siết chặn)')

    video = detail.get('video') or {}
    images = detail.get('images') or []
    title = (detail.get('desc') or '').strip() or 'Video Douyin'

    return {
        'id': aweme_id,
        'title': title,
        'author': ((detail.get('author') or {}).get('nickname') or '').strip(),
        'duration': (video.get('duration') or 0) / 1000,
        'is_album': bool(images) and not (video.get('play_addr') or {}).get('url_list'),
        'images': [i['url_list'][0] for i in images if i.get('url_list')],
        'formats': _formats(video),
        'music': ((((detail.get('music') or {}).get('play_url')) or {}).get('url_list') or [None])[0],
    }


def _formats(video):
    """
    Chuẩn hoá mảng bit_rate thành danh sách format.

    Bỏ bản `dash` (không tải thẳng một file được), chỉ giữ `mp4`.
    Nhãn chất lượng lấy min(rộng, cao) để video dọc lẫn ngang đều hiện đúng
    (1080x1920 và 1920x1080 đều là "1080p").
    """
    out = {}
    for item in video.get('bit_rate') or []:
        if item.get('format') != 'mp4':
            continue
        addr = item.get('play_addr') or {}
        urls = addr.get('url_list') or []
        width, height = addr.get('width'), addr.get('height')
        if not urls or not width or not height:
            continue

        label = min(width, height)
        codec = 'h265' if item.get('is_h265') else 'h264'
        size = addr.get('data_size') or 0
        gear = item.get('gear_name') or ''
        # Giữ mọi mức bitrate (mỗi gear một bản) để ladder() còn chỗ mà chọn
        key = (label, codec, gear)
        if key not in out or size > out[key]['filesize']:
            out[key] = {
                'label': label, 'width': width, 'height': height,
                # Giữ CẢ danh sách: Douyin trả 2-3 nút CDN cho mỗi bản, và một
                # nút lẻ trả 403 là chuyện thường. Có nút dự phòng thì không
                # hỏng cả lượt tải.
                'filesize': size, 'urls': urls, 'codec': codec, 'gear': gear,
            }

    # Bản dự phòng khi bit_rate rỗng
    if not out:
        addr = video.get('play_addr') or {}
        urls = addr.get('url_list') or []
        if urls:
            width = addr.get('width') or 0
            height = addr.get('height') or 0
            out[(min(width, height) or 0, 'h264')] = {
                'label': min(width, height) or 0, 'width': width, 'height': height,
                'filesize': addr.get('data_size') or 0, 'urls': urls,
                'codec': 'h264', 'gear': '',
            }

    return sorted(out.values(), key=lambda f: (f['label'], f['filesize']), reverse=True)


def ladder(formats, prefer_h264=True):
    """
    Thang chất lượng: mỗi độ phân giải đúng một lựa chọn, dung lượng giảm dần
    theo độ phân giải.

    Cần thiết vì Douyin trả nhiều "gear" cùng một độ phân giải với bitrate rất
    khác nhau — chọn bừa bản nặng nhất sẽ ra menu kiểu 576p (43MB) nặng hơn
    720p (40MB), người dùng chọn thấp hơn lại tải file to hơn.
    Ở đây duyệt từ cao xuống, mỗi bậc lấy bản đẹp nhất còn NHẸ HƠN bậc trên.

    prefer_h264=True (gửi Telegram): chỉ lấy H.264 — Telegram hay treo với
    H.265, cùng lý do BEST_FORMAT của bot đã tránh AV1/VP9 từ trước.
    """
    pool = [f for f in formats if f['codec'] == 'h264'] if prefer_h264 else list(formats)
    if not pool:
        pool = list(formats)

    out, cap = [], float('inf')
    for label in sorted({f['label'] for f in pool}, reverse=True):
        same = [f for f in pool if f['label'] == label]
        lighter = [f for f in same if (f['filesize'] or 0) < cap]
        chosen = (max(lighter, key=lambda f: f['filesize'] or 0) if lighter
                  else min(same, key=lambda f: f['filesize'] or 0))
        out.append(chosen)
        cap = chosen['filesize'] or cap
    return out


def pick_format(formats, height=None, prefer_h264=True):
    """Chọn một bậc trong thang chất lượng (≤ height nếu có chỉ định)."""
    steps = ladder(formats, prefer_h264=prefer_h264)
    if not steps:
        raise ValueError('Không có định dạng tải được cho video Douyin này')
    if height:
        fit = [f for f in steps if f['label'] <= height]
        if fit:
            return fit[0]           # đã sắp giảm dần nên phần tử đầu là cao nhất
        return steps[-1]            # yêu cầu thấp hơn mọi bậc → lấy bậc thấp nhất
    return steps[0]


def video_info(url):
    """Khớp chữ ký get_video_info() của downloader: (best_mb, title, formats_menu)."""
    detail = get_detail(url)
    _guard_album(detail)

    steps = ladder(detail['formats'], prefer_h264=True)
    if not steps:
        raise ValueError('Không có định dạng tải được cho video Douyin này')

    menu = [{
        'height': f['label'],
        'format_id': str(f['label']),   # menu Douyin dùng độ phân giải làm id
        'ext': 'mp4',
        'filesize': f['filesize'] or None,
    } for f in steps[:5]]

    return (steps[0]['filesize'] or 0) / (1024 * 1024), detail['title'], menu


def _ydl_opts(detail, download_dir, progress_hook, suffix):
    opts = {
        'quiet': True, 'no_warnings': True, 'noprogress': True,
        'outtmpl': f'{download_dir}/douyin_{detail["id"]}_{suffix}.%(ext)s',
        # CDN của Douyin từ chối request không có Referer
        'http_headers': {'User-Agent': UA, 'Referer': 'https://www.douyin.com/'},
        'retries': 3, 'fragment_retries': 3, 'socket_timeout': 30,
    }
    if progress_hook:
        opts['progress_hooks'] = [progress_hook]
    return opts


def _run(opts, target_url, title):
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target_url, download=True)
        downloads = info.get('requested_downloads') or []
        if downloads and downloads[0].get('filepath'):
            return downloads[0]['filepath'], title
        return ydl.prepare_filename(info), title


# Lỗi CDN nhất thời — đổi nút khác hoặc xin link mới là qua
_CDN_TRANSIENT = ('403', 'forbidden', '404', 'not found', 'unable to download video data',
                  'timed out', 'timeout', 'connection', 'remote end closed')


def _is_transient(error):
    low = str(error).lower()
    return any(s in low for s in _CDN_TRANSIENT)


def _download_any(urls, opts, title, what='video'):
    """Thử lần lượt từng nút CDN, chỉ bỏ cuộc khi hết đường."""
    last = None
    for i, target in enumerate(urls, 1):
        try:
            return _run(opts, target, title)
        except Exception as e:
            last = e
            if not _is_transient(e):
                raise
            logger.info(f"Nút CDN {i}/{len(urls)} lỗi khi tải {what} "
                        f"({str(e)[:60]}), thử nút tiếp theo")
    raise last if last else RuntimeError('Không có URL nào để tải')


def _fetch_and_download(url, build):
    """
    Tải với link đang có; hỏng hết nút CDN thì xin lại detail để có link KÝ MỚI
    rồi thử lại một vòng.

    Link CDN của Douyin có chữ ký kèm hạn dùng, nên link cũ 403 là bình thường —
    đây là lý do "thử lại lần 2 thì được".
    """
    last = None
    for attempt in range(2):
        detail = get_detail(url)
        try:
            return build(detail)
        except Exception as e:
            last = e
            if attempt == 0 and _is_transient(e):
                logger.info('Hỏng hết nút CDN, xin link ký mới rồi thử lại')
                continue
            raise
    raise last


def _guard_album(detail, what='video'):
    if detail['is_album']:
        raise DouyinAlbumError(
            f"Đây là album ảnh ({len(detail['images'])} ảnh), không phải {what} — "
            f"bot chưa hỗ trợ tải album Douyin.")


def download(url, download_dir='downloads', progress_hook=None,
             height=None, prefer_h264=True):
    """Tải video Douyin (bản không watermark) qua URL trực tiếp từ API."""
    def build(detail):
        _guard_album(detail)
        fmt = pick_format(detail['formats'], height=height, prefer_h264=prefer_h264)
        os.makedirs(download_dir, exist_ok=True)
        opts = _ydl_opts(detail, download_dir, progress_hook, f'{fmt["label"]}p')
        return _download_any(fmt['urls'], opts, detail['title'])

    return _fetch_and_download(url, build)


def download_audio(url, download_dir='downloads', progress_hook=None):
    """Tách MP3 từ chính video (không dùng link nhạc nền — có thể khác tiếng gốc)."""
    def build(detail):
        _guard_album(detail, 'video để tách nhạc')
        fmt = pick_format(detail['formats'], prefer_h264=True)
        os.makedirs(download_dir, exist_ok=True)
        opts = _ydl_opts(detail, download_dir, progress_hook, 'audio')
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192',
        }]
        path, title = _download_any(fmt['urls'], opts, detail['title'], what='nhạc')
        mp3 = os.path.splitext(path)[0] + '.mp3'
        return (mp3 if os.path.exists(mp3) else path), title

    return _fetch_and_download(url, build)
