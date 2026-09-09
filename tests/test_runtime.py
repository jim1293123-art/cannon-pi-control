import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import configure_startup
import release_update as updater
import server
from validate_weather import validate

ROOT = Path(__file__).resolve().parents[1]


def payloads():
    result = {name: (ROOT / name).read_bytes() for name in updater.FILES}
    result['release.json'] = json.dumps({'schema': 1, 'files': {
        name: updater.digest(value) for name, value in result.items()}}).encode()
    return result


def change(files, name, content):
    files[name] = content
    files['release.json'] = json.dumps({'schema': 1, 'files': {
        key: updater.digest(files[key]) for key in updater.FILES}}).encode()


class ValidationTests(unittest.TestCase):
    def test_real_ui(self):
        validate(ROOT / 'weather.html')

    def test_invalid_downloads(self):
        real = (ROOT / 'weather.html').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'weather.html'
            for data in (b'', b'404: Not Found', b'\xff' * 2000,
                         real[:4000].encode(), real.replace('pi-weather-app', 'error-page').encode(),
                         real.replace('id="exitDesktop"', 'id="wrong"').encode(), b'x' * 2_000_001):
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
            content = response.read()
            self.assertIn(f'content="{digest}"'.encode(), content)
            self.assertIn(server.EXIT_TOKEN.encode(), content)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def assert_http_error(self, request, code):
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, code)
        error.exception.close()

    def test_private_files_and_get_exit_not_served(self):
        for path in ('/update.sh', '/chromium-profile/Preferences', '/../README.md', '/exit'):
            self.assert_http_error(self.base + path, 404)

    def test_exit_stops_only_systemd_kiosk(self):
        request = Request(self.base + '/exit', method='POST', headers={
            'Origin': self.base, 'X-Weather-Token': server.EXIT_TOKEN})
        with patch('server.subprocess.run') as run:
            with urlopen(request) as response:
                self.assertEqual(response.status, 202)
            self.assertEqual(run.call_args.args[0], ['systemctl', '--user', '--no-block', 'stop', 'pi-weather-kiosk.service'])
            self.assertEqual(run.call_count, 1)

    def test_exit_rejects_other_origins_and_missing_token(self):
        with patch('server.subprocess.run') as run:
            for headers in ({}, {'Origin': self.base}, {'Origin': 'https://example.com', 'X-Weather-Token': server.EXIT_TOKEN},
                            {'Origin': self.base, 'X-Weather-Token': server.EXIT_TOKEN, 'Host': 'evil.example'}):
                self.assert_http_error(Request(self.base + '/exit', method='POST', headers=headers), 403)
            run.assert_not_called()

    def test_exit_reports_service_failure(self):
        with patch('server.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'systemctl')):
            self.assert_http_error(Request(self.base + '/exit', method='POST', headers={
                'Origin': self.base, 'X-Weather-Token': server.EXIT_TOKEN}), 503)


class StartupTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix' and os.geteuid() != 0, 'Non-root Linux launcher test')
    def test_launcher_uses_local_270_and_dedicated_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            app = home / 'pi-weather'
            app.mkdir()
            (app / 'rotation').write_text('270\n')
            binaries = home / 'bin'
            binaries.mkdir()
            scripts = {
                'wlr-randr': '#!/bin/bash\nif [[ $# == 0 ]]; then echo "DSI-1 Touch Display"; else printf "%s\\n" "$*" >> "$HOME/rotation-log"; fi\n',
                'curl': '#!/bin/bash\nexit 0\n',
                'chromium': '#!/bin/bash\nprintf "%s\\n" "$*" > "$HOME/chromium-log"\n',
            }
            for name, body in scripts.items():
                (binaries / name).write_text(body)
                (binaries / name).chmod(0o755)
            subprocess.run(['bash', str(ROOT / 'kiosk.sh')], env={**os.environ, 'HOME': str(home),
                           'WAYLAND_DISPLAY': 'wayland-0', 'PATH': str(binaries) + ':' + os.environ['PATH']}, check=True)
            self.assertIn('--transform 270', (home / 'rotation-log').read_text())
            args = (home / 'chromium-log').read_text()
            self.assertIn('--password-store=basic', args)
            self.assertIn('--user-data-dir=' + str(app / 'chromium-profile'), args)
            self.assertIn('http://127.0.0.1:8765/weather.html', args)
            self.assertEqual((app / 'rotation').read_text(), '270\n')

    def test_migration_removes_duplicates_preserves_other_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            labwc = home / '.config/labwc/autostart'
            labwc.parent.mkdir(parents=True)
            original = 'panel &\n~/pi-weather/start-weather.sh &\n"$HOME/pi-weather/desktop-start.sh" & # pi-weather\nchromium --kiosk http://127.0.0.1:8765/weather.html &\n'
            labwc.write_text(original)
            desktop = home / '.config/autostart/weather.desktop'
            desktop.parent.mkdir(parents=True)
            desktop.write_text('[Desktop Entry]\nType=Application\nExec=/home/cannon/pi-weather/start-weather.sh\n')
            configure_startup.configure(home)
            once = labwc.read_text()
            configure_startup.configure(home)
            self.assertEqual(labwc.read_text(), once)
            self.assertEqual(once.count(configure_startup.BRIDGE), 1)
            self.assertNotIn('start-weather.sh', once)
            self.assertNotIn('chromium', once)
            self.assertIn('panel &', once)
            self.assertIn('Hidden=true', desktop.read_text())
            self.assertEqual(labwc.with_name('autostart.before-weather-v2').read_text(), original)

    def test_launcher_contract(self):
        kiosk = (ROOT / 'kiosk.sh').read_text()
        self.assertIn('--password-store=basic', kiosk)
        self.assertIn('$HOME/pi-weather/rotation', kiosk)
        self.assertNotIn('rotation=90', kiosk)
        self.assertIn('http://127.0.0.1:8765/weather.html', kiosk)
        unit = (ROOT / 'systemd/pi-weather-kiosk.service').read_text()
        self.assertIn('Wants=pi-weather-server.service', unit)
        self.assertNotIn('Requires=', unit)
        self.assertIn('KillMode=control-group', unit)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.files = payloads()
        self.control = patch.object(updater, 'systemctl').start()
        self.health = patch.object(updater, 'check_server').start()
        # bash syntax checks run separately and in Linux CI.
        self.syntax = patch.object(updater.subprocess, 'run').start() if os.name == 'nt' else None
        self.addCleanup(patch.stopall)
        updater.apply_release(self.home, lambda name, stamp: self.files[name], installing=True)
        self.app = self.home / 'pi-weather'
        (self.app / 'rotation').write_text('270\n')
        (self.app / 'chromium-profile').mkdir()
        (self.app / 'chromium-profile/Preferences').write_text('my preferences')
        self.control.reset_mock()

    def update(self):
        updater.apply_release(self.home, lambda name, stamp: self.files[name])

    def test_no_change_and_user_settings_preserved(self):
        before = (self.app / 'weather.html').stat().st_mtime_ns
        self.update()
        self.assertEqual((self.app / 'weather.html').stat().st_mtime_ns, before)
        self.control.assert_not_called()
        change(self.files, 'weather.html', self.files['weather.html'].replace(b'Cannon Weather</title>', b'Cannon Weather updated</title>'))
        self.update()
        self.assertEqual((self.app / 'rotation').read_text(), '270\n')
        self.assertEqual((self.app / 'chromium-profile/Preferences').read_text(), 'my preferences')
        self.assertIn('--password-store=basic', (self.app / 'kiosk.sh').read_text())
        self.assertFalse((self.home / '.config/labwc').exists())
        self.control.assert_not_called()  # HTML updates reload via /revision.

    def test_bad_or_mixed_download_does_not_replace_any_file(self):
        original = (self.app / 'weather.html').read_bytes()
        change(self.files, 'weather.html', original.replace(b'Cannon Weather</title>', b'New weather</title>'))
        self.files['server.py'] = b''  # Simulate a failed / mixed-commit response.
        with self.assertRaises(ValueError):
            self.update()
        self.assertEqual((self.app / 'weather.html').read_bytes(), original)
        self.control.assert_not_called()

    def test_invalid_python_and_lost_password_store_are_rejected(self):
        for name, value in [('server.py', b'def invalid('), ('kiosk.sh', self.files['kiosk.sh'].replace(b'--password-store=basic', b''))]:
            good = self.files[name]
            change(self.files, name, value)
            with self.assertRaises((SyntaxError, ValueError)):
                self.update()
            self.assertEqual((self.app / name).read_bytes(), good)
            change(self.files, name, good)

    def test_backend_restart_and_rollback(self):
        original = (self.app / 'server.py').read_bytes()
        change(self.files, 'server.py', original + b'\n# new backend\n')
        self.health.side_effect = RuntimeError('health failed')
        with self.assertRaises(RuntimeError):
            self.update()
        self.assertEqual((self.app / 'server.py').read_bytes(), original)
        self.assertFalse((self.app / '.update-pending.json').exists())
        self.health.side_effect = None
        self.control.reset_mock()
        self.update()
        self.control.assert_called_once_with('restart', 'pi-weather-server.service')

    def test_kiosk_updates_use_try_restart_never_start(self):
        change(self.files, 'kiosk.sh', self.files['kiosk.sh'] + b'\n# new launcher\n')
        self.update()
        self.control.assert_called_once_with('try-restart', 'pi-weather-kiosk.service')

    def test_interrupted_update_is_recovered_before_next_download(self):
        original = (self.app / 'server.py').read_bytes()
        backup = self.app / '.update-backup/server.py'
        backup.parent.mkdir(exist_ok=True)
        backup.write_bytes(original)
        (self.app / '.update-pending.json').write_text(json.dumps({'server.py': 0o644}))
        (self.app / 'server.py').write_text('incomplete interrupted update')
        self.update()
        self.assertEqual((self.app / 'server.py').read_bytes(), original)
        self.assertFalse((self.app / '.update-pending.json').exists())
        self.assertNotIn(('start', 'pi-weather-kiosk.service'), [call.args for call in self.control.call_args_list])

    def test_manifest_cannot_manage_rotation_or_traverse_paths(self):
        manifest = json.loads(self.files['release.json'])
        for name in ('rotation', '../.bashrc'):
            manifest['files'][name] = '0' * 64
            with self.assertRaises(ValueError):
                updater.parse_manifest(json.dumps(manifest))
            del manifest['files'][name]


if __name__ == '__main__':
    unittest.main()
