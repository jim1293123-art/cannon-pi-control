"""Loopback-only server; only the UI and its revision are exposed."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

APP_DIR = Path(__file__).resolve().parent


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path not in ('/', '/weather.html', '/revision'):
            self.send_error(404)
            return
        try:
            content = (APP_DIR / 'weather.html').read_bytes()
        except OSError:
            self.send_error(503, 'Weather UI unavailable')
            return
        if path == '/revision':
            content = hashlib.sha256(content).hexdigest().encode('ascii')
        else:
            revision = hashlib.sha256(content).hexdigest()
            content = content.replace(b'</head>', f'<meta name="pi-weather-revision" content="{revision}"></head>'.encode(), 1)
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain' if path == '/revision' else 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
