"""ZIP v2 backend, restricted to the UI, revision and authenticated kiosk exit."""
import hashlib
import hmac
import json
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

APP_DIR = Path(__file__).resolve().parent
EXIT_TOKEN = secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    def send_body(self, code, content, content_type='text/plain; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def local_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.local_host():
            self.send_error(403)
            return
        path = urlsplit(self.path).path
        if path == '/health':
            self.send_body(200, json.dumps({'version': 2, 'exit': True}).encode(), 'application/json')
            return
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
            content = content.replace(b'</head>', (f'<meta name="pi-weather-revision" content="{revision}">'
                                      f'<meta name="pi-weather-exit-token" content="{EXIT_TOKEN}"></head>').encode(), 1)
        self.send_body(200, content, 'text/plain' if path == '/revision' else 'text/html; charset=utf-8')

    def do_POST(self):
        if urlsplit(self.path).path != '/exit':
            self.send_error(404)
            return
        origin = f'http://127.0.0.1:{self.server.server_port}'
        if (not self.local_host() or self.headers.get('Origin') != origin
                or not hmac.compare_digest(self.headers.get('X-Weather-Token', ''), EXIT_TOKEN)):
            self.send_error(403, 'Exit requires the local weather page')
            return
        try:
            # Stopping the unit suppresses Restart= and targets its cgroup only.
            # No pkill, shell, root privileges, or unrelated browser processes.
            subprocess.run(['systemctl', '--user', '--no-block', 'stop',
                            'pi-weather-kiosk.service'], check=True, timeout=10,
                           capture_output=True)
        except (OSError, subprocess.SubprocessError):
            self.send_body(503, b'Could not stop the weather kiosk service')
            return
        self.send_body(202, b'Weather kiosk stopping')


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
