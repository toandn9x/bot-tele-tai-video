"""Ghi thống kê lượt tải của bot vào stats.json để dashboard hiển thị."""
import json
import os
import threading
import time
from datetime import datetime

STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'stats.json')
RECENT_MAX = 30
START_TIME = time.time()

_lock = threading.Lock()

_PLATFORM_PATTERNS = [
    ('youtu', 'YouTube'),
    ('tiktok', 'TikTok'),
    ('douyin', 'TikTok'),
    ('facebook', 'Facebook'),
    ('fb.watch', 'Facebook'),
    ('instagram', 'Instagram'),
    ('twitter', 'X/Twitter'),
    ('x.com', 'X/Twitter'),
]

_EMPTY = {
    'totals': {'success': 0, 'failed': 0, 'mb': 0.0},
    'platforms': {},   # tên -> {'success', 'failed', 'mb'}
    'daily': {},       # 'YYYY-MM-DD' -> {'success', 'failed'}
    'recent': [],      # mới nhất trước, tối đa RECENT_MAX
}


def detect_platform(url):
    low = url.lower()
    for pattern, name in _PLATFORM_PATTERNS:
        if pattern in low:
            return name
    return 'Khác'


def _load():
    try:
        with open(STATS_FILE, encoding='utf-8') as f:
            data = json.load(f)
        for key, value in _EMPTY.items():
            data.setdefault(key, json.loads(json.dumps(value)))
        return data
    except (OSError, ValueError):
        return json.loads(json.dumps(_EMPTY))


def _save(data):
    tmp = STATS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, STATS_FILE)


def record(url, ok, size_mb=0.0, title='', quality=''):
    """Ghi một lượt tải (thành công hoặc thất bại)."""
    platform = detect_platform(url)
    today = datetime.now().strftime('%Y-%m-%d')
    key = 'success' if ok else 'failed'

    with _lock:
        data = _load()
        data['totals'][key] += 1
        data['totals']['mb'] += size_mb

        plat = data['platforms'].setdefault(platform, {'success': 0, 'failed': 0, 'mb': 0.0})
        plat[key] += 1
        plat['mb'] += size_mb

        day = data['daily'].setdefault(today, {'success': 0, 'failed': 0})
        day[key] += 1
        # Giữ tối đa 60 ngày gần nhất
        if len(data['daily']) > 60:
            for old in sorted(data['daily'])[:-60]:
                del data['daily'][old]

        data['recent'].insert(0, {
            'ts': datetime.now().strftime('%H:%M %d/%m'),
            'title': title[:80],
            'platform': platform,
            'mb': round(size_mb, 1),
            'ok': ok,
            'quality': quality,
        })
        del data['recent'][RECENT_MAX:]
        _save(data)


def snapshot():
    """Ảnh chụp thống kê hiện tại cho API của dashboard."""
    with _lock:
        data = _load()

    totals = data['totals']
    done = totals['success'] + totals['failed']
    today = datetime.now().strftime('%Y-%m-%d')
    today_counts = data['daily'].get(today, {'success': 0, 'failed': 0})

    return {
        'totals': totals,
        'rate': round(totals['success'] / done * 100) if done else None,
        'today': today_counts,
        'daily': data['daily'],
        'platforms': data['platforms'],
        'recent': data['recent'],
        'uptime_seconds': int(time.time() - START_TIME),
    }
