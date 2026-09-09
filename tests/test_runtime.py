import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

import server
from validate_weather import validate

ROOT = Path(__file__).resolve().parents[1]


class ValidationTests(unittest.TestCase):
    def test_real_ui(self):
        validate(ROOT / 'weather.html')

    def test_invalid_downloads(self):
        real = (ROOT / 'weather.html').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weather.html'
            for data in (b'', b'404: Not Found', b'\xff' * 2000,
                         real[:4000].encode(), real.replace('pi-weather-app', 'error-page').encode(),
                         real.replace('id="daily"', 'id="wrong"').encode(), b'x' * 2_000_001):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    validate(path)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def test_revision_matches_served_document(self):
        digest = hashlib.sha256((ROOT / 'weather.html').read_bytes()).hexdigest()
        with urlopen(self.base + '/revision') as response:
            self.assertEqual(response.read().decode(), digest)
        with urlopen(self.base + '/weather.html') as response:
            self.assertIn(f'content="{digest}"'.encode(), response.read())
            self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_private_files_not_served(self):
        for path in ('/update.sh', '/chromium-profile/Preferences', '/../README.md'):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()


@unittest.skipUnless(os.name == 'posix' and os.geteuid() != 0 and shutil.which('flock'),
                     'Updater integration requires non-root Linux with flock')
class UpdaterTests(unittest.TestCase):
    def test_atomic_failure_and_change_handling(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            app = home / 'pi-weather'
            app.mkdir()
            for name in ('update.sh', 'validate_weather.py', 'weather.html'):
                shutil.copy(ROOT / name, app / name)
            binaries = home / 'bin'
            binaries.mkdir()
            curl = binaries / 'curl'
            curl.write_text('#!/bin/bash\nwhile [[ $# -gt 0 ]]; do if [[ $1 == -o ]]; then shift; out=$1; fi; shift; done\ncp "$PAYLOAD" "$out"\nexit "${CURL_EXIT:-0}"\n')
            curl.chmod(0o755)
            payload = home / 'payload'
            live = app / 'weather.html'
            original = live.read_bytes()
            before = live.stat().st_mtime_ns
            env = {**os.environ, 'HOME': str(home), 'PATH': str(binaries) + ':' + os.environ['PATH'], 'PAYLOAD': str(payload)}
            for data, exit_code in ((b'', '0'), (b'404 Not Found', '0'), (original[:4000], '0'), (original, '22')):
                payload.write_bytes(data)
                result = subprocess.run(['bash', str(app / 'update.sh')], env={**env, 'CURL_EXIT': exit_code}, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(live.read_bytes(), original)
                self.assertEqual(live.stat().st_mtime_ns, before)
            payload.write_bytes(original)
            subprocess.run(['bash', str(app / 'update.sh')], env=env, check=True)
            self.assertEqual(live.stat().st_mtime_ns, before)
            changed = original.replace(b'Cannon Weather', b'Cannon Weather Updated')
            payload.write_bytes(changed)
            subprocess.run(['bash', str(app / 'update.sh')], env=env, check=True)
            self.assertEqual(live.read_bytes(), changed)
            self.assertEqual(list(app.glob('.weather.*')), [])


if __name__ == '__main__':
    unittest.main()
