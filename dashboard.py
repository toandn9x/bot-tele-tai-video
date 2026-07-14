"""Web dashboard local cho bot — dùng http.server có sẵn, không cần cài thêm gì."""
import json
import logging
import os
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import stats

logger = logging.getLogger(__name__)

HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard.html')


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/stats'):
            body = json.dumps(stats.snapshot(), ensure_ascii=False).encode('utf-8')
            self._respond(body, 'application/json; charset=utf-8')
        elif self.path in ('/', '/index.html') or self.path.startswith('/?'):
            try:
                with open(HTML_FILE, 'rb') as f:
                    self._respond(f.read(), 'text/html; charset=utf-8')
            except OSError:
                self.send_error(500, 'Thieu file dashboard.html')
        else:
            self.send_error(404)

    def _respond(self, body, content_type):
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # không xả log request vào console của bot


def start_dashboard(port=8350, host='127.0.0.1'):
    """Chạy dashboard trong thread nền; trả về URL hoặc None nếu không mở được port."""
    try:
        server = ThreadingHTTPServer((host, port), _Handler)
    except OSError as e:
        logger.warning(f"Không mở được dashboard trên {host}:{port}: {e}")
        return None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    display_host = '127.0.0.1' if host in ('0.0.0.0', '') else host
    return f'http://{display_host}:{port}'
